"""Uji temuan, prioritas transparan, dan batasan klaim assurance."""
import unittest

from helpers import analyze, row, sample_raw, factors
from modules.config import RiskConfig, FINDING_LABEL
from modules.pipeline import run_pipeline
from modules.risk_engine import evidence_state, priority_matrix, priority_rule_table, quality_overview


def ftypes(a, rn=None):
    f = a.findings
    return set(f["finding_type"]) if rn is None else set(f[f["row_number"] == rn]["finding_type"])


class TestFindings(unittest.TestCase):
    def test_clean_row_only_has_no_findings_other_than_none(self):
        a = analyze(row())
        self.assertEqual(len(a.findings), 0)

    def test_each_required_finding_type_is_produced(self):
        a = analyze(
            row(transaction_id="A1", supplier_id="S1", activity_quantity=""),                       # missing required
            row(transaction_id="A2", supplier_id="S2", activity_unit="pcs"),                        # unit mismatch
            row(transaction_id="A3", supplier_id="S3", item_category="Tidak Ada"),                  # missing factor
            row(transaction_id="A4", supplier_id="S4", evidence_status="missing", evidence_reference=""),  # evidence missing
            row(transaction_id="A5", supplier_id="S5", data_method="spend_based"),                  # estimation
            row(transaction_id="A6", supplier_id="S6", reporting_period="2024"),                    # inconsistent period
            row(transaction_id="A7", supplier_id="S7"), row(transaction_id="A7", supplier_id="S7"),  # duplicate
            row(transaction_id="A8", supplier_id="S8", item_category="Bahan Kimia Pembersih", activity_unit="L"),  # factor w/o source
        )
        for t in ("missing_required_field", "unit_mismatch", "missing_factor_or_source", "evidence_missing",
                  "estimation_method_used", "inconsistent_reporting_period", "duplicate_transaction"):
            self.assertIn(t, ftypes(a), t)

    def test_every_finding_has_severity_reason_transaction_recommendation(self):
        a = run_pipeline(sample_raw(), factors())
        f = a.findings
        self.assertGreater(len(f), 50)
        for col in ("severity", "reason", "transaction_id", "recommendation", "priority_reason", "priority"):
            self.assertTrue((f[col].astype(str).str.len() > 0).all(), col)
        self.assertTrue(set(f["severity"]) <= {"Tinggi", "Sedang", "Rendah"})
        self.assertTrue(set(f["finding_type"]) <= set(FINDING_LABEL))

    def test_priority_reason_explains_materiality_and_weakness(self):
        a = run_pipeline(sample_raw(), factors())
        top = a.findings.iloc[0]
        self.assertIn("materialitas", top["priority_reason"])
        self.assertIn("kelemahan data", top["priority_reason"])


class TestPriorityRules(unittest.TestCase):
    def test_matrix(self):
        exp = {("Tinggi", "Tinggi"): "Tinggi", ("Tinggi", "Sedang"): "Tinggi", ("Tinggi", "Rendah"): "Sedang",
               ("Sedang", "Tinggi"): "Sedang", ("Sedang", "Sedang"): "Sedang", ("Sedang", "Rendah"): "Sedang",
               ("Rendah", "Tinggi"): "Sedang", ("Rendah", "Sedang"): "Rutin", ("Rendah", "Rendah"): "Rutin"}
        for (m, s), p in exp.items():
            self.assertEqual(priority_matrix(m, s), p, (m, s))
        self.assertEqual(priority_rule_table(RiskConfig()).shape, (3, 4))

    def test_thresholds_are_configurable(self):
        rows = [row(transaction_id=f"T{i}", supplier_id=f"S{i}", activity_quantity=str(q), evidence_status="missing", evidence_reference="")
                for i, q in enumerate([1000, 1000, 1000, 1000])]  # masing-masing 25% dari total
        hi = analyze(*rows, cfg=RiskConfig(high_share=0.20, medium_share=0.10)).findings
        self.assertTrue((hi["priority"] == "Tinggi").all())
        lo = analyze(*rows, cfg=RiskConfig(high_share=0.90, medium_share=0.50)).findings
        self.assertTrue((lo["priority"] == "Sedang").all())  # materialitas Rendah + severity Tinggi -> Sedang

    def test_invalid_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            RiskConfig(high_share=0.01, medium_share=0.05).validate()

    def test_large_emission_weak_evidence_is_high_priority(self):
        a = analyze(row(transaction_id="BIG", supplier_id="B", activity_quantity="100000", evidence_status="missing", evidence_reference=""),
                    row(transaction_id="S1", supplier_id="S1", activity_quantity="10"), row(transaction_id="S2", supplier_id="S2", activity_quantity="10"))
        big = a.findings[(a.findings["transaction_id"] == "BIG") & (a.findings["finding_type"] == "evidence_missing")]
        self.assertEqual(big.iloc[0]["priority"], "Tinggi")

    def test_low_emission_minor_gap_is_routine(self):
        a = analyze(row(transaction_id="BIG", supplier_id="B", activity_quantity="100000"), row(transaction_id="SMALL", supplier_id="SM", activity_quantity="1", data_method="spend_based", purchase_amount="1000"))
        sm = a.findings[a.findings["transaction_id"] == "SMALL"]
        self.assertTrue((sm["priority"] == "Rutin").all())


class TestNoAssuranceClaims(unittest.TestCase):
    def test_evidence_never_verified(self):
        for status in ("provided", "partial", "requested", "missing", "verified", ""):
            code, label, ok = evidence_state({"evidence_status": status, "evidence_reference": "X.pdf", "evidence_file_sha256": "abc"})
            self.assertNotIn("terverifikasi", label.lower().replace("belum diverifikasi", ""))
            self.assertNotEqual(code, "verified")

    def test_attached_document_is_still_unverified(self):
        code, label, ok = evidence_state({"evidence_status": "provided", "evidence_reference": "a.pdf", "evidence_file_sha256": "ff"})
        self.assertIn("belum diverifikasi", label)

    def test_provided_without_reference_is_not_recorded(self):
        code, label, ok = evidence_state({"evidence_status": "provided", "evidence_reference": "", "evidence_file_sha256": ""})
        self.assertFalse(ok)

    def test_quality_has_dimensions_and_no_composite_score(self):
        a = run_pipeline(sample_raw(), factors())
        cols = " ".join(a.quality.columns).lower()
        self.assertNotIn("score", cols)
        self.assertNotIn("skor", cols)
        self.assertEqual(list(quality_overview(a.quality)["Dimensi"]),
                         ["Kelengkapan", "Keterlacakan", "Relevansi", "Konsistensi", "Ketidakpastian"])

    def test_successful_calculation_does_not_imply_good_traceability(self):
        a = analyze(row(evidence_status="missing", evidence_reference=""))
        q = a.quality.iloc[0]
        self.assertEqual(a.data.iloc[0]["status"], "Dihitung")
        self.assertEqual(q["Keterlacakan_status"], "Lemah")


if __name__ == "__main__":
    unittest.main()
