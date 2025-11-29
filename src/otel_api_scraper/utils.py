"""Utility helpers for parsing config values and working with nested data."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
import os
from typing import Any, List, Tuple
from urllib.parse import urlencode

from dateutil import parser as date_parser


def utc_now() -> datetime:
    """Get the current UTC datetime.

    Returns:
        datetime: Timezone-aware current UTC time.
    """
    return datetime.now(timezone.utc)


def ensure_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC.

    Args:
        dt: Datetime object that may or may not have tzinfo.

    Returns:
        datetime: UTC-aware datetime.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_frequency(expr: str) -> timedelta:
    """Convert a frequency string to a timedelta.

    Args:
        expr: Frequency expression such as '5min', '1h', '1d', '1w', '1m', or '1mon'.

    Returns:
        timedelta: Duration represented by the expression.

    Raises:
        ValueError: If the expression does not match expected formats.
    """
    match = re.fullmatch(r"(\d+)(min|m|h|d|w|mon)", expr.strip())
    if not match:
        raise ValueError(f"Invalid frequency '{expr}'")
    value = int(match.group(1))
    unit = match.group(2)
    if unit in ("min", "m"):
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    if unit == "w":
        return timedelta(weeks=value)
    if unit == "mon":
        # Treat months as 30 days for scheduling purposes.
        return timedelta(days=value * 30)
    raise ValueError(f"Unsupported frequency unit '{unit}'")  # pragma: no cover


def parse_datetime(value: str, fmt: str | None) -> datetime:
    """Parse a datetime string.

    Args:
        value: Datetime string to parse.
        fmt: Optional explicit strftime format; falls back to ISO8601 parsing.

    Returns:
        datetime: Parsed timezone-aware datetime.
    """
    if fmt:
        return ensure_aware(datetime.strptime(value, fmt))
    parsed = date_parser.isoparse(value)
    return ensure_aware(parsed)


def format_datetime(dt: datetime, fmt: str | None) -> str:
    """Format a datetime into a string.

    Args:
        dt: Datetime to format.
        fmt: Optional strftime format; uses ISO format when not provided.

    Returns:
        str: Formatted datetime string.
    """
    dt = ensure_aware(dt)
    if fmt:
        return dt.strftime(fmt)
    return dt.isoformat()


def split_key(path: str | None) -> List[str]:
    """Split a dot-path while honoring '/.' as a literal dot separator.

    Args:
        path: Raw path string (e.g., "data.items" or "foo/.bar").

    Returns:
        list[str]: Ordered path segments.
    """
    if not path:
        return []
    parts: List[str] = []
    buf = ""
    i = 0
    while i < len(path):
        if path.startswith("/.", i):
            buf += "."
            i += 2
            continue
        ch = path[i]
        if ch == ".":
            if buf:
                parts.append(buf)
                buf = ""
            i += 1
            continue
        buf += ch
        i += 1
    if buf:
        parts.append(buf)
    return parts


def lookup_path(data: Any, path: str | None, root: Any | None = None) -> Any:
    """Fetch a value from nested data using a dot-separated path.

    Args:
        data: Input object (dict-like).
        path: Dot path with '/.' supporting literal dots and optional '$root.' prefix.
        root: Optional root object; used when path starts with '$root.' to access values
            outside the extracted record scope.

    Returns:
        Any: Value if found; otherwise None.
    """
    if path is None:
        return None
    if path.startswith("$root."):
        if root is None or not isinstance(root, dict):
            raise ShapeMismatch("Root-scoped lookup requires an object payload")
        path = path[len("$root.") :]
        current = root
    else:
        current = data
    for part in split_key(path):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def fingerprint_payload(
    record: dict[str, Any], keys: list[str] | None, source: str
) -> str:
    """Build a deterministic payload string for fingerprinting.

    Args:
        record: Record to fingerprint.
        keys: Optional list of field paths to include; if None the full record is used.
        source: Source name to prepend.

    Returns:
        str: Serialized payload string.
    """
    if keys:
        subset = {key: lookup_path(record, key) for key in keys}
        payload = json.dumps(subset, sort_keys=True, default=str)
    else:
        payload = json.dumps(record, sort_keys=True, default=str)
    return f"{source}:{payload}"


def compute_hash(payload: str) -> str:
    """Hash a payload string with SHA-256."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_query_string(params: dict[str, Any], raw_params: dict[str, str]) -> str:
    """Build a query string with optional raw segments.

    Args:
        params: Encoded parameters.
        raw_params: Parameters that should not be URL-encoded.

    Returns:
        str: Combined query string.
    """
    encoded = urlencode(params, doseq=True)
    raw_parts = [f"{k}={v}" for k, v in raw_params.items()]
    if encoded and raw_parts:
        return encoded + "&" + "&".join(raw_parts)
    if raw_parts:
        return "&".join(raw_parts)
    return encoded


def window_slices(
    start: datetime, end: datetime, delta: timedelta
) -> List[Tuple[datetime, datetime]]:
    """Split a time range into contiguous slices.

    Args:
        start: Range start.
        end: Range end.
        delta: Slice duration.

    Returns:
        list[tuple[datetime, datetime]]: Window boundaries.
    """
    slices = []
    cursor = start
    while cursor < end:
        next_cursor = min(cursor + delta, end)
        slices.append((cursor, next_cursor))
        cursor = next_cursor
    return slices


def matches(rule_type: str, candidate: Any, expected: Any) -> bool:
    """Evaluate a predicate against a candidate value.

    Args:
        rule_type: Predicate type ('equals', 'not_equals', 'in', 'regex').
        candidate: Value to test.
        expected: Comparison value(s).

    Returns:
        bool: True if predicate matches.
    """
    if rule_type == "equals":
        return candidate == expected
    if rule_type == "not_equals":
        return candidate != expected
    if rule_type == "in":
        if isinstance(expected, (list, tuple, set)):
            return candidate in expected
        return (
            expected in candidate
            if isinstance(candidate, (list, tuple, set, str))
            else False
        )
    if rule_type == "regex":
        if candidate is None:
            return False
        return re.search(str(expected), str(candidate)) is not None
    return False


def resolve_env(obj: Any) -> Any:
    """Recursively resolve environment placeholders in config structures.

    Strings of the form "${VAR}" are replaced by the value of VAR if set.
    If a string exactly matches an environment variable name, that variable's
    value is also substituted. Non-string values are traversed recursively.
    """
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            key = obj[2:-1]
            return os.getenv(key, obj)
        if obj in os.environ:
            return os.getenv(obj, obj)
        return obj
    if isinstance(obj, list):
        return [resolve_env(item) for item in obj]
    if isinstance(obj, dict):
        return {k: resolve_env(v) for k, v in obj.items()}
    return obj


class ShapeMismatch(Exception):
    """Raised when payload shapes do not match expected list/dict structures."""


def _parse_data_path(path: str) -> List[Tuple[str, str | None]]:
    """Parse dataKey into segments with optional list selectors."""
    placeholder = "__DOT__"
    safe = path.replace("/.", placeholder)
    segments: List[Tuple[str, str | None]] = []
    for part in safe.split("."):
        if part == "":
            continue
        part = part.replace(placeholder, ".")
        if "[" in part and part.endswith("]"):
            name, sel = part.split("[", 1)
            selector = sel[:-1]
            selector = selector if selector != "" else "all"
            segments.append((name, selector))
        else:
            segments.append((part, None))
    return segments


def extract_records(payload: Any, data_key: str | None) -> List[dict]:
    """Extract records from payload based on dataKey semantics.

    - If dataKey is None/empty: expect payload list; error on dict or primitives.
    - Supports nested access with dot notation and list selectors:
      * field.subfield
      * field[].subfield (expand all items in list)
      * field[0].subfield, field[-1].subfield, field[1:3].subfield
    - If final value is dict, wraps into list; if list of dicts, returns list;
      primitives trigger ShapeMismatch.
    """
    if not data_key:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            raise ShapeMismatch(
                f"Expected list at root but got dict: snippet={str(payload)[:200]}"
            )
        raise ShapeMismatch(
            f"Expected list at root but got {type(payload).__name__}: snippet={str(payload)[:200]}"
        )

    segments = _parse_data_path(data_key)
    current: List[Any] = [payload]

    for name, selector in segments:
        next_items: List[Any] = []
        for item in current:
            if isinstance(item, dict):
                val = item.get(name)
            else:
                val = None
            if val is None:
                continue
            if selector is None:
                next_items.append(val)
            else:
                # list expectations
                if not isinstance(val, list):
                    raise ShapeMismatch(
                        f"Expected list at segment '{name}' but got {type(val).__name__}: snippet={str(val)[:200]}"
                    )
                if selector == "all":
                    next_items.extend(val)
                elif ":" in selector:
                    start_str, end_str = selector.split(":", 1)
                    start = int(start_str) if start_str else None
                    end = int(end_str) if end_str else None
                    next_items.extend(val[slice(start, end)])
                else:
                    idx = int(selector)
                    try:
                        next_items.append(val[idx])
                    except IndexError:
                        raise ShapeMismatch(
                            f"Index {idx} out of bounds for segment '{name}'"
                        )
        current = next_items

    if not current:
        return []

    records: List[dict] = []
    for item in current:
        if isinstance(item, dict):
            records.append(item)
        elif isinstance(item, list):
            # If it's a list of dicts, extend; otherwise error.
            if all(isinstance(x, dict) for x in item):
                records.extend(item)  # type: ignore[arg-type]
            else:
                raise ShapeMismatch(
                    f"Expected list of dicts but got {type(item).__name__}: snippet={str(item)[:200]}"
                )
        else:
            raise ShapeMismatch(
                f"Expected list or dict from dataKey but got {type(item).__name__}: snippet={str(item)[:200]}"
            )
    return records
