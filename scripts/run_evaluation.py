"""Jalankan semua tes, ukur metrik brief (bagian 11), dan hasilkan dokumen bukti.

    python scripts/run_evaluation.py

Keluaran:
  docs/TEST_RESULTS.md                      hasil tes + metrik + keterbatasan
  sample_outputs/readiness_report_sample.*  contoh laporan (MD, PDF)
  sample_outputs/*.csv                      contoh ekspor jejak perhitungan, temuan, kualitas data
Hanya memakai pustaka standar + pandas + reportlab (tanpa Streamlit).
"""
from __future__ import annotations

import io
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd  # noqa: E402

from helpers import DATA, factors, sample_raw  # noqa: E402
from modules.calculator import STATUS_EXCLUDED, STATUS_OK, STATUS_REJECTED  # noqa: E402
from modules.pipeline import run_pipeline  # noqa: E402
from modules.reporting import (audit_trail_table, build_report_blocks, report_markdown,  # noqa: E402
                               report_pdf, to_csv_bytes)
from test_metrics import manual_expected  # noqa: E402

OUT = ROOT / "sample_outputs"
DOCS = ROOT / "docs"


def run_tests() -> tuple[unittest.TestResult, float, str]:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    buf = io.StringIO()
    t0 = time.time()
    res = unittest.TextTestRunner(stream=buf, verbosity=2).run(suite)
    return res, time.time() - t0, buf.getvalue()


def metrics() -> dict:
    a = run_pipeline(sample_raw(), factors())
    d = a.data
    import csv
    raw = list(csv.DictReader(open(DATA / "sample_transactions.csv", encoding="utf-8")))
    fac = list(csv.DictReader(open(DATA / "emission_factors.csv", encoding="utf-8")))
    checked = mism = 0
    for (_, r), rw in zip(d.iterrows(), raw):
        if r["status"] == STATUS_EXCLUDED:
            continue
        exp = manual_expected(rw, fac)
        ok_ = (r["status"] == STATUS_REJECTED) if exp is None else (
            r["status"] == STATUS_OK and abs(r["emissions_kg"] - exp) <= 1e-6 * max(1, abs(exp)))
        checked += 1
        mism += 0 if ok_ else 1
    key = pd.read_csv(DATA / "sample_anomaly_key.csv")
    found = set(zip(a.findings["transaction_id"], a.findings["finding_type"]))
    key["detected"] = [(t, ty) in found for t, ty in zip(key["transaction_id"], key["anomaly_type"])]
    at = audit_trail_table(a)
    okk = at[at["status_hitung"] == STATUS_OK]
    need = ["faktor_id", "faktor_nilai", "faktor_satuan", "kelas_data", "input_aktivitas", "rumus", "versi_metode"]
    chain = okk[need].notna().all(axis=1) & (okk[need].astype(str) != "").all(axis=1)
    arith = (okk["kuantitas_terkonversi"] * okk["faktor_nilai"]).sub(okk["emisi_kg_co2e"]).abs() < 1e-3
    return dict(a=a, checked=checked, mism=mism, key=key, n_ok=len(okk), chain=int((chain & arith).sum()))


def write_outputs(a) -> None:
    OUT.mkdir(exist_ok=True)
    blocks = build_report_blocks(a, dataset_name="sample_transactions.csv (sintetis)",
                                 factor_name="emission_factors.csv (DUMMY demo)",
                                 generated_at=datetime(2026, 10, 27, 12, 0))
    (OUT / "readiness_report_sample.md").write_text(report_markdown(blocks), encoding="utf-8")
    (OUT / "readiness_report_sample.pdf").write_bytes(report_pdf(blocks))
    (OUT / "audit_trail_sample.csv").write_bytes(to_csv_bytes(audit_trail_table(a)))
    (OUT / "findings_sample.csv").write_bytes(to_csv_bytes(a.findings))
    (OUT / "data_quality_sample.csv").write_bytes(to_csv_bytes(a.quality))


def main() -> int:
    res, secs, log = run_tests()
    m = metrics()
    a, key = m["a"], m["key"]
    write_outputs(a)
    rate = key["detected"].mean()
    by = key.groupby("anomaly_type")["detected"].agg(["sum", "count"])
    s = a.summary
    status = "LULUS" if res.wasSuccessful() else "GAGAL"
    L = [
        "# Hasil Pengujian TRACE ESG",
        "",
        f"Dijalankan: {datetime.now():%Y-%m-%d %H:%M} · Python {sys.version.split()[0]} · pandas {pd.__version__}",
        "",
        "Perintah: `python scripts/run_evaluation.py` (atau `python -m unittest discover -s tests`).",
        "",
        "## 1. Ringkasan tes otomatis",
        "",
        f"- Total tes: **{res.testsRun}** · gagal: **{len(res.failures)}** · error: **{len(res.errors)}** · status: **{status}** "
        f"({secs:.1f} dtk)",
        "- Cakupan: perhitungan, validasi, mesin risiko, laporan/ekspor, metrik brief, dan uji asap seluruh halaman UI "
        "(memakai tiruan Streamlit, lihat keterbatasan).",
        "",
        "### Matriks kasus uji yang diminta brief",
        "",
        "| Kasus uji | Tes yang mencakup |",
        "|---|---|",
        "| Data valid | `test_valid_data_has_no_issues`, `test_valid_physical_row`, `test_brief_example_500kg_x_2` |",
        "| Kolom/nilai kosong | `test_blank_required_field`, `test_missing_required_column`, `test_missing_or_invalid_inputs_rejected` |",
        "| Transaksi duplikat | `test_exact_duplicate_id_same_content`, `test_same_content_different_id`, `test_duplicate_excluded_by_default_and_togglable` |",
        "| Satuan tidak cocok | `test_unit_mismatch_rejected_no_number`, `test_incompatible_units_raise`, `test_physical_data_never_multiplied_by_spend_factor` |",
        "| Faktor emisi hilang / tanpa sumber | `test_missing_factor_category`, `test_factor_without_source_flagged` |",
        "| Bukti tidak tersedia | `test_evidence_never_verified`, `test_provided_without_reference_is_not_recorded`, `test_attached_document_is_still_unverified` |",
        "| Metode estimasi | `test_spend_based_row`, `test_each_required_finding_type_is_produced` |",
        "| Determinisme & reproduksi | `test_deterministic`, `test_decimal_exactness`, `test_result_stores_reproducibility_fields`, `test_report_is_deterministic` |",
        "| Tidak ada klaim 'terverifikasi' | `test_no_verified_claims`, `test_disclaimer_present_top_and_bottom` |",
        "",
        "## 2. Metrik keberhasilan internal (brief bagian 11)",
        "",
        "Target adalah sasaran awal internal, bukan standar industri. Pengukuran dilakukan pada dataset sintetis "
        "(`data/sample_transactions.csv`, 100 baris, 20 pemasok) dengan faktor emisi DUMMY.",
        "",
        "| Metrik | Target | Hasil terukur | Status |",
        "|---|---|---|---|",
        f"| Akurasi kalkulasi vs hitung manual independen | 100% | {m['checked'] - m['mism']} dari {m['checked']} baris cocok "
        f"({(m['checked'] - m['mism']) / m['checked']:.0%}); baris yang seharusnya ditolak juga ditolak | "
        f"{'Tercapai' if m['mism'] == 0 else 'Belum'} |",
        f"| Deteksi anomali tertanam | >= 90% | {int(key['detected'].sum())} dari {len(key)} ({rate:.1%}) | "
        f"{'Tercapai' if rate >= 0.9 else 'Belum'} |",
        f"| Keterlacakan: rantai input-faktor-metode lengkap | >= 95% | {m['chain']} dari {m['n_ok']} transaksi terhitung "
        f"({m['chain'] / m['n_ok']:.0%}) | {'Tercapai' if m['chain'] / m['n_ok'] >= 0.95 else 'Belum'} |",
        "| Efisiensi dibanding proses manual | lebih rendah dari manual | **Belum diukur** (perlu uji waktu dengan pengguna) | Belum |",
        "| Kegunaan: keberhasilan tugas inti | >= 80% | **Belum diukur** (perlu uji pengguna; lihat `docs/USER_TEST_PROTOCOL.md`) | Belum |",
        "",
        "Rincian deteksi anomali per jenis:",
        "",
        "| Jenis anomali | Terdeteksi | Total |",
        "|---|---|---|",
    ]
    L += [f"| {t} | {int(r['sum'])} | {int(r['count'])} |" for t, r in by.iterrows()]
    L += [
        "",
        "## 3. Hasil analisis dataset demo",
        "",
        f"- Total estimasi emisi (belum diverifikasi): **{s['total_emissions_kg'] / 1000:,.2f} t CO2e** (faktor DUMMY).",
        f"- Baris: {s['n_rows']} · dihitung: {s['n_calculated']} · ditolak: {s['n_rejected']} · duplikat dikecualikan: {s['n_excluded_duplicates']}.",
        f"- Temuan: {s['n_findings']} (prioritas Tinggi {s['n_priority_high']} / Sedang {s['n_priority_medium']} / Rutin {s['n_priority_routine']}).",
        "",
        "## 4. Keterbatasan pengujian (jujur)",
        "",
        "- **Anomali ditanam oleh tim sendiri**, jadi angka deteksi 100% bersifat optimistis. Angka ini membuktikan tidak ada regresi "
        "dan aturan bekerja pada pola yang diketahui, bukan performa pada data nyata yang berantakan.",
        "- **Akurasi kalkulasi** diuji terhadap implementasi 'hitung manual' independen (tanpa pandas/Decimal) dan contoh deterministik; "
        "ini menguji kebenaran aritmetika dan aturan satuan, bukan kebenaran faktor emisi (faktor demo adalah DUMMY).",
        "- **Uji UI** memakai tiruan modul Streamlit: memastikan semua jalur kode halaman berjalan tanpa exception. Uji ini TIDAK menilai "
        "tampilan visual, kompatibilitas versi Streamlit, maupun interaksi di peramban. Lakukan uji manual dengan `streamlit run app.py` "
        "dan, bila memungkinkan, `streamlit.testing.v1.AppTest`.",
        "- **Efisiensi dan kegunaan** memerlukan partisipan manusia dan belum diukur; jangan dilaporkan sebagai hasil sebelum diuji.",
        "- Dataset hanya 100 baris; performa dan perilaku pada data ribuan baris belum diuji.",
        "",
        "## 5. Log eksekusi tes",
        "",
        "```",
        log.strip(),
        "```",
        "",
    ]
    DOCS.mkdir(exist_ok=True)
    (DOCS / "TEST_RESULTS.md").write_text("\n".join(L), encoding="utf-8")
    print(f"tes: {res.testsRun}, gagal: {len(res.failures)}, error: {len(res.errors)} | anomali {rate:.1%} | "
          f"akurasi {(m['checked'] - m['mism'])}/{m['checked']} | rantai {m['chain']}/{m['n_ok']}")
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
