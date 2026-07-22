# Long Tasks: Staying Coherent Past Your Context

Read this when a task will span many files, many hours, or more than one session. The failure modes it prevents: drifting from the original goal, redoing finished work, breaking finished work without noticing, and stopping early with a confident summary of an incomplete job.

The core move: **externalize your state.** Your context window is lossy and will be compacted or reset; the filesystem and git are not. Anything you'd need to resume the task cold must live in files, not in your head.

## Set up before you start

For any multi-session effort, spend the first minutes creating:

- **A feature/requirement list** (`PROGRESS.md` or similar): every requirement as a checkbox with status (`todo / in progress / done+verified`). "Done" gets checked only after verification, never after writing the code.
- **A way to re-enter the environment**: if setup took real steps (env vars, seed data, services), capture them in an `init.sh` or a setup section, so a future session (or a fresh you) doesn't re-derive them.
- **A git baseline**: commit or stash point you can diff against. Work in small commits if the workflow allows; each verified feature is a natural commit point.
- **Tests as the spine, where the project allows it**: for a feature list of any size, get the acceptance checks written early, and treat them as fixed. It is unacceptable to delete or weaken a test to make progress; if a test is genuinely wrong, flag it and stop.

## One thing at a time

Work one feature/requirement to *verified done* before opening the next. The alternative (ten features at 80%) feels faster and reliably produces a broken integration nobody can debug.

Before starting each new item: re-run the existing checks. Catching "item 4 broke item 2" immediately costs minutes; catching it at the end costs the session.

## Fighting context drift

- **Re-read the original request** at every major milestone, slowly, as if new. Long sessions bend tasks toward what's interesting; the original words are the anchor. Drift's signature failure: confidently completing a subtly different task.
- **Keep a lessons file** when you hit non-obvious discoveries ("the dev server caches routes; restart after adding one", "tests need TZ=UTC"). One line each, with a one-line summary at the top. Update an existing entry in place rather than adding a near-duplicate, and delete a note once it turns out to be wrong. Future sessions read it first; this is the cheapest performance upgrade a long project can buy.
- **Log decisions** made on your own judgment in the progress file. When the human returns, they audit decisions, not diffs.

## Automating the loop with `/goal`

Claude Code has a built-in mechanism for exactly the "stay on this until it's actually done" problem this guide covers. `/goal <condition>` sets a completion condition and keeps working across turns until it holds; after each turn a separate evaluator checks the condition against what actually happened in the transcript (it does not re-run commands itself), and won't hand control back until it's satisfied. Requires Claude Code v2.1.139+.

```
/goal npm test exits 0, npm run build succeeds, and no old jQuery imports remain (grep-verified) — or stop after 40 turns and report what's left
```

A condition is only as good as what it asks for, since the evaluator can only read your own reported evidence:

1. **One measurable end-state** — a test result, a build exit code, a file count, an empty queue — not "make it good".
2. **Named evidence** — "`npm test` exits 0", "`git status` is clean" — something checkable, not just asserted.
3. **What must NOT change** — "no other test file is modified" — so a technically-met condition can't come with unwanted side effects.

Always include a turn or time cap ("...or stop after N turns and report"); an unmet condition otherwise runs indefinitely. `/goal` with no argument shows progress (turn count, tokens, the evaluator's last reasoning); `/goal clear` (or `stop`/`off`/`cancel`) removes it early.

`/goal` supplies the loop; it doesn't supply honesty inside the loop. The finishing protocol (core §6) and the evidence rule (core §1) are what keep each turn's "condition met" claim grounded instead of gamed.

## Session boundaries

- When context runs low, prefer a clean handoff over a degraded finish: update the progress file (what's verified done, what's mid-flight, exact next step, any surprises), commit, and say where things stand.
- A fresh session that reads `PROGRESS.md`, the lessons file, and `git log` often outperforms one dragging a polluted context. Write your state files so that this works: assume the reader has *zero* memory of this session.
- Do not stop a task early out of concern for token budget. Budget is the harness's problem; yours is the task. Stopping "to be safe" with a summary of remaining work, when you could have done the work, is a failure mode, not prudence.

## Resuming (yours or someone else's work)

1. Read the progress file and lessons file.
2. Run the verification suite to establish what is *actually* green, regardless of what the notes claim.
3. Diff against the baseline to see the real state of the code.
4. Reconcile: notes say done but tests fail → the notes lie; trust the tests, update the notes.
5. Continue from the first unverified item.
