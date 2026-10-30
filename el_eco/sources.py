"""Where a life comes from: a sample ghost, a CSV, or a public GitHub repo."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from el_eco.series import Week, monday_of, parse_day, weeks_from_dates

GITHUB_API = "https://api.github.com"
COMMIT_CAP = 500
USER_AGENT = "el-eco-ofrenda"
SAMPLE_BORN = date(2022, 6, 6)
# Thirty-six Mondays beginning 6 June 2022. Internal zeros are vacation weeks,
# kept in the training life. The last week is still a real commit.
SAMPLE_LIVING = (
    2, 3, 5, 4, 6, 8, 7, 9, 6, 5,
    4, 7, 6, 0, 5, 6, 8, 4, 3, 5,
    6, 4, 2, 5, 3, 4, 2, 1, 3, 2,
    1, 2, 0, 1, 1, 2,
)


class SourceError(ValueError):
    """The caller can fix this. The message is safe to show."""


@dataclass(frozen=True)
class Project:
    name: str
    full_name: str
    description: str
    language: str | None
    stars: int
    forks: int
    html_url: str | None
    source: str
    history_note: str
    page_text: str = ""


@dataclass(frozen=True)
class Tombstone:
    full_name: str
    description: str
    language: str | None
    stars: int
    pushed_on: str
    silence_days: int
    archived: bool
    fork: bool


def sample_weeks(today: date) -> list[Week]:
    weeks: list[Week] = []
    cursor = SAMPLE_BORN
    for count in SAMPLE_LIVING:
        weeks.append(Week(cursor, count))
        cursor += timedelta(days=7)
    end = monday_of(today)
    while cursor <= end:
        weeks.append(Week(cursor, 0))
        cursor += timedelta(days=7)
    return weeks


def sample_project() -> Project:
    return Project(
        name="lumen-notes",
        full_name="sample/lumen-notes",
        description=(
            "A local markdown journal with no account and no cloud. "
            "The commits are fictional, so the rite can be rehearsed without anyone's real history."
        ),
        language="TypeScript",
        stars=0,
        forks=0,
        html_url=None,
        source="sample",
        history_note="Fictional life, generated in this repository. Nothing was fetched.",
    )


_REPO = re.compile(r"^[A-Za-z0-9_.-]+$")


def parse_repo(value: str) -> tuple[str, str]:
    text = value.strip()
    text = re.sub(r"^https?://github\.com/", "", text, flags=re.I)
    text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    parts = [part for part in text.split("/") if part]
    if len(parts) != 2 or not _REPO.match(parts[0]) or not _REPO.match(parts[1]):
        raise SourceError("Give a public repository as owner/name or a github.com/owner/name URL.")
    return parts[0], parts[1]


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github(path: str, params: dict | None = None) -> httpx.Response:
    try:
        response = httpx.get(f"{GITHUB_API}{path}", headers=_headers(), params=params, timeout=20.0)
    except httpx.HTTPError as exc:
        raise SourceError(f"GitHub could not be reached: {exc}") from exc
    if response.status_code == 404:
        raise SourceError("GitHub has no public repository at that address.")
    if response.status_code in (403, 429):
        raise SourceError(
            "GitHub is refusing more anonymous requests. Add a GITHUB_TOKEN to the environment, or light the sample candle."
        )
    if response.status_code >= 400:
        raise SourceError(f"GitHub answered {response.status_code}.")
    return response


def graveyard(username: str, today: date, min_silence_days: int = 120) -> list[Tombstone]:
    handle = username.strip().lstrip("@")
    if not _REPO.match(handle):
        raise SourceError("That does not look like a GitHub username.")
    response = _github(f"/users/{handle}/repos", {"per_page": 100, "sort": "pushed", "direction": "asc", "type": "owner"})
    stones: list[Tombstone] = []
    for repo in response.json():
        if repo.get("private"):
            continue
        pushed = repo.get("pushed_at")
        if not pushed:
            continue
        pushed_on = parse_day(pushed)
        quiet = (today - pushed_on).days
        stones.append(
            Tombstone(
                full_name=repo["full_name"],
                description=(repo.get("description") or "").strip(),
                language=repo.get("language"),
                stars=int(repo.get("stargazers_count") or 0),
                pushed_on=pushed_on.isoformat(),
                silence_days=quiet,
                archived=bool(repo.get("archived")),
                fork=bool(repo.get("fork")),
            )
        )
    stones.sort(key=lambda stone: (stone.silence_days >= min_silence_days, stone.silence_days), reverse=True)
    return stones


def commits_for_repo(owner: str, repo: str) -> tuple[Project, list[date], str]:
    meta = _github(f"/repos/{owner}/{repo}").json()
    if meta.get("private"):
        raise SourceError("El Eco only sits with public repositories.")
    days: list[date] = []
    page = 1
    while len(days) < COMMIT_CAP:
        batch = _github(
            f"/repos/{owner}/{repo}/commits",
            {"per_page": 100, "page": page},
        ).json()
        if not isinstance(batch, list) or not batch:
            break
        for commit in batch:
            authored = ((commit.get("commit") or {}).get("author") or {}).get("date")
            if authored:
                days.append(parse_day(authored))
        if len(batch) < 100:
            break
        page += 1
    if not days:
        raise SourceError("This repository has no commits on the default branch to lay on the altar.")
    capped = len(days) >= COMMIT_CAP
    note = (
        f"The {COMMIT_CAP} most recent commits on the default branch. Earlier history is outside this telling."
        if capped
        else "Every commit on the default branch."
    )
    project = Project(
        name=meta.get("name") or repo,
        full_name=meta.get("full_name") or f"{owner}/{repo}",
        description=(meta.get("description") or "").strip() or "A public repository with nothing written in its description.",
        language=meta.get("language"),
        stars=int(meta.get("stargazers_count") or 0),
        forks=int(meta.get("forks_count") or 0),
        html_url=meta.get("html_url"),
        source="github",
        history_note=note,
    )
    return project, days, note


def dates_from_csv(text: str) -> list[date]:
    if len(text) > 1_000_000:
        raise SourceError("That CSV is larger than one megabyte. Trim it to a date and a count.")
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells) < 2:
            raise SourceError("Each CSV row needs a date and a count.")
        try:
            day = parse_day(cells[0])
        except ValueError:
            if not rows:
                continue
            raise SourceError(f"Could not read a date from {cells[0]!r}.")
        try:
            count = int(float(cells[1]))
        except ValueError as exc:
            raise SourceError(f"Could not read a count from {cells[1]!r}.") from exc
        if count < 0 or count > 10_000:
            raise SourceError("Counts have to sit between 0 and 10000.")
        rows.append((day, count))
        if len(rows) > 20_000:
            raise SourceError("Too many rows. Keep the CSV under 20000 dated counts.")
    if not rows:
        raise SourceError("The CSV had no dated rows.")
    days: list[date] = []
    for day, count in rows:
        days.extend([day] * count)
    if not days:
        raise SourceError("Every count was zero, so there is no life to remember.")
    return days


def project_from_csv() -> Project:
    return Project(
        name="untitled-life",
        full_name="local/csv",
        description="A weekly record read from a file on this machine. It was not uploaded anywhere else.",
        language=None,
        stars=0,
        forks=0,
        html_url=None,
        source="csv",
        history_note="Counted from the CSV. Rows in the same week are summed.",
    )


def weeks_for_dates(days: list[date], today: date) -> list[Week]:
    return weeks_from_dates(days, today)
