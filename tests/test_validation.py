"""Uji validasi: kolom wajib, nilai kosong, tipe data, satuan, duplikasi, periode."""
import io
import unittest

from helpers import frame, row, sample_raw
from modules.validation import normalize_unit, read_csv_flexible, validate_transactions


def types(res, t=None):
    iss = res.issues
    return set(iss["issue_type"]) if t is None else iss[iss["issue_type"] == t]


class TestValidation(unittest.TestCase):
    def test_valid_data_has_no_issues(self):
        res = validate_transactions(frame(row(), row(transaction_id="T-2", activity_quantity="700")))
        self.assertTrue(res.schema_ok)
        self.assertEqual(len(res.issues), 0)

    def test_missing_required_column(self):
        df = frame(row()).drop(columns=["currency", "reporting_period"])
        res = validate_transactions(df)
        self.assertFalse(res.schema_ok)
        self.assertEqual(sorted(res.missing_columns), ["currency", "reporting_period"])
        self.assertIn("Tambahkan kolom", res.issues.iloc[0]["action"])

    def test_blank_required_field(self):
        res = validate_transactions(frame(row(activity_quantity=""), row(transaction_id="T-2", supplier_name="")))
        m = types(res, "missing_required_field")
        self.assertEqual(set(m["field"]), {"activity_quantity", "supplier_name"})
        self.assertTrue((m["action"].str.len() > 10).all(), "pesan harus dapat ditindaklanjuti")

    def test_invalid_types(self):
        res = validate_transactions(frame(
            row(activity_quantity="abc"), row(transaction_id="T-2", activity_quantity="-3"),
            row(transaction_id="T-3", purchase_amount="-1"), row(transaction_id="T-4", transaction_date="31/02/2025"),
            row(transaction_id="T-5", data_method="x"), row(transaction_id="T-6", reporting_period="FY25")))
        self.assertEqual(len(types(res, "invalid_value")), 6)

    def test_unknown_unit_is_warning(self):
        res = validate_transactions(frame(row(activity_unit="box")))
        self.assertEqual(types(res), {"unknown_unit"})
        self.assertEqual(res.issues.iloc[0]["level"], "Peringatan")

    def test_exact_duplicate_id_same_content(self):
        res = validate_transactions(frame(row(), row()))
        self.assertEqual(list(res.clean["dup_excluded"]), [False, True])
        self.assertEqual(res.clean.loc[1, "dup_kind"], "exact_row")

    def test_same_id_different_content_not_excluded(self):
        res = validate_transactions(frame(row(), row(activity_quantity="999")))
        self.assertEqual(res.clean.loc[1, "dup_kind"], "id_only")
        self.assertFalse(res.clean.loc[1, "dup_excluded"])
        self.assertEqual(len(types(res, "duplicate_transaction")), 2)

    def test_same_content_different_id(self):
        res = validate_transactions(frame(row(), row(transaction_id="T-2")))
        self.assertEqual(res.clean.loc[1, "dup_kind"], "content_only")
        self.assertTrue(res.clean.loc[1, "dup_excluded"])

    def test_period_inconsistency(self):
        res = validate_transactions(frame(row(reporting_period="2024")))
        self.assertEqual(types(res), {"inconsistent_reporting_period"})

    def test_semicolon_csv_and_header_normalisation(self):
        text = "Transaction_ID ; transaction_date\nT1;2025-01-01\n"
        df = read_csv_flexible(io.StringIO(text))
        self.assertEqual(list(df.columns), ["transaction_id", "transaction_date"])

    def test_unit_table(self):
        self.assertEqual(normalize_unit("TON")[0], "t")
        self.assertEqual(normalize_unit(" Kg ")[0], "kg")
        self.assertIsNone(normalize_unit("box"))

    def test_sample_dataset_shape(self):
        raw = sample_raw()
        self.assertEqual(len(raw), 100)
        self.assertEqual(raw["supplier_id"].nunique(), 20)
        res = validate_transactions(raw)
        self.assertTrue(res.schema_ok)
        self.assertGreater(res.n_errors, 0)  # dataset sengaja memuat anomali


if __name__ == "__main__":
    unittest.main()
