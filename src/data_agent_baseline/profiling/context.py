from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from data_agent_baseline.benchmark.schema import PublicTask

TEXT_EXTENSIONS = {".md", ".txt", ".rst"}


def _safe_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _profile_csv(path: Path, rel_path: str, *, sample_rows: int = 5) -> dict[str, Any]:
    rows: list[list[str]] = []
    row_count = 0
    columns: list[str] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.reader(handle)
        columns = next(reader, [])
        for row in reader:
            row_count += 1
            if len(rows) < sample_rows:
                rows.append(row)
    return {"path": rel_path, "type": "csv", "size_bytes": path.stat().st_size, "columns": columns, "row_count": row_count, "sample_rows": rows}


def _json_shape(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(key): _json_shape(val, depth + 1) for key, val in list(value.items())[:25]}
    if isinstance(value, list):
        return {"type": "list", "length": len(value), "item_shape": _json_shape(value[0], depth + 1) if value else None}
    return type(value).__name__


def _profile_json(path: Path, rel_path: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    sample = payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        sample = {**{k: v for k, v in payload.items() if k != "records"}, "records": payload["records"][:3]}
    elif isinstance(payload, list):
        sample = payload[:3]
    return {"path": rel_path, "type": "json", "size_bytes": path.stat().st_size, "shape": _json_shape(payload), "sample": sample}


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def _profile_db(path: Path, rel_path: str) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    with _connect_readonly(path) as conn:
        table_names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in table_names:
            qtable = '"' + table.replace('"', '""') + '"'
            columns = [dict(cid=r[0], name=r[1], type=r[2], notnull=bool(r[3]), default=r[4], pk=bool(r[5])) for r in conn.execute(f"PRAGMA table_info({qtable})")]
            try:
                row_count = conn.execute(f"SELECT COUNT(*) FROM {qtable}").fetchone()[0]
            except sqlite3.DatabaseError:
                row_count = None
            try:
                sample_rows = [list(row) for row in conn.execute(f"SELECT * FROM {qtable} LIMIT 3").fetchall()]
            except sqlite3.DatabaseError:
                sample_rows = []
            tables.append({"name": table, "columns": columns, "row_count": row_count, "sample_rows": sample_rows})
    return {"path": rel_path, "type": "sqlite", "size_bytes": path.stat().st_size, "tables": tables}


def _profile_doc(path: Path, rel_path: str, *, max_headings: int = 30) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    headings = [line.strip() for line in text.splitlines() if line.lstrip().startswith("#")][:max_headings]
    tokens = re.findall(r"[A-Za-z0-9_가-힣-]{3,}", text.lower())
    top_terms = [term for term, _ in Counter(tokens).most_common(20)]
    return {
        "path": rel_path,
        "type": "document",
        "size_bytes": path.stat().st_size,
        "line_count": text.count("\n") + 1,
        "headings": headings,
        "top_terms": top_terms,
        "preview": text[:1200],
    }


def build_context_profile(task: PublicTask, *, include_samples: bool = True) -> dict[str, Any]:
    del include_samples  # kept for API evolution; v1 profiles include bounded samples.
    root = task.context_dir
    files: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    total_size = 0
    extension_counts: Counter[str] = Counter()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = _safe_rel(path, root)
        size = path.stat().st_size
        suffix = path.suffix.lower() or "<none>"
        total_size += size
        extension_counts[suffix] += 1
        files.append({"path": rel_path, "size_bytes": size, "extension": suffix})
        try:
            if suffix == ".csv":
                profiles.append(_profile_csv(path, rel_path))
            elif suffix == ".json":
                profiles.append(_profile_json(path, rel_path))
            elif suffix in {".db", ".sqlite", ".sqlite3"}:
                profiles.append(_profile_db(path, rel_path))
            elif suffix in TEXT_EXTENSIONS:
                profiles.append(_profile_doc(path, rel_path))
        except Exception as exc:  # noqa: BLE001
            profiles.append({"path": rel_path, "type": suffix, "error": str(exc), "size_bytes": size})
    return {
        "task_id": task.task_id,
        "difficulty": task.difficulty,
        "question": task.question,
        "context_root": str(root),
        "file_count": len(files),
        "total_size_bytes": total_size,
        "extension_counts": dict(extension_counts),
        "files": files,
        "profiles": profiles,
    }


def search_documents(task: PublicTask, query: str, *, max_results: int = 5, chunk_chars: int = 1600) -> dict[str, Any]:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_가-힣-]{2,}", query)]
    results: list[dict[str, Any]] = []
    for path in sorted(task.context_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]
        for index, chunk in enumerate(chunks):
            lower = chunk.lower()
            score = sum(lower.count(term) for term in terms) if terms else 0
            if score > 0:
                results.append({"path": _safe_rel(path, task.context_dir), "chunk_index": index, "score": score, "text": chunk})
    results.sort(key=lambda item: item["score"], reverse=True)
    return {"query": query, "results": results[:max_results]}
