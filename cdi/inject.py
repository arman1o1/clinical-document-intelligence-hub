"""Fault injection: measuring the verification layer without burning API calls.

The verification layer exists to catch fabrication. The regex baseline cannot
fabricate -- it either copies a span or fails -- so running the baseline shows
the layer doing nothing, which tells us nothing about whether it works.

Rather than assert the layer works and hope the reviewer believes it, we inject
synthetic hallucinations at a known rate and measure the catch rate directly.
The injected faults mimic the failure mode that actually matters in production:
the model returns a REAL, correctly-copied evidence quote but a value that is
subtly wrong. That is the dangerous case, because the citation looks perfect.

This gives a real number for the gate on any machine, with no API key. It is a
lower bound on usefulness, not a substitute for measuring the live model -- the
distribution of real hallucinations is not the distribution we inject here.
"""
from __future__ import annotations

import random

from .extract import ALL_FIELDS, BaselineExtractor
from .schema import VITAL_FIELDS

FAKE_NAMES = ["Jonathan Fairweather", "Amrita Deshmukh", "Gregory Nunes", "Helen Ashworth"]
FAKE_DX = ["Pulmonary Embolism", "Acute Pancreatitis", "Septic Arthritis"]
FAKE_DRUGS = ["Clopidogrel", "Prednisolone", "Digoxin"]
FAKE_ALLERGENS = ["Cephalosporins", "Morphine"]


class InjectingExtractor(BaselineExtractor):
    """Baseline extractor that fabricates a known fraction of fields.

    Evidence quotes are left untouched, so every injected fault is a value that
    contradicts its own (genuine) citation.
    """
    name = "inject"

    def __init__(self, rate=0.25, seed=7):
        self.rate = rate
        self.rng = random.Random(seed)
        self.injected: dict[str, set[str]] = {}
        self._doc = None

    def extract(self, doc_id, text, k=1):
        self._doc = doc_id
        self.injected.setdefault(doc_id, set())
        return super().extract(doc_id, text, k=k)

    def _corrupt(self, field, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            delta = self.rng.choice([7, 11, -9, 23, -15])
            return round(value + delta, 1) if isinstance(value, float) else int(value + delta)
        if field == "patient_name":
            return self.rng.choice(FAKE_NAMES)
        if isinstance(value, list) and value:
            pool = {"diagnoses": FAKE_DX, "medications": FAKE_DRUGS,
                    "allergies": FAKE_ALLERGENS}.get(field)
            if pool is None:
                return value
            extra = self.rng.choice(pool)
            return value + ([{"name": extra, "dose": "10 mg", "frequency": "OD"}]
                            if field == "medications" else [extra])
        if isinstance(value, str):
            return value + " (unverified addendum)"
        return value

    def raw(self, text, sample_idx: int = 0):
        out = super().raw(text, sample_idx)
        for f in ALL_FIELDS:
            cell = out.get(f) or {}
            if cell.get("value") in (None, [], "") or self.rng.random() >= self.rate:
                continue
            corrupted = self._corrupt(f, cell["value"])
            if corrupted != cell["value"]:
                cell["value"] = corrupted          # evidence quote deliberately left intact
                out[f] = cell
                self.injected[self._doc].add(f)
        return out


def measure(rate=0.25, seed=7, limit=None):
    """Return catch-rate stats for injected fabrications."""
    import json
    from pathlib import Path
    from .schema import FieldStatus

    root = Path(__file__).resolve().parent.parent
    rows = json.loads((root / "data" / "gold" / "gold_labels.json").read_text())
    if limit:
        rows = rows[:limit]

    ex = InjectingExtractor(rate=rate, seed=seed)
    caught = injected = clean_total = clean_blocked = 0

    for row in rows:
        text = (root / "data" / "documents" / f"{row['doc_id']}.txt").read_text(encoding="utf-8")
        rec = ex.extract(row["doc_id"], text)
        bad = ex.injected[row["doc_id"]]
        for f in ALL_FIELDS:
            fld = rec.field(f)
            if fld.value in (None, [], ""):
                continue
            blocked = fld.status in (FieldStatus.UNGROUNDED, FieldStatus.ABSTAINED)
            if f in bad:
                injected += 1
                caught += blocked
            else:
                clean_total += 1
                clean_blocked += blocked

    return {
        "injection_rate": rate,
        "faults_injected": injected,
        "faults_caught": caught,
        "catch_rate": round(caught / injected, 4) if injected else 0.0,
        "clean_fields": clean_total,
        "clean_fields_blocked": clean_blocked,
        "false_block_rate": round(clean_blocked / clean_total, 4) if clean_total else 0.0,
    }


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(measure(), indent=2))
