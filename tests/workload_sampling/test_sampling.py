import pytest

from workload_sampling.sample_tasks import sample_tasks


def make_task(repo: str, difficulty: str, index: int, category: str = "Category A") -> dict[str, str]:
    return {
        "instance_id": f"{repo.replace('/', '__')}-{difficulty}-{index}",
        "repo": repo,
        "category": category,
        "difficulty": difficulty,
        "image_name": f"image-{index}",
    }


def test_sampling_is_reproducible_and_prefers_repo_diversity():
    tasks = []
    for i in range(1, 7):
        repo = f"org/repo{i}"
        for difficulty in ("easy", "medium", "hard"):
            tasks.append(make_task(repo, difficulty, i))

    quotas = {"easy": 2, "medium": 2, "hard": 2}
    first = sample_tasks(tasks, quotas, seed=42)
    second = sample_tasks(tasks, quotas, seed=42)

    assert first == second
    assert len(first) == 6
    assert len({task["instance_id"] for task in first}) == 6
    assert len({task["repo"] for task in first}) == 6
    assert {d: sum(t["difficulty"] == d for t in first) for d in quotas} == quotas


def test_sampling_reuses_repos_only_when_needed():
    tasks = []
    for i in range(3):
        tasks.append(make_task("org/repo1", "easy", i))
    tasks.append(make_task("org/repo2", "easy", 10))

    sampled = sample_tasks(tasks, {"easy": 3, "medium": 0, "hard": 0}, seed=7)

    assert len(sampled) == 3
    assert {task["repo"] for task in sampled} == {"org/repo1", "org/repo2"}


def test_sampling_fails_when_quota_cannot_be_met():
    tasks = [make_task("org/repo1", "hard", 1)]

    with pytest.raises(ValueError, match="requested=2, available=1"):
        sample_tasks(tasks, {"easy": 0, "medium": 0, "hard": 2}, seed=42)
