"""Deterministic and timezone-aware clock abstraction for InternPath AI.

Provides:
- Timezone-aware UTC timestamps
- Safe ISO-8601 and calendar date parsing
- Deterministic frozen-time testing support for unit tests and simulations
- Deprecation-free replacements for datetime.utcnow()
"""
from contextlib import contextmanager
from datetime import datetime, timezone, date, time as dt_time, timedelta
from typing import Optional, Union, Generator

# Global mock clock for frozen-time test scenarios
_FROZEN_TIME: Optional[datetime] = None


def set_frozen_time(dt: Optional[Union[datetime, str]]) -> None:
    """Freeze the global clock to a specific deterministic datetime or reset it."""
    global _FROZEN_TIME
    if dt is None:
        _FROZEN_TIME = None
    elif isinstance(dt, str):
        _FROZEN_TIME = parse_datetime_safe(dt)
    elif isinstance(dt, datetime):
        if dt.tzinfo is None:
            _FROZEN_TIME = dt.replace(tzinfo=timezone.utc)
        else:
            _FROZEN_TIME = dt.astimezone(timezone.utc)
    else:
        raise TypeError(f"Unsupported type for frozen time: {type(dt)}")


def clear_frozen_time() -> None:
    """Clear frozen time and return to system wall clock."""
    global _FROZEN_TIME
    _FROZEN_TIME = None


@contextmanager
def freeze_time(dt: Union[datetime, str]) -> Generator[datetime, None, None]:
    """Context manager to freeze time temporarily for deterministic tests."""
    previous = _FROZEN_TIME
    try:
        set_frozen_time(dt)
        yield get_utc_now()
    finally:
        set_frozen_time(previous)


def get_utc_now() -> datetime:
    """Return current timezone-aware UTC datetime, or frozen time if set."""
    if _FROZEN_TIME is not None:
        return _FROZEN_TIME
    return datetime.now(timezone.utc)


def get_naive_utc_now() -> datetime:
    """Return naive UTC datetime (for SQLite columns expecting naive datetime)."""
    return get_utc_now().replace(tzinfo=None)


def format_iso_utc(dt: Optional[datetime] = None) -> str:
    """Format datetime as standard ISO-8601 string in UTC."""
    target = dt or get_utc_now()
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    return target.astimezone(timezone.utc).isoformat()


def parse_datetime_safe(val: Optional[Union[str, datetime, date]]) -> Optional[datetime]:
    """Safely parse various datetime and date string representations into timezone-aware UTC datetime.

    Handles:
    - Standard ISO-8601 strings (e.g. '2026-11-04T12:00:00Z', '2026-11-04T12:00:00+00:00')
    - Date-only strings ('2026-11-04', '2028-02-29' for leap years)
    - Slash and hyphen variants ('2026/11/04', '04-11-2026')
    - Existing datetime and date objects
    - Safe error handling: returns None on invalid inputs
    """
    if val is None:
        return None

    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)

    if isinstance(val, date):
        # A date without time is considered end of that calendar day in UTC (23:59:59)
        # to give students full runway of that deadline day.
        return datetime.combine(val, dt_time(23, 59, 59), tzinfo=timezone.utc)

    if not isinstance(val, str):
        return None

    val = val.strip()
    if not val:
        return None

    # 1. Standard ISO-8601
    try:
        iso_str = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        pass

    # 2. Date-only ISO format (YYYY-MM-DD)
    try:
        parts = val.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            d = date(year, month, day)
            return datetime.combine(d, dt_time(23, 59, 59), tzinfo=timezone.utc)
    except Exception:
        pass

    # 3. Common alternative date formats
    date_formats = (
        ("%Y/%m/%d", True),
        ("%Y-%m-%d %H:%M:%S", False),
        ("%Y/%m/%d %H:%M:%S", False),
        ("%d-%m-%Y", True),
        ("%m/%d/%Y", True),
    )
    for fmt, is_date_only in date_formats:
        try:
            parsed = datetime.strptime(val, fmt)
            if is_date_only:
                parsed = parsed.replace(hour=23, minute=59, second=59)
            return parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    return None
