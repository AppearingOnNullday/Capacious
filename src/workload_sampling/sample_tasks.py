from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterable

DATASET_ID = "nebius/SWE-rebench-V2"
DIFFICULTY_ORDER = ("hard", "medium", "easy")


def load_repo_map(path: Path) -> dict[str, str]:
    """Load repo -> category mapping and reject ambiguous inputs."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not {"repo", "category"}.issubset(reader.fieldnames):
            raise ValueError("repo map must contain 'repo' and 'category' columns")

        repo_map: dict[str, str] = {}
        for row in reader:
            repo = row["repo"].strip()
            category = row["category"].strip()
            if not repo or not category:
                raise ValueError("repo map contains an empty repo or category")
            if repo in repo_map:
                raise ValueError(f"duplicate repo in repo map: {repo}")
            repo_map[repo] = category

    if not repo_map:
        raise ValueError("repo map is empty")
    return repo_map


def _extract_difficulty(row: dict) -> str | None:
    try:
        value = row["meta"]["llm_metadata"]["difficulty"]
    except (KeyError, TypeError):
        return None
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if value in {"easy", "medium", "hard"} else None


def load_swe_rebench_tasks(
    repo_map: dict[str, str], dataset_revision: str
) -> tuple[list[dict[str, str]], str]:
    """Resolve an immutable dataset revision, then load only eligible tasks."""
    from datasets import load_dataset
    from huggingface_hub import HfApi

    info = HfApi().dataset_info(DATASET_ID, revision=dataset_revision)
    resolved_revision = info.sha
    if not resolved_revision:
        raise RuntimeError(f"could not resolve dataset revision: {dataset_revision}")

    dataset = load_dataset(
        DATASET_ID,
        split="train",
        revision=resolved_revision,
        streaming=True,
    )

    tasks: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for row in dataset:
        repo = row.get("repo")
        if repo not in repo_map:
            continue

        difficulty = _extract_difficulty(row)
        if difficulty is None:
            continue

        instance_id = row.get("instance_id")
        image_name = row.get("image_name")
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError("eligible dataset row has missing/invalid instance_id")
        if not isinstance(image_name, str) or not image_name:
            raise ValueError(f"task {instance_id} has missing/invalid image_name")
        if instance_id in seen_ids:
            raise ValueError(f"duplicate instance_id in dataset: {instance_id}")
        seen_ids.add(instance_id)

        tasks.append(
            {
                "instance_id": instance_id,
                "repo": repo,
                "category": repo_map[repo],
                "difficulty": difficulty,
                "image_name": image_name,
            }
        )

    return tasks, resolved_revision


def _sample_one_difficulty(
    pool: list[dict[str, str]],
    quota: int,
    used_repos: set[str],
    rng: random.Random,
) -> list[dict[str, str]]:
    if len(pool) < quota:
        raise ValueError(f"requested {quota} tasks but only {len(pool)} are available")

    by_repo: dict[str, list[dict[str, str]]] = defaultdict(list)
    for task in sorted(pool, key=lambda x: x["instance_id"]):
        by_repo[task["repo"]].append(task)

    repo_order = sorted(by_repo)
    rng.shuffle(repo_order)

    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()

    # First use repos not yet selected anywhere in this category.
    for prefer_unused in (True, False):
        for repo in repo_order:
            if len(selected) >= quota:
                break
            if (repo not in used_repos) != prefer_unused:
                continue
            candidates = list(by_repo[repo])
            rng.shuffle(candidates)
            task = candidates[0]
            selected.append(task)
            selected_ids.add(task["instance_id"])
        if len(selected) >= quota:
            break

    # Only if distinct repos are insufficient, allow additional tasks per repo.
    if len(selected) < quota:
        remaining = [task for task in pool if task["instance_id"] not in selected_ids]
        remaining.sort(key=lambda x: x["instance_id"])
        rng.shuffle(remaining)
        selected.extend(remaining[: quota - len(selected)])

    if len(selected) != quota:
        raise RuntimeError("sampling failed to satisfy quota")

    used_repos.update(task["repo"] for task in selected)
    return selected


def sample_tasks(
    tasks: Iterable[dict[str, str]],
    quotas: dict[str, int],
    seed: int,
) -> list[dict[str, str]]:
    """Sample each category with category-wide repo diversity across difficulties."""
    for difficulty in ("easy", "medium", "hard"):
        if quotas[difficulty] < 0:
            raise ValueError(f"quota must be non-negative: {difficulty}={quotas[difficulty]}")

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    categories: set[str] = set()
    for task in tasks:
        category = task["category"]
        difficulty = task["difficulty"]
        if difficulty not in {"easy", "medium", "hard"}:
            continue
        categories.add(category)
        grouped[(category, difficulty)].append(task)

    rng = random.Random(seed)
    sampled: list[dict[str, str]] = []

    for category in sorted(categories):
        used_repos: set[str] = set()
        for difficulty in DIFFICULTY_ORDER:
            quota = quotas[difficulty]
            pool = grouped[(category, difficulty)]
            if len(pool) < quota:
                raise ValueError(
                    f"insufficient tasks for category={category!r}, difficulty={difficulty!r}: "
                    f"requested={quota}, available={len(pool)}"
                )
            sampled.extend(_sample_one_difficulty(pool, quota, used_repos, rng))

    instance_ids = [task["instance_id"] for task in sampled]
    if len(instance_ids) != len(set(instance_ids)):
        raise RuntimeError("sampling produced duplicate instance_id values")

    return sampled


def write_output(
    output_path: Path,
    tasks: list[dict[str, str]],
    resolved_revision: str,
    seed: int,
    quotas: dict[str, int],
) -> None:
    payload = {
        "metadata": {
            "dataset": DATASET_ID,
            "dataset_revision": resolved_revision,
            "seed": seed,
            "sampling_strategy": "category quotas with category-wide repo diversity; hard->medium->easy",
            "quota": quotas,
        },
        "tasks": tasks,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample a reproducible SWE-rebench-V2 workload.")
    parser.add_argument("--repo-map", type=Path, default=Path("data/workload_sampling/repo_sampling_map.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/workload_sampling/task_list.json"))
    parser.add_argument("--dataset-revision", default="main")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--easy", type=int, default=6)
    parser.add_argument("--medium", type=int, default=6)
    parser.add_argument("--hard", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    quotas = {"easy": args.easy, "medium": args.medium, "hard": args.hard}

    repo_map = load_repo_map(args.repo_map)
    source_tasks, resolved_revision = load_swe_rebench_tasks(repo_map, args.dataset_revision)

    expected_categories = set(repo_map.values())
    available_categories = {task["category"] for task in source_tasks}
    missing_categories = sorted(expected_categories - available_categories)
    if missing_categories:
        raise ValueError(f"no eligible tasks found for categories: {missing_categories}")

    sampled = sample_tasks(source_tasks, quotas, args.seed)
    expected_count = len(expected_categories) * sum(quotas.values())
    if len(sampled) != expected_count:
        raise RuntimeError(
            f"unexpected sampled task count: expected={expected_count}, actual={len(sampled)}"
        )

    write_output(args.output, sampled, resolved_revision, args.seed, quotas)

    print(f"Wrote {len(sampled)} tasks to {args.output}")
    print(f"Dataset revision: {resolved_revision}")


if __name__ == "__main__":
    main()
