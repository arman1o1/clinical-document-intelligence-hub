#!/usr/bin/env python3
"""Produce the consolidated evaluation report.

    python run_eval.py                 # baseline arm + fault injection, no API key needed
    python run_eval.py --arm anthropic # adds the LLM arm (needs ANTHROPIC_API_KEY)
    python run_eval.py --arm anthropic --k 3   # with self-consistency
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from cdi.evaluate import run, to_markdown
from cdi.inject import measure
from cdi.ingest_eval import run as run_ingest
from cdi.ingest_eval import to_markdown as ingest_markdown

OUT = Path(__file__).parent / "outputs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="baseline", choices=["baseline", "anthropic", "both"])
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    arms = ["baseline", "anthropic"] if a.arm == "both" else [a.arm]
    results = {}
    for arm in arms:
        _, res = run(arm, a.k if arm == "anthropic" else 1, a.limit)
        results[arm] = res
        (OUT / f"eval_{arm}.json").write_text(json.dumps(res, indent=2))
        (OUT / f"eval_{arm}.md").write_text(to_markdown(arm, res))

    inj = measure(limit=a.limit)
    (OUT / "eval_injection.json").write_text(json.dumps(inj, indent=2))

    L = ["# Evaluation report - Clinical Document Intelligence Hub", "",
         f"Generated {date.today().isoformat()}. Corpus: 32 synthetic clinical documents "
         "(17 structured forms, 15 free-prose narratives) with exact gold labels.", "",
         "## 1. Extraction quality", "",
         "| Arm | Silent error rate | Precision of surfaced fields | Abstention | Fields surfaced | Present fields missed |",
         "|---|---|---|---|---|---|"]
    for arm, res in results.items():
        g = res["gated"]
        L.append(f"| `{arm}` | {g['silent_error_rate']:.1%} | {g['surfaced_precision']:.1%} | "
                 f"{g['abstention_rate']:.1%} | {g['fields_surfaced']} | {g['missed_present_fields']} |")
    L += ["",
          "*Silent error rate* = of the fields the system actually showed a human, the fraction "
          "that were wrong. This is the headline rather than plain accuracy because a withheld "
          "field costs a reviewer thirty seconds while a confidently wrong field can propagate "
          "into a care decision.", "",
          "## 2. Verification layer - fault injection", "",
          "The regex baseline cannot fabricate, so running it shows the verification layer doing "
          "nothing. To measure the layer directly we inject synthetic hallucinations at a known "
          "rate: a genuine, correctly-copied evidence quote paired with a subtly wrong value - "
          "the failure mode that matters, because the citation looks perfect.", "",
          "| Metric | Value |", "|---|---|",
          f"| Faults injected | {inj['faults_injected']} |",
          f"| Faults caught (withheld from the summary card) | {inj['faults_caught']} |",
          f"| **Catch rate** | **{inj['catch_rate']:.1%}** |",
          f"| Clean fields incorrectly blocked | {inj['clean_fields_blocked']} / {inj['clean_fields']} |",
          f"| **False block rate** | **{inj['false_block_rate']:.1%}** |", "",
          "Residual misses are numeric corruptions whose perturbed value coincides with another "
          "number elsewhere in the same document. Numerics are deliberately not hard-gated on "
          "value presence, because legitimate unit conversion (37.6 C -> 99.7 F) produces a "
          "correct value that never appears literally in the text.", ""]
    try:
        ing_rows = run_ingest()
        L += ["## 3. " + ingest_markdown(ing_rows).lstrip("#").lstrip().replace(
            "Ingestion fidelity", "Ingestion fidelity", 1)]
    except Exception as exc:                       # noqa: BLE001
        ing_rows = []
        L += ["## 3. Ingestion fidelity", "", f"Not run: `{type(exc).__name__}: {exc}`", ""]

    for arm, res in results.items():
        L += [f"## 4. Per-field detail - `{arm}`", "", to_markdown(arm, res).split("## Per-field")[1]
              .replace("(verification ON)", "(verification ON)", 1)]
    (OUT / "EVALUATION.md").write_text("\n".join(L))

    print(f"\nwrote outputs/EVALUATION.md")
    for arm, res in results.items():
        g = res["gated"]
        print(f"  [{arm}] silent error {g['silent_error_rate']:.1%} | "
              f"abstention {g['abstention_rate']:.1%} | surfaced {g['fields_surfaced']}")
    print(f"  [injection] catch rate {inj['catch_rate']:.1%} | "
          f"false blocks {inj['false_block_rate']:.1%}")


if __name__ == "__main__":
    main()
