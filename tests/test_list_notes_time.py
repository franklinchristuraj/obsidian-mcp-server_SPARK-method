"""Unit tests for list_notes time filtering helpers."""
from datetime import datetime, timedelta

import pytest

from src.utils.list_notes_time import (
    note_mtime_in_window,
    parse_modified_after_bound,
    parse_modified_before_bound,
    resolve_list_notes_time_window,
)


def test_parse_after_date_only():
    assert parse_modified_after_bound("2026-04-05") == datetime(2026, 4, 5, 0, 0, 0)


def test_parse_before_date_only_end_of_day():
    upper = parse_modified_before_bound("2026-04-05")
    assert upper == datetime(2026, 4, 5, 23, 59, 59, 999999)


def test_resolve_days_and_after_takes_stricter_lower():
    fixed = datetime(2026, 4, 10, 12, 0, 0)
    lower, upper = resolve_list_notes_time_window(
        modified_after="2026-04-09",
        days=2.0,
        now=fixed,
    )
    # days=2 -> 2026-04-08 12:00; after 2026-04-09 00:00 -> max is 2026-04-09
    assert lower == datetime(2026, 4, 9, 0, 0, 0)
    assert upper is None


def test_resolve_invalid_window():
    with pytest.raises(ValueError, match="Invalid time window"):
        resolve_list_notes_time_window(
            modified_after="2026-04-10",
            modified_before="2026-04-05",
            now=datetime(2026, 4, 12, 0, 0, 0),
        )


def test_note_mtime_in_window():
    t = datetime(2026, 4, 5, 15, 0, 0)
    assert note_mtime_in_window(t, None, None) is True
    assert note_mtime_in_window(t, datetime(2026, 4, 5, 0, 0, 0), None) is True
    assert note_mtime_in_window(t, datetime(2026, 4, 6, 0, 0, 0), None) is False
    assert (
        note_mtime_in_window(
            t,
            None,
            datetime(2026, 4, 5, 23, 59, 59, 999999),
        )
        is True
    )


def test_negative_days_rejected():
    with pytest.raises(ValueError, match="days"):
        resolve_list_notes_time_window(days=-1.0)


def test_hours_rolling():
    now = datetime(2026, 4, 10, 12, 0, 0)
    lower, upper = resolve_list_notes_time_window(hours=24.0, now=now)
    assert lower == now - timedelta(hours=24)
    assert upper is None
