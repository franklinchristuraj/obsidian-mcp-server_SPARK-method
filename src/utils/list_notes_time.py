"""
Optional time bounds for list_notes (filesystem mtime, local naive datetimes).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _start_of_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def _parse_keyword(s: str) -> Optional[datetime]:
    key = s.strip().lower()
    if key == "today":
        return _start_of_day(datetime.now().date())
    if key == "yesterday":
        return _start_of_day(datetime.now().date() - timedelta(days=1))
    return None


def parse_modified_after_bound(raw: Optional[str]) -> Optional[datetime]:
    """
    Lower bound inclusive: keep notes with mtime >= result.
    Accepts: YYYY-MM-DD (start of that local day), ISO datetime, 'today', 'yesterday'.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    kw = _parse_keyword(s)
    if kw is not None:
        return kw
    if _DATE_ONLY.fullmatch(s):
        y, m, d = (int(x) for x in s.split("-"))
        return datetime(y, m, d)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"Invalid modified_after value: {raw!r}") from e


def parse_modified_before_bound(raw: Optional[str]) -> Optional[datetime]:
    """
    Upper bound inclusive: keep notes with mtime <= result.
    For date-only YYYY-MM-DD, end of that local calendar day.
    ISO datetimes are inclusive at that instant.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    kw = _parse_keyword(s)
    if kw is not None:
        return kw + timedelta(days=1) - timedelta(microseconds=1)
    if _DATE_ONLY.fullmatch(s):
        y, m, d = (int(x) for x in s.split("-"))
        start = datetime(y, m, d)
        return start + timedelta(days=1) - timedelta(microseconds=1)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"Invalid modified_before value: {raw!r}") from e


def resolve_list_notes_time_window(
    *,
    modified_after: Optional[str] = None,
    modified_before: Optional[str] = None,
    days: Optional[float] = None,
    hours: Optional[float] = None,
    now: Optional[datetime] = None,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Combine rolling windows (days/hours) with explicit bounds.
    Lower = max of all lower candidates; upper = min of all upper candidates.
    Returns (lower_inclusive_or_none, upper_inclusive_or_none).
    """
    if days is not None and days < 0:
        raise ValueError("days must be >= 0")
    if hours is not None and hours < 0:
        raise ValueError("hours must be >= 0")

    clock = now or datetime.now()
    lowers: list[datetime] = []
    uppers: list[datetime] = []

    parsed_after = parse_modified_after_bound(modified_after)
    if parsed_after is not None:
        lowers.append(parsed_after)

    parsed_before = parse_modified_before_bound(modified_before)
    if parsed_before is not None:
        uppers.append(parsed_before)

    if days is not None:
        lowers.append(clock - timedelta(days=float(days)))
    if hours is not None:
        lowers.append(clock - timedelta(hours=float(hours)))

    lower = max(lowers) if lowers else None
    upper = min(uppers) if uppers else None

    if lower is not None and upper is not None and lower > upper:
        raise ValueError(
            "Invalid time window: modified_after (effective) is after modified_before (effective)."
        )

    return lower, upper


def note_mtime_in_window(
    mtime: datetime,
    lower: Optional[datetime],
    upper: Optional[datetime],
) -> bool:
    if lower is not None and mtime < lower:
        return False
    if upper is not None and mtime > upper:
        return False
    return True
