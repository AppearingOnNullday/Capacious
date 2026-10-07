# Workload Sampling

This module constructs a fixed and reproducible Coding Agent workload from [SWE-rebench-V2](https://huggingface.co/datasets/nebius/SWE-rebench-V2).

The goal is to obtain a task set that covers different software domains and difficulty levels while avoiding unnecessary concentration on a small number of repositories.

## Inputs

### Repository taxonomy

`data/workload_sampling/repo_sampling_map.csv`

The file maps 472 repositories to 14 semantic categories:

| Category | Description |
|---|---|
| Application / UI / CMS | User-facing applications, UI frameworks, content-management systems, and related application infrastructure. |
| Blockchain / Smart Contract | Blockchain platforms, smart-contract languages, clients, and supporting tooling. |
| CLI / System Utilities | Command-line interfaces, shells, and general-purpose system utilities. |
| Data / Database / Storage | Data-processing libraries, databases, storage systems, and structured-data infrastructure. |
| DevOps / Cloud / Infrastructure | Cloud, deployment, orchestration, configuration, and infrastructure-management software. |
| Developer Tools / Build / Package | Build systems, package managers, dependency-management tools, and developer tooling. |
| General Library / SDK | General-purpose reusable libraries and software development kits without a more specific domain classification. |
| Language / Compiler / Static Analysis | Programming-language tooling, compilers, linters, parsers, and static-analysis systems. |
| Medical / Bio | Software for medical, neuroscience, bioinformatics, and related biological workloads. |
| Scientific / ML | Scientific computing, optimization, simulation, machine learning, and numerical software. |
| Security / Identity | Security, authentication, authorization, identity, cryptography, and security-analysis software. |
| Systems / Runtime / Distributed | Runtime systems, servers, distributed systems, observability infrastructure, and low-level systems software. |
| Testing / QA | Testing frameworks, mocking tools, synthetic testing, validation, and quality-assurance software. |
| Web / API / Network | Web frameworks, API infrastructure, networking libraries, and protocol-related software. |

### SWE-rebench-V2

The tasks are loaded from:

```text
nebius/SWE-rebench-V2
```

The sampler uses the following fields:

```text
instance_id
repo
image_name
meta.llm_metadata.difficulty
```

Only tasks whose repository appears in `repo_sampling_map.csv` are eligible.

Only the `easy`, `medium`, and `hard` difficulty levels are used.

## Sampling

Sampling is performed independently for each category with configurable quotas for each difficulty level.

The default quota is:

```text
Easy:   6
Medium: 6
Hard:   2
```

With 14 categories, this produces:

```text
14 × (6 + 6 + 2) = 196 tasks
```

Repository diversity is considered across all difficulty levels within the same category.

For each category, sampling proceeds in the order:

```text
Hard → Medium → Easy
```

At each difficulty level, the sampler first prefers repositories that have not yet been selected for that category. Repository reuse is allowed only when the available repository diversity is insufficient to satisfy the requested quota.

Candidate repositories and tasks are shuffled using an explicit random seed. The same inputs, dataset revision, quotas, and seed therefore reproduce the same task list.

If a requested quota cannot be satisfied, the sampler fails instead of silently changing the workload definition.

## Usage

From the repository root:

```bash
conda activate capacious

python src/workload_sampling/sample_tasks.py
```

The default parameters are equivalent to:

```bash
python src/workload_sampling/sample_tasks.py \
    --repo-map data/workload_sampling/repo_sampling_map.csv \
    --output data/workload_sampling/task_list.json \
    --seed 42 \
    --easy 6 \
    --medium 6 \
    --hard 2
```

The quotas and seed can be changed through the corresponding command-line arguments.

## Output

The sampler produces:

```text
data/workload_sampling/task_list.json
```

Each task contains only the information required by downstream experiments:

```json
{
  "instance_id": "...",
  "repo": "...",
  "category": "...",
  "difficulty": "...",
  "image_name": "..."
}
```

The output also records the sampling provenance:

```json
{
  "metadata": {
    "dataset": "nebius/SWE-rebench-V2",
    "dataset_revision": "<commit SHA>",
    "seed": 42,
    "sampling_strategy": "category quotas with category-wide repo diversity; hard->medium->easy",
    "quota": {
      "easy": 6,
      "medium": 6,
      "hard": 2
    }
  }
}
```

The resolved dataset commit SHA is stored so that the sampled workload can be reproduced even if the upstream dataset changes later.