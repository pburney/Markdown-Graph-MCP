"""Countdown resolution over `type:: #Countdown` definition pages.

Computes days remaining to a target date derived from person life-dates (reusing
`age.py`). Kinds:

  * ``outlive`` — target = subject.born + (reference.died − reference.born):
    the day the subject will have been alive exactly as long as the reference was.
  * ``age``     — target = subject.born + <age> years.
  * ``date``    — target = an explicit date.

A definition page carries: ``label::``, ``icon::``, ``kind::``, ``subject::``
(person; default = the people-graph's self page), ``reference::`` (person, for
outlive/age), ``people-graph::`` (graph the people live in), and ``target::``
(date kind) or ``age::`` (age kind). People are loaded from ``people-graph``.

Generic — no Sèvo/BFF specifics; callers format the results.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import logseq_graphs as lg
import age


@dataclass
class Countdown:
    label: str
    icon: str
    kind: str
    target_date: date
    days_remaining: int
    detail: str = ""


def _name(value: str) -> str:
    """Strip a [[wikilink]] wrapper, if present."""
    value = (value or "").strip()
    m = re.match(r"^\[\[(.+)\]\]$", value)
    return m.group(1).strip() if m else value


def ymd_between(d0: date, d1: date) -> tuple[int, int, int]:
    """Calendar (years, months, days) from d0 to d1 (d1 >= d0)."""
    y, m, d = d1.year - d0.year, d1.month - d0.month, d1.day - d0.day
    if d < 0:
        pm = d1.month - 1 or 12
        py = d1.year if d1.month > 1 else d1.year - 1
        d += calendar.monthrange(py, pm)[1]
        m -= 1
    if m < 0:
        y -= 1
        m += 12
    return y, m, d


def _human_span(y: int, m: int, d: int) -> str:
    parts = []
    if y:
        parts.append(f"{y}y")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{d}d")   # always show days, even when 0y 0m
    return " ".join(parts)


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:            # Feb 29 → Feb 28 in a non-leap target year
        return d.replace(year=d.year + years, day=28)


def resolve_countdowns(defs_root: Path, *, today: date | None = None) -> list[Countdown]:
    """Resolve every #Countdown page under defs_root into a Countdown. Definitions
    with missing/unresolvable data are skipped rather than raising, so a bad page
    can never take down a caller (e.g. a dashboard generator)."""
    today = today or date.today()
    rows = lg.search_pages(
        defs_root, [("type", "Countdown")],
        ["file", "label", "icon", "kind", "subject", "reference", "people-graph",
         "target", "age"])
    out = []
    for r in rows:
        try:
            cd = _resolve_one(r, today)
        except Exception:
            cd = None
        if cd is not None:
            out.append(cd)
    out.sort(key=lambda c: c.days_remaining)
    return out


def _resolve_one(r: dict, today: date) -> Countdown | None:
    label = r.get("label") or lg.filename_to_title(Path(r.get("file", "")).stem)
    icon = r.get("icon", "")
    kind = lg._normalize_prop(r.get("kind", "date"))

    people = []
    pg = r.get("people-graph", "").strip()
    if pg:
        _, people_root = lg.resolve_graph(pg)
        people = age.load_people(people_root)

    subject = (age.find_person(people, _name(r["subject"]))
               if r.get("subject") else age.find_reference(people, None))

    if kind == "date":
        ld = age.parse_life_date(r.get("target"))
        target = ld.to_date() if ld else None
        detail = ""
    elif kind == "age":
        if not (subject and subject.born and subject.born.has_year and r.get("age")):
            return None
        target = _add_years(subject.born.to_date(), int(r["age"]))
        detail = f"turns {int(r['age'])}"
    elif kind == "outlive":
        reference = age.find_person(people, _name(r.get("reference", "")))
        if not (subject and subject.born and subject.born.has_year):
            return None
        if not (reference and reference.born and reference.born.has_year
                and reference.died and reference.died.has_year):
            return None
        born = reference.born.to_date()
        died = reference.died.to_date()
        target = subject.born.to_date() + (died - born)
        y, m, d = ymd_between(born, died)
        detail = f"{reference.title} lived {_human_span(y, m, d)} (≈{(died - born).days:,} days)"
    else:
        return None

    if target is None:
        return None
    return Countdown(label=label, icon=icon, kind=kind, target_date=target,
                     days_remaining=(target - today).days, detail=detail)
