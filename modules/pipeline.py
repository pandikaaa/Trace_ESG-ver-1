"""Orkestrasi: validasi -> hitung -> temuan -> kualitas -> ringkasan (satu panggilan)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .calculator import calculate_all
from .config import RiskConfig
from .risk_engine import assess_quality, build_findings, merge_results, summarize
from .validation import ValidationResult, validate_transactions


@dataclass
class Analysis:
    validation: ValidationResult
    data: pd.DataFrame          # transaksi + hasil hitung
    findings: pd.DataFrame
    quality: pd.DataFrame
    summary: dict
    cfg: RiskConfig


def run_pipeline(raw: pd.DataFrame, factors: pd.DataFrame, cfg: Optional[RiskConfig] = None) -> Analysis:
    cfg = cfg or RiskConfig()
    val = validate_transactions(raw)
    if not val.schema_ok:
        empty = pd.DataFrame()
        return Analysis(val, empty, pd.DataFrame(), empty, {}, cfg)
    calc = calculate_all(val.clean, factors, cfg)
    data = merge_results(val.clean, calc)
    findings = build_findings(data, val.issues, cfg)
    quality = assess_quality(data, findings)
    return Analysis(val, data, findings, quality, summarize(data, findings), cfg)
