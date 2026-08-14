"""Group-level nested CV splits -- the leakage firewall.

Ported verbatim in logic from the research pipeline's `models/splits.py`, with
`subject_id` generalised to `group_id`.

The rule is unchanged: every fold splits on the GROUP, never on the row. In the
research pipeline a group was one patient contributing several repeat-tracked
connectomes. In CogniSense a group is one **user contributing one row per day**,
which makes this firewall considerably more load-bearing here than it was
there -- a user with 90 check-ins contributes 90 rows, and splitting those
rows at random would put Tuesday in train and Wednesday in test for the same
person. The model would then be scored on its ability to recognise a familiar
individual, not to detect cognitive change, and the reported accuracy would be
a fiction.

`group_ids` must be parallel to the rows of X.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold


@dataclass
class OuterFold:
    fold_idx: int
    train_idx: np.ndarray
    test_idx: np.ndarray
    inner_cv: object  # sklearn CV object that also respects grouping


def grouped_nested_splits(
    group_ids: np.ndarray,
    y: np.ndarray | None = None,
    outer_folds: int = 5,
    inner_folds: int = 3,
    stratify: bool = True,
    random_state: int = 42,
) -> Iterator[OuterFold]:
    """Yield outer folds; each carries an inner CV that also respects groups."""
    group_ids = np.asarray(group_ids)
    if y is not None and np.asarray(y).shape[0] != group_ids.shape[0]:
        raise ValueError("y and group_ids length mismatch")

    n_groups = len(set(group_ids.tolist()))
    if n_groups < outer_folds:
        raise ValueError(
            f"cannot make {outer_folds} outer folds from {n_groups} groups; "
            f"lower outer_folds or collect more users"
        )

    if stratify and y is not None:
        outer = StratifiedGroupKFold(
            n_splits=outer_folds, shuffle=True, random_state=random_state
        )
        outer_iter = outer.split(np.zeros_like(group_ids), y, groups=group_ids)
    else:
        outer = GroupKFold(n_splits=outer_folds)
        outer_iter = outer.split(np.zeros_like(group_ids), groups=group_ids)

    for fold_idx, (train_idx, test_idx) in enumerate(outer_iter):
        # Sanity: no group on both sides. A hit here is a bug above, not data.
        train_g = set(group_ids[train_idx].tolist())
        test_g = set(group_ids[test_idx].tolist())
        if train_g & test_g:
            raise RuntimeError(
                f"group leak in outer fold {fold_idx}: "
                f"{len(train_g & test_g)} groups on both sides"
            )

        if stratify and y is not None:
            inner = StratifiedGroupKFold(
                n_splits=inner_folds, shuffle=True,
                random_state=random_state + fold_idx,
            )
        else:
            inner = GroupKFold(n_splits=inner_folds)

        yield OuterFold(
            fold_idx=fold_idx,
            train_idx=train_idx,
            test_idx=test_idx,
            inner_cv=inner,
        )


def assert_no_leakage(group_ids: np.ndarray, train_idx, test_idx) -> None:
    """Raise if any group appears on both sides. Exposed for tests."""
    group_ids = np.asarray(group_ids)
    train_g = set(group_ids[train_idx].tolist())
    test_g = set(group_ids[test_idx].tolist())
    overlap = train_g & test_g
    if overlap:
        raise AssertionError(
            f"group leakage: {sorted(overlap)[:5]}... ({len(overlap)} total)"
        )
