#!/bin/sh
set -e

apt-get install -yq \
    python3-yaml \
    python3-ruamel.yaml \
    python3-requests \
    python3-rich \
    reprepro \
    gnupg
