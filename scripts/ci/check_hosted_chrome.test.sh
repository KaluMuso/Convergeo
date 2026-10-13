#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/check_hosted_chrome.sh"

fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
chrome_path="$fixture/chrome"
cat > "$chrome_path" <<'SH'
#!/usr/bin/env bash
test "${1:-}" = --product-version
if [[ -n "${CHROME_FIXTURE_MARKER:-}" ]]; then : > "$CHROME_FIXTURE_MARKER"; fi
printf '%s\n' "$CHROME_FIXTURE_VERSION"
SH
chmod +x "$chrome_path"

dpkg-query() {
  case "$1" in
    -S)
      [[ "$OWNER_FIXTURE" != missing ]] || return 1
      printf '%s\n' "$OWNER_FIXTURE"
      ;;
    -W)
      [[ "$PACKAGE_FIXTURE_VERSION" != missing ]] || return 1
      printf '%s' "$PACKAGE_FIXTURE_VERSION"
      ;;
    *) return 1 ;;
  esac
}

set_fixture() {
  ImageOS=$1 ImageVersion=$2 CHROME_FIXTURE_VERSION=$3 PACKAGE_FIXTURE_VERSION=$4
  OWNER_FIXTURE="google-chrome-stable: $chrome_path"
  export CHROME_FIXTURE_VERSION
}

set_fixture ubuntu24 20261004.327.1 155.0.8059.79 155.0.8059.79-1
output=$(check_hosted_chrome 2>&1)
[[ "$output" == *'ImageOS=ubuntu24 ImageVersion=20261004.327.1'* ]]
[[ "$output" == *'owner=google-chrome-stable product=155.0.8059.79 package=155.0.8059.79-1'* ]]

set_fixture ubuntu24 20260927.320.1 155.0.8059.79 155.0.8059.79-1
check_hosted_chrome >/dev/null

set_fixture ubuntu24 20260927.320.1 154.0.8037.57 154.0.8037.57-1
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=20260927.320.1'* ]]
[[ "$output" == *'No Lighthouse qualification was run.'* ]]

set_fixture ubuntu24 20261004.327.1 154.0.8037.97 154.0.8037.97-1
if check_hosted_chrome >/dev/null 2>&1; then exit 1; fi

for versions in \
  '155.0.8059.39 155.0.8059.39-1' \
  '155.0.8059.79 155.0.8059.39-1' \
  '155.0.8059.39 155.0.8059.79-1'; do
  read -r product package <<< "$versions"
  set_fixture ubuntu24 20261004.327.1 "$product" "$package"
  if check_hosted_chrome >/dev/null 2>&1; then exit 1; fi
done

set_fixture other-os 20261004.327.1 155.0.8059.79 155.0.8059.79-1
if check_hosted_chrome >/dev/null 2>&1; then exit 1; fi

set_fixture ubuntu24 20261011.333.1 155.0.8059.79 155.0.8059.79-1
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=unknown'* ]]

set_fixture ubuntu24 20261004.327.1 155.0.8059.79 155.0.8059.79-1
unset ImageVersion
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=unknown'* ]]

set_fixture ubuntu24 20261004.327.1 155.0.8059.79 missing
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'package=unknown'* ]]

# Unknown hosts cannot start a download or a privileged package install.
download_verified_chrome() { : > "$fixture/unexpected-install"; }
set_fixture ubuntu24 20261011.333.1 155.0.8059.79 155.0.8059.79-1
if install_verified_hosted_chrome >/dev/null 2>&1; then exit 1; fi
[[ ! -e "$fixture/unexpected-install" ]]

# Even a matching preexisting browser cannot mask a failed verification.
download_verified_chrome() { return 1; }
set_fixture ubuntu24 20261004.327.1 155.0.8059.79 155.0.8059.79-1
if install_verified_hosted_chrome >/dev/null 2>&1; then exit 1; fi

chrome_defaults="$fixture/google-chrome-defaults"
chrome_sources_dir="$fixture/sources"
mkdir "$chrome_sources_dir"
printf 'repo_add_once="false"\n' > "$chrome_defaults"
check_install_host_policy
printf 'install_device_trust_key_management_command=true\n' >> "$chrome_defaults"
if check_install_host_policy; then exit 1; fi
printf 'repo_add_once="false"\n' > "$chrome_defaults"
touch "$chrome_sources_dir/google-chrome.sources"
if check_install_host_policy; then exit 1; fi
rm "$chrome_sources_dir/google-chrome.sources"
printf 'repo_add_once="true"\n' > "$chrome_defaults"
if check_install_host_policy; then exit 1; fi

set_fixture SECRET_IMAGE_OS SECRET_IMAGE_VERSION SECRET_PRODUCT SECRET_PACKAGE
OWNER_FIXTURE=SECRET_OWNER
export CHROME_FIXTURE_MARKER="$fixture/unowned-browser-ran"
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" != *SECRET* ]]
[[ "$output" == *'ImageOS=unknown ImageVersion=unknown'* ]]
[[ ! -e "$CHROME_FIXTURE_MARKER" ]]

python3 - "$(dirname "$0")/check_hosted_chrome.sh" "$package_sha256" "$package_filename" "$package_version" "$fixture" <<'PY'
import gzip
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

source, expected_sha, expected_name, expected_version, fixture = sys.argv[1:]
shell = Path(source).read_text()
code = shell.split("<<'PY' || exit 1\n", 1)[1].split("\nPY", 1)[0]
cases = {
    "valid": None,
    "index_missing": "index_record_count",
    "index_duplicate": "index_record_count",
    "index_size": "index_size",
    "index_sha256": "index_sha256",
    "package_missing": "package_record_count",
    "retired_pin": "package_record_count",
    "package_duplicate": "package_record_count",
    "package_architecture": "package_architecture",
    "package_filename": "package_filename",
    "package_sha256": "package_sha256",
    "package_size": "package_size",
    "missing_size": "package_size",
    "malformed_size": "metadata_format",
    "malformed_index_size": "metadata_format",
    "malformed_gzip": "metadata_format",
    "malformed_deflate": "metadata_format",
    "malformed_encoding": "metadata_format",
    "malformed_release": "metadata_format",
}
with tempfile.TemporaryDirectory(dir=fixture, prefix="metadata-") as temp:
    root = Path(temp)
    for fault, reason in cases.items():
        fields = {
            "Package": "google-chrome-stable",
            "Version": expected_version,
            "Architecture": "amd64",
            "Filename": expected_name,
            "SHA256": expected_sha,
            "Size": "143638568",
        }
        if fault == "retired_pin":
            fields["Version"] = "155.0.8059.39-1"
        changes = {
            "package_architecture": ("Architecture", "arm64"),
            "package_filename": ("Filename", "SECRET_METADATA"),
            "package_sha256": ("SHA256", "0" * 64),
            "package_size": ("Size", "143638569"),
            "malformed_size": ("Size", "SECRET_METADATA"),
        }
        if fault in changes:
            key, value = changes[fault]
            fields[key] = value
        if fault == "missing_size":
            del fields["Size"]
        record = "\n".join(f"{key}: {value}" for key, value in fields.items()) + "\n\n"
        payload = record.encode()
        if fault == "package_missing":
            payload = b""
        if fault == "package_duplicate":
            payload *= 2
        if fault == "malformed_encoding":
            payload = b"\xffSECRET_METADATA"
        compressed = gzip.compress(payload)
        if fault == "malformed_gzip":
            compressed = b"SECRET_METADATA"
        if fault == "malformed_deflate":
            compressed = compressed[:10] + b"\x07" + compressed[11:]
        size = str(len(compressed))
        digest = hashlib.sha256(compressed).hexdigest()
        if fault == "index_size":
            size = str(len(compressed) + 1)
        if fault == "malformed_index_size":
            size = "SECRET_METADATA"
        if fault == "index_sha256":
            digest = "0" * 64
        entry = f" {digest} {size} main/binary-amd64/Packages.gz\n"
        if fault == "index_missing":
            entry = ""
        if fault == "index_duplicate":
            entry *= 2
        release = "SHA256:\n" + entry
        if fault == "malformed_release":
            release = "SECRET_METADATA"
        (root / "InRelease").write_text(release)
        (root / "Packages.gz").write_bytes(compressed)
        result = subprocess.run(
            [sys.executable, "-c", code, str(root), expected_sha, expected_name, expected_version],
            capture_output=True, text=True, timeout=10,
        )
        assert result.stdout == "", fault
        assert result.returncode == (0 if reason is None else 1), fault
        expected = "" if reason is None else f"Google Chrome package metadata mismatch: {reason}\n"
        assert result.stderr == expected, fault
        assert "SECRET_METADATA" not in result.stdout + result.stderr, fault
print(f"Chrome metadata verifier fixtures passed: {len(cases)} cases")
PY

echo 'Hosted Chrome preflight fixtures passed'
