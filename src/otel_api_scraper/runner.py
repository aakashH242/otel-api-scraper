"""Entrypoint wiring together config, engine, telemetry, and scheduler."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import suppress

import uvicorn
from dotenv import load_dotenv

from .admin_api import build_admin_app
from .config import AppConfig, load_config
from .fingerprints import build_store
from .http_client import AsyncHttpClient
from .pipeline import RecordPipeline
from .scheduler import ScraperScheduler
from .scraper_engine import ScraperEngine
from .state import build_state_store
from .telemetry import Telemetry
from .utils import utc_now


def setup_logging(level: str) -> None:
    """Configure base logging."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    logging.getLogger().setLevel(numeric)


async def _cleanup_loop(
    store, interval: int, telemetry: Telemetry | None, backend: str
) -> None:
    """Periodic cleanup loop for fingerprint store."""
    while True:
        try:
            start = utc_now()
            await asyncio.sleep(interval)
            cleaned = None
            result = await store.cleanup()
            if isinstance(result, int):
                cleaned = result
            duration = (utc_now() - start).total_seconds()
            if telemetry:
                telemetry.record_cleanup(
                    "fingerprint_cleanup", backend, duration, cleaned
                )
            logging.getLogger(__name__).debug("Ran fingerprint cleanup cycle")
        except asyncio.CancelledError:
            return
        except Exception as exc:
            duration = (
                (utc_now() - start).total_seconds() if "start" in locals() else 0.0
            )
            if telemetry:
                telemetry.record_cleanup("fingerprint_cleanup", backend, duration, None)
            logging.getLogger(__name__).warning("Cleanup loop error: %s", exc)


async def async_main(config_path: str) -> None:
    """Async entrypoint loading config and running scheduler."""
    app_config: AppConfig = load_config(config_path)
    setup_logging(app_config.scraper.logLevel)
    logging.getLogger(__name__).debug("Loaded config from %s", config_path)

    if app_config.scraper.enableAdminApi:
        secret_env = app_config.scraper.adminSecretEnv
        if not secret_env:
            raise ValueError(
                "enableAdminApi=true requires scraper.adminSecretEnv to be set to an env var name"
            )
        if secret_env not in os.environ:
            raise ValueError(
                f"enableAdminApi=true requires environment variable '{secret_env}' to be set for admin authentication"
            )

    fingerprint_store = build_store(app_config.scraper.fingerprintStore)
    state_store = build_state_store(app_config.scraper.fingerprintStore)
    pipeline = RecordPipeline(fingerprint_store, app_config.scraper.fingerprintStore)
    telemetry = Telemetry(app_config.scraper)
    http_client = AsyncHttpClient(
        app_config.scraper.maxGlobalConcurrency, app_config.scraper.enforceTls
    )
    engine = ScraperEngine(app_config, http_client, pipeline, telemetry, state_store)
    engine_scheduler = ScraperScheduler(app_config, engine)

    active_sources = {src.name for src in app_config.sources}
    start_cleanup = utc_now()
    await fingerprint_store.cleanup_orphans(active_sources)
    orphan_duration = (utc_now() - start_cleanup).total_seconds()
    logging.getLogger(__name__).debug(
        "Cleaned orphan fingerprints for sources: %s", active_sources
    )
    telemetry.record_cleanup(
        "orphan_cleanup",
        app_config.scraper.fingerprintStore.backend,
        orphan_duration,
        cleaned=None,
    )

    cleanup_task = asyncio.create_task(
        _cleanup_loop(
            fingerprint_store,
            app_config.scraper.fingerprintStore.cleanupIntervalSeconds,
            telemetry,
            app_config.scraper.fingerprintStore.backend,
        )
    )

    admin_server_task = None
    if app_config.scraper.enableAdminApi:
        admin_app = build_admin_app(app_config, engine)
        uv_config = uvicorn.Config(
            admin_app,
            host="0.0.0.0",
            port=app_config.scraper.servicePort,
            log_level=app_config.scraper.logLevel.lower(),
        )
        admin_server = uvicorn.Server(uv_config)
        admin_server_task = asyncio.create_task(admin_server.serve())

        # Fail fast if admin API cannot bind.
        def _handle_server_error(task: asyncio.Task) -> None:
            exc = task.exception()
            if exc:
                logging.getLogger(__name__).error("Admin API failed to start: %s", exc)
                raise exc

        admin_server_task.add_done_callback(_handle_server_error)

    engine_scheduler.start()
    await engine_scheduler.run_all_once()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        cleanup_task.cancel()
        if admin_server_task:
            admin_server_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        if admin_server_task:
            with suppress(asyncio.CancelledError):
                await admin_server_task
        await engine_scheduler.shutdown(app_config.scraper.terminateGracefully)
        await http_client.close()
        await telemetry.shutdown()
        await fingerprint_store.close()
        await state_store.close()


def main() -> None:
    """CLI entrypoint."""
    load_dotenv()
    config_path = os.environ.get("SCRAPER_CONFIG", "config.yaml")
    try:
        asyncio.run(async_main(config_path))
    except FileNotFoundError:
        print(f"Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Scraper failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
