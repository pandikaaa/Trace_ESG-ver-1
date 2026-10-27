# TRACE ESG: Traceable Reporting, Accounting & Carbon Evidence

Prototipe web interaktif untuk **SMART ACCOUNTING & BUSINESS CHALLENGE 2026 · Track B (Digital Prototype & Solution Challenge) · subtema ESG & Sustainability**.

> **Calculate → Trace → Assess.** Hitung emisi Scope 3 Kategori 1 (Purchased Goods and Services), telusuri asal setiap angka (data aktivitas → faktor emisi → metode → asumsi → bukti), lalu nilai keterbatasan data dan kesiapan dokumentasinya.

**Disclaimer (juga tampil di setiap halaman):** TRACE ESG mendukung perhitungan, penelusuran bukti, dan persiapan dokumentasi. Aplikasi tidak memberikan verifikasi independen, sertifikasi, atau opini assurance.

**Faktor emisi pada data demo adalah DATA DUMMY ILUSTRATIF**, bukan faktor resmi. Semua nama perusahaan dan pemasok pada dataset sintetis fiktif.

## Menjalankan

Butuh Python 3.10+ (diuji pada 3.13).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Aplikasi terbuka di http://localhost:8501. Klik **Muat data demo** (Dashboard) atau unggah `data/sample_transactions.csv` di halaman 2.

Jalankan tes dan hasilkan ulang dokumen bukti:

```bash
python -m unittest discover -s tests          # 72 tes, tanpa perlu Streamlit
python scripts/run_evaluation.py              # tes + metrik -> docs/TEST_RESULTS.md + sample_outputs/
```

### Deploy gratis (agar juri bisa membuka lewat tautan)
Unggah folder ini ke repositori GitHub, lalu buat app di [Streamlit Community Cloud](https://streamlit.io/cloud) dengan *main file* `app.py`.

## Halaman

| # | Halaman | Isi |
|---|---|---|
| 1 | Overview Dashboard | Total estimasi emisi (tidak pernah disebut "verified"), jumlah transaksi/pemasok, % referensi bukti, catatan estimasi, temuan prioritas, grafik emisi |
| 2 | Data Import & Validation | Unggah CSV / input manual, pratinjau, validasi kolom/kosong/duplikat/tipe/satuan dengan pesan tindakan, pustaka faktor |
| 3 | Scope 3 Calculator | Input aktivitas, metode, faktor, sumber, satuan, hasil, kelas data (primer/sekunder/estimasi), alasan penolakan, kalkulator what-if |
| 4 | Evidence & Traceability | Pilih satu angka → rantai Data → Faktor → Metode → Bukti; catat metadata bukti / hash berkas (tidak pernah "terverifikasi") |
| 5 | Data Quality & Risk | Temuan dengan severity, alasan, transaksi, rekomendasi; 5 dimensi kualitas terpisah; prioritas dari matriks materialitas × kelemahan data dengan ambang yang dapat diubah |
| 6 | Readiness Report | Indikator kesiapan + ekspor PDF, Markdown, dan CSV |

## Metode ringkas

- `Emisi (kg CO₂e) = data aktivitas × faktor emisi`, dihitung dengan `Decimal` agar identik dengan hitungan manual.
- Tiga kelas data: **data pemasok (primer)**, **data aktivitas sekunder**, **estimasi berbasis pengeluaran**.
- Data fisik **tidak pernah** dikalikan dengan faktor berbasis pengeluaran. Satuan tak cocok / faktor tak ada / input tak valid → perhitungan **ditolak** dan ditandai (tidak masuk total).
- Prioritas tindak lanjut = materialitas (pangsa emisi) × kelemahan data, aturan terlihat di halaman 5 dan ambangnya dapat dikonfigurasi di sidebar. **Tidak ada skor gabungan kotak-hitam.**

## Struktur

```
app.py                  UI Streamlit (6 halaman)
modules/
  config.py             konstanta, label, disclaimer, ambang default
  validation.py         validasi kolom/nilai/duplikat/periode/satuan
  calculator.py         perhitungan deterministik + pustaka faktor
  risk_engine.py        temuan, materialitas, prioritas, 5 dimensi kualitas
  reporting.py          laporan (MD/PDF) dan ekspor CSV
  pipeline.py           orkestrasi validasi → hitung → temuan → kualitas
data/                   sample_transactions.csv (100 baris, 20 pemasok), emission_factors.csv (DUMMY),
                        sample_anomaly_key.csv (kunci anomali tertanam), generate_sample_data.py
tests/                  72 tes (unittest)
scripts/run_evaluation.py
docs/                   TEST_RESULTS.md, FITUR_BELUM_DIIMPLEMENTASIKAN.md, DEMO_SCRIPT.md, USER_TEST_PROTOCOL.md
sample_outputs/         contoh laporan ekspor (PDF/MD/CSV)
```

## Format CSV

Transaksi: `transaction_id, transaction_date, supplier_id, supplier_name, item_category, item_description, activity_quantity, activity_unit, purchase_amount, currency, data_method, evidence_reference, evidence_status, reporting_period` (opsional: `supplier_emission_factor`).
`data_method`: `primary_supplier` | `secondary_activity` | `spend_based`. `evidence_status`: `provided` | `partial` | `requested` | `missing` (tidak ada status "verified" dengan sengaja).
Faktor: `factor_id, item_category, factor_value, factor_unit, source_name, source_reference, publication_year, geography, boundary_notes, method_notes` (satuan `kg CO2e/<satuan>`). Untuk data nyata, ganti dengan faktor yang sumbernya dapat ditelusuri dan diverifikasi sendiri (mulai dari GHG Protocol Scope 3 Standard / Calculation Guidance).

## Keterbatasan penting
Lihat `docs/FITUR_BELUM_DIIMPLEMENTASIKAN.md` dan bagian 4 `docs/TEST_RESULTS.md`. Singkatnya: hanya Scope 3 Kategori 1; faktor demo adalah dummy; mata uang selain IDR belum dikonversi; isi dokumen bukti tidak dibaca; efisiensi dan kegunaan belum diukur; data tidak persisten antar sesi.
