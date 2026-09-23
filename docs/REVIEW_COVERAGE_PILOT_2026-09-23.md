# Bounded review coverage pilot — September 23, 2026

This is a retrospective case study, not a claim that the revised governance
instructions improve review quality across the portfolio. The independent
reviewer's complete report was frozen before the historical findings were
revealed. The raw report follows the comparison below verbatim.

## Frozen setup

- Case: [claude-user-config PR #94](https://github.com/eriksjaastad/claude-user-config/pull/94), secret-dump PreToolUse hook.
- Reviewed head: `c68416a416cecac0e07d9ab152d1b248f219e812`.
- Diff base: its parent `bb8d46df5c01e0886e5bfa894196a19cd9650e6b`.
  The focused commit changes four files, 446 insertions and 301 deletions.
  This is a commit-focused review, not the entire cumulative PR diff.
- Contract given before review: block protected secret-value reads through
  direct/wrapped readers, redirections and directory-context changes while
  allowing legitimate safe commands; inspect affected callers and the frozen
  repository's `AGENTS.md` and `hooks/AGENTS.md`.
- Blinding: the reviewer was given a detached checkout and the frozen SHAs,
  without later commits, GitHub review comments, cards, replay files or finding
  labels. Its report was saved before the held-out audit was opened. The raw
  report's SHA-256 was
  `b33d8499a38f9cf94029b1f01e28f402494e5e2ee9f5325a255a2750af3f4518`.

## Held-out comparison

The historical audit identifies 11 findings eventually reported over three
reviews at or after this head: six on `c68416a`, three on `108d6c6`, and two
on `75162dc`. Its isolated public-hook replay found all 11 reproducible on
both inherited `f3cd17f` and the frozen reviewed head. This is a lower bound
on defects present, not an exhaustive inventory. Historical review at the
frozen head reported 6/11; subsequent reviews brought cumulative discovery
to 9/11 and then 11/11. These denominators refer to this three-review audit,
not the later closeout batches.

The blind report found two supported cwd findings. Its conditional `cd` and
wrapped `builtin cd` cases match historical finding R6-2's control-flow and
wrapped-directory family. Its `pushd` example matches the later R7-1
directory-builtin family. Counted by the audit's finding families, this is
**2/11 retrospective recall**. The `cd ... || :` example is a new concrete
case in an already represented family; it is not counted as a third family.
The reviewer reported no separate false-positive defect and missed five
historically supported false blocks (R6-4/5/6 and R7-2/3), as well as four
other bypass families (R6-1/3 and R8-1/2). It named option parsing, variable
paths and shell grammar as coverage gaps but did not turn those concerns into
unsupported findings.

The blind report called one cwd bug introduced by new tracking logic. That
origin claim is too strong: the held-out replay already shows the **family**
failing on inherited `f3cd17f`. The exact new `||` spelling was not replayed on
that earlier head here, so its individual origin remains unverified. No
fix-induced regression or deliberate withholding can be inferred from this
pilot. The reviewer tested the public JSON boundary with synthetic commands,
not real secret values; Linux procfs and GNU tool behavior were not exercised
on this macOS host. This single reviewer, short contract prompt, focused commit
diff and historical case cannot establish a future first-review rate.

The practical correction is to require bounded related-form and legitimate-use
probes before claiming coverage. Instruction delivery and a large passing test
count were both present in the historical case, yet neither proved coverage.
Further effectiveness claims need a fresh held-out case and a clear denominator.

## Frozen independent report

# Blinded local review: c68416a416cecac0e07d9ab152d1b248f219e812

Scope: exact diff `bb8d46df5c01e0886e5bfa894196a19cd9650e6b..c68416a416cecac0e07d9ab152d1b248f219e812` in the frozen snapshot, affected parser and hook callers, `AGENTS.md`, and `hooks/AGENTS.md`. No later history or real secret values were inspected. Probes passed command strings to isolated copies of the hook with an empty allowlist; they did not execute the command strings.

## Supported findings

1. **P1, primary contract: successful `cd` is forgotten across `||`.** `hooks/command_parser.py:1213-1214` unconditionally restores `previous_cwd` when the next stage has `sep == "||"`. In `cd /proc/self || :; cat environ`, `cd` succeeds, Bash skips `:`, and `cat` runs in `/proc/self`; the parser nevertheless resets cwd to the original directory and the hook returns JSON `{}` (allow, exit 0). `cd /proc/self || true && cat environ` is another executable form with the same cause. The corresponding `cd /proc/self && cat environ` is denied. The new context model needs to retain both feasible cwd states after a conditional branch or conservatively check the secret path in either state. This is a direct secret-value disclosure through a directory-context change, introduced by the new cwd tracking logic.

2. **P1, primary contract: shell builtins that invoke `cd` are not tracked.** `hooks/command_parser.py:1264-1268` updates cwd only when a simple command begins literally with `cd`. In Bash, `builtin cd /proc/self && cat environ` and `command cd /proc/self && cat environ` change the current shell's directory before `cat`, but the public hook returns JSON `{}` (allow, exit 0) for both. The direct `cd /proc/self && cat environ` counterpart is denied. `pushd /proc/self >/dev/null && cat environ` is another directory-changing Bash builtin with the same miss. The existing command-position and launcher parsing surfaces these forms as commands; the cwd state update fails to apply the shell builtin semantics. Group these forms as one root cause.

## Safe-command and false-positive assessment

The isolated hook denied the intended direct and wrapped examples `cat < /proc/self/environ`, `grep . /proc/self/environ`, `rg . /proc/self/environ`, `env -C /proc/self cat environ`, and `sh -c "cd /proc/self && cat environ"`. It allowed the safe pattern/value case `rg -e --pre README.md`, and ordinary `cat README.md`. The new option parser's metadata-only search modes and value-taking options are important false-positive surfaces; the changed tests exercise many of these, but they do not cover conditional cwd joins or shell builtin cwd changes. No separate supported false-positive defect was found in the focused probes.

## Verification and limits

`hooks/test_command_parser.py`: 274/274 passed. `hooks/test_block_secret_dump_commands.py`: 542/542 passed. Public JSON probes used only synthetic command text, a controlled `/tmp` cwd, and copies of hook files in an isolated temporary directory. No real secrets, `/proc/.../environ` contents, or `.env` files were read. The review did not establish behavior for every shell grammar form, symlink-resolved cwd, variable-expanded paths, or every GNU tool option; those are coverage gaps, not additional findings. Mechanical checks M1-M4 raised no separate supported issue in the changed files; M5 does not apply because no static JavaScript changed. No destructive operations or subprocess execution paths were added by this diff.

**FAIL — c68416a416cecac0e07d9ab152d1b248f219e812**
