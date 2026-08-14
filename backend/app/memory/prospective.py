"""Prospective-memory checks: grading a free recall against the user's own list.

THE ONE RULE THAT MATTERS HERE
------------------------------
The list is ALWAYS shown after the attempt, whether the user recalled anything
or not. This is a memory aid that happens to measure, not a test that withholds.
Withholding somebody's own reminders because they failed to remember them would
punish exactly the impairment the feature exists to help with, and would land
hardest on the users who need it most. `SHOW_AID_ON_FAILURE` is a constant
rather than a setting for that reason -- see `should_show_aid`.

The gate ("name at least one thing") governs SCORING and the wording of the
feedback. It never governs access.

WHAT IS MEASURED
----------------
  n_recalled / n_active   fraction of outstanding intentions named unprompted
  reported done           what the user says they actually did

Those are kept separate on purpose. Forgetting that you meant to do something
is a different signal from remembering it and not getting to it; collapsing them
would blur the one thing this check is for.

MATCHING IS DELIBERATELY LENIENT
--------------------------------
Recall is graded on content-word overlap via the same `activity_overlap` the
evening check-in uses, with stopwords removed. A user who writes "ring the
dentist" for an item saved as "call the dentist about the crown" should pass.
The failure mode we choose is a false pass, not a false fail: wrongly telling
someone they forgot something they in fact remembered is the more harmful error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, Sequence

from app.ml.text_features import RECALL_STOPWORDS, activity_overlap, content_tokens
from core.stats import MetricCI, bootstrap_delta_ci, bootstrap_stat_ci

# Fraction of an item's content words that must appear in the recall.
#
# Set above 0.5 deliberately. At exactly 0.5, a two-content-word item like
# "call the dentist" matches on the shared word "call" alone -- so with "call
# the plumber" also on the list, either item would resolve the other. Above 0.5,
# a single shared word no longer carries a match, and a single DISTINCTIVE word
# still does via rule (b) in match_recall.
MATCH_THRESHOLD = 0.6

# The list is revealed after every attempt. Not configurable; see module docstring.
SHOW_AID_ON_FAILURE = True

# Minimum checks before a prospective-memory trend is reported at all. Matches
# the retrospective side's MINIMUM_CHECKINS_FOR_WARNING.
MIN_CHECKS_FOR_TREND = 14


class HasMatchText(Protocol):
    """Anything with an id and text to match against -- ReminderItem satisfies it."""

    id: int

    @property
    def match_text(self) -> str: ...


@dataclass
class ItemMatch:
    item_id: int
    overlap: float
    matched: bool


@dataclass
class RecallResult:
    matches: list[ItemMatch] = field(default_factory=list)
    n_active: int = 0
    n_recalled: int = 0
    passed: bool = False
    prospective_score: float = 0.0
    show_aid: bool = True

    @property
    def matched_item_ids(self) -> list[int]:
        return [m.item_id for m in self.matches if m.matched]

    @property
    def unrecalled_item_ids(self) -> list[int]:
        return [m.item_id for m in self.matches if not m.matched]


def _item_tokens(item_text: str) -> set[str]:
    """Content tokens for an item, falling back to raw tokens when needed.

    An item phrased entirely in stopwords ("get the thing") has nothing left
    after filtering and would be permanently unmatchable, so those fall back to
    the unfiltered token set rather than guaranteeing a fail on the user's own
    choice of words.
    """
    tokens = content_tokens(item_text, RECALL_STOPWORDS)
    return tokens or content_tokens(item_text)


def _overlap(item_text: str, recall_text: str) -> float:
    if content_tokens(item_text, RECALL_STOPWORDS):
        return activity_overlap(item_text, recall_text, stopwords=RECALL_STOPWORDS)
    return activity_overlap(item_text, recall_text)


def match_recall(
    recall_text: str,
    items: Sequence[HasMatchText],
    threshold: float = MATCH_THRESHOLD,
) -> RecallResult:
    """Grade a free-recall attempt against the user's outstanding items.

    An item counts as recalled when EITHER:

      a) the recall covers at least `threshold` of its content words, or
      b) the recall names a word that belongs to this item and no other item on
         the list -- a distinctive word.

    Rule (b) exists because rule (a) alone penalises detail. "Call the dentist
    about the crown" has four content words, so a user who says "the dentist"
    scores 0.25 and would be marked as having forgotten it. Naming "dentist" IS
    remembering that item, and the more carefully somebody writes their list the
    worse the pure-overlap rule treats them.

    Distinctiveness is computed against the current list, so a word shared by
    two items ("call the dentist", "call the plumber") cannot resolve either on
    its own -- "call" identifies nothing, while "dentist" identifies one.
    """
    n_active = len(items)
    if n_active == 0:
        return RecallResult(n_active=0, passed=False, prospective_score=0.0, show_aid=False)

    recall_text = (recall_text or "").strip()
    recall_tokens = content_tokens(recall_text, RECALL_STOPWORDS) if recall_text else set()

    tokens_by_item = {item.id: _item_tokens(item.match_text) for item in items}
    token_frequency: dict[str, int] = {}
    for tokens in tokens_by_item.values():
        for token in tokens:
            token_frequency[token] = token_frequency.get(token, 0) + 1

    matches: list[ItemMatch] = []
    for item in items:
        overlap = _overlap(item.match_text, recall_text) if recall_text else 0.0
        distinctive = {
            t for t in tokens_by_item[item.id] if token_frequency.get(t, 0) == 1
        }
        named_distinctive = bool(distinctive & recall_tokens)
        matches.append(
            ItemMatch(
                item_id=item.id,
                overlap=round(overlap, 3),
                matched=overlap >= threshold or named_distinctive,
            )
        )

    n_recalled = sum(1 for m in matches if m.matched)
    return RecallResult(
        matches=matches,
        n_active=n_active,
        n_recalled=n_recalled,
        # The gate the user asked for: at least one item named unprompted.
        passed=n_recalled >= 1,
        prospective_score=round(n_recalled / n_active, 3),
        show_aid=should_show_aid(n_recalled >= 1),
    )


def should_show_aid(passed: bool) -> bool:
    """Whether to reveal the list. Always true -- the aid is not a reward.

    Kept as a function so the intent is greppable and any future change to it
    has to be made deliberately, in one place, against this docstring.
    """
    return True if SHOW_AID_ON_FAILURE else passed


def feedback_message(result: RecallResult) -> str:
    """Plain, non-clinical wording for the user. Never diagnostic, never scolding."""
    if result.n_active == 0:
        return "You have nothing on your list right now."

    if result.n_recalled == result.n_active:
        return (
            f"You remembered everything on your list "
            f"({result.n_recalled} of {result.n_active}). Here it is so you can "
            f"tick off what you've done."
        )
    if result.n_recalled >= 1:
        return (
            f"You remembered {result.n_recalled} of {result.n_active}. "
            f"Here's the full list -- have a look at the rest."
        )
    return (
        "No problem -- here's your list. Everyone blanks sometimes, and a single "
        "check doesn't mean anything on its own."
    )


def prospective_memory_summary(
    scores: Iterable[float], random_state: int = 42,
) -> MetricCI:
    """Mean fraction of intentions recalled unprompted, with a 95% interval."""
    return bootstrap_stat_ci(
        list(scores), name="prospective_recall", random_state=random_state
    )


def prospective_trajectory(
    baseline_scores: Sequence[float],
    recent_scores: Sequence[float],
    random_state: int = 42,
) -> MetricCI:
    """Relative change in prospective recall vs. the user's own earlier baseline.

    Same contract as the retrospective trajectory: a change is only real if the
    interval excludes zero. Callers must not act on the point estimate alone.
    """
    return bootstrap_delta_ci(
        baseline_scores, recent_scores, relative=True,
        name="prospective_change", random_state=random_state,
    )


# Shown wherever the feature's output is surfaced. The user asked for this to
# stay attached: the aid supports memory, it does not fix or prevent decline.
MEMORY_AID_DISCLAIMER = (
    "These reminders are a support, not a treatment. CogniSense can help you "
    "keep track of what you meant to do, but it cannot fix, halt, or prevent "
    "memory decline, and how you do on these checks is not a diagnosis. If "
    "you or the people around you are worried about your memory, please speak "
    "with a doctor."
)
