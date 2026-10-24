"""Perirhinal familiarity gate (agentmemory.retrieval.answerability)."""

from __future__ import annotations

import sqlite3

import pytest

from agentmemory.retrieval import answerability as A


# ---------------------------------------------------------------------------
# Porter stems must equal memories_fts' index terms
# ---------------------------------------------------------------------------

_WORDS = (
    "caresses ponies ties caress cats feed agreed plastered bled motoring sing "
    "conflated troubled sized hopping tanned falling hissing fizzed failing filing "
    "happy sky relational conditional rational valenci hesitanci digitizer "
    "conformabli radicalli differentli vileli analogousli vietnamization predication "
    "operator feudalism decisiveness hopefulness callousness formaliti sensitiviti "
    "sensibiliti triplicate formative formalize electriciti electrical hopeful goodness "
    "revival allowance inference airliner gyroscopic adjustable defensible irritant "
    "replacement adjustment dependent adoption homologou communism activate angulariti "
    "homologous effective bowdlerize probate rate cease controll roll generalizations "
    "oscillators provisioned retained Kubernetes Grace's db-staging.internal 9:30 S3 "
    "Résumé naïve café über approved migration analytics escalations"
)


def test_present_terms_matches_full_stemming():
    text = "Kubernetes clusters were provisioned; the provisioning of happy ponies"
    wanted = {"kubernet", "cluster", "provis", "happi", "poni", "absent"}
    full = set(A._stem_texts([text])[0]) & wanted
    assert A._present_terms(text, wanted) == full == wanted - {"absent"}
    assert A._present_terms("", wanted) == set()


def test_fts_present_terms_agrees_with_text_scan(store):
    for q in ("What is the staging database host?",
              "Who approved the migration from Jenkins?",
              "When does the payments team hold standup?"):
        t = A.salient_terms(q)
        ids = list(range(1, len(CORPUS) + 1))
        got = A._fts_present_terms(store, t, ids)
        for i, text in enumerate(CORPUS, start=1):
            assert got[i] == A._present_terms(text, set(t.stems)), (q, text)


def test_corpus_stats_batched_in_one_statement(store):
    seen = []
    store.set_trace_callback(seen.append)
    surface = {"stage": "staging", "databas": "database", "nowher": "nowhere"}
    n, df = A._corpus_stats(store, list(surface), surface)
    store.set_trace_callback(None)
    assert n == len(CORPUS)
    assert df == {"stage": 1, "databas": 1, "nowher": 0}
    assert sum("memories_fts MATCH" in q for q in seen) == 1
    assert len([q for q in seen if not q.startswith("--")]) == 1  # N + df together


def test_porter_matches_fts5_tokenizer():
    from agentmemory.retrieval import _porter

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE s USING fts5(x, tokenize='porter unicode61')")
        conn.execute("CREATE VIRTUAL TABLE v USING fts5vocab(s, 'instance')")
    except sqlite3.OperationalError:
        pytest.skip("FTS5 / fts5vocab not available")
    conn.execute("INSERT INTO s(rowid, x) VALUES (1, ?)", (_WORDS,))
    ref = [t for t, in conn.execute("SELECT term FROM v ORDER BY offset")]
    conn.close()
    ours = [_porter.term(t) for t in A._tokens(_WORDS)]
    assert ours == ref


# ---------------------------------------------------------------------------
# Query terms
# ---------------------------------------------------------------------------

def test_salient_terms_drop_function_words_and_stem():
    t = A.salient_terms("Where are the production secrets stored?")
    assert t.stems == ["product", "secret", "store"]
    assert not t.focus and not t.entities


def test_answer_type_after_wh_word_is_marked_focus():
    t = A.salient_terms("What language is the billing service written in?")
    assert "languag" in t.focus
    assert "bill" in t.stems and "bill" not in t.focus
    # "kind of" / "type of" are skipped, the head noun is the focus
    t2 = A.salient_terms("What kind of database backs the API?")
    assert "databas" in t2.focus


def test_entities_capitalised_acronyms_and_identifiers():
    t = A.salient_terms("Which S3 bucket did Frank use for the SDK?")
    assert set(t.entities) == {"s3", "frank", "sdk"}
    # an entity is never down-weighted as an answer type
    assert "s3" not in t.focus


def test_surface_words_kept_for_fts_queries():
    # Porter is not idempotent: MATCH '"databas"' would look up "databa".
    t = A.salient_terms("Which databases are staging?")
    assert t.surface == {"databas": "databases", "stage": "staging"}


def test_possessive_and_first_word_capital():
    t = A.salient_terms("Grace's phone number")
    assert t.stems == ["grace", "phone", "number"]
    assert t.entities == []          # sentence-initial capital is not a cue


# ---------------------------------------------------------------------------
# Pure scoring pieces
# ---------------------------------------------------------------------------

def test_coverage_optional_terms_only_count_when_present():
    w = {"a": 1.0, "b": 1.0, "c": 2.0}
    assert A._coverage(w, {"a", "b"}) == pytest.approx(0.5)
    assert A._coverage(w, {"a", "b"}, optional={"c"}) == pytest.approx(1.0)
    assert A._coverage(w, {"a", "b", "c"}, optional={"c"}) == pytest.approx(1.0)
    assert A._coverage({}, set()) == 0.0


def test_combine_renormalises_over_present_signals():
    assert A.combine({"coverage": 1.0, "bm25": None, "entity": None}) == pytest.approx(1.0)
    both = A.combine({"coverage": 1.0, "bm25": 0.0})
    w = A.SIGNAL_WEIGHTS
    assert both == pytest.approx(w["coverage"] / (w["coverage"] + w["bm25"]))
    assert A.combine({}) == 0.0
    assert A.combine({"coverage": 7.0}) == 1.0     # clamped


def test_squash_is_monotone_and_centred():
    assert A.squash(A.FAMILIARITY_MIDPOINT) == pytest.approx(0.5)
    xs = [i / 20 for i in range(21)]
    ys = [A.squash(x) for x in xs]
    assert ys == sorted(ys)
    assert 0.0 < ys[0] < 0.01 and 0.9 < ys[-1] < 1.0


def test_constants_are_coherent():
    lo, hi = A.RECOLLECTION_BAND
    assert 0.0 < lo < A.ANSWERABLE_THRESHOLD < hi < 1.0
    assert abs(sum(v for k, v in A.SIGNAL_WEIGHTS.items() if k != "vector") - 0.9) < 1e-9
    assert 0.0 < A.ANSWER_TYPE_WEIGHT <= 1.0


def test_vector_similarity_from_l2_distance():
    assert A._vector_similarity({"distance": 0.0}) == pytest.approx(1.0)
    assert A._vector_similarity({"distance": 2 ** 0.5}) == pytest.approx(0.0)
    assert A._vector_similarity({"similarity": 0.8}) == pytest.approx(0.8)
    assert A._vector_similarity({}) is None


# ---------------------------------------------------------------------------
# assess_familiarity against a tiny real FTS5 store
# ---------------------------------------------------------------------------

CORPUS = [
    "The staging database host is db-staging.internal on port 5433",
    "Production secrets are stored in AWS Secrets Manager under the prod prefix",
    "The billing service is written in Go and owned by the payments team",
    "Henry approved the migration from Webpack to Vite in the Q2 planning review",
    "The search team holds standup at 9:30 every weekday",
    "The company VPN uses WireGuard",
]


@pytest.fixture
def store():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        "CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT, category TEXT,"
        " tags TEXT, retired_at TEXT);"
        "CREATE VIRTUAL TABLE memories_fts USING fts5(content, category, tags,"
        " content=memories, content_rowid=id, tokenize='porter unicode61');"
    )
    for i, text in enumerate(CORPUS, start=1):
        db.execute("INSERT INTO memories(id, content, category) VALUES (?, ?, 'project')", (i, text))
        db.execute("INSERT INTO memories_fts(rowid, content, category, tags) VALUES (?, ?, 'project', '')",
                   (i, text))
    yield db
    db.close()


def _hits(db, query):
    """Rows the way cmd_search hands them over: best-first, type=memory."""
    t = A.salient_terms(query)
    expr = " OR ".join(A._fts_phrase(t.surface[s]) for s in t.stems)
    rows = db.execute(
        "SELECT m.id, 'memory' AS type, m.content, m.category, m.tags,"
        " bm25(memories_fts, 3.0, 1.0, 1.0) AS fts_rank"
        " FROM memories_fts f JOIN memories m ON m.id = f.rowid"
        " WHERE memories_fts MATCH ? ORDER BY fts_rank LIMIT 5", (expr,)
    ).fetchall()
    return [dict(r, source="keyword") for r in rows]


def test_answerable_query_is_familiar(store):
    q = "What is the staging database host?"
    fam = A.assess_familiarity(q, _hits(store, q), db=store)
    assert fam.answerable
    assert fam.signals["coverage"] == pytest.approx(1.0)
    assert fam.best_id == 1
    assert fam.missing_terms == []


def test_near_topic_query_is_unfamiliar(store):
    q = "Who is the on-call engineer for the billing service?"
    hits = _hits(store, q)
    assert hits, "lexical retriever still returns something"
    fam = A.assess_familiarity(q, hits, db=store)
    assert not fam.answerable
    assert set(fam.missing_terms) >= {"call", "engin"}


def test_missing_named_entity_is_reported(store):
    q = "Who approved the migration from Jenkins?"
    fam = A.assess_familiarity(q, _hits(store, q), db=store)
    assert fam.signals["entity"] == 0.0
    assert not fam.answerable
    assert fam.reason == "named_entity_not_in_memory"


def test_answerable_scores_above_near_topic(store):
    good = A.assess_familiarity("What language is the billing service written in?",
                                _hits(store, "billing service written language"), db=store)
    bad = A.assess_familiarity("What is the staging database password?",
                               _hits(store, "staging database password"), db=store)
    assert good.score > bad.score


def test_no_candidates_is_not_answerable():
    fam = A.assess_familiarity("anything at all", [])
    assert fam.score == 0.0 and not fam.answerable and fam.reason == "no_candidates"


def test_indirect_candidates_are_ignored(store):
    q = "What is the staging database host?"
    rows = [dict(r, source="graph") for r in _hits(store, q)]
    fam = A.assess_familiarity(q, rows, db=store)
    assert fam.reason == "no_candidates"


def test_query_without_salient_terms_trusts_retriever():
    fam = A.assess_familiarity("what is it?", [{"id": 1, "content": "x", "type": "memory"}])
    assert fam.answerable and fam.reason == "no_salient_terms"


def test_works_without_db_using_uniform_weights():
    rows = [{"id": 1, "type": "memory", "content": "The company VPN uses WireGuard"}]
    fam = A.assess_familiarity("Which VPN does the company use?", rows)
    assert fam.answerable
    assert "bm25" not in fam.signals      # needs corpus statistics


def test_recollection_finds_a_better_trace(store, monkeypatch):
    # Hand the gate only a weak hit; the answering memory (id 5) is in the
    # store but not among the candidates. Widen the band so the pass runs.
    monkeypatch.setattr(A, "RECOLLECTION_BAND", (0.0, 1.0))
    q = "When does the search team hold standup?"
    weak = [dict(r, source="keyword") for r in _hits(store, "payments team")
            if r["id"] != 5][:1]
    assert A.assess_familiarity(q, weak, db=store).recollection is None  # default: off
    fam = A.assess_familiarity(q, weak, db=store, recollection=True)
    assert fam.recollection is not None and fam.recollection["improved"]
    assert fam.best_id == 5
    assert fam.score > fam.recollection["before"]


def test_assess_answerability_contract(store):
    q = "What is the staging database host?"
    out = A.assess_answerability(q, None, {"memories": _hits(store, q), "events": []}, db=store)
    assert out["score"] == out["familiarity"]
    assert out["abstain"] is (not out["answerable"])
    assert out["abstain"] is False


# ---------------------------------------------------------------------------
# cmd_search / MCP wiring
# ---------------------------------------------------------------------------

def test_cmd_search_flags_without_dropping_and_abstains_on_opt_in():
    from tests.bench.memory_quality import bench_brain

    with bench_brain() as brain:
        brain.add_cli("The staging database host is db-staging.internal on port 5433", "environment")
        brain.add_cli("The billing service is written in Go and owned by the payments team", "project")

        hit = brain.search("What is the staging database host?")
        assert hit["answerable"] is True and hit["familiarity"] >= A.ANSWERABLE_THRESHOLD

        near = brain.search("Who is the on-call engineer for the billing service?")
        assert near["answerable"] is False
        assert near["memories"], "default must keep returning hits"
        assert near["metacognition"]["abstained"] is False

        import types
        args = types.SimpleNamespace(
            query="Who is the on-call engineer for the billing service?", limit=10,
            tables="memories", no_recency=False, no_graph=True, budget=None,
            min_salience=None, mmr=False, mmr_lambda=0.7, explore=False, profile=None,
            pagerank_boost=0.0, quantum=False, benchmark=False, agent="bench-agent",
            format="json", oneline=False, verbose=False, output="return", abstain=True,
        )
        out = brain._impl.cmd_search(args)
        assert out["answerable"] is False and out["memories"] == []
        assert out["metacognition"]["abstained"] is True

        args.query = "What is the staging database host?"
        kept = brain._impl.cmd_search(args)
        assert kept["answerable"] is True and kept["memories"]


def test_mcp_memory_search_and_search_carry_flag():
    from agentmemory import mcp_server
    from tests.bench.memory_quality import bench_brain

    with bench_brain(with_mcp=True) as brain:
        brain.add_mcp("The staging database host is db-staging.internal on port 5433", "environment")
        q_near = "Who is the on-call engineer for the staging database?"

        r = mcp_server.tool_memory_search(agent_id="bench-agent", query="staging database host")
        assert r["ok"] and r["answerable"] is True and r["memories"]

        r = mcp_server.tool_memory_search(agent_id="bench-agent", query=q_near)
        assert r["answerable"] is False and r["memories"]
        r = mcp_server.tool_memory_search(agent_id="bench-agent", query=q_near, abstain=True)
        assert r["answerable"] is False and r["memories"] == [] and r["count"] == 0

        s = mcp_server.tool_search(agent_id="bench-agent", query=q_near)
        assert "familiarity" in s and s["results"]
        s = mcp_server.tool_search(agent_id="bench-agent", query=q_near, abstain=True)
        assert s["results"] == [] and s["answerable"] is False
