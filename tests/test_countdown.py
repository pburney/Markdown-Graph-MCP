"""Unit tests for countdown.py — #Countdown resolution."""

import sys
from pathlib import Path
from datetime import date

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import countdown


def test_ymd_between_and_span():
    y, m, d = countdown.ymd_between(date(1953, 9, 1), date(2005, 9, 10))
    assert (y, m, d) == (52, 0, 9)
    assert countdown._human_span(y, m, d) == "52y 9d"


@pytest.fixture()
def graph(tmp_path):
    """A defs graph whose #Countdown pages reference people in the SAME graph
    (people-graph:: is a configured graph name; here we point it at this tmp graph
    by monkeypatching resolve_graph in the test that needs cross-graph)."""
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "Me.md").write_text(
        "type:: #Person\nrelationship:: self\nborn:: [[1975/07/01]]\n\n- me\n",
        encoding="utf-8")
    (pages / "Mom.md").write_text(
        "type:: #Person\nborn:: [[1953/09/01]]\ndied:: [[2005/09/10]]\n\n- mom\n",
        encoding="utf-8")
    return tmp_path


def _write_countdown(root, name, body):
    (root / "pages" / f"{name}.md").write_text(body, encoding="utf-8")


def test_outlive(graph, monkeypatch):
    # people-graph resolves to this same tmp graph
    monkeypatch.setattr(countdown.lg, "resolve_graph", lambda n: (n, graph))
    _write_countdown(graph, "Mommageddon",
                     "type:: #Countdown\nlabel:: Mommageddon\nkind:: outlive\n"
                     "subject:: [[Me]]\nreference:: [[Mom]]\npeople-graph:: fake\n\n- x\n")
    cds = countdown.resolve_countdowns(graph, today=date(2026, 7, 18))
    assert len(cds) == 1
    c = cds[0]
    assert c.label == "Mommageddon"
    # target = 1975-07-01 + (2005-09-10 − 1953-09-01)
    lifespan = (date(2005, 9, 10) - date(1953, 9, 1))
    assert c.target_date == date(1975, 7, 1) + lifespan
    assert c.days_remaining == (c.target_date - date(2026, 7, 18)).days
    assert c.days_remaining > 0                    # still ahead of Paul
    assert "52y 9d" in c.detail


def test_age_kind(graph, monkeypatch):
    monkeypatch.setattr(countdown.lg, "resolve_graph", lambda n: (n, graph))
    _write_countdown(graph, "Turn 60",
                     "type:: #Countdown\nlabel:: Turn 60\nkind:: age\n"
                     "subject:: [[Me]]\nage:: 60\npeople-graph:: fake\n\n- x\n")
    c = countdown.resolve_countdowns(graph, today=date(2026, 7, 18))[0]
    assert c.target_date == date(2035, 7, 1)
    assert "turns 60" in c.detail


def test_date_kind_needs_no_people(graph):
    _write_countdown(graph, "Launch",
                     "type:: #Countdown\nlabel:: Launch\nkind:: date\n"
                     "target:: [[2027/01/01]]\n\n- x\n")
    cds = [c for c in countdown.resolve_countdowns(graph, today=date(2026, 7, 18))
           if c.label == "Launch"]
    assert cds and cds[0].target_date == date(2027, 1, 1)


def test_missing_data_skipped(graph, monkeypatch):
    monkeypatch.setattr(countdown.lg, "resolve_graph", lambda n: (n, graph))
    # outlive referencing a person with no death date → skipped, not raised
    _write_countdown(graph, "Bad",
                     "type:: #Countdown\nlabel:: Bad\nkind:: outlive\n"
                     "subject:: [[Me]]\nreference:: [[Me]]\npeople-graph:: fake\n\n- x\n")
    labels = {c.label for c in countdown.resolve_countdowns(graph, today=date(2026, 7, 18))}
    assert "Bad" not in labels
