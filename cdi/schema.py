"""Clinical extraction schema.

Design note: every extracted field carries its own provenance (an evidence
quote lifted from the source document) and its own confidence. This is
deliberate -- in a clinical setting an unattributed value is not actionable,
because the reviewer cannot check it without re-reading the whole document.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    INTAKE = "intake_form"
    DISCHARGE = "discharge_summary"
    LAB = "lab_report"
    NOTE = "physician_note"
    UNKNOWN = "unknown"


class FieldStatus(str, Enum):
    EXTRACTED = "extracted"           # value found, evidence verified
    ABSTAINED = "abstained"           # below confidence threshold -> human review
    NOT_PRESENT = "not_present"       # model asserts field absent from document
    UNGROUNDED = "ungrounded"         # value returned but evidence not in source


class ExtractedField(BaseModel):
    """A single extracted value plus everything needed to audit it."""
    value: Any = None
    evidence: Optional[str] = None
    confidence: float = 0.0
    status: FieldStatus = FieldStatus.NOT_PRESENT
    agreement: Optional[float] = None  # self-consistency across samples, if k>1
    dropped_items: int = 0             # list entries removed as unsupported by the document

    @property
    def usable(self) -> bool:
        return self.status is FieldStatus.EXTRACTED

    def display(self) -> str:
        if self.status is FieldStatus.EXTRACTED:
            return str(self.value)
        if self.status is FieldStatus.ABSTAINED:
            return "NEEDS REVIEW (low confidence)"
        if self.status is FieldStatus.UNGROUNDED:
            return "NEEDS REVIEW (unverified)"
        return "not documented"


class Medication(BaseModel):
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None


class LabResult(BaseModel):
    name: str
    value: Optional[float] = None
    unit: Optional[str] = None


class Vitals(BaseModel):
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    heart_rate: Optional[int] = None
    temp_f: Optional[float] = None
    spo2: Optional[int] = None


# Scalar fields the extractor is scored on. Ordering here drives the eval report
# and the summary-card layout, so keep it clinically sensible.
SCALAR_FIELDS = [
    "patient_name",
    "age",
    "sex",
    "mrn",
    "encounter_date",
    "chief_complaint",
    "smoking_status",
    "discharge_disposition",
    "follow_up_days",
]

LIST_FIELDS = ["diagnoses", "allergies", "medications", "labs"]

VITAL_FIELDS = ["bp_systolic", "bp_diastolic", "heart_rate", "temp_f", "spo2"]


class PatientRecord(BaseModel):
    """The structured output of the extraction stage."""
    doc_id: str
    document_type: DocumentType = DocumentType.UNKNOWN

    patient_name: ExtractedField = Field(default_factory=ExtractedField)
    age: ExtractedField = Field(default_factory=ExtractedField)
    sex: ExtractedField = Field(default_factory=ExtractedField)
    mrn: ExtractedField = Field(default_factory=ExtractedField)
    encounter_date: ExtractedField = Field(default_factory=ExtractedField)
    chief_complaint: ExtractedField = Field(default_factory=ExtractedField)
    smoking_status: ExtractedField = Field(default_factory=ExtractedField)
    discharge_disposition: ExtractedField = Field(default_factory=ExtractedField)
    follow_up_days: ExtractedField = Field(default_factory=ExtractedField)

    diagnoses: ExtractedField = Field(default_factory=ExtractedField)
    allergies: ExtractedField = Field(default_factory=ExtractedField)
    medications: ExtractedField = Field(default_factory=ExtractedField)
    labs: ExtractedField = Field(default_factory=ExtractedField)

    vitals: dict[str, ExtractedField] = Field(default_factory=dict)

    def field(self, name: str) -> ExtractedField:
        if name in VITAL_FIELDS:
            return self.vitals.get(name, ExtractedField())
        return getattr(self, name, ExtractedField())

    def review_queue(self) -> list[str]:
        """Fields a human must look at before this record is trusted."""
        out = []
        for n in SCALAR_FIELDS + LIST_FIELDS:
            if self.field(n).status in (FieldStatus.ABSTAINED, FieldStatus.UNGROUNDED):
                out.append(n)
        for n in VITAL_FIELDS:
            if self.field(n).status in (FieldStatus.ABSTAINED, FieldStatus.UNGROUNDED):
                out.append(n)
        return out
