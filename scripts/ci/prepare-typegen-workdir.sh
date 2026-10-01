#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${REPO_ROOT_OVERRIDE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TYPEGEN_WORKDIR="${1:?usage: prepare-typegen-workdir.sh WORKDIR}"
SOURCE_SUPABASE_DIR="${ROOT_DIR}/supabase"
SOURCE_CONFIG="${SOURCE_SUPABASE_DIR}/config.toml"
TYPEGEN_POSTGRES_MAJOR="${TYPEGEN_POSTGRES_MAJOR:-17}"
TYPEGEN_POSTGRES_IMAGE_VERSION="${TYPEGEN_POSTGRES_IMAGE_VERSION:-17.6.1.143}"
TYPEGEN_POSTGRES_META_VERSION="${TYPEGEN_POSTGRES_META_VERSION:-v0.96.6}"

[[ -f "${SOURCE_CONFIG}" ]] || { echo "error: missing ${SOURCE_CONFIG}" >&2; exit 1; }
mkdir -p "${TYPEGEN_WORKDIR}"
if find "${TYPEGEN_WORKDIR}" -mindepth 1 -print -quit | grep -q .; then
  echo "error: disposable typegen workdir must be empty: ${TYPEGEN_WORKDIR}" >&2
  exit 1
fi

# Copy only committed Supabase inputs. This avoids inheriting another local stack's
# .temp selection, linked-project metadata, or generated database state.
git -C "${ROOT_DIR}" archive --format=tar HEAD supabase | tar -xf - -C "${TYPEGEN_WORKDIR}"

TYPEGEN_CONFIG="${TYPEGEN_WORKDIR}/supabase/config.toml"
python3 - "${TYPEGEN_CONFIG}" "${TYPEGEN_POSTGRES_MAJOR}" <<'PY'
from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tomllib

path = Path(sys.argv[1])
major = int(sys.argv[2])
text = path.read_text(encoding="utf-8")

text, project_count = re.subn(
    r'(?m)^project_id\s*=\s*"[^"]+"\s*$',
    'project_id = "vergeo5-typegen"',
    text,
)
text, major_count = re.subn(
    r"(?m)^major_version\s*=\s*15\s*$",
    f"major_version = {major}",
    text,
)
if project_count != 1 or major_count != 1:
    raise SystemExit(
        "error: expected exactly one project_id and one major_version=15 in copied config"
    )

tmp = path.with_suffix(".toml.tmp")
tmp.write_text(text, encoding="utf-8")
os.replace(tmp, path)

with path.open("rb") as handle:
    config = tomllib.load(handle)
if config["project_id"] != "vergeo5-typegen":
    raise SystemExit("error: disposable project_id was not applied")
if config["db"]["major_version"] != major:
    raise SystemExit("error: disposable PostgreSQL major override was not applied")
if config["db"]["seed"]["enabled"] is not False:
    raise SystemExit("error: disposable typegen database must keep demo seeding disabled")
if config["api"]["schemas"] != ["public", "graphql_public"]:
    raise SystemExit("error: typegen schema contract must remain public,graphql_public")
PY

mkdir -p "${TYPEGEN_WORKDIR}/supabase/.temp"
printf '%s\n' "${TYPEGEN_POSTGRES_IMAGE_VERSION}" \
  >"${TYPEGEN_WORKDIR}/supabase/.temp/postgres-version"
printf '%s\n' "${TYPEGEN_POSTGRES_META_VERSION}" \
  >"${TYPEGEN_WORKDIR}/supabase/.temp/pgmeta-version"

printf 'typegen_workdir=%s\n' "${TYPEGEN_WORKDIR}"
printf 'checked_in_postgres_major=15\n'
printf 'disposable_postgres_major=%s\n' "${TYPEGEN_POSTGRES_MAJOR}"
printf 'postgres_image=supabase/postgres:%s\n' "${TYPEGEN_POSTGRES_IMAGE_VERSION}"
printf 'postgres_meta_version=%s\n' "${TYPEGEN_POSTGRES_META_VERSION}"
printf 'generation_schemas=public,graphql_public\n'
