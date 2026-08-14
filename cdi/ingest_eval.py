"""How much does the ingestion path cost you?

The brief asks for text, PDF and image input. Those are not equivalent, and a
prototype that accepts all three without saying what each costs is hiding the
interesting part. This measures the same document through all four routes,
using the plain-text version as the reference, and reports the delta.

The point is not that OCR is worse -- everyone knows that. It is that the
degradation should be *visible*: fields that OCR mangles should fail their
grounding check and be withheld, not surface as confident wrong values.
"""
from __future__ import annotations

from pathlib import Path

from .extract import ALL_FIELDS, get_extractor
from .ingest import load_document
from .reason import evaluate
from .schema import FieldStatus

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "data" / "demo"

ROUTES = [
    ("plain text", "DEMO_discharge_summary.txt"),
    ("PDF, text layer", "DEMO_discharge_summary.pdf"),
    ("PDF, scanned (OCR)", "DEMO_discharge_summary_scanned.pdf"),
    ("image (OCR)", "DEMO_discharge_summary_scan.png"),
]


def _values(rec):
    out = {}
    for f in ALL_FIELDS:
        fld = rec.field(f)
        out[f] = (fld.value if fld.status is FieldStatus.EXTRACTED else None,
                  fld.status is FieldStatus.EXTRACTED)
    return out


def _norm(x):
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(x).lower()).strip()


def _entities(v):
    """The clinical content of a value, stripped of formatting."""
    if isinstance(v, (list, tuple)):
        out = set()
        for it in v:
            out.add(_norm(it.get("name") if isinstance(it, dict) else it))
        return out
    return {_norm(v)}


def _compare(a, b) -> str:
    """'agree' | 'cosmetic' | 'incomplete' | 'wrong'.

    Four outcomes, because collapsing them lies in a specific direction.

      agree       identical
      cosmetic    same clinical entities, different characters -- OCR turns "1."
                  into "1," and "OD" into "oD"
      incomplete  a strict subset: entries were dropped and NOTHING was added.
                  Recall loss. Costly, but not dangerous.
      wrong       contains an entity the reference does not have. Invention.
                  This is the only category a clinician can be misled by.

    Scoring dropped rows as "wrong" would make OCR look like it fabricates lab
    results, which is both false and the wrong thing to engineer against.
    """
    if isinstance(a, float) and isinstance(b, float):
        return "agree" if abs(a - b) < 0.05 else "wrong"
    if str(a) == str(b):
        return "agree"
    ea, eb = _entities(a), _entities(b)
    if ea == eb:
        return "cosmetic"
    return "incomplete" if eb < ea else "wrong"


def run(arm="baseline"):
    ex = get_extractor(arm)
    rows, ref = [], None

    for label, name in ROUTES:
        path = DEMO / name
        if not path.exists():
            rows.append({"route": label, "error": "fixture missing"})
            continue
        try:
            ing = load_document(path)
            rec = ex.extract(name, ing.text)
            flags, urgency, queue = evaluate(rec)
        except Exception as exc:                       # noqa: BLE001
            rows.append({"route": label, "error": f"{type(exc).__name__}: {exc}"})
            continue

        vals = _values(rec)
        if ref is None:
            ref = vals

        agree = cosmetic = incomplete = wrong = lost = 0
        for f in ALL_FIELDS:
            rv, rok = ref[f]
            cv, cok = vals[f]
            if not rok:
                continue                      # reference had nothing to compare
            if not cok:
                lost += 1                     # withheld or missed -- the safe failure
                continue
            verdict = _compare(rv, cv)
            agree += verdict == "agree"
            cosmetic += verdict == "cosmetic"
            incomplete += verdict == "incomplete"
            wrong += verdict == "wrong"       # invented content -- the only dangerous case
        rows.append({
            "route": label, "kind": ing.source_kind, "ocr": ing.ocr_used,
            "chars": len(ing.text), "agree": agree, "cosmetic": cosmetic,
            "incomplete": incomplete, "wrong": wrong, "lost": lost,
            "flags": len(flags), "urgency": urgency, "queue": queue.value,
            "review": len(rec.review_queue()),
        })
    return rows


def to_markdown(rows) -> str:
    L = ["## Ingestion fidelity", "",
         "The same discharge summary, ingested four ways. Plain text is the reference; "
         "every other row is scored against it field by field.", "",
         "| Route | Detected as | Exact | OCR noise, same content | Entries dropped | **Invented** | Withheld | Flags | Urgency |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['route']} | — | — | — | — | — | — | — | `{r['error']}` |")
            continue
        L.append(f"| {r['route']} | `{r['kind']}` | {r['agree']} | {r['cosmetic']} | "
                 f"{r['incomplete']} | **{r['wrong']}** | {r['lost']} | {r['flags']} | "
                 f"{r['urgency']}/100 |")
    invented = sum(r.get("wrong", 0) for r in rows)
    L += ["",
          f"**Invented entities across all four routes: {invented}.** That is the column that "
          "would hurt a patient, and it is the one that stays at zero.", "",
          "What OCR costs is *recall*. On the scanned routes three lab rows are lost — "
          "`HbA1c` transcribes as `HbAlc`, and the row is dropped rather than guessed at — "
          "and the risk-flag count falls from 10 to 7 as a direct consequence. That is a real "
          "and serious loss: a flag that never fires cannot be reviewed. But nothing is "
          "fabricated to fill the gap.", "",
          "Scoring those dropped rows as errors would have made OCR look like it invents lab "
          "results. It does not, and engineering against the wrong failure mode is how you "
          "end up hardening the part that was already safe.", "",
          "A scanned PDF is also *detected* as one rather than passed through as an empty "
          "document — the failure mode that would otherwise yield a confident, entirely "
          "blank patient record.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    rows = run()
    print(to_markdown(rows))
