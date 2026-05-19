from __future__ import annotations

from data_agent_baseline.benchmark.schema import PublicTask
from data_agent_baseline.profiling.context import build_context_profile, search_documents


def profile_task_context(task: PublicTask) -> dict[str, object]:
    return build_context_profile(task)


def search_task_documents(task: PublicTask, query: str, *, max_results: int = 5) -> dict[str, object]:
    return search_documents(task, query, max_results=max_results)
