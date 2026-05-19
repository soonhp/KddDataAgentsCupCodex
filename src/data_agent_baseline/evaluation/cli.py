from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from data_agent_baseline.evaluation.scorer import score_csv

app = typer.Typer(add_completion=False)
console = Console()


@app.command("score-dir")
def score_dir(
    pred_dir: Path = typer.Option(..., exists=True, file_okay=False, help="Directory containing task_<id>/prediction.csv"),
    gold_dir: Path = typer.Option(..., exists=True, file_okay=False, help="Directory containing task_<id>/gold.csv"),
    output_json: Path | None = typer.Option(None, help="Optional JSON summary path."),
) -> None:
    rows = []
    for gold_csv in sorted(gold_dir.glob("task_*/gold.csv"), key=lambda p: int(p.parent.name.removeprefix("task_"))):
        task_id = gold_csv.parent.name
        pred_csv = pred_dir / task_id / "prediction.csv"
        if pred_csv.exists():
            score = score_csv(pred_csv, gold_csv)
            item = {"task_id": task_id, "prediction_exists": True, **score.to_dict()}
        else:
            item = {
                "task_id": task_id,
                "prediction_exists": False,
                "score": 0.0,
                "recall": 0.0,
                "matched_columns": 0,
                "gold_columns": 0,
                "extra_columns": 0,
                "predicted_columns": 0,
            }
        rows.append(item)

    average_score = sum(item["score"] for item in rows) / len(rows) if rows else 0.0
    summary = {"task_count": len(rows), "average_score": round(average_score, 6), "tasks": rows}

    table = Table(title="DABench Local Score Replica")
    table.add_column("task")
    table.add_column("score")
    table.add_column("recall")
    table.add_column("matched/gold")
    table.add_column("extra/pred")
    table.add_column("exists")
    for item in rows:
        table.add_row(
            item["task_id"],
            f"{item['score']:.4f}",
            f"{item['recall']:.4f}",
            f"{item['matched_columns']}/{item['gold_columns']}",
            f"{item['extra_columns']}/{item['predicted_columns']}",
            "yes" if item["prediction_exists"] else "no",
        )
    console.print(table)
    console.print(f"Average score: {average_score:.6f}")

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        console.print(f"Wrote {output_json}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
