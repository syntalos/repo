# Syntalos Package Repository

Native APT repository for [Syntalos](https://github.com/syntalos/syntalos)
and related packages, served via GitHub Pages.

**Repository URL:** `https://syntalos.github.io/repo`


---

## Using the repository

### Automatic setup

```bash
curl -fsSL https://raw.githubusercontent.com/syntalos/repo/refs/heads/main/publish/setup-syntalos-repo.sh | sudo sh
```

The script detects your distribution, installs the signing key to
`/etc/apt/keyrings/syntalos-repo.asc`, writes a `.sources` file, and runs
`apt update` automatically.

You can then run `sudo apt install syntalos` to install Syntalos.


### Supported distributions

| Distribution | Suite | `<distro>` |
|---|---|---|
| Debian 13 (Trixie) | `trixie` | `debian` |
| Ubuntu 24.04 LTS (Noble) | `noble` | `ubuntu` |
| Ubuntu 26.04 LTS (Resolute) | `resolute` | `ubuntu` |


---

## Maintaining the repository

### Repository layout

```
manifests/          Package definitions (one YAML per distro/channel)
  debian/
    stable.yaml
  ubuntu/
    stable.yaml
config/             Build configuration
publish/            Files published alongside the repo
  syntalos-repo.asc Public GPG key (committed)
  setup-syntalos-repo.sh  End-user setup script
_target/            Generated APT repository (git-ignored)
_cache/             Download and reprepro cache (git-ignored)
```

### Building locally

```bash
# Install dependencies
sudo apt install reprepro gnupg python3-yaml python3-requests python3-rich

# Provide the signing key
cp /path/to/your/signing_key.asc config/signing_key.asc

# Build the repository into _target/
python3 build-repo.py

# (Optional) preview directory listings
python3 write-dir-listings.py --root _target/
```

Pass `--help` to either script for all available options.
