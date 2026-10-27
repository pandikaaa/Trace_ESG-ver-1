"""Bantuan uji: pembuat baris transaksi dan pemuat data demo."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from modules.calculator import calculate_all, load_factors  # noqa: E402
from modules.config import RiskConfig  # noqa: E402
from modules.pipeline import run_pipeline  # noqa: E402
from modules.validation import read_csv_flexible, validate_transactions  # noqa: E402

DATA = ROOT / "data"


def factors() -> pd.DataFrame:
    return load_factors(str(DATA / "emission_factors.csv"))


def sample_raw() -> pd.DataFrame:
    return read_csv_flexible(str(DATA / "sample_transactions.csv"))


def row(**over) -> dict:
    base = {
        "transaction_id": "T-1", "transaction_date": "2025-03-10", "supplier_id": "S1", "supplier_name": "PT Uji",
        "item_category": "Tepung Terigu", "item_description": "uji", "activity_quantity": "500", "activity_unit": "kg",
        "purchase_amount": "6000000", "currency": "IDR", "data_method": "secondary_activity",
        "evidence_reference": "INV-1.pdf", "evidence_status": "provided", "reporting_period": "2025",
        "supplier_emission_factor": "",
    }
    base.update(over)
    return base


def frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows)).astype(str)


def calc(*rows: dict, cfg: RiskConfig | None = None, fac: pd.DataFrame | None = None) -> pd.DataFrame:
    val = validate_transactions(frame(*rows))
    return calculate_all(val.clean, factors() if fac is None else fac, cfg)


def analyze(*rows: dict, cfg: RiskConfig | None = None):
    return run_pipeline(frame(*rows), factors(), cfg)
