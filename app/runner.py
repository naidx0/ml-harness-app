import json
import os
import subprocess
import threading

from app import config, db, jobspec, security
from app.jobspec import JobRejected, JobSpec


#: Exit code for a job the runner refused to start. Distinct from -1 (timeout)
#: and from any code a real process can return, so "we would not run this" is
#: never confused with "it ran and failed".
REJECTED = -2

#: Where the reason goes when the refusal is that this database's instance
#: identity cannot name a directory. Normally a refusal is written into the
#: job's own run directory - but that directory is named after the identity, so
#: when the identity is the broken thing there is no such place to write to.
#:
#: A fixed literal, never the rejected value: whatever nonsense is in the
#: database stays out of the filesystem and appears only as text inside the
#: log. It also cannot be mistaken for a real run directory, because
#: `db.get_instance()` mints `uuid4().hex` - thirty-two characters of `[0-9a-f]`
#: - and this word is neither that length nor spelled in that alphabet. Two
#: databases whose identity is unreadable do share this path, and that is the
#: honest answer rather than a gap: an unreadable identity is precisely the
#: state in which two databases cannot be told apart. Nothing is lost to the
#: sharing that was not already lost, because no job ever runs down this path,
#: so the file holds a refusal reason and never a job's output.
UNIDENTIFIED = "unidentified"


class _Completed:
    """Just enough of CompletedProcess for the caller."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _process_group_kwargs():
    """Own the process tree on both platforms.

    Extracted verbatim from `_run_bounded` so the streaming runner below gets
    exactly the same ownership rather than a second, subtly different copy.
    """
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _run_bounded(argv, timeout, cwd=None, env=None):
    """Run `argv` and actually stop it at `timeout`.

    `subprocess.run(shell=True, capture_output=True, timeout=N)` does NOT
    bound the job. On timeout it kills the shell, but the grandchild keeps
    running and keeps the stdout pipe open, so cleanup blocks until the
    grandchild exits on its own. Measured: a 2 second timeout on a 30 second
    sleep took 30.1 seconds and still reported exit -1, so every assertion
    about the timeout passed while the bound did nothing.

    A job runner whose timeout does not bound anything is broken at the one
    thing it exists to do: a runaway job holds the single slot forever.

    So own the process tree. Kill the whole group, not just the shell.

    One thing changed here since that measurement, and only one: `cmd` was a
    string run with `shell=True` and is now an argv list run with
    `shell=False`, with `cwd` and `env` supplied by the caller. The shell was
    an unauthenticated remote-code-execution hole (`docs/ARCHITECTURE.md`
    section 8) and it is also the thing that made the grandchild problem this
    docstring describes possible in the first place - with no shell there is no
    intermediate process, so the group ownership below now has strictly less
    work to do rather than more. The bound, the group and the tree kill are
    unchanged, and `tests/test_runner_failure_paths.py` still measures the
    clock rather than trusting the exit code.
    """
    kwargs = _process_group_kwargs()

    proc = subprocess.Popen(
        argv, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd, env=env, **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout)
        return _Completed(proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        # drain briefly so the handles close; the tree is already dying
        try:
            proc.communicate(timeout=5)
        except Exception:                      # noqa: BLE001
            pass
        raise


def _kill_tree(proc):
    """Kill the process and everything it spawned."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.kill()
    except Exception:                          # noqa: BLE001
        pass


def _run_streaming(argv, timeout, log_path, cwd=None, env=None):
    """Run `argv`, writing output to `log_path` as it arrives.

    `_run_bounded` uses `communicate()`, which returns everything at once when
    the process is already over. That is correct and it is also useless for a
    live pane: a six-hour training run would show nothing for six hours and
    then show everything, and a user watching a job that is silently stuck
    cannot tell it apart from a job that is working.

    This is a sibling of `_run_bounded`, not a rewrite of it. The process-group
    ownership and `_kill_tree` are the same code, and the bound is enforced the
    same way - `proc.wait(timeout=...)`, then kill the tree. The difference is
    only where the bytes go: a reader thread appends each line to the log file
    and flushes, so the file on disk is the live view and any reader can tail
    it. The kill is what unblocks the reader, which is why the bound still
    holds with a pipe open: `readline` returns EOF when the tree dies.

    stderr is merged into stdout deliberately. Interleaving is what a person
    reading a log wants - a traceback belongs next to the line that caused it,
    not in a second file with no timestamps to reconcile against.

    Returns the exit code. Raises `subprocess.TimeoutExpired` like its sibling,
    with whatever the job managed to print already on disk.
    """
    kwargs = _process_group_kwargs()

    proc = subprocess.Popen(
        argv, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        cwd=cwd, env=env, **kwargs)

    log_file = open(log_path, "w", encoding="utf-8")

    def pump():
        try:
            for line in proc.stdout:
                log_file.write(line)
                log_file.flush()
        except (ValueError, OSError):
            # The tree was killed mid-read, or the file is already closed
            # because we timed out and moved on. Either way the process is
            # dying and there is nothing left worth recording.
            pass

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise
    finally:
        # The reader is what holds the pipe open, so it is joined before the
        # handles are closed. After a kill it returns immediately: the tree is
        # gone, so `readline` sees EOF. Popen is not used as a context manager
        # here because its `__exit__` waits for the process, which is the one
        # thing this function exists to bound.
        reader.join(timeout=5)
        try:
            proc.stdout.close()
        except (OSError, ValueError):
            pass
        if not log_file.closed:
            log_file.close()
    return proc.returncode


def spec_for(job):
    """The `JobSpec` stored on a job row.

    A row written before the structured job contract existed has no recipe the
    harness knows, so it is refused here rather than executed. That is the
    whole migration story for old rows: they are readable history and they are
    not runnable.
    """
    try:
        config = json.loads(job["config_json"] or "{}")
    except (TypeError, ValueError):
        raise JobRejected("job config is not valid JSON")
    if not isinstance(config, dict):
        raise JobRejected("job config is not an object")
    return JobSpec(recipe=job["recipe"], kind=job["kind"], config=config)


def _refusal_log_path(job_id):
    """Where a refused job's reason is written.

    The job's own run directory, in every case where that directory can be
    named. When it cannot - the instance identity that names it is missing or
    corrupt - the reason goes to the quarantine directory instead, because a
    refusal nobody can read is not much better than no refusal at all.
    """
    try:
        return jobspec.log_path_for(job_id)
    except JobRejected:
        return jobspec.log_path_for(job_id, instance=UNIDENTIFIED)


def _record_refusal(job, reason):
    """Finish a job the runner will not start, with the reason on disk.

    The row is the part that must always be written: it is what takes the job
    out of the queue and frees the single slot. The log is what makes the
    refusal legible, so it is attempted first and its failure is not allowed to
    become this function's failure - raising here would jam the slot, which is
    the one outcome the refusal path exists to prevent.
    """
    log_path = _refusal_log_path(job["id"])
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"REJECTED: {reason}\n")
    except OSError:
        return db.finish_job(job["id"], REJECTED, None)
    return db.finish_job(job["id"], REJECTED, str(log_path))


def run_next_job(timeout=30, stream=True):
    job = db.next_queued_job()
    if job is None:
        return None

    # Refusals are recorded, not raised. A job the runner will not start is a
    # finished job with a reason in its log; leaving it queued would jam the
    # single slot behind a row that can never succeed.
    #
    # The run directory is derived *inside* this block, and that placement is
    # load-bearing. Deriving it validates the instance identity that names it
    # (`jobspec.runs_root_for`), and an identity that cannot be a directory
    # name is refused there with `JobRejected` like any other bad input. While
    # those two lines sat above this block, that refusal was the one kind that
    # escaped: it left the row queued, so `next_queued_job` handed the same
    # unstartable job to every later invocation and the single slot was jammed
    # for good - the exact failure this comment exists to prevent, arriving
    # through the only line that was outside the protection it describes.
    #
    # Since 2026-09-02 `next_queued_job` CLAIMS the row it hands out, so that
    # historical jam would today present as its opposite: an escaping refusal
    # would leave the row `running` and it would be skipped rather than
    # retried forever. The placement below is still what makes it moot - the
    # refusal is recorded as a finished job either way - and the block is kept
    # where it is for that reason and not for the old one.
    try:
        # One job is one directory. The log used to live in a flat `logs/`
        # folder at the repo root, keyed on the job id alone - and a job id
        # restarts at 1 for every fresh database, so `logs/job_1.log` was a
        # name that two unrelated runs both held. `run_dir_for` keys on the
        # database's own identity now (`app/jobspec.py`), so this path cannot
        # be the same place twice, and the log sits with the `job.json` that
        # produced it.
        run_dir = jobspec.run_dir_for(job["id"])
        log_path = jobspec.log_path_for(job["id"])

        # This call owns this log from here down, and the truncation is what
        # makes that true rather than merely intended. It happens before
        # anything that runs can fail and on every path that reaches a run, so
        # the append in the `TimeoutExpired` handler below can only ever add to
        # bytes this call wrote. Appending to a file some earlier call left
        # behind is precisely how a timed-out job's log came to hold a
        # different job's output.
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")

        spec = spec_for(job)
        jobspec.prepare_run_dir(spec, run_dir)
        argv = jobspec.resolve_argv(spec, run_dir)
    except JobRejected as exc:
        return _record_refusal(job, exc)

    # A recipe reports its metrics back through the engine's own API, so it
    # needs the engine's address and a token.
    #
    # `client_token()`, never `current_token()`. The runner is invoked as its
    # own process - "the runner is invoked separately and processes one queued
    # job per invocation" - so `current_token()` would mint a fresh token that
    # this process accepts and the *engine* has never heard of. Caught by
    # actually running a job against a live engine, which answered 401: the
    # unit tests could not see it, because in-process they share a token by
    # accident. `client_token()` reads the same `engine.json` every other local
    # client reads, so both arrangements work.
    #
    # This hands the job the *engine's* token, which is more authority than a
    # training job needs. A per-job token scoped to that job's run is the right
    # answer and arrives with the supervisor in M7. Named here so it is a known
    # debt and not a surprise.
    token = security.client_token()
    extra = {"MLH_PORT": str(config.PORT)}
    if token:
        extra["MLH_TOKEN"] = token
    env = jobspec.job_env(extra)

    try:
        if stream:
            exit_code = _run_streaming(
                argv, timeout, log_path, cwd=run_dir, env=env)
        else:
            result = _run_bounded(argv, timeout, cwd=run_dir, env=env)
            # "w", not "a": job ids restart at 1 for every fresh database, so
            # an append leaves one log file holding the output of several
            # unrelated runs. The generated test only asserted `"1" in text`,
            # which an append passes.
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write(result.stdout + result.stderr)
            exit_code = result.returncode
    except subprocess.TimeoutExpired:
        # Append rather than truncate: whatever the job printed before it was
        # killed is the most useful thing on disk for working out why it hung,
        # and the old implementation threw it away.
        #
        # Safe to append only because of the truncation at the top of this
        # function. Without it this line was the bug: on the buffered path
        # nothing in this call had written the file at all, so "a" inherited
        # whatever the previous holder of this path had left, and the log of a
        # job that timed out at line one could arrive holding a stranger's
        # complete output followed by the word TIMEOUT.
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write("\nTIMEOUT\n")
        return db.finish_job(job["id"], -1, str(log_path))
    except OSError as exc:
        # The interpreter or entrypoint could not be executed at all.
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"FAILED TO START: {exc}\n")
        return db.finish_job(job["id"], REJECTED, str(log_path))

    return db.finish_job(job["id"], exit_code, str(log_path))
