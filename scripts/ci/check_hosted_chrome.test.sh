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

set_fixture ubuntu24 20261004.327.1 155.0.8059.39 155.0.8059.39-1
output=$(check_hosted_chrome 2>&1)
[[ "$output" == *'ImageOS=ubuntu24 ImageVersion=20261004.327.1'* ]]
[[ "$output" == *'owner=google-chrome-stable product=155.0.8059.39 package=155.0.8059.39-1'* ]]

set_fixture ubuntu24 20260927.320.1 155.0.8059.39 155.0.8059.39-1
check_hosted_chrome >/dev/null

set_fixture ubuntu24 20260927.320.1 154.0.8037.57 154.0.8037.57-1
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=20260927.320.1'* ]]
[[ "$output" == *'No Lighthouse qualification was run.'* ]]

set_fixture ubuntu24 20261004.327.1 154.0.8037.97 154.0.8037.97-1
if check_hosted_chrome >/dev/null 2>&1; then exit 1; fi

set_fixture other-os 20261004.327.1 155.0.8059.39 155.0.8059.39-1
if check_hosted_chrome >/dev/null 2>&1; then exit 1; fi

set_fixture ubuntu24 20261011.333.1 155.0.8059.39 155.0.8059.39-1
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=unknown'* ]]

set_fixture ubuntu24 20261004.327.1 155.0.8059.39 155.0.8059.39-1
unset ImageVersion
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=unknown'* ]]

set_fixture ubuntu24 20261004.327.1 155.0.8059.39 missing
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'package=unknown'* ]]

# Unknown hosts cannot start a download or a privileged package install.
download_verified_chrome() { : > "$fixture/unexpected-install"; }
set_fixture ubuntu24 20261011.333.1 155.0.8059.39 155.0.8059.39-1
if install_verified_hosted_chrome >/dev/null 2>&1; then exit 1; fi
[[ ! -e "$fixture/unexpected-install" ]]

# Even a matching preexisting browser cannot mask a failed verification.
download_verified_chrome() { return 1; }
set_fixture ubuntu24 20261004.327.1 155.0.8059.39 155.0.8059.39-1
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

echo 'Hosted Chrome preflight fixtures passed'
