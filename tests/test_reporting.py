"""Uji laporan & ekspor: disclaimer wajib, tidak ada klaim 'terverifikasi', PDF valid."""
import re
import unittest
from datetime import datetime

from helpers import factors, sample_raw
from modules.config import DISCLAIMER
from modules.pipeline import run_pipeline
from modules.reporting import (
    audit_trail_table, build_report_blocks, readiness_indicators, report_markdown, report_pdf, to_csv_bytes,
)


class TestReporting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = run_pipeline(sample_raw(), factors())
        cls.blocks = build_report_blocks(cls.a, generated_at=datetime(2026, 1, 1, 9, 0))
        cls.md = report_markdown(cls.blocks)

    def test_disclaimer_present_top_and_bottom(self):
        self.assertGreaterEqual(self.md.count(DISCLAIMER), 2)

    def test_required_sections(self):
        for h in ("Ringkasan emisi", "Metode dan sumber faktor emisi", "Status bukti", "Daftar temuan",
                  "Batasan data", "Tindakan perbaikan yang disarankan"):
            self.assertIn(h, self.md)

    def test_no_verified_claims(self):
        self.assertIsNone(re.search(r"verified emissions|emisi terverifikasi|telah diverifikasi", self.md, re.I))
        self.assertIn("belum diverifikasi", self.md)
        self.assertIn("DUMMY", self.md)

    def test_report_is_deterministic(self):
        again = report_markdown(build_report_blocks(self.a, generated_at=datetime(2026, 1, 1, 9, 0)))
        self.assertEqual(self.md, again)

    def test_pdf_valid(self):
        pdf = report_pdf(self.blocks)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 5000)

    def test_csv_exports(self):
        for df in (audit_trail_table(self.a), self.a.findings, self.a.quality):
            b = to_csv_bytes(df)
            self.assertGreater(len(b), 100)
        at = audit_trail_table(self.a)
        self.assertEqual(len(at), 100)
        for col in ("faktor_id", "faktor_sumber", "rumus", "asumsi", "status_bukti", "referensi_bukti"):
            self.assertIn(col, at.columns)

    def test_readiness_indicators_not_a_score(self):
        r = readiness_indicators(self.a)
        self.assertEqual(list(r.columns), ["Indikator", "Nilai", "Status", "Catatan"])
        self.assertTrue(set(r["Status"]) <= {"Terpenuhi", "Sebagian", "Belum"})
        # faktor dummy tidak boleh dihitung sebagai 'bersumber'
        row = r[r["Indikator"].str.startswith("Faktor emisi dengan sumber")].iloc[0]
        self.assertNotEqual(row["Status"], "Terpenuhi")


if __name__ == "__main__":
    unittest.main()
