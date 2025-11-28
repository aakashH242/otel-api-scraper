"""FastAPI admin endpoints for manual control."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from . import config as cfg
from .scraper_engine import ScraperEngine


def build_admin_app(app_config: cfg.AppConfig, engine: ScraperEngine) -> FastAPI:
    """Create FastAPI app exposing admin endpoints."""
    app = FastAPI(title="OTEL API Scraper Admin", version="0.1.0")

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok"}

    @app.get("/sources")
    async def list_sources():
        """List configured sources."""
        return [{"name": s.name, "frequency": s.frequency} for s in app_config.sources]

    @app.get("/sources/{name}")
    async def get_source(name: str):
        """Retrieve configuration for a specific source."""
        for s in app_config.sources:
            if s.name == name:
                return s.model_dump()
        raise HTTPException(status_code=404, detail="Source not found")

    @app.post("/sources/{name}/scrape")
    async def run_source(name: str):
        """Trigger a manual scrape for a source."""
        for s in app_config.sources:
            if s.name == name:
                await engine.scrape_source(s)
                return {"status": "triggered"}
        raise HTTPException(status_code=404, detail="Source not found")

    return app
