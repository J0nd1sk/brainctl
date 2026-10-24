"""DG pattern separation / CA3 pattern completion write gate.

Covers the pure key-token logic, the three-way decision, and the shared
gate wired into both write paths (CLI ``cmd_memory_add`` and MCP
``tool_memory_add``).
"""
import sqlite3
import types

import pytest

from agentmemory.brain import Brain
from agentmemory.lib import pattern_separation as ps
from agentmemory.lib.pattern_separation import Neighbor, decide, key_token_diff


# ---------------------------------------------------------------------------
# Normalised signature
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Redis is used as the session cache for the web tier.",
     "redis is used as the session cache for the web tier"),
    ("Feature flags are managed in LaunchDarkly, not in config files",
     "Feature flags are managed in LaunchDarkly -- not in config files!"),
    ("Logs are retained for 30 days in Loki", "Logs are retained  for 30 days in Loki ."),
    ("The VPN must be connected", "THE VPN MUST BE CONNECTED"),
])
def test_surface_variants_share_a_signature(a, b):
    assert ps.normalize(a) == ps.normalize(b)
    assert ps.jaccard(a, b) == 1.0
    assert key_token_diff(a, b) == {}


def test_contractions_normalise_to_not():
    assert "not" in ps.token_set("You don't deploy on Fridays")
    assert ps.normalize("can't") == ps.normalize("can not") == "can not"
    assert ps.normalize("won't") == "will not"


def test_numbers_keep_internal_separators():
    toks = ps.token_set("Ubuntu 22.04 with Python 3.11 at 9:30")
    assert {"22.04", "3.11", "9:30"} <= toks


# ---------------------------------------------------------------------------
# Key tokens
# ---------------------------------------------------------------------------

def test_negation_is_a_key_token():
    diff = key_token_diff("The payments service should never call the ledger API",
                          "The payments service should call the ledger API")
    assert diff == {"negation": ["never"]}


def test_contracted_negation_is_a_key_token():
    diff = key_token_diff("Agents shouldn't push to main", "Agents should push to main")
    assert diff == {"negation": ["not"]}


def test_number_is_a_key_token():
    diff = key_token_diff("Alert when disk usage exceeds 80 percent",
                          "Alert when disk usage exceeds 95 percent")
    assert diff == {"number": ["80", "95"]}


def test_date_word_is_a_key_token():
    diff = key_token_diff("The team runs its retro on Monday afternoons",
                          "The team runs its retro on friday afternoons")
    assert diff == {"date": ["friday", "monday"]}


def test_mid_sentence_proper_noun_is_a_key_token():
    diff = key_token_diff("The primary datastore is MySQL", "The primary datastore is Postgres")
    assert diff == {"entity": ["mysql", "postgres"]}


def test_swapped_capitalised_subject_is_a_key_token():
    diff = key_token_diff("Alice is the payments on-call engineer",
                          "Bob is the payments on-call engineer")
    assert diff == {"entity": ["alice", "bob"]}


def test_sentence_initial_capital_alone_is_not_an_entity():
    # An added sentence-initial word is not a proper noun (only a swapped
    # capitalised subject is, see the test above).
    assert key_token_diff("Always use ruff for linting", "use ruff for linting") == {}


def test_known_entity_names_count_even_lowercase():
    a = "the ingestion pipeline is owned by atlas"
    b = "the ingestion pipeline is owned by zephyr"
    assert key_token_diff(a, b) == {}
    assert key_token_diff(a, b, entity_names=["Atlas"]) == {"entity": ["atlas"]}


def test_lowercase_common_word_swap_is_not_a_key_token():
    assert key_token_diff("Erin is on call for the payments service",
                          "Erin is on call for the search service") == {}


# ---------------------------------------------------------------------------
# Three-way decision
# ---------------------------------------------------------------------------

def test_decide_reinforces_near_identical():
    n = Neighbor(7, "Bob owns the payments reconciliation job.")
    d = decide("bob owns the payments reconciliation job", [n])
    assert d.action == ps.REINFORCE
    assert d.neighbor.id == 7 and d.similarity == 1.0


def test_decide_separates_negation_flip_even_when_token_subset():
    first = ("Customer data from EU accounts must be stored only in the Frankfurt "
             "region and never replicated to US regions")
    second = first.replace(" and never replicated", " and replicated")
    n = Neighbor(3, first)
    d = decide(second, [n])
    assert n.lexical >= ps.LEXICAL_REINFORCE_THRESHOLD  # would have merged pre-DG
    assert d.action == ps.SEPARATE
    assert [x.id for x in d.separated_from] == [3]
    assert d.summary()["key_token_diff"] == {"negation": ["never"]}


def test_decide_separates_similar_with_number_difference():
    d = decide("The pro plan API rate limit is 1000 requests per minute",
               [Neighbor(1, "The free plan API rate limit is 100 requests per minute")])
    assert d.action == ps.SEPARATE


def test_decide_passthrough_when_similar_without_key_diff():
    d = decide("Erin is the on-call engineer for the search service this week",
               [Neighbor(1, "Erin is the on-call engineer for the payments service this week")])
    assert d.action == ps.PASSTHROUGH


def test_decide_novel_when_nothing_similar():
    d = decide("Our frontend uses Next.js", [Neighbor(1, "Stripe webhooks are verified")])
    assert d.action == ps.NOVEL
    assert d.summary() == {"decision": "novel"}


def test_decide_reinforce_wins_over_separation():
    d = decide("The disk alert fires at 80 percent", [
        Neighbor(1, "The disk alert fires at 95 percent"),
        Neighbor(2, "The disk alert fires at 80 percent."),
    ])
    assert d.action == ps.REINFORCE and d.neighbor.id == 2


def test_decide_cosine_reinforces_paraphrase_without_key_diff():
    n = Neighbor(1, "The deploy target for the API is fly.io", cosine=0.98)
    d = decide("We deploy the API on fly.io", [n])
    assert d.action == ps.REINFORCE and d.neighbor.method == "cosine"


def test_decide_cosine_separates_on_key_diff():
    n = Neighbor(1, "The HTTP timeout is 30 seconds", cosine=0.99)
    d = decide("The HTTP timeout is 60 seconds", [n])
    assert d.action == ps.SEPARATE


def test_thresholds_are_ordered():
    assert ps.LEXICAL_SIMILAR_THRESHOLD < ps.LEXICAL_REINFORCE_THRESHOLD <= 1.0
    assert ps.COSINE_SIMILAR_THRESHOLD < ps.COSINE_REINFORCE_THRESHOLD <= 1.0


# ---------------------------------------------------------------------------
# Both write paths
# ---------------------------------------------------------------------------

AGENT = "dg-agent"


@pytest.fixture
def cli(tmp_path, monkeypatch):
    import agentmemory._impl as _impl
    db_file = tmp_path / "brain.db"
    Brain(db_path=str(db_file), agent_id=AGENT)
    monkeypatch.setattr(_impl, "DB_PATH", db_file)
    monkeypatch.setattr(_impl, "_embed_query_safe", lambda *a, **k: None)
    captured = []
    monkeypatch.setattr(_impl, "json_out", lambda data, compact=False: captured.append(data))

    def add(content, category="convention", **extra):
        args = types.SimpleNamespace(
            content=content, category=category, scope="global", confidence=None,
            tags=None, source_event=None, type="episodic", reflexion=False,
            attribute=False, force=False, dry_run_worthiness=False, supersedes=None,
            file_path=None, file_line=None, agent=AGENT,
        )
        for k, v in extra.items():
            setattr(args, k, v)
        _impl.cmd_memory_add(args)
        return captured[-1]

    return db_file, add


@pytest.fixture
def mcp(tmp_path, monkeypatch):
    from agentmemory import mcp_server
    db_file = tmp_path / "brain.db"
    Brain(db_path=str(db_file), agent_id=AGENT)
    monkeypatch.setattr(mcp_server, "DB_PATH", db_file)
    monkeypatch.setattr(mcp_server, "_embed_safe", lambda *a, **k: None)

    def add(content, category="convention", **extra):
        return mcp_server.tool_memory_add(agent_id=AGENT, content=content,
                                          category=category, **extra)

    return db_file, add


def _conn(db_file):
    c = sqlite3.connect(str(db_file))
    c.row_factory = sqlite3.Row
    return c


@pytest.mark.parametrize("path", ["cli", "mcp"])
def test_write_path_reinforces_surface_duplicate(path, request):
    db_file, add = request.getfixturevalue(path)
    first = add("Use ruff for linting and black for formatting")
    mid = first["memory_id"]
    second = add("Use ruff for linting, and black for formatting.")
    assert second.get("deduplicated") is True
    assert second["reinforced_memory_id"] == mid
    c = _conn(db_file)
    row = c.execute("SELECT alpha, recalled_count FROM memories WHERE id=?", (mid,)).fetchone()
    assert row["recalled_count"] == 1 and row["alpha"] >= 2.0
    assert c.execute("SELECT COUNT(*) FROM memories WHERE retired_at IS NULL").fetchone()[0] == 1
    log = c.execute("SELECT decision, nearest_neighbor_id FROM hippocampus_pattern_separations").fetchall()
    assert [(r["decision"], r["nearest_neighbor_id"]) for r in log] == [("deduplicate", mid)]


@pytest.mark.parametrize("path", ["cli", "mcp"])
def test_write_path_separates_negation_flip(path, request):
    db_file, add = request.getfixturevalue(path)
    first = add("The payments service should never call the ledger API directly from the request path")
    second = add("The payments service should call the ledger API directly from the request path")
    assert not second.get("deduplicated")
    new_id, old_id = second["memory_id"], first["memory_id"]
    assert new_id != old_id
    assert second["pattern_separation"]["decision"] == "separate"
    c = _conn(db_file)
    assert c.execute("SELECT COUNT(*) FROM memories WHERE retired_at IS NULL").fetchone()[0] == 2
    edge = c.execute(
        "SELECT source_id, target_id FROM knowledge_edges WHERE relation_type=?",
        (ps.SEPARATION_RELATION,),
    ).fetchone()
    assert (edge["source_id"], edge["target_id"]) == (new_id, old_id)
    log = c.execute("SELECT decision, memory_id, separation_tag FROM hippocampus_pattern_separations").fetchone()
    assert (log["decision"], log["memory_id"]) == ("separate", new_id)
    assert "negation:never" in log["separation_tag"]


@pytest.mark.parametrize("path", ["cli", "mcp"])
def test_force_bypasses_the_gate(path, request):
    db_file, add = request.getfixturevalue(path)
    add("Bob owns the payments reconciliation job")
    second = add("Bob owns the payments reconciliation job", force=True)
    assert second.get("memory_id") and not second.get("deduplicated")


def test_dedup_is_scoped_by_category(mcp):
    db_file, add = mcp
    add("Bob owns the payments reconciliation job", category="project")
    second = add("Bob owns the payments reconciliation job", category="user")
    assert second.get("memory_id") and not second.get("deduplicated")


def test_explicit_supersedes_skips_reinforcement(cli):
    db_file, add = cli
    first = add("The backend runs on Python 3.11", category="environment")
    second = add("The backend runs on Python 3.11", category="environment",
                 supersedes=first["memory_id"])
    assert second.get("memory_id") and not second.get("deduplicated")


def test_known_entity_from_db_separates_lowercase_swap(mcp):
    db_file, add = mcp
    Brain(db_path=str(db_file), agent_id=AGENT).entity("Atlas", "project")
    add("the ingestion pipeline is owned by the atlas team", category="project")
    second = add("the ingestion pipeline is owned by the zephyr team", category="project")
    assert second["pattern_separation"]["decision"] == "separate"
    assert second["pattern_separation"]["key_token_diff"] == {"entity": ["atlas"]}
