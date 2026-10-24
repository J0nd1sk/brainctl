"""Porter (1980) stemmer, matching SQLite FTS5's ``porter`` tokenizer.

The familiarity gate compares query terms with memory text the way
``memories_fts`` does, so it needs the same stems. Asking SQLite for them
would mean opening a scratch connection per search; this is the reference
algorithm in pure Python instead (``tests/test_familiarity_gate.py`` checks
it against FTS5's own output). Input is one lower-case unicode61 token.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

_VOWELS = frozenset("aeiou")
# fts5_porter.c passes tokens shorter than 3 or longer than 64 through.
_MIN_LEN = 3
_MAX_LEN = 64


def _is_cons(w: str, i: int) -> bool:
    c = w[i]
    if c in _VOWELS:
        return False
    if c == "y":
        return i == 0 or not _is_cons(w, i - 1)
    return True


def _measure(stem: str) -> int:
    """m in [C](VC)^m[V]."""
    m = 0
    i, n = 0, len(stem)
    while i < n and _is_cons(stem, i):
        i += 1
    while i < n:
        while i < n and not _is_cons(stem, i):
            i += 1
        if i >= n:
            break
        while i < n and _is_cons(stem, i):
            i += 1
        m += 1
    return m


def _has_vowel(stem: str) -> bool:
    return any(not _is_cons(stem, i) for i in range(len(stem)))


def _double_cons(w: str) -> bool:
    return len(w) >= 2 and w[-1] == w[-2] and _is_cons(w, len(w) - 1)


def _cvc(w: str) -> bool:
    """*o: ends consonant-vowel-consonant, last not w, x or y."""
    if len(w) < 3:
        return False
    n = len(w)
    return (_is_cons(w, n - 3) and not _is_cons(w, n - 2) and _is_cons(w, n - 1)
            and w[-1] not in "wxy")


def _replace(w: str, rules, cond) -> str:
    for suf, rep in rules:
        if w.endswith(suf):
            stem = w[: len(w) - len(suf)]
            return stem + rep if cond(stem) else w
    return w


_STEP2 = (
    ("ational", "ate"), ("tional", "tion"), ("enci", "ence"), ("anci", "ance"),
    ("izer", "ize"), ("bli", "ble"), ("alli", "al"), ("entli", "ent"),
    ("eli", "e"), ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
    ("ator", "ate"), ("alism", "al"), ("iveness", "ive"), ("fulness", "ful"),
    ("ousness", "ous"), ("aliti", "al"), ("iviti", "ive"), ("biliti", "ble"),
    ("logi", "log"),
)
_STEP3 = (
    ("icate", "ic"), ("ative", ""), ("alize", "al"), ("iciti", "ic"),
    ("ical", "ic"), ("ful", ""), ("ness", ""),
)
_STEP4 = (
    "al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement", "ment",
    "ent", "ion", "ou", "ism", "ate", "iti", "ous", "ive", "ize",
)


def _longest_first(rules):
    return tuple(sorted(rules, key=lambda r: -len(r[0])))


# Porter matches on the longest suffix in each group; ordering by length
# makes "first match" equal "longest match".
_STEP2 = _longest_first(_STEP2)
_STEP3 = _longest_first(_STEP3)


def fold(token: str) -> str:
    """Lower-case and strip diacritics, like unicode61's remove_diacritics."""
    low = token.lower()
    if low.isascii():
        return low
    return "".join(c for c in unicodedata.normalize("NFD", low)
                   if not unicodedata.combining(c))


@lru_cache(maxsize=8192)
def term(token: str) -> str:
    """The FTS5 ``porter unicode61`` index term for one token."""
    return stem(fold(token))


def stem(word: str) -> str:
    w = word
    if len(w) < _MIN_LEN or len(w) > _MAX_LEN:
        return w

    # Step 1a
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies"):
        w = w[:-2]
    elif w.endswith("ss"):
        pass
    elif w.endswith("s"):
        w = w[:-1]

    # Step 1b
    if w.endswith("eed"):
        if _measure(w[:-3]) > 0:
            w = w[:-1]
    else:
        cut = None
        if w.endswith("ed") and _has_vowel(w[:-2]):
            cut = w[:-2]
        elif w.endswith("ing") and _has_vowel(w[:-3]):
            cut = w[:-3]
        if cut is not None:
            w = cut
            if w.endswith(("at", "bl", "iz")):
                w += "e"
            elif _double_cons(w) and w[-1] not in "lsz":
                w = w[:-1]
            elif _measure(w) == 1 and _cvc(w):
                w += "e"

    # Step 1c
    if w.endswith("y") and _has_vowel(w[:-1]):
        w = w[:-1] + "i"

    # Steps 2 and 3
    w = _replace(w, _STEP2, lambda s: _measure(s) > 0)
    w = _replace(w, _STEP3, lambda s: _measure(s) > 0)

    # Step 4 (longest matching suffix decides; it is removed only if m > 1)
    for suf in sorted(_STEP4, key=len, reverse=True):
        if w.endswith(suf):
            s = w[: len(w) - len(suf)]
            if _measure(s) > 1 and (suf != "ion" or s.endswith(("s", "t"))):
                w = s
            break

    # Step 5a
    if w.endswith("e"):
        s = w[:-1]
        m = _measure(s)
        if m > 1 or (m == 1 and not _cvc(s)):
            w = s

    # Step 5b
    if _measure(w) > 1 and _double_cons(w) and w.endswith("l"):
        w = w[:-1]
    return w
