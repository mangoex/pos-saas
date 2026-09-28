"""Pure branch-local pickup availability; UTC instants and no device clock authority."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


class PickupScheduleError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _minutes(value: object) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise PickupScheduleError("pickup_schedule_invalid")
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def pickup_options(schedule: object, timezone_name: str, now: datetime) -> dict[str, Any]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise PickupScheduleError("pickup_schedule_invalid")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise PickupScheduleError("pickup_schedule_invalid") from error
    if schedule is None:
        schedule = []
    if not isinstance(schedule, list):
        raise PickupScheduleError("pickup_schedule_invalid")
    by_day: dict[int, dict[str, Any]] = {}
    for entry in schedule:
        if not isinstance(entry, dict):
            raise PickupScheduleError("pickup_schedule_invalid")
        index = entry.get("day_index")
        if type(index) is not int or not 0 <= index <= 6 or index in by_day:
            raise PickupScheduleError("pickup_schedule_invalid")
        by_day[index] = entry
    now_utc = now.astimezone(UTC)
    local_now = now_utc.astimezone(zone)
    today = local_now.date()
    monday = today - timedelta(days=today.weekday())
    days = []
    earliest = now_utc + timedelta(minutes=15)
    for index in range(7):
        day = monday + timedelta(days=index)
        entry = by_day.get(index)
        closed = not entry or entry.get("is_open") is not True
        slots = []
        if not closed and entry and day >= today:
            opening = _minutes(entry.get("open_time") or "09:00")
            closing = _minutes(entry.get("close_time") or "22:00")
            start = opening
            if day == today:
                current_minutes = local_now.hour * 60 + local_now.minute + 15
                start = max(opening, ((current_minutes + 14) // 15) * 15)
            if opening < closing:
                for minute in range(start, closing + 1, 15):
                    naive = datetime.combine(day, time(minute // 60, minute % 60))
                    candidate = naive.replace(tzinfo=zone)
                    instant = candidate.astimezone(UTC)
                    # Ambiguous/nonexistent wall times cannot identify a unique pickup.
                    if candidate.utcoffset() != candidate.replace(fold=1).utcoffset():
                        continue
                    if instant.astimezone(zone).replace(tzinfo=None) != naive or instant < earliest:
                        continue
                    slots.append(
                        {"value": naive.strftime("%H:%M"), "scheduled_at": instant.isoformat()}
                    )
        days.append(
            {
                "date": day.isoformat(),
                "day_index": index,
                "is_today": day == today,
                "is_past": day < today,
                "is_closed": closed,
                "slots": slots,
            }
        )
    return {
        "generated_at": now_utc.isoformat(),
        "timezone": timezone_name,
        "configured": bool(by_day),
        "days": days,
    }


def validate_pickup(
    schedule: object,
    timezone_name: str,
    now: datetime,
    local_date: object,
    local_time: object,
    order_type: str,
) -> dict[str, str] | None:
    if local_date is None and local_time is None:
        return None
    if (
        order_type != "takeout"
        or not isinstance(local_date, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", local_date)
        or not isinstance(local_time, str)
    ):
        raise PickupScheduleError("pickup_schedule_invalid")
    _minutes(local_time)
    projection = pickup_options(schedule, timezone_name, now)
    for day in projection["days"]:
        if day["date"] == local_date:
            for slot in day["slots"]:
                if slot["value"] == local_time:
                    return {
                        "local_date": local_date,
                        "local_time": local_time,
                        "timezone": timezone_name,
                        "scheduled_at": str(slot["scheduled_at"]),
                    }
    raise PickupScheduleError("pickup_slot_unavailable")
