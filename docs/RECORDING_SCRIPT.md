# 3-minute demo recording script

The brief caps the recording at **3 minutes**. That is tight — it is roughly 420 spoken words. This script is timed to ~2:50, which leaves margin.

## Before you hit record

```bash
cd clinical-doc-intelligence
source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...      # so you can show the LLM arm

# SMOKE TEST FIRST — the LLM arm has never run on your machine. Do not discover
# a broken key or model string mid-recording. This must print a summary card:
python -m cdi.summarize data/demo/DEMO_discharge_summary.txt --arm anthropic

python run_eval.py                       # regenerates outputs/ so the Evaluation tab is populated
streamlit run app.py
```

If the smoke test errors, record with the baseline arm instead — the demo document is structured, so the extraction looks identical on screen; you lose nothing but the backend label. Fix the key afterwards.

Then:

- Browser at **100% zoom**, window maximised, no other tabs visible.
- The app opens on `[demo] DEMO_discharge_summary` with the backend set to `anthropic` (it prefers the LLM arm when a key is present). Leave it there.
- Close the sidebar **after** you've shown the backend selector.
- Have a terminal on a second desktop/space for the closing shot.

Record at 1080p. OBS, QuickTime, or Loom all fine.

---

## Shot list

### 0:00 – 0:25 · The problem, over the source document

**On screen:** the app, left panel showing the raw discharge summary. Scroll it slowly once.

> "This is a discharge summary — the kind of document clinical and admin staff read by hand to pull out the same handful of facts. There are four traps in this one. It quotes vitals from a previous visit. It lists a family-history condition that isn't the patient's. It names a drug that was discontinued. And it prescribes amoxicillin to a patient with a documented penicillin allergy.
>
> A reviewer under time pressure misses at least one of those."

### 0:25 – 0:55 · Extraction with provenance

**On screen:** move to the right panel. Point at the summary card. Expand **one** `source` expander — the medications or the potassium field.

> "The system extracts eighteen fields. What matters is what's attached to each one: a confidence score, and the exact span of the document it came from. Every field can be checked in one click, without re-reading the page.
>
> That's the design constraint the whole thing is built around. A structured field with no provenance still forces the reviewer back to the source — which is the manual work we claimed to remove."

### 0:55 – 1:25 · What it got right

**On screen:** point at blood pressure, then diagnoses, then medications.

> "Blood pressure reads 186 over 104 — the current reading, not the 138 over 82 from six weeks ago. Diagnoses exclude the family-history atrial fibrillation. Medications exclude the discontinued ibuprofen.
>
> None of that is regex. Those are attribution judgements, and they're the reason there's a language model in the pipeline at all."

### 1:25 – 2:00 · Risk flags and triage

**On screen:** scroll to the Risk flags panel. Let the ten flags land, then point at the two criticals.

> "Then a deterministic rules engine runs over the verified record. Ten flags. Two critical: amoxicillin against a documented penicillin allergy, and metformin at an eGFR of 24, where it's contraindicated.
>
> These rules are not the LLM. Deciding a patient needs escalation is clinical policy, and policy has to be auditable and versionable. Every flag names the rule that fired and the value that tripped it.
>
> Result: routed to immediate clinical review, urgency 100."

### 2:00 – 2:30 · The part I'd want reviewed

**On screen:** switch to the **Evaluation** tab. Let the metric cards render.

> "I'd rather show you the measurement than the happy path. Headline metric is silent error rate — of the fields the system actually showed a human, how many were wrong. Not accuracy, because a withheld field costs thirty seconds and a confidently wrong field can reach a care decision.
>
> To test the verification layer I injected synthetic hallucinations at a known rate: a real, correctly-copied quote paired with a subtly wrong value. It catches 96.2% of them, and it blocked zero of 143 clean fields."

### 2:30 – 2:50 · Reproducibility, and close

**On screen:** cut to the terminal. Run it live:

```bash
python run_eval.py
```

Let the output print.

> "That number is reproducible in one command, with no API key — the evaluation runs against a deterministic control arm. The corpus, the gold labels, the harness and the injection are all in the repo.
>
> Thanks for watching."

---

## Optional swap: the ingestion beat (~20s)

If you'd rather show breadth than the live `run_eval.py` at 2:30, swap the closing terminal shot for this. Pick `[demo] DEMO_discharge_summary_scan.png` from the sidebar — a photographed page, no text layer.

> "Same document, but as a scan. The system detects there's no text layer, routes it through OCR, and warns you that every confidence score below is now measured against a transcription rather than the page.
>
> Notice what happens to the output. The flag count drops from ten to seven, because OCR mangles `HbA1c` and that lab row is dropped. That's a real loss — a flag that never fires can't be reviewed. But look at what it *didn't* do: across all four input routes, text, PDF, scan and image, it invented exactly zero values. It degrades by going quiet, not by making things up."

Don't try to fit both this and the live eval run. Pick one — the video is capped at three minutes and rushing the ending is worse than covering less.

## If something breaks mid-recording

The console renderer produces the same result and never depends on the browser:

```bash
python -m cdi.summarize data/demo/DEMO_discharge_summary.txt
```

Use it as the fallback for the extraction and triage segments. It prints the full summary card, flags, and routing decision.

## Things to avoid

- **Don't narrate the UI** ("now I'll click here"). Narrate the decision the system made.
- **Don't apologise for synthetic data** in the video — it's stated in the README and on the deck. Saying it aloud costs ten seconds and reads as hedging.
- **Don't read the slides.** The deck is a separate deliverable; the video should show the thing running.
- If you fluff a line, stop and re-record that segment rather than talking through it. Segment boundaries above are clean cut points.
