from __future__ import annotations

import csv
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from data_agent_baseline.benchmark.dataset import DABenchPublicDataset
from data_agent_baseline.config import AgentConfig, AppConfig, DatasetConfig, RunConfig
from data_agent_baseline.evaluation.linter import lint_table
from data_agent_baseline.evaluation.scorer import score_csv
from data_agent_baseline.profiling.context import build_context_profile
from data_agent_baseline.run.runner import _run_single_task_with_timeout

DEFAULT_INPUT_DIR = Path("/input")
DEFAULT_OUTPUT_DIR = Path("/output")
DEFAULT_LOGS_DIR = Path("/logs")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(logs_dir / "runtime.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_prediction(path: Path, columns: list[Any], rows: list[Any]) -> dict[str, Any]:
    lint = lint_table(columns, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(lint.columns)
        for row in lint.rows:
            writer.writerow(row)
    return lint.to_dict()


def _write_prediction_raw_old(path: Path, columns: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if value is None else value for value in row])


def _write_fallback_prediction(output_dir: Path, task_id: str) -> Path:
    prediction_path = output_dir / task_id / "prediction.csv"
    # Header-only fallback keeps the official output contract even if a task fails.
    # It should score 0 for that task, but prevents missing-file failures.
    _write_prediction(prediction_path, ["answer"], [])
    return prediction_path


def _maybe_score_prediction(prediction_path: Path, task_id: str) -> dict[str, Any] | None:
    raw_gold_dir = os.getenv("DABENCH_GOLD_DIR")
    if not raw_gold_dir:
        return None
    gold_csv = Path(raw_gold_dir) / task_id / "gold.csv"
    if not gold_csv.exists():
        return {"error": f"missing gold csv: {gold_csv}"}
    try:
        return score_csv(prediction_path, gold_csv).to_dict()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _build_config(input_dir: Path, logs_dir: Path) -> AppConfig:
    model_name = os.getenv("MODEL_NAME", "")
    api_base = os.getenv("MODEL_API_URL", "")
    api_key = os.getenv("MODEL_API_KEY", "")
    return AppConfig(
        dataset=DatasetConfig(root_path=input_dir),
        agent=AgentConfig(
            model=model_name,
            api_base=api_base,
            api_key=api_key,
            max_steps=_env_int("DABENCH_AGENT_MAX_STEPS", 16),
            temperature=_env_float("DABENCH_TEMPERATURE", 0.0),
        ),
        run=RunConfig(
            output_dir=logs_dir / "artifacts",
            run_id=None,
            max_workers=_env_int("DABENCH_MAX_WORKERS", 4),
            task_timeout_seconds=_env_int("DABENCH_TASK_TIMEOUT_SECONDS", 600),
        ),
    )


def _solve_task(task_id: str, config: AppConfig, output_dir: Path, logs_dir: Path, smoke_mode: bool) -> dict[str, Any]:
    started = perf_counter()
    prediction_path = output_dir / task_id / "prediction.csv"
    trace_path = logs_dir / "traces" / f"{task_id}.json"
    profile_path = logs_dir / "profiles" / f"{task_id}.json"

    profile: dict[str, Any] | None = None
    if _env_bool("DABENCH_WRITE_PROFILES", True):
        try:
            task = DABenchPublicDataset(config.dataset.root_path).get_task(task_id)
            profile = build_context_profile(task)
            _write_json(profile_path, profile)
        except Exception as exc:  # noqa: BLE001
            profile = {"error": str(exc)}

    if smoke_mode:
        prediction_path = _write_fallback_prediction(output_dir, task_id)
        result = {
            "task_id": task_id,
            "succeeded": True,
            "smoke_mode": True,
            "answer": {"columns": ["answer"], "rows": []},
            "failure_reason": None,
        }
        result["elapsed_seconds"] = round(perf_counter() - started, 3)
        result["profile_path"] = str(profile_path) if profile is not None else None
        result["local_score"] = _maybe_score_prediction(prediction_path, task_id)
        _write_json(trace_path, result)
        return {**result, "prediction_csv_path": str(prediction_path)}

    try:
        result = _run_single_task_with_timeout(task_id=task_id, config=config)
    except BaseException as exc:  # noqa: BLE001
        logging.exception("Task %s crashed", task_id)
        result = {
            "task_id": task_id,
            "answer": None,
            "steps": [],
            "failure_reason": f"Task crashed: {exc}",
            "succeeded": False,
        }

    answer = result.get("answer")
    if isinstance(answer, dict) and isinstance(answer.get("columns"), list) and isinstance(answer.get("rows"), list):
        result["output_lint"] = _write_prediction(prediction_path, list(answer["columns"]), [list(row) for row in answer["rows"]])
    else:
        prediction_path = _write_fallback_prediction(output_dir, task_id)
        result["output_lint"] = {"ok": False, "warnings": ["missing model answer; wrote fallback header-only CSV"], "errors": []}

    result["elapsed_seconds"] = round(perf_counter() - started, 3)
    result["prediction_csv_path"] = str(prediction_path)
    result["profile_path"] = str(profile_path) if profile is not None else None
    result["local_score"] = _maybe_score_prediction(prediction_path, task_id)
    _write_json(trace_path, result)
    return result


def main() -> None:
    input_dir = Path(os.getenv("DABENCH_INPUT_DIR", str(DEFAULT_INPUT_DIR))).resolve()
    output_dir = Path(os.getenv("DABENCH_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))).resolve()
    logs_dir = Path(os.getenv("DABENCH_LOGS_DIR", str(DEFAULT_LOGS_DIR))).resolve()

    _setup_logging(logs_dir)
    started_at = datetime.now(timezone.utc)
    started = perf_counter()

    config = _build_config(input_dir, logs_dir)
    model_env_ready = bool(config.agent.model and config.agent.api_base and config.agent.api_key)
    smoke_mode = _env_bool("DABENCH_SMOKE_MODE", default=not model_env_ready)

    # Never log secrets. Only log whether required model env vars are present.
    logging.info("DABench submission runner started")
    logging.info("input_dir=%s output_dir=%s logs_dir=%s", input_dir, output_dir, logs_dir)
    logging.info(
        "model_env_ready=%s model_name=%s smoke_mode=%s max_workers=%s timeout=%ss max_steps=%s",
        model_env_ready,
        config.agent.model or "<missing>",
        smoke_mode,
        config.run.max_workers,
        config.run.task_timeout_seconds,
        config.agent.max_steps,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = DABenchPublicDataset(input_dir)
    task_ids = dataset.list_task_ids()
    limit = _env_int("DABENCH_TASK_LIMIT", 0)
    if limit > 0:
        task_ids = task_ids[:limit]

    if not task_ids:
        logging.warning("No task_<id> directories found under %s", input_dir)

    max_workers = max(1, config.run.max_workers)
    results: list[dict[str, Any]] = []
    if max_workers == 1 or len(task_ids) <= 1:
        for task_id in task_ids:
            logging.info("Starting task %s", task_id)
            result = _solve_task(task_id, config, output_dir, logs_dir, smoke_mode)
            logging.info("Finished task %s succeeded=%s", task_id, result.get("succeeded"))
            results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(_solve_task, task_id, config, output_dir, logs_dir, smoke_mode): task_id
                for task_id in task_ids
            }
            for future in as_completed(future_to_task):
                task_id = future_to_task[future]
                try:
                    result = future.result()
                except BaseException as exc:  # noqa: BLE001
                    logging.exception("Unhandled worker failure for %s", task_id)
                    _write_fallback_prediction(output_dir, task_id)
                    result = {
                        "task_id": task_id,
                        "succeeded": False,
                        "failure_reason": f"Unhandled worker failure: {exc}",
                    }
                logging.info("Finished task %s succeeded=%s", task_id, result.get("succeeded"))
                results.append(result)

    results.sort(key=lambda item: int(str(item.get("task_id", "task_0")).removeprefix("task_")))
    scored = [item.get("local_score") for item in results if isinstance(item.get("local_score"), dict) and "score" in item.get("local_score", {})]
    summary = {
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(perf_counter() - started, 3),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "logs_dir": str(logs_dir),
        "task_count": len(results),
        "succeeded_task_count": sum(1 for item in results if item.get("succeeded")),
        "smoke_mode": smoke_mode,
        "model_env_ready": model_env_ready,
        "local_average_score": round(sum(float(item["score"]) for item in scored) / len(scored), 6) if scored else None,
        "config": {
            "dataset": {"root_path": str(config.dataset.root_path)},
            "agent": {
                "model": config.agent.model,
                "api_base_present": bool(config.agent.api_base),
                "api_key_present": bool(config.agent.api_key),
                "max_steps": config.agent.max_steps,
                "temperature": config.agent.temperature,
            },
            "run": {
                "output_dir": str(config.run.output_dir),
                "run_id": config.run.run_id,
                "max_workers": config.run.max_workers,
                "task_timeout_seconds": config.run.task_timeout_seconds,
            },
        },
        "tasks": results,
    }
    _write_json(logs_dir / "summary.json", summary)
    logging.info("DABench submission runner finished: %s/%s succeeded", summary["succeeded_task_count"], summary["task_count"])


if __name__ == "__main__":
    main()
