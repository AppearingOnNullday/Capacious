"""Read-only checks for the Docker Record MVP on a Linux SUT Host."""

import os
import platform
import shutil
import subprocess
from pathlib import Path

REQUIRED_CONTROLLERS = {"cpu", "memory", "io"}
CGROUP_CONTROLLERS = Path("/sys/fs/cgroup/cgroup.controllers")


def check_cgroup(path: Path = CGROUP_CONTROLLERS) -> list[tuple[str, bool, str]]:
    """Check kernel support, not per-container counter readability."""
    try:
        available = set(path.read_text().split())
    except OSError as exc:
        return [("cgroup v2", False, str(exc))]

    missing = REQUIRED_CONTROLLERS - available
    return [
        ("cgroup v2", True, "mounted and readable"),
        ("controllers", not missing, "missing: " + ", ".join(sorted(missing)) if missing else "cpu, memory, io"),
    ]


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=15, check=False)


def check_docker() -> list[tuple[str, bool, str]]:
    if not shutil.which("docker"):
        return [("Docker", False, "docker CLI not found")]

    try:
        info = docker("info", "--format", "{{.CgroupVersion}}")
        if info.returncode:
            return [("Docker", False, info.stderr.strip() or "daemon unavailable")]

        # Docker CLI may target a remote daemon, invalidating host-side measurements.
        if os.getenv("DOCKER_CONTEXT"):
            context = docker("context", "inspect", os.environ["DOCKER_CONTEXT"], "--format", "{{.Endpoints.docker.Host}}")
            endpoint = context.stdout.strip() if context.returncode == 0 else ""
        elif os.getenv("DOCKER_HOST"):
            endpoint = os.environ["DOCKER_HOST"]
        else:
            context = docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}")
            endpoint = context.stdout.strip() if context.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [("Docker", False, str(exc))]

    return [
        ("Docker daemon", True, "reachable"),
        ("Docker endpoint", endpoint.startswith("unix://"), endpoint or "unknown"),
        ("Docker cgroup v2", info.stdout.strip() == "2", info.stdout.strip()),
    ]


def main() -> int:
    print("Capacious SUT Host Preflight")
    print(f"Host: {platform.system()} {platform.release()} ({platform.machine()})")

    checks = [
        ("Linux", platform.system() == "Linux", platform.system()),
        *check_cgroup(),
        *check_docker(),
    ]
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    success = all(ok for _, ok, _ in checks)
    print(f"Overall: {'PASS' if success else 'FAIL'}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
