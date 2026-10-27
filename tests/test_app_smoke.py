"""Uji asap app.py memakai tiruan Streamlit (tanpa Streamlit terpasang).

Memastikan setiap halaman dan form berjalan tanpa exception terhadap data demo, data kosong,
CSV rusak, serta alur unggah bukti. TIDAK menguji tampilan visual/kompatibilitas versi Streamlit.
"""
import runpy
import sys
import unittest

import helpers  # noqa: F401
from helpers import DATA
from streamlit_fake import FakeUpload, _Dict, _Rerun, _Stop, make_streamlit

PAGES = ["1. Overview Dashboard", "2. Data Import & Validation", "3. Scope 3 Calculator",
         "4. Evidence & Traceability", "5. Data Quality & Risk", "6. Readiness Report"]
APP = str(helpers.ROOT / "app.py")


def run_app(page, sess, **kw):
    st = make_streamlit(page, session=sess, **kw)
    sys.modules["streamlit"] = st
    for _ in range(5):
        try:
            runpy.run_path(APP)
            break
        except _Stop:
            break
        except _Rerun:
            continue
    return st


class TestAppSmoke(unittest.TestCase):
    def test_all_pages_without_data(self):
        sess = _Dict()
        for p in PAGES:
            run_app(p, sess)
        self.assertIsNone(sess["raw_df"])

    def test_all_pages_with_demo_data(self):
        sess = _Dict()
        run_app(PAGES[0], sess, button_labels=("Muat data demo (100 transaksi sintetis)",))
        self.assertEqual(len(sess["raw_df"]), 100)
        for p in PAGES:
            st = run_app(p, sess)
            self.assertTrue(any(c[0] == "metric" or c[0] == "dataframe" for c in st.calls), p)
        st = run_app(PAGES[5], sess)
        names = [c[1] for c in st.calls if c[0] == "download"]
        self.assertTrue(any("PDF" in n for n in names))

    def test_csv_upload_flow(self):
        sess = _Dict()
        up = FakeUpload("sample_transactions.csv", (DATA / "sample_transactions.csv").read_bytes())
        run_app(PAGES[1], sess, uploads={"Unggah CSV transaksi": up})
        self.assertEqual(len(sess["raw_df"]), 100)
        self.assertEqual(sess["dataset_name"], "sample_transactions.csv")

    def test_broken_csv_shows_actionable_error_not_crash(self):
        sess = _Dict()
        bad = FakeUpload("bad.csv", b"kolom_salah,lain\n1,2\n")
        st = run_app(PAGES[1], sess, uploads={"Unggah CSV transaksi": bad})
        self.assertTrue(any(c[0] == "error" and "Kolom wajib tidak lengkap" in c[1][0] for c in st.calls))
        for p in PAGES:  # halaman lain tidak boleh crash ketika skema salah
            run_app(p, sess)

    def test_empty_file_does_not_crash(self):
        sess = _Dict()
        st = run_app(PAGES[1], sess, uploads={"Unggah CSV transaksi": FakeUpload("e.csv", b"")})
        self.assertTrue(any(c[0] == "error" for c in st.calls))

    def test_whatif_calculator_and_manual_form(self):
        sess = _Dict()
        run_app(PAGES[0], sess, button_labels=("Muat data demo (100 transaksi sintetis)",))
        run_app(PAGES[2], sess, submit_labels=("Hitung",))
        run_app(PAGES[1], sess, submit_labels=("Tambahkan transaksi",))
        self.assertEqual(len(sess["raw_df"]), 101)

    def test_evidence_upload_marks_unverified_not_verified(self):
        sess = _Dict()
        run_app(PAGES[0], sess, button_labels=("Muat data demo (100 transaksi sintetis)",))
        doc = FakeUpload("faktur.pdf", b"%PDF-1.4 dummy")
        run_app(PAGES[3], sess, submit_labels=("Simpan metadata bukti",), uploads={"Unggah berkas bukti": doc})
        raw = sess["raw_df"]
        hit = raw[raw["evidence_file_name"] == "faktur.pdf"]
        self.assertEqual(len(hit), 1)
        self.assertEqual(len(hit.iloc[0]["evidence_file_sha256"]), 64)
        self.assertNotIn(hit.iloc[0]["evidence_status"], ("verified", "terverifikasi"))
        st = run_app(PAGES[3], sess)  # render ulang dengan data yang berubah

    def test_reset_button(self):
        sess = _Dict()
        run_app(PAGES[0], sess, button_labels=("Muat data demo (100 transaksi sintetis)",))
        run_app(PAGES[0], sess, button_labels=("Atur ulang data sesi",))
        self.assertIsNone(sess["raw_df"])


if __name__ == "__main__":
    unittest.main()
