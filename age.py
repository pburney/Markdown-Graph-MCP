"""Relative-age computation over Logseq person/event pages.

Generic: works on any graph whose person pages carry ``type:: #Person`` with
``born::`` / ``died::`` date properties, and whose event pages carry
``type:: #Event`` with a ``date::``. Date values may be:

  * ``[[yyyy/MM/dd]]`` or ``yyyy/MM/dd`` (Logseq date-node form)
  * ``yyyy-MM-dd`` (ISO)
  * long-form, e.g. ``September 19, 1949`` / ``Sep 1949``
  * partial: year-only (``1979``) or month/day without a year (``April 16``)

The core question this answers is *age relative to a reference person* — by
default the ``relationship:: self`` page — so you can ask "when I was 10, how
old was everyone?" and "what year was Dad my current age?".

Pure logic + graph reads only; formatting lives in the callers (the MCP tool
and the page generator).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import logseq_graphs as lg

# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_MONTHS = {}
for _i, _full in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1):
    _MONTHS[_full] = _i
    _MONTHS[_full[:3]] = _i  # abbreviations (jan, feb, ...)


@dataclass(frozen=True)
class LifeDate:
    """A possibly-partial date. Any of year/month/day may be None."""
    year: int | None
    month: int | None
    day: int | None
    raw: str

    @property
    def has_year(self) -> bool:
        return self.year is not None

    @property
    def is_full(self) -> bool:
        return None not in (self.year, self.month, self.day)

    def to_date(self, default_month: int = 1, default_day: int = 1) -> date | None:
        """Concrete date, filling missing month/day with the given defaults.
        Returns None if there is no year (nothing to anchor on)."""
        if self.year is None:
            return None
        m = self.month or default_month
        d = self.day or default_day
        # Clamp the day to a valid value for the month (handles e.g. Feb 30
        # from a coarse default, and leap-day edge cases when year lacks it).
        while d > 28:
            try:
                return date(self.year, m, d)
            except ValueError:
                d -= 1
        return date(self.year, m, d)


def _strip_wikilink(value: str) -> str:
    value = value.strip()
    m = re.match(r"^\[\[(.+)\]\]$", value)
    return m.group(1).strip() if m else value


def parse_life_date(value: str | None) -> LifeDate | None:
    """Parse a property value into a LifeDate, or None if empty/unparseable."""
    if not value:
        return None
    raw = value.strip()
    s = _strip_wikilink(raw)
    if not s:
        return None

    # yyyy/MM/dd or yyyy-MM-dd  (also yyyy/MM, yyyy)
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m:
        return LifeDate(int(m.group(1)), int(m.group(2)), int(m.group(3)), raw)
    m = re.match(r"^(\d{4})[/-](\d{1,2})$", s)
    if m:
        return LifeDate(int(m.group(1)), int(m.group(2)), None, raw)
    m = re.match(r"^(\d{4})$", s)
    if m:
        return LifeDate(int(m.group(1)), None, None, raw)

    # Month-name forms: "September 19, 1949", "Sep 1949", "April 16", "November"
    low = s.lower().replace(",", " ")
    parts = low.split()
    month = day = year = None
    for tok in parts:
        if tok in _MONTHS:
            month = _MONTHS[tok]
        elif re.fullmatch(r"\d{4}", tok):
            year = int(tok)
        elif re.fullmatch(r"\d{1,2}", tok):
            day = int(tok)
    if month or year:
        return LifeDate(year, month, day, raw)

    return None


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@dataclass
class Person:
    title: str
    born: LifeDate | None
    died: LifeDate | None
    relationship: str = ""
    icon: str = ""
    aliases: list[str] = field(default_factory=list)
    formal_name: str = ""   # value of a `name::` property, if distinct from the title

    @property
    def is_self(self) -> bool:
        return lg._normalize_prop(self.relationship) == "self"


@dataclass
class Event:
    title: str
    date: LifeDate | None
    category: str = ""
    critical: bool = False
    placement: str = ""


@dataclass
class AgeResult:
    person: Person
    on: date
    status: str          # "unborn" | "alive" | "deceased" | "unknown"
    age: int | None      # age on `on` if alive; age at death if deceased; else None
    approx: bool = False  # True when born/on precision is coarse (year-only, etc.)


def years_between(born: date, on: date) -> int:
    """Whole years elapsed from `born` to `on` (birthday-accurate)."""
    years = on.year - born.year
    if (on.month, on.day) < (born.month, born.day):
        years -= 1
    return years


def age_on(person: Person, on: date) -> AgeResult:
    """Age + life-status of `person` on date `on`."""
    if person.born is None or not person.born.has_year:
        return AgeResult(person, on, "unknown", None)
    born_d = person.born.to_date()
    approx = not person.born.is_full
    if on < born_d:
        return AgeResult(person, on, "unborn", None, approx)
    if person.died is not None and person.died.has_year:
        died_d = person.died.to_date(default_month=12, default_day=31)
        if on > died_d:
            return AgeResult(person, on, "deceased",
                             years_between(born_d, died_d),
                             approx or not person.died.is_full)
    return AgeResult(person, on, "alive", years_between(born_d, on), approx)


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------

def _split_list(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def load_people(graph_root) -> list[Person]:
    rows = lg.search_pages(
        graph_root,
        [("type", "Person")],
        ["file", "name", "born", "died", "relationship", "icon", "alias"],
    )
    people = []
    for r in rows:
        # `name` is polluted when the page has its own `name::` property (Logseq's
        # parser reuses the "name" key for the filename stem), so derive the title
        # from the file path instead, and keep any `name::` value as formal_name.
        title = lg.filename_to_title(Path(r.get("file", "")).stem)
        formal = r.get("name", "")
        if formal == Path(r.get("file", "")).stem:
            formal = ""
        people.append(Person(
            title=title,
            born=parse_life_date(r.get("born")),
            died=parse_life_date(r.get("died")),
            relationship=r.get("relationship", ""),
            icon=r.get("icon", ""),
            aliases=_split_list(r.get("alias", "")),
            formal_name=formal,
        ))
    return people


def load_events(graph_root) -> list[Event]:
    rows = lg.search_pages(
        graph_root,
        [("type", "Event")],
        ["name", "date", "category", "critical", "placement"],
    )
    events = []
    for r in rows:
        title = lg.filename_to_title(r.get("name", ""))
        events.append(Event(
            title=title,
            date=parse_life_date(r.get("date")),
            category=r.get("category", ""),
            critical=lg._normalize_prop(r.get("critical", "")) in ("true", "yes", "1", "*"),
            placement=r.get("placement", ""),
        ))
    return events


def find_reference(people: list[Person], ref_name: str | None) -> Person | None:
    """Resolve the reference person: by name/alias if given, else the self page."""
    if ref_name:
        want = ref_name.strip().lower()
        for p in people:
            names = [p.title.lower(), p.formal_name.lower(), *(a.lower() for a in p.aliases)]
            if want in names:
                return p
        return None
    for p in people:
        if p.is_self:
            return p
    return None


def find_person(people: list[Person], name: str) -> Person | None:
    return find_reference(people, name)


# ---------------------------------------------------------------------------
# The two headline operations
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    on: date
    reference: Person
    ref_result: AgeResult
    results: list[AgeResult]   # everyone (incl. reference), sorted by descending age
    label: str = ""            # human description of the moment


def _resolve_moment(ref: Person, *, at_age=None, at_year=None,
                    on_date=None) -> tuple[date, str]:
    """Turn one of {at_age, at_year, on_date} into a concrete date + a label,
    anchored on the reference person's birthday where a year/age is given."""
    if on_date is not None:
        return on_date, f"on {on_date.isoformat()}"
    born = ref.born.to_date() if (ref.born and ref.born.has_year) else None
    if at_age is not None:
        if born is None:
            raise ValueError(f"{ref.title} has no birth year; cannot resolve at_age.")
        return (ref.born.to_date().replace(year=born.year + int(at_age)),
                f"when {ref.title} was {int(at_age)}")
    if at_year is not None:
        y = int(at_year)
        if born is not None:
            return born.replace(year=y), f"in {y}"
        return date(y, 7, 1), f"in {y}"
    raise ValueError("Provide one of at_age, at_year, or on_date.")


def _snapshot(people, ref, on, label) -> Snapshot:
    results = [age_on(p, on) for p in people]
    results.sort(key=lambda r: (r.age is None, -(r.age or 0), r.person.title))
    ref_result = next((r for r in results if r.person is ref), age_on(ref, on))
    return Snapshot(on=on, reference=ref, ref_result=ref_result,
                    results=results, label=label)


def ages_at(graph_root, *, reference=None, at_age=None, at_year=None,
            on_date=None) -> Snapshot:
    """Everyone's age at a single moment in the reference person's timeline."""
    people = load_people(graph_root)
    ref = find_reference(people, reference)
    if ref is None:
        raise ValueError("Reference person not found "
                         f"({reference!r} or a relationship:: self page).")
    on, label = _resolve_moment(ref, at_age=at_age, at_year=at_year, on_date=on_date)
    return _snapshot(people, ref, on, label)


@dataclass
class Mirror:
    person: Person
    reference: Person
    ref_current_age: int
    year: int               # calendar year `person` was ref's current age
    on_date: date           # `person`'s birthday that year
    snapshot: Snapshot      # everyone's ages at that moment


def mirror(graph_root, person_name, *, reference=None,
           today: date | None = None) -> Mirror:
    """The year `person` was the reference person's *current* age, plus a
    full age snapshot of that moment. Powers "what was Dad doing at my age?"."""
    today = today or date.today()
    people = load_people(graph_root)
    ref = find_reference(people, reference)
    if ref is None:
        raise ValueError("Reference person not found "
                         f"({reference!r} or a relationship:: self page).")
    person = find_person(people, person_name)
    if person is None:
        raise ValueError(f"Person not found: {person_name!r}.")
    if not (ref.born and ref.born.has_year):
        raise ValueError(f"{ref.title} has no birth year.")
    if not (person.born and person.born.has_year):
        raise ValueError(f"{person.title} has no birth year.")

    ref_age = age_on(ref, today).age
    if ref_age is None:
        raise ValueError(f"Cannot compute {ref.title}'s current age.")
    year = person.born.year + ref_age
    on_date = person.born.to_date().replace(year=year)
    snap = _snapshot(people, ref, on_date,
                     f"when {person.title} was {ref_age} (ref: {ref.title}'s age)")
    return Mirror(person=person, reference=ref, ref_current_age=ref_age,
                  year=year, on_date=on_date, snapshot=snap)


def annotate_event(event: Event, people: list[Person],
                   reference: Person | None = None) -> Snapshot | None:
    """Everyone's ages at an event's date, or None if the event has no year."""
    if event.date is None or not event.date.has_year:
        return None
    on = event.date.to_date(default_month=7, default_day=1)
    ref = reference
    if ref is None:
        ref = next((p for p in people if p.is_self), None)
    label = event.title
    results = [age_on(p, on) for p in people]
    results.sort(key=lambda r: (r.age is None, -(r.age or 0), r.person.title))
    ref_result = age_on(ref, on) if ref else None
    return Snapshot(on=on, reference=ref, ref_result=ref_result,
                    results=results, label=label)
