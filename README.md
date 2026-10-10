# Capacious

## Development Environment

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

## SUT Host Setup

Prepare a Linux host for the Docker-based Record MVP, from the repository root on the host:

```bash
bash scripts/env_setup/setup_sut_host.sh --grant-docker-access
```

If Docker group membership changes, reconnect SSH, then verify:

```bash
python3 scripts/env_setup/preflight_sut_host.py
```

Expected: `Overall: PASS` (exit code `0`).

Automatic installation supports Ubuntu 22.04/24.04/26.04 and Debian 12/13; system changes require sudo. The `docker` group grants root-level privileges, so use `--grant-docker-access` only on authorized hosts.

## Current Modules

- [`workload_sampling`](src/workload_sampling/README.md): constructs a fixed and reproducible workload from SWE-rebench-V2.