"""Pembangkit dataset SINTETIS untuk demo TRACE ESG (seed tetap -> hasil selalu sama).

Menghasilkan:
  data/sample_transactions.csv   : 100 transaksi pembelian dari 20 pemasok fiktif
  data/sample_anomaly_key.csv    : kunci anomali yang SENGAJA ditanam (untuk uji deteksi)

Semua nama pemasok, nomor dokumen, dan angka bersifat fiktif.
Jalankan:  python data/generate_sample_data.py
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 2026
OUT = Path(__file__).resolve().parent

# supplier_id: (nama, [kategori], jumlah_transaksi, pemasok_primer?)
SUPPLIERS = {
    "S01": ("PT Agro Tepung Sentosa", ["Tepung Terigu"], 7, 0.78),
    "S02": ("CV Gula Manis Jaya", ["Gula Pasir"], 4, None),
    "S03": ("PT Sawit Lestari Abadi", ["Minyak Sawit"], 7, 2.05),
    "S04": ("PT Karton Prima Kemas", ["Kemasan Karton"], 5, 1.05),
    "S05": ("PT Plastindo Flexipack", ["Kemasan Plastik Film"], 4, 2.50),
    "S06": ("UD Kayu Palet Mandiri", ["Palet Kayu"], 4, None),
    "S07": ("PT Kimia Bersih Utama", ["Bahan Kimia Pembersih"], 4, None),
    "S08": ("PT Teknologi Kantor Nusa", ["Perangkat IT", "Perlengkapan Kantor"], 5, None),
    "S09": ("PT Servis Mesin Andalan", ["Jasa Pemeliharaan"], 5, None),
    "S10": ("PT Konsultan Mitra Strategi", ["Jasa Konsultan"], 4, None),
    "S11": ("CV Alat Tulis Cemerlang", ["Perlengkapan Kantor"], 4, None),
    "S12": ("PT Tepung Karya Pangan", ["Tepung Terigu", "Gula Pasir"], 6, None),
    "S13": ("PT Pack Solusi Indonesia", ["Kemasan Karton", "Kemasan Plastik Film"], 5, None),
    "S14": ("PT Perisa Rasa Nusantara", ["Perisa Makanan"], 4, None),
    "S15": ("PT Gudang Palet Logistik", ["Palet Kayu"], 3, None),
    "S16": ("PT Minyak Nabati Raya", ["Minyak Sawit"], 4, None),
    "S17": ("CV Kimia Industri Prima", ["Bahan Kimia Pembersih"], 3, None),
    "S18": ("PT Digital Peralatan Kerja", ["Perangkat IT"], 4, None),
    "S19": ("PT Layanan Teknik Terpadu", ["Jasa Pemeliharaan", "Jasa Konsultan"], 5, None),
    "S20": ("PT Grosir Bahan Pokok", ["Tepung Terigu", "Gula Pasir", "Minyak Sawit"], 8, None),
}

# kategori: (satuan, (qty_min, qty_max), harga_per_satuan, [deskripsi])
CATEGORY = {
    "Tepung Terigu": ("kg", (5000, 60000), 12000, ["Tepung terigu protein sedang", "Tepung terigu protein tinggi", "Tepung terigu serbaguna"]),
    "Gula Pasir": ("kg", (3000, 40000), 16000, ["Gula pasir kristal putih", "Gula pasir curah"]),
    "Minyak Sawit": ("kg", (2000, 30000), 18000, ["Minyak sawit olahan RBD", "Minyak goreng curah"]),
    "Kemasan Karton": ("kg", (1000, 15000), 15000, ["Karton gelombang 5 ply", "Dus pengiriman produk jadi"]),
    "Kemasan Plastik Film": ("kg", (500, 6000), 30000, ["Film plastik laminasi", "Plastik kemasan primer"]),
    "Palet Kayu": ("unit", (100, 1500), 90000, ["Palet kayu standar 1,2 x 1 m", "Palet kayu ekspor"]),
    "Bahan Kimia Pembersih": ("L", (200, 3000), 25000, ["Pembersih lantai produksi", "Sanitizer peralatan"]),
    "Perangkat IT": ("unit", (2, 40), 12000000, ["Laptop kerja staf", "Perangkat jaringan kantor", "PC desktop"]),
    "Perisa Makanan": ("kg", (200, 3000), 85000, ["Perisa vanila", "Perisa cokelat", "Perisa buah"]),
    "Jasa Pemeliharaan": ("paket", (1, 1), None, ["Servis berkala mesin produksi", "Perawatan boiler", "Kalibrasi peralatan"]),
    "Jasa Konsultan": ("paket", (1, 1), None, ["Jasa konsultan sistem mutu", "Jasa konsultan K3"]),
    "Perlengkapan Kantor": ("paket", (1, 1), None, ["Alat tulis kantor bulanan", "Perlengkapan cetak dan arsip"]),
}
SERVICE_RANGE = {"Jasa Pemeliharaan": (20_000_000, 250_000_000),
                 "Jasa Konsultan": (15_000_000, 120_000_000),
                 "Perlengkapan Kantor": (3_000_000, 40_000_000)}
ALWAYS_SPEND = {"Jasa Pemeliharaan", "Jasa Konsultan", "Perlengkapan Kantor"}
COLUMNS = [
    "transaction_id", "transaction_date", "supplier_id", "supplier_name", "item_category",
    "item_description", "activity_quantity", "activity_unit", "purchase_amount", "currency",
    "data_method", "evidence_reference", "evidence_status", "reporting_period",
    "supplier_emission_factor",
]


def build() -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    rows: list[dict] = []
    for sid, (name, cats, n, sup_ef) in SUPPLIERS.items():
        for _ in range(n):
            cat = rng.choice(cats)
            unit, (qmin, qmax), price, descs = CATEGORY[cat]
            if cat in ALWAYS_SPEND:
                qty = 1
                amount = rng.randrange(*[v // 1000 for v in SERVICE_RANGE[cat]]) * 1000
                method = "spend_based"
            else:
                qty = rng.randint(qmin, qmax)
                if unit == "kg" or unit == "L":
                    qty = round(qty / 50) * 50 or 50
                amount = round(qty * price * rng.uniform(0.9, 1.1) / 1000) * 1000
                if sup_ef is not None and rng.random() < 0.85:
                    method = "primary_supplier"
                elif cat == "Perangkat IT":
                    method = "secondary_activity" if rng.random() < 0.6 else "spend_based"
                else:
                    method = "secondary_activity" if rng.random() < 0.7 else "spend_based"
            d = date(2025, 1, 1) + timedelta(days=rng.randrange(0, 365))
            rows.append(dict(
                supplier_id=sid, supplier_name=name, item_category=cat,
                item_description=rng.choice(descs), activity_quantity=qty, activity_unit=unit,
                purchase_amount=amount, currency="IDR", data_method=method,
                transaction_date=d.isoformat(), reporting_period="2025",
                supplier_emission_factor=(sup_ef if method == "primary_supplier" else ""),
            ))
    rows.sort(key=lambda r: (r["transaction_date"], r["supplier_id"]))
    for i, r in enumerate(rows, 1):
        r["transaction_id"] = f"TRX-2025-{i:03d}"
        r["evidence_status"] = "provided"
        r["evidence_reference"] = f"INV-{r['supplier_id']}-{r['transaction_date'][2:4]}{r['transaction_date'][5:7]}-{i:03d}.pdf"
    assert len(rows) == 95, len(rows)

    key: list[dict] = []
    locked: set[int] = set()

    def mark(idx: int, typ: str, note: str) -> None:
        key.append({"transaction_id": rows[idx]["transaction_id"], "anomaly_type": typ, "note": note})

    def pick(pred, k: int, pool=None) -> list[int]:
        elig = [i for i, r in enumerate(rows) if i not in locked and pred(r)]
        chosen = rng.sample(elig, k)
        locked.update(chosen)
        return chosen

    secondary_phys = lambda r: (r["data_method"] == "secondary_activity"
                                and r["item_category"] in ("Tepung Terigu", "Gula Pasir", "Minyak Sawit",
                                                           "Kemasan Karton", "Kemasan Plastik Film"))
    # 0) sumber duplikat dikunci agar salinannya identik dengan baris asli yang bersih
    dup_exact_src = pick(lambda r: r["data_method"] != "spend_based", 3)
    dup_content_src = pick(lambda r: r["data_method"] != "spend_based", 2)

    # 1) satuan konvertibel tidak konsisten (kg -> ton, jumlah ekuivalen)
    for i in pick(lambda r: secondary_phys(r) and r["activity_unit"] == "kg", 3):
        r = rows[i]
        r["activity_quantity"] = round(r["activity_quantity"] / 1000, 3)
        r["activity_unit"] = "ton"
        mark(i, "unit_mismatch", "Satuan 'ton' padahal satuan standar kategori 'kg' (konversi otomatis, perlu konfirmasi)")
    # 2) satuan tidak kompatibel / tidak dikenal
    for i, bad in zip(pick(lambda r: secondary_phys(r), 3), ["pcs", "pcs", "box"]):
        rows[i]["activity_unit"] = bad
        mark(i, "unit_mismatch", f"Satuan '{bad}' tidak kompatibel dengan faktor emisi berbasis massa")
    # 3) nilai wajib kosong
    for i in pick(lambda r: secondary_phys(r), 2):
        rows[i]["activity_quantity"] = ""
        mark(i, "missing_required_field", "activity_quantity kosong")
    j = pick(lambda r: r["data_method"] == "spend_based", 1)[0]
    rows[j]["supplier_name"] = ""
    mark(j, "missing_required_field", "supplier_name kosong")
    j = pick(lambda r: secondary_phys(r), 1)[0]
    rows[j]["activity_unit"] = ""
    mark(j, "missing_required_field", "activity_unit kosong")
    # 4) nilai tidak valid
    j = pick(lambda r: secondary_phys(r), 1)[0]
    rows[j]["activity_quantity"] = -500
    mark(j, "invalid_value", "activity_quantity negatif")
    j = pick(lambda r: r["data_method"] != "spend_based", 1)[0]
    rows[j]["transaction_date"] = "31/02/2025"
    mark(j, "invalid_value", "transaction_date bukan tanggal valid")
    # 5) periode pelaporan tidak konsisten
    for i in pick(lambda r: True, 2):
        rows[i]["reporting_period"] = "2024"
        mark(i, "inconsistent_reporting_period", "reporting_period 2024 tetapi tanggal transaksi 2025")
    j = pick(lambda r: r["transaction_date"].startswith("2025-12"), 1)[0] if any(
        r["transaction_date"].startswith("2025-12") for r in rows) else pick(lambda r: True, 1)[0]
    rows[j]["transaction_date"] = "2026-01-06"
    mark(j, "inconsistent_reporting_period", "tanggal transaksi 2026 tetapi reporting_period 2025")
    # 6) satu transaksi non-IDR berbasis pengeluaran
    j = pick(lambda r: r["item_category"] == "Perangkat IT" and r["data_method"] == "spend_based", 1)
    if not j:
        j = pick(lambda r: r["data_method"] == "spend_based" and r["item_category"] not in ALWAYS_SPEND, 1)
    j = j[0]
    rows[j]["currency"] = "USD"
    rows[j]["purchase_amount"] = round(rows[j]["purchase_amount"] / 16000)
    mark(j, "unit_mismatch", "Mata uang USD; faktor berbasis pengeluaran hanya tersedia dalam IDR")

    # 7) bukti: dua di antaranya sengaja pada transaksi beremisi besar agar demo prioritas Tinggi terlihat
    def est(r):  # perkiraan emisi kasar hanya untuk memilih baris demo
        return r["activity_quantity"] if isinstance(r["activity_quantity"], (int, float)) else 0
    big = sorted([i for i, r in enumerate(rows) if i not in dup_exact_src + dup_content_src
                  and r["data_method"] != "spend_based" and r["item_category"] in ("Minyak Sawit", "Tepung Terigu")
                  and r["activity_unit"] == "kg"],
                 key=lambda i: -est(rows[i]) * (2.3 if rows[i]["item_category"] == "Minyak Sawit" else 0.9))[:2]
    for i in big:
        rows[i]["evidence_status"], rows[i]["evidence_reference"] = "missing", ""
        mark(i, "evidence_missing", "Bukti belum tersedia pada transaksi beremisi besar")
    locked.update(big)
    for i in pick(lambda r: True, 8):
        rows[i]["evidence_status"], rows[i]["evidence_reference"] = "missing", ""
        mark(i, "evidence_missing", "Bukti belum tersedia")
    for i in pick(lambda r: True, 3):
        rows[i]["evidence_status"] = "partial"
        mark(i, "evidence_missing", "Bukti hanya sebagian")
    for i in pick(lambda r: True, 2):
        rows[i]["evidence_status"], rows[i]["evidence_reference"] = "requested", ""
        mark(i, "evidence_missing", "Bukti diminta, belum diterima")
    for i in pick(lambda r: True, 2):
        rows[i]["evidence_reference"] = ""
        mark(i, "evidence_missing", "Status 'provided' tetapi referensi kosong")

    # 8) anomali alami: ditandai karena memang akan terdeteksi oleh aturan
    for i, r in enumerate(rows):
        if r["data_method"] == "spend_based":
            mark(i, "estimation_method_used", "Estimasi berbasis pengeluaran")
        if r["item_category"] == "Perisa Makanan":
            mark(i, "missing_factor_or_source", "Kategori tidak ada di pustaka faktor emisi")
        if r["item_category"] == "Bahan Kimia Pembersih" and r["data_method"] == "secondary_activity":
            mark(i, "missing_factor_or_source", "Faktor emisi kategori ini tidak memiliki sumber")

    # 9) duplikat: 3 ID persis sama + 2 isi sama dengan ID berbeda (menjadi baris ke-96..100)
    extra: list[dict] = []
    for i in dup_exact_src:
        extra.append(dict(rows[i]))
        mark(i, "duplicate_transaction", "ID transaksi muncul dua kali")
    next_id = 96
    for i in dup_content_src:
        c = dict(rows[i])
        c["transaction_id"] = f"TRX-2025-{next_id:03d}"
        next_id += 1
        extra.append(c)
        mark(i, "duplicate_transaction", "Isi transaksi identik dengan transaksi lain (ID berbeda)")
        key.append({"transaction_id": c["transaction_id"], "anomaly_type": "duplicate_transaction",
                    "note": f"Salinan isi dari {rows[i]['transaction_id']}"})
    for c in extra:  # sisipkan di posisi acak setelah aslinya (mensimulasikan impor ganda)
        pos = rng.randrange(len(rows) // 2, len(rows))
        rows.insert(pos, c)
    assert len(rows) == 100, len(rows)
    return rows, key


def main() -> None:
    rows, key = build()
    with open(OUT / "sample_transactions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    # hapus duplikasi entri kunci
    seen, uniq = set(), []
    for k in key:
        t = (k["transaction_id"], k["anomaly_type"])
        if t not in seen:
            seen.add(t)
            uniq.append(k)
    with open(OUT / "sample_anomaly_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["transaction_id", "anomaly_type", "note"])
        w.writeheader()
        w.writerows(uniq)
    print(f"{len(rows)} transaksi, {len({r['supplier_id'] for r in rows})} pemasok, {len(uniq)} entri kunci anomali")


if __name__ == "__main__":
    main()
