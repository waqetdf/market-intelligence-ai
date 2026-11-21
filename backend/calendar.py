"""Official BLS release schedule with scheduled times normalized to UTC."""

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

import httpx

BLS_CALENDAR = "https://www.bls.gov/schedule/news_release/bls.ics"
MAJOR_RELEASE = re.compile(
    r"^(consumer price index|producer price index|employment situation|job openings and labor turnover)",
    re.IGNORECASE,
)


def parse_schedule(content):
    events = {}
    lines = re.sub(r"\r?\n[ \t]", "", content).splitlines()
    fields = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            fields = {}
        elif line == "END:VEVENT" and fields is not None:
            start, title = fields.get("DTSTART", ""), fields.get("SUMMARY", "").strip()
            if MAJOR_RELEASE.search(title):
                try:
                    if start.endswith("Z"):
                        stamp = datetime.strptime(start, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                    elif fields.get("timezone") in {"US-Eastern", "America/New_York"}:
                        stamp = datetime.strptime(start, "%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo("America/New_York"))
                    else:
                        raise ValueError("unspecified release timezone")
                except ValueError:
                    fields = None
                    continue
                when = int(stamp.timestamp())
                events[title, when] = {"title": title, "starts_at": when, "url": BLS_CALENDAR, "source": "BLS"}
            fields = None
        elif fields is not None:
            name, _, value = line.partition(":")
            if name.startswith("DTSTART;TZID="):
                fields["timezone"] = name.split("=", 1)[1]
                name = "DTSTART"
            fields[name] = value
    return sorted(events.values(), key=lambda item: item["starts_at"])


async def fetch_schedule():
    async with httpx.AsyncClient(timeout=8) as client:
        async with client.stream("GET", BLS_CALENDAR) as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > 2_000_000:
                    raise ValueError("Calendario demasiado grande")
    schedule = parse_schedule(content.decode("utf-8-sig"))
    if not schedule:
        raise ValueError("Calendario sin eventos reconocidos")
    return schedule


def nearby_releases(events, observed, minutes):
    return [event for event in events if abs(event["starts_at"] - observed) <= minutes * 60]
