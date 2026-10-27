"""Konfigurasi bersama TRACE ESG: konstanta, label, ambang batas default, dan disclaimer.

Semua ambang batas risiko dapat diubah dari antarmuka (halaman Data Quality & Risk).
"""
from __future__ import annotations

from dataclasses import dataclass

APP_NAME = "TRACE ESG"
APP_TAGLINE = "Traceable Reporting, Accounting & Carbon Evidence"
METHOD_VERSION = "TRACE-C1-v0.1 (Scope 3 Kategori 1, prototipe)"

DISCLAIMER = (
    "TRACE ESG mendukung perhitungan, penelusuran bukti, dan persiapan dokumentasi. "
    "Aplikasi tidak memberikan verifikasi independen, sertifikasi, atau opini assurance."
)
DUMMY_FACTOR_NOTICE = (
    "Faktor emisi pada data demo adalah DATA DUMMY ILUSTRATIF untuk keperluan demonstrasi. "
    "Angka tersebut bukan faktor emisi resmi dan tidak boleh dipakai untuk pelaporan sebenarnya."
)

# --- Skema data ---------------------------------------------------------------
TRANSACTION_REQUIRED_COLUMNS = [
    "transaction_id", "transaction_date", "supplier_id", "supplier_name",
    "item_category", "item_description", "activity_quantity", "activity_unit",
    "purchase_amount", "currency", "data_method", "evidence_reference",
    "evidence_status", "reporting_period",
]
# Kolom opsional (tidak wajib ada di CSV unggahan)
TRANSACTION_OPTIONAL_COLUMNS = [
    "supplier_emission_factor",   # kg CO2e per satuan aktivitas, diklaim pemasok (belum diverifikasi)
    "evidence_file_name", "evidence_file_sha256", "assumption_note",
]
# Kolom yang nilainya tidak boleh kosong agar transaksi dapat dihitung
MANDATORY_VALUE_FIELDS = [
    "transaction_id", "transaction_date", "supplier_id", "supplier_name",
    "item_category", "activity_quantity", "activity_unit", "purchase_amount",
    "currency", "data_method", "reporting_period",
]
FACTOR_REQUIRED_COLUMNS = [
    "factor_id", "item_category", "factor_value", "factor_unit", "source_name",
    "source_reference", "publication_year", "geography", "boundary_notes", "method_notes",
]

# --- Metode dan klasifikasi data -------------------------------------------------
METHOD_PRIMARY = "primary_supplier"
METHOD_SECONDARY = "secondary_activity"
METHOD_SPEND = "spend_based"
ALLOWED_METHODS = [METHOD_PRIMARY, METHOD_SECONDARY, METHOD_SPEND]
METHOD_LABEL = {
    METHOD_PRIMARY: "Data pemasok (primer)",
    METHOD_SECONDARY: "Data aktivitas sekunder",
    METHOD_SPEND: "Estimasi berbasis pengeluaran",
}

# --- Status bukti (TIDAK ADA status 'terverifikasi' dengan sengaja) -----------------
EVIDENCE_ALLOWED = ["provided", "partial", "requested", "missing"]
EVIDENCE_LABEL = {
    "provided": "Referensi tercatat (belum diverifikasi)",
    "partial": "Sebagian tersedia",
    "requested": "Diminta, belum diterima",
    "missing": "Belum tersedia",
}
EVIDENCE_UPLOADED_LABEL = "File diunggah (belum diverifikasi)"

# --- Satuan --------------------------------------------------------------------------
# alias (huruf kecil) -> (kanonik, keluarga, pengali ke satuan dasar keluarga)
UNIT_TABLE = {
    "kg": ("kg", "massa", 1.0), "kilogram": ("kg", "massa", 1.0),
    "g": ("g", "massa", 0.001), "gram": ("g", "massa", 0.001),
    "t": ("t", "massa", 1000.0), "ton": ("t", "massa", 1000.0), "tonne": ("t", "massa", 1000.0),
    "l": ("L", "volume", 1.0), "liter": ("L", "volume", 1.0), "litre": ("L", "volume", 1.0),
    "ml": ("mL", "volume", 0.001),
    "m3": ("m3", "volume", 1000.0), "m³": ("m3", "volume", 1000.0),
    "unit": ("unit", "jumlah", 1.0), "pcs": ("pcs", "jumlah", 1.0),
    "pc": ("pcs", "jumlah", 1.0), "buah": ("pcs", "jumlah", 1.0),
    "paket": ("paket", "layanan", 1.0), "lot": ("paket", "layanan", 1.0),
    "jam": ("jam", "layanan", 1.0),
    "idr": ("IDR", "mata_uang", 1.0), "rp": ("IDR", "mata_uang", 1.0),
    "usd": ("USD", "mata_uang_asing", 1.0),
}
FAMILY_BASE_UNIT = {"massa": "kg", "volume": "L", "jumlah": "unit", "mata_uang": "IDR"}
# 'pcs' dan 'unit' diperlakukan setara (keduanya hitungan) pada keluarga 'jumlah'.

SPEND_CURRENCY = "IDR"

# --- Risiko --------------------------------------------------------------------------
SEVERITY_ORDER = {"Tinggi": 3, "Sedang": 2, "Rendah": 1}
PRIORITY_ORDER = {"Tinggi": 3, "Sedang": 2, "Rutin": 1}

FINDING_LABEL = {
    "missing_required_field": "Missing required field",
    "invalid_value": "Invalid value",
    "duplicate_transaction": "Duplicate transaction",
    "unit_mismatch": "Unit mismatch",
    "missing_factor_or_source": "Missing factor/source",
    "evidence_missing": "Evidence missing",
    "estimation_method_used": "Estimation method used",
    "inconsistent_reporting_period": "Inconsistent reporting period",
    "factor_outdated": "Outdated factor",
}
QUALITY_DIMENSIONS = ["Kelengkapan", "Keterlacakan", "Relevansi", "Konsistensi", "Ketidakpastian"]


@dataclass
class RiskConfig:
    """Ambang batas yang dapat dikonfigurasi pengguna.

    Materialitas = pangsa emisi sebuah transaksi terhadap total emisi yang dihitung.
    Untuk transaksi yang tidak dapat dihitung, proxy-nya adalah pangsa pengeluaran
    terhadap total pengeluaran (dinyatakan eksplisit pada alasan temuan).
    """
    high_share: float = 0.03      # >= 3% total  -> materialitas Tinggi
    medium_share: float = 0.01    # >= 1% total  -> materialitas Sedang
    max_factor_age_years: int = 5  # faktor lebih tua dari ini ditandai tidak relevan
    exclude_duplicates: bool = True

    def validate(self) -> None:
        if not (0 <= self.medium_share <= self.high_share <= 1):
            raise ValueError("Ambang batas harus memenuhi 0 <= sedang <= tinggi <= 1")
