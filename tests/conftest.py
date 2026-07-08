"""Shared fixtures: builds a minimal fake Logseq graph in tmp_path."""

import json
import pytest
from pathlib import Path


@pytest.fixture()
def graph(tmp_path):
    """
    A minimal Logseq graph structure for testing.

    Layout:
      pages/
        Simple Page.md             — no properties, just bullets
        Typed___Thing.md           — type:: #Widget, status:: #Active
        NS___Alpha.md              — namespace page, icon:: 🔵
        NS___Beta.md               — namespace page, icon:: 🟢
        NS___Gamma.md              — namespace page, icon:: 🟡, status:: #Done
        Fake Street.md             — entity page, mistoria-reference:: place:90210:Fake-Street:100
        Carol.md                   — entity page, mistoria-reference:: person:carol
        Carol Notes.md             — related page, no mistoria-reference (near-miss for "Carol")
        Places Index.md            — links to [[Fake Street]]
      journals/
        2026_01_01.md
        2026_01_02.md              — links to [[Fake Street]]
        2026_01_03.md              — most recent
    """
    pages = tmp_path / "pages"
    journals = tmp_path / "journals"
    pages.mkdir()
    journals.mkdir()

    (pages / "Simple Page.md").write_text(
        "- First bullet\n- Second bullet\n",
        encoding="utf-8",
    )
    (pages / "Typed___Thing.md").write_text(
        "type:: #Widget\nstatus:: #Active\n\n- Some content\n",
        encoding="utf-8",
    )
    (pages / "NS___Alpha.md").write_text(
        "icon:: 🔵\ntype:: #Widget\n\n- Alpha content\n",
        encoding="utf-8",
    )
    (pages / "NS___Beta.md").write_text(
        "icon:: 🟢\ntype:: #Widget\n\n- Beta content\n",
        encoding="utf-8",
    )
    (pages / "NS___Gamma.md").write_text(
        "icon:: 🟡\ntype:: #Widget\nstatus:: #Done\n\n- Gamma content\n",
        encoding="utf-8",
    )

    (pages / "Fake Street.md").write_text(
        "icon:: 🏡\nmistoria-reference:: place:90210:Fake-Street:100\n\n- A test place entity.\n",
        encoding="utf-8",
    )
    (pages / "Carol.md").write_text(
        "mistoria-reference:: person:carol\n\n- A test person entity.\n",
        encoding="utf-8",
    )
    (pages / "Carol Notes.md").write_text(
        "- Some notes about Carol, not yet an entity page.\n",
        encoding="utf-8",
    )
    (pages / "Places Index.md").write_text(
        "- [[Fake Street]]\n- Some other content.\n",
        encoding="utf-8",
    )

    (journals / "2026_01_01.md").write_text(
        "- Journal entry one\n- Another bullet\n",
        encoding="utf-8",
    )
    (journals / "2026_01_02.md").write_text(
        "- Journal entry two\n- Mentioned [[Fake Street]] again\n",
        encoding="utf-8",
    )
    (journals / "2026_01_03.md").write_text(
        "- Journal entry three — most recent\n- Second bullet\n",
        encoding="utf-8",
    )

    return tmp_path
