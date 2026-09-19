# Boundary Tests — dbmed Database Access Enforcement

**Purpose:** Prove that agent processes cannot reach `tracker.db` directly, and must go through the dbmed mediation daemon.

**Cards:** #7219 (project-tracker integration), #7228 (mechanism), umbrella #7217

---

## What These Tests Prove

The boundary test suite validates the dbmed enforcement layer across multiple dimensions:

1. **Protocol correctness** — operations allowlist, parameter schemas, error handling
2. **Authorization model** — destructive operations require tokens, backups verified before mutations
3. **Fail-closed guarantee** — when the daemon is unavailable, clients exit non-zero and do not fall back to opening files
4. **POSIX enforcement** — when the root install is present, kernel-level file access denials

**Critical distinction:** Most of these tests pass *without* a root install. They validate the protocol and the client behavior, but they **do not prove a process cannot open the file**. Only the POSIX denial probes in `test_posix_denial.py` can prove that, and those skip when the install is absent.

---

## Running the Tests

### Local Development (No Install Required)

```bash
# Run the full boundary suite
uv run pytest tests/boundary/ -v

# Run only protocol tests (work without an install)
uv run pytest tests/boundary/test_operation_surface.py -v
uv run pytest tests/boundary/test_destructive_gate.py -v
uv run pytest tests/boundary/test_fail_closed.py -v

# Generate the evidence matrix (what was actually proven)
uv run pytest tests/boundary/ -s -k evidence_matrix
```

**Expected result:** Green, but the evidence matrix will show `UNVERIFIED` for POSIX denials. This is correct — nothing stopped you from opening the file, because no boundary exists yet.

### With Root Install (Erik's Machines)

```bash
# After running the installer with sudo
sudo scripts/dbmed-install/install.sh

# Run the full suite, including POSIX denial probes
uv run pytest tests/boundary/ -v

# Generate verified evidence
uv run pytest tests/boundary/ -s -k evidence_matrix > /tmp/evidence-$(date +%Y%m%d).md
```

**Expected result:** Green, and the evidence matrix shows `VERIFIED` for POSIX denials. The matrix explicitly names the gaps (Mac Mini, non-Claude runtimes) and states them as unfinished work.

---

## Interpreting Results

### test_evidence_matrix.py

**Always passes.** It reports; it does not judge. Its output is the authoritative statement of what this run proved.

Key sections:

- **Installation** — whether the root install components exist at their expected paths
- **What this run proved** — plain-language summary (install present or not)
- **Coverage** — which areas are VERIFIED vs UNVERIFIED on this host/runtime
- **Known gaps** — explicit enumeration of what is NOT covered (Mac Mini, Codex, Cursor, Grok sudo posture)

**Rule:** If a row in "Known gaps" says UNVERIFIED or OUT OF SCOPE, you may not claim it is proven. Card #7217: "an uncovered path is unfinished work".

### test_operation_surface.py

Validates the allowlist:

- Only operations in `ALLOWLIST` are reachable
- Parameter schemas are enforced (no arbitrary SQL, paths, or code crosses the socket)
- Destructive operations are classified correctly

**Passes without an install.** Proves the protocol design is sound, not that files are protected.

### test_destructive_gate.py

Validates the authorization model:

- Destructive operations refuse without a token
- Tokens are single-use and issued only after a verified backup
- Audit records written for all destructive calls

**Passes without an install.** Proves the gate logic works, not that files are protected.

### test_fail_closed.py

Validates the fail-closed guarantee:

- When the daemon is unreachable, the client exits non-zero
- The client has no database driver, so a fallback is impossible to write

**Passes without an install.** Proves the client cannot open files on its own, but does not prove another tool (sqlite3, Python, cat, etc.) is blocked.

### test_posix_denial.py

**SKIPS without an install.** When present, proves:

- `sqlite3` CLI cannot open the file
- Python `sqlite3` and `libsql` drivers cannot open the file
- File tools (`cat`, `head`, `strings`, `dd`, `cp`, `mv`, `rm`) cannot read or modify the file
- Symlinks, subprocess tricks, and SSH do not bypass the boundary
- Guard files (plist, code, dylib, registry) cannot be modified
- The daemon cannot be stopped by an agent

**Only these tests prove the file is protected.** Everything else is necessary but not sufficient.

---

## CI / Cloud Agents

Cloud agent VMs **do not** have a root install. The POSIX denial probes skip, and the evidence matrix will say `UNVERIFIED`. This is correct and expected.

What CI does prove:

- The protocol is well-formed and complete
- The client-side contract is intact
- No regression in the allowlist or parameter schemas

What CI cannot prove without a root install:

- That a determined attacker cannot open the file

**Acceptance criteria (card #7217):** The evidence matrix from Erik's MacBook with a real install, not from CI.

---

## Retained Evidence

The evidence matrix is designed to be captured and committed:

```bash
# On Erik's MacBook, after install
uv run pytest tests/boundary/ -s -k evidence_matrix > docs/BOUNDARY_EVIDENCE_$(date +%Y%m%d).md
git add docs/BOUNDARY_EVIDENCE_*.md
```

This creates a dated, host-specific record of what was proven. The PRD (dbmed/PRD.md) requires this as part of the Phase 1 release contract.

---

## Failure Modes This Prevents

1. **Claiming the boundary works when it has never been installed.** The matrix says UNVERIFIED when the install is absent.
2. **Claiming Mac Mini coverage when only the MacBook was tested.** The matrix names the host it ran on.
3. **Claiming Codex/Cursor/Grok are denied `sudo` when they were never checked.** The matrix says UNVERIFIED and explains why.
4. **Treating a green CI run as proof of enforcement.** CI never has an install, so CI cannot prove files are protected.

Card #7217 is explicit: "an uncovered path is unfinished work", not a pass to be claimed later.

---

## Troubleshooting

### "All POSIX denial tests skipped"

**Cause:** No root install detected.

**Fix:** Run the installer: `sudo scripts/dbmed-install/install.sh` (Erik only; agents cannot and must not attempt it).

### "Client import test failed: found sqlite3 / psycopg2"

**Cause:** The client module imported a database driver, which would allow a fallback.

**Fix:** The client is `dbmed/client.py` and `scripts/db/manager.py`. Neither may import a driver. This is enforced by `test_client_has_no_driver.py`.

### "Operation not in allowlist"

**Cause:** A test tried to call an operation that is not in `scripts/db/dbmed_ops.py:ALLOWLIST`.

**Fix:** If the operation is legitimate, add it to the allowlist and redeploy the daemon. If it is a probe, this is the correct denial.

### "Daemon not reachable"

**Cause:** The daemon is not running, or `DBMED_SOCKET` points at the wrong path.

**Fix (local):** `sudo launchctl bootstrap system /Library/LaunchDaemons/com.dbmed.plist`

**Fix (test fixture):** `conftest.py` automatically starts a test-mode daemon. If it failed to start, check `/tmp/dbmed-test-*.log`.

---

## See Also

- `dbmed/PRD.md` — the boundary's design and requirements
- `dbmed/PROJECT_DOD.md` — acceptance criteria for Phase 1
- `docs/BACKUP_RESTORE_EVIDENCE.md` — backup / restore evidence (separate from boundary enforcement)
- `CLAUDE.md` — project-level instructions, including the database safety gate
