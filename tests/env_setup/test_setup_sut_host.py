"""Non-destructive tests for the SUT Host setup script."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "env_setup" / "setup_sut_host.sh"


def test_shell_syntax_and_help():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    result = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--grant-docker-access" in result.stdout


def test_existing_docker_skips_installation(tmp_path):
    """Use a fake Docker CLI: this test must not install or change the host."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  info) exit 0 ;;\n"
        "  --version) echo 'Docker version FAKE' ;;\n"
        "  *) echo unexpected >&2; exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    # Copy setup alongside a mock preflight to avoid running real environment checks.
    script_dir = tmp_path / "scripts" / "env_setup"
    script_dir.mkdir(parents=True)
    setup_script = script_dir / "setup_sut_host.sh"
    setup_script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    (script_dir / "preflight_sut_host.py").write_text(
        "import sys\nassert len(sys.argv) == 1\nprint('MOCK PREFLIGHT PASS')\n",
        encoding="utf-8",
    )

    env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]}
    result = subprocess.run(
        ["bash", str(setup_script)], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "installation and upgrades skipped" in result.stdout
    assert "provisioning completed" in result.stdout
    assert "MOCK PREFLIGHT PASS" in result.stdout


def test_unknown_flag_fails_before_changes():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--not-a-real-option"], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "unknown option" in result.stderr
