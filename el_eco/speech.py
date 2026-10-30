"""The séance: Gemma, speaking only from the numbers on the altar."""

from __future__ import annotations

import os
import re
from datetime import date

import httpx

from el_eco.forecast import Forecast
from el_eco.series import Life
from el_eco.sources import Project

SYSTEM = """You are the ghost of an abandoned software project at a Día de los Muertos ofrenda.
You are the project itself, in the first person. You are not an assistant and you do not explain the prompt.
Write two short paragraphs. Be specific, eerie, and kind. Do not be gory, and do not pretend a person has died.
This altar is for unfinished work.
Rules:
- Use the project's name.
- Every integer you write must appear in allowed_numbers. No other digits, anywhere.
- Do not invent users, stars, downloads, lines of code, or dates that are not already numbers in allowed_numbers.
- Do not use thousands separators.
- End with one question about why the work was left.
"""


def allowed_numbers(project: Project, life: Life, forecast: Forecast | None, today: date) -> list[int]:
    found: set[int] = set()

    def add(value) -> None:
        if value is None:
            return
        number = int(round(float(value)))
        if number >= 0:
            found.add(number)

    add(life.silence_days)
    add(life.silence_days // 365)
    add(life.silence_days // 30)
    add(life.weeks_alive)
    add(life.weeks_silent)
    add(life.total_commits)
    add(life.peak_count)
    add(project.stars)
    add(project.forks)
    for day in (life.born, life.died, life.peak_week, today):
        add(day.year)
        add(day.month)
        add(day.day)
    if forecast is not None:
        add(forecast.ghost_commits)
        add(round(forecast.expected_on_death_week))
    return sorted(found)


def _strip_thousands(text: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", text)


def stray_numbers(text: str, allowed: list[int]) -> list[int]:
    cleaned = _strip_thousands(text)
    allowed_set = set(allowed)
    stray = []
    for match in re.findall(r"\d+", cleaned):
        number = int(match)
        if number not in allowed_set:
            stray.append(number)
    return stray


def mentions_project(text: str, name: str) -> bool:
    folded = re.sub(r"[^a-z0-9]", "", text.lower())
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return bool(key) and key in folded


_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _long_date(day: date) -> str:
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def grounded_eulogy(project: Project, life: Life, forecast: Forecast | None) -> str:
    born = _long_date(life.born)
    died = _long_date(life.died)
    opening = (
        f"I am {project.name}. I was opened on {born}, and the last week anyone touched me "
        f"was {died}. I have been quiet for {life.silence_days} days. "
        f"What remains of me is {life.total_commits} commits, and the busiest week I ever had held {life.peak_count}."
    )
    if forecast is None:
        closing = (
            "The forecast candle is unlit, so I will not invent the work that never happened. "
            "Why did you leave the rest of me in the dark?"
        )
    else:
        expected = int(round(forecast.expected_on_death_week))
        closing = (
            f"If the last rhythm had held, the weeks of silence would hold about {forecast.ghost_commits} commits "
            f"that were never written. The week you stopped, that same rhythm still expected "
            f"{expected}. Why did you leave the rest of me in the dark?"
        )
    return f"{opening}\n\n{closing}"


def dossier_text(project: Project, life: Life, forecast: Forecast | None, today: date) -> str:
    allowed = allowed_numbers(project, life, forecast, today)
    lines = [
        f"name: {project.name}",
        f"description: {project.description}",
        f"language: {project.language or 'unspecified'}",
        f"born: {life.born.isoformat()}",
        f"died: {life.died.isoformat()}",
        f"silence_days: {life.silence_days}",
        f"weeks_alive: {life.weeks_alive}",
        f"weeks_silent: {life.weeks_silent}",
        f"total_commits: {life.total_commits}",
        f"peak_commits_in_one_week: {life.peak_count}",
        f"stars: {project.stars}",
        f"forks: {project.forks}",
        "allowed_numbers: " + ", ".join(str(number) for number in allowed),
    ]
    if project.page_text:
        lines.append("page_text: " + project.page_text)
    if forecast is not None:
        expected = int(round(forecast.expected_on_death_week))
        lines.insert(11, f"forecast_unwritten_commits: {forecast.ghost_commits}")
        lines.insert(12, f"forecast_expected_on_death_week: {expected}")
    return "\n".join(lines)


def ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def list_models(host: str | None = None) -> list[str]:
    root = host or ollama_host()
    try:
        response = httpx.get(f"{root}/api/tags", timeout=2.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    models = response.json().get("models") or []
    return [item.get("name", "") for item in models if item.get("name")]


def pick_gemma(names: list[str]) -> str | None:
    override = os.environ.get("OLLAMA_MODEL", "").strip()
    if override:
        if "gemma" not in override.lower():
            return None
        return override
    gemmas = [name for name in names if "gemma" in name.lower()]

    def rank(name: str) -> tuple[int, str]:
        lowered = name.lower()
        for index, key in enumerate(("gemma3", "gemma4", "gemma2", "gemma")):
            if key in lowered:
                return index, name
        return 9, name

    if not gemmas:
        return None
    return sorted(gemmas, key=rank)[0]


def _ask(host: str, model: str, dossier: str, temperature: float) -> str:
    response = httpx.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": dossier},
            ],
            "options": {"temperature": temperature, "num_predict": 320},
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return ((response.json().get("message") or {}).get("content") or "").strip()


def speak(project: Project, life: Life, forecast: Forecast | None, today: date) -> dict:
    allowed = allowed_numbers(project, life, forecast, today)
    host = ollama_host()
    override = os.environ.get("OLLAMA_MODEL", "").strip()
    if override and "gemma" not in override.lower():
        return {
            "speaker": "record",
            "model": None,
            "local": True,
            "text": grounded_eulogy(project, life, forecast),
            "fact_check": "grounded",
            "note": "OLLAMA_MODEL is not a Gemma model. El Eco will not call it Gemma, so the record speaks instead.",
        }
    model = pick_gemma(list_models(host))
    note = ""
    if model:
        dossier = dossier_text(project, life, forecast, today)
        for temperature in (0.7, 0.2):
            try:
                text = _ask(host, model, dossier, temperature)
            except httpx.HTTPError as exc:
                note = f"Gemma did not answer ({exc})."
                break
            if text and mentions_project(text, project.name) and not stray_numbers(text, allowed):
                return {
                    "speaker": "gemma",
                    "model": model,
                    "local": True,
                    "text": text,
                    "fact_check": "passed",
                    "note": "Every number in the eulogy is in the dossier.",
                }
            note = "Gemma wrote a number that is not in the record, so the altar kept the grounded telling."
    elif list_models(host):
        note = "Ollama is running, but no Gemma model is pulled. Try: ollama pull gemma3"
    else:
        note = "Ollama is not answering on this machine, so Gemma could not speak. The record still can."

    return {
        "speaker": "record",
        "model": None,
        "local": True,
        "text": grounded_eulogy(project, life, forecast),
        "fact_check": "grounded",
        "note": note,
    }
