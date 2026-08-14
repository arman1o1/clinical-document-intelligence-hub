"""Test suite. Runs with no API key.

The most important thing here is `TestLLMPath`. The Anthropic extractor is the
primary arm of this system and it cannot be exercised in CI without a key, which
means the code most likely to be demoed is the code least likely to be tested.
So we drive the real `Extractor.extract()` pipeline with a canned payload shaped
exactly like a Claude tool-use response, and separately assert that the tool
schema we send is valid JSON Schema. Between them, everything except the network
call is covered.

    python -m pytest tests/ -q          (or: python tests/test_pipeline.py)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cdi.extract import (ALL_FIELDS, AnthropicExtractor, BaselineExtractor,  # noqa: E402
                         Extractor, build_tool_schema)
from cdi.ingest import load_document  # noqa: E402
from cdi.reason import evaluate  # noqa: E402
from cdi.schema import FieldStatus  # noqa: E402
from cdi.verify import adjudicate, presence_score  # noqa: E402

DEMO = ROOT / "data" / "demo" / "DEMO_discharge_summary.txt"
DOC = DEMO.read_text(encoding="utf-8")


def cell(value, evidence):
    return {"value": value, "evidence": evidence}


class FakeClaude(Extractor):
    """Returns a payload in the exact shape Claude's tool_use block produces."""
    name = "fake"

    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.calls = []

    def raw(self, text, sample_idx=0):
        self.calls.append(sample_idx)
        out = {
            "document_type": "discharge_summary",
            "patient_name": cell("Margaret Ellison", "Patient Name : Margaret Ellison"),
            "age": cell(71, "Age / Sex    : 71 / F"),
            "sex": cell("F", "Age / Sex    : 71 / F"),
            "mrn": cell("MRN-408815", "MRN          : MRN-408815"),
            "encounter_date": cell("2026-08-11", "Date         : 2026-08-11"),
            "chief_complaint": cell("shortness of breath on exertion with ankle swelling",
                                    "Presenting complaint - shortness of breath on exertion with ankle swelling."),
            "smoking_status": cell(None, None),
            "discharge_disposition": cell("discharged home", "Disposition: discharged home."),
            "follow_up_days": cell(None, "No follow-up appointment arranged."),
            "diagnoses": cell(["Congestive Heart Failure", "Type 2 Diabetes Mellitus",
                               "Chronic Kidney Disease Stage 3"],
                              "1. Congestive Heart Failure\n2. Type 2 Diabetes Mellitus\n3. Chronic Kidney Disease Stage 3"),
            "allergies": cell(["Penicillin"], "Known allergies:\n  Penicillin - reaction: rash"),
            "medications": cell(
                [{"name": "Metformin", "dose": "1000 mg", "frequency": "BD"},
                 {"name": "Amoxicillin", "dose": "500 mg", "frequency": "TDS"}],
                "- Metformin 1000 mg BD\n  - Amoxicillin 500 mg TDS"),
            "labs": cell([{"name": "Potassium", "value": 5.9, "unit": "mmol/L"},
                          {"name": "eGFR", "value": 24, "unit": "mL/min/1.73m2"}],
                         "Potassium .......... 5.9 mmol/L\n  eGFR .......... 24 mL/min/1.73m2"),
            "bp_systolic": cell(186, "B/P 186 over 104 mmHg"),
            "bp_diastolic": cell(104, "B/P 186 over 104 mmHg"),
            "heart_rate": cell(118, "Pulse rate ...... 118 bpm"),
            "temp_f": cell(99.1, "Temp: 99.1 F"),
            "spo2": cell(91, "SpO2 ...... 91%"),
        }
        out.update(self.overrides.get(sample_idx, self.overrides.get("all", {})))
        return out


class TestToolSchema(unittest.TestCase):
    def test_schema_is_valid_json_schema(self):
        import jsonschema
        schema = build_tool_schema()
        jsonschema.Draft7Validator.check_schema(schema)

    def test_schema_covers_every_scored_field(self):
        props = build_tool_schema()["properties"]
        for f in ALL_FIELDS:
            self.assertIn(f, props, f"{f} missing from the tool schema")
            self.assertEqual(sorted(props[f]["properties"]), ["evidence", "value"])

    def test_every_field_requires_evidence(self):
        """A value without a citation must be structurally impossible."""
        for f, spec in build_tool_schema()["properties"].items():
            if f == "document_type":
                continue
            self.assertIn("evidence", spec["required"], f"{f} can return a value uncited")

    def test_anthropic_arm_fails_only_on_credentials(self):
        """Our own code must be sound; the only thing missing should be a key.

        The SDK resolves auth lazily, so construction succeeds without a key and
        the failure appears on the first request. Asserting that the error is an
        auth error -- and not a TypeError from a malformed tool schema or a bad
        model string -- is what makes this arm safe to demo on a machine that has
        never run it. Anything other than an auth failure here is our bug.
        """
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("anthropic SDK not installed")

        ex = AnthropicExtractor()                       # must not raise
        self.assertEqual(ex.tool["name"], "record_extraction")
        self.assertTrue(ex.model, "no model string configured")

        import os
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.skipTest("a real key is present; live behaviour is not asserted here")
        with self.assertRaises(Exception) as ctx:
            ex.raw("Patient Name : Test Person")
        msg = f"{ctx.exception}".lower()
        self.assertTrue(
            any(t in msg for t in ("api_key", "authentication", "auth_token", "credentials")),
            f"expected an auth failure, got: {ctx.exception!r}")


class TestLLMPath(unittest.TestCase):
    """The Anthropic arm's plumbing, exercised without the network."""

    def test_canned_response_produces_a_usable_record(self):
        rec = FakeClaude().extract("DEMO", DOC)
        self.assertEqual(rec.document_type.value, "discharge_summary")
        self.assertEqual(rec.field("patient_name").value, "Margaret Ellison")
        self.assertEqual(rec.field("bp_systolic").value, 186)
        self.assertTrue(rec.field("patient_name").usable)
        self.assertEqual(rec.field("smoking_status").status, FieldStatus.NOT_PRESENT)

    def test_reasoning_layer_consumes_the_llm_record(self):
        rec = FakeClaude().extract("DEMO", DOC)
        flags, urgency, queue = evaluate(rec)
        ids = {f.rule_id for f in flags}
        self.assertIn("SAFETY.allergy_conflict", ids)   # amoxicillin vs penicillin allergy
        self.assertIn("MED.metformin_egfr", ids)        # metformin at eGFR 24
        self.assertIn("VITAL.hypertensive_crisis", ids)
        self.assertEqual(urgency, 100)
        self.assertEqual(queue.value, "IMMEDIATE CLINICAL REVIEW")

    def test_hallucinated_value_is_withheld(self):
        """A real quote paired with an invented name must not reach the card."""
        rec = FakeClaude({"all": {"patient_name": cell(
            "Jonathan Fairweather", "Patient Name : Jonathan Fairweather")}}).extract("DEMO", DOC)
        self.assertEqual(rec.field("patient_name").status, FieldStatus.UNGROUNDED)
        self.assertIn("patient_name", rec.review_queue())

    def test_invented_list_entry_is_dropped_and_flagged(self):
        rec = FakeClaude({"all": {"medications": cell(
            [{"name": "Metformin", "dose": "1000 mg", "frequency": "BD"},
             {"name": "Clopidogrel", "dose": "75 mg", "frequency": "OD"}],
            "- Metformin 1000 mg BD")}}).extract("DEMO", DOC)
        med = rec.field("medications")
        self.assertEqual(med.dropped_items, 1)
        self.assertNotIn("clopidogrel",
                         " ".join(m["name"].lower() for m in med.value))
        self.assertEqual(med.status, FieldStatus.ABSTAINED)

    def test_k_greater_than_one_requests_k_samples(self):
        fake = FakeClaude()
        fake.extract("DEMO", DOC, k=3)
        self.assertEqual(fake.calls, [0, 1, 2])

    def test_disagreement_across_samples_lowers_confidence(self):
        agree = FakeClaude().extract("DEMO", DOC, k=3).field("heart_rate")
        disagree = FakeClaude({
            1: {"heart_rate": cell(112, "Pulse rate ...... 118 bpm")},
            2: {"heart_rate": cell(121, "Pulse rate ...... 118 bpm")},
        }).extract("DEMO", DOC, k=3).field("heart_rate")
        self.assertEqual(agree.agreement, 1.0)
        self.assertLess(disagree.agreement, 1.0)
        self.assertLess(disagree.confidence, agree.confidence)

    def test_malformed_backend_response_does_not_crash(self):
        class Broken(FakeClaude):
            def raw(self, text, sample_idx=0):
                return {}
        rec = Broken().extract("DEMO", DOC)
        self.assertEqual(rec.document_type.value, "unknown")
        self.assertFalse(rec.field("patient_name").usable)


class TestVerification(unittest.TestCase):
    def test_converted_temperature_is_accepted(self):
        doc = "temperature 37.6 degrees Celsius"
        self.assertEqual(presence_score(99.7, doc), 1.0)
        self.assertEqual(adjudicate(99.7, doc, doc).status, FieldStatus.EXTRACTED)

    def test_spelled_out_number_is_accepted(self):
        doc = "the pulse one hundred and twenty-two and regular"
        self.assertEqual(adjudicate(122, doc, doc).status, FieldStatus.EXTRACTED)

    def test_fabricated_entity_is_rejected(self):
        self.assertEqual(adjudicate("Jane Doe", "Patient Name : Jane Doe", DOC).status,
                         FieldStatus.UNGROUNDED)

    def test_negation_supports_an_empty_list(self):
        doc = "Allergies: No known drug allergies."
        self.assertEqual(adjudicate([], "No known drug allergies", doc).status,
                         FieldStatus.EXTRACTED)

    def test_absent_section_is_not_a_fabrication(self):
        self.assertEqual(adjudicate([], None, DOC).status, FieldStatus.NOT_PRESENT)


class TestIngestion(unittest.TestCase):
    def test_text_pdf_and_ocr_routes(self):
        cases = [("DEMO_discharge_summary.txt", "text", False),
                 ("DEMO_discharge_summary.pdf", "pdf", False),
                 ("DEMO_discharge_summary_scanned.pdf", "pdf-scanned", True),
                 ("DEMO_discharge_summary_scan.png", "image", True)]
        for name, kind, ocr in cases:
            path = DEMO.parent / name
            if not path.exists():
                self.skipTest(f"fixture {name} not generated")
            ing = load_document(path)
            self.assertEqual(ing.source_kind, kind, name)
            self.assertEqual(ing.ocr_used, ocr, name)
            self.assertIn("Ellison", ing.text, name)

    def test_scanned_pdf_is_not_returned_empty(self):
        path = DEMO.parent / "DEMO_discharge_summary_scanned.pdf"
        if not path.exists():
            self.skipTest("fixture not generated")
        self.assertGreater(len(load_document(path).text), 400)

    def test_supported_text_type_is_accepted(self):
        self.assertEqual(load_document(ROOT / "requirements.txt").source_kind, "text")

    def test_unsupported_type_is_rejected_clearly(self):
        with self.assertRaises(ValueError) as ctx:
            load_document(ROOT / "run_eval.py")          # .py is not a document
        self.assertIn("Unsupported file type", str(ctx.exception))

    def test_missing_file_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            load_document(ROOT / "does_not_exist.pdf")

    def test_ocr_noise_does_not_crash_the_extractor(self):
        path = DEMO.parent / "DEMO_discharge_summary_scan.png"
        if not path.exists():
            self.skipTest("fixture not generated")
        rec = BaselineExtractor().extract("scan", load_document(path).text)
        evaluate(rec)   # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
