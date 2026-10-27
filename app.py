"""TRACE ESG - antarmuka Streamlit (6 halaman).

Jalankan:  streamlit run app.py

Seluruh logika perhitungan/validasi/risiko ada di paket `modules/` (murni pandas, dapat diuji tanpa UI).
File ini hanya menyusun tampilan dan menyimpan data sesi.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.calculator import (
    STATUS_EXCLUDED, STATUS_OK, STATUS_REJECTED, calculate_all, emissions_by, load_factors, validate_factors,
)
from modules.config import (
    ALLOWED_METHODS, APP_NAME, APP_TAGLINE, DISCLAIMER, DUMMY_FACTOR_NOTICE, EVIDENCE_ALLOWED, EVIDENCE_LABEL,
    METHOD_LABEL, METHOD_VERSION, QUALITY_DIMENSIONS, TRANSACTION_OPTIONAL_COLUMNS, TRANSACTION_REQUIRED_COLUMNS,
    RiskConfig,
)
from modules.pipeline import run_pipeline
from modules.reporting import (
    LIMITATIONS, audit_trail_table, build_report_blocks, readiness_indicators, report_markdown, report_pdf,
    to_csv_bytes,
)
from modules.risk_engine import evidence_state, priority_rule_table, quality_overview
from modules.utils import fmt_factor, fmt_id
from modules.validation import normalize_unit, read_csv_flexible, validate_transactions

BASE = Path(__file__).resolve().parent
SAMPLE_TX = BASE / "data" / "sample_transactions.csv"
SAMPLE_EF = BASE / "data" / "emission_factors.csv"

PAGES = [
    "1. Overview Dashboard",
    "2. Data Import & Validation",
    "3. Scope 3 Calculator",
    "4. Evidence & Traceability",
    "5. Data Quality & Risk",
    "6. Readiness Report",
]
PRIO_BADGE = {"Tinggi": "🔴 Tinggi", "Sedang": "🟠 Sedang", "Rutin": "🟢 Rutin"}
QUAL_BADGE = {"Baik": "✅ Baik", "Perhatian": "⚠️ Perhatian", "Lemah": "⛔ Lemah"}
UNIT_CHOICES = ["kg", "t", "g", "L", "m3", "unit", "pcs", "paket"]

st.set_page_config(page_title="TRACE ESG", page_icon="🧾", layout="wide")


# --------------------------------------------------------------------------------------
# Status sesi & data
# --------------------------------------------------------------------------------------
def ensure_optional_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in TRANSACTION_OPTIONAL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("raw_df", None)
    ss.setdefault("dataset_name", "(belum ada data)")
    ss.setdefault("last_upload_sig", None)
    ss.setdefault("last_ef_sig", None)
    ss.setdefault("uploader_n", 0)
    ss.setdefault("_memo", None)
    if "factors" not in ss:
        ss["factors"] = load_factors(str(SAMPLE_EF))
        ss["factor_name"] = "emission_factors.csv (data dummy demo)"


def load_demo() -> None:
    st.session_state["raw_df"] = ensure_optional_cols(read_csv_flexible(str(SAMPLE_TX)))
    st.session_state["dataset_name"] = "sample_transactions.csv (sintetis)"


def sidebar_config() -> RiskConfig:
    with st.sidebar.expander("⚙️ Aturan & ambang batas", expanded=False):
        st.caption("Dipakai oleh kalkulator dan mesin risiko. Perubahan langsung menghitung ulang seluruh hasil.")
        hi = st.number_input("Materialitas TINGGI jika pangsa emisi ≥ (%)", 0.0, 100.0, 3.0, 0.5,
                             help="Pangsa sebuah transaksi terhadap total emisi yang dihitung.")
        mid = st.number_input("Materialitas SEDANG jika pangsa emisi ≥ (%)", 0.0, 100.0, 1.0, 0.5)
        age = st.number_input("Usia maksimum faktor emisi (tahun)", 0, 30, 5, 1,
                              help="Faktor yang lebih tua dari ini ditandai kurang relevan.")
        excl = st.checkbox("Kecualikan duplikat dari total emisi", value=True,
                           help="Baris duplikat kedua dst. tidak dihitung agar tidak terhitung ganda.")
    cfg = RiskConfig(high_share=hi / 100, medium_share=mid / 100, max_factor_age_years=int(age), exclude_duplicates=excl)
    try:
        cfg.validate()
    except ValueError:
        st.sidebar.error("Ambang Sedang harus ≤ ambang Tinggi. Memakai nilai default.")
        cfg = RiskConfig()
    return cfg


def get_analysis(cfg: RiskConfig):
    ss = st.session_state
    raw = ss["raw_df"]
    if raw is None:
        return None
    key = (int(pd.util.hash_pandas_object(raw, index=True).sum()),
           int(pd.util.hash_pandas_object(ss["factors"].astype(str), index=True).sum()),
           cfg.high_share, cfg.medium_share, cfg.max_factor_age_years, cfg.exclude_duplicates)
    memo = ss.get("_memo")
    if memo and memo[0] == key:
        return memo[1]
    analysis = run_pipeline(raw, ss["factors"], cfg)
    ss["_memo"] = (key, analysis)
    return analysis


def require_data(a):
    if a is None or a.data.empty:
        st.info("Belum ada data transaksi yang valid. Muat data demo atau unggah CSV di halaman **2. Data Import & Validation**.")
        if st.button("Muat data demo (100 transaksi sintetis)", key="demo_btn_" + str(id(a))):
            load_demo()
            st.rerun()
        st.stop()


def t_co2e(kg: float) -> str:
    return f"{fmt_id(kg / 1000, 2)} t CO₂e"


def disclaimer_box() -> None:
    st.info("ℹ️ " + DISCLAIMER)


def dummy_notice(a) -> None:
    ok = a.data[a.data["status"] == STATUS_OK]
    if len(ok) and ok["factor_is_dummy"].astype(bool).any():
        st.warning("🧪 " + DUMMY_FACTOR_NOTICE)


# --------------------------------------------------------------------------------------
# Halaman 1 - Dashboard
# --------------------------------------------------------------------------------------
def page_dashboard(a) -> None:
    st.title("Overview Dashboard")
    st.caption(f"{APP_NAME} · {APP_TAGLINE}")
    disclaimer_box()
    require_data(a)
    dummy_notice(a)
    s = a.summary

    c = st.columns(3)
    c[0].metric("Total estimasi emisi (belum diverifikasi)", t_co2e(s["total_emissions_kg"]),
                help="Jumlah emisi dari transaksi berstatus 'Dihitung'. Ini estimasi, bukan emisi terverifikasi.")
    c[1].metric("Transaksi dihitung / total", f"{s['n_calculated']} / {s['n_counted']}",
                help="Total tidak menghitung baris duplikat yang dikecualikan.")
    c[2].metric("Jumlah pemasok", s["n_suppliers"])
    c = st.columns(3)
    c[0].metric("Catatan dengan referensi bukti", f"{fmt_id(s['evidence_recorded_pct'], 1)}%",
                help="Referensi tercatat, BUKAN bukti terverifikasi.")
    c[1].metric("Catatan estimasi (berbasis pengeluaran)", s["n_estimate"])
    c[2].metric("Temuan prioritas Tinggi", s["n_priority_high"],
                help=f"Dari total {s['n_findings']} temuan.")

    if s["n_rejected"] or s["n_excluded_duplicates"]:
        st.warning(f"{s['n_rejected']} transaksi ditolak (tidak masuk total) dan {s['n_excluded_duplicates']} duplikat "
                   "dikecualikan. Total emisi di atas dapat lebih rendah dari kenyataan sampai data diperbaiki.")

    st.subheader("Emisi per kelompok")
    ok = a.data[a.data["status"] == STATUS_OK]
    tab1, tab2, tab3 = st.tabs(["Per pemasok (10 terbesar)", "Per kategori barang/jasa", "Per kelas data"])
    with tab1:
        g = emissions_by(ok, "supplier_name").head(10)
        st.bar_chart(g.set_index("supplier_name")["emissions_kg"].div(1000).rename("t CO₂e"))
    with tab2:
        g = emissions_by(ok, "item_category")
        st.bar_chart(g.set_index("item_category")["emissions_kg"].div(1000).rename("t CO₂e"))
    with tab3:
        g = emissions_by(ok, "data_class")
        st.bar_chart(g.set_index("data_class")["emissions_kg"].div(1000).rename("t CO₂e"))
        st.caption("Kelas data menunjukkan seberapa kuat dasar angka: data pemasok, data aktivitas sekunder, atau estimasi pengeluaran.")

    st.subheader("Temuan prioritas")
    f = a.findings
    if f.empty:
        st.success("Tidak ada temuan.")
    else:
        top = f[f["priority"] == "Tinggi"].head(10).copy()
        if top.empty:
            top = f.head(10).copy()
        top["priority"] = top["priority"].map(PRIO_BADGE)
        st.dataframe(top[["finding_id", "priority", "finding_label", "transaction_id", "supplier_name",
                          "priority_reason", "recommendation"]].rename(columns={
            "finding_id": "ID", "priority": "Prioritas", "finding_label": "Temuan", "transaction_id": "Transaksi",
            "supplier_name": "Pemasok", "priority_reason": "Alasan prioritas", "recommendation": "Rekomendasi"}),
            hide_index=True)
        st.caption("Rincian lengkap dan filter ada di halaman 5. Data Quality & Risk.")


# --------------------------------------------------------------------------------------
# Halaman 2 - Import & validasi
# --------------------------------------------------------------------------------------
def page_import(a, cfg) -> None:
    st.title("Data Import & Validation")
    disclaimer_box()
    ss = st.session_state

    tab_up, tab_manual, tab_ef = st.tabs(["Unggah CSV transaksi", "Input manual", "Pustaka faktor emisi"])

    with tab_up:
        c1, c2 = st.columns([2, 1])
        with c1:
            up = st.file_uploader("Unggah CSV transaksi pembelian", type=["csv"], key=f"tx_up_{ss['uploader_n']}",
                                  help="Gunakan kolom seperti data/sample_transactions.csv. Pemisah koma atau titik koma.")
            if up is not None:
                sig = (up.name, up.size)
                if ss["last_upload_sig"] != sig:
                    try:
                        df = read_csv_flexible(up)
                    except Exception as e:  # CSV rusak / encoding
                        st.error(f"Berkas tidak dapat dibaca sebagai CSV: {e}. Pastikan format CSV (UTF-8) dan baris header ada.")
                    else:
                        ss["raw_df"] = ensure_optional_cols(df)
                        ss["dataset_name"] = up.name
                        ss["last_upload_sig"] = sig
                        st.rerun()  # di luar try agar tidak tertelan except
        with c2:
            st.write("")
            if st.button("Gunakan data demo (sintetis)"):
                load_demo()
                st.rerun()
            st.download_button("Unduh templat/contoh CSV", data=SAMPLE_TX.read_bytes(),
                               file_name="sample_transactions.csv", mime="text/csv")
        st.caption("Kolom wajib: " + ", ".join(TRANSACTION_REQUIRED_COLUMNS) +
                   ". Kolom opsional: supplier_emission_factor (kg CO₂e per satuan aktivitas, klaim pemasok).")

    with tab_manual:
        manual_form(ss)

    with tab_ef:
        ef_panel(ss)

    st.divider()
    if a is None:
        st.info("Belum ada data. Unggah CSV, input manual, atau gunakan data demo.")
        return

    v = a.validation
    st.subheader(f"Hasil validasi · {ss['dataset_name']}")
    if not v.schema_ok:
        st.error("Kolom wajib tidak lengkap: " + ", ".join(v.missing_columns) +
                 ". Tambahkan kolom tersebut pada CSV lalu unggah ulang (lihat templat).")
    c = st.columns(4)
    c[0].metric("Baris data", len(v.clean))
    c[1].metric("Error", v.n_errors, help="Masalah yang menghalangi atau merusak perhitungan baris tersebut.")
    c[2].metric("Peringatan", v.n_warnings)
    c[3].metric("Kolom tambahan diabaikan", len(v.extra_columns), help=", ".join(v.extra_columns) or "tidak ada")

    st.markdown("**Pratinjau data** (50 baris pertama)")
    prev_cols = [c_ for c_ in TRANSACTION_REQUIRED_COLUMNS if c_ in v.clean.columns]
    st.dataframe(v.clean[prev_cols].head(50), hide_index=True)

    if v.issues.empty:
        st.success("Tidak ada masalah validasi.")
        return
    st.markdown("**Masalah validasi** — setiap pesan menyertakan tindakan perbaikan")
    c1, c2 = st.columns(2)
    lv = c1.multiselect("Tingkat", ["Error", "Peringatan"], default=["Error", "Peringatan"])
    types = sorted(v.issues["issue_type"].unique())
    ty = c2.multiselect("Jenis isu", types, default=types)
    iss = v.issues[v.issues["level"].isin(lv) & v.issues["issue_type"].isin(ty)]
    st.dataframe(iss.rename(columns={"row_number": "Baris", "transaction_id": "Transaksi", "issue_type": "Jenis",
                                     "field": "Kolom", "level": "Tingkat", "message": "Pesan", "action": "Tindakan"}),
                 hide_index=True)
    st.caption("Duplikat dan satuan/faktor tidak cocok juga muncul sebagai temuan di halaman 5; "
               "baris yang ditolak tidak masuk total emisi.")


def manual_form(ss) -> None:
    cats = sorted(set(ss["factors"]["item_category"]))
    with st.form("manual_form", clear_on_submit=False):
        st.markdown("Tambahkan satu transaksi ke dataset aktif (disimpan dalam sesi).")
        c = st.columns(3)
        tid = c[0].text_input("transaction_id", value=f"TRX-MAN-{(0 if ss['raw_df'] is None else len(ss['raw_df'])) + 1:03d}")
        tdate = c[1].date_input("transaction_date", value=date(2025, 6, 30))
        period = c[2].text_input("reporting_period", value="2025")
        c = st.columns(3)
        sid = c[0].text_input("supplier_id", value="S99")
        sname = c[1].text_input("supplier_name", value="")
        cat = c[2].selectbox("item_category", cats + ["(lain-lain, isi di bawah)"])
        cat_other = st.text_input("Kategori lain (opsional; jika diisi menggantikan pilihan di atas)", value="")
        desc = st.text_input("item_description", value="")
        c = st.columns(4)
        qty = c[0].number_input("activity_quantity", min_value=0.0, value=0.0, step=1.0, format="%.3f")
        unit = c[1].selectbox("activity_unit", UNIT_CHOICES)
        amount = c[2].number_input("purchase_amount", min_value=0.0, value=0.0, step=1000.0)
        cur = c[3].selectbox("currency", ["IDR", "USD"])
        c = st.columns(3)
        method = c[0].selectbox("data_method", ALLOWED_METHODS, format_func=lambda m: f"{m} — {METHOD_LABEL[m]}")
        sef = c[1].number_input("supplier_emission_factor (opsional; 0 = kosong)", min_value=0.0, value=0.0, format="%.6f")
        evs = c[2].selectbox("evidence_status", EVIDENCE_ALLOWED, format_func=lambda x: f"{x} — {EVIDENCE_LABEL[x]}", index=3)
        evref = st.text_input("evidence_reference (nomor/nama dokumen)", value="")
        submitted = st.form_submit_button("Tambahkan transaksi")
    if submitted:
        row = {
            "transaction_id": tid, "transaction_date": tdate.isoformat(), "supplier_id": sid, "supplier_name": sname,
            "item_category": cat_other.strip() or ("" if cat.startswith("(lain") else cat), "item_description": desc,
            "activity_quantity": ("" if qty == 0 else f"{qty:g}"), "activity_unit": unit,
            "purchase_amount": f"{amount:g}", "currency": cur, "data_method": method,
            "evidence_reference": evref, "evidence_status": evs, "reporting_period": period,
            "supplier_emission_factor": ("" if sef == 0 else f"{sef:g}"),
            "evidence_file_name": "", "evidence_file_sha256": "", "assumption_note": "",
        }
        base = ss["raw_df"] if ss["raw_df"] is not None else pd.DataFrame(columns=list(row.keys()))
        ss["raw_df"] = pd.concat([ensure_optional_cols(base), pd.DataFrame([row])], ignore_index=True)
        if ss["dataset_name"].startswith("(belum"):
            ss["dataset_name"] = "input manual"
        st.rerun()


def ef_panel(ss) -> None:
    f = ss["factors"]
    st.caption(f"Pustaka aktif: **{ss['factor_name']}**")
    if f["is_dummy"].any():
        st.warning("🧪 " + DUMMY_FACTOR_NOTICE)
    problems = validate_factors(f)
    if problems:
        st.error("Masalah pada pustaka faktor:\n\n" + "\n".join(f"- {p}" for p in problems))
    else:
        st.success("Skema dan nilai pustaka faktor valid.")
    up = st.file_uploader("Ganti pustaka faktor emisi (CSV)", type=["csv"], key="ef_up",
                          help="Kolom: " + ", ".join(["factor_id", "item_category", "factor_value", "factor_unit",
                                                     "source_name", "source_reference", "publication_year",
                                                     "geography", "boundary_notes", "method_notes"]))
    if up is not None and ss["last_ef_sig"] != (up.name, up.size):
        try:
            new_factors = load_factors(up)
        except Exception as e:
            st.error(f"Pustaka faktor tidak dapat dipakai: {e}")
        else:
            ss["factors"] = new_factors
            ss["factor_name"] = up.name
            ss["last_ef_sig"] = (up.name, up.size)
            st.rerun()  # di luar try agar tidak tertelan except
    cols = ["factor_id", "item_category", "factor_value", "factor_unit", "source_name", "source_reference",
            "publication_year", "geography", "boundary_notes", "method_notes"]
    st.dataframe(f[cols], hide_index=True)


# --------------------------------------------------------------------------------------
# Halaman 3 - Kalkulator
# --------------------------------------------------------------------------------------
def page_calculator(a, cfg) -> None:
    st.title("Scope 3 Calculator")
    st.caption("Kategori 1 — Purchased Goods and Services")
    disclaimer_box()
    require_data(a)
    dummy_notice(a)
    with st.expander("Metode perhitungan", expanded=False):
        st.markdown(
            "**Emisi (kg CO₂e) = Data aktivitas × Faktor emisi**, dengan satuan yang kompatibel.\n\n"
            "- *Data pemasok (primer)*: memakai `supplier_emission_factor` jika ada (klaim pemasok, belum diverifikasi).\n"
            "- *Data aktivitas sekunder*: kuantitas fisik (dikonversi ke satuan faktor, mis. ton→kg) × faktor fisik.\n"
            "- *Estimasi berbasis pengeluaran*: pengeluaran IDR × faktor kg CO₂e/IDR.\n"
            "- Data fisik **tidak pernah** dikalikan dengan faktor pengeluaran. Jika satuan tidak cocok, faktor tidak ada, "
            "atau input tidak valid, perhitungan **ditolak** dan transaksi ditandai.\n\n"
            f"Versi metode: `{METHOD_VERSION}`. Contoh ilustrasi: 500 kg × 2 kg CO₂e/kg = 1.000 kg CO₂e (angka faktor hanya contoh).")

    d = a.data
    st.subheader("Hasil perhitungan per transaksi")
    c = st.columns(4)
    status_f = c[0].multiselect("Status", [STATUS_OK, STATUS_REJECTED, STATUS_EXCLUDED], default=[STATUS_OK, STATUS_REJECTED, STATUS_EXCLUDED])
    class_opts = sorted(d["data_class"].dropna().unique())
    class_f = c[1].multiselect("Kelas data", class_opts, default=class_opts)
    cat_opts = sorted(d["item_category"].replace("", pd.NA).dropna().unique())
    cat_f = c[2].multiselect("Kategori", cat_opts, default=cat_opts)
    q = c[3].text_input("Cari ID / pemasok", "")
    m = d["status"].isin(status_f) & (d["data_class"].isin(class_f) | d["data_class"].isna()) & \
        (d["item_category"].isin(cat_f) | (d["item_category"] == ""))
    if q:
        m &= d["transaction_id"].str.contains(q, case=False) | d["supplier_name"].str.contains(q, case=False)
    view = d[m]
    show = view[["transaction_id", "supplier_name", "item_category", "data_class", "is_estimate", "activity_input",
                 "converted_quantity", "converted_unit", "factor_id", "factor_value", "factor_unit", "factor_source",
                 "factor_year", "emissions_kg", "status", "calc_message"]].rename(columns={
        "transaction_id": "Transaksi", "supplier_name": "Pemasok", "item_category": "Kategori", "data_class": "Kelas data",
        "is_estimate": "Estimasi?", "activity_input": "Input aktivitas", "converted_quantity": "Kuantitas terkonversi",
        "converted_unit": "Satuan", "factor_id": "ID faktor", "factor_value": "Faktor", "factor_unit": "Satuan faktor",
        "factor_source": "Sumber faktor", "factor_year": "Tahun", "emissions_kg": "Emisi (kg CO₂e)", "status": "Status",
        "calc_message": "Keterangan"})
    st.dataframe(show, hide_index=True, column_config={
        "Emisi (kg CO₂e)": st.column_config.NumberColumn(format="%.2f"),
        "Faktor": st.column_config.NumberColumn(format="%.6f"),
        "Kuantitas terkonversi": st.column_config.NumberColumn(format="%.3f"),
        "Tahun": st.column_config.NumberColumn(format="%d"),
    })
    st.caption(f"{len(view)} baris ditampilkan · total emisi pada tampilan: {t_co2e(view.loc[view['status'] == STATUS_OK, 'emissions_kg'].sum())} (estimasi).")

    rej = d[d["status"] == STATUS_REJECTED]
    if len(rej):
        with st.expander(f"⛔ {len(rej)} perhitungan ditolak — alasan dan tindakan"):
            st.dataframe(rej[["transaction_id", "supplier_name", "item_category", "activity_input", "calc_message"]]
                         .rename(columns={"transaction_id": "Transaksi", "supplier_name": "Pemasok", "item_category": "Kategori",
                                          "activity_input": "Input", "calc_message": "Alasan penolakan"}), hide_index=True)

    st.divider()
    st.subheader("Uji satu perhitungan (what-if)")
    st.caption("Coba kombinasi input untuk melihat bagaimana aturan satuan dan faktor bekerja. Tidak mengubah dataset.")
    cats = sorted(set(st.session_state["factors"]["item_category"]))
    with st.form("whatif"):
        c = st.columns(5)
        cat = c[0].selectbox("Kategori", cats)
        qty = c[1].number_input("Kuantitas", min_value=0.0, value=500.0, format="%.3f")
        unit = c[2].selectbox("Satuan", UNIT_CHOICES)
        method = c[3].selectbox("Metode", ALLOWED_METHODS, format_func=lambda m_: METHOD_LABEL[m_])
        amount = c[4].number_input("Nilai pembelian (IDR)", min_value=0.0, value=10_000_000.0, step=100000.0)
        go = st.form_submit_button("Hitung")
    if go:
        raw = pd.DataFrame([{
            "transaction_id": "WHATIF-1", "transaction_date": "2025-06-30", "supplier_id": "X", "supplier_name": "What-if",
            "item_category": cat, "item_description": "", "activity_quantity": f"{qty:g}", "activity_unit": unit,
            "purchase_amount": f"{amount:g}", "currency": "IDR", "data_method": method, "evidence_reference": "",
            "evidence_status": "missing", "reporting_period": "2025", "supplier_emission_factor": ""}])
        val = validate_transactions(raw)
        res = calculate_all(val.clean, st.session_state["factors"], cfg).iloc[0]
        if res["status"] == STATUS_OK:
            st.success(f"{res['formula']}")
            st.write(f"Faktor `{res['factor_id']}` · sumber: {res['factor_source']} · tahun {res['factor_year']} · "
                     f"kelas data: {res['data_class']}")
            if res["assumptions"]:
                st.caption("Asumsi: " + res["assumptions"])
        else:
            st.error(f"Ditolak: {res['calc_message']}")


# --------------------------------------------------------------------------------------
# Halaman 4 - Evidence & traceability
# --------------------------------------------------------------------------------------
def page_evidence(a, cfg) -> None:
    st.title("Evidence & Traceability")
    disclaimer_box()
    require_data(a)
    d = a.data

    tab_trace, tab_list = st.tabs(["Telusuri satu angka", "Daftar penelusuran seluruh transaksi"])
    with tab_trace:
        order = d.assign(_e=d["emissions_kg"].fillna(-1)).sort_values("_e", ascending=False)
        labels = {}
        for _, r in order.iterrows():
            em = "tidak dihitung" if pd.isna(r["emissions_kg"]) else t_co2e(r["emissions_kg"])
            labels[f"{r['transaction_id']} · {r['supplier_name'] or '(tanpa pemasok)'} · {r['item_category']} · {em} (baris {int(r['row_number'])})"] = int(r["row_number"])
        choice = st.selectbox("Pilih transaksi (diurutkan dari emisi terbesar)", list(labels.keys()))
        rn = labels[choice]
        r = d[d["row_number"] == rn].iloc[0]
        ev_code, ev_label, ev_ok = evidence_state(r)

        st.markdown("#### Rantai penelusuran: Data → Faktor → Metode → Bukti")
        c = st.columns(4)
        with c[0].container(border=True):
            st.markdown("**① Data aktivitas**")
            st.write(f"ID: `{r['transaction_id']}`")
            st.write(f"Pemasok: {r['supplier_name'] or '(kosong)'} (`{r['supplier_id']}`)")
            st.write(f"Tanggal: {r['transaction_date']} · Periode: {r['reporting_period']}")
            st.write(f"Aktivitas: {r['activity_input'] if isinstance(r['activity_input'], str) else r['activity_quantity'] + ' ' + r['activity_unit']}")
            st.write(f"Nilai: {r['purchase_amount']} {r['currency']}")
        with c[1].container(border=True):
            st.markdown("**② Faktor emisi**")
            if r["status"] == STATUS_OK:
                st.write(f"`{r['factor_id']}`: {fmt_factor(r['factor_value'])} {r['factor_unit']}")
                st.write(f"Sumber: {r['factor_source']}")
                st.write(f"Referensi: {r['factor_source_reference']}")
                st.write(f"Tahun: {r['factor_year']} · Wilayah: {r['factor_geography']}")
                st.write(f"Batas: {r['factor_boundary']}")
                if r["factor_is_dummy"]:
                    st.warning("Faktor DUMMY (demo)")
                if not r["factor_has_source"]:
                    st.error("Sumber faktor tidak lengkap")
            else:
                st.error("Tidak ada faktor yang dipakai.")
        with c[2].container(border=True):
            st.markdown("**③ Metode & hasil**")
            st.write(f"Kelas data: {r['data_class']}")
            if r["status"] == STATUS_OK:
                st.write(f"Rumus: {r['formula']}")
                st.write(f"Konversi: {r['conversion_note']}")
                st.caption(f"Asumsi: {r['assumptions'] or '-'}")
            else:
                st.error(f"{r['status']}: {r['calc_message']}")
            st.caption(f"Versi metode: {r['method_version']}")
        with c[3].container(border=True):
            st.markdown("**④ Bukti**")
            st.write(f"Status: {ev_label}")
            st.write(f"Referensi: {r['evidence_reference'] or '-'}")
            if r["evidence_file_name"]:
                st.write(f"Berkas: {r['evidence_file_name']}")
                st.caption(f"SHA-256: {r['evidence_file_sha256'][:16]}…")
            st.caption("Status ini hanya pencatatan; aplikasi tidak memverifikasi isi dokumen.")
        if r["status"] == STATUS_OK:
            st.success(f"**{t_co2e(r['emissions_kg'])}** (estimasi, belum diverifikasi) ← {r['formula']}")

        fr = a.findings[a.findings["row_number"] == rn]
        st.markdown("**Temuan terkait transaksi ini**")
        if fr.empty:
            st.success("Tidak ada temuan untuk transaksi ini.")
        else:
            x = fr.copy(); x["priority"] = x["priority"].map(PRIO_BADGE)
            st.dataframe(x[["finding_id", "priority", "finding_label", "severity", "reason", "recommendation"]]
                         .rename(columns={"finding_id": "ID", "priority": "Prioritas", "finding_label": "Temuan",
                                          "severity": "Severity", "reason": "Alasan", "recommendation": "Rekomendasi"}),
                         hide_index=True)

        st.markdown("#### Catat / perbarui metadata bukti")
        st.caption("Jika berkas tidak diunggah, referensi tetap boleh dicatat, tetapi tidak pernah ditandai terverifikasi.")
        with st.form(f"evform_{rn}"):
            ref = st.text_input("Referensi dokumen (no. faktur / nama file)", value=r["evidence_reference"])
            cur = r["evidence_status"] if r["evidence_status"] in EVIDENCE_ALLOWED else "missing"
            stat = st.selectbox("Status bukti", EVIDENCE_ALLOWED, index=EVIDENCE_ALLOWED.index(cur),
                                format_func=lambda x: EVIDENCE_LABEL[x])
            f = st.file_uploader("Unggah berkas bukti (opsional; hanya dihitung hash-nya, isi tidak dibaca)")
            if st.form_submit_button("Simpan metadata bukti"):
                pos = rn - 2
                raw = st.session_state["raw_df"].copy()
                raw.at[pos, "evidence_reference"] = ref.strip()
                raw.at[pos, "evidence_status"] = stat
                if f is not None:
                    data = f.getvalue()
                    raw.at[pos, "evidence_file_name"] = f.name
                    raw.at[pos, "evidence_file_sha256"] = hashlib.sha256(data).hexdigest()
                    if stat == "missing":
                        raw.at[pos, "evidence_status"] = "provided"
                    if not ref.strip():
                        raw.at[pos, "evidence_reference"] = f.name
                st.session_state["raw_df"] = raw
                st.rerun()

    with tab_list:
        rows = []
        for _, r in d.iterrows():
            code, label, ok_ = evidence_state(r)
            rows.append({
                "Transaksi": r["transaction_id"], "Pemasok": r["supplier_name"], "Dokumen/referensi": r["evidence_reference"],
                "Faktor emisi": ("-" if pd.isna(r["factor_value"]) else f"{r['factor_id']}: {fmt_factor(r['factor_value'])} {r['factor_unit']}"),
                "Metode": r["data_class"], "Asumsi": r["assumptions"] or "-", "Periode": r["reporting_period"],
                "Status bukti": label, "Rantai lengkap": "Ya" if r["trace_chain_complete"] else "Tidak", "_code": code,
            })
        tl = pd.DataFrame(rows)
        sel = st.multiselect("Filter status bukti", sorted(tl["Status bukti"].unique()), default=sorted(tl["Status bukti"].unique()))
        st.dataframe(tl[tl["Status bukti"].isin(sel)].drop(columns=["_code"]), hide_index=True)
        st.download_button("Unduh daftar penelusuran (CSV)", data=to_csv_bytes(audit_trail_table(a)),
                           file_name="trace_esg_audit_trail.csv", mime="text/csv")


# --------------------------------------------------------------------------------------
# Halaman 5 - Kualitas data & risiko
# --------------------------------------------------------------------------------------
def page_risk(a, cfg) -> None:
    st.title("Data Quality & Risk")
    disclaimer_box()
    require_data(a)

    with st.expander("Bagaimana prioritas ditentukan? (aturan transparan, bukan skor kotak-hitam)", expanded=False):
        st.markdown(
            f"1. **Severity** (kelemahan data) ditetapkan tetap per jenis temuan, mis. satuan tidak cocok/faktor tidak ada = Tinggi, "
            "bukti hilang = Tinggi (sebagian = Sedang), satuan dikonversi/periode tidak konsisten = Sedang, metode estimasi = Rendah.\n"
            f"2. **Materialitas** = pangsa emisi transaksi terhadap total: Tinggi ≥ {cfg.high_share:.1%}, Sedang ≥ {cfg.medium_share:.1%} "
            "(ubah di sidebar). Transaksi yang tidak dapat dihitung memakai proxy pangsa pengeluaran.\n"
            "3. **Prioritas** = matriks materialitas × severity di bawah. Setiap temuan menampilkan alasannya.")
        st.dataframe(priority_rule_table(cfg), hide_index=True)
        st.caption("Ambang dan matriks adalah heuristik internal prototipe, bukan standar resmi atau opini assurance.")

    st.subheader("Kualitas data per dimensi")
    st.caption("Kelengkapan, keterlacakan, relevansi, konsistensi, dan ketidakpastian dinilai terpisah. "
               "Data yang lengkap tidak otomatis akurat. Tidak ada skor gabungan.")
    qo = quality_overview(a.quality)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(qo, hide_index=True)
    with c2:
        st.bar_chart(qo.set_index("Dimensi")[["Baik", "Perhatian", "Lemah"]], color=["#2E7D6B", "#E0A526", "#C0392B"])

    st.subheader("Daftar temuan")
    f = a.findings
    if f.empty:
        st.success("Tidak ada temuan.")
        return
    c = st.columns(3)
    pf = c[0].multiselect("Prioritas", ["Tinggi", "Sedang", "Rutin"], default=["Tinggi", "Sedang", "Rutin"])
    types = sorted(f["finding_label"].unique())
    tf = c[1].multiselect("Jenis temuan", types, default=types)
    sf = c[2].multiselect("Severity", ["Tinggi", "Sedang", "Rendah"], default=["Tinggi", "Sedang", "Rendah"])
    fv = f[f["priority"].isin(pf) & f["finding_label"].isin(tf) & f["severity"].isin(sf)].copy()
    shown = fv.copy()
    shown["priority"] = shown["priority"].map(PRIO_BADGE)
    shown["materiality_share"] = shown["materiality_share"] * 100
    st.dataframe(shown[["finding_id", "priority", "finding_label", "severity", "transaction_id", "supplier_name",
                        "materiality_level", "materiality_share", "reason", "recommendation"]].rename(columns={
        "finding_id": "ID", "priority": "Prioritas", "finding_label": "Temuan", "severity": "Severity",
        "transaction_id": "Transaksi", "supplier_name": "Pemasok", "materiality_level": "Materialitas",
        "materiality_share": "Pangsa (%)", "reason": "Alasan temuan", "recommendation": "Rekomendasi"}),
        hide_index=True, column_config={"Pangsa (%)": st.column_config.NumberColumn(format="%.2f")})
    st.caption(f"{len(fv)} dari {len(f)} temuan. Urutan: prioritas, lalu pangsa emisi terbesar.")
    st.download_button("Unduh temuan (CSV)", data=to_csv_bytes(f), file_name="trace_esg_findings.csv", mime="text/csv")

    if len(fv):
        pick = st.selectbox("Jelaskan prioritas temuan", fv["finding_id"].tolist(),
                            format_func=lambda i: f"{i} · {fv.set_index('finding_id').loc[i, 'finding_label']} · {fv.set_index('finding_id').loc[i, 'transaction_id']}")
        row = fv.set_index("finding_id").loc[pick]
        st.markdown(f"**{PRIO_BADGE[row['priority']]}** — {row['priority_reason']}")
        st.write(f"**Alasan temuan:** {row['reason']}")
        st.write(f"**Rekomendasi:** {row['recommendation']}")

    st.subheader("Status kualitas per transaksi")
    q = a.quality
    cols = ["transaction_id", "supplier_name", "item_category"] + [f"{d_}_status" for d_ in QUALITY_DIMENSIONS]
    qq = q[cols].copy()
    for d_ in QUALITY_DIMENSIONS:
        qq[f"{d_}_status"] = qq[f"{d_}_status"].map(QUAL_BADGE)
    qq.columns = ["Transaksi", "Pemasok", "Kategori"] + QUALITY_DIMENSIONS
    st.dataframe(qq, hide_index=True)
    opts = {f"{r['transaction_id']} (baris {int(r['row_number'])})": int(r["row_number"]) for _, r in q.iterrows()}
    k = st.selectbox("Lihat alasan per dimensi untuk transaksi", list(opts.keys()))
    qr = q[q["row_number"] == opts[k]].iloc[0]
    st.dataframe(pd.DataFrame({"Dimensi": QUALITY_DIMENSIONS,
                               "Status": [QUAL_BADGE[qr[f"{d_}_status"]] for d_ in QUALITY_DIMENSIONS],
                               "Alasan": [qr[f"{d_}_reason"] for d_ in QUALITY_DIMENSIONS]}), hide_index=True)


# --------------------------------------------------------------------------------------
# Halaman 6 - Laporan
# --------------------------------------------------------------------------------------
def page_report(a, cfg) -> None:
    st.title("Readiness Report")
    disclaimer_box()
    require_data(a)
    dummy_notice(a)
    ss = st.session_state

    st.subheader("Indikator kesiapan")
    st.dataframe(readiness_indicators(a), hide_index=True)
    st.caption("Heuristik internal prototipe untuk membantu memprioritaskan perbaikan — bukan skor, standar resmi, atau opini assurance.")

    blocks = build_report_blocks(a, dataset_name=ss["dataset_name"], factor_name=ss["factor_name"], generated_at=datetime.now())
    md = report_markdown(blocks)
    st.subheader("Ekspor")
    c = st.columns(4)
    try:
        pdf = report_pdf(blocks)
        c[0].download_button("📄 Laporan PDF", data=pdf, file_name="trace_esg_readiness_report.pdf", mime="application/pdf")
    except ImportError:
        c[0].warning("Paket reportlab belum terpasang; PDF tidak tersedia (pip install reportlab).")
    c[1].download_button("📝 Laporan Markdown", data=md.encode("utf-8"), file_name="trace_esg_readiness_report.md", mime="text/markdown")
    c[2].download_button("📊 Jejak perhitungan (CSV)", data=to_csv_bytes(audit_trail_table(a)),
                         file_name="trace_esg_audit_trail.csv", mime="text/csv")
    c[3].download_button("🗂️ Temuan (CSV)", data=to_csv_bytes(a.findings), file_name="trace_esg_findings.csv", mime="text/csv")
    c = st.columns(2)
    c[0].download_button("Kualitas data per dimensi (CSV)", data=to_csv_bytes(a.quality),
                         file_name="trace_esg_data_quality.csv", mime="text/csv")
    c[1].download_button("Data transaksi + metadata bukti terbaru (CSV)", data=to_csv_bytes(ss["raw_df"]),
                         file_name="transactions_with_evidence_metadata.csv", mime="text/csv")

    with st.expander("Pratinjau isi laporan", expanded=True):
        st.markdown(md)
    with st.expander("Fitur yang belum diimplementasikan"):
        st.markdown("\n".join(f"- {x}" for x in [
            "Login multi-user dan peran (preparer/reviewer)", "Integrasi ERP / sistem pemasok", "Kategori Scope 3 selain Kategori 1; Scope 1 & 2",
            "Penyimpanan persisten (SQLite) dan riwayat versi", "Kuantifikasi ketidakpastian statistik", "Kurs dan penyesuaian inflasi",
            "Pembacaan isi dokumen bukti (OCR)", "Pengiriman permintaan dokumen ke pemasok"]))


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main() -> None:
    init_state()
    st.markdown(
        "<style>.block-container{padding-top:1.6rem;} "
        "div[data-testid='stMetricValue']{font-size:1.5rem;}</style>", unsafe_allow_html=True)
    st.sidebar.markdown(f"### 🧾 {APP_NAME}")
    st.sidebar.caption(APP_TAGLINE)
    page = st.sidebar.radio("Navigasi", PAGES, key="page")
    cfg = sidebar_config()
    st.sidebar.caption(f"Dataset aktif: **{st.session_state['dataset_name']}**")
    with st.sidebar.expander("Panduan demo (5–7 menit)"):
        st.markdown(
            "1. **Import**: unggah `data/sample_transactions.csv`, lihat validasi\n"
            "2. **Calculator**: lihat faktor, metode, hasil\n"
            "3. **Evidence**: pilih satu angka → telusuri ke bukti\n"
            "4. **Risk**: baris bermasalah (estimasi, bukti hilang, satuan)\n"
            "5. **Report**: prioritas & ekspor laporan")
    if st.sidebar.button("Atur ulang data sesi"):
        for k in ("raw_df", "last_upload_sig", "_memo"):
            st.session_state[k] = None
        st.session_state["uploader_n"] = st.session_state.get("uploader_n", 0) + 1
        st.session_state["dataset_name"] = "(belum ada data)"
        st.rerun()
    st.sidebar.warning(DISCLAIMER)

    a = get_analysis(cfg)
    if page == PAGES[0]:
        page_dashboard(a)
    elif page == PAGES[1]:
        page_import(a, cfg)
    elif page == PAGES[2]:
        page_calculator(a, cfg)
    elif page == PAGES[3]:
        page_evidence(a, cfg)
    elif page == PAGES[4]:
        page_risk(a, cfg)
    else:
        page_report(a, cfg)


main()
