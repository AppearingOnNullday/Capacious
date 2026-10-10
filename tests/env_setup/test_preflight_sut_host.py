"""Test failure conditions without requiring Docker on the CI runner."""

from pathlib import Path
from runpy import run_path

script = run_path(str(Path(__file__).resolve().parents[2] / "scripts/env_setup/preflight_sut_host.py"))
check_cgroup = script["check_cgroup"]
check_docker = script["check_docker"]


def test_cgroup_requires_cpu_memory_io(tmp_path):
    path = tmp_path / "cgroup.controllers"
    path.write_text("cpu memory io pids\n")
    assert all(ok for _, ok, _ in check_cgroup(path))

    path.write_text("cpu memory\n")
    results = check_cgroup(path)
    assert results[0][1] is True
    assert results[1][1] is False
    assert "io" in results[1][2]


def test_missing_docker_fails(monkeypatch):
    monkeypatch.setitem(check_docker.__globals__["shutil"].__dict__, "which", lambda _: None)
    assert check_docker()[0][1] is False


def test_remote_docker_endpoint_fails(monkeypatch):
    from subprocess import CompletedProcess

    namespace = check_docker.__globals__
    monkeypatch.setattr(namespace["shutil"], "which", lambda _: "/usr/bin/docker")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setenv("DOCKER_HOST", "tcp://server:2375")
    monkeypatch.setitem(namespace, "docker", lambda *args: CompletedProcess(args, 0, stdout="2\n"))

    checks = check_docker()
    assert checks[0][1] is True
    assert checks[1][1] is False  # Host-side cgroup readings would target the wrong machine.
