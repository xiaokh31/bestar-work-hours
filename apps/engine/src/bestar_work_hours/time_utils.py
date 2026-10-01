from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_OPERATIONAL_TIME_ZONE = "America/Edmonton"


def operational_timezone() -> ZoneInfo:
    configured = (
        os.environ.get("OPERATIONAL_TIME_ZONE")
        or os.environ.get("TZ")
        or DEFAULT_OPERATIONAL_TIME_ZONE
    )
    try:
        return ZoneInfo(configured)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_OPERATIONAL_TIME_ZONE)


def operational_now() -> datetime:
    return datetime.now(operational_timezone())


def operational_today() -> date:
    return operational_now().date()
