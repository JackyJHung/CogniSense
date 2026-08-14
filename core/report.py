"""Contract-enforcing report renderer: Markdown page + flat-key JSON sidecar.

Ported from the research pipeline's `report/render.py`, with the field list
un-hardcoded. The original pinned ~50 dMRI-specific fields into a `RunReport`
dataclass (`idh_auc`, `tract_median_streamlines`, ...). Here the template
declares the contract and the caller satisfies it, so the same renderer serves
both a model-validation report and a per-user trend report.

What is kept, because it is the whole point:

  - A placeholder in the template with no matching field raises. Reports drift
    silently otherwise, and a report that quietly renders a blank where a
    number should be is worse than no report.
  - MetricCI fields render through `.render()`, so a value always arrives with
    its interval attached and nobody has to remember to format it.
  - `None` renders as "n/a" rather than "None".
  - The JSON sidecar mirrors the Markdown with flat keys, for diffing runs.
"""
from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.stats import NA, MetricCI

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def template_placeholders(template: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(template))


def _to_markdown(value: Any) -> str:
    if value is None:
        return NA
    if isinstance(value, MetricCI):
        return value.render()
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _to_json(value: Any) -> Any:
    if isinstance(value, MetricCI):
        return value.to_dict()
    return value


def render_report(
    template_path: str | Path,
    fields: Mapping[str, Any],
    out_dir: str | Path,
    run_id: str | None = None,
    extras: Mapping[str, Any] | None = None,
    filename_stem: str = "report",
) -> tuple[Path, Path]:
    """Render `template_path` with `fields`; write .md and .json to `out_dir`.

    Raises RuntimeError if the template references a field that `fields` does
    not provide -- the contract check. Returns (md_path, json_path).
    """
    template_path = Path(template_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    template = template_path.read_text(encoding="utf-8")
    expected = template_placeholders(template)
    missing = expected - set(fields.keys())
    if missing:
        raise RuntimeError(
            f"{template_path.name} references fields not supplied by the caller: "
            f"{sorted(missing)}"
        )

    run_id = run_id or str(fields.get("run_id") or make_run_id())

    md_fields = {k: _to_markdown(v) for k, v in fields.items()}
    md = string.Formatter().vformat(template, args=(), kwargs=md_fields)

    payload: dict[str, Any] = {k: _to_json(v) for k, v in fields.items()}
    if extras:
        payload["extras"] = dict(extras)

    md_path = out_dir / f"{filename_stem}_{run_id}.md"
    json_path = out_dir / f"results_{run_id}.json"

    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return md_path, json_path
