"""Evaluation harness.

Plain accuracy is the wrong headline metric for this system. A field the
pipeline withholds costs a reviewer thirty seconds; a field it gets wrong and
presents confidently can propagate into a care decision. Those are not the same
error and should not be averaged together.

So the headline is SILENT ERROR RATE -- of the fields the system actually put in
front of a human, what fraction were wrong. Abstentions are excluded from the
numerator and tracked separately as the price paid.

We report each arm twice: gated (verification layer on, the shipped behaviour)
and ungated (every non-null prediction surfaced, i.e. what you get without the
verification layer). The delta is the measured value of the verification layer.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from .extract import get_extractor
from .schema import (LIST_FIELDS, SCALAR_FIELDS, VITAL_FIELDS, FieldStatus,
                     PatientRecord)

ROOT = Path(__file__).resolve().parent.parent
DOC_DIR, GOLD = ROOT / "data" / "documents", ROOT / "data" / "gold" / "gold_labels.json"
OUT = ROOT / "outputs"

FUZZY_FIELDS = {"chief_complaint", "smoking_status", "discharge_disposition"}
SURFACED = {FieldStatus.EXTRACTED}
WITHHELD = {FieldStatus.ABSTAINED, FieldStatus.UNGROUNDED}


def _n(x):
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(x).lower()).strip()


def scalar_match(field, pred, gold) -> bool:
    if pred is None or gold is None:
        return pred is None and gold is None
    if field == "temp_f":
        try:
            return abs(float(pred) - float(gold)) <= 0.25
        except (TypeError, ValueError):
            return False
    if isinstance(gold, (int, float)) and not isinstance(gold, bool):
        try:
            return abs(float(pred) - float(gold)) < 1e-6
        except (TypeError, ValueError):
            return False
    if field == "mrn":
        import re as _re
        dp, dg = _re.sub(r"\D", "", str(pred)), _re.sub(r"\D", "", str(gold))
        return bool(dg) and dp == dg
    if field in FUZZY_FIELDS:
        return SequenceMatcher(None, _n(pred), _n(gold)).ratio() >= 0.85
    return _n(pred) == _n(gold)


def _keys(field, items):
    out = set()
    for it in items or []:
        if field == "medications":
            out.add(_n(it.get("name") if isinstance(it, dict) else it))
        elif field == "labs":
            if isinstance(it, dict):
                v = it.get("value")
                out.add((_n(it.get("name")), round(float(v), 2) if v is not None else None))
        else:
            out.add(_n(it))
    return out


def list_prf(field, pred, gold):
    p, g = _keys(field, pred), _keys(field, gold)
    if not p and not g:
        return 1.0, 1.0, 1.0, 0, 0
    tp = len(p & g)
    prec = tp / len(p) if p else (1.0 if not g else 0.0)
    rec = tp / len(g) if g else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return prec, rec, f1, len(p - g), len(g - p)


def gold_of(gold_row, field):
    if field in VITAL_FIELDS:
        return (gold_row.get("vitals") or {}).get(field)
    return gold_row.get(field)


def score(records: dict[str, PatientRecord], gold_rows: list[dict], gated=True) -> dict:
    per = defaultdict(lambda: dict(surfaced=0, correct=0, wrong=0, withheld=0,
                                   missed=0, correct_absent=0, spurious=0))
    lp = defaultdict(lambda: dict(p=[], r=[], f=[], fp=0, fn=0))
    doc_ok = 0

    for row in gold_rows:
        rec = records.get(row["doc_id"])
        if rec is None:
            continue
        doc_ok += int(rec.document_type.value == row["document_type"])

        for f in SCALAR_FIELDS + VITAL_FIELDS:
            fld, gv, s = rec.field(f), gold_of(row, f), per[f]
            withheld = fld.status in WITHHELD
            visible = (fld.status in SURFACED) if gated else (fld.value is not None)
            if withheld and gated:
                s["withheld"] += 1
                if gv is None:
                    s["correct_absent"] += 1   # withholding an absent field is fine
                else:
                    s["missed"] += 1
                continue
            if not visible:
                if gv is None:
                    s["correct_absent"] += 1
                else:
                    s["missed"] += 1
                continue
            s["surfaced"] += 1
            if gv is None:
                s["spurious"] += 1
                s["wrong"] += 1          # inventing a value for an absent field
            elif scalar_match(f, fld.value, gv):
                s["correct"] += 1
            else:
                s["wrong"] += 1

        for f in LIST_FIELDS:
            fld, gv = rec.field(f), gold_of(row, f) or []
            if fld.status in WITHHELD and gated:
                per[f]["withheld"] += 1
                continue
            pv = fld.value if (fld.value is not None) else []
            p, r, f1, fp, fn = list_prf(f, pv, gv)
            lp[f]["p"].append(p); lp[f]["r"].append(r); lp[f]["f"].append(f1)
            lp[f]["fp"] += fp; lp[f]["fn"] += fn
            per[f]["surfaced"] += 1
            if f1 >= 0.999:
                per[f]["correct"] += 1
            else:
                per[f]["wrong"] += 1

    tot_surf = sum(v["surfaced"] for v in per.values())
    tot_wrong = sum(v["wrong"] for v in per.values())
    tot_with = sum(v["withheld"] for v in per.values())
    tot_missed = sum(v["missed"] for v in per.values())
    denom = tot_surf + tot_with

    return {
        "n_documents": len(gold_rows),
        "doc_type_accuracy": round(doc_ok / max(1, len(gold_rows)), 4),
        "fields_surfaced": tot_surf,
        "fields_withheld": tot_with,
        "silent_error_rate": round(tot_wrong / tot_surf, 4) if tot_surf else 0.0,
        "surfaced_precision": round(1 - tot_wrong / tot_surf, 4) if tot_surf else 0.0,
        "abstention_rate": round(tot_with / denom, 4) if denom else 0.0,
        "missed_present_fields": tot_missed,
        "per_field": {k: dict(v) for k, v in sorted(per.items())},
        "list_prf": {k: {"precision": round(sum(v["p"]) / len(v["p"]), 4),
                         "recall": round(sum(v["r"]) / len(v["r"]), 4),
                         "f1": round(sum(v["f"]) / len(v["f"]), 4),
                         "false_positives": v["fp"], "false_negatives": v["fn"]}
                     for k, v in sorted(lp.items()) if v["p"]},
    }


def run(arm="baseline", k=1, limit=None):
    gold_rows = json.loads(GOLD.read_text())
    if limit:
        gold_rows = gold_rows[:limit]
    ex = get_extractor(arm)
    records = {}
    for row in gold_rows:
        text = (DOC_DIR / f"{row['doc_id']}.txt").read_text(encoding="utf-8")
        records[row["doc_id"]] = ex.extract(row["doc_id"], text, k=k)
    return records, {"gated": score(records, gold_rows, True),
                     "ungated": score(records, gold_rows, False)}


def to_markdown(arm, res) -> str:
    g, u = res["gated"], res["ungated"]
    L = [f"# Extraction evaluation - `{arm}` arm", "",
         f"Corpus: {g['n_documents']} synthetic clinical documents with exact gold labels.",
         "", "## Headline", "",
         "| Metric | Verification ON (shipped) | Verification OFF |",
         "|---|---|---|",
         f"| Silent error rate (wrong values shown to a human) | **{g['silent_error_rate']:.1%}** | {u['silent_error_rate']:.1%} |",
         f"| Precision of surfaced fields | **{g['surfaced_precision']:.1%}** | {u['surfaced_precision']:.1%} |",
         f"| Abstention rate (routed to human) | {g['abstention_rate']:.1%} | 0.0% |",
         f"| Fields surfaced | {g['fields_surfaced']} | {u['fields_surfaced']} |",
         f"| Document-type accuracy | {g['doc_type_accuracy']:.1%} | - |", "",
         "## Per-field (verification ON)", "",
         "| Field | Surfaced | Correct | Wrong | Withheld | Accuracy on surfaced |",
         "|---|---|---|---|---|---|"]
    for f, s in g["per_field"].items():
        acc = f"{s['correct']/s['surfaced']:.1%}" if s["surfaced"] else "-"
        L.append(f"| `{f}` | {s['surfaced']} | {s['correct']} | {s['wrong']} | {s['withheld']} | {acc} |")
    if g["list_prf"]:
        L += ["", "## Multi-value fields (micro P/R/F1)", "",
              "| Field | Precision | Recall | F1 | FP | FN |", "|---|---|---|---|---|---|"]
        for f, s in g["list_prf"].items():
            L.append(f"| `{f}` | {s['precision']:.3f} | {s['recall']:.3f} | {s['f1']:.3f} | "
                     f"{s['false_positives']} | {s['false_negatives']} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="baseline", choices=["baseline", "anthropic"])
    ap.add_argument("--k", type=int, default=1, help="samples per document for self-consistency")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    _, res = run(a.arm, a.k, a.limit)
    OUT.mkdir(exist_ok=True)
    (OUT / f"eval_{a.arm}.json").write_text(json.dumps(res, indent=2))
    (OUT / f"eval_{a.arm}.md").write_text(to_markdown(a.arm, res))
    g = res["gated"]
    print(f"[{a.arm}] silent error {g['silent_error_rate']:.1%} | "
          f"abstention {g['abstention_rate']:.1%} | surfaced {g['fields_surfaced']}")
    print(f"wrote outputs/eval_{a.arm}.json and .md")


if __name__ == "__main__":
    main()
