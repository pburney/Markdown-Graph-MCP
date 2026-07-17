"""Unit tests for logseq_graphs utility functions."""

import sys
from pathlib import Path
from datetime import date

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import logseq_graphs as lg


# ---------------------------------------------------------------------------
# Filename encoding / decoding
# ---------------------------------------------------------------------------

def test_title_to_filename_simple():
    assert lg.title_to_filename("Simple Page") == "Simple Page"

def test_title_to_filename_namespace():
    assert lg.title_to_filename("AI/Claude") == "AI___Claude"

def test_title_to_filename_deep():
    assert lg.title_to_filename("A/B/C") == "A___B___C"

def test_filename_to_title_roundtrip():
    titles = ["Simple Page", "AI/Claude", "Job Search 2026/Opportunities/Acme Inc"]
    for t in titles:
        assert lg.filename_to_title(lg.title_to_filename(t)) == t


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def test_parse_date_none_returns_today():
    assert lg.parse_date(None) == date.today()

def test_parse_date_string():
    assert lg.parse_date("2026-01-15") == date(2026, 1, 15)

def test_parse_date_invalid():
    with pytest.raises(ValueError):
        lg.parse_date("not-a-date")

def test_journal_filename():
    assert lg.journal_filename(date(2026, 6, 15)) == "2026_06_15.md"


# ---------------------------------------------------------------------------
# Config: graph paths and read-only settings
# ---------------------------------------------------------------------------

@pytest.fixture()
def config(monkeypatch):
    """Directly inject a config dict, bypassing config.json on disk."""
    def _set(cfg):
        monkeypatch.setattr(lg, "_config", cfg)
    return _set


def test_list_graphs_normalizes_object_entries(config):
    config({
        "default_graph": "a",
        "graphs": {
            "a": "/path/a",
            "b": {"path": "/path/b", "read_only": True},
        },
    })
    assert lg.list_graphs() == {"a": "/path/a", "b": "/path/b"}

def test_resolve_graph_handles_object_entry(config):
    config({
        "default_graph": "a",
        "graphs": {"a": "/path/a", "b": {"path": "/path/b", "read_only": True}},
    })
    name, root = lg.resolve_graph("b")
    assert name == "b"
    assert root == Path("/path/b")

def test_read_only_mode_default_false(config):
    config({"default_graph": "a", "graphs": {"a": "/path/a"}})
    assert lg.read_only_mode() is False

def test_read_only_mode_global_true(config):
    config({"default_graph": "a", "read_only": True, "graphs": {"a": "/path/a"}})
    assert lg.read_only_mode() is True

def test_graph_is_read_only_per_graph(config):
    config({
        "default_graph": "a",
        "graphs": {
            "a": "/path/a",
            "b": {"path": "/path/b", "read_only": True},
        },
    })
    assert lg.graph_is_read_only("a") is False
    assert lg.graph_is_read_only("b") is True

def test_graph_is_read_only_global_forces_all(config):
    config({
        "default_graph": "a",
        "read_only": True,
        "graphs": {"a": "/path/a", "b": {"path": "/path/b", "read_only": False}},
    })
    assert lg.graph_is_read_only("a") is True
    assert lg.graph_is_read_only("b") is True


# ---------------------------------------------------------------------------
# Page finding
# ---------------------------------------------------------------------------

def test_find_page_exists(graph):
    result = lg.find_page(graph, "Simple Page")
    assert result is not None
    assert result.name == "Simple Page.md"

def test_find_page_namespace(graph):
    result = lg.find_page(graph, "NS/Alpha")
    assert result is not None
    assert result.stem == "NS___Alpha"

def test_find_page_case_insensitive(graph):
    result = lg.find_page(graph, "simple page")
    assert result is not None

def test_find_page_missing(graph):
    assert lg.find_page(graph, "Does Not Exist") is None

def test_page_path(graph):
    p = lg.page_path(graph, "AI/Claude")
    assert p == graph / "pages" / "AI___Claude.md"


# ---------------------------------------------------------------------------
# Property parsing
# ---------------------------------------------------------------------------

def test_parse_page_properties_with_props(graph):
    f = graph / "pages" / "Typed___Thing.md"
    props = lg.parse_page_properties(f)
    assert props["type"] == "#Widget"
    assert props["status"] == "#Active"
    assert props["name"] == "Typed___Thing"

def test_parse_page_properties_stops_at_bullet(graph):
    f = graph / "pages" / "Simple Page.md"
    props = lg.parse_page_properties(f)
    assert "type" not in props

def test_parse_page_properties_includes_name_and_file(graph):
    f = graph / "pages" / "Typed___Thing.md"
    props = lg.parse_page_properties(f)
    assert props["name"] == "Typed___Thing"
    assert props["file"] == str(f)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search_pages_single_filter(graph):
    results = lg.search_pages(graph, [("type", "#Widget")], ["name"])
    names = [r["name"] for r in results]
    assert "Typed___Thing" in names
    assert "NS___Alpha" in names
    assert "NS___Beta" in names
    assert "NS___Gamma" in names
    assert "Simple Page" not in names

def test_search_pages_multi_filter(graph):
    results = lg.search_pages(graph, [("type", "#Widget"), ("status", "#Done")], ["name"])
    assert len(results) == 1
    assert results[0]["name"] == "NS___Gamma"

def test_search_pages_no_match(graph):
    results = lg.search_pages(graph, [("type", "#Nonexistent")], ["name"])
    assert results == []

def test_search_pages_return_props(graph):
    results = lg.search_pages(graph, [("type", "#Widget"), ("status", "#Active")], ["name", "status"])
    assert len(results) == 1
    assert results[0]["status"] == "#Active"

def test_search_pages_normalize_tag(graph):
    # Filter with and without # should both match
    results_with = lg.search_pages(graph, [("type", "#Widget")], ["name"])
    results_without = lg.search_pages(graph, [("type", "Widget")], ["name"])
    assert len(results_with) == len(results_without)


# ---------------------------------------------------------------------------
# List page titles
# ---------------------------------------------------------------------------

def test_list_page_titles_all(graph):
    titles = lg.list_page_titles(graph)
    assert "Simple Page" in titles
    assert "NS/Alpha" in titles
    assert "NS/Beta" in titles
    assert "Typed/Thing" in titles

def test_list_page_titles_prefix(graph):
    titles = lg.list_page_titles(graph, prefix="NS")
    assert all(t.startswith("NS/") for t in titles)
    assert "Simple Page" not in titles
    assert len(titles) == 3

def test_list_page_titles_sorted(graph):
    titles = lg.list_page_titles(graph)
    assert titles == sorted(titles)

def test_list_page_titles_prefix_no_match(graph):
    titles = lg.list_page_titles(graph, prefix="Nonexistent")
    assert titles == []


# ---------------------------------------------------------------------------
# Recent journals
# ---------------------------------------------------------------------------

def test_list_recent_journals_count(graph):
    entries = lg.list_recent_journals(graph, n=2)
    assert len(entries) == 2

def test_list_recent_journals_order(graph):
    entries = lg.list_recent_journals(graph, n=3)
    dates = [e[0] for e in entries]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2026-01-03"

def test_list_recent_journals_preview(graph):
    entries = lg.list_recent_journals(graph, n=1)
    date_str, path, preview = entries[0]
    assert date_str == "2026-01-03"
    assert any("most recent" in p for p in preview)

def test_list_recent_journals_n_larger_than_available(graph):
    entries = lg.list_recent_journals(graph, n=100)
    assert len(entries) == 3


# ---------------------------------------------------------------------------
# set_page_property
# ---------------------------------------------------------------------------

def test_set_property_adds_new(graph):
    page = graph / "pages" / "Simple Page.md"
    old, action = lg.set_page_property(page, "status", "#Draft")
    assert action == "added"
    assert old is None
    content = page.read_text()
    assert "status:: #Draft" in content

def test_set_property_updates_existing(graph):
    page = graph / "pages" / "Typed___Thing.md"
    old, action = lg.set_page_property(page, "status", "#Done")
    assert action == "updated"
    assert old == "#Active"
    content = page.read_text()
    assert "status:: #Done" in content
    assert "status:: #Active" not in content

def test_set_property_inserts_before_first_bullet(graph):
    page = graph / "pages" / "Simple Page.md"
    lg.set_page_property(page, "new-prop", "hello")
    lines = page.read_text().splitlines()
    prop_idx = next(i for i, l in enumerate(lines) if "new-prop::" in l)
    bullet_idx = next(i for i, l in enumerate(lines) if l.startswith("- "))
    assert prop_idx < bullet_idx

def test_set_property_creates_page_if_missing(graph):
    page = graph / "pages" / "Brand New Page.md"
    assert not page.exists()
    lg.set_page_property(page, "type", "#Note")
    assert page.exists()
    assert "type:: #Note" in page.read_text()

def test_set_property_atomic_write(graph):
    """No .tmp file should remain after write."""
    page = graph / "pages" / "Typed___Thing.md"
    lg.set_page_property(page, "icon", "🔴")
    tmp_files = list((graph / "pages").glob("*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# search_content
# ---------------------------------------------------------------------------

def test_search_content_page_match(graph):
    results = lg.search_content(graph, "First bullet")
    assert len(results) == 1
    assert results[0]["type"] == "page"
    assert results[0]["title"] == "Simple Page"
    assert results[0]["matches"][0]["line_number"] == 1

def test_search_content_journal_match(graph):
    results = lg.search_content(graph, "most recent")
    journal_hits = [r for r in results if r["type"] == "journal"]
    assert len(journal_hits) == 1
    assert journal_hits[0]["title"] == "2026-01-03"

def test_search_content_case_insensitive(graph):
    results_lower = lg.search_content(graph, "first bullet")
    results_upper = lg.search_content(graph, "FIRST BULLET")
    assert len(results_lower) == len(results_upper) == 1

def test_search_content_no_match(graph):
    results = lg.search_content(graph, "xyzzy_no_such_text")
    assert results == []

def test_search_content_exclude_journals(graph):
    results = lg.search_content(graph, "Journal entry", include_journals=False)
    assert all(r["type"] == "page" for r in results)

def test_search_content_context_lines(graph):
    # "First bullet" only appears in Simple Page.md line 1 → context_after should include line 2
    results = lg.search_content(graph, "First bullet", context_lines=1)
    assert len(results) == 1
    m = results[0]["matches"][0]
    assert len(m["context_after"]) == 1
    assert "Second bullet" in m["context_after"][0]

def test_search_content_context_zero(graph):
    results = lg.search_content(graph, "First bullet", context_lines=0)
    assert results[0]["matches"][0]["context_before"] == []
    assert results[0]["matches"][0]["context_after"] == []

def test_search_content_context_clamped_at_start(graph):
    # Line 1 has no lines before it; context_before should be empty even with context_lines=5
    results = lg.search_content(graph, "First bullet", context_lines=5)
    assert results[0]["matches"][0]["context_before"] == []

def test_search_content_multiple_matches_in_file(graph):
    # Both journal entries on 2026-01-01 contain "bullet"
    results = lg.search_content(graph, "bullet")
    total_matches = sum(len(r["matches"]) for r in results)
    assert total_matches >= 2


# ---------------------------------------------------------------------------
# extract_wikilinks
# ---------------------------------------------------------------------------

def test_extract_wikilinks_empty():
    assert lg.extract_wikilinks("no links here") == []

def test_extract_wikilinks_single():
    assert lg.extract_wikilinks("See [[Fake Street]] for details.") == ["Fake Street"]

def test_extract_wikilinks_multiple():
    result = lg.extract_wikilinks("Visited [[Fake Street]] and [[Carol]] today.")
    assert result == ["Fake Street", "Carol"]

def test_extract_wikilinks_dedupes_case_insensitive():
    result = lg.extract_wikilinks("[[Fake Street]] again, then [[fake street]] once more.")
    assert result == ["Fake Street"]

def test_extract_wikilinks_malformed_brackets():
    assert lg.extract_wikilinks("This has [[ unclosed brackets") == []
    assert lg.extract_wikilinks("This has ]] reversed [[") == []

def test_extract_wikilinks_preserves_order():
    result = lg.extract_wikilinks("[[Beta]] then [[Alpha]]")
    assert result == ["Beta", "Alpha"]


# ---------------------------------------------------------------------------
# find_backlinks
# ---------------------------------------------------------------------------

def test_find_backlinks_finds_page_and_journal(graph):
    results = lg.find_backlinks(graph, "Fake Street")
    types = {r["type"] for r in results}
    assert "page" in types
    assert "journal" in types

def test_find_backlinks_page_match_detail(graph):
    results = lg.find_backlinks(graph, "Fake Street")
    page_hit = next(r for r in results if r["type"] == "page")
    assert page_hit["title"] == "Places Index"
    assert page_hit["matches"][0]["line_number"] == 1

def test_find_backlinks_journal_match_detail(graph):
    results = lg.find_backlinks(graph, "Fake Street")
    journal_hit = next(r for r in results if r["type"] == "journal")
    assert journal_hit["title"] == "2026-01-02"

def test_find_backlinks_case_insensitive(graph):
    results = lg.find_backlinks(graph, "fake street")
    assert len(results) >= 1

def test_find_backlinks_no_match(graph):
    assert lg.find_backlinks(graph, "Nonexistent Page") == []

def test_find_backlinks_exclude_journals(graph):
    results = lg.find_backlinks(graph, "Fake Street", include_journals=False)
    assert all(r["type"] == "page" for r in results)

def test_find_backlinks_does_not_substring_match(graph):
    # "Fake" alone should not match a [[Fake Street]] link
    assert lg.find_backlinks(graph, "Fake") == []


# ---------------------------------------------------------------------------
# find_entity_pages
# ---------------------------------------------------------------------------

def test_find_entity_pages_exact_title_match(graph):
    result = lg.find_entity_pages(graph, "Fake Street")
    names = [p["name"] for p in result["entity_pages"]]
    assert "Fake Street" in names

def test_find_entity_pages_reference_fragment_match(graph):
    result = lg.find_entity_pages(graph, "place:90210")
    names = [p["name"] for p in result["entity_pages"]]
    assert "Fake Street" in names

def test_find_entity_pages_type_filter(graph):
    result = lg.find_entity_pages(graph, "Fake Street", type_filter="place")
    assert any(p["name"] == "Fake Street" for p in result["entity_pages"])
    result_wrong_type = lg.find_entity_pages(graph, "Fake Street", type_filter="person")
    assert result_wrong_type["entity_pages"] == []

def test_find_entity_pages_near_miss(graph):
    result = lg.find_entity_pages(graph, "Carol")
    entity_names = [p["name"] for p in result["entity_pages"]]
    related_names = [p["name"] for p in result["related_pages"]]
    assert "Carol" in entity_names
    assert "Carol Notes" in related_names

def test_find_entity_pages_no_match(graph):
    result = lg.find_entity_pages(graph, "Nonexistent Entity")
    assert result == {"entity_pages": [], "related_pages": []}


# ---------------------------------------------------------------------------
# list_entity_pages
# ---------------------------------------------------------------------------

def test_list_entity_pages_by_type(graph):
    results = lg.list_entity_pages(graph, "place")
    names = [p["name"] for p in results]
    assert names == ["Fake Street"]

def test_list_entity_pages_excludes_other_types(graph):
    results = lg.list_entity_pages(graph, "place")
    names = [p["name"] for p in results]
    assert "Carol" not in names

def test_list_entity_pages_filter_text(graph):
    results = lg.list_entity_pages(graph, "place", filter_text="90210")
    assert len(results) == 1
    results_no_match = lg.list_entity_pages(graph, "place", filter_text="99999")
    assert results_no_match == []

def test_list_entity_pages_no_type_match(graph):
    assert lg.list_entity_pages(graph, "chapter") == []

def test_list_entity_pages_sorted(graph):
    results = lg.list_entity_pages(graph, "place")
    names = [p["name"] for p in results]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# delete_page_file / backup_page_file
# ---------------------------------------------------------------------------

def test_delete_page_file_moves_to_trash(graph):
    page_file = graph / "pages" / "Simple Page.md"
    original = page_file.read_text()
    trash_path = lg.delete_page_file(page_file, graph)
    assert not page_file.exists()
    assert trash_path.exists()
    assert trash_path.parent == graph / ".trash"
    assert trash_path.read_text() == original

def test_delete_page_file_trash_filename_includes_timestamp(graph):
    page_file = graph / "pages" / "Simple Page.md"
    trash_path = lg.delete_page_file(page_file, graph)
    assert trash_path.name.endswith("-Simple Page.md")
    assert trash_path.name != "Simple Page.md"

def test_backup_page_file_leaves_original_in_place(graph):
    page_file = graph / "pages" / "Simple Page.md"
    original = page_file.read_text()
    backup_path = lg.backup_page_file(page_file, graph)
    assert page_file.exists()
    assert page_file.read_text() == original
    assert backup_path.read_text() == original
    assert backup_path.parent == graph / ".trash"

def test_backup_page_file_creates_trash_dir(graph):
    assert not (graph / ".trash").exists()
    page_file = graph / "pages" / "Simple Page.md"
    lg.backup_page_file(page_file, graph)
    assert (graph / ".trash").is_dir()

def test_trashed_page_excluded_from_iter_pages(graph):
    page_file = graph / "pages" / "Simple Page.md"
    lg.delete_page_file(page_file, graph)
    titles = [lg.filename_to_title(f.stem) for f in lg._iter_pages(graph)]
    assert "Simple Page" not in titles


# ---------------------------------------------------------------------------
# In-memory content index: reconciliation, invalidation, caching
#
# The index is keyed by resolved graph root; every test's `graph` fixture is a
# unique tmp_path, so entries never leak between tests. These prove the
# always-reconcile-on-access guarantee: mgm is not the only writer, so external
# creates/deletes/edits between calls must be reflected.
# ---------------------------------------------------------------------------

def test_index_detects_new_file(graph):
    lg.search_content(graph, "First bullet")  # prime the index
    (graph / "pages" / "Fresh Page.md").write_text(
        "- contains brandnewtoken here\n", encoding="utf-8")
    results = lg.search_content(graph, "brandnewtoken")
    assert [r["title"] for r in results] == ["Fresh Page"]

def test_index_detects_deleted_file(graph):
    assert lg.search_content(graph, "First bullet")  # prime; Simple Page matches
    (graph / "pages" / "Simple Page.md").unlink()
    assert lg.search_content(graph, "First bullet") == []
    idx = lg.refresh_graph(graph)
    assert not any(e.path.name == "Simple Page.md" for e in idx.entries.values())

def test_index_detects_external_edit_size_change(graph):
    assert lg.search_content(graph, "appendedtoken") == []
    with open(graph / "pages" / "Simple Page.md", "a", encoding="utf-8") as f:
        f.write("- appendedtoken line\n")   # grows the file -> st_size changes
    results = lg.search_content(graph, "appendedtoken")
    assert [r["title"] for r in results] == ["Simple Page"]

def test_index_detects_external_edit_same_size(graph):
    """Same-length rewrite (st_size unchanged) must still reparse via st_mtime_ns."""
    import os
    page = graph / "pages" / "Simple Page.md"
    assert lg.search_content(graph, "Zecond") == []  # prime; token absent
    original = page.read_text()
    replaced = original.replace("Second", "Zecond")  # 6 chars -> 6 chars
    assert len(replaced) == len(original)
    page.write_text(replaced, encoding="utf-8")
    # Force a distinct mtime in case the rewrite landed in the same clock tick.
    st = page.stat()
    os.utime(page, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    results = lg.search_content(graph, "Zecond")
    assert [r["title"] for r in results] == ["Simple Page"]

def test_index_cache_hit_skips_rebuild(graph, monkeypatch):
    n = len(list(lg._walk_pages_and_journals(graph)))
    assert n > 0
    calls = {"n": 0}
    real_build = lg._build_entry
    def counting_build(md_file, kind, stamp):
        calls["n"] += 1
        return real_build(md_file, kind, stamp)
    monkeypatch.setattr(lg, "_build_entry", counting_build)

    lg.refresh_graph(graph)
    assert calls["n"] == n     # first pass: every file parsed
    calls["n"] = 0
    lg.refresh_graph(graph)
    assert calls["n"] == 0     # unchanged files: pure cache hits, no read/parse

def test_index_excludes_logseq_and_dotdirs(graph):
    (graph / "pages" / "logseq").mkdir()
    (graph / "pages" / "logseq" / "hidden.md").write_text(
        "- secretlogseqtoken\n", encoding="utf-8")
    (graph / "pages" / ".backup").mkdir()
    (graph / "pages" / ".backup" / "old.md").write_text(
        "- secretdottoken\n", encoding="utf-8")
    idx = lg.refresh_graph(graph)
    names = [e.path.name for e in idx.entries.values()]
    assert "hidden.md" not in names
    assert "old.md" not in names
    assert lg.search_content(graph, "secretlogseqtoken") == []
    assert lg.search_content(graph, "secretdottoken") == []

def test_index_trash_backup_never_indexed(graph):
    """.trash sits outside pages/ and journals/, so backups are never walked."""
    lg.backup_page_file(graph / "pages" / "Simple Page.md", graph)
    idx = lg.refresh_graph(graph)
    assert not any(".trash" in str(e.path) for e in idx.entries.values())
