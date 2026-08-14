"""Extraction backends.

Two arms, same interface, same verification path:

  AnthropicExtractor -- schema-constrained extraction via tool use. The tool
      schema forces one (value, evidence) pair per field, so the model cannot
      return a value without also committing to where it came from.

  BaselineExtractor  -- deterministic regex/rules over the common phrasings.
      This is the control arm. It needs no API key, so the eval harness produces
      real numbers on any machine, and it quantifies how much the LLM is
      actually buying us over a competent afternoon of regex.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

from .schema import (LIST_FIELDS, SCALAR_FIELDS, VITAL_FIELDS, DocumentType,
                     ExtractedField, FieldStatus, PatientRecord)
from .verify import adjudicate

ALL_FIELDS = SCALAR_FIELDS + LIST_FIELDS + VITAL_FIELDS

FIELD_HELP = {
    "patient_name": "Full name of the patient this document is about.",
    "age": "Patient age in years, as an integer.",
    "sex": "'M' or 'F'.",
    "mrn": "Medical record number, e.g. MRN-123456.",
    "encounter_date": "Date of this encounter in YYYY-MM-DD.",
    "chief_complaint": "The presenting complaint IN THIS ENCOUNTER. Symptoms the patient denies are NOT the chief complaint.",
    "smoking_status": "Smoking/tobacco status as stated.",
    "discharge_disposition": "Where the patient went on discharge.",
    "follow_up_days": "Days until follow-up, as an integer. If no follow-up was arranged, return null.",
    "diagnoses": "Active diagnoses for THIS patient. Exclude family history and excluded conditions.",
    "allergies": "Allergens. If the document states no known allergies, return an empty list [].",
    "medications": "Current medications as objects {name, dose, frequency}. Exclude discontinued drugs.",
    "labs": "Lab results as objects {name, value, unit}. value must be a number.",
    "bp_systolic": "Systolic BP from THIS encounter (not a previous visit).",
    "bp_diastolic": "Diastolic BP from THIS encounter (not a previous visit).",
    "heart_rate": "Heart rate / pulse in bpm from THIS encounter.",
    "temp_f": "Temperature in DEGREES FAHRENHEIT. Convert if the document records Celsius.",
    "spo2": "Oxygen saturation percentage as an integer.",
}

_INT = {"age", "follow_up_days", "bp_systolic", "bp_diastolic", "heart_rate", "spo2"}
_NUM = {"temp_f"}


def _value_schema(f):
    if f == "medications":
        return {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "dose": {"type": ["string", "null"]},
            "frequency": {"type": ["string", "null"]}}, "required": ["name"]}}
    if f == "labs":
        return {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "value": {"type": ["number", "null"]},
            "unit": {"type": ["string", "null"]}}, "required": ["name"]}}
    if f in ("diagnoses", "allergies"):
        return {"type": "array", "items": {"type": "string"}}
    if f in _INT:
        return {"type": ["integer", "null"]}
    if f in _NUM:
        return {"type": ["number", "null"]}
    return {"type": ["string", "null"]}


def build_tool_schema():
    props = {
        f: {"type": "object", "description": FIELD_HELP[f], "properties": {
            "value": _value_schema(f),
            "evidence": {"type": ["string", "null"], "description":
                         "VERBATIM span copied from the document that supports this value. "
                         "Copy exactly, do not paraphrase. Null only if the field is absent."}},
            "required": ["value", "evidence"]}
        for f in ALL_FIELDS
    }
    props["document_type"] = {"type": "string",
                              "enum": [d.value for d in DocumentType if d != DocumentType.UNKNOWN]}
    return {"type": "object", "properties": props, "required": ["document_type"] + ALL_FIELDS}


SYSTEM = """You are a clinical document extraction engine used by hospital administrative staff.

Rules, in order of priority:
1. Extract only what the document states. Never infer, never fill gaps from clinical plausibility.
2. Every field must carry an `evidence` span copied VERBATIM from the document. If you cannot copy a supporting span, the value must be null.
3. Absence is a valid answer. A field that is not documented gets value null - not a guess.
4. Negation is not evidence of presence. "No known drug allergies" means allergies = []. "Denies chest pain" means chest pain is NOT the chief complaint.
5. Attribution matters. Family history is not the patient's diagnosis. Previous-visit vitals are not this encounter's vitals. Discontinued drugs are not current medications.

Call the record_extraction tool exactly once."""


class Extractor(ABC):
    name = "base"

    @abstractmethod
    def raw(self, text: str, sample_idx: int = 0) -> dict: ...

    def extract(self, doc_id: str, text: str, k: int = 1) -> PatientRecord:
        """Run the backend k times, adjudicate every field, assemble the record.

        Sample 0 is the primary extraction. Samples 1..k-1 exist only to measure
        agreement, so backends that support temperature raise it for those runs --
        k identical greedy decodes would make agreement trivially 1.0 and the
        signal worthless.
        """
        runs = [self.raw(text, i) for i in range(max(1, k))]
        primary = runs[0]
        rec = PatientRecord(doc_id=doc_id)
        try:
            rec.document_type = DocumentType(primary.get("document_type", "unknown"))
        except ValueError:
            rec.document_type = DocumentType.UNKNOWN

        for f in ALL_FIELDS:
            cell = primary.get(f) or {}
            samples = [(r.get(f) or {}).get("value") for r in runs]
            fld = adjudicate(cell.get("value"), cell.get("evidence"), text, samples)
            if f in VITAL_FIELDS:
                rec.vitals[f] = fld
            else:
                setattr(rec, f, fld)
        return rec


class AnthropicExtractor(Extractor):
    name = "anthropic"

    def __init__(self, model=None, temperature=0.0):
        import anthropic  # imported lazily so the baseline arm needs no SDK
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("CDI_MODEL", "claude-sonnet-5")
        self.temperature = temperature
        self.tool = {"name": "record_extraction",
                     "description": "Record every extracted field with its supporting evidence span.",
                     "input_schema": build_tool_schema()}

    def raw(self, text: str, sample_idx: int = 0) -> dict:
        # consistency samples need diversity; the primary stays greedy
        temp = self.temperature if sample_idx == 0 else max(self.temperature, 0.7)
        msg = self.client.messages.create(
            model=self.model, max_tokens=4096, temperature=temp,
            system=SYSTEM, tools=[self.tool],
            tool_choice={"type": "tool", "name": "record_extraction"},
            messages=[{"role": "user", "content": f"<document>\n{text}\n</document>"}],
        )
        for block in msg.content:
            if block.type == "tool_use":
                return block.input
        return {}


# --------------------------------------------------------------- baseline arm

_PATTERNS = {
    "patient_name": [r"Patient Name\s*:\s*(.+)", r"^([A-Z][a-z]+ [A-Z][a-z]+),\s+an?\s+\d+-year-old"],
    "age": [r"Age\s*/\s*Sex\s*:\s*(\d+)", r"(\d+)-year-old"],
    "sex": [r"Age\s*/\s*Sex\s*:\s*\d+\s*/\s*([MF])", r"\d+-year-old\s+(male|female)"],
    "mrn": [r"(MRN-\d{6})"],
    "encounter_date": [r"Date\s*:\s*(\d{4}-\d{2}-\d{2})", r"seen on (\d{4}-\d{2}-\d{2})"],
    "chief_complaint": [r"Chief Complaint:\s*(.+)", r"Presenting complaint\s*-\s*(.+?)\.",
                        r"Patient presents with (.+?)\.", r"C/O (.+?)\."],
    "smoking_status": [r"Social History:\s*(.+?)\.", r"Smoking status\s*-\s*(.+?)\.",
                       r"SOCIAL HX:\s*(.+?);", r"Tobacco:\s*(.+?)\."],
    "discharge_disposition": [r"Disposition:\s*(.+?)\.", r"DISPOSITION\s*-\s*(.+)",
                              r"Patient was (.+?)\."],
    "follow_up_days": [r"Follow-up in (\d+) days", r"reviewed in clinic after (\d+) days",
                       r"F/U:\s*(\d+) days"],
    "bp_systolic": [r"BP:?\s*(\d{2,3})/\d{2,3}", r"Blood [Pp]ressure\s*\.*\s*(\d{2,3})/\d{2,3}",
                    r"B/P (\d{2,3}) over \d{2,3}"],
    "bp_diastolic": [r"BP:?\s*\d{2,3}/(\d{2,3})", r"Blood [Pp]ressure\s*\.*\s*\d{2,3}/(\d{2,3})",
                     r"B/P \d{2,3} over (\d{2,3})"],
    "heart_rate": [r"HR:\s*(\d{2,3})", r"Pulse\s+(\d{2,3})/min", r"Heart rate (\d{2,3})",
                   r"P:\s*(\d{2,3})", r"Pulse rate\s*\.*\s*(\d{2,3})"],
    "spo2": [r"SpO2:?\s*\.*\s*(\d{2,3})\s*%", r"O2 sat (\d{2,3})%",
             r"Oxygen saturation (\d{2,3})%", r"SaO2 (\d{2,3})%"],
    "temp_f": [r"Temp:?\s*(\d{2,3}\.?\d?)\s*F", r"Temperature\s+(\d{2,3}\.?\d?)\s*°?F",
               r"Temperature\s*\.*\s*(\d{2,3}\.?\d?)\s*F"],
}


class BaselineExtractor(Extractor):
    """Good-faith regex baseline over the most common phrasings. No API key needed."""
    name = "baseline"

    def raw(self, text: str, sample_idx: int = 0) -> dict:
        out = {"document_type": self._doc_type(text)}
        for f in SCALAR_FIELDS + VITAL_FIELDS:
            out[f] = self._first(text, _PATTERNS.get(f, []), f)
        out["diagnoses"] = self._section_list(
            text, r"(?:DIAGNOSES|Active Problem List:|Assessment:|IMPRESSION)")
        out["allergies"] = self._allergies(text)
        out["medications"] = self._meds(text)
        out["labs"] = self._labs(text)
        return out

    @staticmethod
    def _doc_type(t):
        for key, val in [("DISCHARGE SUMMARY", "discharge_summary"),
                         ("PATIENT INTAKE FORM", "intake_form"),
                         ("LABORATORY REPORT", "lab_report"),
                         ("PROGRESS NOTE", "physician_note")]:
            if key in t:
                return val
        return "physician_note"

    def _first(self, text, pats, field):
        """First matching pattern wins. Unparseable matches are skipped, not raised.

        OCR output routinely produces things like "Temp: 9.1 F" or a bare ".",
        and an extractor that throws on the first malformed number takes the whole
        document down with it. Failing to extract one field is recoverable;
        crashing is not.
        """
        for p in pats:
            m = re.search(p, text, re.MULTILINE)
            if not m:
                continue
            raw = m.group(1).strip().rstrip(".")
            line = text[text.rfind("\n", 0, m.start()) + 1:
                        text.find("\n", m.end()) if text.find("\n", m.end()) > 0 else len(text)]
            val = raw
            try:
                if field in _INT:
                    val = int(float(raw))
                elif field in _NUM:
                    val = float(raw)
                elif field == "sex":
                    val = {"male": "M", "female": "F"}.get(raw.lower(), raw.upper()[:1])
            except (TypeError, ValueError):
                continue    # malformed for this pattern; try the next one
            return {"value": val, "evidence": line.strip()}
        return {"value": None, "evidence": None}

    @staticmethod
    def _section(text, header_pat):
        m = re.search(header_pat, text)
        if not m:
            return ""
        rest = text[m.end():]
        end = rest.find("\n\n")
        return rest[:end if end > 0 else len(rest)]

    def _section_list(self, text, header_pat):
        blk = self._section(text, header_pat)
        if not blk:
            return {"value": [], "evidence": None}
        items = []
        for ln in blk.splitlines():
            ln = ln.strip()
            if not ln or "Family history" in ln or ln.startswith("["):
                continue
            # OCR renders "1." as "1," or "1)" about as often as it gets it right
            ln = re.sub(r"^\d+\s*[.,)]\s*|^[-*\u2022]\s*", "", ln)
            if ln.startswith("Known "):
                items += [x.strip().rstrip(".") for x in ln[6:].split(";")]
            else:
                items.append(ln.rstrip("."))
        return {"value": [i for i in items if i], "evidence": blk.strip()[:400]}

    def _allergies(self, text):
        for neg in [r"ALLERGIES:\s*NKDA", r"Allergies:\s*No known drug allergies\.",
                    r"Known allergies:\s*none reported",
                    r"reports no known drug allergies"]:
            m = re.search(neg, text)
            if m:
                return {"value": [], "evidence": m.group(0)}
        blk = self._section(text, r"(?:ALLERGIES|Known allergies:|Drug allergies:)")
        if not blk.strip():
            return {"value": [], "evidence": None}
        line = blk.strip().splitlines()[0]
        clean = re.sub(r"\s*[-(].*$", "", line).strip()
        parts = re.split(r",| and |;", clean)
        return {"value": [p.strip() for p in parts if p.strip()], "evidence": line}

    def _meds(self, text):
        blk = self._section(text, r"(?:CURRENT MEDICATIONS|Medications on admission:|Rx:|MEDICATION LIST)")
        meds = []
        for ln in blk.splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("["):
                continue
            ln = re.sub(r"^[-*]\s*", "", ln)
            m = (re.match(r"(.+?)\s*\((.+?)\)\s*-\s*(.+)", ln)
                 or re.match(r"(.+?),\s*(.+?),\s*(.+)", ln)
                 or re.match(r"(.+?)\s+(\d+\s*(?:mg|mcg|puffs))\s+(.+)", ln))
            if m:
                meds.append({"name": m.group(1).strip(), "dose": m.group(2).strip(),
                             "frequency": m.group(3).strip()})
        return {"value": meds, "evidence": blk.strip()[:400] or None}

    def _labs(self, text):
        blk = self._section(text, r"(?:LABORATORY RESULTS|Investigations:|LAB DATA)")
        labs = []
        for ln in blk.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            m = re.match(r"(.+?)[\s.:]{2,}([\d.]+)\s*(\S*)", ln) or \
                re.match(r"(.+?):\s*([\d.]+)\s*(\S*)", ln)
            if not m:
                continue
            try:
                value = float(m.group(2))
            except ValueError:
                continue    # OCR debris such as a lone "." -- drop the row
            labs.append({"name": m.group(1).strip().rstrip(":."),
                         "value": value, "unit": m.group(3) or None})
        return {"value": labs, "evidence": blk.strip()[:400] or None}


def get_extractor(name: str) -> Extractor:
    return {"baseline": BaselineExtractor, "anthropic": AnthropicExtractor}[name]()
