# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: MPL-2.0

import logging
import tempfile
from pathlib import Path

import yaml

from .utils import make_http_session, setup_signing_key, fetch_package_debs
from .config import DistroConfig
from .reprepro import reprepro_includedeb, build_distributions_content

log = logging.getLogger(__name__)


class RepoBuilder:
    """Orchestrates downloading packages and building APT repositories."""

    def __init__(
        self,
        pkginfo_dir: Path,
        output_dir: Path,
        config_dir: Path,
        cache_dir: Path | None = None,
        continue_on_error: bool = False,
    ) -> None:
        self._pkginfo_dir = pkginfo_dir
        self._output_dir = output_dir
        self._config_dir = config_dir
        self._cache_dir = cache_dir
        self._continue_on_error = continue_on_error
        self._websession = make_http_session()
        self._gpghome: Path | None = None
        self._signing_key_id: str | None = None

        if not self._cache_dir:
            self._cache_dir = Path(tempfile.gettempdir()) / "reporepo-cache"

    def load_all(self) -> dict[str, dict[str, dict]]:
        """
        Walk ``distros/`` and return
        ``{distro: {channel: {codename: release_data}}}``.
        """
        result: dict[str, dict[str, dict]] = {}
        for distro_dir in sorted(self._pkginfo_dir.iterdir()):
            if not distro_dir.is_dir() or distro_dir.name.startswith("."):
                continue
            distro = distro_dir.name
            channels: dict[str, dict] = {}
            for yaml_file in sorted(distro_dir.glob("*.yaml")):
                channel = yaml_file.stem
                with open(yaml_file) as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict):
                    channels[channel] = data
                    log.debug("Loaded %s/%s (%d codename(s))", distro, channel, len(data))
            if channels:
                result[distro] = channels
        return result

    def setup_signing_key(self) -> str | None:
        """
        Prepare the isolated GPG keyring and return the key fingerprint.

        Raises :class:`RuntimeError` if no signing key is configured —
        repositories are always signed.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._gpghome, self._signing_key_id = setup_signing_key(self._config_dir, self._cache_dir)
        return self._signing_key_id

    def setup_reprepro(
        self,
        distro: str,
        repo_dir: Path,
        channels: dict[str, dict],
        signing_key_id: str | None,
    ) -> None:
        """Create (or refresh) the reprepro ``conf/`` directory."""
        conf_dir = repo_dir / "conf"
        conf_dir.mkdir(parents=True, exist_ok=True)

        distro_cfg = DistroConfig.load(self._config_dir, distro)

        # conf/distributions
        if distro_cfg.distributions:
            # Inline content from the YAML takes precedence.
            (conf_dir / "distributions").write_text(distro_cfg.distributions)
            log.info("Using inline distributions config from %s-config.yaml", distro)
        else:
            content = build_distributions_content(
                channels, signing_key_id, distro_cfg.architectures_str
            )
            (conf_dir / "distributions").write_text(content)
            log.info(
                "Generated conf/distributions for %s:\n%s",
                distro,
                content.rstrip(),
            )

        # conf/options (optional)
        if distro_cfg.reprepro_options:
            options_text = "\n".join(distro_cfg.reprepro_options) + "\n"
            (conf_dir / "options").write_text(options_text)
            log.info("Wrote conf/options for %s", distro)

    def build(self) -> bool:
        """
        Build all APT repositories.

        Returns ``True`` on success, ``False`` if any package failed.
        """
        all_distros = self.load_all()
        if not all_distros:
            log.error("No distro YAML files found under %s", self._pkginfo_dir)
            return False

        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._config_dir.mkdir(parents=True, exist_ok=True)

        signing_key_id = self.setup_signing_key()
        errors: list[str] = []

        for distro, channels in all_distros.items():
            log.info("━" * 60)
            log.info("Building APT repository: %s", distro)
            log.info("━" * 60)

            repo_dir = self._output_dir / distro
            repo_dir.mkdir(parents=True, exist_ok=True)

            self.setup_reprepro(distro, repo_dir, channels, signing_key_id)

            for channel, releases in channels.items():
                for codename, release_data in releases.items():
                    packages = release_data.get("packages", [])
                    log.info(
                        "Channel %-12s  codename %-12s  %d package(s)",
                        channel,
                        codename,
                        len(packages),
                    )

                    with tempfile.TemporaryDirectory(
                        prefix=f"apt-repo-{distro}-{codename}-"
                    ) as tmpdir:
                        work_dir = Path(tmpdir)

                        for pkg in packages:
                            label = f"{pkg.get('name', '?')} {pkg.get('version', '')}".strip()
                            log.info("  Package: %s", label)
                            try:
                                # package-level 'type' acts as a fallback for
                                # file entries that don't carry their own type
                                pkg_type_fallback: str | None = pkg.get("type")
                                files = pkg.get("files", [])
                                if not files:
                                    raise ValueError(f"Package {label!r} has no 'files' entries")
                                debs: list[Path] = []
                                for file_entry in files:
                                    if pkg_type_fallback and "type" not in file_entry:
                                        file_entry = dict(file_entry, type=pkg_type_fallback)
                                    debs.extend(
                                        fetch_package_debs(
                                            self._websession,
                                            file_entry,
                                            work_dir,
                                            self._cache_dir,
                                        )
                                    )
                                for deb in debs:
                                    reprepro_includedeb(
                                        repo_dir,
                                        self._cache_dir / "rr" / distro,
                                        codename,
                                        channel,
                                        deb,
                                        self._gpghome,
                                    )
                            except Exception as exc:
                                msg = f"{distro}/{codename}/{channel} [{label}]: {exc}"
                                log.error("FAILED — %s", msg)
                                errors.append(msg)
                                if not self._continue_on_error:
                                    log.error(
                                        "Aborting. Use --continue-on-error to"
                                        " keep going after failures."
                                    )
                                    return False

        if errors:
            log.error("%d error(s) occurred during the build:", len(errors))
            for err in errors:
                log.error("  • %s", err)
            return False

        log.info("━" * 60)
        log.info("✓ All repositories built successfully.")
        log.info("━" * 60)
        return True
