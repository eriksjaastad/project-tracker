"""dbmedd — the privileged side.

Runs as the `_dbmed` service account under a root-owned LaunchDaemon. It is the
only process on the machine with permission to open a protected database file.

Startup order matters and is not negotiable:

1. Verify the installed code tree and config tree are root-owned and not
   writable by anyone else. If an agent could edit the daemon's own code, the
   daemon is not a boundary — it is a confused deputy with database privileges.
2. Load the registry. A project without an entry is denied for the process
   lifetime; entries are never synthesised.
3. Import each project's operations module from the verified install tree only.
4. Bind the socket, then serve.

Any failure in 1–3 is fatal. A daemon that starts in a degraded state is worse
than one that does not start, because callers would read its answers as
authoritative.
"""

from __future__ import annotations

import argparse
import importlib
import os
import secrets
import signal
import socketserver
import stat
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import opspec, protocol
from .audit import AuditLog
from .errors import (
    BackupRequired,
    DbmedError,
    InvalidParams,
    NotAuthorized,
    OperationFailed,
    UnknownOperation,
)
from .opspec import Kind, OpSpec
from .peercred import PeerCredentialError, peer_uid
from .registry import (
    DEFAULT_CONFIG_DIR,
    DEFAULT_DATA_ROOT,
    DEFAULT_INSTALL_DIR,
    DEFAULT_SOCKET,
    IntegrityError,
    RegistryEntry,
    current_host,
    load_registry,
    resolve,
    verify_tree,
)

SOCKET_MODE = 0o660
TOKEN_TTL_SECONDS = 120.0


@dataclass
class LoadedProject:
    entry: RegistryEntry
    backend: Any
    ops: dict[str, OpSpec]
    lock: threading.RLock


@dataclass
class Grant:
    """A single-use authorization for one destructive operation."""

    token: str
    uid: int
    project: str
    op: str
    backup_path: str
    issued_at: float

    def matches(self, uid: int, project: str, op: str) -> bool:
        return self.uid == uid and self.project == project and self.op == op

    def expired(self, now: float) -> bool:
        return now - self.issued_at > TOKEN_TTL_SECONDS


class Service:
    """Registry, loaded backends, token store, and dispatch."""

    def __init__(
        self,
        *,
        config_dir: Path = DEFAULT_CONFIG_DIR,
        install_dir: Path = DEFAULT_INSTALL_DIR,
        data_root: Path = DEFAULT_DATA_ROOT,
        verify_integrity: bool = True,
    ) -> None:
        self.config_dir = config_dir
        self.install_dir = install_dir
        self.data_root = data_root

        if verify_integrity:
            verify_tree(install_dir, label="installed backend")
            verify_tree(config_dir, label="registry config")
        elif os.geteuid() == 0:
            raise IntegrityError(
                "refusing to skip integrity verification while running as root"
            )

        if str(install_dir) not in sys.path:
            sys.path.insert(0, str(install_dir))

        self.audit = AuditLog(data_root / "audit" / "dbmed.jsonl")
        self.registry = load_registry(config_dir, verify=verify_integrity)
        self.projects: dict[str, LoadedProject] = {}
        self._grants: dict[str, Grant] = {}
        self._grant_lock = threading.Lock()
        self.host = current_host()

        for entry in self.registry.values():
            self.projects[entry.project] = self._load_project(entry)

    def _load_project(self, entry: RegistryEntry) -> LoadedProject:
        module = importlib.import_module(entry.ops_module)
        if not hasattr(module, "build"):
            raise IntegrityError(
                f"{entry.ops_module!r} has no build(entry) function; it cannot be an "
                "operations module"
            )
        backend, allowlist = module.build(entry)
        ops = opspec.build_operations(backend, allowlist)
        return LoadedProject(entry=entry, backend=backend, ops=ops, lock=threading.RLock())

    # -- dispatch ---------------------------------------------------------

    def handle(self, uid: int, frame: dict[str, Any]) -> Any:
        project_name = frame["project"]
        op_name = frame["op"]
        params = frame["params"]
        token = frame.get("token")

        entry = resolve(self.registry, project_name)
        if not entry.permits(uid):
            raise NotAuthorized(f"uid {uid} is not an allowed caller for {project_name!r}")
        if entry.hosts and self.host not in entry.hosts:
            raise NotAuthorized(
                f"{project_name!r} is not registered for host {self.host!r}; "
                f"registered hosts: {sorted(entry.hosts)}"
            )

        loaded = self.projects[project_name]

        if op_name.startswith("dbmed."):
            return self._builtin(uid, loaded, op_name, params)

        spec = opspec.resolve(loaded.ops, op_name)
        checked = spec.validate(params)

        if spec.kind is Kind.DESTRUCTIVE:
            self._consume_grant(uid, project_name, op_name, token)

        with loaded.lock:
            try:
                return spec.method(**checked)
            except DbmedError:
                raise
            except Exception as exc:
                raise OperationFailed(
                    f"{op_name} failed: {type(exc).__name__}: {exc}",
                    exc_type=type(exc).__name__,
                ) from exc

    def _builtin(
        self, uid: int, loaded: LoadedProject, op_name: str, params: dict[str, Any]
    ) -> Any:
        if op_name == "dbmed.ping":
            return {"ok": True, "host": self.host, "project": loaded.entry.project}

        if op_name == "dbmed.ops":
            return {
                name: {
                    "kind": spec.kind.value,
                    "order": spec.order,
                    "extra": sorted(spec.accepts_extra),
                }
                for name, spec in sorted(loaded.ops.items())
            }

        if op_name == "dbmed.authorize":
            return self._authorize(uid, loaded, params)

        if op_name in ("dbmed.fixture.create", "dbmed.fixture.destroy"):
            return self._fixture(loaded, params, create=op_name.endswith("create"))

        if op_name == "dbmed.seed":
            return self._seed(loaded, params)

        if op_name == "dbmed.count":
            return self._count(loaded, params)

        raise UnknownOperation(f"{op_name!r} is not a dbmed built-in operation")

    def _authorize(self, uid: int, loaded: LoadedProject, params: dict[str, Any]) -> dict:
        target = params.get("op")
        reason = params.get("reason")
        if not isinstance(target, str) or not target:
            raise InvalidParams("dbmed.authorize requires 'op'")
        if not isinstance(reason, str) or len(reason.strip()) < 8:
            raise InvalidParams(
                "dbmed.authorize requires a 'reason' of at least 8 characters — the "
                "audit record is the point"
            )

        spec = opspec.resolve(loaded.ops, target)
        if spec.kind is not Kind.DESTRUCTIVE:
            raise InvalidParams(
                f"{target!r} is a {spec.kind.value} operation and needs no authorization"
            )

        backup = getattr(loaded.backend, "dbmed_backup", None)
        verify = getattr(loaded.backend, "dbmed_verify_backup", None)
        if backup is None or verify is None:
            raise BackupRequired(
                f"{loaded.entry.project!r} does not expose dbmed_backup and "
                "dbmed_verify_backup; a destructive operation cannot be authorized "
                "without a backup that can be checked"
            )

        with loaded.lock:
            path = Path(backup(label=f"pre_{target.replace('.', '_')}"))
            if not verify(str(path)):
                raise BackupRequired(
                    f"the backup at {path} did not verify; refusing to authorize {target!r}"
                )

        grant = Grant(
            token=secrets.token_urlsafe(32),
            uid=uid,
            project=loaded.entry.project,
            op=target,
            backup_path=str(path),
            issued_at=time.monotonic(),
        )
        with self._grant_lock:
            self._prune_grants()
            self._grants[grant.token] = grant

        self.audit.record(
            event="authorize",
            uid=uid,
            project=loaded.entry.project,
            op=target,
            kind=Kind.DESTRUCTIVE.value,
            ok=True,
            duration_ms=0.0,
            detail=f"backup={path}; reason={reason.strip()[:200]}",
        )
        return {"token": grant.token, "backup_path": str(path), "expires_in": TOKEN_TTL_SECONDS}

    def _consume_grant(self, uid: int, project: str, op: str, token: str | None) -> Grant:
        if not token:
            raise NotAuthorized(
                f"{op!r} is destructive and refuses by default. Call dbmed.authorize "
                "first; it takes a verified timestamped backup and issues a single-use "
                "token."
            )
        now = time.monotonic()
        with self._grant_lock:
            self._prune_grants(now)
            grant = self._grants.pop(token, None)
        if grant is None:
            raise NotAuthorized("the authorization token is unknown, already used, or expired")
        if not grant.matches(uid, project, op):
            raise NotAuthorized(
                "the authorization token was issued for a different caller or operation"
            )
        return grant

    def _prune_grants(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for token in [t for t, g in self._grants.items() if g.expired(now)]:
            del self._grants[token]

    def _seed(self, loaded: LoadedProject, params: dict[str, Any]) -> Any:
        """Set columns a normal operation deliberately cannot set.

        Tests need to control timestamps — to prove that retention archives
        the *oldest* Done cards, you must be able to make some cards older.
        No product operation backdates a task, and none should: a completion
        time you can rewrite is not evidence of anything.

        So it lives here instead, behind a registry flag that the installer
        never writes. A production daemon has no entry with `allow_seeding`,
        so this refuses there, and an agent cannot add one because it cannot
        write the root-owned registry.
        """
        if not loaded.entry.test_support:
            raise NotAuthorized(
                f"{loaded.entry.project!r} does not allow seeding. This operation "
                "exists for test fixtures and is refused on any registry entry that "
                "does not explicitly enable it."
            )
        handler = getattr(loaded.backend, "dbmed_seed", None)
        if handler is None:
            raise UnknownOperation(
                f"{loaded.entry.project!r} does not implement dbmed_seed"
            )
        with loaded.lock:
            return handler(**params)

    def _count(self, loaded: LoadedProject, params: dict[str, Any]) -> Any:
        """Row count for one allowlisted table. Test support only.

        The regression these guard is #6870, where a retention sweep deleted
        1,288 Done cards and cascaded into `task_history`, erasing its own
        evidence. Proving "this deleted nothing" means counting rows,
        including in tables no product read operation exposes.

        Gated exactly like `dbmed.seed`, and read-only besides.
        """
        if not loaded.entry.test_support:
            raise NotAuthorized(
                f"{loaded.entry.project!r} does not enable test-support operations"
            )
        handler = getattr(loaded.backend, "dbmed_count_rows", None)
        if handler is None:
            raise UnknownOperation(
                f"{loaded.entry.project!r} does not implement dbmed_count_rows"
            )
        with loaded.lock:
            return handler(**params)

    def _fixture(self, loaded: LoadedProject, params: dict[str, Any], *, create: bool) -> Any:
        """Provision or drop a synthetic database behind the same boundary.

        Probes need something to fail to read. They must not use the live
        database to get it (card #7217: "Never probe by opening or modifying a
        live database directly"), so the daemon makes a disposable one in the
        same protected directory, with the same ownership and mode.
        """
        if loaded.entry.fixture_root is None:
            raise InvalidParams(
                f"{loaded.entry.project!r} has no fixture_root registered; synthetic "
                "fixtures are unavailable"
            )
        name = params.get("name")
        if not isinstance(name, str) or not name.replace("-", "").replace("_", "").isalnum():
            raise InvalidParams("fixture 'name' must be alphanumeric with - or _")

        attr = "dbmed_fixture_create" if create else "dbmed_fixture_destroy"
        handler = getattr(loaded.backend, attr, None)
        if handler is None:
            raise UnknownOperation(
                f"{loaded.entry.project!r} does not implement fixture provisioning"
            )
        with loaded.lock:
            return handler(name=name)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:  # noqa: D102 - socketserver interface
        service: Service = self.server.service  # type: ignore[attr-defined]
        started = time.perf_counter()
        uid = -1
        frame: dict[str, Any] = {}
        try:
            try:
                uid = peer_uid(self.request)
            except PeerCredentialError as exc:
                self._send_error(NotAuthorized(str(exc)))
                return

            with self.request.makefile("rb") as stream:
                blob = protocol.read_frame(stream, protocol.MAX_REQUEST_BYTES)
            if not blob:
                return
            frame = protocol.decode_request(blob)

            data = service.handle(uid, frame)
            self.request.sendall(protocol.encode_response(True, data))
            self._audit(service, uid, frame, started, ok=True)
        except DbmedError as exc:
            self._send_error(exc)
            self._audit(service, uid, frame, started, ok=False, exc=exc)
        except Exception as exc:  # pragma: no cover - last resort
            wrapped = OperationFailed(f"unhandled {type(exc).__name__}: {exc}")
            self._send_error(wrapped)
            self._audit(service, uid, frame, started, ok=False, exc=wrapped)

    def _audit(
        self,
        service: Service,
        uid: int,
        frame: dict[str, Any],
        started: float,
        *,
        ok: bool,
        exc: DbmedError | None = None,
    ) -> None:
        service.audit.record(
            event="call",
            uid=uid,
            project=frame.get("project", "?"),
            op=frame.get("op", "?"),
            kind=_kind_of(service, frame),
            ok=ok,
            duration_ms=(time.perf_counter() - started) * 1000,
            param_names=list(frame.get("params", {})),
            error_code=exc.code if exc else None,
            detail=exc.message[:300] if exc else None,
        )

    def _send_error(self, exc: DbmedError) -> None:
        try:
            self.request.sendall(protocol.encode_response(False, error=exc.to_wire()))
        except OSError:
            pass


def _kind_of(service: Service, frame: dict[str, Any]) -> str:
    project = service.projects.get(frame.get("project", ""))
    if project is None:
        return "unknown"
    spec = project.ops.get(frame.get("op", ""))
    return spec.kind.value if spec else "builtin"


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 64

    def __init__(self, path: str, service: Service) -> None:
        self.service = service
        super().__init__(path, _Handler)


def _bind(socket_path: Path, service: Service) -> _Server:
    """Bind atomically over any stale socket.

    We deliberately do not delete the old socket first. Binding a fresh path
    and renaming it into place is atomic on POSIX, so there is never a moment
    when the well-known path is absent — a client that connects during a
    restart waits or is refused, rather than seeing "no such file" and having
    to decide what that means. It also keeps this code free of file deletion
    entirely, which is the house rule.
    """
    if socket_path.is_symlink():
        raise IntegrityError(f"{socket_path} is a symlink; refusing to bind through it")
    if socket_path.exists() and not stat.S_ISSOCK(socket_path.stat().st_mode):
        raise IntegrityError(f"{socket_path} exists and is not a socket")

    staging = socket_path.with_name(f".{socket_path.name}.{os.getpid()}")
    if staging.exists() or staging.is_symlink():
        raise IntegrityError(f"staging path {staging} already exists; refusing to bind")

    server = _Server(str(staging), service)
    try:
        os.chmod(staging, SOCKET_MODE)
        os.rename(staging, socket_path)
    except OSError:
        server.server_close()
        raise
    return server


def serve(
    *,
    socket_path: Path = DEFAULT_SOCKET,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    install_dir: Path = DEFAULT_INSTALL_DIR,
    data_root: Path = DEFAULT_DATA_ROOT,
    verify_integrity: bool = True,
    ready: threading.Event | None = None,
    control: dict | None = None,
    poll_interval: float = 0.2,
) -> None:
    service = Service(
        config_dir=config_dir,
        install_dir=install_dir,
        data_root=data_root,
        verify_integrity=verify_integrity,
    )

    socket_path.parent.mkdir(parents=True, exist_ok=True)
    server = _bind(socket_path, service)

    def _shutdown(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except ValueError:
            # Not the main thread: an embedding test harness owns shutdown.
            pass

    # An embedding harness (the test suite) needs a way to stop a daemon it
    # started on a thread, where signal handlers are unavailable. Handing back
    # the server object is the whole mechanism: `control["server"].shutdown()`.
    if control is not None:
        control["server"] = server

    # `poll_interval` is how long `shutdown()` can take to be noticed. The
    # default suits a daemon that runs for weeks and should not wake 100
    # times a second to check whether it has been asked to stop. The test
    # suite starts and stops a daemon per test and passes something much
    # smaller, where the tradeoff runs the other way.

    if ready is not None:
        ready.set()
    try:
        server.serve_forever(poll_interval=poll_interval)
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dbmedd", description="dbmed mediation daemon")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--install-dir", type=Path, default=DEFAULT_INSTALL_DIR)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--skip-integrity-check",
        action="store_true",
        help="test harness only; refused when running as root",
    )
    args = parser.parse_args(argv)

    try:
        serve(
            socket_path=args.socket,
            config_dir=args.config_dir,
            install_dir=args.install_dir,
            data_root=args.data_root,
            verify_integrity=not args.skip_integrity_check,
        )
    except IntegrityError as exc:
        print(f"dbmedd: refusing to start: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
