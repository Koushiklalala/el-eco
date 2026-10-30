"""HTTP altar. The heavy work stays in-process: GitHub is read, then TabPFN and Gemma run here."""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from el_eco.forecast import ForecastUnavailable, forecast_life, series_payload
from el_eco.page_read import browserbase_configured, read_public_page
from el_eco.series import find_life
from el_eco.sources import (
    Project,
    SourceError,
    commits_for_repo,
    dates_from_csv,
    graveyard,
    parse_repo,
    project_from_csv,
    sample_project,
    sample_weeks,
    weeks_for_dates,
)
from el_eco.speech import list_models, ollama_host, pick_gemma, speak
from el_eco.voice import VoiceError, elevenlabs_configured, synthesize

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
logger = logging.getLogger("el_eco")

app = FastAPI(title="El Eco", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()


class GraveyardIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class RitualIn(BaseModel):
    sample: bool = False
    repo: str | None = None
    csv: str | None = None
    name: str | None = Field(default=None, max_length=60)


class VoiceIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _clean_name(value: str | None) -> str:
    if not value:
        return "untitled-life"
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in " _.-").strip()
    return cleaned[:60] or "untitled-life"


def _tabpfn_status() -> dict:
    try:
        import tabpfn
        from tabpfn.constants import ModelVersion
    except Exception:
        return {"installed": False, "version": None, "selected": None}
    version = getattr(ModelVersion, "V3_5", None)
    return {
        "installed": True,
        "version": getattr(tabpfn, "__version__", "unknown"),
        "selected": getattr(version, "value", "v3.5") if version else "v3.5",
    }


def _prepare(body: RitualIn, today: date) -> tuple[Project, list]:
    chosen = sum(bool(item) for item in (body.sample, body.repo, body.csv))
    if chosen != 1:
        raise HTTPException(status_code=400, detail="Choose one source: the sample ghost, a repository, or a CSV.")
    if body.sample:
        return sample_project(), sample_weeks(today)
    if body.repo:
        try:
            owner, repo = parse_repo(body.repo)
            project, days, _note = commits_for_repo(owner, repo)
        except SourceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        excerpt = read_public_page(owner, repo)
        if excerpt:
            project = replace(
                project,
                page_text=excerpt,
                history_note=project.history_note
                + " A Browserbase browser opened the public page and brought its words back.",
            )
        return project, weeks_for_dates(days, today)
    try:
        days = dates_from_csv(body.csv or "")
    except SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    project = project_from_csv()
    named = _clean_name(body.name)
    project = Project(
        name=named,
        full_name=f"local/{named}",
        description=project.description,
        language=None,
        stars=0,
        forks=0,
        html_url=None,
        source="csv",
        history_note=project.history_note,
    )
    return project, weeks_for_dates(days, today)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    models = list_models()
    return {
        "ok": True,
        "tabpfn": _tabpfn_status(),
        "ollama": {"host": ollama_host(), "models": models, "gemma": pick_gemma(models)},
        "elevenlabs": elevenlabs_configured(),
        "browserbase": browserbase_configured(),
        "github_token": bool(os.environ.get("GITHUB_TOKEN", "").strip()),
    }


@app.post("/api/graveyard")
def list_graveyard(body: GraveyardIn) -> dict:
    try:
        stones = graveyard(body.username, date.today())
    except SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"username": body.username.strip().lstrip("@"), "repos": [asdict(stone) for stone in stones]}


@app.post("/api/ritual")
def ritual(body: RitualIn) -> dict:
    today = date.today()
    project, weeks = _prepare(body, today)
    try:
        life = find_life(weeks, today)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    forecast = None
    forecast_error = None
    if not life.alive:
        try:
            forecast = forecast_life(life)
        except ForecastUnavailable as exc:
            forecast_error = str(exc)
            logger.info("forecast unavailable: %s", exc)

    eulogy = None if life.alive else speak(project, life, forecast, today)
    return {
        "today": today.isoformat(),
        "project": asdict(project),
        "death": {
            "born": life.born.isoformat(),
            "died": life.died.isoformat(),
            "silence_days": life.silence_days,
            "weeks_alive": life.weeks_alive,
            "weeks_silent": life.weeks_silent,
            "total_commits": life.total_commits,
            "peak_count": life.peak_count,
            "peak_week": life.peak_week.isoformat(),
            "alive": life.alive,
        },
        "forecast": None
        if forecast is None
        else {
            "engine": forecast.engine,
            "ghost_commits": forecast.ghost_commits,
            "expected_on_death_week": forecast.expected_on_death_week,
            "device": forecast.device,
            "detail": forecast.detail,
        },
        "forecast_error": forecast_error,
        "series": series_payload(life, forecast),
        "eulogy": eulogy,
    }


@app.post("/api/voice")
def voice(body: VoiceIn) -> dict:
    try:
        audio, voice_id = synthesize(body.text)
    except VoiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="ElevenLabs could not be reached.") from exc
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "voice_id": voice_id,
        "left_the_machine": True,
    }
