"""Pure temporal oracles; no browser clock or wall-clock-dependent fixtures."""

from datetime import datetime, timedelta, timezone

import pytest
from restaurant_os.pickup_schedule import PickupScheduleError, pickup_options, validate_pickup

UTC = timezone.utc
MONDAY = {"day_index": 0, "is_open": True, "open_time": "16:00", "close_time": "18:00"}


def test_clock_seconds_closing_and_branch_day_are_authoritative():
    now = datetime(2026, 9, 28, 22, 0, tzinfo=UTC)
    schedule = [MONDAY]
    first = pickup_options(schedule, "America/Chihuahua", now)
    assert first == pickup_options(schedule, "America/Chihuahua", now)
    assert first["days"][0]["slots"][0]["value"] == "16:15"
    after = pickup_options(schedule, "America/Chihuahua", now + timedelta(seconds=1))
    assert after["days"][0]["slots"][0]["value"] == "16:30"
    boundary = now + timedelta(hours=1, minutes=45)
    assert [
        s["value"]
        for s in pickup_options(schedule, "America/Chihuahua", boundary)["days"][0]["slots"]
    ] == ["18:00"]
    assert (
        pickup_options(schedule, "America/Chihuahua", boundary + timedelta(microseconds=1))["days"][
            0
        ]["slots"]
        == []
    )
    # UTC Tuesday is still Monday at the branch; a browser in Asia cannot change it.
    late = pickup_options(schedule, "America/Chihuahua", datetime(2026, 9, 29, 1, tzinfo=UTC))
    assert late["days"][0]["is_today"] is True
    assert late["days"][0]["date"] == "2026-09-28"


def test_future_day_slots_and_current_week_boundary():
    now = datetime(2026, 9, 28, 15, tzinfo=UTC)
    future = {**MONDAY, "day_index": 2}
    projection = pickup_options([future], "America/Chihuahua", now)
    assert projection["days"][2]["date"] == "2026-09-30"
    assert [s["value"] for s in projection["days"][2]["slots"]] == [
        "16:00",
        "16:15",
        "16:30",
        "16:45",
        "17:00",
        "17:15",
        "17:30",
        "17:45",
        "18:00",
    ]
    for requested_date in ("2026-09-27", "2026-10-05", "2026-02-30"):
        with pytest.raises(PickupScheduleError, match="pickup_slot_unavailable"):
            validate_pickup([MONDAY], "America/Chihuahua", now, requested_date, "16:00", "takeout")
    next_week = pickup_options([MONDAY], "America/Chihuahua", now + timedelta(days=7))
    assert next_week["days"][0]["date"] == "2026-10-05"


@pytest.mark.parametrize(
    "entry",
    [
        {**MONDAY, "is_open": False},
        {**MONDAY, "is_open": None},
        {**MONDAY, "is_open": 0},
        {key: value for key, value in MONDAY.items() if key != "is_open"},
        {**MONDAY, "open_time": "22:00", "close_time": "02:00"},
        {**MONDAY, "open_time": "16:00", "close_time": "16:00"},
    ],
)
def test_closed_or_unsupported_window_has_no_slots(entry):
    projection = pickup_options([entry], "America/Chihuahua", datetime(2026, 9, 28, 12, tzinfo=UTC))
    assert projection["days"][0]["slots"] == []


def test_no_schedule_preserves_unscheduled_capture_only():
    now = datetime(2026, 9, 28, 12, tzinfo=UTC)
    assert pickup_options(None, "America/Chihuahua", now)["configured"] is False
    assert validate_pickup(None, "America/Chihuahua", now, None, None, "takeout") is None
    with pytest.raises(PickupScheduleError, match="pickup_slot_unavailable"):
        validate_pickup(None, "America/Chihuahua", now, "2026-09-28", "16:00", "takeout")


@pytest.mark.parametrize(
    "schedule,zone",
    [
        ([MONDAY], "Invalid/Zone"),
        ([{**MONDAY, "open_time": "25:00"}], "America/Chihuahua"),
        ([{**MONDAY, "day_index": True}], "America/Chihuahua"),
        ([MONDAY, MONDAY], "America/Chihuahua"),
        ("not-a-schedule", "America/Chihuahua"),
    ],
)
def test_invalid_configuration_fails_explicitly(schedule, zone):
    with pytest.raises(PickupScheduleError, match="pickup_schedule_invalid"):
        pickup_options(schedule, zone, datetime(2026, 9, 28, 12, tzinfo=UTC))


@pytest.mark.parametrize(
    "now,excluded",
    [
        (datetime(2026, 3, 2, 12, tzinfo=UTC), "02:"),
        (datetime(2026, 10, 26, 12, tzinfo=UTC), "01:"),
    ],
)
def test_dst_gap_and_ambiguous_hours_are_excluded(now, excluded):
    sunday = {"day_index": 6, "is_open": True, "open_time": "00:00", "close_time": "04:00"}
    slots = pickup_options([sunday], "America/New_York", now)["days"][6]["slots"]
    assert slots
    assert all(not item["value"].startswith(excluded) for item in slots)
    assert len({item["scheduled_at"] for item in slots}) == len(slots)
