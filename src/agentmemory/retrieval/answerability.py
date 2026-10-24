"""Perirhinal familiarity gate: can search say "not in memory"?

Dual-process memory theory splits recognition into two routes:

* **familiarity** — a fast, scalar "have I seen this before?" signal
  (perirhinal cortex). No details are retrieved, only a sense of match
  strength.
* **recollection** — a slower, effortful retrieval of the specific trace and
  its context (hippocampus).

``cmd_search`` always returns *something* for a query that shares vocabulary
with the store, and its scores are max-normalised per bucket, so the best hit
always scores the same (1.0 x intent multiplier) whether it answers the query
or merely shares a word with it. That makes "nothing in memory answers this"
invisible. This module computes a familiarity score in [0, 1] from evidence
that exists *before* that normalisation:

``coverage``   IDF-weighted fraction of the query's salient terms present in
               the hit (Porter-stemmed exactly like ``memories_fts``). A hit
               that matches "staging database" but not "password" covers
               only the common part of the question.
``bm25``       Raw BM25 of the hit over the salient terms, divided by the BM25
               an ideal hit (every term once, average length) would get under
               the same corpus statistics. Raw BM25 grows with log(N), so the
               ratio is what transfers across store sizes.
``entity``     Fraction of the query's named things (capitalised words,
               acronyms, identifiers with digits) found in the hit. Only
               present when the query names something.
``margin``     How far the best hit stands out from the runner-up, in raw
               BM25: (s1 - s2) / s1.
``vector``     Cosine similarity of the hit's embedding, when the vector leg
               ran and attached a distance.

The signals are averaged with fixed weights (absent signals drop out and the
weights renormalise), and the average goes through a logistic squash centred
on ``FAMILIARITY_MIDPOINT``, which makes the score read as P(answerable).
``answerable`` is ``familiarity >= ANSWERABLE_THRESHOLD`` (0.25, a cost-
asymmetric cut: false abstentions are the expensive error).

When the caller is about to act on the verdict (``recollection=True``, which
the search paths pass only under ``--abstain`` / ``abstain=True``), hits in
the uncertain middle band get one recollection pass (``_recollect``): the
store is re-probed with an expanded query that requires the terms the best
hit was missing, and the best re-probed memory replaces the hit if it covers
the question better. The annotate-only default skips it to stay cheap.

How the constants were chosen: signal weights, the answer-type rule and the
threshold by principle (see each constant); only the logistic midpoint and
slope were fit, on one half of the abstention bench fixtures at a time with
the other half held out (``tests/bench/memory_quality.py``).

Nothing in this module drops results by itself. ``cmd_search`` and the MCP
search tools only add ``answerable`` / ``familiarity`` to their payloads
unless the caller opts in with ``--abstain`` / ``abstain=True``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from agentmemory.retrieval import _porter

__all__ = [
    "ANSWERABLE_THRESHOLD",
    "Familiarity",
    "assess_answerability",
    "assess_familiarity",
    "salient_terms",
]

# ---------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------

#: Signal weights for the familiarity average. Coverage carries most of the
#: weight: "does the remembered trace contain what the question asks about"
#: is the core of recognition. BM25 ratio adds length / term-frequency
#: evidence on top of coverage, so it gets less. Entity overlap is a strong
#: but sparse cue (only when the query names something). Margin is a weak,
#: noisy cue (many answerable questions have several relevant memories).
#: Vector similarity is as strong as BM25 when it exists.
SIGNAL_WEIGHTS: Dict[str, float] = {
    "coverage": 0.45,
    "bm25": 0.20,
    "entity": 0.20,
    "margin": 0.05,
    "vector": 0.20,
}

#: Centre and slope of the logistic squash over the weighted average, i.e.
#: the calibration that turns the average into P(answerable). Fit by 1-D
#: logistic regression on each half of the abstention bench fixtures
#: separately (even / odd query index): both halves gave a midpoint of 0.65
#: and a slope of 6.5-7.2, rounded here. The other half is the held-out check.
FAMILIARITY_MIDPOINT = 0.65
FAMILIARITY_SLOPE = 8.0

#: familiarity >= this => ``answerable``. Not 0.5: a false "not in memory"
#: costs more than a false "maybe" (the agent loses a memory it has, versus
#: reading hits that turn out not to answer). Treating a false abstention as
#: 3x the cost of a false answer puts the Bayes cut at
#: P(answerable) = 1 / (1 + 3) = 0.25.
ANSWERABLE_THRESHOLD = 0.25

#: Familiarity band where one recollection pass runs before deciding. Below
#: it the hits are clearly unfamiliar, above it clearly familiar; in between
#: the verdict could flip if a better trace exists further down the store.
RECOLLECTION_BAND: Tuple[float, float] = (0.10, 0.50)

#: Number of top-ranked direct candidates the gate looks at. Familiarity is
#: the best of them, so a recency or tie-break reshuffle in the ranker above
#: does not flip the verdict.
CANDIDATES_CONSIDERED = 3

#: In "what/which <X> ..." questions X is the expected answer type
#: ("what *language* is billing written in" -> "Go"). Memories state the
#: answer, not its type, so a missing X is uninformative and drops out of the
#: coverage denominator; a present X still counts at this fraction of its
#: IDF weight (mild confirmation).
ANSWER_TYPE_WEIGHT = 0.5

#: Column weights used by cmd_search's BM25 over memories_fts
#: (content, category, tags). Kept identical so the ratio matches retrieval.
BM25_COLUMN_WEIGHTS: Tuple[float, float, float] = (3.0, 1.0, 1.0)

#: Below this many active memories corpus statistics are meaningless and IDF
#: falls back to uniform term weights.
MIN_CORPUS_FOR_IDF = 2

# Function words plus question scaffolding that carries no content. Superset
# of cmd_search's _FTS_STOPWORDS.
_STOPWORDS = frozenset({
    "a", "about", "after", "all", "also", "am", "an", "and", "any", "are", "as",
    "at", "be", "been", "before", "being", "between", "but", "by", "can",
    "could", "currently", "did", "do", "does", "doing", "during", "each", "for",
    "from", "get", "got", "had", "has", "have", "having", "he", "her", "here",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just",
    "know", "like", "long", "many", "me", "much", "my", "now", "of", "often",
    "on", "one", "or", "our", "out", "over", "per", "please", "she", "should",
    "so", "some", "tell", "than", "that", "the", "their", "them", "then",
    "there", "these", "they", "this", "those", "to", "under", "up", "us", "use",
    "used", "uses", "using", "was", "we", "were", "what", "when", "where",
    "whether", "which", "while", "who", "whom", "whose", "why", "will", "with",
    "would", "you", "your",
})
_WH_FOCUS = frozenset({"what", "which", "whose"})
_FOCUS_SKIP = frozenset({"kind", "sort", "type", "of"})

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_TEXT_FIELDS = ("content", "text", "summary", "detail", "title", "name",
                "compiled_truth", "description", "goal", "rationale", "tags")
_INDIRECT_SOURCES = frozenset({"graph", "explore"})


# ---------------------------------------------------------------------------
# Tokenisation (Porter stems identical to memories_fts' tokenizer)
# ---------------------------------------------------------------------------

def _tokens(text: str) -> List[str]:
    """unicode61-style tokens: runs of letters/digits, original case."""
    return _TOKEN_RE.findall(text or "")


def _stem_texts(texts: Sequence[str]) -> List[List[str]]:
    """Index terms for each text's tokens, aligned with :func:`_tokens`."""
    return [[_porter.term(t) for t in _tokens(text)] for text in texts]


def _present_terms(text: str, wanted: set) -> set:
    """The subset of ``wanted`` index terms that occur in ``text``.

    Memories can be whole chat sessions, so stemming every token is the
    expensive part of the gate. Porter only rewrites a word's tail: apart
    from the last two letters of the stem (``-biliti`` -> ``-ble`` is the
    worst case) a stem is a prefix of every word that produces it. So only
    unique tokens starting with such a prefix of a wanted term get stemmed.
    """
    if not wanted or not text:
        return set()
    keys = tuple({w[: max(1, len(w) - 2)] for w in wanted})
    found = set()
    for low in set(_TOKEN_RE.findall(text.lower())):
        if not low.isascii():
            low = _porter.fold(low)
        if not low.startswith(keys):
            continue
        t = _porter.stem(low)
        if t in wanted:
            found.add(t)
    return found


@dataclass
class _QueryTerms:
    stems: List[str]                      # salient stems, query order, unique
    focus: set = field(default_factory=set)      # answer-type stems
    entities: List[str] = field(default_factory=list)  # stems of named things
    # stem -> lower-cased surface word. FTS5 MATCH re-stems its input and
    # Porter is not idempotent ("database" -> "databas" -> "databa"), so
    # queries against memories_fts must use the surface word, not the stem.
    surface: Dict[str, str] = field(default_factory=dict)


def _is_entity_token(tok: str, position: int) -> bool:
    if any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
        return True                                   # S3, v3, gpt4
    if len(tok) >= 2 and tok.isupper():
        return True                                   # API, SDK, VPN
    if position > 0 and tok[:1].isupper():
        return True                                   # Frank, Kubernetes
    return False


def salient_terms(query: str) -> _QueryTerms:
    """Content-bearing stems of ``query`` plus answer-type and entity marks."""
    toks = _tokens(query)
    stems = _stem_texts([query])[0] if toks else []
    seen: set = set()
    out = _QueryTerms(stems=[])
    prev_wh = False
    for i, (tok, stem) in enumerate(zip(toks, stems)):
        low = tok.lower()
        if low in _WH_FOCUS:
            prev_wh = True
            continue
        if low in _STOPWORDS or (len(low) < 2 and not low.isdigit()):
            if low not in _FOCUS_SKIP:
                prev_wh = False
            continue
        if low in _FOCUS_SKIP and prev_wh:
            continue
        if stem not in seen:
            seen.add(stem)
            out.stems.append(stem)
            out.surface[stem] = _porter.fold(tok)
            if _is_entity_token(tok, i):
                out.entities.append(stem)
        if prev_wh:
            out.focus.add(stem)
        prev_wh = False
    # A term that is both the answer type and a named thing ("which S3
    # bucket") is a named thing first.
    out.focus -= set(out.entities)
    return out


def _row_text(row: Dict[str, Any]) -> str:
    parts = []
    for key in _TEXT_FIELDS:
        val = row.get(key)
        if val:
            parts.append(val if isinstance(val, str) else str(val))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Corpus statistics (memories_fts)
# ---------------------------------------------------------------------------

def _fts_phrase(stem: str) -> str:
    return '"' + stem.replace('"', '""') + '"'


def _corpus_stats(db, stems: Sequence[str],
                  surface: Optional[Dict[str, str]] = None) -> Optional[Tuple[int, Dict[str, int]]]:
    """(N active memories, {stem: document frequency}) or None."""
    if db is None or not stems:
        return None
    try:
        n = int(db.execute(
            "SELECT COUNT(*) FROM memories WHERE retired_at IS NULL"
        ).fetchone()[0])
        if n < MIN_CORPUS_FOR_IDF:
            return None
        # One statement for every term's document frequency.
        uniq = list(dict.fromkeys(stems))
        sub = ", ".join(
            "(SELECT COUNT(*) FROM memories_fts WHERE memories_fts MATCH ?)" for _ in uniq
        )
        surface = surface or {}
        counts = db.execute(f"SELECT {sub}",
                            [_fts_phrase(surface.get(t, t)) for t in uniq]).fetchone()
        return n, {t: int(c) for t, c in zip(uniq, counts)}
    except Exception:
        return None


def _idf(n: int, df: int) -> float:
    """Always-positive BM25 IDF (Lucene form)."""
    return math.log(1.0 + (n - df + 0.5) / (df + 0.5))


def _fts5_idf(n: int, df: int) -> float:
    """The IDF FTS5's bm25() itself uses (clamped like FTS5 does)."""
    return max(math.log((n - df + 0.5) / (df + 0.5)), 1e-6)


def _fts_present_terms(db, terms: "_QueryTerms",
                       rowids: Sequence[int]) -> Optional[Dict[int, set]]:
    """{rowid: salient stems it contains} from memories_fts, one statement.

    Every rowid in ``rowids`` gets an entry (possibly empty). None on error
    (the caller then scans the row text instead).
    """
    if db is None or not rowids:
        return None
    ids = list(dict.fromkeys(int(r) for r in rowids))
    ph = ",".join("?" * len(ids))
    parts, params = [], []
    for i, s in enumerate(terms.stems):
        parts.append(f"SELECT rowid, {i} FROM memories_fts "
                     f"WHERE memories_fts MATCH ? AND rowid IN ({ph})")
        # content + tags, like _row_text (category labels are not evidence)
        params.append("{content tags} : " + _fts_phrase(terms.surface.get(s, s)))
        params.extend(ids)
    out: Dict[int, set] = {i: set() for i in ids}
    if not parts:
        return out
    try:
        for rid, idx in db.execute(" UNION ALL ".join(parts), params):
            out.setdefault(int(rid), set()).add(terms.stems[int(idx)])
    except Exception:
        return None
    return out


def _raw_bm25(db, stems: Sequence[str], rowids: Sequence[int],
              surface: Optional[Dict[str, str]] = None) -> Dict[int, float]:
    """FTS5 bm25 (positive, larger = better) of ``rowids`` over ``stems``."""
    if db is None or not stems or not rowids:
        return {}
    surface = surface or {}
    expr = " OR ".join(_fts_phrase(surface.get(s, s)) for s in stems)
    w = BM25_COLUMN_WEIGHTS
    ph = ",".join("?" * len(rowids))
    try:
        rows = db.execute(
            f"SELECT rowid, -bm25(memories_fts, {w[0]}, {w[1]}, {w[2]}) "
            f"FROM memories_fts WHERE memories_fts MATCH ? AND rowid IN ({ph})",
            (expr, *rowids),
        ).fetchall()
    except Exception:
        return {}
    return {int(r[0]): float(r[1]) for r in rows}


def _is_memory_row(row: Dict[str, Any]) -> bool:
    t = row.get("type")
    if t is not None:
        return t == "memory"
    # MCP memory_search rows are ``SELECT m.*`` with no ``type`` column.
    return "content" in row and ("memory_type" in row or "category" in row)


def _vector_similarity(row: Dict[str, Any]) -> Optional[float]:
    """Cosine similarity from a sqlite-vec distance, when one is attached."""
    if row.get("similarity") is not None:
        try:
            return max(0.0, min(1.0, float(row["similarity"])))
        except (TypeError, ValueError):
            return None
    d = row.get("distance")
    if d is None:
        return None
    try:
        d = float(d)
    except (TypeError, ValueError):
        return None
    # vec0 defaults to L2 over unit-normalised embeddings: cos = 1 - d^2 / 2
    return max(0.0, min(1.0, 1.0 - d * d / 2.0))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass
class Familiarity:
    score: float                       # calibrated familiarity in [0, 1]
    answerable: bool
    reason: str
    raw: float = 0.0                   # weighted signal average before squash
    signals: Dict[str, float] = field(default_factory=dict)
    salient_terms: List[str] = field(default_factory=list)
    missing_terms: List[str] = field(default_factory=list)
    best_id: Any = None
    recollection: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        d = {
            "familiarity": self.score,
            "answerable": self.answerable,
            "reason": self.reason,
            "raw": self.raw,
            "signals": dict(self.signals),
            "salient_terms": list(self.salient_terms),
            "missing_terms": list(self.missing_terms),
            "best_id": self.best_id,
        }
        if self.recollection is not None:
            d["recollection"] = dict(self.recollection)
        return d


def squash(raw: float) -> float:
    """Logistic map of the weighted signal average onto [0, 1]."""
    return 1.0 / (1.0 + math.exp(-FAMILIARITY_SLOPE * (raw - FAMILIARITY_MIDPOINT)))


def combine(signals: Dict[str, Optional[float]]) -> float:
    """Weighted mean of the available signals (None = absent)."""
    num = den = 0.0
    for name, value in signals.items():
        if value is None:
            continue
        w = SIGNAL_WEIGHTS.get(name, 0.0)
        num += w * max(0.0, min(1.0, float(value)))
        den += w
    return num / den if den else 0.0


def _term_weights(terms: _QueryTerms, stats) -> Dict[str, float]:
    weights = {}
    for s in terms.stems:
        w = _idf(stats[0], stats[1].get(s, 0)) if stats else 1.0
        if s in terms.focus:
            w *= ANSWER_TYPE_WEIGHT
        weights[s] = w
    return weights


def _coverage(weights: Dict[str, float], present: set, optional: Iterable[str] = ()) -> float:
    """Weighted share of query terms present; ``optional`` terms only count
    when present."""
    opt = set(optional)
    total = sum(w for s, w in weights.items() if s in present or s not in opt)
    if total <= 0:
        return 0.0
    return sum(w for s, w in weights.items() if s in present) / total


def _ideal_bm25(terms: _QueryTerms, stats) -> float:
    n, df = stats
    return BM25_COLUMN_WEIGHTS[0] * sum(_fts5_idf(n, df.get(s, 0)) for s in terms.stems)


def _candidate_signals(
    terms: _QueryTerms,
    weights: Dict[str, float],
    stems: set,
    bm25: Optional[float],
    ideal: Optional[float],
    runner_up: Optional[float],
    vector: Optional[float],
) -> Dict[str, Optional[float]]:
    sig: Dict[str, Optional[float]] = {
        "coverage": _coverage(weights, stems, terms.focus),
        "bm25": None,
        "entity": None,
        "margin": None,
        "vector": vector,
    }
    if bm25 is not None and ideal:
        sig["bm25"] = min(1.0, bm25 / ideal)
        if bm25 > 0:
            sig["margin"] = max(0.0, (bm25 - (runner_up or 0.0)) / bm25)
    if terms.entities:
        sig["entity"] = sum(1 for e in terms.entities if e in stems) / len(terms.entities)
    return sig


def _direct(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in candidates or []:
        if not isinstance(r, dict):
            continue
        if r.get("source") in _INDIRECT_SOURCES or r.get("_temporal_neighbor"):
            continue
        out.append(r)
    return out


def _score_candidates(
    terms: _QueryTerms,
    rows: List[Dict[str, Any]],
    db,
    stats,
) -> Tuple[float, Dict[str, Optional[float]], Optional[Dict[str, Any]], set]:
    """Best (raw, signals, row, stems) over ``rows``."""
    weights = _term_weights(terms, stats)
    wanted = set(terms.stems)
    mem_ids = [int(r["id"]) for r in rows if _is_memory_row(r) and r.get("id") is not None]
    # Memory rows: ask memories_fts which terms each one contains (posting
    # list lookups, no text scan). Other rows, or no db: scan their text.
    indexed = _fts_present_terms(db, terms, mem_ids) if stats else None
    stemmed = []
    for r in rows:
        rid = r.get("id")
        if indexed is not None and rid is not None and _is_memory_row(r) and int(rid) in indexed:
            stemmed.append(indexed[int(rid)])
        else:
            stemmed.append(_present_terms(_row_text(r), wanted))
    bm25 = _raw_bm25(db, terms.stems, mem_ids, terms.surface) if stats else {}
    ideal = _ideal_bm25(terms, stats) if stats else None
    best: Tuple[float, Dict[str, Optional[float]], Optional[Dict[str, Any]], set] = (-1.0, {}, None, set())
    ranked_bm25 = sorted(bm25.values(), reverse=True)
    for row, stem_set in zip(rows, stemmed):
        b = bm25.get(int(row["id"])) if row.get("id") is not None and _is_memory_row(row) else None
        others = list(ranked_bm25)
        if b is not None and b in others:
            others.remove(b)
        runner_up = others[0] if others else 0.0
        sig = _candidate_signals(terms, weights, stem_set, b, ideal, runner_up,
                                 _vector_similarity(row))
        raw = combine(sig)
        if raw > best[0]:
            best = (raw, sig, row, stem_set)
    return best


def _recollect(terms: _QueryTerms, missing: Sequence[str], db, exclude: set,
               limit: int = 5) -> List[Dict[str, Any]]:
    """One expanded re-probe: memories that contain a missing salient term.

    Familiarity only looked at the ranker's top hits; the trace that answers
    the question may sit lower because it shares fewer of the *common*
    terms. Require at least one missing term (prefix-expanded to catch
    morphological variants the stemmer leaves apart) plus any other salient
    term, and return the strongest matches.
    """
    if db is None or not missing:
        return []
    need = " OR ".join(_fts_phrase(s) + "*" for s in missing)
    rest = [s for s in terms.stems if s not in missing]
    expr = f"({need})" + (f" AND ({' OR '.join(_fts_phrase(s) + '*' for s in rest)})" if rest else "")
    w = BM25_COLUMN_WEIGHTS
    try:
        rows = db.execute(
            f"SELECT m.id, 'memory' AS type, m.content, m.category, m.tags "
            f"FROM memories_fts f JOIN memories m ON m.id = f.rowid "
            f"WHERE memories_fts MATCH ? AND m.retired_at IS NULL "
            f"ORDER BY bm25(memories_fts, {w[0]}, {w[1]}, {w[2]}) LIMIT ?",
            (expr, limit + len(exclude)),
        ).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        d = dict(r) if not isinstance(r, dict) else r
        if d.get("id") in exclude:
            continue
        out.append({"id": d["id"], "type": "memory", "content": d.get("content"),
                    "category": d.get("category"), "tags": d.get("tags"),
                    "source": "recollection"})
        if len(out) >= limit:
            break
    return out


def assess_familiarity(
    query: str,
    candidates: Sequence[Dict[str, Any]],
    *,
    db=None,
    threshold: float = ANSWERABLE_THRESHOLD,
    recollection: bool = False,
) -> Familiarity:
    """Familiarity of ``query`` against ranked search ``candidates``.

    ``candidates`` are result rows best-first (any bucket). ``db`` is an open
    connection to the brain.db the rows came from; without it the gate uses
    uniform term weights and only the coverage / entity / vector signals.
    """
    terms = salient_terms(query)
    rows = _direct(candidates)[:CANDIDATES_CONSIDERED]
    if not rows:
        return Familiarity(0.0, False, "no_candidates", salient_terms=terms.stems,
                           missing_terms=list(terms.stems))
    if not terms.stems:
        # Nothing content-bearing to recognise ("what is it?"): trust the
        # retriever rather than abstain on a technicality.
        return Familiarity(1.0, True, "no_salient_terms", raw=1.0, best_id=rows[0].get("id"))

    stats = _corpus_stats(db, terms.stems, terms.surface)
    raw, sig, best_row, stem_set = _score_candidates(terms, rows, db, stats)
    score = squash(raw)
    missing = [s for s in terms.stems if s not in stem_set]
    reco_info: Optional[Dict[str, Any]] = None

    lo, hi = RECOLLECTION_BAND
    if recollection and lo <= score < hi and missing and db is not None:
        seen = {r.get("id") for r in rows}
        extra = _recollect(terms, missing, db, seen)
        reco_info = {"probed": len(extra), "improved": False, "before": round(score, 4)}
        if extra:
            r_raw, r_sig, r_row, r_stems = _score_candidates(terms, extra, db, stats)
            if r_raw > raw:
                raw, sig, best_row, stem_set = r_raw, r_sig, r_row, r_stems
                score = squash(raw)
                missing = [s for s in terms.stems if s not in stem_set]
                reco_info.update(improved=True, best_id=best_row.get("id"))
        reco_info["after"] = round(score, 4)

    answerable = score >= threshold
    if answerable:
        reason = "familiar"
    elif sig.get("entity") == 0.0:
        reason = "named_entity_not_in_memory"
    else:
        reason = "low_familiarity"
    return Familiarity(
        score=round(score, 4),
        answerable=answerable,
        reason=reason,
        raw=round(raw, 4),
        signals={k: round(v, 4) for k, v in sig.items() if v is not None},
        salient_terms=list(terms.stems),
        missing_terms=missing,
        best_id=(best_row or {}).get("id"),
        recollection=reco_info,
    )


_BUCKET_ORDER = ("memories", "procedures", "decisions", "events", "context", "entities")


def assess_answerability(
    query: str,
    plan: Any = None,
    buckets: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    *,
    db=None,
    threshold: float = ANSWERABLE_THRESHOLD,
    recollection: bool = False,
) -> Dict[str, Any]:
    """``cmd_search`` entry point.

    Flattens the result buckets best-first by ``final_score`` and returns
    ``Familiarity.as_dict()`` plus the keys the ``cmd_search`` import site
    reads: ``score`` (= familiarity) and ``abstain`` (= not answerable; the
    caller decides whether to act on it). ``plan`` is accepted for the
    query-planner contract and ignored.
    """
    flat: List[Dict[str, Any]] = []
    for name in _BUCKET_ORDER:
        flat.extend((buckets or {}).get(name) or [])
    for name, rows in (buckets or {}).items():
        if name not in _BUCKET_ORDER:
            flat.extend(rows or [])
    flat.sort(key=lambda r: float(r.get("final_score") or 0.0), reverse=True)
    fam = assess_familiarity(query, flat, db=db, threshold=threshold,
                             recollection=recollection)
    out = fam.as_dict()
    out["score"] = fam.score
    out["abstain"] = not fam.answerable
    return out
