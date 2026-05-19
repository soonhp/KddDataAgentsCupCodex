from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True, slots=True)
class LintResult:
    ok: bool
    columns: list[str]
    rows: list[list[str]]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "columns": self.columns,
            "rows": self.rows,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _looks_numeric(value: str) -> bool:
    text = value.strip().replace(",", "")
    if text in {"", "+", "-"}:
        return False
    try:
        Decimal(text)
        return True
    except InvalidOperation:
        return False


def _normalize_number(value: str) -> str:
    text = value.strip().replace(",", "")
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return value.strip()
    if not dec.is_finite():
        return ""
    # Keep integers as integers; otherwise keep a stable compact decimal with at least score-relevant precision.
    if dec == dec.to_integral_value():
        return str(dec.quantize(Decimal("1")))
    quantized = dec.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return format(quantized.normalize(), "f")


def _normalize_date(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    iso_date = re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text)
    if iso_date:
        y, m, d = text.split("-")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    for fmt in ("%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.date().isoformat()
        except ValueError:
            pass
    return text


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return _normalize_number(str(value))
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "nat", "inf", "-inf"}:
        return ""
    text = _normalize_date(text)
    if _looks_numeric(text):
        return _normalize_number(text)
    return text


def lint_table(columns: list[Any] | None, rows: list[Any] | None) -> LintResult:
    warnings: list[str] = []
    errors: list[str] = []
    if not columns:
        columns = ["answer"]
        warnings.append("missing columns; inserted fallback 'answer' column")
    normalized_columns = [str(column).strip() or f"column_{index + 1}" for index, column in enumerate(columns)]
    seen: dict[str, int] = {}
    unique_columns: list[str] = []
    for column in normalized_columns:
        count = seen.get(column, 0)
        seen[column] = count + 1
        unique_columns.append(column if count == 0 else f"{column}_{count + 1}")
    if unique_columns != normalized_columns:
        warnings.append("duplicate column names renamed for debuggability")

    if rows is None:
        rows = []
    if not isinstance(rows, list):
        errors.append("rows is not a list")
        rows = []

    width = len(unique_columns)
    normalized_rows: list[list[str]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, list):
            row = [row]
            warnings.append(f"row {row_index} was scalar; wrapped as single cell")
        row_values = list(row)
        if len(row_values) < width:
            row_values.extend([""] * (width - len(row_values)))
            warnings.append(f"row {row_index} padded to match column count")
        elif len(row_values) > width:
            row_values = row_values[:width]
            warnings.append(f"row {row_index} truncated to match column count")
        normalized_rows.append([normalize_cell(value) for value in row_values])

    if width == 0:
        errors.append("table has zero columns")
    if len(unique_columns) > 8:
        warnings.append("many output columns; extra-column penalty risk")
    return LintResult(ok=not errors, columns=unique_columns, rows=normalized_rows, warnings=warnings, errors=errors)
