"""Clinical reasoning: risk flags, urgency scoring, triage routing.

Deliberate design choice: this layer is RULES, not an LLM.

The LLM's job is reading comprehension -- turning prose into structured fields.
Deciding that a potassium of 6.4 warrants immediate review is not a reading
problem, it is a policy problem, and in healthcare that policy has to be
auditable, versionable, and reviewable by a clinician who does not trust the
model. A rule fires identically every time and can be traced to a threshold in
a table. An LLM asked to triage cannot offer that, and its failure mode
(plausible-sounding wrong urgency) is exactly the one that hurts patients.

So: LLM extracts, rules decide. Every flag names the rule that produced it.

Thresholds below follow widely used adult reference/critical-value conventions
and standard label contraindications. They are illustrative for a prototype and
would require clinical governance sign-off before any real deployment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .schema import PatientRecord


class Queue(str, Enum):
    IMMEDIATE = "IMMEDIATE CLINICAL REVIEW"
    PHARMACY = "PHARMACIST REVIEW"
    COORDINATION = "CARE COORDINATION"
    ROUTINE = "ROUTINE ADMIN PROCESSING"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    INFO = "info"


SEV_POINTS = {Severity.CRITICAL: 45, Severity.HIGH: 25, Severity.MODERATE: 12, Severity.INFO: 3}

DISPLAY = {"wbc": "WBC", "egfr": "eGFR", "hba1c": "HbA1c", "troponin i": "Troponin I",
           "glucose (fasting)": "Fasting glucose"}


def _label(name: str) -> str:
    return DISPLAY.get(name, name.title())


@dataclass
class Flag:
    rule_id: str
    severity: Severity
    message: str
    basis: str          # the concrete value that tripped the rule
    queue: Queue


# name -> (low_critical, low_warn, high_warn, high_critical); None = unbounded
LAB_RULES = {
    "potassium":        (2.9, 3.5, 5.2, 6.0),
    "sodium":           (120, 135, 145, 158),
    "hemoglobin":       (7.0, 12.0, None, None),
    "platelets":        (50, 150, None, None),
    "wbc":              (2.0, 4.5, 11.0, 20.0),
    "creatinine":       (None, None, 1.3, 3.0),
    "troponin i":       (None, None, 0.04, 0.5),
    "hba1c":            (None, None, 7.0, 9.0),
    "egfr":             (30, 60, None, None),
    "glucose (fasting)": (54, 70, 126, 250),
}

NEPHROTOXIC = {"ibuprofen", "naproxen", "diclofenac"}
RENAL_CLEARED = {"metformin"}
K_RAISING = {"lisinopril", "enalapril", "ramipril", "spironolactone"}
BLEED_RISK = {"warfarin", "apixaban", "rivaroxaban"}

ALLERGY_CONFLICTS = {
    "penicillin": {"amoxicillin", "ampicillin", "co-amoxiclav", "penicillin"},
    "aspirin": {"aspirin", "ibuprofen", "naproxen"},   # NSAID cross-sensitivity
    "sulfa drugs": {"co-trimoxazole", "sulfamethoxazole", "furosemide"},
    "codeine": {"codeine", "tramadol"},
}

HIGH_RISK_DX = {"congestive heart failure", "acute coronary syndrome", "copd",
                "chronic kidney disease stage 3"}


def _labs(rec: PatientRecord) -> dict[str, float]:
    if not rec.labs.usable or not rec.labs.value:
        return {}
    out = {}
    for lb in rec.labs.value:
        try:
            out[str(lb.get("name", "")).strip().lower()] = float(lb.get("value"))
        except (TypeError, ValueError):
            continue
    return out


def _med_names(rec: PatientRecord) -> list[str]:
    if not rec.medications.usable or not rec.medications.value:
        return []
    return [str(m.get("name", "")).strip().lower() for m in rec.medications.value]


def evaluate(rec: PatientRecord) -> tuple[list[Flag], int, Queue]:
    """Return (flags, urgency 0-100, routing queue)."""
    flags: list[Flag] = []
    labs, meds = _labs(rec), _med_names(rec)

    # --- lab thresholds -----------------------------------------------------
    for name, val in labs.items():
        rule = LAB_RULES.get(name)
        if not rule:
            continue
        lo_c, lo_w, hi_w, hi_c = rule
        if lo_c is not None and val <= lo_c:
            flags.append(Flag(f"LAB.{name}.critical_low", Severity.CRITICAL,
                              f"Critically low {_label(name)}", f"{name}={val}", Queue.IMMEDIATE))
        elif hi_c is not None and val >= hi_c:
            flags.append(Flag(f"LAB.{name}.critical_high", Severity.CRITICAL,
                              f"Critically high {_label(name)}", f"{name}={val}", Queue.IMMEDIATE))
        elif lo_w is not None and val < lo_w:
            flags.append(Flag(f"LAB.{name}.low", Severity.MODERATE,
                              f"{_label(name)} below reference range", f"{name}={val}", Queue.COORDINATION))
        elif hi_w is not None and val > hi_w:
            flags.append(Flag(f"LAB.{name}.high", Severity.MODERATE,
                              f"{_label(name)} above reference range", f"{name}={val}", Queue.COORDINATION))

    # --- vitals -------------------------------------------------------------
    def v(n):
        f = rec.field(n)
        return f.value if f.usable else None

    sbp, dbp, hr, spo2, temp = v("bp_systolic"), v("bp_diastolic"), v("heart_rate"), v("spo2"), v("temp_f")
    if (sbp and sbp >= 180) or (dbp and dbp >= 120):
        flags.append(Flag("VITAL.hypertensive_crisis", Severity.CRITICAL,
                          "Hypertensive crisis range", f"BP={sbp}/{dbp}", Queue.IMMEDIATE))
    if spo2 is not None and spo2 < 90:
        flags.append(Flag("VITAL.hypoxaemia", Severity.CRITICAL,
                          "Oxygen saturation below 90%", f"SpO2={spo2}%", Queue.IMMEDIATE))
    if hr is not None and (hr > 120 or hr < 50):
        flags.append(Flag("VITAL.rate_abnormal", Severity.HIGH,
                          "Heart rate outside 50-120 bpm", f"HR={hr}", Queue.IMMEDIATE))
    if temp is not None and temp >= 101.0:
        flags.append(Flag("VITAL.febrile", Severity.MODERATE,
                          "Febrile", f"Temp={temp}F", Queue.COORDINATION))

    # --- medication safety --------------------------------------------------
    egfr = labs.get("egfr")
    if egfr is not None:
        for m in meds:
            if any(r in m for r in RENAL_CLEARED) and egfr < 30:
                flags.append(Flag("MED.metformin_egfr", Severity.CRITICAL,
                                  "Metformin contraindicated at eGFR < 30",
                                  f"{m}, eGFR={egfr}", Queue.PHARMACY))
            if any(r in m for r in NEPHROTOXIC) and egfr < 60:
                flags.append(Flag("MED.nsaid_ckd", Severity.HIGH,
                                  "NSAID with reduced renal function",
                                  f"{m}, eGFR={egfr}", Queue.PHARMACY))
    k = labs.get("potassium")
    if k is not None and k > 5.2:
        for m in meds:
            if any(r in m for r in K_RAISING):
                flags.append(Flag("MED.acei_hyperkalaemia", Severity.HIGH,
                                  "Potassium-raising drug with elevated potassium",
                                  f"{m}, K={k}", Queue.PHARMACY))
    if any(any(b in m for b in BLEED_RISK) for m in meds) and \
       any(any(n in m for n in NEPHROTOXIC) for m in meds):
        flags.append(Flag("MED.anticoag_nsaid", Severity.HIGH,
                          "Anticoagulant co-prescribed with NSAID - bleeding risk",
                          "; ".join(meds), Queue.PHARMACY))

    # --- allergy / prescription conflict ------------------------------------
    if rec.allergies.usable and rec.allergies.value:
        for allergen in rec.allergies.value:
            conflict = ALLERGY_CONFLICTS.get(str(allergen).strip().lower(), set())
            for m in meds:
                if any(c in m for c in conflict):
                    flags.append(Flag("SAFETY.allergy_conflict", Severity.CRITICAL,
                                      f"Prescribed drug conflicts with documented {allergen} allergy",
                                      f"allergy={allergen}, drug={m}", Queue.IMMEDIATE))

    # --- care continuity ----------------------------------------------------
    dxs = [str(d).lower() for d in (rec.diagnoses.value or [])] if rec.diagnoses.usable else []
    high_risk = [d for d in dxs if any(h in d for h in HIGH_RISK_DX)]
    if rec.document_type.value == "discharge_summary" and high_risk and not rec.follow_up_days.usable:
        flags.append(Flag("CARE.no_followup_highrisk", Severity.HIGH,
                          "High-risk diagnosis discharged with no follow-up documented",
                          "; ".join(high_risk), Queue.COORDINATION))

    # --- data quality: extraction gaps are themselves actionable -------------
    gaps = rec.review_queue()
    if gaps:
        flags.append(Flag("DATA.low_confidence_fields", Severity.INFO,
                          f"{len(gaps)} field(s) withheld pending human verification",
                          ", ".join(gaps), Queue.ROUTINE))

    urgency = min(100, sum(SEV_POINTS[f.severity] for f in flags))
    order = [Queue.IMMEDIATE, Queue.PHARMACY, Queue.COORDINATION, Queue.ROUTINE]
    present = {f.queue for f in flags}
    queue = next((q for q in order if q in present), Queue.ROUTINE)
    return flags, urgency, queue


def next_step(queue: Queue, flags: list[Flag]) -> str:
    crit = [f for f in flags if f.severity is Severity.CRITICAL] or \
           [f for f in flags if f.severity is Severity.HIGH]
    if queue is Queue.IMMEDIATE:
        return ("Escalate to on-call clinician now. Driving flags: "
                + "; ".join(f.message for f in crit[:3]))
    if queue is Queue.PHARMACY:
        return "Route to pharmacist for medication reconciliation before the next dispense."
    if queue is Queue.COORDINATION:
        return "Assign to care coordination for follow-up scheduling and result communication."
    return "No clinical escalation triggered. Process through standard administrative queue."
