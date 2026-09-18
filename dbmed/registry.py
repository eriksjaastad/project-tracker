"""The registry: which projects exist, where their data lives, who may call.

Three properties this file is responsible for.

**A missing entry denies.** Card #7228 is explicit: "A missing registration is a
deployment failure, not permission for raw access." There is no default entry,
no path guessing, and no "create it if absent".

**Only root can write an entry.** The registry lives in a root-owned directory
and every file is checked for root ownership and non-group-writability before
it is parsed. An agent that could add a registry entry could point a project at
a database of its choosing, which would make the whole boundary decorative.

**The daemon refuses to run from code an agent can edit.** `verify_tree` walks
the installed backend and fails startup if anything in it is writable by
someone other than root. Card #7228 again: "A development checkout is not
automatically trusted executable code."
"""

from __future__ import annotations

import grp
import os
import pwd
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import NotRegistered

DEFAULT_CONFIG_DIR = Path("/usr/local/etc/dbmed")
DEFAULT_INSTALL_DIR = Path("/usr/local/libexec/dbmed")
DEFAULT_DATA_ROOT = Path("/usr/local/var/dbmed")
DEFAULT_SOCKET = Path("/usr/local/var/run/dbmed.sock")


class IntegrityError(RuntimeError):
    """The installation is not trustworthy. Always fatal at startup."""


@dataclass(frozen=True)
class RegistryEntry:
    project: str
    db_path: Path
    backup_dir: Path
    external_backup_dir: Path
    ops_module: str
    allowed_uids: frozenset[int]
    hosts: frozenset[str]
    fixture_root: Path | None = None
    test_support: bool = False
    """Whether this entry may accept the test-support operations.

    Off unless a registry file says otherwise, and `install.sh` never writes
    it — only the test suite's generated registry does. The reason this is
    safe to have at all is the same reason everything else here is: the
    registry directory is root-owned, the daemon refuses to parse it if it is
    not, and an agent cannot add a flag to a file it cannot write.
    """

    def permits(self, uid: int) -> bool:
        return uid in self.allowed_uids


def verify_tree(root: Path, *, label: str) -> None:
    """Fail unless every path under `root` is root-owned and not group/other writable.

    Walks symlinks' targets are *not* followed; a symlink inside the install
    tree is itself a finding, because it is a way to point trusted code at
    untrusted content.
    """
    if not root.exists():
        raise IntegrityError(f"{label}: {root} does not exist")

    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise IntegrityError(
                f"{label}: {path} is a symlink; symlinks inside the trusted tree are "
                "a way to redirect trusted code at editable content"
            )
        if info.st_uid != 0:
            owner = _username(info.st_uid)
            raise IntegrityError(
                f"{label}: {path} is owned by {owner} (uid {info.st_uid}), not root. "
                "Anything writable by an agent cannot be trusted with database privileges."
            )
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise IntegrityError(
                f"{label}: {path} is group- or world-writable (mode {info.st_mode & 0o7777:04o})"
            )


def load_registry(
    config_dir: Path = DEFAULT_CONFIG_DIR, *, verify: bool = True
) -> dict[str, RegistryEntry]:
    """Parse every `registry.d/*.toml`. Raises IntegrityError on an untrusted file.

    `verify=False` exists for the test harness, which cannot create root-owned
    files. The daemon passes it through from its own integrity setting, and
    refuses to accept it while running as root, so an unverified registry can
    never be loaded by the real service.
    """
    registry_dir = config_dir / "registry.d"
    if verify:
        verify_tree(config_dir, label="registry config")

    entries: dict[str, RegistryEntry] = {}
    for path in sorted(registry_dir.glob("*.toml")):
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        entry = _parse_entry(path, raw)
        if entry.project in entries:
            raise IntegrityError(
                f"duplicate registry entry for {entry.project!r} in {path}"
            )
        entries[entry.project] = entry
    return entries


def resolve(registry: dict[str, RegistryEntry], project: str) -> RegistryEntry:
    entry = registry.get(project)
    if entry is None:
        raise NotRegistered(
            f"{project!r} is not registered with dbmed. This is a deployment failure — "
            "register the project through the reviewed install path. It is not "
            "permission to open the database another way."
        )
    return entry


def _parse_entry(path: Path, raw: dict) -> RegistryEntry:
    required = ("project", "db_path", "ops_module")
    missing = [key for key in required if key not in raw]
    if missing:
        raise IntegrityError(f"{path}: missing required keys {missing}")

    db_path = Path(raw["db_path"])
    if not db_path.is_absolute():
        raise IntegrityError(f"{path}: db_path must be absolute, got {db_path}")

    data_root = Path(raw.get("data_root", DEFAULT_DATA_ROOT))
    if not _is_within(db_path, data_root):
        raise IntegrityError(
            f"{path}: db_path {db_path} is outside the protected data root {data_root}. "
            "A registered database living where an agent can reach it defeats the boundary."
        )

    allowed_uids = frozenset(_resolve_uids(path, raw.get("allowed_users", [])))
    if not allowed_uids:
        raise IntegrityError(
            f"{path}: allowed_users is empty, so no caller could ever be served. "
            "State the intended callers explicitly."
        )

    return RegistryEntry(
        project=raw["project"],
        db_path=db_path,
        backup_dir=Path(raw.get("backup_dir", db_path.parent / "backups")),
        external_backup_dir=Path(
            raw.get("external_backup_dir", data_root / "external" / raw["project"])
        ),
        ops_module=raw["ops_module"],
        allowed_uids=allowed_uids,
        hosts=frozenset(raw.get("hosts", [])),
        fixture_root=Path(raw["fixture_root"]) if "fixture_root" in raw else None,
        test_support=bool(raw.get("test_support", False)),
    )


def _resolve_uids(path: Path, names: list) -> list[int]:
    uids: list[int] = []
    for name in names:
        if isinstance(name, int):
            uids.append(name)
            continue
        try:
            uids.append(pwd.getpwnam(name).pw_uid)
        except KeyError as exc:
            raise IntegrityError(f"{path}: allowed_users names unknown user {name!r}") from exc
    return uids


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _username(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return f"uid:{uid}"


def groupname(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return f"gid:{gid}"


def current_host() -> str:
    return os.uname().nodename.split(".")[0]
