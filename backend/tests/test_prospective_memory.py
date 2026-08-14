"""Prospective-memory checks: the gate, the matcher, and the aid guarantee.

The single most important test in this file is
`test_the_list_is_shown_even_when_nothing_was_recalled`. Everything else is
accuracy; that one is safety.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.memory.prospective import (
    MEMORY_AID_DISCLAIMER,
    feedback_message,
    match_recall,
    prospective_memory_summary,
    prospective_trajectory,
    should_show_aid,
)


@dataclass
class FakeItem:
    """Stands in for ReminderItem without needing a database."""

    id: int
    text: str

    @property
    def match_text(self) -> str:
        return self.text


DENTIST = FakeItem(1, "call the dentist about the crown")
BINS = FakeItem(2, "put the bins out")
PILLS = FakeItem(3, "pick up my blood pressure pills")
LIST = [DENTIST, BINS, PILLS]


# --------------------------------------------------------------------------
# The aid guarantee
# --------------------------------------------------------------------------

def test_the_list_is_shown_even_when_nothing_was_recalled():
    """A failed attempt must never withhold the user's own reminders.

    Withholding would punish precisely the impairment the feature exists to
    support. If this test is ever changed to allow withholding, the feature has
    stopped being a memory aid.
    """
    result = match_recall("I honestly can't remember any of it", LIST)

    assert result.passed is False
    assert result.n_recalled == 0
    assert result.show_aid is True, "the list must be revealed after a failed attempt"


def test_the_list_is_shown_on_success_too():
    result = match_recall("the dentist", LIST)
    assert result.passed is True
    assert result.show_aid is True


def test_should_show_aid_is_unconditional():
    assert should_show_aid(passed=True) is True
    assert should_show_aid(passed=False) is True


def test_feedback_never_scolds_on_a_blank():
    result = match_recall("no idea", LIST)
    message = feedback_message(result)
    assert "here's your list" in message.lower()
    for word in ("fail", "wrong", "poor", "bad", "worse"):
        assert word not in message.lower(), f"feedback should not say {word!r}"


# --------------------------------------------------------------------------
# The gate: at least one item, named unprompted
# --------------------------------------------------------------------------

def test_naming_one_item_passes_the_gate():
    result = match_recall("I was supposed to put the bins out", LIST)
    assert result.passed is True
    assert result.n_recalled == 1
    assert result.matched_item_ids == [BINS.id]
    assert result.prospective_score == round(1 / 3, 3)


def test_naming_everything_scores_one():
    result = match_recall(
        "call the dentist about the crown, put the bins out, "
        "and pick up my blood pressure pills",
        LIST,
    )
    assert result.n_recalled == 3
    assert result.prospective_score == 1.0
    assert result.passed is True


def test_empty_recall_recalls_nothing():
    result = match_recall("", LIST)
    assert result.n_recalled == 0
    assert result.passed is False
    assert result.show_aid is True


def test_no_active_items_means_no_check():
    result = match_recall("anything", [])
    assert result.n_active == 0
    assert result.passed is False
    assert result.show_aid is False


# --------------------------------------------------------------------------
# Matching accuracy
# --------------------------------------------------------------------------

def test_a_distinctive_word_recalls_a_long_item():
    """Detail in a description must not make an item harder to recall.

    "call the dentist about the crown" has several content words; someone who
    says "the dentist" has plainly remembered it and must not be scored as
    having forgotten.
    """
    result = match_recall("the dentist", LIST)
    assert DENTIST.id in result.matched_item_ids


def test_a_shared_word_resolves_neither_item():
    """'call' cannot identify which call, when two items are calls."""
    items = [FakeItem(1, "call the dentist"), FakeItem(2, "call the plumber")]
    result = match_recall("I had to call someone", items)
    assert result.n_recalled == 0, "a word common to both items must not match either"

    # But the distinctive half resolves it cleanly.
    result2 = match_recall("call the plumber", items)
    assert result2.matched_item_ids == [2]


def test_stopwords_alone_match_nothing():
    result = match_recall("the and that thing", LIST)
    assert result.n_recalled == 0


def test_similar_but_different_items_do_not_cross_match():
    result = match_recall("pick up my pills", LIST)
    assert PILLS.id in result.matched_item_ids
    assert DENTIST.id not in result.matched_item_ids
    assert BINS.id not in result.matched_item_ids


def test_an_item_made_only_of_stopwords_is_still_matchable():
    """A vaguely-worded item must not be impossible to recall by construction."""
    vague = [FakeItem(9, "get the thing")]
    result = match_recall("get the thing", vague)
    assert result.n_recalled == 1


# --------------------------------------------------------------------------
# Scoring carries uncertainty, like everything else
# --------------------------------------------------------------------------

def test_summary_carries_an_interval():
    scores = [0.66, 0.5, 0.75, 0.6, 0.7, 0.5, 0.8, 0.65]
    m = prospective_memory_summary(scores)
    assert m.is_estimable
    assert m.ci_low <= m.value <= m.ci_high


def test_summary_refuses_an_interval_on_one_check():
    m = prospective_memory_summary([0.5])
    assert m.value == 0.5
    assert m.ci_low is None


def test_trajectory_flags_a_real_decline_but_not_a_noisy_one():
    steady = [0.9, 0.85, 0.95, 0.9, 0.88, 0.92, 0.9, 0.87]
    dropped = [0.3, 0.25, 0.35, 0.3, 0.28, 0.32, 0.3, 0.27]
    real = prospective_trajectory(steady, dropped)
    assert real.value < 0 and real.excludes(0.0)

    rng = np.random.default_rng(0)
    noisy_before = list(rng.uniform(0.2, 0.9, size=6))
    noisy_after = list(rng.uniform(0.15, 0.85, size=6))
    noisy = prospective_trajectory(noisy_before, noisy_after)
    assert not noisy.excludes(0.0)


def test_disclaimer_says_it_is_not_a_fix():
    text = MEMORY_AID_DISCLAIMER.lower()
    assert "not a treatment" in text
    assert "cannot fix" in text
    assert "not a diagnosis" in text
