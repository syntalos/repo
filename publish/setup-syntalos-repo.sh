#!/bin/sh
#
# Setup script to easily configure the Syntalos APT repository.
#
set -eu

REPO_BASE_URL="https://syntalos.github.io/repo"
KEYRING_URL="https://raw.githubusercontent.com/syntalos/repo/refs/heads/main/publish/syntalos-repo.asc"

KEYRING_DIR=/etc/apt/keyrings
KEYRING_FILE=$KEYRING_DIR/syntalos-repo.asc
SOURCES_FILE=/etc/apt/sources.list.d/syntalos.sources

if [ "$(id -u)" -ne 0 ]; then
    echo "This installer must be run as root." >&2
    exit 1
fi

if [ ! -r /etc/os-release ]; then
    echo "Unable to detect operating system: /etc/os-release not found." >&2
    exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release

case "${ID:-}" in
    debian)
        case "${VERSION_CODENAME:-}" in
            trixie)
                REPO_URL="${REPO_BASE_URL}/debian/"
                SUITE="${VERSION_CODENAME}"
                ;;
            *)
                echo "Unsupported Debian release: ${VERSION_CODENAME:-unknown}" >&2
                echo "Supported Debian release: trixie" >&2
                exit 1
                ;;
        esac
        ;;
    ubuntu)
        case "${VERSION_CODENAME:-}" in
            noble|resolute)
                REPO_URL="${REPO_BASE_URL}/ubuntu/"
                SUITE="${VERSION_CODENAME}"
                ;;
            *)
                echo "Unsupported Ubuntu release: ${VERSION_CODENAME:-unknown}" >&2
                echo "Supported Ubuntu releases: noble, resolute" >&2
                exit 1
                ;;
        esac
        ;;
    *)
        echo "Unsupported distribution: ${ID:-unknown}" >&2
        echo "We only support Ubuntu and Debian right now." >&2
        echo "Compiling from source or the Flatpak package might work for you." >&2
        exit 1
        ;;
esac

install -d -m 0755 "$KEYRING_DIR"

TMP_KEY="$(mktemp)"
trap 'rm -f "$TMP_KEY"' EXIT INT TERM HUP

curl -fsSL "${KEYRING_URL}" -o "$TMP_KEY"
install -m 0644 "$TMP_KEY" "$KEYRING_FILE"

cat >"$SOURCES_FILE" <<EOF
Types: deb
URIs: $REPO_URL
Suites: $SUITE
Components: stable
Signed-By: $KEYRING_FILE
EOF

apt update

echo
echo "Syntalos repository installed successfully."
