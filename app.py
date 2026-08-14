"""Clinical Document Intelligence Hub - demo UI.

    streamlit run app.py

The interface is built around one claim: a reviewer should never have to trust
a value. Every extracted field shows its confidence and the exact span it came
from, and anything the pipeline could not verify is moved OUT of the summary
card and into a review queue rather than displayed with a quiet caveat.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

from cdi.extract import BaselineExtractor, get_extractor
from cdi.ingest import IMAGE_SUFFIXES, load_bytes, load_document
from cdi.reason import Queue, Severity, evaluate, next_step
from cdi.schema import FieldStatus

ROOT = Path(__file__).parent
DOCS, OUT = ROOT / "data" / "documents", ROOT / "outputs"
DEMO = ROOT / "data" / "demo"   # walkthrough fixtures, deliberately NOT in the eval corpus

SEV_COLOR = {Severity.CRITICAL: "#b3261e", Severity.HIGH: "#c26401",
             Severity.MODERATE: "#7a5c00", Severity.INFO: "#40556b"}
QUEUE_COLOR = {Queue.IMMEDIATE: "#b3261e", Queue.PHARMACY: "#c26401",
               Queue.COORDINATION: "#1b6ca8", Queue.ROUTINE: "#3d6b47"}

st.set_page_config(page_title="Clinical Document Intelligence Hub",
                   page_icon="+", layout="wide")


@st.cache_data(show_spinner=False)
def load_docs():
    """Demo fixtures first, then the evaluation corpus.

    The demo documents live in a separate folder and are excluded from every
    metric in run_eval.py -- a document chosen because it looks good in a
    walkthrough has no business in an accuracy number.
    """
    # explicit order: the plain-text fixture leads so the walkthrough is predictable,
    # with the PDF and scanned variants next to it for the ingestion segment
    rank = {".txt": 0, ".md": 0, ".pdf": 1}
    demo = [("demo", p.name) for p in sorted(
        (q for q in DEMO.iterdir() if q.suffix.lower() in {".txt", ".md", ".pdf"} | IMAGE_SUFFIXES),
        key=lambda q: (rank.get(q.suffix.lower(), 2), q.name))]
    corpus = [("corpus", p.name) for p in sorted(DOCS.glob("*.txt"))]
    return demo + corpus


def conf_bar(c: float) -> str:
    filled = int(round(c * 10))
    return "█" * filled + "░" * (10 - filled)


def render_field(label: str, fld, unit: str = ""):
    if fld.status is FieldStatus.EXTRACTED:
        val = fld.value
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        st.markdown(f"**{label}**  \n{val}{unit}")
        st.caption(f"{conf_bar(fld.confidence)} {fld.confidence:.2f}")
        if fld.evidence:
            with st.expander("source", expanded=False):
                st.code(fld.evidence.strip()[:300], language=None)
    elif fld.status in (FieldStatus.ABSTAINED, FieldStatus.UNGROUNDED):
        st.markdown(f"**{label}**  \n:orange[withheld - needs review]")
        st.caption(f"{fld.status.value} · conf {fld.confidence:.2f}")
    else:
        st.markdown(f"**{label}**  \n:gray[not documented]")


# ------------------------------------------------------------------ sidebar
st.sidebar.title("Clinical DI Hub")
st.sidebar.caption("Firstsource POC · document -> structured record -> triage")

def _api_key() -> str | None:
    """Streamlit Cloud supplies secrets; a local run uses the environment."""
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:                                  # noqa: BLE001
        pass                                           # no secrets.toml -- fine
    return os.environ.get("ANTHROPIC_API_KEY")


key = _api_key()
has_key = bool(key)
if has_key:
    os.environ.setdefault("ANTHROPIC_API_KEY", key)    # the SDK reads the env

arm = st.sidebar.selectbox(
    "Extraction backend",
    ["anthropic", "baseline"] if has_key else ["baseline", "anthropic"],
    format_func=lambda a: ("anthropic (LLM)" if a == "anthropic" else "baseline (no key needed)")
                          + ("" if has_key or a == "baseline" else " - key not configured"),
    help="`anthropic` = schema-constrained LLM extraction. `baseline` = deterministic "
         "regex control arm, runs with no API key.")
if arm == "anthropic" and not has_key:
    st.sidebar.warning(
        "No API key is configured on this deployment, so the LLM arm cannot run. "
        "Switch back to `baseline`.")
k = st.sidebar.slider("Samples per document (self-consistency)", 1, 5, 1,
                      help="k>1 re-runs extraction and scores agreement across samples. "
                           "Costs k x tokens.") if arm == "anthropic" else 1

st.sidebar.divider()
src = st.sidebar.radio("Document source", ["Sample corpus", "Paste / upload"])

text, doc_id, ingested = None, "PASTED", None
if src == "Sample corpus":
    entries = load_docs()
    labels = [f"{'[demo] ' if k == 'demo' else ''}{n}" for k, n in entries]
    idx = st.sidebar.selectbox("Document", range(len(entries)), index=0,
                               format_func=lambda i: labels[i])
    kind, name = entries[idx]
    doc_id = Path(name).stem
    try:
        ingested = load_document((DEMO if kind == "demo" else DOCS) / name)
        text = ingested.text
    except Exception as exc:                       # noqa: BLE001
        st.sidebar.error(f"{type(exc).__name__}: {exc}")
    if kind == "demo":
        st.sidebar.caption("Demo fixture - excluded from all evaluation metrics.")
else:
    up = st.sidebar.file_uploader(
        "Upload a document", type=["txt", "md", "pdf", "png", "jpg", "jpeg", "tif", "tiff"],
        help="Text and text-layer PDFs are read directly. Scanned PDFs and images "
             "are detected and routed through OCR.")
    pasted = st.sidebar.text_area("...or paste document text", height=200)
    if up is not None:
        try:
            ingested = load_bytes(up.read(), up.name)
            text, doc_id = ingested.text, Path(up.name).stem
        except Exception as exc:                   # noqa: BLE001
            st.sidebar.error(f"{type(exc).__name__}: {exc}")
    elif pasted.strip():
        text = pasted

if not has_key:
    st.sidebar.info(
        "**Running the deterministic arm.** This public demo has no API key, so it runs "
        "the regex control arm rather than the LLM. Everything else is identical: the same "
        "verification layer, the same rules engine, the same triage. The Evaluation tab "
        "reports both arms and the fault-injection result, none of which need a key.")

tab_run, tab_eval = st.tabs(["Extraction & triage", "Evaluation"])

# ------------------------------------------------------------------ main tab
with tab_run:
    if not text:
        st.info("Choose a sample document or paste one in the sidebar.")
        st.stop()

    if ingested is not None and ingested.degraded:
        st.warning(
            f"This document was read as **{ingested.source_kind}** via OCR. Every "
            "confidence score below is measured against the transcription, not the "
            "original page — treat withheld fields as expected rather than anomalous.")
    elif ingested is not None and ingested.source_kind != "text":
        st.caption(f"Ingested as `{ingested.source_kind}`"
                   + (f" · {ingested.pages} pages" if ingested.pages > 1 else ""))

    left, right = st.columns([1, 1.35], gap="large")
    with left:
        st.subheader("Source document")
        st.text_area("raw", text, height=520, label_visibility="collapsed")

    with right:
        try:
            with st.spinner(f"Extracting with `{arm}`..."):
                rec = get_extractor(arm).extract(doc_id, text, k=k)
        except Exception as exc:                      # noqa: BLE001
            st.error(f"{type(exc).__name__}: {exc}")
            st.caption("Falling back to the deterministic baseline arm.")
            rec = BaselineExtractor().extract(doc_id, text)

        flags, urgency, queue = evaluate(rec)

        st.markdown(
            f"<div style='padding:14px 18px;border-radius:10px;background:{QUEUE_COLOR[queue]};"
            f"color:white'><div style='font-size:0.78rem;opacity:.85;letter-spacing:.08em'>"
            f"ROUTED TO</div><div style='font-size:1.25rem;font-weight:700'>{queue.value}</div>"
            f"<div style='font-size:0.9rem;margin-top:4px'>Urgency score {urgency}/100 · "
            f"{rec.document_type.value.replace('_',' ')}</div></div>",
            unsafe_allow_html=True)
        st.caption(next_step(queue, flags))

        st.subheader("Patient summary card")
        c = st.columns(4)
        for col, (lbl, f) in zip(c, [("Patient", "patient_name"), ("Age", "age"),
                                     ("Sex", "sex"), ("MRN", "mrn")]):
            with col:
                render_field(lbl, rec.field(f))
        c = st.columns(4)
        for col, (lbl, f, u) in zip(c, [("BP systolic", "bp_systolic", " mmHg"),
                                        ("BP diastolic", "bp_diastolic", " mmHg"),
                                        ("Heart rate", "heart_rate", " bpm"),
                                        ("SpO2", "spo2", " %")]):
            with col:
                render_field(lbl, rec.field(f), u)
        c = st.columns(4)
        for col, (lbl, f, u) in zip(c, [("Temperature", "temp_f", " F"),
                                        ("Encounter date", "encounter_date", ""),
                                        ("Follow-up", "follow_up_days", " days"),
                                        ("Smoking", "smoking_status", "")]):
            with col:
                render_field(lbl, rec.field(f), u)

        st.markdown("**Chief complaint**")
        cc = rec.field("chief_complaint")
        st.write(cc.display())

        for lbl, f in [("Diagnoses", "diagnoses"), ("Allergies", "allergies")]:
            fld = rec.field(f)
            st.markdown(f"**{lbl}**")
            if fld.status is FieldStatus.EXTRACTED:
                st.write(", ".join(map(str, fld.value)) if fld.value else "_none documented_")
            else:
                st.write(fld.display())
            if fld.dropped_items:
                st.caption(f"{fld.dropped_items} entry(s) removed - not supported by the document")

        med = rec.field("medications")
        st.markdown("**Medications**")
        if med.status is FieldStatus.EXTRACTED and med.value:
            st.dataframe([{"Drug": m.get("name"), "Dose": m.get("dose"),
                           "Frequency": m.get("frequency")} for m in med.value],
                         width="stretch", hide_index=True)
        else:
            st.write(med.display())

        lab = rec.field("labs")
        st.markdown("**Laboratory results**")
        if lab.status is FieldStatus.EXTRACTED and lab.value:
            st.dataframe([{"Test": l.get("name"), "Value": l.get("value"),
                           "Unit": l.get("unit")} for l in lab.value],
                         width="stretch", hide_index=True)
        else:
            st.write(lab.display())

        st.subheader(f"Risk flags ({len(flags)})")
        if not flags:
            st.success("No rules triggered.")
        for f in flags:
            st.markdown(
                f"<div style='border-left:4px solid {SEV_COLOR[f.severity]};padding:6px 12px;"
                f"margin-bottom:6px;background:rgba(128,128,128,0.07)'>"
                f"<b>{f.message}</b><br><span style='font-size:0.82rem;opacity:.75'>"
                f"{f.severity.value.upper()} · <code>{f.rule_id}</code> · {f.basis}</span></div>",
                unsafe_allow_html=True)

        gaps = rec.review_queue()
        st.subheader(f"Human review queue ({len(gaps)})")
        if gaps:
            st.warning("Withheld rather than shown: " + ", ".join(f"`{g}`" for g in gaps))
        else:
            st.success("Every field cleared verification.")

        with st.expander("Structured output (JSON)"):
            st.json(json.loads(rec.model_dump_json()))

# ------------------------------------------------------------------ eval tab
with tab_eval:
    st.subheader("Measured performance")
    arms_avail = sorted(p.stem.replace("eval_", "") for p in OUT.glob("eval_*.json")
                        if p.stem != "eval_injection")
    inj = OUT / "eval_injection.json"
    if not arms_avail:
        st.info("Run `python run_eval.py` to generate the evaluation artefacts.")
    else:
        pick = st.selectbox("Extraction arm", arms_avail,
                            index=arms_avail.index("anthropic") if "anthropic" in arms_avail else 0)
        g = json.loads((OUT / f"eval_{pick}.json").read_text())["gated"]
        c = st.columns(4)
        c[0].metric("Silent error rate", f"{g['silent_error_rate']:.1%}",
                    help="Of fields shown to a human, the fraction that were wrong.")
        c[1].metric("Surfaced precision", f"{g['surfaced_precision']:.1%}")
        c[2].metric("Abstention rate", f"{g['abstention_rate']:.1%}")
        c[3].metric("Doc-type accuracy", f"{g['doc_type_accuracy']:.1%}")
        if inj.exists():
            i = json.loads(inj.read_text())
            st.markdown("**Verification layer under fault injection**")
            c = st.columns(3)
            c[0].metric("Fabrication catch rate", f"{i['catch_rate']:.1%}")
            c[1].metric("False block rate", f"{i['false_block_rate']:.1%}")
            c[2].metric("Faults injected", i["faults_injected"])
        st.markdown("**Per-field**")
        st.dataframe([{"Field": k, **v} for k, v in g["per_field"].items()],
                     width="stretch", hide_index=True)
        rep = OUT / "EVALUATION.md"
        if rep.exists():
            with st.expander("Full evaluation report"):
                st.markdown(rep.read_text())
