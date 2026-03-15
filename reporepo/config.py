# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: MPL-2.0

"""Per-distribution configuration, loaded from ``config/<distro>-config.yaml``.

YAML layout
-----------
  architectures:          # optional; defaults to [amd64, arm64]
    - amd64
    - arm64

  reprepro_options:       # optional; written verbatim to conf/options
    - verbose
    - ask-passphrase

  distributions: |        # optional; overrides the auto-generated conf/distributions
    Codename: noble
    Suite: noble
    Components: stable
    Architectures: amd64 arm64
    SignWith: 0xABCDEF01
"""

from pathlib import Path
from dataclasses import field, dataclass

import yaml


@dataclass
class DistroConfig:
    """Holds per-distribution build configuration."""

    architectures: list[str] = field(default_factory=lambda: ["amd64", "arm64"])
    reprepro_options: list[str] = field(default_factory=list)
    # When set, this string is written verbatim to conf/distributions instead
    # of the auto-generated content.
    distributions: str | None = None

    @property
    def architectures_str(self) -> str:
        """Space-separated architecture string for reprepro."""
        return " ".join(self.architectures)

    @classmethod
    def load(cls, config_dir: Path, distro: str) -> "DistroConfig":
        """
        Load configuration from ``config/<distro>-config.yaml``.

        Returns a default :class:`DistroConfig` when the file does not exist.
        """
        config_file = config_dir / f"{distro}-config.yaml"
        if not config_file.exists():
            return cls()

        with open(config_file) as fh:
            data: dict = yaml.safe_load(fh) or {}

        raw_arches = data.get("architectures", ["amd64", "arm64"])
        if isinstance(raw_arches, str):
            # Accept a single space-separated string as well as a YAML list.
            arches = raw_arches.split()
        else:
            arches = [str(a) for a in raw_arches]

        return cls(
            architectures=arches,
            reprepro_options=[str(o) for o in data.get("reprepro_options", [])],
            distributions=data.get("distributions"),
        )
