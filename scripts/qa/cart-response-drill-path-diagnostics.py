"""Read-only failure evidence. Emit path aliases and permissions, never host identities."""

from __future__ import annotations

import errno
import json
import os
import stat
import struct
import sys
from pathlib import Path


def access_bits(path: Path, metadata: os.stat_result, uid: int, gid: int) -> tuple[int | None, str]:
    """Evaluate the dedicated user's sole group, including Linux access ACL masks."""
    mode = stat.S_IMODE(metadata.st_mode)
    try:
        raw = os.getxattr(path, "system.posix_acl_access")
    except OSError as error:
        if error.errno not in (errno.ENODATA, errno.ENOTSUP):
            return None, "unavailable"
        if metadata.st_uid == uid:
            return (mode >> 6) & 7, "owner"
        return ((mode >> 3) & 7, "group") if metadata.st_gid == gid else (mode & 7, "other")
    if len(raw) < 4 or struct.unpack_from("<I", raw)[0] != 2 or (len(raw) - 4) % 8:
        return None, "unavailable"
    entries = list(struct.iter_unpack("<HHI", raw[4:]))
    basic = {tag: bits for tag, bits, _ in entries if tag in (1, 4, 16, 32)}
    if not {1, 4, 32}.issubset(basic):
        return None, "unavailable"
    if metadata.st_uid == uid:
        return basic[1], "acl_owner"
    mask = basic.get(16, 7)
    for tag, bits, identity in entries:
        if tag == 2 and identity == uid:
            return bits & mask, "acl_test_uid"
    groups = [bits for tag, bits, identity in entries if tag == 8 and identity == gid]
    if metadata.st_gid == gid:
        groups.append(basic[4])
    if groups:
        combined = 0
        for bits in groups:
            combined |= bits
        return combined & mask, "acl_test_group"
    return basic[32], "acl_other"


def mount_flags(path: Path, table: str) -> dict[str, bool] | None:
    best: tuple[int, set[str]] | None = None
    for line in table.splitlines():
        parts = line.split()
        if len(parts) < 10 or "-" not in parts:
            continue
        mount = parts[4]
        for escaped, plain in (
            (r"\040", " "),
            (r"\011", "\t"),
            (r"\012", "\n"),
            (r"\134", "\\"),
        ):
            mount = mount.replace(escaped, plain)
        if path == Path(mount) or Path(mount) in path.parents:
            separator = parts.index("-")
            options = set(parts[5].split(","))
            if len(parts) > separator + 3:
                options.update(parts[separator + 3].split(","))
            if best is None or len(mount) > best[0]:
                best = len(mount), options
    if best is None:
        return None
    return {flag: flag in best[1] for flag in ("noexec", "nosuid", "nodev", "ro")}


def collect(workspace: Path, sdk: Path, uid: int, gid: int) -> dict[str, object]:
    invocation = workspace / "services/api/.venv/bin/python"
    try:
        resolved = invocation.resolve(strict=True)
        resolved_in_sdk = resolved.parent == sdk / "bin" and resolved.name.startswith("python")
    except OSError:
        resolved, resolved_in_sdk = invocation, False
    try:
        mounts = Path("/proc/self/mountinfo").read_text()
    except OSError:
        mounts = ""
    paths: list[tuple[str, Path]] = []
    for alias, base, leaf in (
        ("workspace", workspace, invocation),
        ("python_sdk", sdk, resolved),
    ):
        if alias == "python_sdk" and not resolved_in_sdk:
            continue
        for depth, parent in reversed(list(enumerate(base.parents, 1))):
            paths.append((f"{alias}:ancestor_up={depth}", parent))
        paths.append((alias, base))
        relative = leaf.relative_to(base)
        for count in range(1, len(relative.parts) + 1):
            suffix = Path(*relative.parts[:count])
            # Never emit an environment-derived SDK filename.
            label = (
                "bin/python"
                if alias == "python_sdk" and count == len(relative.parts)
                else suffix.as_posix()
            )
            paths.append((f"{alias}/{label}", base / suffix))
    rows = []
    for alias, path in paths:
        row: dict[str, object] = {"path_alias": alias}
        try:
            metadata = path.stat()
            bits, access_class = access_bits(path, metadata, uid, gid)
            directory = stat.S_ISDIR(metadata.st_mode)
            row.update(
                mode=f"{stat.S_IMODE(metadata.st_mode):04o}",
                kind="directory"
                if directory
                else "regular"
                if stat.S_ISREG(metadata.st_mode)
                else "other",
                access_class=access_class,
                test_uid_read=None if bits is None else bool(bits & 4),
                test_uid_search_or_execute=None if bits is None else bool(bits & 1),
                mount_flags=mount_flags(path.resolve(), mounts),
            )
        except OSError as error:
            row["metadata_status"] = (
                "denied"
                if error.errno == errno.EACCES
                else "missing"
                if error.errno == errno.ENOENT
                else "unavailable"
            )
        rows.append(row)
    denied = [row["path_alias"] for row in rows if row.get("test_uid_search_or_execute") is False]
    noexec = [
        row["path_alias"]
        for row in rows
        if row.get("kind") == "regular" and (row.get("mount_flags") or {}).get("noexec")
    ]
    return {
        "version": 1,
        "test_uid": uid,
        "resolved_into_python_sdk": resolved_in_sdk,
        "paths": rows,
        "permission_denial_candidates": denied,
        "noexec_candidates": noexec,
        "limits": (
            "Metadata inference only; no execution, environment values, "
            "host identities or file payloads collected"
        ),
    }


if __name__ == "__main__":
    print(
        json.dumps(
            collect(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])),
            indent=2,
        )
    )
