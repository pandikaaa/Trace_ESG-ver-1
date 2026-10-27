"""Uji perhitungan emisi: hasil harus sama persis dengan hitungan manual (kasus deterministik)."""
import unittest
from decimal import Decimal

from helpers import calc, factors, row  # noqa: F401  (helpers menambah path proyek)
from modules.calculator import (
    STATUS_EXCLUDED, STATUS_OK, STATUS_REJECTED, UnitMismatchError, compute_emission, convert_quantity,
    split_factor_unit, load_factors, validate_factors,
)
from modules.config import RiskConfig


class TestComputeEmission(unittest.TestCase):
    def test_brief_example_500kg_x_2(self):
        em, q, u, mult = compute_emission(500, "kg", 2, "kg CO2e/kg")
        self.assertEqual(em, Decimal("1000"))
        self.assertEqual((q, u, mult), (Decimal("500"), "kg", Decimal("1")))

    def test_decimal_exactness(self):
        em, *_ = compute_emission(3, "kg", 0.1, "kg CO2e/kg")  # float biasa: 0.30000000000000004
        self.assertEqual(em, Decimal("0.3"))

    def test_ton_to_kg(self):
        em, q, u, mult = compute_emission(12.5, "ton", 1.1, "kg CO2e/kg")
        self.assertEqual(q, Decimal("12500.0"))
        self.assertEqual(em, Decimal("13750.00"))
        self.assertEqual(u, "kg")

    def test_m3_to_litre(self):
        em, q, *_ = compute_emission(2, "m3", 1.6, "kg CO2e/L")
        self.assertEqual(q, Decimal("2000"))
        self.assertEqual(em, Decimal("3200.0"))

    def test_incompatible_units_raise(self):
        with self.assertRaises(UnitMismatchError):
            convert_quantity(10, "pcs", "kg")
        with self.assertRaises(UnitMismatchError):
            convert_quantity(10, "box", "kg")
        with self.assertRaises(UnitMismatchError):
            convert_quantity(10, "kg", "IDR")

    def test_split_factor_unit(self):
        self.assertEqual(split_factor_unit("kg CO2e/kg"), ("kg CO2e", "kg"))
        self.assertEqual(split_factor_unit("kg CO2e/IDR"), ("kg CO2e", "IDR"))


class TestCalculateRows(unittest.TestCase):
    def one(self, **over):
        return calc(row(**over)).iloc[0]

    def test_valid_physical_row(self):
        r = self.one()  # 500 kg tepung x 0.9 (dummy) = 450
        self.assertEqual(r["status"], STATUS_OK)
        self.assertAlmostEqual(r["emissions_kg"], 450.0, places=6)
        self.assertEqual(r["factor_id"], "EF-D001")
        self.assertEqual(r["data_class"], "Data aktivitas sekunder")
        self.assertFalse(bool(r["is_estimate"]))
        self.assertTrue(bool(r["trace_chain_complete"]))

    def test_unit_conversion_documented(self):
        r = self.one(activity_quantity="12.5", activity_unit="ton")
        self.assertAlmostEqual(r["emissions_kg"], 12500 * 0.9, places=6)
        self.assertIn("unit_converted", r["reason_codes"])
        self.assertIn("dikonversi", r["assumptions"])

    def test_spend_based_row(self):
        r = self.one(data_method="spend_based", purchase_amount="10000000")  # 1e7 x 0.000075 = 750
        self.assertAlmostEqual(r["emissions_kg"], 750.0, places=6)
        self.assertTrue(bool(r["is_estimate"]))
        self.assertEqual(r["data_class"], "Estimasi berbasis pengeluaran")
        self.assertEqual(r["factor_basis"], "spend")

    def test_unit_mismatch_rejected_no_number(self):
        for unit in ("pcs", "box", "paket"):
            r = self.one(activity_unit=unit)
            self.assertEqual(r["status"], STATUS_REJECTED, unit)
            self.assertTrue(r["emissions_kg"] != r["emissions_kg"], "emisi harus NaN untuk baris ditolak")

    def test_physical_data_never_multiplied_by_spend_factor(self):
        # 'Jasa Konsultan' hanya punya faktor berbasis pengeluaran
        r = self.one(item_category="Jasa Konsultan", data_method="secondary_activity", activity_unit="jam")
        self.assertEqual(r["status"], STATUS_REJECTED)
        self.assertIn("factor_missing", r["reason_codes"])

    def test_missing_factor_category(self):
        r = self.one(item_category="Kategori Tidak Ada")
        self.assertEqual(r["status"], STATUS_REJECTED)
        self.assertIn("factor_missing", r["reason_codes"])

    def test_non_idr_spend_rejected_without_fx(self):
        r = self.one(data_method="spend_based", currency="USD")
        self.assertEqual(r["status"], STATUS_REJECTED)
        self.assertIn("currency_mismatch", r["reason_codes"])

    def test_missing_or_invalid_inputs_rejected(self):
        for over in ({"activity_quantity": ""}, {"activity_quantity": "-5"}, {"activity_quantity": "abc"},
                     {"activity_unit": ""}, {"data_method": ""}, {"data_method": "ngawur"}):
            self.assertEqual(self.one(**over)["status"], STATUS_REJECTED, over)

    def test_primary_with_supplier_factor(self):
        r = self.one(data_method="primary_supplier", supplier_emission_factor="0.78")
        self.assertAlmostEqual(r["emissions_kg"], 390.0, places=6)
        self.assertEqual(r["data_class"], "Data pemasok (primer)")
        self.assertIn("klaim", r["factor_source"])  # jelas ditandai sebagai klaim, bukan verified
        self.assertTrue(r["factor_id"].startswith("SUPPLIER-"))

    def test_primary_without_supplier_factor_falls_back_and_flags(self):
        r = self.one(data_method="primary_supplier", supplier_emission_factor="")
        self.assertEqual(r["status"], STATUS_OK)
        self.assertIn("primary_without_supplier_factor", r["reason_codes"])
        self.assertEqual(r["data_class"], "Data aktivitas sekunder")

    def test_primary_supplier_factor_without_evidence_has_no_source(self):
        r = self.one(data_method="primary_supplier", supplier_emission_factor="0.78",
                     evidence_reference="", evidence_status="missing")
        self.assertIn("factor_no_source", r["reason_codes"])

    def test_factor_without_source_flagged(self):
        r = self.one(item_category="Bahan Kimia Pembersih", activity_quantity="100", activity_unit="L")
        self.assertEqual(r["status"], STATUS_OK)
        self.assertIn("factor_no_source", r["reason_codes"])
        self.assertAlmostEqual(r["emissions_kg"], 160.0, places=6)

    def test_old_factor_flagged(self):
        r = self.one(item_category="Palet Kayu", activity_quantity="10", activity_unit="unit")
        self.assertIn("factor_old", r["reason_codes"])
        self.assertAlmostEqual(r["emissions_kg"], 65.0, places=6)

    def test_duplicate_excluded_by_default_and_togglable(self):
        a, b = row(transaction_id="D-1"), row(transaction_id="D-1")
        df = calc(a, b)
        self.assertEqual(list(df["status"]), [STATUS_OK, STATUS_EXCLUDED])
        df2 = calc(a, b, cfg=RiskConfig(exclude_duplicates=False))
        self.assertEqual(list(df2["status"]), [STATUS_OK, STATUS_OK])

    def test_deterministic(self):
        r1, r2 = calc(row(), row(transaction_id="T-2", activity_unit="pcs")), calc(row(), row(transaction_id="T-2", activity_unit="pcs"))
        self.assertTrue(r1.equals(r2))

    def test_result_stores_reproducibility_fields(self):
        r = self.one()
        for k in ("factor_id", "factor_value", "factor_unit", "factor_source", "factor_year", "method_version",
                  "formula", "assumptions", "converted_quantity", "converted_unit"):
            self.assertNotIn(r[k], (None, ""), k)


class TestFactorLibrary(unittest.TestCase):
    def test_demo_library_valid_and_labelled_dummy(self):
        f = factors()
        self.assertEqual(validate_factors(f), [])
        self.assertTrue(f.loc[f["source_name"] != "", "is_dummy"].all(), "semua faktor bersumber harus berlabel DUMMY")
        self.assertTrue(((~f["has_source"]) & (f["factor_id"] == "EF-D007")).any())

    def test_bad_library_schema(self):
        import io
        with self.assertRaises(ValueError):
            load_factors(io.StringIO("factor_id,factor_value\nX,1\n"))

    def test_bad_value_reported(self):
        import io
        csv = ("factor_id,item_category,factor_value,factor_unit,source_name,source_reference,publication_year,geography,"
               "boundary_notes,method_notes\nX,A,abc,kg CO2e/kg,S,R,2025,G,B,M\n")
        self.assertTrue(validate_factors(load_factors(io.StringIO(csv))))


if __name__ == "__main__":
    unittest.main()
