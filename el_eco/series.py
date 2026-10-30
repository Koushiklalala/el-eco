"""Turn a list of dates into a weekly life, and find where it went quiet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class Week:
    week_start: date
    count: int


@dataclass(frozen=True)
class Life:
    """The shape of a project that has already gone still.

    ``silence_index`` is the first week excluded from training: the start of
    the trailing quiet that runs through today. Weeks before it are the life
    TabPFN is allowed to learn from.
    """

    weeks: tuple[Week, ...]
    silence_index: int
    born: date
    died: date
    silence_days: int
    total_commits: int
    peak_count: int
    peak_week: date
    alive: bool

    @property
    def weeks_alive(self) -> int:
        return self.silence_index

    @property
    def weeks_silent(self) -> int:
        return len(self.weeks) - self.silence_index


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def parse_day(value: str) -> date:
    text = value.strip()
    if not text:
        raise ValueError("blank date")
    head = text.replace("Z", "")
    try:
        if "T" in head:
            return datetime.fromisoformat(head).date()
        return date.fromisoformat(head[:10])
    except ValueError as exc:
        raise ValueError(f"could not read a date from {value!r}") from exc


def weeks_from_dates(days: list[date], today: date) -> list[Week]:
    if not days:
        raise ValueError("no dates to lay out")
    start = monday_of(min(days))
    end = monday_of(today)
    if end < start:
        end = start
    counts: dict[date, int] = {}
    for day in days:
        bucket = monday_of(day)
        counts[bucket] = counts.get(bucket, 0) + 1
    weeks: list[Week] = []
    cursor = start
    while cursor <= end:
        weeks.append(Week(cursor, counts.get(cursor, 0)))
        cursor += timedelta(days=7)
    return weeks


def find_life(weeks: list[Week], today: date, min_silence_days: int = 90) -> Life:
    if not weeks:
        raise ValueError("no weeks")
    active = [index for index, week in enumerate(weeks) if week.count > 0]
    if not active:
        raise ValueError("every week is empty")
    last = active[-1]
    peak = max(active, key=lambda index: weeks[index].count)
    total = sum(week.count for week in weeks)
    silence_index = last + 1
    died = weeks[last].week_start
    silence_days = (today - died).days
    still_here = silence_index >= len(weeks) or silence_days < min_silence_days
    return Life(
        weeks=tuple(weeks),
        silence_index=len(weeks) if still_here else silence_index,
        born=weeks[active[0]].week_start,
        died=died,
        silence_days=max(silence_days, 0),
        total_commits=total,
        peak_count=weeks[peak].count,
        peak_week=weeks[peak].week_start,
        alive=still_here,
    )
