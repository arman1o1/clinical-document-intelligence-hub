"""Synthetic clinical corpus generator.

The brief permits generated data. Templating is the only way to obtain exact
gold labels for free, but naive templating produces a corpus that a regex can
solve -- which would make the eval meaningless. So the generator deliberately
injects the things that break brittle extractors:

  * surface variation   -- 4-6 phrasings per field ("BP 148/92", "B/P 148 over 92")
  * distractor values   -- prior-visit vitals/labs that must NOT be extracted
  * negation            -- "no known drug allergies", "denies chest pain"
  * structural absence  -- fields omitted entirely, so gold is None (tests abstention)
  * OCR noise           -- character-level corruption on a subset of documents
  * narrative documents -- ~30% are rendered as free prose with no field labels,
                           numbers spelled out, dates in long form and temperature
                           in Celsius. Real physician notes look like this, and no
                           regex recovers the fields from them.

Seeded, so the corpus and its labels are byte-reproducible.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_DIR = ROOT / "data" / "documents"
GOLD_PATH = ROOT / "data" / "gold" / "gold_labels.json"

FIRST_M = ["Rajesh", "Michael", "Arun", "David", "Sanjay", "Thomas", "Vikram", "James", "Anil", "Robert"]
FIRST_F = ["Priya", "Sarah", "Meera", "Linda", "Kavita", "Emily", "Anita", "Susan", "Deepa", "Karen"]
LAST = ["Sharma", "Patel", "Nair", "Whitfield", "Iyer", "Donnelly", "Rao", "Kaminski", "Menon", "Alvarez",
        "Banerjee", "Okafor", "Reddy", "Lindqvist", "Chatterjee", "Moreau"]

CONDITIONS = [
    "Type 2 Diabetes Mellitus", "Essential Hypertension", "Chronic Kidney Disease Stage 3",
    "Congestive Heart Failure", "COPD", "Atrial Fibrillation", "Hypothyroidism",
    "Community-Acquired Pneumonia", "Acute Coronary Syndrome", "Cellulitis of Lower Limb",
    "Iron Deficiency Anemia", "Osteoarthritis of Knee",
]

COMPLAINTS = [
    "shortness of breath on exertion", "intermittent chest tightness", "persistent productive cough",
    "swelling of both ankles", "fatigue and lightheadedness", "burning epigastric pain",
    "palpitations at rest", "left calf redness and warmth", "recurrent morning headache",
    "unintentional weight loss over 3 months",
]

MEDS = [
    ("Metformin", ["500 mg", "850 mg", "1000 mg"], ["BD", "twice daily", "OD"]),
    ("Lisinopril", ["5 mg", "10 mg", "20 mg"], ["OD", "once daily"]),
    ("Atorvastatin", ["10 mg", "20 mg", "40 mg"], ["nocte", "at bedtime", "OD"]),
    ("Amlodipine", ["5 mg", "10 mg"], ["OD", "once daily"]),
    ("Furosemide", ["20 mg", "40 mg"], ["OD", "BD"]),
    ("Warfarin", ["2 mg", "3 mg", "5 mg"], ["OD", "once daily"]),
    ("Ibuprofen", ["200 mg", "400 mg"], ["TDS", "three times daily", "PRN"]),
    ("Amoxicillin", ["250 mg", "500 mg"], ["TDS", "three times daily"]),
    ("Levothyroxine", ["50 mcg", "75 mcg", "100 mcg"], ["OD", "once daily"]),
    ("Salbutamol inhaler", ["100 mcg", "2 puffs"], ["PRN", "as needed"]),
]

ALLERGENS = ["Penicillin", "Sulfa drugs", "Aspirin", "Latex", "Iodinated contrast", "Codeine"]

# name, unit, (normal_lo, normal_hi), (abnormal_lo, abnormal_hi)
LAB_PANEL = [
    ("Hemoglobin", "g/dL", (12.5, 16.5), (7.2, 10.4)),
    ("WBC", "10^3/uL", (5.0, 10.2), (14.0, 22.0)),
    ("Platelets", "10^3/uL", (180, 400), (60, 130)),
    ("Creatinine", "mg/dL", (0.8, 1.2), (2.1, 4.4)),
    ("Potassium", "mmol/L", (3.7, 4.9), (2.6, 6.4)),
    ("Sodium", "mmol/L", (136, 144), (124, 131)),
    ("Glucose (fasting)", "mg/dL", (78, 96), (168, 310)),
    ("HbA1c", "%", (4.9, 5.6), (9.1, 12.4)),
    ("Troponin I", "ng/mL", (0.01, 0.03), (0.09, 1.8)),
    ("eGFR", "mL/min/1.73m2", (78, 104), (16, 41)),
]

_ONES = ["zero","one","two","three","four","five","six","seven","eight","nine","ten",
         "eleven","twelve","thirteen","fourteen","fifteen","sixteen","seventeen",
         "eighteen","nineteen"]
_TENS = ["","","twenty","thirty","forty","fifty","sixty","seventy","eighty","ninety"]
_MONTHS = ["January","February","March","April","May","June","July","August",
           "September","October","November","December"]


def _words(n: int) -> str:
    """Spell an integer 0-999. Used to make narrative vitals unparseable by regex."""
    n = int(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
    rem = n % 100
    return _ONES[n // 100] + " hundred" + (" and " + _words(rem) if rem else "")


def _longdate(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {_MONTHS[int(m)-1]} {y}"


SMOKING = ["never smoker", "current smoker, 10 pack-years", "ex-smoker, quit 2019",
           "current smoker, 25 pack-years", "never smoked"]

DISPOSITIONS = ["discharged home", "discharged to skilled nursing facility",
                "transferred to tertiary care centre", "discharged home with home health",
                "left against medical advice"]

# ---------------------------------------------------------------- renderers

def _bp(rng, sys_, dia):
    return rng.choice([
        f"BP: {sys_}/{dia} mmHg", f"Blood pressure {sys_}/{dia}",
        f"B/P {sys_} over {dia} mmHg", f"BP {sys_}/{dia}",
        f"Blood Pressure ...... {sys_}/{dia} mmHg",
    ])

def _hr(rng, hr):
    return rng.choice([f"HR: {hr} bpm", f"Pulse {hr}/min", f"Heart rate {hr} beats per minute",
                       f"P: {hr}", f"Pulse rate ...... {hr} bpm"])

def _temp(rng, f):
    c = round((f - 32) * 5 / 9, 1)
    return rng.choice([f"Temp: {f} F", f"Temperature {f}°F", f"T {c}°C",
                       f"Temp {c} C", f"Temperature ...... {f} F"])

def _spo2(rng, s):
    return rng.choice([f"SpO2: {s}% on room air", f"O2 sat {s}%", f"Oxygen saturation {s}% RA",
                       f"SaO2 {s}%", f"SpO2 ...... {s}%"])

def _ocr_noise(rng, text, rate=0.004):
    sub = {"0": "O", "1": "l", "5": "S", "m": "rn", "n": "ri", "l": "1"}
    out = []
    for ch in text:
        if ch in sub and rng.random() < rate:
            out.append(sub[ch])
        else:
            out.append(ch)
    return "".join(out)


def _make_truth(rng, doc_type, idx):
    sex = rng.choice(["M", "F"])
    name = f"{rng.choice(FIRST_M if sex == 'M' else FIRST_F)} {rng.choice(LAST)}"
    t = {
        "doc_id": f"DOC{idx:03d}",
        "document_type": doc_type,
        "patient_name": name,
        "age": rng.randint(24, 88),
        "sex": sex,
        "mrn": f"MRN-{rng.randint(100000, 999999)}",
        "encounter_date": f"2026-0{rng.randint(1,8)}-{rng.randint(10,28)}",
        "chief_complaint": None, "smoking_status": None,
        "discharge_disposition": None, "follow_up_days": None,
        "diagnoses": [], "allergies": [], "medications": [], "labs": [],
        "vitals": {k: None for k in ["bp_systolic", "bp_diastolic", "heart_rate", "temp_f", "spo2"]},
    }

    if doc_type in ("intake_form", "physician_note", "discharge_summary"):
        t["chief_complaint"] = rng.choice(COMPLAINTS)
    if doc_type in ("intake_form", "physician_note"):
        t["smoking_status"] = rng.choice(SMOKING)
    if doc_type in ("physician_note", "discharge_summary"):
        t["diagnoses"] = rng.sample(CONDITIONS, rng.randint(1, 3))
    if doc_type in ("intake_form", "discharge_summary", "physician_note"):
        n = rng.randint(1, 4)
        t["medications"] = [
            {"name": m[0], "dose": rng.choice(m[1]), "frequency": rng.choice(m[2])}
            for m in rng.sample(MEDS, n)
        ]
    if doc_type in ("intake_form", "discharge_summary"):
        # ~35% of patients genuinely have no allergies -> tests negation handling
        t["allergies"] = [] if rng.random() < 0.35 else rng.sample(ALLERGENS, rng.randint(1, 2))
    if doc_type in ("lab_report", "discharge_summary"):
        picks = rng.sample(LAB_PANEL, rng.randint(3, 6))
        for nm, unit, norm, abn in picks:
            lo, hi = abn if rng.random() < 0.45 else norm
            val = round(rng.uniform(lo, hi), 2 if hi < 10 else 0)
            if hi >= 10:
                val = float(int(val))
            t["labs"].append({"name": nm, "value": val, "unit": unit})
    if doc_type in ("intake_form", "physician_note", "discharge_summary"):
        v = t["vitals"]
        crisis = rng.random() < 0.25
        v["bp_systolic"] = rng.randint(182, 214) if crisis else rng.randint(108, 158)
        v["bp_diastolic"] = rng.randint(112, 128) if crisis else rng.randint(62, 92)
        v["heart_rate"] = rng.choice([rng.randint(58, 96), rng.randint(122, 148), rng.randint(38, 49)])
        v["temp_f"] = round(rng.uniform(97.1, 103.2), 1)
        v["spo2"] = rng.choice([rng.randint(95, 99), rng.randint(82, 91)])
    if doc_type == "discharge_summary":
        t["discharge_disposition"] = rng.choice(DISPOSITIONS)
        t["follow_up_days"] = rng.choice([7, 14, 30, None, 3])
    return t


def _render_narrative(rng, t):
    """Free-prose rendering: no field labels, numbers as words, Celsius, long dates.

    This is the arm of the corpus that actually separates reading comprehension
    from pattern matching.
    """
    v, L = t["vitals"], []
    title = "Mr" if t["sex"] == "M" else "Ms"
    noun = "gentleman" if t["sex"] == "M" else "lady"
    L.append(rng.choice(["CLINICAL NARRATIVE", "PROGRESS NOTE - DICTATED", "WARD ROUND NOTE"]))
    L.append("")
    L.append(f"{title} {t['patient_name']} is a {_words(t['age'])}-year-old {noun}, "
             f"hospital record {t['mrn'].replace('MRN-', 'number ')}, reviewed on "
             f"{_longdate(t['encounter_date'])}.")

    if t["chief_complaint"]:
        L.append(f"He" if t["sex"] == "M" else "She")
        L[-1] += (f" attended {rng.choice(['complaining of', 'reporting', 'with a history of'])} "
                  f"{t['chief_complaint']}, which has been troubling "
                  f"{'him' if t['sex']=='M' else 'her'} for some weeks. "
                  f"{'He' if t['sex']=='M' else 'She'} specifically denies "
                  f"{rng.choice(COMPLAINTS)}.")

    if v["bp_systolic"]:
        c = round((v["temp_f"] - 32) * 5 / 9, 1)
        L.append(f"On examination the blood pressure was {_words(v['bp_systolic'])} over "
                 f"{_words(v['bp_diastolic'])} millimetres of mercury, the pulse "
                 f"{_words(v['heart_rate'])} and regular, temperature {c} degrees Celsius, "
                 f"and oxygen saturations {_words(v['spo2'])} per cent breathing room air.")

    if t["diagnoses"]:
        L.append(f"{'His' if t['sex']=='M' else 'Her'} active problems include "
                 + ", ".join(t["diagnoses"][:-1])
                 + (" and " if len(t["diagnoses"]) > 1 else "") + t["diagnoses"][-1] + ".")
        if rng.random() < 0.3:
            L.append(f"There is a family history of {rng.choice(CONDITIONS)} in the mother, "
                     f"though this has never affected the patient.")

    if t["medications"]:
        meds = [f"{m['name'].lower()} {m['dose']} {m['frequency']}" for m in t["medications"]]
        L.append(f"{'He' if t['sex']=='M' else 'She'} continues on "
                 + ", ".join(meds[:-1]) + (" and " if len(meds) > 1 else "") + meds[-1] + ".")

    if t["document_type"] in ("intake_form", "discharge_summary"):
        if t["allergies"]:
            L.append(f"There is a documented allergy to "
                     + " and ".join(a.lower() for a in t["allergies"]) + ".")
        else:
            L.append(rng.choice(["No drug allergies were reported.",
                                 "There are no known drug allergies.",
                                 "The patient denies any drug allergy."]))

    if t["labs"]:
        parts = [f"{lb['name'].lower()} of {lb['value']:g} {lb['unit']}" for lb in t["labs"]]
        L.append("Bloods taken on admission showed " + ", ".join(parts[:-1])
                 + (" and " if len(parts) > 1 else "") + parts[-1] + ".")

    if t["smoking_status"]:
        L.append(f"In terms of social history, {'he' if t['sex']=='M' else 'she'} is a "
                 f"{t['smoking_status']}.")

    if t["discharge_disposition"]:
        L.append(f"The patient was {t['discharge_disposition']}.")
    if t["follow_up_days"]:
        L.append(f"Arrangements have been made for review in {_words(t['follow_up_days'])} days.")
    elif t["document_type"] == "discharge_summary":
        L.append("No follow-up appointment was arranged prior to discharge.")

    L += ["", f"Dictated by Dr {rng.choice(LAST)}."]
    return "\n".join(L)


def _render(rng, t):
    """Turn a ground-truth record into a messy, human-looking document."""
    dt, L = t["document_type"], []
    hdr = rng.choice(["ST. ANDREW'S REGIONAL MEDICAL CENTER", "MERIDIAN HEALTH SYSTEM",
                      "LAKESIDE COMMUNITY HOSPITAL", "NORTHFIELD GENERAL HOSPITAL"])
    L.append(hdr)
    L.append({"intake_form": "PATIENT INTAKE FORM", "discharge_summary": "DISCHARGE SUMMARY",
              "lab_report": "LABORATORY REPORT", "physician_note": "PROGRESS NOTE"}[dt])
    L.append("=" * 58)

    demo = rng.choice(["block", "inline"])
    if demo == "block":
        L += [f"Patient Name : {t['patient_name']}",
              f"Age / Sex    : {t['age']} / {t['sex']}",
              f"MRN          : {t['mrn']}",
              f"Date         : {t['encounter_date']}"]
    else:
        sx = "male" if t["sex"] == "M" else "female"
        L.append(f"{t['patient_name']}, a {t['age']}-year-old {sx} ({t['mrn']}), "
                 f"seen on {t['encounter_date']}.")
    L.append("")

    if t["chief_complaint"]:
        L.append(rng.choice([
            f"Chief Complaint: {t['chief_complaint']}",
            f"Presenting complaint - {t['chief_complaint']}.",
            f"Patient presents with {t['chief_complaint']}.",
            f"C/O {t['chief_complaint']}.",
        ]))
        # distractor: a symptom that is explicitly denied
        if rng.random() < 0.45:
            L.append(rng.choice([
                f"Denies {rng.choice(COMPLAINTS)}.",
                f"No history of {rng.choice(COMPLAINTS)}.",
                f"Patient specifically denies {rng.choice(COMPLAINTS)}.",
            ]))
        L.append("")

    if any(v is not None for v in t["vitals"].values()):
        v = t["vitals"]
        L.append(rng.choice(["VITAL SIGNS", "Vitals on arrival:", "Observations:", "VITALS"]))
        parts = [_bp(rng, v["bp_systolic"], v["bp_diastolic"]), _hr(rng, v["heart_rate"]),
                 _temp(rng, v["temp_f"]), _spo2(rng, v["spo2"])]
        rng.shuffle(parts)
        L.append("  " + rng.choice(["   ", " | ", ", "]).join(parts) if rng.random() < 0.5
                 else "\n".join("  " + p for p in parts))
        # distractor: previous-visit vitals that must not be picked up
        if rng.random() < 0.4:
            L.append(f"  (At last visit {rng.randint(2,9)} weeks ago: BP was "
                     f"{rng.randint(110,135)}/{rng.randint(64,84)}, pulse {rng.randint(60,88)}.)")
        L.append("")

    if t["diagnoses"]:
        L.append(rng.choice(["DIAGNOSES", "Active Problem List:", "Assessment:", "IMPRESSION"]))
        style = rng.choice(["num", "dash", "prose"])
        if style == "prose":
            L.append("  Known " + "; ".join(t["diagnoses"]) + ".")
        else:
            for i, d in enumerate(t["diagnoses"], 1):
                L.append(f"  {i}. {d}" if style == "num" else f"  - {d}")
        if rng.random() < 0.3:
            L.append(f"  Family history of {rng.choice(CONDITIONS)} (father) - not active for this patient.")
        L.append("")

    if t["medications"]:
        L.append(rng.choice(["CURRENT MEDICATIONS", "Medications on admission:",
                             "Rx:", "MEDICATION LIST"]))
        for m in t["medications"]:
            L.append(rng.choice([
                f"  - {m['name']} {m['dose']} {m['frequency']}",
                f"  * {m['name']}, {m['dose']}, {m['frequency']}",
                f"  {m['name']} ({m['dose']}) - {m['frequency']}",
            ]))
        if rng.random() < 0.25:
            L.append(f"  [Discontinued last month: {rng.choice(MEDS)[0]} - do not resume]")
        L.append("")

    if t["document_type"] in ("intake_form", "discharge_summary"):
        if t["allergies"]:
            L.append(rng.choice(["ALLERGIES", "Known allergies:", "Drug allergies:"]))
            L.append("  " + rng.choice([", ".join(t["allergies"]),
                                        "; ".join(t["allergies"]),
                                        " and ".join(t["allergies"])])
                     + rng.choice([" - reaction: rash", " (anaphylaxis)", "", " - urticaria"]))
        else:
            L.append(rng.choice(["ALLERGIES: NKDA", "Allergies: No known drug allergies.",
                                 "Known allergies: none reported",
                                 "The patient reports no known drug allergies."]))
        L.append("")

    if t["labs"]:
        L.append(rng.choice(["LABORATORY RESULTS", "Investigations:", "LAB DATA"]))
        for lb in t["labs"]:
            val = int(lb["value"]) if float(lb["value"]).is_integer() else lb["value"]
            L.append(rng.choice([
                f"  {lb['name']:<22}{val} {lb['unit']}",
                f"  {lb['name']}: {val} {lb['unit']}",
                f"  {lb['name']} .......... {val} {lb['unit']}",
            ]))
        L.append("")

    if t["smoking_status"]:
        L.append(rng.choice([f"Social History: {t['smoking_status']}.",
                             f"Smoking status - {t['smoking_status']}.",
                             f"SOCIAL HX: {t['smoking_status']}; alcohol occasional.",
                             f"Tobacco: {t['smoking_status']}."]))
        L.append("")

    if t["discharge_disposition"]:
        L.append(rng.choice([f"Disposition: {t['discharge_disposition']}.",
                             f"DISPOSITION - {t['discharge_disposition']}",
                             f"Patient was {t['discharge_disposition']}."]))
    if t["follow_up_days"]:
        L.append(rng.choice([f"Follow-up in {t['follow_up_days']} days.",
                             f"To be reviewed in clinic after {t['follow_up_days']} days.",
                             f"F/U: {t['follow_up_days']} days."]))
    elif t["document_type"] == "discharge_summary":
        L.append(rng.choice(["Follow-up not scheduled at time of discharge.",
                             "No follow-up appointment arranged."]))

    L += ["", "-" * 58,
          f"Signed: Dr. {rng.choice(LAST)}, {rng.choice(['MD','MBBS','DO'])}"]
    text = "\n".join(L)
    if rng.random() < 0.22:
        text = _ocr_noise(rng, text)
    return text


def build(n=32, seed=20260814):
    rng = random.Random(seed)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    for old in DOC_DIR.glob("*.txt"):
        try:
            old.unlink()
        except OSError:
            pass  # some mounts disallow unlink; filenames are deterministic so we overwrite

    types = (["intake_form"] * 8 + ["discharge_summary"] * 9 +
             ["lab_report"] * 7 + ["physician_note"] * 8)[:n]
    rng.shuffle(types)

    gold = []
    for i, dt in enumerate(types, 1):
        t = _make_truth(rng, dt, i)
        # ~30% narrative, biased toward notes and discharge summaries where prose is realistic
        narrative = rng.random() < (0.45 if dt in ("physician_note", "discharge_summary") else 0.12)
        t["_style"] = "narrative" if narrative else "structured"
        body = _render_narrative(rng, t) if narrative else _render(rng, t)
        (DOC_DIR / f"{t['doc_id']}.txt").write_text(body, encoding="utf-8")
        gold.append(t)
    GOLD_PATH.write_text(json.dumps(gold, indent=2), encoding="utf-8")
    return gold


if __name__ == "__main__":
    g = build()
    print(f"wrote {len(g)} documents -> {DOC_DIR}")
    print(f"wrote gold labels     -> {GOLD_PATH}")
