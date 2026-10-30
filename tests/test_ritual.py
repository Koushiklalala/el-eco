from datetime import date, timedelta

import pytest

from el_eco.forecast import Forecast, ForecastUnavailable, build_frames, forecast_life
from el_eco.series import Week, find_life, monday_of
from el_eco.sources import (
    SAMPLE_LIVING,
    dates_from_csv,
    parse_repo,
    sample_project,
    sample_weeks,
)
from el_eco.speech import allowed_numbers, grounded_eulogy, mentions_project, stray_numbers


TODAY = date(2026, 10, 26)


def _sample_life():
    return find_life(sample_weeks(TODAY), TODAY)


def test_sample_life_is_a_long_silence():
    life = _sample_life()
    assert life.alive is False
    assert life.total_commits == sum(SAMPLE_LIVING)
    assert life.weeks_alive == len(SAMPLE_LIVING)
    assert life.born == date(2022, 6, 6)
    assert life.silence_days > 365
    assert life.peak_count == 9
    assert life.weeks[-1].count == 0


def test_a_project_touched_this_week_is_still_alive():
    start = monday_of(TODAY)
    weeks = [Week(start - timedelta(days=7), 3), Week(start, 1)]
    life = find_life(weeks, TODAY)
    assert life.alive is True
    assert life.weeks_silent == 0


def test_future_features_stay_inside_the_living_habit():
    life = _sample_life()
    train_x, train_y, future_x = build_frames(life.weeks, life.silence_index)
    assert len(train_y) == life.weeks_alive
    assert len(future_x) == life.weeks_silent
    assert future_x[0][2] == train_y[-1]
    assert future_x[0][3] == train_y[-2]
    assert future_x[0][4] == train_y[-4]
    assert all(row[2:5] == future_x[0][2:5] for row in future_x)
    assert all(1 <= row[0] <= 12 for row in future_x)
    assert all(1 <= row[1] <= 53 for row in future_x)


def test_short_lives_are_refused():
    start = date(2024, 1, 1)
    weeks = [Week(start + timedelta(days=7 * index), 2) for index in range(4)]
    weeks.append(Week(start + timedelta(days=28), 0))
    life = find_life(weeks, start + timedelta(days=200))
    with pytest.raises(ForecastUnavailable):
        build_frames(life.weeks, life.silence_index)


class _FlatModel:
    def fit(self, features, target):
        self.rows = len(features)

    def predict(self, features):
        return [1.5] * len(features)


def test_forecast_sums_the_silent_weeks():
    life = _sample_life()
    result = forecast_life(life, model=_FlatModel(), engine="test-double", device="cpu")
    assert result.engine == "test-double"
    assert result.expected_on_death_week == 1.5
    assert result.ghost_commits == round(1.5 * life.weeks_silent)
    assert len(result.weekly_ghost) == life.weeks_silent


def test_grounded_eulogy_uses_only_recorded_numbers():
    life = _sample_life()
    project = sample_project()
    forecast = Forecast(
        engine="test-double",
        ghost_commits=40,
        expected_on_death_week=1.4,
        weekly_ghost=(1.4,),
        device="cpu",
        detail="test",
    )
    text = grounded_eulogy(project, life, forecast)
    allowed = allowed_numbers(project, life, forecast, TODAY)
    assert stray_numbers(text, allowed) == []
    assert mentions_project(text, project.name)
    assert "40" in text


def test_stray_numbers_catch_an_invented_total():
    assert stray_numbers("I would have reached 10000 lines.", [40, 2022]) == [10000]


def test_csv_sums_a_week_and_skips_a_header():
    days = dates_from_csv("date,count\n2022-06-06,2\n2022-06-07,1\n")
    assert len(days) == 3


def test_sample_ritual_stands_when_the_model_is_unlit(monkeypatch):
    from fastapi.testclient import TestClient

    from el_eco.forecast import ForecastUnavailable
    from el_eco.main import app

    def unavailable(_life):
        raise ForecastUnavailable("weights not on this machine")

    monkeypatch.setattr("el_eco.main.forecast_life", unavailable)
    monkeypatch.setattr("el_eco.main.speak", lambda *args, **kwargs: {
        "speaker": "record",
        "model": None,
        "local": True,
        "text": "I am lumen-notes. The forecast candle is unlit.",
        "fact_check": "grounded",
        "note": "test",
    })
    response = TestClient(app).post("/api/ritual", json={"sample": True})
    assert response.status_code == 200
    body = response.json()
    assert body["project"]["name"] == "lumen-notes"
    assert body["death"]["alive"] is False
    assert body["forecast"] is None
    assert "weights" in body["forecast_error"]
    assert body["series"][0]["actual"] == 2
    assert body["series"][-1]["actual"] == 0


def test_page_text_keeps_words_and_drops_digits():
    from el_eco.page_read import without_digits

    assert without_digits("Hello 10000 stars since 2022") == "Hello stars since"


def test_repo_parser_accepts_a_url_and_rejects_a_subpage():
    assert parse_repo("https://github.com/octocat/Hello-World/") == ("octocat", "Hello-World")
    with pytest.raises(Exception):
        parse_repo("https://github.com/octocat/Hello-World/issues")
