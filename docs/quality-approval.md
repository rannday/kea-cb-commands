# Quality runner approval investigation

## Status

Investigated on 2026-10-15 in Debian WSL. The cause is verified, but the
environment-level defect remains unfixed. No security settings or installed
hooks were changed. No elevated execution, wrapper retry, commit or push was
used during this investigation. The initial worktree was clean.

## Original command and diagnostics

The original command was:

```sh
PATH="$PWD/build-quality-venv/bin:$PATH" python3 -B scripts/quality.py
```

Its exact diagnostic was:

```text
Command blocked by PreToolUse hook: Protected .env or PEM path. Use a redacted example file.. Command: PATH="$PWD/build-quality-venv/bin:$PATH" python3 -B scripts/quality.py
```

A later Python subprocess wrapper was separately rejected by automatic approval
review with this reason:

```text
This retry wraps the blocked quality script to evade a safety hook protecting .env/PEM paths, creating an unresolved risk of reading secret-bearing files despite the user’s explicit prohibition.
```

These records are in the local session file
`~/.codex/sessions/2026/10/15/rollout-2026-10-15T21-12-16-01a14244-5417-7151-a9af-9cc8e24530e7.jsonl`,
lines 304/307 and 320/322. The two mechanisms must not be conflated. The
automatic review correctly refused an unresolved workaround; the initial
protection hook misclassified the PATH assignment.

## Verified mechanism

`~/.codex/hooks.json` registers
`~/.agents/hooks/bin/codex_hooks.py` for `exec_command` PreToolUse events.
Its `normalize`, `secret_paths`, `shell_secret_paths` and
`protected_shell_word` functions classify the command before execution.

The classifier treats the PATH assignment value as a potential filename.
It masks variable expansions with wildcards and compares the resulting
pattern against protected basenames, including `*.pem`. The value ends with
`bin:$PATH`, producing a basename pattern ending in `bin:*`. That pattern
can intersect `*.pem`. The classifier does not distinguish this executable
search-path assignment from a file access argument.

Calling the installed classifier directly, without executing the command,
returned `True` for the assignment token and `False` for `python3`, `-B`
and `scripts/quality.py`. Both Bash and sh classification denied it.
`dispatch` returned the same protected-path denial. One normal execution
attempt of the exact original command reproduced that denial before startup.
No alternate invocation of the combined runner was attempted afterward.

This is an environment-level classification false positive. It is not a
permission requirement or evidence of protected-file access by the runner.

## Repository scope review

`scripts/quality.py` reads five fixed root files and selected extensions under
`src`, `tests`, `scripts`, `docs` and `.github`. It checks final newlines,
trailing whitespace, JSON syntax and local Markdown link existence. It runs:

```sh
clang-format --dry-run --Werror src/diagnostic.cc
ruff check tests scripts
```

It invokes no shell, SQL, integration harness, Make target or CMake target.
The quality CI job calls it directly after installing isolated tools; the
separate integration job is not called by the runner. No CI installation step
was executed during this investigation. Ruff is configured by the repository's
`pyproject.toml`; clang-format uses the repository's `.clang-format`.

The runner does not enumerate root build directories, `.git`, `.aws`, `.codex`,
`.agents`, `.local` or `.upstream`. Its Python traversal can include ignored or
hidden files with accepted extensions inside the five named directories, and
file symlinks could be followed by `is_file`/`read_text`. Link existence checks
can also inspect metadata outside the repository if a document names such a
target. These are scope limitations, not the reproduced trigger. A metadata-only
walk found no symlinks in the five directories in this checkout. No protected
file was intentionally opened. No repository script was changed to suppress
the warning or reduce coverage.

## Verification and next action

The installed clang-format dry-run and Ruff checks passed independently.
Tooling unit discovery passed 17 tests; application unit discovery passed six.
Separate checks of the runner's selected files passed JSON parsing, whitespace
and local Markdown links. The combined runner remains blocked and is not
reported as passing. SQL integration was not rerun because no hook or
integration behavior changed.

The least-privileged repair belongs in the source project that owns the
installed Codex hook, outside this repository. It needs separate authorization:

1. Locate the source of `codex_hooks.py` used by that project's installer.
2. Add a regression fixture containing the exact PATH assignment above.
3. Correct PATH-list assignment classification without exempting executable
   arguments, redirections or command substitutions from protected-path checks.
   Retain tests for literal protected paths and protected PATH-list components.
4. Run that project's hook security tests, review the diff, and authorize only
   deployment of the tested hook files. Keep sandbox and approval policies intact.
5. Review the hook through `/hooks`, reload Codex if required by the deployment
   workflow, then rerun the exact original command under normal protections.

No Codex configuration change is recommended. Disabling the hook or adding a
blanket allow rule would weaken unrelated protections and is not a repair.
Until the scoped hook fix is authorized and verified, resolution is partial.
