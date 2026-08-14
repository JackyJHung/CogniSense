"""Pure-text feature helpers, shared by the behavioral model and the memory aid.

Extracted from `behavioral_model.py` so the prospective-memory matcher can reuse
exactly the same token logic instead of growing a second, subtly different copy.
It also keeps these helpers importable without pulling in torch, which matters
because the reminder flow does text matching on every check and has no reason to
load a 400 MB dependency to do it.

`behavioral_model` re-exports both functions, so existing imports keep working.

NOTE ON THE TWO TOKENISERS. `lexical_diversity` and `activity_overlap` split
text differently -- the first keeps every token as-is, the second strips
trailing punctuation and drops tokens of 2 characters or fewer. That difference
predates this refactor and feeds the trained behavioral checkpoint, so it is
preserved verbatim rather than tidied; changing it would silently move every
daily score.
"""
from __future__ import annotations

# Common words that carry no recall evidence. Applied only where a caller opts
# in via `stopwords=`, so the behavioral model's scoring is untouched.
RECALL_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "have", "has", "had",
    "was", "were", "are", "get", "got", "put", "some", "any", "all",
    "you", "your", "our", "their", "his", "her", "its",
    "from", "into", "out", "off", "then", "than", "but", "not",
    "need", "needs", "want", "wants", "going", "gonna", "today",
    "tomorrow", "later", "thing", "things", "stuff", "about",
})


def lexical_diversity(text: str) -> float:
    """Type/token ratio. A naive proxy for linguistic richness."""
    if not text.strip():
        return 0.0
    tokens = [t.lower() for t in text.split() if t.strip()]
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def content_tokens(text: str, stopwords: frozenset[str] | None = None) -> set[str]:
    """Lowercased tokens longer than two characters, trailing punctuation removed.

    This is the tokeniser `activity_overlap` has always used, lifted out so the
    reminder matcher can share it. The stripped punctuation set is deliberately
    the original ".,!?" and not a wider one: widening it would quietly shift
    every stored `activity_recall_accuracy`, and this function is on the path
    that feeds the trained behavioral checkpoint. Widen it only as a considered
    change, with the scoring impact understood.

    The one deviation is `discard("")`: a token like "..." strips to the empty
    string, and the original left that in the set, where it could only ever
    manufacture a spurious match. Removing it cannot lower a genuine score.
    """
    tokens = {t.lower().strip(".,!?") for t in text.split() if len(t) > 2}
    tokens.discard("")
    if stopwords:
        tokens -= stopwords
    return tokens


def activity_overlap(
    planned: str, recalled: str, stopwords: frozenset[str] | None = None,
) -> float:
    """Fraction of `planned`'s tokens that appear in `recalled`.

    Very rough; a real implementation would use lemma matching or embedding
    similarity.

    `stopwords` defaults to None, which reproduces the original behaviour
    exactly for the evening check-in. The reminder matcher passes
    RECALL_STOPWORDS, because there "call the dentist" vs "call the doctor"
    would otherwise score 0.67 on the strength of "call" and "the" alone.
    """
    planned_tokens = content_tokens(planned, stopwords)
    recalled_tokens = content_tokens(recalled, stopwords)
    if not planned_tokens:
        return 0.0
    return len(planned_tokens & recalled_tokens) / len(planned_tokens)
