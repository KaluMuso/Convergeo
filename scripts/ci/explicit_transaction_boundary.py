"""Bound the five immutable outer-transaction migrations without rewriting them.

This parser recognizes only the SQL forms present in the reviewed files. It
fails closed on unfamiliar transaction control, meta commands, or unterminated
quotes/comments. The result identifies a byte offset immediately before the
final top-level COMMIT; it does not authorize a hosted database connection.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
BOUND_FILES = {
    "20260930170000_reconciliation_report_versions.sql": "a94fb1fac2187fda1f1007d88b7b0928a5be387a8fb6a5e68c4d3edec23a074e",
    "20260930170100_vendor_stock_adjustment_authority.sql": "3aec8abb59a58e9fdf64e75657657a52572215cf0acc8398cfd28f30e5f21437",
    "20261001120000_merchant_protected_listing_admission.sql": "301466ad39d1bb0655943bf86fc7ef8366660d35c0a1455b537719114ef66d46",
    "20261001120100_stock_claim_replay_authority.sql": "b5e415a00ee2f41030c634e926b1611575433c8bb6aa59493835386fcf0743a0",
    "20261001120200_stock_claim_parent_lock_compatibility.sql": "97b6b3e67549b973c5ca5dff4247b2585f24bce96418324c0cc1f17c299636a7",
}
_DOLLAR_TAG = re.compile(rb"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$")
_INNER_CONTROL = re.compile(
    rb"(?i)(?:BEGIN|START\s+TRANSACTION|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE|PREPARE\s+TRANSACTION|SET\s+TRANSACTION)\b"
)
_SUPPORTED = frozenset(
    {
        b"ALTER",
        b"COMMENT",
        b"CREATE",
        b"DELETE",
        b"DO",
        b"DROP",
        b"GRANT",
        b"INSERT",
        b"NOTIFY",
        b"REVOKE",
        b"SELECT",
        b"SET",
        b"UPDATE",
    }
)


class BoundaryError(ValueError):
    """The reviewed source or its supported SQL boundary no longer matches."""


@dataclass(frozen=True)
class Boundary:
    filename: str
    version: str
    name: str
    source_sha256: str
    raw: bytes
    statements: tuple[str, ...]
    commit_offset: int

    def disposable_history_insert(self) -> str:
        """Build the CLI-shaped three-column insert for the fixture ledger."""
        if not re.fullmatch(r"[0-9]+", self.version) or not re.fullmatch(
            r"[a-z0-9_]+", self.name
        ):
            raise BoundaryError("unexpected migration version or name")
        statements = ",".join(
            "convert_from(decode('" + statement.encode().hex() + "','hex'),'UTF8')"
            for statement in self.statements
        )
        return (
            "INSERT INTO supabase_migrations.schema_migrations"
            "(version,name,statements) VALUES ("
            f"'{self.version}','{self.name}',ARRAY[{statements}]::text[]);"
        )

    def with_disposable_history_before_commit(self) -> bytes:
        """Interleave the fixture row, retaining every original source byte."""
        encoded = self.disposable_history_insert().encode("utf-8")
        parsed = _split(encoded)
        if len(parsed) != 1 or not re.match(
            rb"(?is)^INSERT\s+INTO\s+supabase_migrations\.schema_migrations\b",
            encoded[parsed[0][1] : parsed[0][2]],
        ):
            raise BoundaryError("only one migration-history INSERT is supported")
        return (
            self.raw[: self.commit_offset]
            + b"\n"
            + encoded
            + b"\n"
            + self.raw[self.commit_offset :]
        )

    def disposable_history_row(
        self,
    ) -> tuple[str, str, tuple[str, ...], None, None, None]:
        """Expected six-column row, including the CLI insert's default NULLs."""
        return (
            self.version,
            self.name,
            self.statements,
            None,
            None,
            None,
        )


def verify_disposable_prefix(rows: Sequence[Sequence[object]]) -> int:
    """Return the next bound file index only for an exact fixture ledger prefix.

    The caller must supply rows selected from the five-version window and
    ordered by version. A missing row alone cannot prove no SQL was applied;
    the disposable catalog baseline must be checked separately before replay.
    """
    files = tuple(BOUND_FILES)
    if len(rows) > len(files):
        raise BoundaryError("fixture ledger contains more rows than the bound window")
    for index, row in enumerate(rows):
        expected = parse_bound_file(files[index]).disposable_history_row()
        if len(row) != len(expected):
            raise BoundaryError("fixture ledger is not an exact bound prefix")
        normalized = (
            *row[:2],
            tuple(row[2]) if isinstance(row[2], (tuple, list)) else row[2],
            *row[3:],
        )
        if normalized != expected:
            raise BoundaryError("fixture ledger is not an exact bound prefix")
    return len(rows)


def _split(raw: bytes) -> list[tuple[int, int, int]]:
    """Return (token start, first SQL byte, end) for top-level statements."""
    if b"\x00" in raw or b"\r" in raw:
        raise BoundaryError("NUL or CR is outside the supported SQL form")
    raw.decode("utf-8")
    spans: list[tuple[int, int, int]] = []
    token_start = 0
    first_code: int | None = None
    i = 0
    while i < len(raw):
        pair = raw[i : i + 2]
        if raw[i] in b" \t\n\f":
            i += 1
            continue
        if pair == b"--":
            end = raw.find(b"\n", i + 2)
            i = len(raw) if end < 0 else end
            continue
        if pair == b"/*":
            depth = 1
            i += 2
            while depth:
                if i >= len(raw):
                    raise BoundaryError("unterminated block comment")
                pair = raw[i : i + 2]
                if pair == b"/*":
                    depth += 1
                    i += 2
                elif pair == b"*/":
                    depth -= 1
                    i += 2
                else:
                    i += 1
            continue
        if first_code is None:
            first_code = i
        if raw[i] in (ord("'"), ord('"')):
            quote = raw[i]
            i += 1
            while True:
                if i >= len(raw):
                    raise BoundaryError("unterminated quoted value")
                if raw[i] == ord("\\"):
                    raise BoundaryError(
                        "backslash escapes are outside the supported SQL form"
                    )
                if raw[i] == quote:
                    if raw[i + 1 : i + 2] == bytes((quote,)):
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if raw[i] == ord("$"):
            match = _DOLLAR_TAG.match(raw, i)
            if not match:
                raise BoundaryError("unrecognized dollar token")
            tag = match.group()
            end = raw.find(tag, match.end())
            if end < 0:
                raise BoundaryError("unterminated dollar quote")
            i = end + len(tag)
            continue
        if raw[i] == ord("\\"):
            raise BoundaryError("psql meta commands are unsupported")
        if raw[i] == ord(";"):
            spans.append((token_start, first_code, i + 1))
            token_start = i + 1
            first_code = None
        i += 1
    if first_code is not None:
        raise BoundaryError("unterminated final statement")
    if not spans:
        raise BoundaryError("no SQL statements")
    return spans


def parse_bound_file(filename: str, *, migrations: Path | None = None) -> Boundary:
    expected = BOUND_FILES.get(filename)
    if expected is None or Path(filename).name != filename:
        raise BoundaryError("migration is outside the five reviewed files")
    directory = migrations or ROOT / "supabase/migrations"
    raw = (directory / filename).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise BoundaryError("immutable migration byte hash changed")
    spans = _split(raw)
    statements = tuple(
        raw[start:end].decode("utf-8").rstrip(";").strip() for start, _, end in spans
    )
    first = raw[spans[0][1] : spans[0][2]].strip().upper()
    last = raw[spans[-1][1] : spans[-1][2]].strip().upper()
    if first != b"BEGIN;" or last != b"COMMIT;":
        raise BoundaryError("exact outer BEGIN/COMMIT boundary is required")
    for _, code, end in spans[1:-1]:
        statement = raw[code:end]
        if _INNER_CONTROL.match(statement):
            raise BoundaryError("nested top-level transaction control is unsupported")
        keyword = re.match(rb"[A-Za-z]+", statement)
        if keyword is None or keyword.group().upper() not in _SUPPORTED:
            raise BoundaryError("unsupported top-level SQL statement")
        if re.search(
            rb"(?i)\b(?:CONCURRENTLY|BEGIN\s+ATOMIC|FROM\s+STDIN)\b", statement
        ):
            raise BoundaryError("non-atomic SQL form is unsupported")
    version, name = filename.removesuffix(".sql").split("_", 1)
    return Boundary(filename, version, name, expected, raw, statements, spans[-1][1])
