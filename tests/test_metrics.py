"""Metrik keberhasilan internal (brief bagian 11) -- diukur pada dataset sintetis.

Catatan keterbatasan: anomali ditanam oleh tim sendiri sehingga angka deteksi bersifat optimistis;
uji ini memastikan tidak ada regresi, bukan klaim performa pada data nyata.
"""
import csv
import unittest

import pandas as pd

from helpers import DATA, factors, sample_raw
from modules.calculator import STATUS_EXCLUDED, STATUS_OK, STATUS_REJECTED
from modules.pipeline import run_pipeline
from modules.reporting import audit_trail_table

UNIT = {"kg": ("m", 1.0), "ton": ("m", 1000.0), "g": ("m", 0.001), "l": ("v", 1.0), "m3": ("v", 1000.0),
        "unit": ("c", 1.0), "pcs": ("c", 1.0)}


def manual_expected(r: dict, fac: list[dict]):
    """Implementasi 'hitung manual' independen (tanpa pandas/Decimal). None = harus ditolak."""
    m, cat = r["data_method"], r["item_category"]
    if m not in ("spend_based", "secondary_activity", "primary_supplier") or not cat:
        return None
    if m == "spend_based":
        if r["currency"] != "IDR" or r["purchase_amount"] in ("",) or float(r["purchase_amount"]) < 0:
            return None
        fs = [f for f in fac if f["item_category"] == cat and f["factor_unit"].endswith("/IDR")]
        return float(r["purchase_amount"]) * float(fs[0]["factor_value"]) if fs else None
    q, u = r["activity_quantity"], r["activity_unit"].lower()
    try:
        qv = float(q)
    except ValueError:
        return None
    if qv <= 0 or u not in UNIT:
        return None
    if m == "primary_supplier" and r["supplier_emission_factor"]:
        return qv * float(r["supplier_emission_factor"])
    fs = [f for f in fac if f["item_category"] == cat and not f["factor_unit"].endswith("/IDR")]
    if not fs:
        return None
    den = fs[0]["factor_unit"].split("/")[1].lower()
    if den not in UNIT or UNIT[den][0] != UNIT[u][0]:
        return None
    return qv * UNIT[u][1] / UNIT[den][1] * float(fs[0]["factor_value"])


class TestMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = run_pipeline(sample_raw(), factors())
        with open(DATA / "sample_transactions.csv", encoding="utf-8") as f:
            cls.raw_rows = list(csv.DictReader(f))
        with open(DATA / "emission_factors.csv", encoding="utf-8") as f:
            cls.fac = list(csv.DictReader(f))

    def test_calculation_accuracy_matches_manual_100pct(self):
        d = self.a.data
        checked = mismatches = 0
        for (_, r), raw in zip(d.iterrows(), self.raw_rows):
            if r["status"] == STATUS_EXCLUDED:
                continue
            exp = manual_expected(raw, self.fac)
            if exp is None:
                self.assertEqual(r["status"], STATUS_REJECTED, raw["transaction_id"])
            else:
                self.assertEqual(r["status"], STATUS_OK, raw["transaction_id"])
                if abs(r["emissions_kg"] - exp) > 1e-6 * max(1, abs(exp)):
                    mismatches += 1
            checked += 1
        self.assertEqual(mismatches, 0)
        self.assertEqual(checked, 95)

    def test_total_equals_sum_of_rows(self):
        d = self.a.data
        self.assertAlmostEqual(self.a.summary["total_emissions_kg"], d.loc[d["status"] == STATUS_OK, "emissions_kg"].sum(), places=6)

    def test_anomaly_detection_rate_at_least_90pct(self):
        key = pd.read_csv(DATA / "sample_anomaly_key.csv")
        found = set(zip(self.a.findings["transaction_id"], self.a.findings["finding_type"]))
        det = [(t, ty) in found for t, ty in zip(key["transaction_id"], key["anomaly_type"])]
        rate = sum(det) / len(det)
        missed = key[[not x for x in det]]
        self.assertGreaterEqual(rate, 0.90, f"terlewat:\n{missed}")

    def test_every_anomaly_type_has_full_recall(self):
        key = pd.read_csv(DATA / "sample_anomaly_key.csv")
        found = set(zip(self.a.findings["transaction_id"], self.a.findings["finding_type"]))
        for ty, g in key.groupby("anomaly_type"):
            rec = sum((t, ty) in found for t in g["transaction_id"]) / len(g)
            self.assertEqual(rec, 1.0, ty)

    def test_traceability_chain_at_least_95pct(self):
        at = audit_trail_table(self.a)
        ok = at[at["status_hitung"] == STATUS_OK]
        need = ["faktor_id", "faktor_nilai", "faktor_satuan", "kelas_data", "input_aktivitas", "rumus", "versi_metode"]
        complete = ok[need].notna().all(axis=1) & (ok[need].astype(str) != "").all(axis=1)
        # rantai juga harus konsisten secara aritmetika: kuantitas x faktor = emisi
        recomputed = (ok["kuantitas_terkonversi"] * ok["faktor_nilai"]).sub(ok["emisi_kg_co2e"]).abs() < 1e-3
        rate = (complete & recomputed).mean()
        self.assertGreaterEqual(rate, 0.95)
        self.assertEqual(len(ok), 83)

    def test_sample_data_contains_all_required_variations(self):
        d = self.a.data
        self.assertGreater((d["dup_kind"] != "").sum(), 0)
        for t in ("missing_required_field", "invalid_value", "duplicate_transaction", "unit_mismatch",
                  "missing_factor_or_source", "evidence_missing", "estimation_method_used", "inconsistent_reporting_period"):
            self.assertIn(t, set(self.a.findings["finding_type"]))
        self.assertEqual(set(d["data_method"]), {"primary_supplier", "secondary_activity", "spend_based"})


if __name__ == "__main__":
    unittest.main()
