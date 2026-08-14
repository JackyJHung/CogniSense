"""Global seed control.

Ported from the research pipeline's `reproducibility/seeding.py`. This REPLACES
the two-line `set_seed()` that lived in `backend/app/ml/train_models.py`, which
seeded numpy and torch but left `random` and `PYTHONHASHSEED` untouched. That
mattered: the check-in flow picks the five daily image associations with
`random.sample()`, so the stdlib RNG is part of what a user actually
experiences and part of what any replay of a training run has to reproduce.

What this does NOT make deterministic:
  - GPU BLAS / cuDNN reductions. Making those deterministic costs real speed
    (torch.use_deterministic_algorithms(True) plus CUBLAS_WORKSPACE_CONFIG).
    We accept the variance and quantify it instead -- see core.stats.
  - Thread scheduling in DataLoader workers with num_workers > 0.
"""
from __future__ import annotations

import logging
import os
import random

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_SEED = 42


def set_global_seed(seed: int = DEFAULT_SEED) -> int:
    """Seed every RNG the app touches. Returns the seed, for logging."""
    if seed is None:
        raise ValueError("seed must be an int, not None")

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)

    # torch is a hard dependency of the backend, but keep this import soft so
    # core.* stays usable from tooling that does not want to pay torch's
    # import cost.
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        logger.debug("torch not importable; skipping torch seeding")

    # sklearn takes random_state per estimator; core.pipelines threads it
    # through. Nothing to set globally.

    logger.info("global seed set to %d", seed)
    return seed
