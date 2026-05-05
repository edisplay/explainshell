<!--
Subagent brief template for /mandoc-fix.

The orchestrator fills the placeholders in <ANGLE_BRACKETS> and dispatches
the rendered text as a fresh general-purpose agent. Every section pulls its
weight; if a section is empty, drop it rather than emit a placeholder.

Required substitutions:
- {{WORKTREE}}         absolute path, e.g. /home/idank/dev/vibe/mandoc-1.14.6
- {{HEAD_COMMIT}}      output of `git log --oneline -1` in the worktree
- {{LOCAL_HISTORY}}    bullet list of recent local commits the subagent must
                       not break (subject lines + one-sentence intent each)
- {{BUG_NAME}}         short label for the bug class
- {{BUG_DESCRIPTION}}  why the bug matters in plain English
- {{REPRO_CLI}}        printf | mandoc invocation that demonstrates the bug
                       and the desired output
- {{REPRO_PAGE}}       at least one real manpage path (under
                       ../explainshell/manpages/) that contains the pattern
- {{ACCEPTANCE_TESTS}} numbered list of what the candidate must produce
- {{INVARIANTS}}       list of behaviors that must NOT change (e.g. "italic
                       still emits *...*", "&zwnj; insertion intact",
                       "intraword italic still works")
- {{AUDIT_RULE}}       audit rule id whose count must drop (e.g. quad_star_run)
- {{AUDIT_PAGE_SET}}   "the standard corpus" or "the {{N}}-page list at
                       <path>"
- {{BASELINE_COUNT}}   "<P> pages, <N> occurrences" measured before dispatch
- {{REPORTING_FIELDS}} pass-through fields the orchestrator needs back
  (commit hash, smoke test outputs, audit count, regress tally, judgment
  calls)
-->

You're working in {{WORKTREE}}, a vendored mandoc 1.14.6 source tree with a
stack of local fixes. Build with `make`; output is `./mandoc`.

## Context

`HEAD` is at `{{HEAD_COMMIT}}`. Recent local commits you must preserve:

{{LOCAL_HISTORY}}

## The bug — {{BUG_NAME}}

{{BUG_DESCRIPTION}}

### Repro

CLI:

```
{{REPRO_CLI}}
```

Real-world example: `{{REPRO_PAGE}}` (under `../explainshell/manpages/`).

## What I want

{{ACCEPTANCE_TESTS}}

## Invariants — these MUST keep working

{{INVARIANTS}}

## Process

1. Read `git log -p <range>` for the recent local commits in this tree
   before patching anything in `mdoc_markdown.c` — they share data
   structures with what you're about to change.
2. Implement the fix. Prefer extending existing machinery
   (`pending_close_marker`, `marker_stack`, `outer_marker`, font-mode
   helpers) over inventing new globals.
3. Build (`make`).
4. Run the CLI repro above and confirm the desired output.
5. `make regress` 100% pass. Update fixtures only when the change
   legitimately changes their expected output. Add a new fixture under
   `regress/man/B/` (or `regress/mdoc/`) covering the new case, in the
   style of recent additions like `regress/man/B/emphasis_transitions`.
6. Cross-check on the audit page set. From `/home/idank/dev/vibe/explainshell`:

   ```
   source .venv/bin/activate
   python tests/evals/render/render_eval.py render \
     --label candidate-{{BUG_NAME}} --mandoc {{WORKTREE}}/mandoc <CORPUS_OR_LIST>
   python tests/evals/render/render_eval.py audit <run-dir> --rules {{AUDIT_RULE}}
   ```

   Target: `{{AUDIT_RULE}}` count strictly below the baseline of
   `{{BASELINE_COUNT}}`. Acceptable residue is content-driven (literal
   `*` in source roff, etc.) — call those out so the orchestrator can
   verify rather than guessing.
7. Commit with a Conventional-Commits-shaped subject:
   `Fix -T markdown: <one-line>`. Body explains the mechanism, references
   the canonical motivating page (`{{REPRO_PAGE}}`), and notes any
   accepted residue.

## What NOT to do

- Don't reintroduce `*` for italic if a prior local commit switched to
  `_` (or vice versa). Check `{{LOCAL_HISTORY}}`.
- Don't remove `&zwnj;` insertion machinery; it's load-bearing for
  bold↔italic abutment.
- Don't touch any file outside `{{WORKTREE}}`.
- Don't promote the binary into `../explainshell/tools/`.
- Don't push the commit.

## Reporting back

When done, give a short summary:

{{REPORTING_FIELDS}}

If anything blocks the fix (e.g. it would regress an invariant), stop
and report — don't ship a partial fix.
