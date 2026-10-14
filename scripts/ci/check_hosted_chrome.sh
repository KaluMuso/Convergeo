#!/usr/bin/env bash
set -euo pipefail

chrome_path=/opt/google/chrome/chrome
chrome_version=155.0.8059.79
package_version=155.0.8059.79-1
package_sha256=b7726070ca707965e9a17b38e4f15ba283bf6f65c339626c092862af7b19badc
google_key_fingerprint=EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796
package_filename=pool/main/g/google-chrome-stable/google-chrome-stable_155.0.8059.79-1_amd64.deb
chrome_defaults=/etc/default/google-chrome
chrome_sources_dir=/etc/apt/sources.list.d

supported_image() {
  [[ "${ImageOS-}" == ubuntu24 ]] || return 1
  case "${ImageVersion-}" in
    20260927.320.1 | 20261004.327.1) return 0 ;;
    *) return 1 ;;
  esac
}

check_install_host_policy() {
  grep -qx 'repo_add_once="false"' "$chrome_defaults" || return 1
  if grep -q 'install_device_trust_key_management_command=true' "$chrome_defaults"; then return 1; fi
  if compgen -G "$chrome_sources_dir/google-chrome*" >/dev/null; then return 1; fi
}

# Google signs InRelease, which binds Packages.gz, which binds the exact .deb.
# Verification keeps its keyring temporary and adds no APT source.
download_verified_chrome() (
  set -euo pipefail
  local scratch key_details primary_fingerprint
  scratch=$(mktemp -d) || exit 1
  trap 'rm -rf "$scratch"' EXIT
  mkdir -m 700 "$scratch/gnupg" || exit 1
  export GNUPGHOME="$scratch/gnupg"

  for item in linux_signing_key.pub stable/InRelease stable/main/binary-amd64/Packages.gz; do
    case "$item" in
      linux_signing_key.pub)
        curl -fsSL --retry 2 --max-time 30 "https://dl.google.com/linux/$item" -o "$scratch/google.asc" 2>/dev/null || exit 1 ;;
      stable/InRelease)
        curl -fsSL --retry 2 --max-time 30 "https://dl.google.com/linux/chrome/deb/dists/$item" -o "$scratch/InRelease" 2>/dev/null || exit 1 ;;
      stable/main/binary-amd64/Packages.gz)
        curl -fsSL --retry 2 --max-time 30 "https://dl.google.com/linux/chrome/deb/dists/$item" -o "$scratch/Packages.gz" 2>/dev/null || exit 1 ;;
    esac
  done
  key_details=$(gpg --batch --show-keys --with-colons "$scratch/google.asc" 2>/dev/null) || exit 1
  [[ $(printf '%s\n' "$key_details" | grep -c '^pub:') == 1 ]] || exit 1
  primary_fingerprint=$(printf '%s\n' "$key_details" | awk -F: '$1=="pub" {seen=1; next} seen && $1=="fpr" {print $10; exit}')
  [[ "$primary_fingerprint" == "$google_key_fingerprint" ]] || exit 1
  gpg --batch --dearmor -o "$scratch/google.gpg" "$scratch/google.asc" 2>/dev/null || exit 1
  gpg --batch --no-default-keyring --keyring "$scratch/google.gpg" \
    --verify "$scratch/InRelease" 2>/dev/null || exit 1

  python3 - "$scratch" "$package_sha256" "$package_filename" "$package_version" <<'PY' || exit 1
import gzip
import hashlib
from pathlib import Path
import sys
import zlib

root, expected_sha, expected_name, expected_version = sys.argv[1:]
def require(condition, reason):
    if not condition:
        raise SystemExit("Google Chrome package metadata mismatch: " + reason)

try:
    release = (Path(root) / "InRelease").read_text()
    section = release.split("SHA256:\n", 1)[1].splitlines()
    entries = []
    for line in section:
        if not line.startswith(" "):
            break
        entries.append(line.split())
    matches = [entry for entry in entries if len(entry) == 3 and entry[2] == "main/binary-amd64/Packages.gz"]
    require(len(matches) == 1, "index_record_count")
    compressed = (Path(root) / "Packages.gz").read_bytes()
    require(int(matches[0][1]) == len(compressed), "index_size")
    require(matches[0][0] == hashlib.sha256(compressed).hexdigest(), "index_sha256")
    records = gzip.decompress(compressed).decode().split("\n\n")
    packages = []
    for record in records:
        fields = dict(line.split(": ", 1) for line in record.splitlines() if ": " in line)
        if fields.get("Package") == "google-chrome-stable" and fields.get("Version") == expected_version:
            packages.append(fields)
    require(len(packages) == 1, "package_record_count")
    package = packages[0]
    require(package.get("Architecture") == "amd64", "package_architecture")
    require(package.get("Filename") == expected_name, "package_filename")
    require(package.get("SHA256") == expected_sha, "package_sha256")
    require(int(package.get("Size", "0")) == 143638568, "package_size")
except (OSError, ValueError, IndexError, EOFError, zlib.error):
    raise SystemExit("Google Chrome package metadata mismatch: metadata_format") from None
PY

  curl -fsSL --retry 2 --max-time 180 \
    "https://dl.google.com/linux/chrome/deb/$package_filename" \
    -o "$scratch/google-chrome-stable.deb" 2>/dev/null || exit 1
  printf '%s  %s\n' "$package_sha256" "$scratch/google-chrome-stable.deb" | sha256sum --check --status || exit 1
  [[ $(dpkg-deb -f "$scratch/google-chrome-stable.deb" Package) == google-chrome-stable ]] || exit 1
  [[ $(dpkg-deb -f "$scratch/google-chrome-stable.deb" Version) == "$package_version" ]] || exit 1
  [[ $(dpkg-deb -f "$scratch/google-chrome-stable.deb" Architecture) == amd64 ]] || exit 1

  if [[ "${1-}" == install ]]; then
    # GitHub's runner image disables the package's repo setup. Enforce that
    # state rather than widening the host's future APT trust or update scope.
    # The package can otherwise create a setgid management service and key.
    check_install_host_policy || exit 1
    sudo dpkg --install "$scratch/google-chrome-stable.deb" >/dev/null || exit 1
    check_install_host_policy || exit 1
  fi
  printf 'Google Chrome package signature chain and SHA-256 verified.\n'
)

install_verified_hosted_chrome() {
  if ! supported_image; then
    printf 'Unsupported Ubuntu runner image; Chrome package was not installed.\n' >&2
    return 1
  fi
  download_verified_chrome install || return 1
  check_hosted_chrome
}

check_hosted_chrome() {
  local image_os=unknown image_version=unknown executable=missing
  local owner=unknown product=unknown package=unknown
  local raw_owner= raw_product= raw_package=

  # Print only fixed labels, even when a runner returns unexpected text.
  if [[ "${ImageOS-}" == ubuntu24 ]]; then image_os=ubuntu24; fi
  case "${ImageVersion-}" in
    20260927.320.1 | 20261004.327.1) image_version=$ImageVersion ;;
  esac
  raw_owner=$(dpkg-query -S "$chrome_path" 2>/dev/null) || raw_owner=
  raw_package=$(dpkg-query -W -f='${Version}' google-chrome-stable 2>/dev/null) || raw_package=

  if [[ "$raw_owner" == "google-chrome-stable: $chrome_path" ]]; then owner=google-chrome-stable; fi
  if [[ -x "$chrome_path" ]]; then
    executable=yes
    if [[ "$owner" == google-chrome-stable ]]; then
      raw_product=$("$chrome_path" --product-version 2>/dev/null) || raw_product=
    fi
  fi
  case "$raw_product" in
    154.0.8037.57 | 154.0.8037.97 | 155.0.8059.39 | 155.0.8059.79) product=$raw_product ;;
  esac
  case "$raw_package" in
    154.0.8037.57-1 | 154.0.8037.97-1 | 155.0.8059.39-1 | 155.0.8059.79-1) package=$raw_package ;;
  esac
  printf 'Chrome preflight: ImageOS=%s ImageVersion=%s path=/opt/google/chrome/chrome executable=%s owner=%s product=%s package=%s\n' \
    "$image_os" "$image_version" "$executable" "$owner" "$product" "$package"

  if supported_image && \
        [[ "$image_os" == ubuntu24 && \
        "$executable" == yes && "$owner" == google-chrome-stable && \
        "$product" == "$chrome_version" && "$package" == "$package_version" ]]; then
    return 0
  fi
  printf 'Unsupported hosted Chrome image/package; require verified Google Chrome 155.0.8059.79-1 on an approved Ubuntu 24.04 image. No Lighthouse qualification was run.\n' >&2
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1-}" in
    --install-verified) install_verified_hosted_chrome ;;
    --verify-download) download_verified_chrome verify ;;
    '') check_hosted_chrome ;;
    *) printf 'Unsupported Chrome guard mode.\n' >&2; exit 2 ;;
  esac
fi
