"""Unit tests for age.py — date parsing and relative-age computation."""

import sys
from pathlib import Path
from datetime import date

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import age


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def test_parse_full_slash():
    d = age.parse_life_date("1975/07/01")
    assert (d.year, d.month, d.day) == (1975, 7, 1)
    assert d.is_full

def test_parse_wikilinked():
    d = age.parse_life_date("[[1953/09/01]]")
    assert (d.year, d.month, d.day) == (1953, 9, 1)

def test_parse_iso():
    d = age.parse_life_date("2005-09-10")
    assert (d.year, d.month, d.day) == (2005, 9, 10)

def test_parse_longform():
    d = age.parse_life_date("September 19, 1949")
    assert (d.year, d.month, d.day) == (1949, 9, 19)

def test_parse_year_only():
    d = age.parse_life_date("1979")
    assert (d.year, d.month, d.day) == (1979, None, None)
    assert d.has_year and not d.is_full

def test_parse_month_day_no_year():
    d = age.parse_life_date("April 16")
    assert (d.year, d.month, d.day) == (None, 4, 16)
    assert not d.has_year

def test_parse_month_only():
    d = age.parse_life_date("November")
    assert (d.year, d.month, d.day) == (None, 11, None)

def test_parse_empty_and_junk():
    assert age.parse_life_date("") is None
    assert age.parse_life_date(None) is None
    assert age.parse_life_date("someday") is None

def test_to_date_defaults_and_leap_clamp():
    assert age.parse_life_date("1979").to_date() == date(1979, 1, 1)
    # Feb with a day default that overshoots clamps down to a valid day.
    assert age.parse_life_date("2001-02").to_date(default_day=31) == date(2001, 2, 28)


# ---------------------------------------------------------------------------
# age_on statuses
# ---------------------------------------------------------------------------

def _p(title, born, died=None, rel=""):
    return age.Person(title, age.parse_life_date(born),
                      age.parse_life_date(died), relationship=rel)

def test_age_on_alive():
    mom = _p("Mom", "1953/09/01", "2005/09/10")
    r = age.age_on(mom, date(1985, 9, 1))
    assert r.status == "alive" and r.age == 32

def test_age_on_before_birthday_in_year():
    mom = _p("Mom", "1953/09/01")
    r = age.age_on(mom, date(1985, 8, 31))
    assert r.age == 31  # day before her 32nd birthday

def test_age_on_unborn():
    kid = _p("Kid", "2003/01/01")
    assert age.age_on(kid, date(2000, 1, 1)).status == "unborn"

def test_age_on_deceased_reports_age_at_death():
    mom = _p("Mom", "1953/09/01", "2005/09/10")
    r = age.age_on(mom, date(2020, 1, 1))
    assert r.status == "deceased" and r.age == 52

def test_age_on_unknown_without_year():
    p = _p("Vague", "April 16")
    assert age.age_on(p, date(2000, 1, 1)).status == "unknown"


# ---------------------------------------------------------------------------
# Graph-level: ages_at, mirror, annotate_event
# ---------------------------------------------------------------------------

@pytest.fixture()
def family(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "Me.md").write_text(
        "type:: #Person\nrelationship:: self\nborn:: [[1975/07/01]]\n\n- me\n",
        encoding="utf-8")
    (pages / "Mom.md").write_text(
        "type:: #Person\nborn:: [[1953/09/01]]\ndied:: [[2005/09/10]]\n\n- mom\n",
        encoding="utf-8")
    (pages / "Dad.md").write_text(
        "type:: #Person\nborn:: [[1949/09/19]]\ndied:: [[2010/04/12]]\n\n- dad\n",
        encoding="utf-8")
    (pages / "Kid.md").write_text(
        "type:: #Person\nborn:: 2003\n\n- year-only birth\n",
        encoding="utf-8")
    (pages / "Death of Mom.md").write_text(
        "type:: #Event\ndate:: 2005\ncategory:: #Deaths\ncritical:: true\n\n- TODO\n",
        encoding="utf-8")
    return tmp_path

def test_ages_at_age_10(family):
    # Me born 1975-07-01, so age 10 → 1985-07-01.
    snap = age.ages_at(family, at_age=10)
    ages = {r.person.title: (r.status, r.age) for r in snap.results}
    assert ages["Me"] == ("alive", 10)
    assert ages["Mom"] == ("alive", 31)   # turns 32 that Sept
    assert ages["Dad"] == ("alive", 35)   # turns 36 that Sept
    assert ages["Kid"][0] == "unborn"

def test_ages_at_default_reference_is_self(family):
    snap = age.ages_at(family, at_year=2000)
    assert snap.reference.title == "Me"

def test_mirror_year_dad_was_my_age(family):
    m = age.mirror(family, "Dad", today=date(2026, 7, 2))
    assert m.ref_current_age == 51            # Me on 2026-07-02
    assert m.year == 1949 + 51                # Dad born 1949 → 2000
    # In that snapshot Dad is 51 and Mom is still alive (died 2005).
    dad = next(r for r in m.snapshot.results if r.person.title == "Dad")
    assert dad.age == 51

def test_annotate_event_death_of_mom(family):
    people = age.load_people(family)
    ev = next(e for e in age.load_events(family) if e.title == "Death of Mom")
    assert ev.critical
    snap = age.annotate_event(ev, people)
    got = {r.person.title: r.age for r in snap.results}
    assert got["Me"] == 30                     # 2005-07-01 (event year default)
    assert got["Dad"] == 55

def test_annotate_event_no_date_returns_none(family):
    people = age.load_people(family)
    ev = age.Event("Trip", None)
    assert age.annotate_event(ev, people) is None
