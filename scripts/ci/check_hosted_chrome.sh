#!/usr/bin/env bash
set -euo pipefail

chrome_path=/opt/google/chrome/chrome

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
    154.0.8037.57 | 154.0.8037.97) product=$raw_product ;;
  esac
  case "$raw_package" in
    154.0.8037.57-1 | 154.0.8037.97-1) package=$raw_package ;;
  esac
  printf 'Chrome preflight: ImageOS=%s ImageVersion=%s path=/opt/google/chrome/chrome executable=%s owner=%s product=%s package=%s\n' \
    "$image_os" "$image_version" "$executable" "$owner" "$product" "$package"

  if [[ "$image_os" == ubuntu24 && "$image_version" == 20261004.327.1 && \
        "$executable" == yes && "$owner" == google-chrome-stable && \
        "$product" == 154.0.8037.97 && "$package" == 154.0.8037.97-1 ]]; then
    return 0
  fi
  printf 'Unsupported hosted Chrome image/package; require ubuntu24/20261004.327.1 with Google Chrome 154.0.8037.97-1. No Lighthouse qualification was run.\n' >&2
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  check_hosted_chrome
fi
