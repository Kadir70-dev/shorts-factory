"""K70 original newspaper-style source card + safety checks."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.pipeline import dataviz_adv as A
from app.pipeline.dataviz_adv.core import DataError, new_layer
from app.pipeline.dataviz_adv.press import _fit_lines


@pytest.fixture(scope="module")
def theme():
    return A.ChartTheme.load("k70_chart_aurora")


@pytest.fixture
def brief():
    return A.NewsBrief(
        "U.S. inflation hits 9.1% in June 2022",
        "U.S. Bureau of Labor Statistics",
        "2022-07-13",
        "https://www.bls.gov/news.release/archives/cpi_07132022.htm",
        topic="USA FINANCE",
    ).validate()


def test_press_rejects_unsourced_or_future_headlines(brief):
    with pytest.raises(DataError):
        A.NewsBrief("News", "A source", "2022-07-13", "").validate()
    with pytest.raises(DataError):
        A.NewsBrief("News", "A source", "2022-07-13", "http://example.com").validate()
    with pytest.raises(DataError):
        A.NewsBrief("News", "A source", (date.today() + timedelta(days=1)).isoformat(), brief.source_url).validate()
    with pytest.raises(DataError):
        A.NewsBrief("A" * 126, "A source", "2022-07-13", brief.source_url).validate()
    with pytest.raises(DataError):
        A.NewsBrief("", "A source", "2022-07-13", brief.source_url).validate()


def test_press_wrap_is_fitted_for_phone(theme):
    lines, size = _fit_lines("U.S. inflation hits 9.1% in June 2022", theme.display, 792)
    assert 2 <= len(lines) <= 5
    assert size >= 54


@pytest.mark.parametrize("t", [0.1, 0.25, 0.6, 1.0, 1.5, 2.3, 2.65])
def test_press_has_source_date_and_no_collisions(theme, brief, t):
    _, boxes = A.qa.draw_and_record(lambda L, time: A.draw_news_brief(L, theme, brief, time, hold=3.0), t)
    tags = {b["tag"] for b in boxes}
    assert {"press-headline", "press-source", "press-date", "press-brand", "press-topic"} <= tags
    assert not A.qa.text_issues(boxes)
    assert not A.qa.overlap_issues(boxes, (
        "press-headline", "press-source", "press-date", "press-brand", "press-topic"
    ))


def test_press_is_an_overlay_and_not_background(theme, brief):
    L = new_layer()
    assert L.getpixel((0, 0))[3] == 0
    A.draw_news_brief(L, theme, brief, 1.0)
    assert L.getpixel((0, 0))[3] == 0
    assert L.getpixel((180, 480))[3] > 0
