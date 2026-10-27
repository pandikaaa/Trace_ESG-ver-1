"""Validasi data transaksi: kolom wajib, nilai kosong, tipe data, satuan, dan duplikasi.

Fungsi di sini tidak menghitung emisi. Hasilnya berupa:
  * `ValidationResult.clean`  : DataFrame dengan kolom ter-parse (quantity_num, amount_num, ...)
  * `ValidationResult.issues` : satu baris per masalah, dengan pesan yang dapat ditindaklanjuti
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import IO, Union

import pandas as pd

from .config import (
    ALLOWED_METHODS, EVIDENCE_ALLOWED, MANDATORY_VALUE_FIELDS, TRANSACTION_OPTIONAL_COLUMNS,
    TRANSACTION_REQUIRED_COLUMNS, UNIT_TABLE,
)

ISSUE_COLUMNS = ["row_number", "transaction_id", "issue_type", "field", "level", "message", "action"]

# Jenis isu validasi yang diteruskan menjadi temuan risiko (sisanya hanya informasi impor)
FINDING_ISSUE_TYPES = {
    "missing_required_field", "invalid_value", "duplicate_transaction", "inconsistent_reporting_period",
}


@dataclass
class ValidationResult:
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    issues: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=ISSUE_COLUMNS))
    clean: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def schema_ok(self) -> bool:
        return not self.missing_columns

    @property
    def n_errors(self) -> int:
        return int((self.issues["level"] == "Error").sum()) if len(self.issues) else 0

    @property
    def n_warnings(self) -> int:
        return int((self.issues["level"] == "Peringatan").sum()) if len(self.issues) else 0


def read_csv_flexible(source: Union[str, IO[bytes], IO[str]]) -> pd.DataFrame:
    """Baca CSV sebagai teks (tanpa konversi otomatis) agar nilai asli dapat divalidasi.

    Mendukung pemisah koma atau titik koma. Nama kolom dirapikan (trim + huruf kecil).
    """
    if hasattr(source, "read"):
        raw = source.read()
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    else:
        with open(source, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    first_line = text.splitlines()[0] if text.strip() else ""
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip().lower() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    return df


def _issue(rows: list, row_number: int, tid: str, typ: str, fld: str, level: str, msg: str, action: str) -> None:
    rows.append({"row_number": row_number, "transaction_id": tid, "issue_type": typ, "field": fld,
                 "level": level, "message": msg, "action": action})


def _to_number(s: str):
    s = (s or "").strip()
    if s == "":
        return float("nan"), "blank"
    try:
        return float(s.replace(",", "")) if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s) else float(s), "ok"
    except ValueError:
        return float("nan"), "invalid"


def normalize_unit(unit: str):
    """Kembalikan (kanonik, keluarga, pengali) atau None jika satuan tidak dikenal."""
    return UNIT_TABLE.get((unit or "").strip().lower())


def validate_transactions(df_in: pd.DataFrame) -> ValidationResult:
    """Validasi DataFrame transaksi (seluruh kolom bertipe teks)."""
    df = df_in.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    res = ValidationResult()
    res.missing_columns = [c for c in TRANSACTION_REQUIRED_COLUMNS if c not in df.columns]
    known = set(TRANSACTION_REQUIRED_COLUMNS) | set(TRANSACTION_OPTIONAL_COLUMNS)
    res.extra_columns = [c for c in df.columns if c not in known]
    if res.missing_columns:
        rows: list = []
        _issue(rows, 0, "", "missing_column", ", ".join(res.missing_columns), "Error",
               f"Kolom wajib tidak ditemukan: {', '.join(res.missing_columns)}.",
               "Tambahkan kolom tersebut pada CSV (lihat data/sample_transactions.csv sebagai templat) lalu unggah ulang.")
        res.issues = pd.DataFrame(rows, columns=ISSUE_COLUMNS)
        res.clean = df
        return res

    for c in TRANSACTION_OPTIONAL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df.fillna("").astype(str).reset_index(drop=True)
    df["row_number"] = df.index + 2  # +2: baris header = 1

    issues: list = []
    # --- kolom ter-parse -------------------------------------------------------------
    qty, amt, sef = [], [], []
    qty_state, amt_state = [], []
    for _, r in df.iterrows():
        q, qs = _to_number(r["activity_quantity"]); qty.append(q); qty_state.append(qs)
        a, as_ = _to_number(r["purchase_amount"]); amt.append(a); amt_state.append(as_)
        s, ss = _to_number(r["supplier_emission_factor"])
        sef.append(s if ss == "ok" else float("nan"))
        if ss == "invalid":
            _issue(issues, int(r["row_number"]), r["transaction_id"], "invalid_value", "supplier_emission_factor",
                   "Peringatan", "supplier_emission_factor bukan angka; nilai diabaikan.",
                   "Isi dengan angka (kg CO2e per satuan aktivitas) atau kosongkan.")
    df["quantity_num"], df["amount_num"], df["supplier_ef_num"] = qty, amt, sef
    df["date_parsed"] = pd.to_datetime(df["transaction_date"], format="%Y-%m-%d", errors="coerce")

    blocking = pd.Series(False, index=df.index)

    for i, r in df.iterrows():
        rn, tid = int(r["row_number"]), r["transaction_id"]
        label = f"Baris {rn}" + (f" ({tid})" if tid else "")
        # nilai wajib kosong
        for f in MANDATORY_VALUE_FIELDS:
            if r[f] == "":
                _issue(issues, rn, tid, "missing_required_field", f, "Error",
                       f"{label}: kolom '{f}' kosong.",
                       f"Lengkapi '{f}' dari dokumen sumber lalu unggah ulang.")
                blocking[i] = True
        # tipe data
        if qty_state[i] == "invalid" or (qty_state[i] == "ok" and qty[i] <= 0):
            _issue(issues, rn, tid, "invalid_value", "activity_quantity", "Error",
                   f"{label}: activity_quantity '{r['activity_quantity']}' tidak valid (harus angka > 0).",
                   "Perbaiki jumlah aktivitas sesuai dokumen pembelian (mis. surat jalan / faktur).")
            blocking[i] = True
        if amt_state[i] == "invalid" or (amt_state[i] == "ok" and amt[i] < 0):
            _issue(issues, rn, tid, "invalid_value", "purchase_amount", "Error",
                   f"{label}: purchase_amount '{r['purchase_amount']}' tidak valid (harus angka >= 0).",
                   "Perbaiki nilai pembelian; retur/kredit sebaiknya dicatat terpisah.")
            blocking[i] = True
        if r["transaction_date"] != "" and pd.isna(r["date_parsed"]):
            _issue(issues, rn, tid, "invalid_value", "transaction_date", "Error",
                   f"{label}: transaction_date '{r['transaction_date']}' bukan tanggal valid (format YYYY-MM-DD).",
                   "Gunakan format YYYY-MM-DD dan pastikan tanggalnya ada di kalender.")
            blocking[i] = True
        if r["data_method"] != "" and r["data_method"] not in ALLOWED_METHODS:
            _issue(issues, rn, tid, "invalid_value", "data_method", "Error",
                   f"{label}: data_method '{r['data_method']}' tidak dikenal.",
                   f"Gunakan salah satu: {', '.join(ALLOWED_METHODS)}.")
            blocking[i] = True
        if r["evidence_status"] != "" and r["evidence_status"] not in EVIDENCE_ALLOWED:
            _issue(issues, rn, tid, "invalid_value", "evidence_status", "Peringatan",
                   f"{label}: evidence_status '{r['evidence_status']}' tidak dikenal; diperlakukan sebagai 'missing'.",
                   f"Gunakan salah satu: {', '.join(EVIDENCE_ALLOWED)}.")
        if r["reporting_period"] != "" and not re.fullmatch(r"\d{4}", r["reporting_period"]):
            _issue(issues, rn, tid, "invalid_value", "reporting_period", "Error",
                   f"{label}: reporting_period '{r['reporting_period']}' bukan tahun 4 digit.",
                   "Isi tahun pelaporan, mis. 2025.")
            blocking[i] = True
        # satuan dikenal?
        if r["activity_unit"] != "" and normalize_unit(r["activity_unit"]) is None:
            _issue(issues, rn, tid, "unknown_unit", "activity_unit", "Peringatan",
                   f"{label}: satuan '{r['activity_unit']}' tidak ada di tabel satuan aplikasi.",
                   "Gunakan satuan baku (kg, t, g, L, m3, unit, paket) atau konversi manual sebelum impor.")
        # konsistensi periode
        if re.fullmatch(r"\d{4}", r["reporting_period"]) and pd.notna(r["date_parsed"]):
            if int(r["reporting_period"]) != r["date_parsed"].year:
                _issue(issues, rn, tid, "inconsistent_reporting_period", "reporting_period", "Peringatan",
                       f"{label}: tanggal transaksi {r['transaction_date']} berada di tahun "
                       f"{r['date_parsed'].year}, tetapi reporting_period = {r['reporting_period']}.",
                       "Periksa cut-off: pindahkan transaksi ke periode yang benar atau koreksi tanggalnya.")
    df["blocking_error"] = blocking

    # --- duplikasi -------------------------------------------------------------------
    content_cols = ["supplier_id", "transaction_date", "item_category", "activity_quantity",
                    "activity_unit", "purchase_amount", "currency"]
    df["dup_kind"] = ""
    df["duplicate_of"] = ""
    df["dup_excluded"] = False
    seen_id: dict[str, int] = {}
    seen_content: dict[tuple, int] = {}
    # baris dengan nilai kosong pada kolom isi tidak dianggap duplikat isi (terlalu lemah sebagai bukti)
    for i, r in df.iterrows():
        tid = r["transaction_id"]
        ckey = tuple(r[c] for c in content_cols)
        content_ok = all(v != "" for v in ckey)
        first_by_id = seen_id.get(tid) if tid else None
        first_by_content = seen_content.get(ckey) if content_ok else None
        if first_by_id is not None:
            j = first_by_id
            same_content = tuple(df.at[j, c] for c in content_cols) == ckey
            kind = "exact_row" if same_content else "id_only"
            df.at[i, "dup_kind"], df.at[i, "duplicate_of"] = kind, df.at[j, "transaction_id"]
            df.at[i, "dup_excluded"] = same_content
            df.at[j, "dup_kind"] = df.at[j, "dup_kind"] or "original"
            msg = ("ID transaksi muncul lebih dari sekali dengan isi identik (kemungkinan impor ganda)."
                   if same_content else
                   "ID transaksi muncul lebih dari sekali dengan isi BERBEDA.")
            for k in (j, i):
                _issue(issues, int(df.at[k, "row_number"]), tid, "duplicate_transaction", "transaction_id",
                       "Error" if k == i else "Peringatan",
                       f"Baris {int(df.at[k, 'row_number'])} ({tid}): {msg}",
                       "Pertahankan satu catatan; baris duplikat dikecualikan dari total emisi." if same_content
                       else "Periksa mana catatan yang benar dan beri ID unik; kedua baris belum dikecualikan.")
        elif first_by_content is not None:
            j = first_by_content
            df.at[i, "dup_kind"], df.at[i, "duplicate_of"] = "content_only", df.at[j, "transaction_id"]
            df.at[i, "dup_excluded"] = True
            df.at[j, "dup_kind"] = df.at[j, "dup_kind"] or "original"
            for k in (j, i):
                _issue(issues, int(df.at[k, "row_number"]), df.at[k, "transaction_id"], "duplicate_transaction",
                       "transaction_id", "Error" if k == i else "Peringatan",
                       f"Baris {int(df.at[k, 'row_number'])} ({df.at[k, 'transaction_id']}): isi transaksi identik dengan "
                       f"{df.at[j, 'transaction_id']} (pemasok, tanggal, kategori, jumlah, satuan, nilai sama) tetapi ID berbeda.",
                       "Konfirmasi apakah ini pembelian berulang yang sah; jika bukan, hapus salah satu. "
                       "Secara default baris kedua dikecualikan dari total.")
        if tid and tid not in seen_id:
            seen_id[tid] = i
        if content_ok and ckey not in seen_content:
            seen_content[ckey] = i

    res.issues = pd.DataFrame(issues, columns=ISSUE_COLUMNS).sort_values(
        ["row_number", "issue_type"], kind="stable").reset_index(drop=True)
    res.clean = df
    return res
