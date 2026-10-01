> **SUPERSEDED 2026-08-18 by `docs/ROADMAP.md`. Complete: 30 of 30 steps, 0 open.**
>
> This plan is finished. It took the repository from nothing to a working
> FastAPI + SQLite app with a run tracker, a feasibility estimate, an intake
> form, a generated plan and a bounded job runner, with 111 tests green.
>
> It is kept for two reasons, and it is not to be deleted:
>
> 1. **It is real history.** Each step records what was built, what broke, and
>    which test guards it. Several tests in `tests/` have no other written
>    explanation for why they exist.
> 2. **It is the style reference.** `docs/ROADMAP.md` writes its milestone steps
>    in this exact format — exact signatures, exact acceptance-test lines, named
>    target files, and the "READ THIS LAST" warnings that stopped agents
>    repeating known mistakes. When you expand the next milestone into steps,
>    copy the shape of the steps below.
>
> **The target below is out of date.** This plan aimed at planning and
> feasibility for one consumer GPU. The product is now the decision layer above
> the trainer: it delegates training execution to pinned backends and owns the
> question of whether to train at all. See `docs/VISION.md` and
> `docs/COMPETITION.md`. Do not take new work from this file — take it from
> `docs/ROADMAP.md`.

---

# ML Harness — build plan, zero to one

Target: **Sequence, but for machine learning.** A local-first tool that turns
"I want to train X" into a plan the user can actually run on hardware they own.

Not another experiment tracker. W&B, MLflow, Aim and ClearML own that. The wedge
is planning and feasibility for people with **one consumer GPU**, which is the
problem Max solved for himself in August and almost nobody writes down.

## Execution contract — read before touching anything

- Do **one** unchecked step per run. Not two. Not "while I'm here".
- Every step lists its own acceptance test. The step is done when that test
  passes, not when the code looks finished.
- Gate before commit: `python scripts/gate.py` must pass. It runs
  `unittest discover -s tests` and then asserts what that command cannot: that
  as many tests ran as were discovered, that no module failed to import, and
  that the run reached its verdict line.
- Branch first. Never `main`. `git switch -c agent/mlh-<step-id>`.
- Never push, never merge.
- If a step is ambiguous, write the question into this file under the step and
  stop. Do not guess.
- Keep it boring: stdlib + FastAPI + sqlite. No new heavy dependency without a
  step that exists to add it.

Current state: FastAPI app, sqlite store, run/metric recording, run comparison,
6 passing tests, ~350 lines.

---

## Phase 1 — Intake (the front door)

- [x] **1.1a Hardware table + db helpers.** DONE 2026-08-12 by autobuild.
  `hardware_profile` table in `app/db.py` plus `create_hardware_profile()` and
  `get_latest_hardware_profile()`.

- [x] **1.1b Test the hardware db helpers.** The implementation already
  exists in `app/db.py`. Write ONLY the acceptance test.
  Call `db.create_hardware_profile("RTX 2060 SUPER", 8.0, 16.0, "Windows", 200.0)`,
  then `db.get_latest_hardware_profile()`, and assert with `self.assertEqual`
  that `gpu_name` is `"RTX 2060 SUPER"`, `vram_gb` is `8.0`, and `os` is
  `"Windows"`. Call the real `db` functions - do NOT define your own.
  Target file: `app/db.py`.
  *Accept:* three `self.assertEqual` calls on the values that came back.
- [x] **1.1c Hardware endpoints.** DONE 2026-08-12 (hand-written after 6 autobuild attempts) Add `POST /hardware` and `GET /hardware` to
  `app/main.py`, calling the helpers that already exist in `app/db.py`.
  *Accept:* a test using the existing TestClient pattern from
  `tests/test_app.py` posts a profile and gets it back.

- [x] **1.2a Parse nvidia-smi output.** `parse_nvidia_smi(text)` already
  exists in `app/hwdetect.py`. Write ONLY the acceptance test.
  It is a PURE FUNCTION - call `hwdetect.parse_nvidia_smi(...)` directly.
  There is no endpoint, do NOT use `self.client`.
  Assert with `self.assertEqual` that
  `hwdetect.parse_nvidia_smi("NVIDIA GeForce RTX 2060 SUPER, 8192 MiB")["gpu_name"]`
  equals `"NVIDIA GeForce RTX 2060 SUPER"`, that its `["vram_gb"]` equals `8.0`,
  and that `hwdetect.parse_nvidia_smi("")["gpu_name"]` is None using
  `self.assertIsNone`.
  Target file: `app/hwdetect.py`.
  *Accept:* three assertions, all calling the real function.
- [x] **1.2b Detect RAM and disk.** `local_specs()` already exists in
  `app/hwdetect.py`. Write ONLY the acceptance test.
  Assign `specs = hwdetect.local_specs()` then assert with `self.assertIn`
  that `"ram_gb"`, `"disk_free_gb"` and `"os"` are each in `specs`, and with
  `self.assertIsInstance` that `specs["os"]` is a `str`.
  Target file: `app/hwdetect.py`.
  *Accept:* four assertions on the returned dict.
- [x] **1.3 Intake questions endpoint.** `GET /intake/questions` already
  exists in `app/main.py`. Write ONLY the acceptance test.
  Assign `resp = self.client.get("/intake/questions")`, assert
  `resp.status_code` equals 200 with `self.assertEqual`, assign
  `items = resp.json()`, assert `len(items)` is greater than 0 with
  `self.assertGreater`, then for the FIRST item assert with `self.assertIn`
  that each of `"id"`, `"prompt"`, `"type"`, `"options"` is in `items[0]`.
  Target file: `app/main.py`.
  *Accept:* status 200, a non-empty list, and all four keys present.
- [x] **1.4a Intake storage helpers.** DONE 2026-08-12 (hand-written after 6 autobuild attempts) Add THREE new functions to `app/db.py`.
  You may only ADD functions - you cannot edit `init_db`, so the table must be
  created by your own code, not by `init_db`.
  1. `ensure_intake_table()` runs
     `CREATE TABLE IF NOT EXISTS intake (id INTEGER PRIMARY KEY AUTOINCREMENT,
     session_id TEXT, answers TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)`
     using `with session() as connection:` exactly like `init_db` does.
  2. `create_intake(session_id, answers)` calls `ensure_intake_table()` FIRST,
     then json-dumps the answers dict and inserts a row.
  3. `get_intake(session_id)` calls `ensure_intake_table()` FIRST, selects the
     newest row for that session_id, and returns a dict with `answers`
     json-loaded back into a dict, or None if there is no row.
  Use `json` (already imported) and copy the style of `create_hardware_profile`.
  Target file: `app/db.py`.
  *Accept:* a test calling `db.create_intake("s1", {"goal": "fine-tune"})` then
  `db.get_intake("s1")` and asserting the answers dict round-trips. No HTTP.

- [x] **1.4b Intake endpoints.** Add `POST /intake` and `GET /intake/{session_id}`
  to `app/main.py`, calling `db.create_intake` and `db.get_intake` which now
  exist. POST takes `{"session_id": str, "answers": dict}` and returns 201.
  GET returns the stored row or 404.
  Target file: `app/main.py`.
  *Accept:* a test that POSTs a session then GETs it back and asserts the
  answers match.

## Phase 2 — Feasibility (the part that is actually ours)

- [x] **2.1 VRAM estimator.** Write EXACTLY ONE function, no others:
  `estimate_vram(params_b, quant, ctx_len, kv_quant)`.
  It MUST return a dict with exactly these two keys:
  `{"weights_gb": float, "kv_gb": float}`, each rounded to 2 decimals.
  Do NOT return a tuple. Do NOT add endpoint, summary or metrics variants -
  a previous attempt wrote six functions and was rejected.
  Arithmetic: bytes-per-param is 0.5 for "Q4", 1.0 for "Q8", 2.0 for "FP16";
  `weights_gb = params_b * 1e9 * bytes_per_param / 1024**3`.
  For KV assume 32 layers, 8 kv_heads, head_dim 128, and bytes-per-element
  1.0 for "q8_0" else 2.0;
  `kv_gb = 2 * 32 * 8 * 128 * ctx_len * bytes_per_elem / 1024**3`.
  Target file: `app/feasibility.py`.
  *Accept:* a test calling
  `feasibility.estimate_vram(9.0, "Q4", 65536, "q8_0")` and asserting
  `weights_gb` is about 4.19 and `kv_gb` is about 4.0, both with
  `assertAlmostEqual(..., delta=0.5)`.

- [x] **2.2 Verdict function.** `verdict(vram_gb, weights_gb, kv_gb)` already
  exists in `app/feasibility.py`. Write ONLY the acceptance test.
  Call the REAL function as `feasibility.verdict(...)`. Do NOT define a local
  `verdict` - a previous attempt redefined it inside the test, asserted
  nothing, and was reverted.
  Assert with `self.assertEqual` that
  `feasibility.verdict(8.0, 2.0, 2.0)["verdict"]` is `"FITS"`,
  `feasibility.verdict(8.0, 4.19, 3.5)["verdict"]` is `"SPILLS"`, and
  `feasibility.verdict(8.0, 9.0, 3.0)["verdict"]` is `"WONT_FIT"`.
  Target file: `app/feasibility.py`.
  *Accept:* three `self.assertEqual` calls on the real function.
- [x] **2.3 Recommendation.** Write EXACTLY ONE function, no others:
  `recommend(goal, vram_gb)`.
  Return a dict with exactly these keys:
  `{"model": str, "quant": str, "method": str, "reason": str}`.
  Table-driven, no model call, no endpoint variants.
  Rules: if `goal == "fine-tune"` and `vram_gb < 12` return model
  `"Qwen3-4B"`, quant `"Q4"`, method `"QLoRA"`. If `goal == "fine-tune"` and
  `vram_gb >= 12` return `"Qwen3-8B"`, `"Q4"`, `"LoRA"`. For any other goal
  return `"Qwen3-4B"`, `"Q4"`, `"inference-only"`.
  The `reason` string MUST contain the substring `"VRAM"`.
  Target file: `app/feasibility.py`.
  *Accept:* a test asserting `feasibility.recommend("fine-tune", 8.0)` returns
  method `"QLoRA"`, model `"Qwen3-4B"`, and that `"VRAM"` is in `reason`.

- [x] **2.4 Rent-instead advice.** Write EXACTLY ONE function, no others:
  `rent_advice(needed_gb)`.
  Return a dict with exactly these keys:
  `{"gpu": str, "vram_gb": int, "usd_per_hour": float, "note": str}`.
  Static table (add a comment saying prices are indicative, RunPod, Aug 2026):
  needed <= 24 gives `"RTX 4090"`, 24, 0.60;
  needed <= 48 gives `"A6000"`, 48, 0.90;
  otherwise `"A100 80GB"`, 80, 1.80.
  No endpoint variants. No network calls.
  Target file: `app/feasibility.py`.
  *Accept:* a test asserting `feasibility.rent_advice(30.0)` returns gpu
  `"A6000"` and a `usd_per_hour` greater than 0.

## Phase 3 — The plan artifact

- [x] **3.1a Markdown plan renderer.** Write EXACTLY ONE function, no others:
  `render_plan(answers, rec, verdict_info)`.
  `answers` is a dict like `{"goal": "fine-tune", "dataset_rows": 5000,
  "kind": "text"}`. `rec` is the dict returned by `feasibility.recommend`
  (keys `model`, `quant`, `method`, `reason`). `verdict_info` is the dict
  returned by `feasibility.verdict` (keys `verdict`, `needed_gb`, `vram_gb`,
  `headroom_gb`).
  Return ONE markdown string, built with an f-string. No model call, no db,
  no network, no endpoint.
  It MUST contain, in this order:
  1. a line `# Training plan`
  2. a line containing `rec["model"]` and a line containing
     `verdict_info["verdict"]`
  3. EXACTLY four headings written as `## Phase 1 - Data`,
     `## Phase 2 - Preprocess`, `## Phase 3 - Train`, `## Phase 4 - Evaluate`
  4. under each of those four headings, ONE line that starts with
     `Exit criterion:` and is followed ON THE SAME LINE by a concrete sentence
     of at least 30 more characters saying how you know that phase is done.
     An empty `Exit criterion:` is a FAILED step - a previous attempt emitted
     four bare labels, passed its test, and was reverted as useless.
  5. somewhere in the body, the value of `answers["goal"]`, the value of
     `rec["method"]`, and the value of `rec["quant"]`. A plan that ignores its
     own inputs is rejected.
  Target file: `app/plan.py`.
  *Accept:* a test calling
  `plan.render_plan({"goal": "fine-tune"}, feasibility.recommend("fine-tune", 8.0),
  feasibility.verdict(8.0, 4.19, 3.5))` and asserting `"Qwen3-4B" in out`,
  `"SPILLS" in out`, `"QLoRA" in out`, `"fine-tune" in out`,
  `out.count("## Phase") == 4`, and that every line in
  `[l for l in out.splitlines() if l.startswith("Exit criterion:")]` has
  `len(l) > 45`, with four such lines.

- [x] **3.1b Plan endpoint.** Add `GET /plan/{session_id}` to `app/main.py`.
  Look the session up with `db.get_intake(session_id)`; return 404 via
  `HTTPException` if it is None. Otherwise call
  `feasibility.recommend(row["answers"].get("goal", ""), 8.0)` and
  `feasibility.verdict(8.0, 4.19, 3.5)`, pass both into
  `plan.render_plan(row["answers"], rec, v)`, and return the resulting string
  as a POSITIONAL argument: `return PlainTextResponse(markdown)`.
  There is no `text=` keyword - `PlainTextResponse(text=...)` raises
  TypeError. The first positional argument is the body.
  The function MUST be annotated `-> PlainTextResponse`, NOT
  `-> dict[str, Any]`. A previous attempt copied the dict annotation from the
  endpoints above it and FastAPI raised ResponseValidationError because the
  body is markdown, not a dict.
  Decorate it `@app.get("/plan/{session_id}", response_class=PlainTextResponse)`.
  Target file: `app/main.py`.
  *Accept:* a test that POSTs `/intake` with
  `{"session_id": "p1", "answers": {"goal": "fine-tune"}}`, then GETs
  `/plan/p1`, asserts status 200 and `"# Training plan" in response.text`,
  and asserts `GET /plan/nope` returns 404.

- [x] **3.2 Mermaid pipeline diagram.** Write EXACTLY ONE function, no others:
  `render_diagram(rec, verdict_info)`.
  `rec` is the dict from `feasibility.recommend` (keys `model`, `quant`,
  `method`, `reason`). `verdict_info` is the dict from `feasibility.verdict`
  (keys `verdict`, `needed_gb`, `vram_gb`, `headroom_gb`).
  Return ONE string, built with an f-string. No model call, no db, no network,
  no endpoint, no HTTP.
  Build the ``` fence as `chr(96) * 3` and NEVER type a literal backtick in
  the code. Backticks inside the generated source collide with the markdown
  fence the output is extracted from, and three attempts were lost to a
  truncated file with an unterminated string.
  Write it as a list of lines joined with a newline. Build EXACTLY these eight
  lines, in this order, and nothing else:

      fence = chr(96) * 3
      lines = [
          f"{fence}mermaid",
          "flowchart LR",
          "    data[Data] --> preprocess[Preprocess]",
          f"    preprocess --> train[Train {rec['model']}]",
          "    train --> eval[Evaluate]",
          f"    eval --> serve[Serve {verdict_info['verdict']}]",
          fence,
      ]
      return "\n".join(lines)

  That is the whole function. Do not add nodes, do not add a verdict node of
  its own, do not put the fence on the same line as an arrow. Node labels must
  contain no parentheses and no quotes - mermaid rejects them.
  Target file: `app/diagram.py`.
  *Accept:* a test assigning
  `out = diagram.render_diagram(feasibility.recommend("fine-tune", 8.0),
  feasibility.verdict(8.0, 4.19, 3.5))` then asserting with `self.assertTrue`
  that `out.startswith(chr(96) * 3 + "mermaid")`, with `self.assertIn` that
  `"flowchart"`, `"Qwen3-4B"` and `"SPILLS"` are in `out`, with
  `self.assertGreaterEqual` that `out.count("-->")` is at least 4, and — this
  one matters — with `self.assertTrue` that
  `out.rstrip().endswith(chr(96) * 3)` and with `self.assertEqual` that
  `out.count(chr(96) * 3)` is exactly 2.
  The test must ALSO use `chr(96) * 3` rather than literal backticks, for the
  same extraction reason.
  A previous attempt left the closing fence off. Its test passed because it
  never checked, and a mermaid block does not render without it.
- [x] **3.3 Plan download.** Add `GET /plan/{session_id}/download` to
  `app/main.py`. Name the function EXACTLY `download_plan`. Do NOT call it
  `get_plan` - that name is already taken by the endpoint from 3.1b, and a
  previous attempt collided with it, wrote no code at all, and then tested a
  route that did not exist. Build the body exactly the way `get_plan` already does -
  `db.get_intake`, 404 via `HTTPException` if None, then
  `feasibility.recommend`, `feasibility.verdict`, `plan.render_plan`.
  Return `PlainTextResponse(markdown, headers={"Content-Disposition":
  "attachment; filename=plan.md"})`. The body is the FIRST POSITIONAL
  argument - there is no `text=` keyword.
  The FIRST line you write MUST be the decorator, on its own line, exactly:
  `@app.get("/plan/{session_id}/download", response_class=PlainTextResponse)`
  A previous attempt emitted the bare `def download_plan(...)` with no
  decorator at all. The function was appended, the route was never registered,
  and every request returned 404.
  The second line is `def download_plan(session_id: str) -> PlainTextResponse:`.
  The last two lines of the function body MUST be exactly these two lines:
  `    headers = {"Content-Disposition": "attachment; filename=plan.md"}`
  `    return PlainTextResponse(markdown, headers=headers)`
  Three attempts returned `PlainTextResponse(markdown)` with no headers at all.
  The response WILL fail its test without that `headers=headers` argument.
  This is the single thing that distinguishes 3.3 from 3.1b - everything else
  in the function is identical to `get_plan`.
  Target file: `app/main.py`.
  *Accept:* a test whose FIRST line is exactly this, and it is NOT optional -
  without it there is no session d1 and the endpoint correctly returns 404:
  `self.client.post("/intake", json={"session_id": "d1", "answers": {"goal": "fine-tune"}})`
  then `resp = self.client.get("/plan/d1/download")`, then asserts
  `resp.status_code` is 200, asserts with `self.assertIn` that `"attachment"`
  is in `resp.headers["content-disposition"]`, and asserts `"# Training plan"`
  is in `resp.text`.
  Do NOT post to `/api/runs` - that creates a run, not an intake session, and
  a previous attempt used a run id as a session id and got a 404.
- [x] **4.1a Job storage helpers.** Add THREE new functions to `app/db.py`.
  You may only ADD functions - you cannot edit `init_db`, so the table must be
  created by your own code. Copy the exact shape of `ensure_intake_table`,
  `create_intake` and `get_intake`, which already work.
  1. `ensure_jobs_table()` runs, inside `with session() as connection:`,
     `CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,
     intake_id TEXT, cmd TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT,
     exit_code INTEGER, log_path TEXT)`
  2. `create_job(intake_id, cmd)` calls `ensure_jobs_table()` FIRST, inserts a
     row with just `intake_id` and `cmd`, then selects that row back and
     returns it as a dict. Status comes from the column default, so do NOT
     pass a status.
  3. `get_job(job_id)` calls `ensure_jobs_table()` FIRST, selects the row with
     that id, and returns it as a dict, or None if there is no row.
  Name them EXACTLY those three names. Do not add a list, update or delete
  helper - a previous step wrote six functions and was rejected.
  Target file: `app/db.py`.
  *Accept:* a test assigning
  `job = db.create_job("s1", "python -c \"print(1)\"")` then asserting with
  `self.assertEqual` that `job["status"]` is `"queued"` and `job["cmd"]` is
  `"python -c \"print(1)\""`, then assigning `fetched = db.get_job(job["id"])`
  and asserting with `self.assertEqual` that `fetched["cmd"]` equals
  `job["cmd"]`, and with `self.assertIsNone` that `db.get_job(99999)` is None.
  No HTTP - do NOT use `self.client`.
  READ THIS LAST, IT IS THE ONE THING THAT KEEPS GOING WRONG:
  the last two lines of `get_job` must be exactly
  `    out = dict(row)` then `    return out`.
  Three attempts wrote `out["answers"] = json.loads(out["answers"])` between
  them, copied from `get_intake`. The `jobs` table has NO `answers` column and
  stores NO JSON, so that line raises `KeyError: 'answers'` every time.
  `create_job` ends the same way: `return dict(row)`, nothing decoded.
  This is the ONLY difference between these helpers and the intake ones.

- [x] **4.1b Job enqueue endpoint.** Add `POST /jobs` to `app/main.py`.
  Name the function EXACTLY `enqueue_job`. Do NOT reuse any existing name.
  The FIRST line you write MUST be the decorator, on its own line, exactly:
  `@app.post("/jobs", status_code=201)`
  The second line is `def enqueue_job(payload: dict[str, Any]) -> dict[str, Any]:`.
  The body calls `db.create_job(payload.get("intake_id"), payload["cmd"])` and
  returns that dict directly. This one DOES return a dict, so the
  `-> dict[str, Any]` annotation is correct here.
  Target file: `app/main.py`.
  *Accept:* a test assigning
  `resp = self.client.post("/jobs", json={"intake_id": "s1", "cmd": "echo hi"})`
  then asserting with `self.assertEqual` that `resp.status_code` is 201, that
  `resp.json()["status"]` is `"queued"`, and that `resp.json()["cmd"]` is
  `"echo hi"`.

- [x] **4.2a Job state helpers.** Add EXACTLY TWO new functions to `app/db.py`.
  Name them EXACTLY `next_queued_job` and `finish_job`. Do not add others.
  1. `next_queued_job()` calls `ensure_jobs_table()` FIRST, then selects the
     OLDEST row whose status is `'queued'`
     (`SELECT * FROM jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1`)
     and returns it as a dict, or None if there is no such row.
  2. `finish_job(job_id, exit_code, log_path)` calls `ensure_jobs_table()`
     FIRST, then runs
     `UPDATE jobs SET status = 'done', finished_at = CURRENT_TIMESTAMP,
     exit_code = ?, log_path = ? WHERE id = ?`
     and returns the updated row as a dict.
  Target file: `app/db.py`.
  *Accept:* a test that assigns
  `job = db.create_job("s1", "echo hi")`, then
  `nxt = db.next_queued_job()` and asserts with `self.assertEqual` that
  `nxt["id"]` equals `job["id"]`, then assigns
  `done = db.finish_job(job["id"], 0, "logs/1.log")` and asserts with
  `self.assertEqual` that `done["status"]` is `"done"` and `done["exit_code"]`
  is `0`, then asserts with `self.assertIsNone` that `db.next_queued_job()` is
  None because the only job is no longer queued.
  No HTTP - do NOT use `self.client`.
  READ THIS LAST, IT IS THE ONE THING THAT KEEPS GOING WRONG:
  the `jobs` table has NO `answers` column and stores NO JSON. Both functions
  end with `return dict(row)` and nothing decoded. Do NOT copy the
  `out["answers"] = json.loads(out["answers"])` line from `get_intake`.

- [x] **4.2b Local runner.** Create `app/runner.py` with EXACTLY ONE function,
  no others: `run_next_job(timeout=30)`.
  Behaviour, in order:
  1. `job = db.next_queued_job()`. If it is None, return None immediately.
  2. Build the log path: `logs_dir = Path(__file__).resolve().parents[1] / "logs"`,
     then `logs_dir.mkdir(parents=True, exist_ok=True)`, then
     `log_path = logs_dir / f"job_{job['id']}.log"`.
  3. Run the command with
     `subprocess.run(job["cmd"], shell=True, capture_output=True, text=True,
     timeout=timeout)`.
  4. Write `result.stdout + result.stderr` to `log_path` with
     `encoding="utf-8"`.
  5. Return `db.finish_job(job["id"], result.returncode, str(log_path))`.
  Wrap step 3 in `try/except subprocess.TimeoutExpired` and on timeout write
  the text `TIMEOUT` to the log and call `db.finish_job(job["id"], -1, str(log_path))`.
  Import `subprocess`, `Path` from `pathlib`, and `db` via `from app import db`.
  No endpoint, no FastAPI, no threading, no queue module.
  Target file: `app/runner.py`.
  *Accept:* a test that assigns
  `job = db.create_job("s1", "python -c \"print(1)\"")`, then
  `done = runner.run_next_job()`, then asserts with `self.assertEqual` that
  `done["exit_code"]` is `0` and `done["status"]` is `"done"`, then assigns
  `text = Path(done["log_path"]).read_text(encoding="utf-8")` and asserts with
  `self.assertIn` that `"1"` is in `text`, and finally asserts with
  `self.assertIsNone` that `runner.run_next_job()` is None because the queue
  is now empty.
  READ THIS LAST: `run_next_job` takes NO required arguments. Call it as
  `runner.run_next_job()` with empty parentheses. It reads the job from the
  database itself - do NOT pass it a job, an id, or a cmd.

  > **CORRECTION — do not build step 2 as written above. It is the source of a
  > real defect, fixed in `b024da4`.**
  >
  > The line `log_path = logs_dir / f"job_{job['id']}.log"` names a log file
  > after the job id and nothing else. A job id is not a name, it is a counter,
  > and `AUTOINCREMENT` restarts it at 1 for every fresh database — so
  > `logs/job_1.log` is a path that every database on the machine claims. The
  > first job of a database that has just been reset writes over, or appends
  > onto, the log of some earlier database's first job.
  >
  > This is a product defect and not only a test problem. A user who deletes
  > `ml_harness.db` and starts again gets job 1 back, and its log arrives
  > holding a stranger's output. It showed up first as an intermittent test
  > failure, which is the same defect seen from the other side: the suite gave
  > every test class its own temporary `db.DB_PATH` but left `logs/` shared at
  > the repo root, so every test's first job was id 1 and whichever test
  > finished last owned the file. `scripts/flake_hunt.py` captured it on run 2
  > of 12, and the captured log read `hello-4-3\nkind=train\n\nTIMEOUT\n` — the
  > `printer` fixture's output sitting inside the `halting` job's log. Two
  > jobs, one file.
  >
  > The right shape is to key the path on something that does not repeat. A
  > database now mints its own identity (`db.get_instance()`, a uuid), and a
  > job's artifacts live together underneath it:
  >
  > ```
  > runs/<instance>/job_<id>/job.json    # what the job was asked to do
  > runs/<instance>/job_<id>/job.log     # what it said while doing it
  > ```
  >
  > built through `jobspec.run_dir_for(job_id)` and
  > `jobspec.log_path_for(job_id)` rather than assembled at the call site, so
  > there is one place that knows the layout. Two databases that both mint job
  > 1 cannot name the same directory. The flat `logs/` folder is gone; a job's
  > input and its output are in one place rather than two, and only one of them
  > was ever isolated. `tests/support.py` closes the test-side half with
  > `sandbox()`, which hands a test its database, its recipes and its artifact
  > root together, because isolating one of the three and forgetting another is
  > how this arrived.
  >
  > Two smaller notes on the same step, both fixed later and both worth seeing
  > before copying it: step 3's `shell=True` was an unauthenticated
  > remote-execution hole and jobs are argv lists now (`app/jobspec.py`), and
  > the *Accept* test's `self.assertIn("1", text)` is a check an appended log
  > passes just as happily as a correct one — which is why the collision above
  > survived it.

- [x] **4.3 Log tail endpoint.** Add `GET /jobs/{job_id}/log` to `app/main.py`.
  Name the function EXACTLY `job_log`. Do NOT reuse any existing name.
  The FIRST line you write MUST be the decorator, on its own line, exactly:
  `@app.get("/jobs/{job_id}/log", response_class=PlainTextResponse)`
  The second line is exactly:
  `def job_log(job_id: int, tail: int = 200) -> PlainTextResponse:`
  Body, in order:
  1. `job = db.get_job(job_id)`; if it is None raise
     `HTTPException(status_code=404, detail="job not found")`.
  2. If `job["log_path"]` is falsy, return `PlainTextResponse("")`.
  3. `path = Path(job["log_path"])`; if `not path.exists()` return
     `PlainTextResponse("")`.
  4. `lines = path.read_text(encoding="utf-8").splitlines()`
  5. `return PlainTextResponse("\n".join(lines[-tail:]))`
  Annotate it `-> PlainTextResponse`, NOT `-> dict[str, Any]`.
  Target file: `app/main.py`.
  *Accept:* a test that assigns
  `job = db.create_job("s1", "python -c \"print(1)\"")`, then
  `done = runner.run_next_job()`, then
  `resp = self.client.get(f"/jobs/{job['id']}/log")` and asserts with
  `self.assertEqual` that `resp.status_code` is 200 and with `self.assertIn`
  that `"1"` is in `resp.text`, then asserts with `self.assertEqual` that
  `self.client.get("/jobs/99999/log").status_code` is 404.
  READ THIS LAST: the query parameter is `tail`, declared as a plain default
  argument `tail: int = 200` in the signature. Do NOT import or use `Query`,
  and do NOT make it part of the URL path. The path has exactly one parameter,
  `job_id`.
  AND READ THIS TOO, IT IS WHAT KEEPS FAILING: the test's first two lines are
  NOT optional. Three attempts referenced `job` without ever creating it,
  which is an UnboundLocalError. Write these two lines FIRST, with NO leading
  spaces of your own:
  `job = db.create_job("s1", 'python -c "print(1)"')`
  `done = runner.run_next_job()`
  Every line you write starts at column zero. Python owns the indentation.
  Only then may you use `job["id"]`. `runner` is already importable as
  `from app import runner` in the scaffold.

## Phase 5 — Web UI

- [x] **5.1 Intake page.** Add `GET /ui/intake` to `app/main.py`.
  Name the function EXACTLY `intake_page`. Do NOT reuse an existing name.
  The FIRST line you write MUST be the decorator, on its own line, exactly:
  `@app.get("/ui/intake", response_class=HTMLResponse)`
  The second line is exactly `def intake_page() -> HTMLResponse:`.
  Body, in order:
  1. `questions = intake_questions()` - call the existing function directly,
     do NOT make an HTTP request to your own app.
  2. Build a list of HTML strings. For EACH question append
     `f'<label>{q["prompt"]}<input name="{q["id"]}" type="text"></label>'`.
  3. Join them and wrap in a form:
     `html = "<html><body><h1>Intake</h1><form method='post' action='/intake'>"
     + "".join(fields) + "<button type='submit'>Submit</button></form></body></html>"`
  4. `return HTMLResponse(html)`
  Annotate it `-> HTMLResponse`, NOT `-> dict[str, Any]`. `HTMLResponse` is
  already imported in main.py.
  Target file: `app/main.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `resp = self.client.get("/ui/intake")`
  `questions = self.client.get("/intake/questions").json()`
  then asserts with `self.assertEqual` that `resp.status_code` is 200, with
  `self.assertEqual` that `resp.text.count("<input")` equals `len(questions)`,
  and with `self.assertIn` that `"<form"` is in `resp.text`.
  READ THIS LAST: the page must contain EXACTLY one `<input` per question, so
  the count assertion is the real check. Do not add a hidden input, a search
  box, or a CSRF field - any extra `<input` breaks it.

- [x] **5.2 Plan page.** Add `GET /ui/plan/{session_id}` to `app/main.py`.
  Name the function EXACTLY `plan_page`. Do NOT reuse an existing name.
  The FIRST line you write MUST be the decorator, on its own line, exactly:
  `@app.get("/ui/plan/{session_id}", response_class=HTMLResponse)`
  The second line is exactly `def plan_page(session_id: str) -> HTMLResponse:`.
  Body, in order:
  1. `row = db.get_intake(session_id)`; if None raise
     `HTTPException(status_code=404, detail="session not found")`.
  2. `rec = feasibility.recommend(row["answers"].get("goal", ""), 8.0)`
  3. `v = feasibility.verdict(8.0, 4.19, 3.5)`
  4. `markdown = plan.render_plan(row["answers"], rec, v)`
  5. `mermaid = diagram.render_diagram(rec, v)`
  6. `html = f"<html><body><h1>Plan</h1><pre>{markdown}</pre><pre>{mermaid}</pre></body></html>"`
  7. `return HTMLResponse(html)`
  Annotate it `-> HTMLResponse`, NOT `-> dict[str, Any]`.
  Target file: `app/main.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `self.client.post("/intake", json={"session_id": "u1", "answers": {"goal": "fine-tune"}})`
  `resp = self.client.get("/ui/plan/u1")`
  then asserts with `self.assertEqual` that `resp.status_code` is 200, with
  `self.assertIn` that `"# Training plan"` is in `resp.text`, with
  `self.assertIn` that `"flowchart"` is in `resp.text`, and with
  `self.assertEqual` that `self.client.get("/ui/plan/nope").status_code` is 404.
  READ THIS LAST: the page embeds BOTH the markdown plan and the mermaid
  diagram, each in its own `<pre>` block. A page with only one of them fails.

- [x] **5.3a List jobs helper.** Add EXACTLY ONE new function to `app/db.py`,
  named EXACTLY `list_jobs`. It calls `ensure_jobs_table()` FIRST, runs
  `SELECT * FROM jobs ORDER BY id DESC`, and returns `[dict(r) for r in rows]`.
  Copy the shape of `list_hardware_profiles`, which already does exactly this
  for another table.
  Target file: `app/db.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `db.create_job("s1", "echo one")`
  `db.create_job("s2", "echo two")`
  `jobs = db.list_jobs()`
  then asserts with `self.assertEqual` that `len(jobs)` is 2 and that
  `jobs[0]["cmd"]` is `"echo two"` because the order is newest first, and with
  `self.assertEqual` that `jobs[1]["cmd"]` is `"echo one"`.
  No HTTP - do NOT use `self.client`.
  READ THIS LAST: the `jobs` table has NO `answers` column and stores NO JSON.
  Return `[dict(r) for r in rows]` with nothing decoded.

- [x] **5.3b Jobs page.** Add `GET /ui/jobs` to `app/main.py`.
  Name the function EXACTLY `jobs_page`. Do NOT reuse an existing name.
  `db.list_jobs()` already exists from 5.3a, call it directly.
  The FIRST line you write MUST be the decorator:
  `@app.get("/ui/jobs", response_class=HTMLResponse)`
  The second line is exactly `def jobs_page() -> HTMLResponse:`.
  Body: `jobs = db.list_jobs()`, then build one table row per job as
  `f'<tr><td>{j["id"]}</td><td>{j["status"]}</td>'
  f'<td><a href="/jobs/{j["id"]}/log">log</a></td></tr>'`,
  then wrap them: `html = "<html><body><h1>Jobs</h1><table>" + "".join(rows)
  + "</table></body></html>"`, then `return HTMLResponse(html)`.
  Annotate it `-> HTMLResponse`.
  Target file: `app/main.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `db.create_job("s1", "echo one")`
  `db.create_job("s2", "echo two")`
  `resp = self.client.get("/ui/jobs")`
  then asserts with `self.assertEqual` that `resp.status_code` is 200 and that
  `resp.text.count("<tr>")` equals 2, and with `self.assertIn` that
  `"/jobs/1/log"` is in `resp.text`.
  READ THIS LAST, THIS IS WHAT KEEPS FAILING: the test is exactly these six
  lines, at column zero, and nothing else. Four attempts copied the
  `{j["id"]}` template out of the implementation above into the test, where
  `j` does not exist, which is an UnboundLocalError. There is no loop and no
  `j` anywhere in the test:
  `db.create_job("s1", "echo one")`
  `db.create_job("s2", "echo two")`
  `resp = self.client.get("/ui/jobs")`
  `self.assertEqual(resp.status_code, 200)`
  `self.assertEqual(resp.text.count("<tr>"), 2)`
  `self.assertIn("/jobs/1/log", resp.text)`
  Also: `list_jobs` returns EVERY job, so do not paginate and do not add a
  header `<tr>` - a header row would make the count 3 and fail.

## Phase 6 — Registry and data (only after 1-5 are green)

- [x] **6.1 Model registry helpers.** Add EXACTLY THREE new functions to
  `app/db.py`, named EXACTLY `ensure_models_table`, `create_model` and
  `list_models`. Copy the shape of the jobs helpers directly above them.
  1. `ensure_models_table()` runs, inside `with session() as connection:`,
     `CREATE TABLE IF NOT EXISTS models (id INTEGER PRIMARY KEY AUTOINCREMENT,
     name TEXT NOT NULL, base TEXT, quant TEXT, method TEXT, path TEXT,
     notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`
  2. `create_model(name, base, quant, method, path, notes)` calls
     `ensure_models_table()` FIRST, inserts a row, selects it back, returns
     `dict(row)`.
  3. `list_models()` calls `ensure_models_table()` FIRST, runs
     `SELECT * FROM models ORDER BY id DESC`, returns `[dict(r) for r in rows]`.
  Target file: `app/db.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `m = db.create_model("qwen3-4b-q4", "Qwen3-4B", "Q4", "QLoRA", "/models/q4", "fits 8GB")`
  `self.assertEqual(m["name"], "qwen3-4b-q4")`
  `self.assertEqual(m["quant"], "Q4")`
  `models = db.list_models()`
  `self.assertEqual(len(models), 1)`
  `self.assertEqual(models[0]["method"], "QLoRA")`
  No HTTP - do NOT use `self.client`.
  READ THIS LAST, THIS IS WHAT WENT WRONG BEFORE: a previous attempt ticked
  this step with a test that called `db.create_run` - a function that already
  existed and has nothing to do with a model registry. The test MUST call
  `db.create_model` and `db.list_models` by name. The `models` table has NO
  `answers` column and stores NO JSON: return `dict(row)` with nothing decoded.
- [x] **6.2a Dataset registry helpers.** Add EXACTLY THREE new functions to
  `app/db.py`, named EXACTLY `ensure_datasets_table`, `create_dataset` and
  `list_datasets`. Copy the shape of the models helpers directly above them.
  1. `ensure_datasets_table()` runs, inside `with session() as connection:`,
     `CREATE TABLE IF NOT EXISTS datasets (id INTEGER PRIMARY KEY AUTOINCREMENT,
     path TEXT NOT NULL, rows INTEGER, format TEXT, split TEXT, notes TEXT,
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`
  2. `create_dataset(path, rows, format, split, notes)` calls
     `ensure_datasets_table()` FIRST, inserts a row, selects it back, returns
     `dict(row)`.
  3. `list_datasets()` calls `ensure_datasets_table()` FIRST, runs
     `SELECT * FROM datasets ORDER BY id DESC`, returns `[dict(r) for r in rows]`.
  Target file: `app/db.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `d = db.create_dataset("/data/train.csv", 5000, "csv", "train", "cleaned")`
  `self.assertEqual(d["path"], "/data/train.csv")`
  `self.assertEqual(d["rows"], 5000)`
  `sets = db.list_datasets()`
  `self.assertEqual(len(sets), 1)`
  `self.assertEqual(sets[0]["split"], "train")`
  No HTTP - do NOT use `self.client`.
  READ THIS LAST: every one of the three functions uses
  `with session() as connection:` - `connection` does not exist outside that
  block and a previous step wrote three attempts that used it bare. The
  `datasets` table has NO `answers` column and stores NO JSON: return
  `dict(row)` with nothing decoded.
  AND THIS, WHICH IS WHY IT KEEPS FAILING: the test is those SIX lines and
  NOTHING ELSE. Two attempts created a second dataset and added
  `self.assertEqual(sets[1]["split"], "test")`, which is wrong because
  `list_datasets` orders newest first, so `sets[1]` is the older row. Create
  ONE dataset. Add no extra assertions. Six lines, stop.

- [x] **6.2b Data quality report.** Create `app/dataquality.py` with EXACTLY
  ONE function, no others: `data_quality_report(path)`.
  It reads a CSV with the stdlib `csv` module and returns a dict with exactly
  these three keys:
  `{"rows": int, "null_rate": dict, "duplicates": int}`.
  Behaviour, in order:
  1. `import csv` and `from pathlib import Path` at the top of the file.
  2. If the file does not exist, return
     `{"rows": 0, "null_rate": {}, "duplicates": 0}`.
  3. Read it with `csv.DictReader`, collecting rows into a list.
  4. `rows` is `len(records)`.
  5. `null_rate` maps each column name to the fraction of records where the
     value is an empty string, rounded to 2 decimals. Use the reader's
     `fieldnames` for the column list. If there are no records, use `0.0`.
  6. `duplicates` is the number of records whose full tuple of values has been
     seen before, i.e. `len(records) - len(set_of_distinct_value_tuples)`.
  No db, no network, no pandas, no endpoint.
  Target file: `app/dataquality.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `p = Path(self.temp.name) / "d.csv"`
  `p.write_text("a,b\n1,x\n2,\n1,x\n", encoding="utf-8")`
  `r = dataquality.data_quality_report(str(p))`
  `self.assertEqual(r["rows"], 3)`
  `self.assertEqual(r["duplicates"], 1)`
  `self.assertAlmostEqual(r["null_rate"]["b"], 0.33, delta=0.01)`
  READ THIS LAST: `self.temp` is the TemporaryDirectory already created in
  setUp, so write the CSV inside it. The three rows are `1,x` then `2,` then
  `1,x`: three records, one duplicate of the first, and column `b` empty in
  one of three records so its null rate is 0.33.

## Phase 7 — from the vault's real backlog (`TASKS.md`)

These come from `Projects/ml-harness/TASKS.md`, which `ACTIVE - ML Harness.md`
names as the lane's actual task list. The earlier phases were a plan I wrote;
this is Max's.

- [x] **7.1 CSV export for one run and its metrics.** Write EXACTLY ONE
  function, no others: `run_to_csv(run_id)`.
  Return ONE string of CSV text. Use the stdlib `csv` module with
  `io.StringIO`. No file writes, no db writes, no endpoint, no pandas.
  Behaviour, in order:
  1. `metrics = db.metrics_for(run_id)`
  2. Create `buf = io.StringIO()` and
     `writer = csv.writer(buf)`.
  3. Write the header row exactly: `["step", "name", "value"]`
  4. For each metric in `metrics`, write
     `[m["step"], m["name"], m["value"]]`
  5. `return buf.getvalue()`
  Import `csv`, `io`, and `from app import db` at the top of the file.
  Target file: `app/export.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `run = db.create_run("demo", "{}")`
  `db.add_metric(run["id"], 1, "loss", 0.5)`
  `db.add_metric(run["id"], 2, "loss", 0.25)`
  `text = export.run_to_csv(run["id"])`
  `self.assertIn("step,name,value", text)`
  `self.assertIn("1,loss,0.5", text)`
  `self.assertEqual(len(text.strip().splitlines()), 3)`
  READ THIS LAST: three lines total in the output - one header plus two
  metrics. Write no extra columns and no extra rows. `metrics_for` already
  exists in `app/db.py`; call it, do not write your own query.

- [x] **7.2 Loss curve teaching panel.** Write EXACTLY ONE function, no
  others: `explain_loss(run_id)`.
  Return a dict with exactly these three keys:
  `{"observed": str, "heuristic": str, "points": int}`.
  Read the data with `db.metrics_for(run_id, "loss")` - that function already
  exists, do not write your own query.
  Behaviour, in order:
  1. `points` is the number of loss metrics returned.
  2. If `points` is 0, return
     `{"observed": "no loss recorded", "heuristic": "", "points": 0}`.
  3. `first` is the value of the earliest metric, `last` the value of the
     latest. Build `observed` as an f-string stating both, rounded to 3
     decimals, and the number of points. It describes ONLY recorded values.
  4. `heuristic` is a rule-of-thumb string that MUST begin with the exact
     prefix `Heuristic: `. If `last < first` say the loss is decreasing; if
     `last > first` say it is increasing and may indicate too high a learning
     rate; otherwise say it is flat.
  No model call, no network, no endpoint.
  Target file: `app/teach.py`.
  *Accept:* a test whose lines, each starting at column zero, are:
  `run = db.create_run("t", "{}")`
  `db.add_metric(run["id"], 1, "loss", 0.9)`
  `db.add_metric(run["id"], 2, "loss", 0.4)`
  `out = teach.explain_loss(run["id"])`
  `self.assertEqual(out["points"], 2)`
  `self.assertTrue(out["heuristic"].startswith("Heuristic: "))`
  `self.assertIn("0.9", out["observed"])`
  READ THIS LAST: `observed` states measurements only and `heuristic` is the
  only place an interpretation may appear, which is why it carries the
  `Heuristic: ` prefix. That separation is the whole point of the task.

## Out of scope for now

Hosted VMs, multi-user auth, cloud training, RL environment manager, distributed
anything. Revisit once phases 1-5 are green and one real user has run it.
