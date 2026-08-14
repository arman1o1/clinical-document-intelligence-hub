# Extraction evaluation - `baseline` arm

Corpus: 32 synthetic clinical documents with exact gold labels.

## Headline

| Metric | Verification ON (shipped) | Verification OFF |
|---|---|---|
| Silent error rate (wrong values shown to a human) | **14.0%** | 14.0% |
| Precision of surfaced fields | **86.0%** | 86.0% |
| Abstention rate (routed to human) | 0.0% | 0.0% |
| Fields surfaced | 293 | 293 |
| Document-type accuracy | 62.5% | - |

## Per-field (verification ON)

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
