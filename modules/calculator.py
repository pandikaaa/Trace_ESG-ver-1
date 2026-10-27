"""Perhitungan emisi Scope 3 Kategori 1 (Purchased Goods and Services).

Rumus (deterministik, memakai Decimal agar sama persis dengan hitungan manual):

    Emisi (kg CO2e) = Data Aktivitas (dalam satuan penyebut faktor) x Faktor Emisi

* Berbasis aktivitas fisik : kuantitas dikonversi ke satuan penyebut faktor (mis. ton -> kg).
* Berbasis pengeluaran     : purchase_amount (IDR) x faktor kg CO2e/IDR.
* Data pemasok (primer)    : memakai `supplier_emission_factor` jika ada; jika tidak ada, jatuh ke
                             faktor pustaka dan ditandai sebagai data sekunder.

Perhitungan DITOLAK (tidak ada angka dihasilkan) bila satuan tidak kompatibel, faktor tidak tersedia,
atau input tidak valid. Tidak ada konversi tersembunyi antara data fisik dan faktor berbasis pengeluaran.
"""
from __future__ import annotations

import io
from decimal import Decimal
from typing import IO, Optional, Union

import pandas as pd

from .config import (
    FACTOR_REQUIRED_COLUMNS, METHOD_LABEL, METHOD_PRIMARY, METHOD_SECONDARY, METHOD_SPEND,
    METHOD_VERSION, SPEND_CURRENCY, UNIT_TABLE, RiskConfig,
)
from .utils import fmt_factor, fmt_id
from .validation import normalize_unit

STATUS_OK = "Dihitung"
STATUS_REJECTED = "Tidak dihitung"
STATUS_EXCLUDED = "Dikecualikan (duplikat)"

RESULT_COLUMNS = [
    "transaction_id", "row_number", "status", "calc_message", "reason_codes", "data_method",
    "data_class", "is_estimate", "activity_input", "converted_quantity", "converted_unit",
    "conversion_note", "factor_id", "factor_value", "factor_unit", "factor_source",
    "factor_source_reference", "factor_year", "factor_geography", "factor_boundary",
    "factor_method_notes", "factor_basis", "factor_is_dummy", "factor_has_source",
    "emissions_kg", "formula", "assumptions", "method_version", "trace_chain_complete",
]


class UnitMismatchError(ValueError):
    """Satuan aktivitas tidak dapat dikonversi ke satuan penyebut faktor emisi."""


# --------------------------------------------------------------------------------------
# Faktor emisi
# --------------------------------------------------------------------------------------
def split_factor_unit(factor_unit: str) -> tuple[str, str]:
    """'kg CO2e/kg' -> ('kg CO2e', 'kg'). Penyebut kosong jika tidak ada '/'."""
    if "/" not in (factor_unit or ""):
        return (factor_unit or "").strip(), ""
    num, den = factor_unit.rsplit("/", 1)
    return num.strip(), den.strip()


def load_factors(source: Union[str, IO[bytes], IO[str]]) -> pd.DataFrame:
    """Baca & siapkan pustaka faktor emisi dari CSV. Melempar ValueError jika skema salah."""
    if hasattr(source, "read"):
        raw = source.read()
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    else:
        df = pd.read_csv(source, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in FACTOR_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Kolom faktor emisi tidak lengkap: {', '.join(missing)}")
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    df["factor_value_num"] = pd.to_numeric(df["factor_value"], errors="coerce")
    df["publication_year_num"] = pd.to_numeric(df["publication_year"], errors="coerce")
    dens = df["factor_unit"].map(lambda u: split_factor_unit(u)[1])
    info = dens.map(normalize_unit)
    df["den_unit"] = [i[0] if i else "" for i in info]
    df["den_family"] = [i[1] if i else "" for i in info]
    df["den_mult"] = [i[2] if i else float("nan") for i in info]
    df["basis"] = df["den_family"].map(lambda f: "spend" if f == "mata_uang" else ("physical" if f else "unknown"))
    df["has_source"] = (df["source_name"] != "") & (df["source_reference"] != "")
    df["is_dummy"] = df["source_name"].str.upper().str.contains("DUMMY")
    return df


def validate_factors(f: pd.DataFrame) -> list[str]:
    """Daftar masalah pada pustaka faktor (kosong jika baik)."""
    msgs: list[str] = []
    for _, r in f.iterrows():
        if pd.isna(r["factor_value_num"]) or r["factor_value_num"] < 0:
            msgs.append(f"{r['factor_id']}: factor_value '{r['factor_value']}' tidak valid.")
        if r["basis"] == "unknown":
            msgs.append(f"{r['factor_id']}: satuan faktor '{r['factor_unit']}' tidak dapat diurai.")
    dups = f[f["factor_id"].duplicated(keep=False)]["factor_id"].unique()
    msgs += [f"factor_id ganda: {d}" for d in dups]
    return msgs


# --------------------------------------------------------------------------------------
# Inti hitung
# --------------------------------------------------------------------------------------
def convert_quantity(quantity, unit: str, target_unit: str) -> tuple[Decimal, Decimal]:
    """Konversi kuantitas dari `unit` ke `target_unit`. Mengembalikan (nilai, pengali).

    Melempar UnitMismatchError bila satuan tidak dikenal atau berbeda keluarga (mis. kg vs unit).
    """
    a, b = normalize_unit(unit), normalize_unit(target_unit)
    if a is None:
        raise UnitMismatchError(f"Satuan '{unit}' tidak dikenal.")
    if b is None:
        raise UnitMismatchError(f"Satuan faktor '{target_unit}' tidak dikenal.")
    if a[1] != b[1]:
        raise UnitMismatchError(f"Satuan '{unit}' ({a[1]}) tidak kompatibel dengan '{target_unit}' ({b[1]}).")
    mult = Decimal(str(a[2])) / Decimal(str(b[2]))
    return Decimal(str(quantity)) * mult, mult


def compute_emission(quantity, unit: str, factor_value, factor_unit: str):
    """Emisi = kuantitas (dikonversi) x faktor. Mengembalikan (emisi_kg: Decimal, kuantitas_terkonversi, satuan, pengali)."""
    _, den = split_factor_unit(factor_unit)
    q_conv, mult = convert_quantity(quantity, unit, den)
    emission = q_conv * Decimal(str(factor_value))
    return emission, q_conv, normalize_unit(den)[0], mult


def _empty(tid, rn, status, msg, codes, method) -> dict:
    d = {c: None for c in RESULT_COLUMNS}
    d.update(transaction_id=tid, row_number=rn, status=status, calc_message=msg,
             reason_codes=";".join(codes), data_method=method, method_version=METHOD_VERSION,
             emissions_kg=float("nan"), is_estimate=(method == METHOD_SPEND), trace_chain_complete=False,
             data_class=METHOD_LABEL.get(method, "-"), factor_is_dummy=False, factor_has_source=False,
             assumptions="")
    return d


def _pick_factor(cands: pd.DataFrame) -> pd.Series:
    """Pilih faktor: publikasi terbaru, lalu factor_id (urutan deterministik)."""
    return cands.sort_values(["publication_year_num", "factor_id"], ascending=[False, True]).iloc[0]


def _reporting_year(r) -> Optional[int]:
    try:
        return int(r["reporting_period"])
    except (ValueError, TypeError):
        return None


def calculate_row(r: pd.Series, factors: pd.DataFrame, cfg: RiskConfig) -> dict:
    tid, rn = r["transaction_id"], int(r["row_number"])
    method = r["data_method"]
    cat = r["item_category"]

    if bool(r.get("dup_excluded", False)) and cfg.exclude_duplicates:
        return _empty(tid, rn, STATUS_EXCLUDED,
                      f"Duplikat dari {r['duplicate_of']}; dikecualikan agar tidak terhitung ganda.",
                      ["excluded_duplicate"], method)
    if method not in (METHOD_PRIMARY, METHOD_SECONDARY, METHOD_SPEND):
        return _empty(tid, rn, STATUS_REJECTED, "data_method kosong/tidak dikenal; metode tidak dapat dipilih.",
                      ["method_invalid"], method)
    if not cat:
        return _empty(tid, rn, STATUS_REJECTED, "item_category kosong; faktor tidak dapat dicari.",
                      ["input_invalid"], method)

    codes: list[str] = []
    assumptions: list[str] = []
    cat_f = factors[factors["item_category"] == cat]

    # ------------------------------------------------------------------ berbasis pengeluaran
    if method == METHOD_SPEND:
        cur = (r["currency"] or "").strip()
        amount = r["amount_num"]
        if pd.isna(amount) or amount < 0:
            return _empty(tid, rn, STATUS_REJECTED, "purchase_amount kosong/tidak valid.", ["input_invalid"], method)
        if cur.upper() != SPEND_CURRENCY:
            return _empty(tid, rn, STATUS_REJECTED,
                          f"Mata uang '{cur}' tidak kompatibel: faktor berbasis pengeluaran tersedia dalam {SPEND_CURRENCY}. "
                          "Tidak ada kurs yang diasumsikan.", ["currency_mismatch"], method)
        cands = cat_f[cat_f["basis"] == "spend"]
        if cands.empty:
            return _empty(tid, rn, STATUS_REJECTED,
                          f"Tidak ada faktor emisi berbasis pengeluaran untuk kategori '{cat}'.",
                          ["factor_missing"], method)
        fr = _pick_factor(cands)
        em, q_conv, q_unit, mult = compute_emission(amount, SPEND_CURRENCY, fr["factor_value_num"], fr["factor_unit"])
        act_text = f"{fmt_id(amount, 0)} {SPEND_CURRENCY}"
        conv_note = "Tanpa konversi"
        codes.append("spend_based")
        assumptions.append("Pengeluaran nominal IDR tanpa penyesuaian inflasi/harga; hasil adalah estimasi kasar.")
        data_class, factor_basis = METHOD_LABEL[METHOD_SPEND], "spend"

    # ------------------------------------------------------------------ berbasis aktivitas fisik / primer
    else:
        q, unit = r["quantity_num"], (r["activity_unit"] or "").strip()
        if pd.isna(q) or q <= 0 or not unit:
            return _empty(tid, rn, STATUS_REJECTED,
                          "activity_quantity/activity_unit kosong atau tidak valid; perhitungan fisik ditolak.",
                          ["input_invalid"], method)
        unit_info = normalize_unit(unit)
        if unit_info is None:
            return _empty(tid, rn, STATUS_REJECTED,
                          f"Satuan '{unit}' tidak dikenal; tidak dapat dicocokkan dengan faktor emisi.",
                          ["unit_unknown"], method)
        act_text = f"{fmt_id(q, 3).rstrip('0').rstrip(',')} {unit}"
        use_supplier = (method == METHOD_PRIMARY and pd.notna(r.get("supplier_ef_num", float("nan")))
                        and r["supplier_ef_num"] > 0 and unit_info[1] not in ("mata_uang", "mata_uang_asing"))
        if use_supplier:
            fr = pd.Series({
                "factor_id": f"SUPPLIER-{r['supplier_id']}", "factor_value_num": r["supplier_ef_num"],
                "factor_unit": f"kg CO2e/{unit_info[0]}", "source_name": "Data pemasok (diklaim, belum diverifikasi)",
                "source_reference": r["evidence_reference"], "publication_year_num": _reporting_year(r),
                "geography": "-", "boundary_notes": "Sesuai klaim pemasok (batas tidak diverifikasi)",
                "method_notes": "Faktor spesifik pemasok dari kolom supplier_emission_factor",
                "has_source": bool(r["evidence_reference"]), "is_dummy": False,
            })
            data_class = METHOD_LABEL[METHOD_PRIMARY]
            assumptions.append("Faktor emisi adalah klaim pemasok; belum diverifikasi independen.")
            if not fr["has_source"]:
                codes.append("factor_no_source")
        else:
            if method == METHOD_PRIMARY:
                codes.append("primary_without_supplier_factor")
                assumptions.append("Berlabel data pemasok namun supplier_emission_factor kosong; "
                                   "diperlakukan sebagai data sekunder dengan faktor pustaka.")
            cands = cat_f[cat_f["basis"] == "physical"]
            if cands.empty:
                has_any = not cat_f.empty
                msg = (f"Kategori '{cat}' hanya memiliki faktor berbasis pengeluaran; data fisik tidak dikalikan dengan "
                       "faktor pengeluaran." if has_any else f"Kategori '{cat}' tidak ada di pustaka faktor emisi.")
                return _empty(tid, rn, STATUS_REJECTED, msg, ["factor_missing"], method)
            compat = cands[cands["den_family"] == unit_info[1]]
            if compat.empty:
                std = ", ".join(sorted(set(cands["factor_unit"])))
                return _empty(tid, rn, STATUS_REJECTED,
                              f"Satuan '{unit}' tidak kompatibel dengan faktor kategori '{cat}' ({std}). "
                              "Perhitungan ditolak; koreksi satuan atau konfirmasi data fisiknya.",
                              ["unit_incompatible"], method)
            fr = _pick_factor(compat)
            data_class = METHOD_LABEL[METHOD_SECONDARY]
            if fr["is_dummy"]:
                assumptions.append("Faktor emisi adalah data dummy ilustratif untuk demo.")
            if not fr["has_source"]:
                codes.append("factor_no_source")
        try:
            em, q_conv, q_unit, mult = compute_emission(q, unit, fr["factor_value_num"], fr["factor_unit"])
        except UnitMismatchError as e:  # pertahanan berlapis; seharusnya sudah tersaring di atas
            return _empty(tid, rn, STATUS_REJECTED, str(e), ["unit_incompatible"], method)
        if unit_info[0] != q_unit and not (unit_info[1] == "jumlah" and q_unit in ("unit", "pcs")):
            codes.append("unit_converted")
            conv_note = f"{act_text} x {fmt_id(float(mult), 6).rstrip('0').rstrip(',')} = {fmt_id(float(q_conv), 3)} {q_unit}"
            assumptions.append(f"Satuan dikonversi dari '{unit}' ke '{q_unit}' (pengali {float(mult):g}); "
                               "pastikan satuan di dokumen sumber memang demikian.")
        else:
            conv_note = "Tanpa konversi"
        factor_basis = "physical"

    # ------------------------------------------------------------------ atribut umum hasil
    ryear = _reporting_year(r)
    fyear = fr["publication_year_num"]
    if ryear and pd.notna(fyear) and ryear - int(fyear) > cfg.max_factor_age_years and not str(fr["factor_id"]).startswith("SUPPLIER-"):
        codes.append("factor_old")
        assumptions.append(f"Faktor terbit {int(fyear)}, lebih dari {cfg.max_factor_age_years} tahun sebelum periode {ryear}.")
    if method == METHOD_SPEND and fr["is_dummy"]:
        assumptions.append("Faktor emisi adalah data dummy ilustratif untuk demo.")
    if method == METHOD_SPEND and not fr["has_source"]:
        codes.append("factor_no_source")
    if r.get("assumption_note", ""):
        assumptions.append(f"Catatan pengguna: {r['assumption_note']}")

    em_q = em.quantize(Decimal("0.000001"))
    fv = float(fr["factor_value_num"])
    d = {c: None for c in RESULT_COLUMNS}
    d.update(
        transaction_id=tid, row_number=rn, status=STATUS_OK, reason_codes=";".join(codes), data_method=method,
        data_class=data_class, is_estimate=(method == METHOD_SPEND), activity_input=act_text,
        converted_quantity=float(q_conv), converted_unit=q_unit, conversion_note=conv_note,
        factor_id=fr["factor_id"], factor_value=fv, factor_unit=fr["factor_unit"],
        factor_source=fr["source_name"] or "(tidak ada sumber)", factor_source_reference=fr["source_reference"] or "(tidak ada)",
        factor_year=(int(fyear) if pd.notna(fyear) else None), factor_geography=fr["geography"],
        factor_boundary=fr["boundary_notes"], factor_method_notes=fr["method_notes"], factor_basis=factor_basis,
        factor_is_dummy=bool(fr["is_dummy"]), factor_has_source=bool(fr["has_source"]),
        emissions_kg=float(em_q),
        formula=f"{fmt_id(float(q_conv), 3)} {q_unit} × {fmt_factor(fv)} {fr['factor_unit']} = {fmt_id(float(em_q), 2)} kg CO2e",
        assumptions=" | ".join(assumptions), method_version=METHOD_VERSION, calc_message="OK",
    )
    d["trace_chain_complete"] = all(d[k] not in (None, "") for k in
                                    ("factor_id", "factor_value", "factor_unit", "converted_quantity", "data_class", "formula"))
    return d


def calculate_all(clean: pd.DataFrame, factors: pd.DataFrame, cfg: Optional[RiskConfig] = None) -> pd.DataFrame:
    """Hitung seluruh transaksi. Urutan baris hasil = urutan baris masukan (deterministik)."""
    cfg = cfg or RiskConfig()
    rows = [calculate_row(r, factors, cfg) for _, r in clean.iterrows()]
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def emissions_by(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Total emisi (kg CO2e) per kolom pengelompokan, hanya transaksi berstatus 'Dihitung'."""
    ok = df[df["status"] == STATUS_OK]
    out = ok.groupby(col, dropna=False)["emissions_kg"].agg(["sum", "count"]).reset_index()
    out.columns = [col, "emissions_kg", "n_transactions"]
    return out.sort_values("emissions_kg", ascending=False).reset_index(drop=True)
