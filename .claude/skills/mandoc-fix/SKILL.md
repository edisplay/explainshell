---
name: mandoc-fix
description: Drive a mandoc rendering-bug fix end-to-end — scope the bug class, dispatch a subagent in the mandoc source tree, validate via /eval-render audit + compare, and decide whether to promote. Use when the user has identified (or suspects) a class of `-T markdown` rendering bug and wants the full diagnose → fix → validate → promote cycle.
user_invocable: true
---

# mandoc-fix

You orchestrate the recurring mandoc-fix cycle: scope a bug class, dispatch a fresh subagent in `~/dev/vibe/mandoc-1.14.6/` (or the configured tree), validate the result with the existing render eval (`audit` for absolute check, `compare` for regression net), and decide promote / iterate / defer.

This skill calls `/eval-render` and `/eval-llm` as substeps — do not re-implement what they do.

## Usage

```
/mandoc-fix <bug-description> [--rule <audit-rule>] [--pages <file>] [--mandoc-worktree <path>]
```

## Arguments

- **bug-description** (required): Free-text description of the bug class, written so a subagent in the mandoc tree can understand it without prior context. Include a roff repro if possible.
- **rule** (optional): One of the audit rule ids (`quad_star_run`, `empty_emphasis_tag`, `roff_named_escape`, `roff_two_letter_escape`, `roff_font_escape`, `visible_zwnj_entity`, `visible_nbsp_entity`, `visible_double_amp`, `giant_markdown_line`, `synopsis_no_spaces_run`). When provided, the rule's count over the corpus is the load-bearing acceptance metric. When omitted, ask the user which rule (or rules) define success — guess only if the bug-description maps unambiguously to one rule.
- **pages** (optional): Path to a file listing repo-relative manpage paths affected by the bug (one per line). When provided, the absolute baseline is rendered against this list specifically; otherwise the standard `tests/evals/render/corpus.txt` is used.
- **mandoc-worktree** (optional): Path to the mandoc source tree. Defaults to `/home/idank/dev/vibe/mandoc-1.14.6/`.

## Step 1: Scope

Confirm what's being measured before you spend any agent time. Show the user:

- The audit rule that will gate promotion.
- The page set the rule will be applied to (corpus vs `--pages` file, with row count).
- The current mandoc HEAD commit and the binary md5 of `tools/mandoc-md` so they know what "baseline" means.

If the user gave a free-text bug-description without a rule, name one and ask them to confirm. If neither a rule nor `--pages` makes the success metric concrete, stop and ask. Don't dispatch the subagent without a measurable target.

## Step 2: Capture absolute baseline

Render the chosen page set with the current `tools/mandoc-md`, then audit:

```bash
source .venv/bin/activate
# Standard corpus
python tests/evals/render/render_eval.py render --label baseline-<rule> --mandoc tools/mandoc-md
# OR custom page list
python tests/evals/render/render_eval.py render --label baseline-<rule> --mandoc tools/mandoc-md $(cat <pages-file>)
python tests/evals/render/render_eval.py audit <run-dir> --rules <rule>
```

Record the rule's `pages × occurrences` baseline number. This is what the candidate must beat.

## Step 3: Dispatch subagent

Use the `templates/subagent-brief.md` template. Fill in every placeholder. Spawn a fresh general-purpose agent (the mandoc tree is a separate working directory; the subagent will operate there).

Brief the agent **not to push or promote** — those are your job after validation.

Wait for the subagent to return before continuing. Run it foreground (default), not background — the validation steps depend on its output.

## Step 4: Validate (three layers)

After the subagent reports a commit + rebuilt binary:

a. **Absolute check (load-bearing).** Render the same page set with the candidate; audit; compare counts to the baseline. Target: rule's `pages × occurrences` strictly down. Acceptable residue is content-driven (e.g. literal `*` in source roff); the subagent's report should distinguish.

b. **Regression net.** Invoke `/eval-render <candidate-binary>` to run the standard compare. Read the verdict. Suspicious deltas unrelated to the targeted rule are regressions.

c. **Spot-check.** Render and visually diff 2–3 of the most-affected pages from the baseline, confirming the fix matches the subagent's repro and doesn't introduce new visual artifacts.

## Step 5: Apply the rubric

- **merge** ⇢ absolute count strictly down, `/eval-render` verdict is merge, spot-checks clean. Recommend: `cp <candidate> tools/mandoc-md`, commit referencing the upstream commit hash, suggest `/eval-llm` and re-extraction of the affected pages.
- **regression** ⇢ any layer fails. Re-dispatch the subagent (Step 3) with a delta brief that names the specific regression and concrete acceptance test. Re-iterate until merge or defer.
- **defer** ⇢ ambiguous cases (e.g. absolute count drops but `/eval-render` flags structural changes). Surface evidence to the user and ask.

## Step 6: Promote and propose downstream

On merge:

```bash
cp <candidate-binary> tools/mandoc-md
git add tools/mandoc-md
git commit -m "feat(tools): promote mandoc-md with <one-line summary>

Picks up mandoc <upstream-commit> (\"<upstream-subject>\"). <impact line>.
<rule> drops from <baseline> to <candidate> across the <page-set>."
```

Then propose (don't run without explicit go-ahead):

1. **`/eval-llm`** as a sanity check that cleaner markdown doesn't perturb extraction quality.
2. **Re-extract the affected pages** with `--reason` populated:
   ```
   python -m explainshell.manager extract --mode llm:<model> --overwrite \
     -j 10 --reason "<one-line: what fixed, eval verdict>" \
     $(tr '\n' ' ' < <pages-file>)
   ```
3. **Upload the live DB** with `make upload-live-db` once the user confirms the re-extract looked clean.

## Reporting back

Final user-facing report (in chat, not a file):

- One-line verdict.
- Baseline → candidate counts for the gating rule, with `pages × occurrences`.
- `/eval-render` aggregate verdict (one line).
- Spot-checked pages (one bullet each, before → after).
- If **merge**: the promotion commands above, ready to run.
- If **regression**: the redispatched subagent prompt fenced and ready.
- If **defer**: the specific evidence and a concrete question.

## What NOT to do

- Don't dispatch a subagent without a measurable success metric (rule + page set).
- Don't promote without all three validation layers passing.
- Don't run `/eval-llm`, re-extract, or `make upload-live-db` without explicit user confirmation — those are downstream actions with cost or production impact.
- Don't push or merge changes in the mandoc tree from this session — the subagent commits in its own tree; the user pushes those upstream when they choose.
