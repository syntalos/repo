#!/usr/bin/env python3
#
# Copyright (C) 2026 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: MPL-2.0

"""
Manifest Updater

Adds a new package entry to a channel manifest, promoting the previous entry
to ``<name>-previous`` (dropping any older ``-previous`` entry that already
existed).  Checksums are computed locally from the supplied files; URLs are
constructed as ``<base-url>/<basename>``.

Usage example
-------------
  ./update-manifest.py \\
      --distro ubuntu --suite noble --channel stable \\
      --name syntalos --version 2.2.0 \\
      --base-url https://github.com/syntalos/syntalos/releases/download/v2.2.0 \\
      syntalos_2.2.0_amd64_ubuntu24.04.zip syntalos_2.2.0_arm64_ubuntu24.04.zip
"""

import sys
import logging
import argparse
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from reporepo.utils import sha256_file

log = logging.getLogger(__name__)


def _ensure_blank_line_before(seq: CommentedSeq, index: int) -> None:
    """Add one blank line before *seq[index]* in the YAML output if not already present.

    ruamel.yaml stores blank-line separators as ``CommentToken('\\n', ...)``
    values in ``seq.ca.items[index][1]`` (the "before" comment slot).
    We inspect that slot first so we never double-up on existing spacing.
    """
    if index >= len(seq):
        return

    existing = seq.ca.items.get(index)
    before_tokens = existing[1] if existing else None

    # If any token in the "before" slot already contains a newline the blank
    # line is already there — nothing to do.
    if before_tokens:
        for tok in before_tokens:
            if "\n" in tok.value:
                return

    blank = CommentToken("\n", CommentMark(0), None)
    if before_tokens is not None:
        before_tokens.insert(0, blank)
    elif existing:
        existing[1] = [blank]
    else:
        seq.ca.items[index] = [None, [blank], None, None]


def build_file_entry(local_file: Path, base_url: str) -> CommentedMap:
    """Return a ruamel CommentedMap for one file entry."""
    url = base_url.rstrip("/") + "/" + local_file.name
    digest = sha256_file(local_file)
    log.info("  %s  sha256:%s", local_file.name, digest)
    entry = CommentedMap()
    entry["url"] = url
    entry["sha256"] = digest
    return entry


def build_package_entry(name: str, version: str, file_entries: list[CommentedMap]) -> CommentedMap:
    """Return a ruamel CommentedMap for a full package entry."""
    pkg = CommentedMap()
    pkg["name"] = name
    pkg["version"] = version
    files_seq = CommentedSeq(file_entries)
    pkg["files"] = files_seq
    return pkg


def update_manifest(
    manifest_path: Path,
    suite: str,
    name: str,
    version: str,
    base_url: str,
    local_files: list[Path],
) -> None:
    """
    Edit *manifest_path* in-place:

    1. Remove any existing ``<name>-previous`` entry in *suite*.
    2. Rename the existing ``<name>`` entry to ``<name>-previous``.
    3. Insert a fresh ``<name>`` entry (with the supplied files) at the
       position where the old entry was, or append if none existed before.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # avoid unwanted line wrapping

    with open(manifest_path) as fh:
        data = yaml.load(fh)

    if data is None:
        log.error("Manifest file is empty: %s", manifest_path)
        sys.exit(1)

    if suite not in data:
        log.error(
            "Suite %r not found in %s.  Available suites: %s",
            suite,
            manifest_path,
            ", ".join(data.keys()),
        )
        sys.exit(1)

    suite_data = data[suite]
    packages: CommentedSeq = suite_data.get("packages")
    if packages is None:
        log.error("Suite %r has no 'packages' key in %s", suite, manifest_path)
        sys.exit(1)

    previous_name = f"{name}-previous"
    old_index: int | None = None  # where the current ``name`` entry lives

    # locate entries we care about, collect indices to drop
    indices_to_remove: list[int] = []
    for i, pkg in enumerate(packages):
        pkg_name = pkg.get("name", "")
        if pkg_name == previous_name:
            indices_to_remove.append(i)
        elif pkg_name == name:
            old_index = i

    # drop old "-previous" entries (highest index first)
    for i in sorted(indices_to_remove, reverse=True):
        log.info("Removing stale '%s' entry at index %d", previous_name, i)
        del packages[i]
        # adjust old_index if it was after a removed item
        if old_index is not None and i < old_index:
            old_index -= 1

    # build new entry
    file_entries = [build_file_entry(f, base_url) for f in local_files]
    new_pkg = build_package_entry(name, version, file_entries)

    # rename existing entry to "*-previous" and insert new one
    insert_at: int
    if old_index is not None:
        log.info(
            "Renaming existing '%s' entry (index %d) to '%s'",
            name,
            old_index,
            previous_name,
        )
        packages[old_index]["name"] = previous_name
        # Insert new entry right before the now-renamed previous entry
        insert_at = old_index
        packages.insert(insert_at, new_pkg)
        # Ensure a blank line separates the new entry from the previous one
        _ensure_blank_line_before(packages, insert_at + 1)
    else:
        log.info("No existing '%s' entry found; appending new entry.", name)
        packages.append(new_pkg)

    # write back
    with open(manifest_path, "w") as fh:
        yaml.dump(data, fh)

    log.info("Updated %s  (suite=%s, package=%s, version=%s)", manifest_path, suite, name, version)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        prog="update-manifest",
        description="Add a new package version to a channel manifest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        metavar="FILE",
        help="Local package files to include in the new entry.",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        metavar="URL",
        help=(
            "Base URL used to construct download URLs.  Each file's URL is "
            "built as <base-url>/<filename>.  "
            "Example: https://github.com/org/pkg/releases/download/v1.2.3"
        ),
    )
    parser.add_argument(
        "--name",
        required=True,
        metavar="NAME",
        help="Package name as it appears in the manifest (e.g. syntalos).",
    )
    parser.add_argument(
        "--version",
        required=True,
        metavar="VERSION",
        help="Version string for the new package entry (e.g. 2.2.0).",
    )
    parser.add_argument(
        "--distro",
        required=True,
        metavar="DISTRO",
        help="Distribution name, used to locate manifests/<distro>/. " "Examples: debian, ubuntu",
    )
    parser.add_argument(
        "--suite",
        required=True,
        metavar="SUITE",
        help="Suite (codename) inside the manifest (e.g. trixie, noble).",
    )
    parser.add_argument(
        "--channel",
        required=True,
        metavar="CHANNEL",
        help="Channel name that determines which YAML file to edit "
        "(e.g. stable → manifests/<distro>/stable.yaml).",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=Path("manifests"),
        metavar="DIR",
        help="Root directory that contains per-distro manifest sub-directories. "
        "Defaults to ./manifests.",
    )

    args = parser.parse_args(argv)

    # basic input validation
    manifest_path = args.manifests_dir / args.distro / f"{args.channel}.yaml"
    if not manifest_path.exists():
        log.error("Manifest file not found: %s", manifest_path)
        return 1

    missing = [f for f in args.files if not f.exists()]
    if missing:
        for f in missing:
            log.error("File not found: %s", f)
        return 1

    # run
    log.info(
        "Updating manifest for %s/%s/%s  package=%s  version=%s",
        args.distro,
        args.suite,
        args.channel,
        args.name,
        args.version,
    )
    log.info("Computing checksums for %d file(s):", len(args.files))

    update_manifest(
        manifest_path=manifest_path,
        suite=args.suite,
        name=args.name,
        version=args.version,
        base_url=args.base_url,
        local_files=args.files,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
