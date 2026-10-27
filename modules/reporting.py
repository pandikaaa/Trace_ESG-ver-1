"""Laporan Kesiapan (Readiness Report) dan ekspor CSV/Markdown/PDF.

Laporan dibangun dari satu model blok (judul, paragraf, tabel) sehingga isi Markdown dan PDF identik.
Laporan TIDAK menyatakan emisi 'terverifikasi' dan selalu memuat disclaimer.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

import pandas as pd

from .calculator import STATUS_EXCLUDED, STATUS_OK, STATUS_REJECTED
from .config import (
    APP_NAME, DISCLAIMER, DUMMY_FACTOR_NOTICE, FINDING_LABEL, METHOD_LABEL, METHOD_VERSION, QUALITY_DIMENSIONS,
)
from .pipeline import Analysis
from .risk_engine import evidence_state, priority_rule_table, quality_overview
from .utils import fmt_factor, fmt_id

# --------------------------------------------------------------------------------------
# Ekspor CSV
# --------------------------------------------------------------------------------------
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def audit_trail_table(a: Analysis) -> pd.DataFrame:
    """Jejak perhitungan lengkap per transaksi (input -> faktor -> metode -> asumsi -> bukti)."""
    d = a.data
    ev = [evidence_state(r) for _, r in d.iterrows()]
    out = pd.DataFrame({
        "transaction_id": d["transaction_id"], "supplier_name": d["supplier_name"], "item_category": d["item_category"],
        "reporting_period": d["reporting_period"], "status_hitung": d["status"], "kelas_data": d["data_class"],
        "input_aktivitas": d["activity_input"], "kuantitas_terkonversi": d["converted_quantity"],
        "satuan_terkonversi": d["converted_unit"], "faktor_id": d["factor_id"], "faktor_nilai": d["factor_value"],
        "faktor_satuan": d["factor_unit"], "faktor_sumber": d["factor_source"],
        "faktor_referensi": d["factor_source_reference"], "faktor_tahun": d["factor_year"],
        "faktor_dummy": d["factor_is_dummy"], "emisi_kg_co2e": d["emissions_kg"], "rumus": d["formula"],
        "asumsi": d["assumptions"], "versi_metode": d["method_version"], "referensi_bukti": d["evidence_reference"],
        "status_bukti": [e[1] for e in ev], "pesan_hitung": d["calc_message"],
    })
    return out


# --------------------------------------------------------------------------------------
# Indikator kesiapan (heuristik internal prototipe)
# --------------------------------------------------------------------------------------
def readiness_indicators(a: Analysis) -> pd.DataFrame:
    s, d = a.summary, a.data
    counted = d[d["status"] != STATUS_EXCLUDED]
    ok = d[d["status"] == STATUS_OK]
    n = max(len(counted), 1)
    pct_calc = len(ok) / n * 100
    pct_ev = s["evidence_recorded_pct"]
    pct_src = (ok["factor_has_source"].astype(bool) & ~ok["factor_is_dummy"].astype(bool)).mean() * 100 if len(ok) else 0
    em_tot = ok["emissions_kg"].sum()
    pct_est_em = (ok.loc[ok["is_estimate"].astype(bool), "emissions_kg"].sum() / em_tot * 100) if em_tot else 0
    n_chain = int(ok["trace_chain_complete"].astype(bool).sum())

    def lvl(pct, good=100.0, mid=80.0):
        return "Terpenuhi" if pct >= good else ("Sebagian" if pct >= mid else "Belum")

    rows = [
        ("Transaksi yang berhasil dihitung", f"{len(ok)} dari {len(counted)} ({pct_calc:.1f}%)", lvl(pct_calc),
         "Transaksi yang ditolak tidak masuk total sehingga total bisa terlalu rendah."),
        ("Referensi bukti tercatat", f"{s['n_evidence_recorded']} dari {len(counted)} ({pct_ev:.1f}%)", lvl(pct_ev),
         "Hanya mencatat referensi; isi dokumen belum diverifikasi oleh aplikasi."),
        ("Faktor emisi dengan sumber yang dapat ditelusuri (bukan dummy)", f"{pct_src:.1f}% transaksi dihitung", lvl(pct_src),
         "Faktor berlabel DUMMY pada data demo tidak dihitung sebagai bersumber."),
        ("Rantai input-faktor-metode lengkap", f"{n_chain} dari {len(ok)}", lvl(n_chain / max(len(ok), 1) * 100),
         "Mengecek kelengkapan rantai, bukan kebenaran isinya."),
        ("Porsi emisi dari estimasi berbasis pengeluaran", f"{pct_est_em:.1f}% dari total emisi",
         "Terpenuhi" if pct_est_em <= 20 else ("Sebagian" if pct_est_em <= 50 else "Belum"),
         "Semakin tinggi porsinya, semakin besar ketidakpastian."),
        ("Temuan prioritas Tinggi yang masih terbuka", f"{s['n_priority_high']} temuan",
         "Terpenuhi" if s["n_priority_high"] == 0 else "Belum", "Perlu ditindaklanjuti lebih dulu."),
    ]
    return pd.DataFrame(rows, columns=["Indikator", "Nilai", "Status", "Catatan"])


# --------------------------------------------------------------------------------------
# Model laporan
# --------------------------------------------------------------------------------------
LIMITATIONS = [
    "Prototipe untuk demonstrasi kompetisi; cakupan hanya Scope 3 Kategori 1 (Purchased Goods and Services).",
    "Faktor emisi pada data demo adalah DATA DUMMY ILUSTRATIF, bukan faktor resmi. Untuk data nyata, "
    "faktor, batas, dan metode harus ditinjau oleh tenaga ahli yang kompeten.",
    "Kelengkapan data tidak sama dengan keakuratan data; aplikasi hanya memeriksa kelengkapan, keterlacakan, "
    "konsistensi dasar, dan menandai relevansi serta ketidakpastian secara kualitatif.",
    "Aplikasi mencatat referensi/metadata bukti dan hash berkas yang diunggah, tetapi tidak membaca atau "
    "memverifikasi isi dokumen.",
    "Transaksi yang ditolak (satuan tidak cocok, faktor tidak tersedia, input tidak valid) tidak masuk total "
    "sehingga total dapat terlalu rendah; duplikat dikecualikan menurut aturan yang terdokumentasi.",
    "Tidak ada kurs mata uang asing, penyesuaian inflasi, alokasi, maupun kuantifikasi ketidakpastian statistik.",
    "Ambang materialitas dan indikator kesiapan adalah heuristik internal prototipe, bukan standar resmi.",
]


def build_report_blocks(a: Analysis, dataset_name: str = "sample_transactions.csv",
                        factor_name: str = "emission_factors.csv", generated_at: Optional[datetime] = None) -> list:
    """Daftar blok: ('h1'|'h2'|'p'|'bullets'|'table', konten)."""
    ts = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    s, d, f, cfg = a.summary, a.data, a.findings, a.cfg
    ok = d[d["status"] == STATUS_OK]
    B: list = []
    B.append(("h1", f"{APP_NAME} - Laporan Kesiapan Dokumentasi Emisi Scope 3 Kategori 1"))
    B.append(("p", f"Dibuat: {ts} | Dataset: {dataset_name} | Pustaka faktor: {factor_name} | Versi metode: {METHOD_VERSION}"))
    B.append(("p", "DISCLAIMER: " + DISCLAIMER))
    B.append(("p", "Angka pada laporan ini adalah ESTIMASI emisi yang belum diverifikasi."))
    if ok["factor_is_dummy"].astype(bool).any():
        B.append(("p", "PERHATIAN: " + DUMMY_FACTOR_NOTICE))

    B.append(("h2", "1. Ringkasan emisi"))
    B.append(("table", pd.DataFrame([
        ("Total estimasi emisi (belum diverifikasi)", f"{fmt_id(s['total_emissions_kg'] / 1000, 2)} t CO2e"),
        ("Transaksi pada berkas / dihitung / ditolak / duplikat dikecualikan",
         f"{s['n_rows']} / {s['n_calculated']} / {s['n_rejected']} / {s['n_excluded_duplicates']}"),
        ("Jumlah pemasok", str(s["n_suppliers"])),
        ("Catatan estimasi berbasis pengeluaran", str(s["n_estimate"])),
        ("Referensi bukti tercatat", f"{fmt_id(s['evidence_recorded_pct'], 1)}%"),
        ("Temuan (Tinggi / Sedang / Rutin)", f"{s['n_priority_high']} / {s['n_priority_medium']} / {s['n_priority_routine']}"),
    ], columns=["Ukuran", "Nilai"])))
    cls = (ok.groupby("data_class")["emissions_kg"].agg(["sum", "count"]).reset_index()
           if len(ok) else pd.DataFrame(columns=["data_class", "sum", "count"]))
    if len(cls):
        cls["Pangsa"] = (cls["sum"] / cls["sum"].sum() * 100).map(lambda v: f"{fmt_id(v, 1)}%")
        cls["Emisi (t CO2e)"] = (cls["sum"] / 1000).map(lambda v: fmt_id(v, 2))
        B.append(("table", cls.rename(columns={"data_class": "Kelas data", "count": "Transaksi"})[
            ["Kelas data", "Transaksi", "Emisi (t CO2e)", "Pangsa"]]))
    sup = ok.groupby("supplier_name")["emissions_kg"].sum().sort_values(ascending=False).head(10)
    if len(sup):
        B.append(("p", "10 pemasok dengan estimasi emisi terbesar:"))
        B.append(("table", pd.DataFrame({
            "Pemasok": sup.index, "Emisi (t CO2e)": [fmt_id(v / 1000, 2) for v in sup.values],
            "Pangsa": [f"{fmt_id(v / s['total_emissions_kg'] * 100, 1)}%" for v in sup.values]})))

    B.append(("h2", "2. Metode dan sumber faktor emisi"))
    B.append(("p", "Emisi (kg CO2e) = data aktivitas (dalam satuan penyebut faktor) x faktor emisi. Data fisik hanya dikalikan "
                   "faktor berbasis fisik; pengeluaran (IDR) hanya dikalikan faktor berbasis pengeluaran. Perhitungan ditolak "
                   "jika satuan tidak kompatibel atau faktor tidak tersedia."))
    if len(ok):
        fu = (ok.groupby(["factor_id", "factor_unit", "factor_value", "factor_source", "factor_year"], dropna=False)
              .agg(Transaksi=("transaction_id", "count"), em=("emissions_kg", "sum")).reset_index())
        fu["Faktor"] = fu["factor_value"].map(fmt_factor) + " " + fu["factor_unit"]
        fu["Emisi (t CO2e)"] = (fu["em"] / 1000).map(lambda v: fmt_id(v, 2))
        fu["Tahun"] = fu["factor_year"].map(lambda v: "-" if pd.isna(v) else str(int(v)))
        B.append(("table", fu.rename(columns={"factor_id": "ID faktor", "factor_source": "Sumber"})[
            ["ID faktor", "Faktor", "Sumber", "Tahun", "Transaksi", "Emisi (t CO2e)"]].sort_values("ID faktor")))

    B.append(("h2", "3. Status bukti"))
    codes = [evidence_state(r)[1] for _, r in d[d["status"] != STATUS_EXCLUDED].iterrows()]
    ev = pd.Series(codes).value_counts().rename_axis("Status bukti").reset_index(name="Transaksi")
    B.append(("table", ev))
    B.append(("p", "Tidak ada bukti yang ditandai 'terverifikasi': aplikasi hanya mencatat referensi dan metadata."))

    B.append(("h2", "4. Indikator kesiapan (heuristik internal prototipe)"))
    B.append(("table", readiness_indicators(a)))
    B.append(("p", "Indikator ini adalah ringkasan deskriptif, bukan skor, standar resmi, maupun opini assurance."))

    B.append(("h2", "5. Kualitas data per dimensi"))
    B.append(("table", quality_overview(a.quality)))
    B.append(("p", "Setiap dimensi dinilai terpisah dengan alasan per transaksi (lihat ekspor CSV kualitas data). "
                   "Tidak ada skor gabungan."))

    B.append(("h2", "6. Daftar temuan"))
    if len(f):
        pv = pd.crosstab(f["finding_label"], f["priority"]).reindex(columns=["Tinggi", "Sedang", "Rutin"], fill_value=0)
        pv["Total"] = pv.sum(axis=1)
        B.append(("table", pv.reset_index().rename(columns={"finding_label": "Jenis temuan"})))
        B.append(("p", f"Aturan prioritas: materialitas Tinggi jika pangsa >= {cfg.high_share:.1%} dari total, Sedang jika >= "
                       f"{cfg.medium_share:.1%}. Matriks prioritas:"))
        B.append(("table", priority_rule_table(cfg)))
        top = f[f["priority"] == "Tinggi"].head(15)
        if len(top):
            B.append(("p", f"Temuan prioritas Tinggi (maks. 15 dari {s['n_priority_high']}); daftar lengkap ada pada ekspor CSV:"))
            B.append(("table", top[["finding_id", "transaction_id", "finding_label", "severity", "priority_reason", "recommendation"]]
                      .rename(columns={"finding_id": "ID", "transaction_id": "Transaksi", "finding_label": "Temuan",
                                       "severity": "Severity", "priority_reason": "Alasan prioritas",
                                       "recommendation": "Rekomendasi"})))
    else:
        B.append(("p", "Tidak ada temuan."))

    B.append(("h2", "7. Tindakan perbaikan yang disarankan"))
    if len(f):
        acts = []
        for typ, g in f.groupby("finding_type"):
            hi = (g["priority"] == "Tinggi").sum()
            acts.append((FINDING_LABEL.get(typ, typ), len(g), int(hi), g.iloc[0]["recommendation"]))
        act = pd.DataFrame(acts, columns=["Jenis temuan", "Jumlah", "Prioritas Tinggi", "Tindakan"]) \
            .sort_values(["Prioritas Tinggi", "Jumlah"], ascending=False)
        B.append(("table", act))

    B.append(("h2", "8. Batasan data dan batasan prototipe"))
    B.append(("bullets", LIMITATIONS))
    B.append(("p", "DISCLAIMER: " + DISCLAIMER))
    return B


def report_markdown(blocks: list) -> str:
    out: list[str] = []
    for kind, c in blocks:
        if kind == "h1":
            out.append(f"# {c}\n")
        elif kind == "h2":
            out.append(f"\n## {c}\n")
        elif kind == "p":
            out.append(c + "\n")
        elif kind == "bullets":
            out.extend(f"- {x}" for x in c)
            out.append("")
        elif kind == "table":
            df = c.astype(str).replace({"nan": "-", "None": "-"})
            out.append("| " + " | ".join(df.columns) + " |")
            out.append("|" + "|".join("---" for _ in df.columns) + "|")
            for _, r in df.iterrows():
                out.append("| " + " | ".join(v.replace("|", "/").replace("\n", " ") for v in r) + " |")
            out.append("")
    return "\n".join(out)


def _pdf_safe(t) -> str:
    """Helvetica bawaan hanya mendukung Latin-1; ganti simbol khusus agar tidak rusak."""
    t = str(t)
    for a, b in {"×": "x", "≥": ">=", "≤": "<=", "→": "->", "₂": "2", "–": "-", "—": "-", "’": "'", "≈": "~",
                 "“": '"', "”": '"', "§": ""}.items():
        t = t.replace(a, b)
    return t.encode("latin-1", "replace").decode("latin-1")


def report_pdf(blocks: list) -> bytes:
    """Hasilkan PDF (A4 landscape) memakai reportlab. Melempar ImportError jika reportlab tidak ada."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    cell = ParagraphStyle("c", parent=body, fontSize=7.5, leading=9)
    head = ParagraphStyle("hc", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title="TRACE ESG - Readiness Report")
    width = landscape(A4)[0] - 28 * mm
    story = []
    for kind, c in blocks:
        if kind == "h1":
            story += [Paragraph(escape(_pdf_safe(c)), ss["Title"]), Spacer(1, 3)]
        elif kind == "h2":
            story += [Spacer(1, 6), Paragraph(escape(_pdf_safe(c)), ss["Heading2"])]
        elif kind == "p":
            story += [Paragraph(escape(_pdf_safe(c)), body), Spacer(1, 3)]
        elif kind == "bullets":
            for x in c:
                story.append(Paragraph("&bull; " + escape(_pdf_safe(x)), body))
            story.append(Spacer(1, 3))
        elif kind == "table":
            df = c.astype(str).replace({"nan": "-", "None": "-"})
            data = [[Paragraph(escape(_pdf_safe(h)), head) for h in df.columns]]
            data += [[Paragraph(escape(_pdf_safe(v)), cell) for v in row] for row in df.itertuples(index=False)]
            # lebar kolom proporsional terhadap panjang teks (dibatasi)
            lens = [max(8, min(60, int(df[col].str.len().quantile(0.9)) if len(df) else 8, len(col) + 40)) for col in df.columns]
            tot = sum(lens)
            t = Table(data, colWidths=[width * l / tot for l in lens], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E46")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F4")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BFC8C5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            story += [t, Spacer(1, 5)]

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(14 * mm, 8 * mm, _pdf_safe("TRACE ESG - dokumen pendukung persiapan; bukan verifikasi/assurance."))
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f"Hal. {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
