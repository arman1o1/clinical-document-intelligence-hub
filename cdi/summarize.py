"""Console renderer for a single document. Also the demo fallback if the UI misbehaves.

    python -m cdi.summarize data/demo/DEMO_discharge_summary.txt
    python -m cdi.summarize data/demo/DEMO_discharge_summary.pdf
    python -m cdi.summarize data/demo/DEMO_discharge_summary_scan.png
    python -m cdi.summarize data/documents/DOC018.txt --arm anthropic
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .extract import get_extractor
from .ingest import load_document
from .reason import Severity, evaluate, next_step
from .schema import FieldStatus

BAR = "=" * 74
SEV_TAG = {Severity.CRITICAL: "CRITICAL", Severity.HIGH: "HIGH    ",
           Severity.MODERATE: "MODERATE", Severity.INFO: "INFO    "}


def cell(rec, name, unit=""):
    f = rec.field(name)
    if f.status is FieldStatus.EXTRACTED:
        v = int(f.value) if isinstance(f.value, float) and f.value.is_integer() else f.value
        return f"{v}{unit}  [{f.confidence:.2f}]"
    if f.status in (FieldStatus.ABSTAINED, FieldStatus.UNGROUNDED):
        return f"** WITHHELD - needs review ({f.status.value}) **"
    return "not documented"


def render(rec, flags, urgency, queue) -> str:
    L = [BAR, "  CLINICAL DOCUMENT INTELLIGENCE HUB - PATIENT SUMMARY CARD", BAR,
         f"  Document   : {rec.doc_id}  ({rec.document_type.value.replace('_', ' ')})",
         f"  Routed to  : {queue.value}",
         f"  Urgency    : {urgency}/100", "",
         "-" * 74, "  PATIENT", "-" * 74,
         f"  Name            : {cell(rec, 'patient_name')}",
         f"  Age / Sex       : {cell(rec, 'age')} / {cell(rec, 'sex')}",
         f"  MRN             : {cell(rec, 'mrn')}",
         f"  Encounter date  : {cell(rec, 'encounter_date')}",
         f"  Chief complaint : {cell(rec, 'chief_complaint')}", "",
         "-" * 74, "  VITALS", "-" * 74,
         f"  Blood pressure  : {cell(rec, 'bp_systolic')} / {cell(rec, 'bp_diastolic')} mmHg",
         f"  Heart rate      : {cell(rec, 'heart_rate', ' bpm')}",
         f"  Temperature     : {cell(rec, 'temp_f', ' F')}",
         f"  SpO2            : {cell(rec, 'spo2', ' %')}", ""]

    for title, key in [("DIAGNOSES", "diagnoses"), ("ALLERGIES", "allergies")]:
        f = rec.field(key)
        L += ["-" * 74, f"  {title}", "-" * 74]
        if f.status is FieldStatus.EXTRACTED:
            L += [f"    - {d}" for d in f.value] or ["    (none documented)"]
        else:
            L.append(f"    ** {f.display()} **")
        if f.dropped_items:
            L.append(f"    ! {f.dropped_items} entry(s) removed - unsupported by the document")
        L.append("")

    f = rec.field("medications")
    L += ["-" * 74, "  MEDICATIONS", "-" * 74]
    if f.status is FieldStatus.EXTRACTED and f.value:
        L += [f"    - {m.get('name','?'):<22}{m.get('dose') or '':<10}{m.get('frequency') or ''}"
              for m in f.value]
    else:
        L.append(f"    {f.display()}")
    L.append("")

    f = rec.field("labs")
    L += ["-" * 74, "  LABORATORY RESULTS", "-" * 74]
    if f.status is FieldStatus.EXTRACTED and f.value:
        L += [f"    - {l.get('name','?'):<24}{l.get('value')} {l.get('unit') or ''}"
              for l in f.value]
    else:
        L.append(f"    {f.display()}")
    L.append("")

    L += ["-" * 74, f"  RISK FLAGS ({len(flags)})", "-" * 74]
    if not flags:
        L.append("    No rules triggered.")
    for fl in flags:
        L.append(f"    [{SEV_TAG[fl.severity]}] {fl.message}")
        L.append(f"                 rule {fl.rule_id}  |  {fl.basis}")
    L.append("")

    gaps = rec.review_queue()
    L += ["-" * 74, f"  HUMAN REVIEW QUEUE ({len(gaps)})", "-" * 74]
    L.append("    " + (", ".join(gaps) if gaps else "Every field cleared verification."))
    L += ["", "-" * 74, "  RECOMMENDED NEXT STEP", "-" * 74,
          "    " + next_step(queue, flags), BAR,
          "  [n.nn] = computed confidence. Withheld fields are never shown as values.", BAR]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--arm", default="baseline", choices=["baseline", "anthropic"])
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--json", action="store_true", help="also print the structured record")
    a = ap.parse_args()

    p = Path(a.path)
    ing = load_document(p)
    rec = get_extractor(a.arm).extract(p.stem, ing.text, k=a.k)
    flags, urgency, queue = evaluate(rec)
    print(render(rec, flags, urgency, queue))
    if ing.source_kind != "text" or ing.notes:
        print(f"  Ingested as: {ing.source_kind}"
              + (f" ({ing.pages} page(s))" if ing.pages > 1 else ""))
        for n in ing.notes:
            print(f"  ! {n}")
        if ing.degraded:
            print("  ! Confidence scores below are measured against the OCR transcription,")
            print("    not the original document.")
        print(BAR)
    if a.json:
        print("\n--- STRUCTURED RECORD ---")
        print(rec.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
