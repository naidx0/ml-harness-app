# Tasks

**This backlog is closed. New work comes from `docs/PHASES.md`.**
(It came from `docs/ROADMAP.md` until 2026-08-27; that file is the reference now.)

Everything on the old list is done. The one item that was still open — which
model to recommend for image goals — is no longer a standalone task: model choice
is now the job of the diagnosis engine (`docs/diagnosis_engine.yaml`) and the fit
ranker, which receive the data kind and the measured hardware profile rather than
a goal string and a hardcoded 8.0. It is closed here and answered there, in
Milestone 5.

If you are an agent looking for the next thing to build, take the next unchecked
step from the execution queue at the bottom of `docs/PHASES.md` and follow the
rules in `AGENTS.md`.

---

# Archive — completed backlog

Kept because each entry is evidence: what the defect was, how it was verified,
and which test guards it now. Do not delete these. Several are the only written
record of why a test exists.

- [x] Add comparison of two selected runs for one metric, with API/UI tests.

- [x] Add a teaching panel that explains loss curves using only recorded values
  and clearly labels heuristics. DONE 2026-08-13 as plan step 7.2 — `app/teach.py`,
  `explain_loss(run_id)`. Observed states only measured endpoints; heuristics
  carry the "Heuristic: " prefix. The first version reported direction backwards
  (min/max instead of first/last); fixed and covered by
  `tests/test_teach_direction.py`.

- [x] Add CSV export for one run and its metrics, with tests. DONE 2026-08-13 by
  autobuild as plan step 7.1 — `app/export.py`, `run_to_csv(run_id)`, covered by
  `tests/test_step_7_1.py`. Mutation-checked: corrupting the header row turns the
  suite red.

- [x] Connect /ui/intake to the API. DONE 2026-08-15. The form posted urlencoded
  to a JSON-only endpoint and returned 422 for everyone. Fixed additively: a
  "field" key on each question, a new POST /ui/intake that generates a uuid4
  session_id and 303-redirects to the plan. POST /intake, IntakeCreate and the
  integer ids are untouched. Verified by clicking Submit in a browser, landing on
  /ui/plan/1bfefdb9ea0648c8875006f25c736b75 with the goal text carried through.
  Guard: `tests/test_intake_form_journey.py`, mutation-tested by reverting the
  form action.

- [x] Make the fine-tune recommendation reachable. DONE 2026-08-15. `recommend()`
  used `goal == "fine-tune"`, exact equality on a free-text field, so QLoRA and
  LoRA were unreachable from the UI and every real goal returned inference-only.
  Matching is now casefolded/stripped/substring. Verified through the form in a
  browser: the same intake that returned inference-only now returns QLoRA. Guard
  `tests/test_recommend_reachable.py`, mutation-tested. `test_step_2_3.py`
  untouched.

- [ ] ~~Decide which model to recommend for image goals.~~ **CLOSED 2026-08-18,
  superseded.** `recommend()` never received `data_kind` — it took only a goal
  and a hardcoded 8.0 VRAM — so "Fine-tune a small image classifier" was answered
  with Qwen3-4B, a language model. This is no longer a one-off product call:
  `recommend()` is replaced by the diagnosis engine, and model selection moves to
  the fit ranker in Milestone 5, which receives the data kind and the measured
  hardware profile as inputs. See `docs/ROADMAP.md`.

- [x] Render the plan page instead of dumping it, and stop reflecting user input.
  DONE 2026-08-15. Two defects, one fix. The page dumped markdown into `<pre>`, so
  readers saw literal "# Training plan"; and the goal is user input that was
  interpolated unescaped, which was a live reflected XSS — confirmed by loading a
  goal of `<img src=x onerror="document.title='XSS-EXECUTED'">` in a real browser
  and watching the tab title change. Now `html.escape()` runs BEFORE
  `markdown.markdown()`, which neutralises injected tags while leaving `#`/`##`
  intact. The plaintext /plan and /plan/download routes are untouched and still
  return raw markdown. `markdown>=3.5` added to pyproject — it was used but
  undeclared. Guards in `tests/test_plan_page_render.py`, both mutation-tested:
  removing the escape reddens the XSS test, reverting to the `<pre>` dump reddens
  the render test. Re-verified in the browser: the same payload is now inert text.

- [x] Screenshot set captured. DONE 2026-08-15. Four PNGs at 1440x1200 in
  09-Nightshift/inbox/shots/: dashboard-empty, dashboard-compare (two separated
  curves), intake-composer, plan. Captured by Codex's fleet-verify skill via a
  cached Puppeteer headless shell — the repo still carries no browser dependency.
  Reading them found a real defect no DOM assertion had: Goal/Method/Quantization
  rendered as one run-on line.

- [x] Screenshot package. DONE 2026-08-15. Four current captures at 1440x1200 in
  09-Nightshift/inbox/shots/ plus HOW-THESE-WERE-MADE.md with the exact command.
  No browser dependency was added: Chrome screenshots from the command line using
  the chromium already cached on this machine. Post copy drafted in
  09-Nightshift/inbox/2026-08-15-post-drafts-ml-harness.md — four options, NOT
  posted. Two earlier captures had to be discarded for showing markup that no
  longer existed; the note explains how to avoid that.
