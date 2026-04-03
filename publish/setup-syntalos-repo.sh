#!/bin/sh
#
# Setup script to easily configure the Syntalos APT repository.
#
set -eu

# NOTE: We are not longer using GitHub Pages to deploy our packages!
# We have migrated to Cliudsmith for that purpose.
# This script has been adjusted to set up the Cloudsmith repo instead of
# the GitHub Pages repo instead.

REPO_BASE_URL="https://dl.cloudsmith.io/public/syntalos/syntalos/deb"
KEYRING_URL="https://syntalos.org/setup/syntalos-repo.gpg"

KEYRING_DIR=/etc/apt/keyrings
KEYRING_FILE=$KEYRING_DIR/syntalos-repo.gpg
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
            trixie|forky)
                REPO_URL="${REPO_BASE_URL}/debian/"
                SUITE="${VERSION_CODENAME}"
                ;;
            *)
                echo "Unsupported Debian release: ${VERSION_CODENAME:-unknown}" >&2
                echo "Supported Debian releases: trixie, forky" >&2
                exit 1
                ;;
        esac
        ;;
    ubuntu)
        case "${VERSION_CODENAME:-}" in
            noble)
                # on Ubuntu 24.04, we are using the older PPA instead of the new GitHub deployment
                add-apt-repository ppa:ximion/syntalos
                echo
                echo "Syntalos repository installed successfully."
                exit 0
                ;;
            resolute)
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
        echo "Check out https://syntalos.org/get/ for more information." >&2
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
Components: main
Signed-By: $KEYRING_FILE
EOF

apt update

echo
echo "Syntalos repository installed successfully."
