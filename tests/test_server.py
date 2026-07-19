"""Integration tests: full MCP protocol via subprocess pipes."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SERVER = Path(__file__).parent.parent / "server.py"
# Use the interpreter running the tests, not a hardcoded local .venv — the venv
# is gitignored and does not exist on CI (actions/setup-python puts the
# interpreter on PATH, not at <repo>/.venv/bin/python).
PYTHON = sys.executable


def _start_mcp(tmp_path, config_dict):
    """
    Start the MCP server with a patched config, do the initialize handshake,
    and return (proc, send). Caller is responsible for tearing down proc.
    """
    import json as _json
    config_path = tmp_path / "config.json"
    config_path.write_text(_json.dumps(config_dict), encoding="utf-8")

    # Patch the server's config path via env var — we monkey-patch _CONFIG_PATH
    # by writing a minimal wrapper that overrides it before importing server.
    wrapper = tmp_path / "run_server.py"
    wrapper.write_text(
        f"""
import sys
sys.path.insert(0, {str(SERVER.parent)!r})
import logseq_graphs as lg
lg._CONFIG_PATH = {str(config_path)!r}
from pathlib import Path
lg._CONFIG_PATH = Path({str(config_path)!r})
import importlib, runpy
runpy.run_path({str(SERVER)!r}, run_name='__main__')
""",
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [str(PYTHON), str(wrapper)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.2)

    def send(method, params=None, msg_id=1):
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            msg["params"] = params
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    def notify(method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()

    # Handshake
    send("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    })
    notify("notifications/initialized")

    return proc, send


@pytest.fixture()
def mcp(graph, tmp_path):
    """MCP server config: single writable graph named 'test'."""
    proc, send = _start_mcp(tmp_path, {
        "default_graph": "test",
        "graphs": {"test": str(graph)}
    })
    yield send
    proc.stdin.close()
    proc.wait(timeout=3)


@pytest.fixture()
def mcp_readonly_graph(graph, tmp_path):
    """MCP server config: 'test' graph is read-only via its per-graph object entry."""
    proc, send = _start_mcp(tmp_path, {
        "default_graph": "test",
        "graphs": {"test": {"path": str(graph), "read_only": True}}
    })
    yield send
    proc.stdin.close()
    proc.wait(timeout=3)


@pytest.fixture()
def mcp_global_readonly(graph, tmp_path):
    """MCP server config: top-level read_only forces every graph read-only."""
    proc, send = _start_mcp(tmp_path, {
        "default_graph": "test",
        "read_only": True,
        "graphs": {"test": str(graph)}
    })
    yield send
    proc.stdin.close()
    proc.wait(timeout=3)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

def test_tools_list_returns_15(mcp):
    r = mcp("tools/list", {})
    tools = r["result"]["tools"]
    assert len(tools) == 15

def test_tools_list_names(mcp):
    r = mcp("tools/list", {})
    names = {t["name"] for t in r["result"]["tools"]}
    expected = {
        "list_graphs", "capture_to_journal", "get_journal",
        "read_page", "write_page", "delete_page",
        "search_pages", "list_pages", "list_recent_journals", "set_property",
        "search_content",
        "get_backlinks", "find_entity", "list_entities",
        "person_ages",
    }
    assert names == expected

def test_unknown_tool_returns_error(mcp):
    r = mcp("tools/call", {"name": "nonexistent", "arguments": {}})
    assert "error" in r

def test_unknown_method_returns_error(mcp):
    r = mcp("bogus/method", {})
    assert "error" in r


# ---------------------------------------------------------------------------
# list_graphs
# ---------------------------------------------------------------------------

def test_list_graphs(mcp):
    r = mcp("tools/call", {"name": "list_graphs", "arguments": {}})
    text = r["result"]["content"][0]["text"]
    assert "test" in text
    assert "✓" in text


# ---------------------------------------------------------------------------
# capture_to_journal / get_journal
# ---------------------------------------------------------------------------

def test_capture_creates_journal(mcp, graph):
    r = mcp("tools/call", {"name": "capture_to_journal", "arguments": {
        "graph": "test", "content": "Test capture entry", "date": "2026-03-01"
    }})
    assert "Created" in r["result"]["content"][0]["text"]
    assert (graph / "journals" / "2026_03_01.md").exists()

def test_capture_appends_to_existing(mcp, graph):
    mcp("tools/call", {"name": "capture_to_journal", "arguments": {
        "graph": "test", "content": "First", "date": "2026-03-02"
    }})
    mcp("tools/call", {"name": "capture_to_journal", "arguments": {
        "graph": "test", "content": "Second", "date": "2026-03-02"
    }})
    content = (graph / "journals" / "2026_03_02.md").read_text()
    assert "First" in content
    assert "Second" in content

def test_capture_auto_prefixes_bullet(mcp, graph):
    mcp("tools/call", {"name": "capture_to_journal", "arguments": {
        "graph": "test", "content": "No dash here", "date": "2026-03-03"
    }})
    content = (graph / "journals" / "2026_03_03.md").read_text()
    assert "- No dash here" in content  # appears as \t- No dash here under the tag

def test_capture_adds_mcp_tag(mcp, graph):
    mcp("tools/call", {"name": "capture_to_journal", "arguments": {
        "graph": "test", "content": "Tagged entry", "date": "2026-03-11"
    }})
    written = (graph / "journals" / "2026_03_11.md").read_text()
    assert "#🦾" in written
    assert "\t- Tagged entry" in written

def test_capture_preserves_indented_blocks(mcp, graph):
    content = "- Parent task\n\t- Child note\n\t- TODO Sub-task\n\t\t- Grandchild"
    mcp("tools/call", {"name": "capture_to_journal", "arguments": {
        "graph": "test", "content": content, "date": "2026-03-10"
    }})
    written = (graph / "journals" / "2026_03_10.md").read_text()
    # All content is indented one level under the MCP tag block
    assert "#🦾" in written
    assert "\t- Parent task" in written
    assert "\t\t- Child note" in written
    assert "\t\t- TODO Sub-task" in written
    assert "\t\t\t- Grandchild" in written
    assert "- \t- " not in written  # no double-prefix

def test_get_journal_existing(mcp):
    r = mcp("tools/call", {"name": "get_journal", "arguments": {
        "graph": "test", "date": "2026-01-03"
    }})
    text = r["result"]["content"][0]["text"]
    assert "most recent" in text

def test_get_journal_missing(mcp):
    r = mcp("tools/call", {"name": "get_journal", "arguments": {
        "graph": "test", "date": "1999-01-01"
    }})
    assert "No journal" in r["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# read_page / write_page
# ---------------------------------------------------------------------------

def test_read_page_existing(mcp):
    r = mcp("tools/call", {"name": "read_page", "arguments": {
        "graph": "test", "title": "Simple Page"
    }})
    text = r["result"]["content"][0]["text"]
    assert "First bullet" in text

def test_read_page_namespace(mcp):
    r = mcp("tools/call", {"name": "read_page", "arguments": {
        "graph": "test", "title": "NS/Alpha"
    }})
    assert "Alpha content" in r["result"]["content"][0]["text"]

def test_read_page_missing(mcp):
    r = mcp("tools/call", {"name": "read_page", "arguments": {
        "graph": "test", "title": "Does Not Exist"
    }})
    assert "not found" in r["result"]["content"][0]["text"]

def test_write_page_creates(mcp, graph):
    mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Brand New", "content": "- hello\n"
    }})
    assert (graph / "pages" / "Brand New.md").exists()

def test_write_page_overwrites(mcp, graph):
    mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Simple Page", "content": "- replaced\n"
    }})
    content = (graph / "pages" / "Simple Page.md").read_text()
    assert "replaced" in content
    assert "First bullet" not in content

def test_write_page_overwrite_backs_up_previous_content(mcp, graph):
    r = mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Simple Page", "content": "- replaced\n"
    }})
    text = r["result"]["content"][0]["text"]
    assert "backed up" in text.lower()
    trash_files = list((graph / ".trash").glob("*-Simple Page.md"))
    assert len(trash_files) == 1
    assert "First bullet" in trash_files[0].read_text()

def test_write_page_create_mode_does_not_back_up(mcp, graph):
    mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Brand New No Backup", "content": "- hello\n", "mode": "create"
    }})
    assert not (graph / ".trash").exists()


# ---------------------------------------------------------------------------
# delete_page
# ---------------------------------------------------------------------------

def test_delete_page_moves_to_trash(mcp, graph):
    r = mcp("tools/call", {"name": "delete_page", "arguments": {
        "graph": "test", "title": "Simple Page"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Moved" in text
    assert not (graph / "pages" / "Simple Page.md").exists()
    trash_files = list((graph / ".trash").glob("*-Simple Page.md"))
    assert len(trash_files) == 1
    assert "First bullet" in trash_files[0].read_text()

def test_delete_page_missing(mcp):
    r = mcp("tools/call", {"name": "delete_page", "arguments": {
        "graph": "test", "title": "Does Not Exist"
    }})
    assert "not found" in r["result"]["content"][0]["text"]

def test_delete_page_namespace(mcp, graph):
    r = mcp("tools/call", {"name": "delete_page", "arguments": {
        "graph": "test", "title": "NS/Alpha"
    }})
    assert "Moved" in r["result"]["content"][0]["text"]
    assert not (graph / "pages" / "NS___Alpha.md").exists()

def test_deleted_page_excluded_from_list_pages(mcp, graph):
    mcp("tools/call", {"name": "delete_page", "arguments": {
        "graph": "test", "title": "Simple Page"
    }})
    r = mcp("tools/call", {"name": "list_pages", "arguments": {"graph": "test"}})
    assert "Simple Page" not in r["result"]["content"][0]["text"]

def test_deleted_page_excluded_from_search_content(mcp, graph):
    mcp("tools/call", {"name": "delete_page", "arguments": {
        "graph": "test", "title": "Simple Page"
    }})
    r = mcp("tools/call", {"name": "search_content", "arguments": {
        "graph": "test", "query": "First bullet"
    }})
    assert "No matches" in r["result"]["content"][0]["text"]

def test_readonly_graph_blocks_delete_page(mcp_readonly_graph, graph):
    r = mcp_readonly_graph("tools/call", {"name": "delete_page", "arguments": {
        "graph": "test", "title": "Simple Page"
    }})
    text = r["result"]["content"][0]["text"]
    assert "read-only" in text.lower()
    assert (graph / "pages" / "Simple Page.md").exists()


# ---------------------------------------------------------------------------
# search_pages
# ---------------------------------------------------------------------------

def test_search_pages_basic(mcp):
    r = mcp("tools/call", {"name": "search_pages", "arguments": {
        "graph": "test",
        "filters": ["type=#Widget"],
        "return_props": ["name", "status"],
    }})
    text = r["result"]["content"][0]["text"]
    assert "NS___Alpha" in text or "NS/Alpha" in text or "NS___Alpha" in text

def test_search_pages_multi_filter(mcp):
    r = mcp("tools/call", {"name": "search_pages", "arguments": {
        "graph": "test",
        "filters": ["type=#Widget", "status=#Done"],
        "return_props": ["name"],
    }})
    text = r["result"]["content"][0]["text"]
    assert "Gamma" in text
    assert "1 page" in text

def test_search_pages_no_results(mcp):
    r = mcp("tools/call", {"name": "search_pages", "arguments": {
        "graph": "test",
        "filters": ["type=#Nonexistent"],
        "return_props": ["name"],
    }})
    assert "No pages" in r["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# list_pages
# ---------------------------------------------------------------------------

def test_list_pages_all(mcp):
    r = mcp("tools/call", {"name": "list_pages", "arguments": {"graph": "test"}})
    text = r["result"]["content"][0]["text"]
    assert "Simple Page" in text
    assert "NS/Alpha" in text

def test_list_pages_prefix(mcp):
    r = mcp("tools/call", {"name": "list_pages", "arguments": {
        "graph": "test", "prefix": "NS"
    }})
    text = r["result"]["content"][0]["text"]
    assert "NS/Alpha" in text
    assert "Simple Page" not in text


# ---------------------------------------------------------------------------
# list_recent_journals
# ---------------------------------------------------------------------------

def test_list_recent_journals(mcp):
    r = mcp("tools/call", {"name": "list_recent_journals", "arguments": {
        "graph": "test", "n": 2
    }})
    text = r["result"]["content"][0]["text"]
    assert "2026-01-03" in text
    assert "2026-01-02" in text
    assert "2026-01-01" not in text


# ---------------------------------------------------------------------------
# set_property
# ---------------------------------------------------------------------------

def test_set_property_add(mcp, graph):
    r = mcp("tools/call", {"name": "set_property", "arguments": {
        "graph": "test", "title": "Simple Page", "key": "status", "value": "#Draft"
    }})
    assert "Added" in r["result"]["content"][0]["text"]
    assert "status:: #Draft" in (graph / "pages" / "Simple Page.md").read_text()

def test_set_property_update(mcp, graph):
    r = mcp("tools/call", {"name": "set_property", "arguments": {
        "graph": "test", "title": "Typed/Thing", "key": "status", "value": "#Done"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Updated" in text
    assert "#Active" in text
    assert "#Done" in text

def test_set_property_invalid_graph(mcp):
    r = mcp("tools/call", {"name": "set_property", "arguments": {
        "graph": "nonexistent", "title": "Page", "key": "k", "value": "v"
    }})
    assert "Error" in r["result"]["content"][0]["text"] or "error" in r


# ---------------------------------------------------------------------------
# get_backlinks
# ---------------------------------------------------------------------------

def test_get_backlinks_finds_page_and_journal(mcp):
    r = mcp("tools/call", {"name": "get_backlinks", "arguments": {
        "graph": "test", "title": "Fake Street"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Places Index" in text
    assert "2026-01-02" in text

def test_get_backlinks_all_graphs(mcp):
    r = mcp("tools/call", {"name": "get_backlinks", "arguments": {
        "title": "Fake Street"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Graphs searched: test" in text
    assert "Places Index" in text

def test_get_backlinks_no_match(mcp):
    r = mcp("tools/call", {"name": "get_backlinks", "arguments": {
        "graph": "test", "title": "Nonexistent Page"
    }})
    assert "No backlinks" in r["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# find_entity
# ---------------------------------------------------------------------------

def test_find_entity_exact_match(mcp):
    r = mcp("tools/call", {"name": "find_entity", "arguments": {
        "graph": "test", "name": "Fake Street"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Fake Street" in text
    assert "place:90210:Fake-Street:100" in text

def test_find_entity_near_miss(mcp):
    r = mcp("tools/call", {"name": "find_entity", "arguments": {
        "graph": "test", "name": "Carol"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Carol Notes" in text

def test_find_entity_no_match(mcp):
    r = mcp("tools/call", {"name": "find_entity", "arguments": {
        "graph": "test", "name": "Nonexistent Entity"
    }})
    assert "No matches" in r["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# list_entities
# ---------------------------------------------------------------------------

def test_list_entities_by_type(mcp):
    r = mcp("tools/call", {"name": "list_entities", "arguments": {
        "graph": "test", "type": "place"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Fake Street" in text
    assert "Carol" not in text

def test_list_entities_filter_text(mcp):
    r = mcp("tools/call", {"name": "list_entities", "arguments": {
        "graph": "test", "type": "place", "filter_text": "90210"
    }})
    assert "Fake Street" in r["result"]["content"][0]["text"]

def test_list_entities_no_match(mcp):
    r = mcp("tools/call", {"name": "list_entities", "arguments": {
        "graph": "test", "type": "chapter"
    }})
    assert "No" in r["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# write_page mode (safer writes)
# ---------------------------------------------------------------------------

def test_write_page_mode_create_succeeds_when_new(mcp, graph):
    r = mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Brand New Create", "content": "- hello\n", "mode": "create"
    }})
    assert "Created" in r["result"]["content"][0]["text"]
    assert (graph / "pages" / "Brand New Create.md").exists()

def test_write_page_mode_create_fails_when_exists(mcp, graph):
    r = mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Simple Page", "content": "- clobbered\n", "mode": "create"
    }})
    text = r["result"]["content"][0]["text"]
    assert "Error" in text
    assert "already exists" in text
    content = (graph / "pages" / "Simple Page.md").read_text()
    assert "First bullet" in content  # untouched

def test_write_page_mode_overwrite_still_works(mcp):
    r = mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Simple Page", "content": "- replaced again\n", "mode": "overwrite"
    }})
    assert "Updated" in r["result"]["content"][0]["text"]

def test_write_page_default_mode_is_overwrite(mcp):
    r = mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Simple Page", "content": "- default mode replace\n"
    }})
    assert "Updated" in r["result"]["content"][0]["text"]

def test_write_page_invalid_mode(mcp):
    r = mcp("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Whatever", "content": "- x\n", "mode": "bogus"
    }})
    assert "Error" in r["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# read-only mode
# ---------------------------------------------------------------------------

def test_list_graphs_shows_read_only_marker(mcp_readonly_graph):
    r = mcp_readonly_graph("tools/call", {"name": "list_graphs", "arguments": {}})
    assert "[read-only]" in r["result"]["content"][0]["text"]

def test_readonly_graph_blocks_write_page(mcp_readonly_graph, graph):
    r = mcp_readonly_graph("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Should Not Write", "content": "- nope\n"
    }})
    text = r["result"]["content"][0]["text"]
    assert "read-only" in text.lower()
    assert not (graph / "pages" / "Should Not Write.md").exists()

def test_readonly_graph_blocks_capture_to_journal(mcp_readonly_graph, graph):
    r = mcp_readonly_graph("tools/call", {"name": "capture_to_journal", "arguments": {
        "graph": "test", "content": "Should not be captured", "date": "2026-05-01"
    }})
    text = r["result"]["content"][0]["text"]
    assert "read-only" in text.lower()
    assert not (graph / "journals" / "2026_05_01.md").exists()

def test_readonly_graph_blocks_set_property(mcp_readonly_graph, graph):
    r = mcp_readonly_graph("tools/call", {"name": "set_property", "arguments": {
        "graph": "test", "title": "Simple Page", "key": "status", "value": "#Draft"
    }})
    text = r["result"]["content"][0]["text"]
    assert "read-only" in text.lower()
    content = (graph / "pages" / "Simple Page.md").read_text()
    assert "status::" not in content

def test_readonly_graph_still_allows_reads(mcp_readonly_graph):
    r = mcp_readonly_graph("tools/call", {"name": "read_page", "arguments": {
        "graph": "test", "title": "Simple Page"
    }})
    assert "First bullet" in r["result"]["content"][0]["text"]

def test_global_readonly_blocks_writes(mcp_global_readonly, graph):
    r = mcp_global_readonly("tools/call", {"name": "write_page", "arguments": {
        "graph": "test", "title": "Should Not Write Either", "content": "- nope\n"
    }})
    text = r["result"]["content"][0]["text"]
    assert "read-only" in text.lower()
    assert not (graph / "pages" / "Should Not Write Either.md").exists()

def test_global_readonly_shown_in_list_graphs(mcp_global_readonly):
    r = mcp_global_readonly("tools/call", {"name": "list_graphs", "arguments": {}})
    assert "global read-only mode is ON" in r["result"]["content"][0]["text"]
