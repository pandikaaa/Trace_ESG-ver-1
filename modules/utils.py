"""Fungsi bantu kecil (format angka gaya Indonesia, dsb.)."""
from __future__ import annotations

import math


def fmt_id(x, nd: int = 2) -> str:
    """Format angka gaya Indonesia: 1.234.567,89 (None/NaN -> '-')."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    s = f"{float(x):,.{nd}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_factor(x) -> str:
    """Format faktor emisi tanpa kehilangan digit signifikan (mis. 0,000075)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    s = f"{float(x):.10f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")
