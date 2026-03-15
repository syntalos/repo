# Config

Place optional configuration files here to control signing and
per-distro reprepro settings.

## Signing

| File | Purpose |
|---|---|
| `signing_key.asc` | ASCII-armored GPG private key (**required**) |
| `signing_key.gpg` | Binary GPG private key (alternative to `.asc`) |

All repositories are **always signed** - the build fails loudly when no key
file is present.

## Per-distribution configuration

Create a `config/<distro>-config.yaml` file to customize the build for a
specific distribution. All fields are optional.

```yaml
# config/ubuntu-config.yaml

# Architectures to include (default: amd64 arm64)
architectures:
  - amd64
  - arm64

# Lines written verbatim into conf/options (default: none)
reprepro_options:
  - verbose
  # - ask-passphrase

# Full conf/distributions content — overrides the auto-generated one.
# distributions: |
#   Codename: noble
#   Suite: noble
#   Version: 24.04
#   Components: stable
#   Architectures: amd64 arm64
#   SignWith: 0xABCDEF0123456789
```

### Fields

| Field | Type | Default | Purpose |
|---|---|---|---|
| `architectures` | list of strings | `[amd64, arm64]` | Architectures written to the `Architectures:` reprepro field |
| `reprepro_options` | list of strings | `[]` | Lines written verbatim to `conf/options` |
| `distributions` | multiline string | *(auto-generated)* | Overrides the entire `conf/distributions` file |
