"""Counterfactual weekly activity from TabPFN-3.5.

The silent weeks are not shown to the model. It only sees the weeks the
project was still being touched. Each future week is described with the
calendar season (month, week of year) and the lag pattern of the last
living weeks, frozen. Those features stay inside the range of the life
the model actually sat with, so the forecast is a continuation of the
habit at the end, not a curve extrapolated off the edge of the table.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from el_eco.series import Life, Week

FEATURE_NAMES = ("month", "week_of_year", "lag1", "lag2", "lag4")
MIN_LIVING_WEEKS = 12


class ForecastUnavailable(RuntimeError):
    """TabPFN-3.5 could not take this life. The message is safe to show."""


@dataclass(frozen=True)
class Forecast:
    engine: str
    ghost_commits: int
    expected_on_death_week: float
    weekly_ghost: tuple[float, ...]
    device: str
    detail: str


def _lags(counts: list[int], index: int) -> tuple[float, float, float]:
    def at(offset: int) -> float:
        earlier = index - offset
        if earlier < 0:
            return 0.0
        return float(counts[earlier])

    return at(1), at(2), at(4)


def build_frames(weeks: list[Week] | tuple[Week, ...], silence_index: int) -> tuple[list[list[float]], list[float], list[list[float]]]:
    if silence_index < MIN_LIVING_WEEKS:
        raise ForecastUnavailable(
            f"TabPFN needs at least {MIN_LIVING_WEEKS} living weeks. This one has {silence_index}."
        )
    counts = [week.count for week in weeks]
    train_x: list[list[float]] = []
    train_y: list[float] = []
    for index in range(silence_index):
        week = weeks[index]
        lag1, lag2, lag4 = _lags(counts, index)
        train_x.append([float(week.week_start.month), float(week.week_start.isocalendar().week), lag1, lag2, lag4])
        train_y.append(float(week.count))

    frozen = _lags(counts, silence_index)
    future_x: list[list[float]] = []
    for index in range(silence_index, len(weeks)):
        week = weeks[index]
        future_x.append(
            [float(week.week_start.month), float(week.week_start.isocalendar().week), frozen[0], frozen[1], frozen[2]]
        )
    if not future_x:
        raise ForecastUnavailable("There is no silence to forecast. This project is still being touched.")
    return train_x, train_y, future_x


def _license_message(exc: Exception) -> str:
    text = str(exc)
    if "TABPFN_TOKEN" in text or "license" in text.lower():
        return (
            "TabPFN-3.5 weights are not unlocked on this machine yet. "
            "Accept the non-commercial license at https://ux.priorlabs.ai, "
            "put TABPFN_TOKEN in .env, and light the candle again."
        )
    return f"TabPFN could not finish this forecast: {exc}"


def _device() -> str:
    try:
        import torch
    except Exception:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_tabpfn():
    """Return a TabPFN-3.5 regressor and a short engine label.

    The web process does not open a license browser. Set TABPFN_TOKEN after
    accepting the non-commercial license, or set TABPFN_NO_BROWSER=0 if you
    want the package's own login window.
    """
    os.environ.setdefault("TABPFN_NO_BROWSER", "1")
    try:
        from tabpfn import TabPFNRegressor
        from tabpfn.constants import ModelVersion
    except Exception as exc:
        raise ForecastUnavailable(
            "TabPFN is not installed. From the project folder, with Python 3.12: pip install tabpfn"
        ) from exc

    device = _device()
    errors: list[str] = []
    attempts = (
        {"device": device, "n_estimators": 1},
        {"device": device},
        {},
    )
    for kwargs in attempts:
        try:
            model = TabPFNRegressor.create_default_for_version(ModelVersion.V3_5, **kwargs)
            return model, "tabpfn-3.5", device
        except TypeError as exc:
            errors.append(str(exc))
            continue
        except Exception as exc:
            raise ForecastUnavailable(_license_message(exc)) from exc
    raise ForecastUnavailable(
        "This installed tabpfn package has no TabPFN-3.5 constructor. Upgrade with pip install -U tabpfn. "
        + " ".join(errors)
    )


def forecast_life(life: Life, model=None, engine: str | None = None, device: str | None = None) -> Forecast:
    if life.alive:
        raise ForecastUnavailable("This project is still breathing, so there is no ghost timeline to draw.")
    train_x, train_y, future_x = build_frames(life.weeks, life.silence_index)
    if model is None:
        model, engine, device = load_tabpfn()
    engine = engine or "tabpfn-3.5"
    device = device or "cpu"

    import pandas as pd

    frame_x = pd.DataFrame(train_x, columns=list(FEATURE_NAMES))
    frame_y = pd.Series(train_y, name="commits")
    future = pd.DataFrame(future_x, columns=list(FEATURE_NAMES))
    try:
        model.fit(frame_x, frame_y)
        raw = model.predict(future)
    except Exception as exc:
        raise ForecastUnavailable(_license_message(exc)) from exc

    weekly = tuple(max(0.0, float(value)) for value in list(raw))
    ghost_total = int(round(sum(weekly)))
    return Forecast(
        engine=engine,
        ghost_commits=ghost_total,
        expected_on_death_week=round(weekly[0], 2),
        weekly_ghost=tuple(round(value, 3) for value in weekly),
        device=device,
        detail=(
            "Trained only on weeks before the final silence. "
            "Each silent week is scored with its own month and week-of-year, "
            "and with the commit lags frozen at the last living weeks."
        ),
    )


def series_payload(life: Life, forecast: Forecast | None) -> list[dict]:
    rows: list[dict] = []
    ghosts = forecast.weekly_ghost if forecast else ()
    for index, week in enumerate(life.weeks):
        ghost = None
        if forecast and index >= life.silence_index:
            ghost = ghosts[index - life.silence_index]
        rows.append(
            {
                "week": week.week_start.isoformat(),
                "actual": week.count,
                "ghost": ghost,
            }
        )
    return rows
