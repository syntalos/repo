# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: MPL-2.0

import os
import shutil
import hashlib
import logging
import tarfile
import zipfile
import subprocess
from pathlib import Path

import requests
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

log = logging.getLogger(__name__)

_TAR_TYPES: frozenset[str] = frozenset({".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar"})


def setup_signing_key(config_dir: Path, cache_dir: Path) -> tuple[Path, str]:
    """
    Prepare an isolated GPG keyring and return ``(gnupghome, fingerprint)``.

    Raises :class:`RuntimeError` when no key file is found so that the build
    always fails loudly rather than producing unsigned repositories.
    """
    # locate the key file
    key_path: Path | None = None
    for name in ("signing_key.asc", "signing_key.gpg"):
        candidate = config_dir / name
        if candidate.exists():
            key_path = candidate
            break

    if key_path is None:
        raise RuntimeError(
            "No signing key found in config/.\n"
            "Place your GPG private key in config/signing_key.asc "
            "(ASCII-armored) or config/signing_key.gpg (binary)."
        )

    # create an isolated keyring dir
    gpghome = cache_dir / "gpghome"
    gpghome.mkdir(mode=0o700, exist_ok=True)
    gpghome.chmod(0o700)  # enforce permissions even if it already existed

    # unset the GPG agent-related stuff that may interfere
    env = os.environ.copy()
    env.pop("GPG_AGENT_INFO", None)
    env.pop("SSH_AUTH_SOCK", None)
    env["GNUPGHOME"] = str(gpghome.absolute())

    def run_gpg(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a GPG command."""
        result = subprocess.run(
            args,
            env=env,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            stdout = f"stdout:\n{stdout}\n\n" if stdout else ""
            stderr = f"stderr:\n{stderr}" if stderr else ""
            raise RuntimeError(f"Command failed: {' '.join(args)}\n" f"{stdout}{stderr}")
        return result

    # if gpg-agent isn't running, all secret key actions fill fail
    subprocess.run(
        ["gpg-agent", "--disable-scdaemon", "--batch", "--daemon"],
        env=env,
    )

    # if a secret key already exists, don't import again.
    existing = run_gpg(
        [
            "gpg",
            "--homedir",
            str(gpghome.absolute()),
            "--batch",
            "--with-colons",
            "--list-secret-keys",
        ],
        check=False,
    )

    fingerprint: str | None = None
    if existing.returncode == 0:
        for line in existing.stdout.splitlines():
            parts = line.split(":")
            if parts[0] == "fpr" and len(parts) > 9 and parts[9]:
                fingerprint = parts[9]
                break

    if fingerprint:
        log.info("Detected signing key fingerprint: %s", fingerprint)
        return gpghome, fingerprint

    # No secret key present yet: import it.
    log.info("Importing GPG signing key from %s", key_path.name)
    run_gpg(
        [
            "gpg",
            "--homedir",
            str(gpghome.absolute()),
            "--batch",
            "--import",
            str(key_path.absolute()),
        ],
        check=True,
    )

    # Now determine fingerprint from the imported secret key.
    listed = run_gpg(
        ["gpg", "--homedir", str(gpghome), "--batch", "--with-colons", "--list-secret-keys"]
    )

    fingerprint = None
    for line in listed.stdout.splitlines():
        parts = line.split(":")
        if parts[0] == "fpr" and len(parts) > 9 and parts[9]:
            fingerprint = parts[9]
            break

    if not fingerprint:
        raise RuntimeError("Could not determine fingerprint of the imported signing key.")

    log.info("Detected signing key fingerprint: %s", fingerprint)
    return gpghome, fingerprint


def sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 digest of *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_http_session() -> requests.Session:
    """Return a :class:`requests.Session` with automatic retries."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def download_file(
    session: requests.Session,
    url: str,
    dest: Path,
    expected_sha256: str,
) -> None:
    """Download *url* to *dest* and verify its SHA-256 checksum."""
    log.info("Downloading %s", url)
    resp = session.get(url, stream=True, timeout=600)
    resp.raise_for_status()

    total = int(resp.headers.get("Content-Length", 0)) or None
    with (
        open(dest, "wb") as fh,
        Progress(
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            transient=True,
        ) as progress,
    ):
        task = progress.add_task(dest.name, total=total)
        for chunk in resp.iter_content(chunk_size=65_536):
            fh.write(chunk)
            progress.update(task, advance=len(chunk))

    actual = sha256_file(dest)
    if actual.lower() != expected_sha256.lower():
        dest.unlink(missing_ok=True)
        raise ValueError(
            f"SHA-256 mismatch for {url}\n"
            f"  expected : {expected_sha256}\n"
            f"  actual   : {actual}"
        )
    log.info("  ✓ SHA-256 OK  %s", actual)


def _extract_debs_zip(archive: Path, dest_dir: Path) -> list[Path]:
    """Return list of .deb paths extracted from a ZIP archive."""
    debs: list[Path] = []
    with zipfile.ZipFile(archive, "r") as zf:
        for entry in zf.namelist():
            if entry.endswith(".deb"):
                target = dest_dir / Path(entry).name
                log.debug("  extracting %s → %s", entry, target.name)
                target.write_bytes(zf.read(entry))
                debs.append(target)
    return debs


def _extract_debs_tar(archive: Path, dest_dir: Path) -> list[Path]:
    """Return list of .deb paths extracted from a tar archive."""
    debs: list[Path] = []
    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            if member.isfile() and member.name.endswith(".deb"):
                target = dest_dir / Path(member.name).name
                log.debug("  extracting %s → %s", member.name, target.name)
                src = tf.extractfile(member)
                if src is not None:
                    target.write_bytes(src.read())
                    debs.append(target)
    return debs


def _infer_type_from_url(url: str) -> str:
    """Infer the file type from the URL filename extension."""
    name = Path(url).name.lower()
    if name.endswith(".deb"):
        return "deb"
    if name.endswith(".zip"):
        return "zip"
    for ext in _TAR_TYPES:
        if name.endswith(ext):
            return "tar"
    # Fall back to treating it as zip file (we fail early if it isn't)
    return "zip"


def fetch_package_debs(
    session: requests.Session,
    file_entry: dict,
    work_dir: Path,
    cache_dir: Path | None,
) -> list[Path]:
    """
    Download (or retrieve from cache) a single file entry and return the list
    of .deb files it provides.

    *file_entry* must contain at least ``url`` and ``sha256``.
    """
    url: str = file_entry["url"]
    expected_sha256: str = file_entry["sha256"]
    pkg_type: str = file_entry.get("type") or _infer_type_from_url(url)
    pkg_type = pkg_type.lower()
    url_filename = Path(url).name

    # resolve download path (possibly from cache)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / url_filename
        if cached.exists() and sha256_file(cached).lower() == expected_sha256.lower():
            log.info("  Cache hit: %s", cached.name)
            download_path = cached
        else:
            if cached.exists():
                log.warning("  Cache checksum mismatch, re-downloading %s", cached.name)
                cached.unlink()
            download_file(session, url, cached, expected_sha256)
            download_path = cached
    else:
        download_path = work_dir / url_filename
        download_file(session, url, download_path, expected_sha256)

    # process by type
    if pkg_type == "deb":
        # Copy into work_dir so all results live in the same temp directory.
        if download_path.parent != work_dir:
            dest = work_dir / download_path.name
            shutil.copy2(download_path, dest)
            return [dest]
        return [download_path]

    if pkg_type == "zip":
        debs = _extract_debs_zip(download_path, work_dir)
        if not debs:
            raise ValueError(f"No .deb files found inside ZIP: {url}")
        return debs

    if pkg_type == "tar":
        debs = _extract_debs_tar(download_path, work_dir)
        if not debs:
            raise ValueError(f"No .deb files found inside tarball: {url}")
        return debs

    raise ValueError(f"Unknown package type {pkg_type!r} (url: {url})")
