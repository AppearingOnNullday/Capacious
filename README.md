# Capacious

## Environment Setup

Create and activate the Conda environment:

```bash
conda create -n capacious python=3.11 -y
conda activate capacious
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest -q
```

## Current Modules

- [`workload_sampling`](src/workload_sampling/README.md): constructs a fixed and reproducible workload from SWE-rebench-V2.