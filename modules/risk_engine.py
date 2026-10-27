"""Mesin temuan & prioritas risiko yang TRANSPARAN (aturan eksplisit, bukan skor kotak-hitam).

Alur:
  1. Setiap temuan punya `severity` (seberapa lemah datanya: Tinggi/Sedang/Rendah) dari aturan tetap.
  2. Setiap transaksi punya `materialitas` (pangsa emisi terhadap total; ambang dapat dikonfigurasi).
  3. `priority` = fungsi dari (materialitas, severity) lewat matriks di `priority_rule_table()`.
  4. Alasan prioritas ditulis dalam kalimat per temuan (lihat kolom `priority_reason`).

Kualitas data ditampilkan per DIMENSI (kelengkapan, keterlacakan, relevansi, konsistensi,
ketidakpastian) dengan status dan alasan -- tanpa skor gabungan.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .calculator import STATUS_EXCLUDED, STATUS_OK, STATUS_REJECTED
from .config import (
    EVIDENCE_LABEL, EVIDENCE_UPLOADED_LABEL, FINDING_LABEL, METHOD_PRIMARY, METHOD_SPEND,
    PRIORITY_ORDER, QUALITY_DIMENSIONS, SEVERITY_ORDER, SPEND_CURRENCY, RiskConfig,
)
from .validation import FINDING_ISSUE_TYPES

FINDING_COLUMNS = [
    "finding_id", "finding_type", "finding_label", "dimension", "severity", "priority", "transaction_id",
    "row_number", "supplier_name", "item_category", "emissions_kg", "materiality_level", "materiality_share",
    "materiality_basis", "reason", "priority_reason", "recommendation",
]
CRITICAL_FIELDS = {"activity_quantity", "activity_unit", "purchase_amount", "currency", "item_category",
                   "data_method", "transaction_id", "transaction_date"}
DIMENSION_OF = {
    "missing_required_field": "Kelengkapan", "invalid_value": "Kelengkapan",
    "duplicate_transaction": "Konsistensi", "unit_mismatch": "Konsistensi",
    "inconsistent_reporting_period": "Konsistensi", "missing_factor_or_source": "Keterlacakan",
    "evidence_missing": "Keterlacakan", "estimation_method_used": "Relevansi", "factor_outdated": "Relevansi",
}


# --------------------------------------------------------------------------------------
# Bantuan
# --------------------------------------------------------------------------------------
def merge_results(clean: pd.DataFrame, calc: pd.DataFrame) -> pd.DataFrame:
    """Gabungkan data transaksi ter-validasi dengan hasil hitung (satu baris per baris CSV)."""
    return clean.merge(calc.drop(columns=["transaction_id", "data_method"]), on="row_number", how="left")


def evidence_state(row) -> tuple[str, str, bool]:
    """(kode, label, tercatat?). TIDAK PERNAH bernilai 'terverifikasi'."""
    status = (row.get("evidence_status") or "").strip().lower()
    ref = (row.get("evidence_reference") or "").strip()
    has_file = bool((row.get("evidence_file_sha256") or "").strip())
    if status not in ("provided", "partial", "requested", "missing"):
        status = "missing"
    if status == "provided" and has_file:
        return "uploaded", EVIDENCE_UPLOADED_LABEL, True
    if status == "provided" and ref:
        return "provided_ref", EVIDENCE_LABEL["provided"], True
    if status == "provided":
        return "provided_no_ref", "Berstatus 'tercatat' tetapi referensi kosong", False
    return status, EVIDENCE_LABEL[status], False


def priority_matrix(materiality: str, severity: str) -> str:
    """Aturan prioritas (lihat priority_rule_table untuk penjelasannya)."""
    if materiality == "Tinggi" and severity in ("Tinggi", "Sedang"):
        return "Tinggi"
    if materiality == "Sedang" or severity == "Tinggi" or materiality == "Tinggi":
        return "Sedang"
    return "Rutin"


def priority_rule_table(cfg: RiskConfig) -> pd.DataFrame:
    rows = []
    for m in ("Tinggi", "Sedang", "Rendah"):
        row = {"Materialitas \\ Kelemahan data": f"Materialitas {m}"}
        for s in ("Tinggi", "Sedang", "Rendah"):
            row[f"Kelemahan {s}"] = priority_matrix(m, s)
        rows.append(row)
    return pd.DataFrame(rows)


def _materiality(calc_row, total_em: float, total_spend: float, cfg: RiskConfig):
    """Kembalikan (tingkat, pangsa, dasar). Dasar eksplisit agar alasan dapat dijelaskan."""
    if calc_row["status"] == STATUS_OK and total_em > 0:
        share = float(calc_row["emissions_kg"]) / total_em
        basis = "pangsa emisi"
    else:
        cur = (calc_row.get("currency") or "").upper()
        amt = calc_row.get("amount_num")
        if cur == SPEND_CURRENCY and pd.notna(amt) and total_spend > 0:
            share, basis = float(amt) / total_spend, "proxy: pangsa pengeluaran (emisi tidak dapat dihitung)"
        else:
            return "Sedang", float("nan"), "tidak dapat dinilai (diperlakukan Sedang secara konservatif)"
    level = "Tinggi" if share >= cfg.high_share else ("Sedang" if share >= cfg.medium_share else "Rendah")
    return level, share, basis


# --------------------------------------------------------------------------------------
# Temuan
# --------------------------------------------------------------------------------------
def build_findings(data: pd.DataFrame, validation_issues: pd.DataFrame, cfg: Optional[RiskConfig] = None) -> pd.DataFrame:
    """`data` = hasil merge_results(). Mengembalikan satu baris per temuan."""
    cfg = cfg or RiskConfig()
    cfg.validate()
    ok = data[data["status"] == STATUS_OK]
    total_em = float(ok["emissions_kg"].sum()) if len(ok) else 0.0
    spend_rows = data[(data["currency"].str.upper() == SPEND_CURRENCY) & (data["status"] != STATUS_EXCLUDED)]
    total_spend = float(spend_rows["amount_num"].sum()) if len(spend_rows) else 0.0

    by_row = {int(r["row_number"]): r for _, r in data.iterrows()}
    out: list[dict] = []

    def add(r, ftype, severity, reason, reco):
        level, share, basis = _materiality(r, total_em, total_spend, cfg)
        prio = priority_matrix(level, severity)
        share_txt = "n/a" if pd.isna(share) else f"{share:.2%}"
        out.append({
            "finding_type": ftype, "finding_label": FINDING_LABEL.get(ftype, ftype),
            "dimension": DIMENSION_OF.get(ftype, ""), "severity": severity, "priority": prio,
            "transaction_id": r["transaction_id"], "row_number": int(r["row_number"]),
            "supplier_name": r["supplier_name"] or "(kosong)", "item_category": r["item_category"],
            "emissions_kg": r["emissions_kg"], "materiality_level": level, "materiality_share": share,
            "materiality_basis": basis, "reason": reason,
            "priority_reason": (f"Prioritas {prio}: materialitas {level} ({share_txt}, {basis}; ambang Tinggi ≥ "
                                f"{cfg.high_share:.1%}, Sedang ≥ {cfg.medium_share:.1%}) dan kelemahan data {severity}."),
            "recommendation": reco,
        })

    # A. isu validasi -> temuan
    for _, iss in validation_issues.iterrows():
        if iss["issue_type"] not in FINDING_ISSUE_TYPES or int(iss["row_number"]) not in by_row:
            continue
        r = by_row[int(iss["row_number"])]
        t = iss["issue_type"]
        if t == "missing_required_field":
            sev = "Tinggi" if iss["field"] in CRITICAL_FIELDS else "Sedang"
        elif t == "invalid_value":
            sev = "Tinggi" if iss["level"] == "Error" else "Sedang"
        elif t == "duplicate_transaction":
            sev = "Tinggi" if iss["level"] == "Error" else "Sedang"
        else:
            sev = "Sedang"
        add(r, t, sev, iss["message"], iss["action"])

    # B-D. temuan dari hasil hitung dan bukti (tidak untuk baris duplikat yang dikecualikan)
    for _, r in data.iterrows():
        if r["status"] == STATUS_EXCLUDED:
            continue
        codes = set(filter(None, str(r["reason_codes"]).split(";")))
        cat = r["item_category"]
        if codes & {"unit_incompatible", "unit_unknown", "currency_mismatch"}:
            add(r, "unit_mismatch", "Tinggi", r["calc_message"],
                "Konfirmasi satuan/mata uang dan kuantitas pada surat jalan atau faktur, koreksi data, lalu hitung ulang. "
                "Sampai dikoreksi, transaksi ini TIDAK termasuk dalam total emisi.")
        if "unit_converted" in codes:
            add(r, "unit_mismatch", "Sedang",
                f"Satuan '{r['activity_unit']}' berbeda dari satuan standar faktor ({r['factor_unit']}); dikonversi otomatis: {r['conversion_note']}.",
                "Pastikan satuan pada dokumen sumber memang demikian (salah satuan dapat menggeser hasil 1.000x) dan seragamkan satuan input.")
        if "factor_missing" in codes:
            add(r, "missing_factor_or_source", "Tinggi", r["calc_message"],
                f"Tambahkan faktor emisi untuk '{cat}' dengan sumber yang dapat ditelusuri, atau minta data emisi dari pemasok. "
                "Sementara itu transaksi tidak dihitung (emisi bisa terlalu rendah).")
        if "factor_no_source" in codes:
            add(r, "missing_factor_or_source", "Sedang",
                f"Faktor {r['factor_id']} dipakai tanpa sumber/referensi yang lengkap.",
                "Lengkapi source_name dan source_reference faktor (atau lampirkan dokumen pemasok), atau ganti dengan faktor yang sumbernya jelas.")
        if "primary_without_supplier_factor" in codes:
            add(r, "missing_factor_or_source", "Sedang",
                "Data berlabel 'data pemasok (primer)' tetapi faktor spesifik pemasok tidak diisi; dihitung dengan faktor pustaka.",
                "Minta faktor emisi dari pemasok (kolom supplier_emission_factor) atau ubah label metode menjadi data sekunder.")
        if "factor_old" in codes:
            add(r, "factor_outdated", "Rendah",
                f"Faktor {r['factor_id']} terbit {r['factor_year']}, melewati batas usia {cfg.max_factor_age_years} tahun.",
                "Cari faktor yang lebih mutakhir atau dokumentasikan alasan memakai faktor lama.")
        if r["data_method"] == METHOD_SPEND:
            add(r, "estimation_method_used", "Rendah",
                "Emisi dihitung dari pengeluaran (estimasi), bukan dari data aktivitas fisik atau data pemasok.",
                "Jika transaksi ini material, minta data aktivitas fisik atau faktor spesifik pemasok agar tidak bergantung pada estimasi pengeluaran.")
        code, label, recorded = evidence_state(r)
        if not recorded:
            sev = "Sedang" if code == "partial" else "Tinggi"
            reco = {
                "missing": "Minta/unggah dokumen pendukung (faktur, surat jalan, bukti pembayaran) dan catat referensinya.",
                "requested": "Tindak lanjuti permintaan dokumen ke pemasok dan catat referensinya saat diterima.",
                "partial": "Lengkapi dokumen yang masih kurang agar rantai bukti utuh.",
                "provided_no_ref": "Isi referensi dokumen (nomor/nama file) atau ubah status bukti menjadi 'missing'.",
            }[code]
            add(r, "evidence_missing", sev, f"Status bukti: {label}.", reco)

    f = pd.DataFrame(out, columns=[c for c in FINDING_COLUMNS if c != "finding_id"])
    if f.empty:
        return pd.DataFrame(columns=FINDING_COLUMNS)
    f["_p"] = f["priority"].map(PRIORITY_ORDER)
    f["_s"] = f["severity"].map(SEVERITY_ORDER)
    f["_sh"] = f["materiality_share"].fillna(0)
    f = f.sort_values(["_p", "_sh", "_s", "row_number"], ascending=[False, False, False, True]).drop(columns=["_p", "_s", "_sh"])
    f = f.reset_index(drop=True)
    f.insert(0, "finding_id", [f"F-{i:03d}" for i in range(1, len(f) + 1)])
    return f


# --------------------------------------------------------------------------------------
# Kualitas data per dimensi
# --------------------------------------------------------------------------------------
def assess_quality(data: pd.DataFrame, findings: pd.DataFrame) -> pd.DataFrame:
    """Status & alasan per dimensi untuk tiap transaksi. Tidak ada skor gabungan."""
    ftypes = (findings.groupby("row_number")["finding_type"].apply(set).to_dict() if len(findings) else {})
    rows = []
    for _, r in data.iterrows():
        rn = int(r["row_number"])
        ft = ftypes.get(rn, set())
        codes = set(filter(None, str(r["reason_codes"]).split(";")))
        ev_code, ev_label, ev_ok = evidence_state(r)
        calc_ok = r["status"] == STATUS_OK
        d: dict = {"row_number": rn, "transaction_id": r["transaction_id"], "supplier_name": r["supplier_name"],
                   "item_category": r["item_category"], "status": r["status"], "emissions_kg": r["emissions_kg"]}

        # Kelengkapan
        if ft & {"missing_required_field", "invalid_value"}:
            d["Kelengkapan"] = ("Lemah", "Ada kolom wajib kosong atau nilai tidak valid.")
        else:
            d["Kelengkapan"] = ("Baik", "Semua kolom wajib terisi dan valid.")
        # Keterlacakan
        if not calc_ok:
            d["Keterlacakan"] = ("Lemah", "Tidak ada hasil hitung sehingga rantai input→faktor→metode tidak lengkap.")
        elif not ev_ok:
            d["Keterlacakan"] = ("Lemah", f"Bukti: {ev_label}.")
        elif ev_code == "partial" or "factor_no_source" in codes:
            d["Keterlacakan"] = ("Perhatian", "Faktor emisi tanpa sumber lengkap atau bukti hanya sebagian.")
        else:
            d["Keterlacakan"] = ("Baik", "Referensi bukti tercatat dan sumber faktor ada (belum diverifikasi).")
        # Relevansi
        if not calc_ok:
            d["Relevansi"] = ("Lemah", "Tidak ada faktor emisi yang relevan/kompatibel.")
        elif r["data_method"] == METHOD_SPEND:
            d["Relevansi"] = ("Perhatian", "Faktor berbasis pengeluaran kurang spesifik terhadap produk/pemasok.")
        elif "factor_old" in codes:
            d["Relevansi"] = ("Perhatian", "Faktor emisi berumur melebihi batas yang ditetapkan.")
        else:
            d["Relevansi"] = ("Baik", "Faktor berbasis aktivitas fisik/pemasok untuk kategori yang sama.")
        # Konsistensi
        if ft & {"duplicate_transaction"} or codes & {"unit_incompatible", "unit_unknown", "currency_mismatch"}:
            d["Konsistensi"] = ("Lemah", "Duplikasi atau satuan/mata uang tidak cocok.")
        elif "unit_converted" in codes or "inconsistent_reporting_period" in ft:
            d["Konsistensi"] = ("Perhatian", "Satuan dikonversi atau periode pelaporan tidak sejalan dengan tanggal.")
        else:
            d["Konsistensi"] = ("Baik", "Satuan, periode, dan ID konsisten.")
        # Ketidakpastian (kualitatif; tidak dikuantifikasi di MVP)
        if not calc_ok:
            d["Ketidakpastian"] = ("Lemah", "Tidak dapat dinilai karena tidak ada hasil hitung.")
        elif r["data_method"] == METHOD_SPEND:
            d["Ketidakpastian"] = ("Lemah", "Tinggi: estimasi dari pengeluaran dengan faktor rata-rata.")
        elif r["data_class"] == "Data pemasok (primer)" and ev_ok:
            d["Ketidakpastian"] = ("Baik", "Relatif lebih rendah: faktor spesifik pemasok (tetap klaim, belum diverifikasi).")
        else:
            d["Ketidakpastian"] = ("Perhatian", "Sedang: faktor generik atau klaim pemasok tanpa bukti.")
        rows.append(d)

    out = pd.DataFrame(rows)
    for dim in QUALITY_DIMENSIONS:
        out[f"{dim}_status"] = out[dim].map(lambda t: t[0])
        out[f"{dim}_reason"] = out[dim].map(lambda t: t[1])
    return out.drop(columns=QUALITY_DIMENSIONS)


def quality_overview(quality: pd.DataFrame) -> pd.DataFrame:
    """Jumlah transaksi per dimensi x status (Baik/Perhatian/Lemah)."""
    rows = []
    for dim in QUALITY_DIMENSIONS:
        vc = quality[f"{dim}_status"].value_counts()
        rows.append({"Dimensi": dim, "Baik": int(vc.get("Baik", 0)), "Perhatian": int(vc.get("Perhatian", 0)),
                     "Lemah": int(vc.get("Lemah", 0))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
# Ringkasan
# --------------------------------------------------------------------------------------
def summarize(data: pd.DataFrame, findings: pd.DataFrame) -> dict:
    counted = data[data["status"] != STATUS_EXCLUDED]
    ok = data[data["status"] == STATUS_OK]
    ev = [evidence_state(r) for _, r in counted.iterrows()]
    n_recorded = sum(1 for e in ev if e[2])
    return {
        "total_emissions_kg": float(ok["emissions_kg"].sum()) if len(ok) else 0.0,
        "n_rows": int(len(data)),
        "n_counted": int(len(counted)),
        "n_calculated": int(len(ok)),
        "n_rejected": int((data["status"] == STATUS_REJECTED).sum()),
        "n_excluded_duplicates": int((data["status"] == STATUS_EXCLUDED).sum()),
        "n_suppliers": int(counted["supplier_id"].replace("", np.nan).nunique()),
        "evidence_recorded_pct": (n_recorded / len(counted) * 100) if len(counted) else 0.0,
        "n_evidence_recorded": n_recorded,
        "n_estimate": int(ok["is_estimate"].fillna(False).astype(bool).sum()) if len(ok) else 0,
        "n_findings": int(len(findings)),
        "n_priority_high": int((findings["priority"] == "Tinggi").sum()) if len(findings) else 0,
        "n_priority_medium": int((findings["priority"] == "Sedang").sum()) if len(findings) else 0,
        "n_priority_routine": int((findings["priority"] == "Rutin").sum()) if len(findings) else 0,
        "emissions_by_class": ok.groupby("data_class")["emissions_kg"].sum().to_dict() if len(ok) else {},
    }
