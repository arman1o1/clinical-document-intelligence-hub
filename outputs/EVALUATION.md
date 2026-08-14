# Evaluation report - Clinical Document Intelligence Hub

Generated 2026-08-14. Corpus: 32 synthetic clinical documents (17 structured forms, 15 free-prose narratives) with exact gold labels.

## 1. Extraction quality

| Arm | Silent error rate | Precision of surfaced fields | Abstention | Fields surfaced | Present fields missed |
|---|---|---|---|---|---|
| `baseline` | 14.0% | 86.0% | 0.0% | 293 | 177 |

*Silent error rate* = of the fields the system actually showed a human, the fraction that were wrong. This is the headline rather than plain accuracy because a withheld field costs a reviewer thirty seconds while a confidently wrong field can propagate into a care decision.

## 2. Verification layer - fault injection

The regex baseline cannot fabricate, so running it shows the verification layer doing nothing. To measure the layer directly we inject synthetic hallucinations at a known rate: a genuine, correctly-copied evidence quote paired with a subtly wrong value - the failure mode that matters, because the citation looks perfect.

| Metric | Value |
|---|---|
| Faults injected | 52 |
| Faults caught (withheld from the summary card) | 50 |
| **Catch rate** | **96.2%** |
| Clean fields incorrectly blocked | 0 / 143 |
| **False block rate** | **0.0%** |

Residual misses are numeric corruptions whose perturbed value coincides with another number elsewhere in the same document. Numerics are deliberately not hard-gated on value presence, because legitimate unit conversion (37.6 C -> 99.7 F) produces a correct value that never appears literally in the text.

## 3. Ingestion fidelity

The same discharge summary, ingested four ways. Plain text is the reference; every other row is scored against it field by field.

| Route | Detected as | Exact | OCR noise, same content | Entries dropped | **Invented** | Withheld | Flags | Urgency |
|---|---|---|---|---|---|---|---|---|
| plain text | `text` | 16 | 0 | 0 | **0** | 0 | 10 | 100/100 |
| PDF, text layer | `pdf` | 15 | 0 | 0 | **0** | 1 | 10 | 100/100 |
| PDF, scanned (OCR) | `pdf-scanned` | 12 | 0 | 1 | **0** | 3 | 7 | 100/100 |
| image (OCR) | `image` | 10 | 1 | 1 | **0** | 4 | 7 | 100/100 |

**Invented entities across all four routes: 0.** That is the column that would hurt a patient, and it is the one that stays at zero.

What OCR costs is *recall*. On the scanned routes three lab rows are lost — `HbA1c` transcribes as `HbAlc`, and the row is dropped rather than guessed at — and the risk-flag count falls from 10 to 7 as a direct consequence. That is a real and serious loss: a flag that never fires cannot be reviewed. But nothing is fabricated to fill the gap.

Scoring those dropped rows as errors would have made OCR look like it invents lab results. It does not, and engineering against the wrong failure mode is how you end up hardening the part that was already safe.

A scanned PDF is also *detected* as one rather than passed through as an empty document — the failure mode that would otherwise yield a confident, entirely blank patient record.

## 4. Per-field detail - `baseline`

 (verification ON)

| Field | Surfaced | Correct | Wrong | Withheld | Accuracy on surfaced |
|---|---|---|---|---|---|
| `age` | 17 | 17 | 0 | 0 | 100.0% |
| `allergies` | 32 | 25 | 7 | 0 | 78.1% |
| `bp_diastolic` | 12 | 12 | 0 | 0 | 100.0% |
| `bp_systolic` | 12 | 12 | 0 | 0 | 100.0% |
| `chief_complaint` | 12 | 12 | 0 | 0 | 100.0% |
| `diagnoses` | 32 | 21 | 11 | 0 | 65.6% |
| `discharge_disposition` | 1 | 1 | 0 | 0 | 100.0% |
| `encounter_date` | 17 | 17 | 0 | 0 | 100.0% |
| `follow_up_days` | 1 | 1 | 0 | 0 | 100.0% |
| `heart_rate` | 12 | 12 | 0 | 0 | 100.0% |
| `labs` | 32 | 22 | 10 | 0 | 68.8% |
| `medications` | 32 | 19 | 13 | 0 | 59.4% |
| `mrn` | 17 | 17 | 0 | 0 | 100.0% |
| `patient_name` | 17 | 17 | 0 | 0 | 100.0% |
| `sex` | 17 | 17 | 0 | 0 | 100.0% |
| `smoking_status` | 11 | 11 | 0 | 0 | 100.0% |
| `spo2` | 12 | 12 | 0 | 0 | 100.0% |
| `temp_f` | 7 | 7 | 0 | 0 | 100.0% |

## Multi-value fields (micro P/R/F1)

| Field | Precision | Recall | F1 | FP | FN |
|---|---|---|---|---|---|
| `allergies` | 0.781 | 0.781 | 0.781 | 0 | 10 |
| `diagnoses` | 0.656 | 0.656 | 0.656 | 0 | 21 |
| `labs` | 0.688 | 0.688 | 0.688 | 0 | 44 |
| `medications` | 0.594 | 0.594 | 0.594 | 0 | 27 |
