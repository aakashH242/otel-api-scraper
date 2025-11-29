from datetime import datetime, timedelta, timezone

import pytest

from otel_api_scraper.utils import (
    ShapeMismatch,
    build_query_string,
    compute_hash,
    ensure_aware,
    extract_records,
    fingerprint_payload,
    format_datetime,
    lookup_path,
    matches,
    parse_datetime,
    parse_frequency,
    resolve_env,
    split_key,
    utc_now,
    window_slices,
)


def test_utc_now_and_ensure_aware():
    now = utc_now()
    assert now.tzinfo is not None
    naive = datetime(2025, 1, 1)
    aware = ensure_aware(naive)
    assert aware.tzinfo == timezone.utc
    already = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert ensure_aware(already) == already


def test_parse_frequency_units_and_invalid():
    assert parse_frequency("5min") == timedelta(minutes=5)
    assert parse_frequency("2m") == timedelta(minutes=2)
    assert parse_frequency("2h") == timedelta(hours=2)
    assert parse_frequency("1d") == timedelta(days=1)
    assert parse_frequency("1w") == timedelta(weeks=1)
    assert parse_frequency("2mon") == timedelta(days=60)
    with pytest.raises(ValueError):
        parse_frequency("bad")


def test_parse_and_format_datetime():
    iso = "2025-01-01T00:00:00+00:00"
    parsed = parse_datetime(iso, None)
    assert parsed.tzinfo is not None
    fmt = "%Y-%m-%d"
    parsed_fmt = parse_datetime("2025-02-02", fmt)
    assert parsed_fmt.year == 2025 and parsed_fmt.month == 2
    formatted = format_datetime(parsed_fmt, fmt)
    assert formatted == "2025-02-02"
    assert format_datetime(parsed_fmt, None).startswith("2025-02-02")


def test_split_key_and_lookup_path():
    assert split_key(None) == []
    assert split_key("a.b/.c") == ["a", "b.c"]
    assert split_key(".a") == [
        "a"
    ]  # leading dot produces empty segment that is skipped
    from otel_api_scraper.utils import _parse_data_path

    assert _parse_data_path(".a") == [("a", None)]
    data = {"a": {"b.c": {"d": 1}}, "plain": 2}
    assert lookup_path(data, "a.b/.c.d") == 1
    # When supplied, root context is used for $root.* even if record lacks the field.
    record = {"nested": {"x": 1}}
    raw_payload = {"limit": 10}
    assert lookup_path(record, "$root.limit", root=raw_payload) == 10
    with pytest.raises(ShapeMismatch):
        lookup_path(record, "$root.limit")
    assert lookup_path(data, "$root.plain", root=data) == 2
    assert lookup_path(data, "missing.path") is None


def test_fingerprint_and_hash():
    record = {"a": 1}
    payload_full = fingerprint_payload(record, None, "svc")
    payload_keys = fingerprint_payload(record, ["a"], "svc")
    assert payload_full.startswith("svc:")
    assert payload_keys.endswith("1}")
    assert compute_hash(payload_full) == compute_hash(payload_full)


def test_build_query_string():
    assert build_query_string({"a": 1}, {}) == "a=1"
    assert build_query_string({}, {"raw": "x"}) == "raw=x"
    both = build_query_string({"a": 1}, {"raw": "x"})
    assert "a=1" in both and "raw=x" in both


def test_window_slices():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=5)
    slices = window_slices(start, end, timedelta(minutes=2))
    assert slices[0][0] == start
    assert slices[-1][1] == end


def test_matches_predicates():
    assert matches("equals", 1, 1) is True
    assert matches("not_equals", 1, 2) is True
    assert matches("in", "a", ["a", "b"]) is True
    assert matches("in", ["a"], "a") is True
    assert matches("regex", "abc", "a.c") is True
    assert matches("regex", None, "a.c") is False
    assert matches("unknown", 1, 1) is False


def test_resolve_env_recursive(monkeypatch):
    monkeypatch.setenv("MY_ENV", "secret")
    obj = {
        "a": "${MY_ENV}",
        "b": ["${MY_ENV}", 2],
        "c": {"nested": "MY_ENV"},
        "d": "plain",
    }
    resolved = resolve_env(obj)
    assert resolved["a"] == "secret"
    assert resolved["b"][0] == "secret"
    assert resolved["c"]["nested"] == "secret"
    assert resolved["d"] == "plain"


def test_extract_records_root_errors():
    with pytest.raises(ShapeMismatch):
        extract_records({"a": 1}, None)
    with pytest.raises(ShapeMismatch):
        extract_records(123, None)


def test_extract_records_edge_cases():
    # selector expects list but gets non-list
    with pytest.raises(ShapeMismatch):
        extract_records({"a": {"b": 1}}, "a[].c")
    # index out of bounds raises
    with pytest.raises(ShapeMismatch):
        extract_records({"a": [1]}, "a[5]")
    # missing key returns empty list
    assert extract_records({"a": [{"b": 1}]}, "a[].missing") == []
    # list of non-dicts at end raises
    with pytest.raises(ShapeMismatch):
        extract_records({"a": [[1, 2]]}, "a")
    # non-dict final element raises
    with pytest.raises(ShapeMismatch):
        extract_records({"a": [1]}, "a")
    # when no dataKey and payload is list, it is returned
    assert extract_records([{"a": 1}], None) == [{"a": 1}]
    # non-dict intermediate results are skipped leading to empty
    assert extract_records(["abc"], "missing") == []
    with pytest.raises(ShapeMismatch):
        extract_records({"a": {"b": 1}}, "a.b")


def test_extract_records_happy_paths_and_slices():
    payload = {"items": [{"v": 1}, {"v": 2}, {"v": 3}]}
    # All items
    records = extract_records(payload, "items[]")
    assert len(records) == 3
    # Index
    first = extract_records(payload, "items[0]")
    assert first == [{"v": 1}]
    # Slice
    sliced = extract_records(payload, "items[1:3]")
    assert sliced == [{"v": 2}, {"v": 3}]
    # Nested path wrapping dict into list
    nested = extract_records({"data": {"v": 1}}, "data")
    assert nested == [{"v": 1}]


def test_extract_records_errors(monkeypatch):
    # Non-list when list expected
    with pytest.raises(ShapeMismatch):
        extract_records({"items": {"not": "list"}}, "items[]")
    # Out of bounds
    with pytest.raises(ShapeMismatch):
        extract_records({"items": [1]}, "items[5]")
    # Mixed list types
    with pytest.raises(ShapeMismatch):
        extract_records({"items": [[1, 2]]}, "items[]")
    # Primitive in path
    with pytest.raises(ShapeMismatch):
        extract_records({"items": ["x"]}, "items")


def test_parse_data_key_with_literal_dots():
    payload = {"a.b": {"c": [{"d": 1}, {"d": 2}]}}
    records = extract_records(payload, "a/.b.c")
    assert records == [{"d": 1}, {"d": 2}]
