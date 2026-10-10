#!/usr/bin/env bash
# Prepare a Linux SUT Host for the Docker Record MVP.
#
# Scope: install missing Docker Engine / Python 3 on supported Ubuntu/Debian hosts,
# start the Docker service, and optionally grant this user Docker socket access.
# This script intentionally does NOT remove existing runtimes, reset Docker data,
# change kernel settings, or install Conda/Claude Code.
set -Eeuo pipefail

GRANT_DOCKER_ACCESS=false
DOCKER_VERSION=""

usage() {
  cat <<'USAGE'
Usage: bash scripts/env_setup/setup_sut_host.sh [--grant-docker-access] [--docker-version APT_VERSION]

  --grant-docker-access   Add the invoking user to the docker group, if needed.
                          WARNING: docker group membership grants root-level access.
  --docker-version VER   Install an exact apt package version of docker-ce/cli.
                          Only used for a fresh Docker installation.
  -h, --help              Show this help.

Run as the intended SSH user. The script invokes sudo only for system changes.
Supported for automatic installation: Ubuntu 22.04/24.04/26.04, Debian 12/13.
Already-working Docker installations on other Linux distributions are preserved.
USAGE
}

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[setup] $*"; }

while (($#)); do
  case "$1" in
    --grant-docker-access) GRANT_DOCKER_ACCESS=true; shift ;;
    --docker-version)
      (($# >= 2)) || die "--docker-version needs an apt version string"
      DOCKER_VERSION="$2"
      [[ -n "$DOCKER_VERSION" ]] || die "Docker version cannot be empty"
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ "$(uname -s)" == "Linux" ]] || die "this setup script runs only on Linux"
command -v python3 >/dev/null 2>&1 && log "Python 3 already available: $(python3 --version)"

# Do not run apt against arbitrary Linux distributions or derivatives.
# The check is deferred: preinstalled Docker can work without any package changes.
select_apt_distribution() {
  [[ -r /etc/os-release ]] || die "cannot identify Linux distribution"
  # shellcheck disable=SC1091
  source /etc/os-release
  case "${ID:-}:${VERSION_ID:-}" in
    ubuntu:22.04|ubuntu:24.04|ubuntu:26.04)
      DOCKER_DISTRO=ubuntu
      DOCKER_SUITE="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}" ;;
    debian:12|debian:13)
      DOCKER_DISTRO=debian
      DOCKER_SUITE="${VERSION_CODENAME:-}" ;;
    *) die "automatic installation unsupported on ${PRETTY_NAME:-unknown distro}; provision Docker manually, then run preflight" ;;
  esac
  [[ -n "$DOCKER_SUITE" ]] || die "cannot identify apt repository suite"
  command -v apt-get >/dev/null || die "apt-get not found"
  command -v dpkg-query >/dev/null || die "dpkg-query not found"
}

# sudo is requested only if host state must be changed.
as_root() {
  if (( EUID == 0 )); then
    "$@"
  else
    command -v sudo >/dev/null || die "sudo required for system changes"
    sudo "$@"
  fi
}

package_installed() {
  [[ "$(dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null || true)" == installed ]]
}

install_missing_dependencies() {
  select_apt_distribution
  local need_docker="$1"
  local need_python="$2"

  if [[ "$need_docker" == true ]]; then
    # Removing conflicting packages automatically could disrupt other experiments.
    local conflicts=() pkg
    for pkg in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
      if package_installed "$pkg"; then conflicts+=("$pkg"); fi
    done
    ((${#conflicts[@]} == 0)) || die "conflicting packages installed (${conflicts[*]}). Review Docker's official conflict-removal instructions manually; nothing was removed."
    # Detect partial installations instead of silently attempting an upgrade/repair.
    if package_installed docker-ce || package_installed docker-ce-cli; then
      die "Docker packages are installed but the docker CLI is unavailable; inspect the existing installation manually"
    fi
  fi

  log "Updating apt package metadata"
  as_root apt-get update
  if [[ "$need_python" == true ]]; then
    log "Installing Python 3 (for read-only preflight)"
    as_root apt-get install -y python3
  fi
  if [[ "$need_docker" != true ]]; then return; fi

  log "Installing Docker Engine from Docker's official apt repository"
  as_root apt-get install -y ca-certificates curl
  as_root install -m 0755 -d /etc/apt/keyrings

  # Never execute a downloaded installer. APT verifies packages with this key.
  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    local temp_key
    temp_key="$(mktemp)"
    trap 'rm -f "${temp_key:-}"' EXIT
    curl --fail --silent --show-error --location \
      "https://download.docker.com/linux/${DOCKER_DISTRO}/gpg" -o "$temp_key"
    as_root install -m 0644 "$temp_key" /etc/apt/keyrings/docker.asc
    rm -f "$temp_key"
    trap - EXIT
  else
    log "Using existing /etc/apt/keyrings/docker.asc"
  fi

  if [[ ! -e /etc/apt/sources.list.d/docker.sources ]]; then
    # Write a .sources file atomically in the privileged directory.
    local temp_sources
    temp_sources="$(mktemp)"
    trap 'rm -f "${temp_sources:-}"' EXIT
    cat > "$temp_sources" <<SOURCES
Types: deb
URIs: https://download.docker.com/linux/${DOCKER_DISTRO}
Suites: ${DOCKER_SUITE}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES
    as_root install -m 0644 "$temp_sources" /etc/apt/sources.list.d/docker.sources
    rm -f "$temp_sources"
    trap - EXIT
  else
    log "Using existing /etc/apt/sources.list.d/docker.sources (not overwritten)"
  fi

  as_root apt-get update
  if [[ -n "$DOCKER_VERSION" ]]; then
    as_root apt-get install -y \
      "docker-ce=${DOCKER_VERSION}" "docker-ce-cli=${DOCKER_VERSION}" \
      containerd.io docker-buildx-plugin
  else
    as_root apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  fi
}

NEED_DOCKER=false
NEED_PYTHON=false
command -v docker >/dev/null 2>&1 || NEED_DOCKER=true
command -v python3 >/dev/null 2>&1 || NEED_PYTHON=true

if [[ "$NEED_DOCKER" == true || "$NEED_PYTHON" == true ]]; then
  install_missing_dependencies "$NEED_DOCKER" "$NEED_PYTHON"
else
  log "Docker CLI already installed; installation and upgrades skipped"
fi

command -v docker >/dev/null 2>&1 || die "Docker CLI still unavailable after setup"
command -v python3 >/dev/null 2>&1 || die "Python 3 still unavailable after setup"

# Even when the CLI exists, daemon may be stopped. Start the system Docker unit
# only if the current user cannot already reach a daemon.
if ! docker info >/dev/null 2>&1; then
  if command -v systemctl >/dev/null 2>&1; then
    if ! systemctl is-active --quiet docker; then
      log "Starting and enabling Docker daemon"
      as_root systemctl enable --now docker
    fi
  fi
fi

# Existing Docker users need no privilege escalation. If this user cannot
# access Docker, distinguish a permission failure from an unavailable daemon.
# Clear client overrides for the privileged local-daemon check.
if ! docker info >/dev/null 2>&1; then
  if ! as_root env -u DOCKER_HOST -u DOCKER_CONTEXT docker info >/dev/null 2>&1; then
    die "local Docker daemon unavailable even with administrator permissions; inspect 'systemctl status docker'"
  fi
fi

log "Docker Engine available: $(docker --version)"

if ! docker info >/dev/null 2>&1; then
  if (( EUID == 0 )); then
    die "Docker is unavailable to root's configured context; check DOCKER_HOST/DOCKER_CONTEXT"
  fi
  if [[ "$GRANT_DOCKER_ACCESS" == true ]]; then
    # docker group is root-equivalent: only add when specifically requested.
    login_user="$(id -un)"
    log "Granting ${login_user} membership in docker group (root-equivalent permission)"
    getent group docker >/dev/null || as_root groupadd docker
    as_root usermod -aG docker "$login_user"
    echo "[setup] Group membership updated. Reconnect SSH (or run 'newgrp docker') before preflight."
  else
    echo "[setup] Docker daemon is running, but this user cannot access its socket."
    echo "[setup] To permit non-sudo Docker: bash scripts/env_setup/setup_sut_host.sh --grant-docker-access"
    echo "[setup] WARNING: docker group grants root-level privileges. See README.md"
    exit 1
  fi
fi

log "Host provisioning completed"

# Keep setup and preflight separate and independently runnable. For convenience,
# execute preflight now when the active login session already has Docker access.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFLIGHT="${SCRIPT_DIR}/preflight_sut_host.py"
if [[ -f "$PREFLIGHT" ]] && docker info >/dev/null 2>&1; then
  log "Running read-only SUT Host preflight"
  python3 "$PREFLIGHT"
else
  log "After refreshing permissions, run:"
  echo "  python3 scripts/env_setup/preflight_sut_host.py"
fi
