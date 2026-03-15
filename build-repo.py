#!/usr/bin/env python3
#
# Copyright (C) 2026 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: MPL-2.0

"""
APT Repository Builder

Reads package definitions from the distros/ directory and creates
APT repositories using reprepro in the output/ directory.

Directory layout expected
-------------------------
  distros/
    <distro>/           e.g. ubuntu/, debian/
      <channel>.yaml    e.g. stable.yaml, snapshots.yaml

  config/               (optional)
    signing_key.asc     GPG private key to import (ASCII-armored)
    signing_key.gpg     GPG private key to import (binary)
    signing_key_id      Text file containing the GPG key ID / fingerprint
    <distro>-config.yaml  Per-distro build settings (architectures, options, …)

  output/               Created automatically
    <distro>/           reprepro repository root

YAML config format
------------------
  <codename>:
    version: <human-readable version>   # optional
    packages:
      - name: <package-name>
        version: <version>              # optional, informational only
        type: deb | zip | tar           # download format
        url: <download-url>
        sha256: <hex-sha256>
"""

import sys
import logging
import argparse
from pathlib import Path

from reporepo import RepoBuilder

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build-repo",
        description="Build APT repositories from YAML package lists.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--distros-dir",
        type=Path,
        default=Path("distros"),
        metavar="DIR",
        help="Directory containing distribution YAML files (default: distros/)",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        metavar="DIR",
        help="Configuration directory (default: config/)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("_target"),
        metavar="DIR",
        help="Output directory for APT repositories (default: _target/)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("_cache"),
        metavar="DIR",
        help="Cache directory for downloads and databases (default: _cache/)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing other packages when one fails",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.distros_dir.is_dir():
        log.error("distros directory not found: %s", args.distros_dir)
        return 1

    builder = RepoBuilder(
        distros_dir=args.distros_dir,
        output_dir=args.output_dir,
        config_dir=args.config_dir,
        cache_dir=args.cache_dir,
        continue_on_error=args.continue_on_error,
    )

    return 0 if builder.build() else 1


if __name__ == "__main__":
    sys.exit(main())
