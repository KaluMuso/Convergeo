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

set_fixture ubuntu24 20261004.327.1 154.0.8037.97 154.0.8037.97-1
output=$(check_hosted_chrome 2>&1)
[[ "$output" == *'ImageOS=ubuntu24 ImageVersion=20261004.327.1'* ]]
[[ "$output" == *'owner=google-chrome-stable product=154.0.8037.97 package=154.0.8037.97-1'* ]]

set_fixture ubuntu24 20260927.320.1 154.0.8037.57 154.0.8037.57-1
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=20260927.320.1'* ]]
[[ "$output" == *'No Lighthouse qualification was run.'* ]]

set_fixture ubuntu24 20261004.327.1 154.0.8037.57 154.0.8037.57-1
if check_hosted_chrome >/dev/null 2>&1; then exit 1; fi

set_fixture other-os 20261004.327.1 154.0.8037.97 154.0.8037.97-1
if check_hosted_chrome >/dev/null 2>&1; then exit 1; fi

set_fixture ubuntu24 20261011.333.1 154.0.8037.97 154.0.8037.97-1
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=unknown'* ]]

set_fixture ubuntu24 20261004.327.1 154.0.8037.97 154.0.8037.97-1
unset ImageVersion
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'ImageVersion=unknown'* ]]

set_fixture ubuntu24 20261004.327.1 154.0.8037.97 missing
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" == *'package=unknown'* ]]

set_fixture SECRET_IMAGE_OS SECRET_IMAGE_VERSION SECRET_PRODUCT SECRET_PACKAGE
OWNER_FIXTURE=SECRET_OWNER
export CHROME_FIXTURE_MARKER="$fixture/unowned-browser-ran"
if output=$(check_hosted_chrome 2>&1); then exit 1; fi
[[ "$output" != *SECRET* ]]
[[ "$output" == *'ImageOS=unknown ImageVersion=unknown'* ]]
[[ ! -e "$CHROME_FIXTURE_MARKER" ]]

echo 'Hosted Chrome preflight fixtures passed'
