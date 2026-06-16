#!/usr/bin/env bash
set -euo pipefail

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "Docker and Docker Compose are already installed."
  exit 0
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
else
  echo "Cannot determine OS: /etc/os-release is missing." >&2
  exit 1
fi

case "${ID:-}" in
  ubuntu|debian)
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg git rsync
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${ID}/gpg" | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    ;;
  amzn)
    sudo dnf update -y
    sudo dnf install -y docker git rsync
    sudo systemctl enable --now docker
    if ! docker compose version >/dev/null 2>&1; then
      sudo mkdir -p /usr/local/lib/docker/cli-plugins
      arch="$(uname -m)"
      case "${arch}" in
        x86_64) compose_arch="x86_64" ;;
        aarch64|arm64) compose_arch="aarch64" ;;
        *)
          echo "Unsupported architecture for Docker Compose plugin: ${arch}" >&2
          exit 1
          ;;
      esac
      sudo curl -fsSL \
        "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-${compose_arch}" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
      sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    fi
    ;;
  *)
    echo "Unsupported OS '${ID:-unknown}'. Use Ubuntu 24.04 LTS or Amazon Linux 2023." >&2
    exit 1
    ;;
esac

sudo systemctl enable --now docker
sudo usermod -aG docker "${USER}"

echo "Bootstrap complete. Log out and back in before running docker without sudo."
