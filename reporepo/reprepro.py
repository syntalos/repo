# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: MPL-2.0

import os
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def reprepro_includedeb(
    basedir: Path,
    cachedir: Path,
    codename: str,
    component: str,
    deb_path: Path,
    gnupghome: Path,
) -> None:
    """
    Call ``reprepro includedeb`` to add *deb_path* to the repository.

    Silently skips if reprepro reports the package is already registered
    (making repeated runs idempotent).
    """
    cmd = [
        "reprepro",
        "--basedir",
        str(basedir),
        "--dbdir",
        str(cachedir / "db"),
        "-C",
        component,
        "includedeb",
        codename,
        str(deb_path),
    ]
    env = os.environ.copy()
    env["GNUPGHOME"] = str(gnupghome)

    log.debug("  $ %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.stdout:
        log.debug("reprepro stdout: %s", result.stdout.rstrip())

    if result.returncode != 0:
        stderr_lower = result.stderr.lower()
        # reprepro prints this when the exact same version is already present.
        if "already registered" in stderr_lower or "already exists" in stderr_lower:
            log.warning(
                "  ⚠ %s already present in %s/%s - skipping",
                deb_path.name,
                codename,
                component,
            )
            return
        raise RuntimeError(
            f"reprepro includedeb failed (exit {result.returncode}):\n"
            f"{result.stderr}\n{result.stdout}"
        )

    log.info("  ✓ Added %s → %s / %s", deb_path.name, codename, component)


def build_distributions_content(
    channels: dict[str, dict],
    signing_key_id: str | None,
    architectures: str,
) -> str:
    """
    Generate a reprepro ``conf/distributions`` file from the channel data.

    *channels* maps ``channel_name → {codename: release_data}``.
    Each stanza covers one codename, listing all its channels as components.
    """
    # Collect codename → {version, set-of-channels}
    codename_info: dict[str, dict] = {}
    for channel, releases in channels.items():
        for codename, release_data in releases.items():
            entry = codename_info.setdefault(
                codename,
                {"version": release_data.get("version", ""), "channels": set()},
            )
            entry["channels"].add(channel)

    stanzas: list[str] = []
    for codename, info in sorted(codename_info.items()):
        components = " ".join(sorted(info["channels"]))
        lines = [
            f"Codename: {codename}",
            f"Suite: {codename}",
        ]
        if info["version"]:
            lines.append(f"Version: {info['version']}")
        lines.append(f"Components: {components}")
        lines.append(f"Architectures: {architectures}")
        if signing_key_id:
            lines.append(f"SignWith: {signing_key_id}")
        # Omitting SignWith → reprepro won't sign (safer than "SignWith: !").
        stanzas.append("\n".join(lines))

    return "\n\n".join(stanzas) + "\n"
