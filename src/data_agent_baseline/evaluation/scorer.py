from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from data_agent_baseline.evaluation.linter import normalize_cell


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: float
    recall: float
    matched_columns: int
    gold_columns: int
    extra_columns: int
    predicted_columns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "recall": self.recall,
            "matched_columns": self.matched_columns,
            "gold_columns": self.gold_columns,
            "extra_columns": self.extra_columns,
            "predicted_columns": self.predicted_columns,
        }


def _score_normalize(value: Any) -> str:
    text = normalize_cell(value)
    try:
        dec = Decimal(text)
    except (InvalidOperation, ValueError):
        return text
    if not dec.is_finite():
        return ""
    rounded = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return str(rounded.quantize(Decimal("1")))
    return format(rounded.normalize(), "f")


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def column_signatures(columns: list[str], rows: list[list[Any]]) -> list[tuple[str, ...]]:
    signatures: list[tuple[str, ...]] = []
    for col_index, _ in enumerate(columns):
        values = []
        for row in rows:
            values.append(_score_normalize(row[col_index] if col_index < len(row) else ""))
        signatures.append(tuple(sorted(values)))
    return signatures


def score_tables(
    pred_columns: list[str],
    pred_rows: list[list[Any]],
    gold_columns: list[str],
    gold_rows: list[list[Any]],
    *,
    penalty_lambda: float = 0.2,
) -> ScoreResult:
    pred_sigs = column_signatures(pred_columns, pred_rows)
    gold_sigs = column_signatures(gold_columns, gold_rows)
    remaining = list(pred_sigs)
    matched = 0
    for gold_sig in gold_sigs:
        if gold_sig in remaining:
            matched += 1
            remaining.remove(gold_sig)
    gold_count = len(gold_sigs)
    pred_count = len(pred_sigs)
    recall = matched / gold_count if gold_count else 0.0
    extra = max(pred_count - matched, 0)
    penalty = penalty_lambda * (extra / pred_count) if pred_count else 0.0
    score = max(0.0, recall - penalty)
    return ScoreResult(
        score=round(score, 6),
        recall=round(recall, 6),
        matched_columns=matched,
        gold_columns=gold_count,
        extra_columns=extra,
        predicted_columns=pred_count,
    )


def score_csv(prediction_csv: Path, gold_csv: Path, *, penalty_lambda: float = 0.2) -> ScoreResult:
    pred_columns, pred_rows = _read_csv(prediction_csv)
    gold_columns, gold_rows = _read_csv(gold_csv)
    return score_tables(pred_columns, pred_rows, gold_columns, gold_rows, penalty_lambda=penalty_lambda)
