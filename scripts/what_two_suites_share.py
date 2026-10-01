"""Run the suite and record every file and port it touches OUTSIDE its checkout.

    python scripts/what_two_suites_share.py --record here.json
    python scripts/what_two_suites_share.py --compare here.json there.json

WHY THIS AND NOT ANOTHER CONCURRENT RUN. The evidence for narrowing the suite
lock was a code reading plus an observation: 31 of 77 recorded runs ran beside a
concurrent suite and 0 of them lost a test. That says **nothing collided**. It
does not say **nothing can**, and a lane deciding whether to adopt a
shared-infrastructure change is entitled to the second one. Sampling outcomes
cannot give it: a fixed path written by both runs at different moments collides
never, until the day it does.

So this enumerates the shared surface instead of sampling the failures. An audit
hook records every path opened for writing, created, renamed or removed, and
every port bound, discarding anything inside the checkout because two different
checkouts cannot collide there by construction. Run it in two checkouts and
**intersect the two sets**: a name in both is a resource two lanes share, and a
name in neither run's set is not shared no matter how many concurrent runs pass.

WHAT IT CANNOT SEE, and the list is the honest part:

* **Anything a subprocess touches.** The hook lives in this interpreter. A test
  that shells out is invisible, and the suite does shell out.
* **Reads.** Two readers do not collide, but a reader racing a writer does, and
  the writer is what this records.
* **Non-file, non-socket state** - a registry key, a named mutex, a service.
* **Order.** It says two runs write the same name, never that they would have
  written it at the same instant.

A name in the intersection is therefore a CANDIDATE collision that a person has
to look at, not a proven one. The empty intersection is the stronger result: it
says the two runs share no writable name this instrument can see.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unittest
from pathlib import Path

#: The tree being measured. Overridable so arm B can be another lane's REAL
#: checkout without copying this file into it - a measurement should not
#: have to modify the thing it measures, least of all somebody else's tree.
REPO = Path(os.environ.get("MLH_COLLISION_REPO") or Path(__file__).resolve().parents[1])

#: PUT THIS CHECKOUT FIRST, the way `scripts/gate.py` does at its line 61.
#: Leaving it out is how the first version of this instrument produced three
#: identical failures in both concurrent runs AND in the solo control: the
#: shared virtualenv carries an editable install of `app` pointing at the
#: OTHER lane's checkout, so `import app` resolved there and
#: `paths.data_root()` returned a tree this run does not own. The failures
#: were the instrument, which is the usual way round.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Filled by the audit hook. Sets, because the question is which NAMES are
#: shared and not how often each was touched.
WROTE: set[str] = set()
BOUND: set[str] = set()

#: PATHS READ. THE REASON IS THE METHOD, NOT A SIGHTING. Recording writes
#: alone cannot see a contention whose LOSER declines to write and returns -
#: and `write_portfile` is exactly that shape: it reads the incumbent,
#: finds a different live pid, and returns without writing. "Paths written by
#: both" is empty for that case by construction, the same way "0 lost tests"
#: is unable to see a collision that costs no test.
#:
#: THE EVIDENCE THAT PROMPTED THIS WAS WITHDRAWN AND THE EXTENSION STAYS.
#: It arrived as 82 of 90 runs printing a deferral; the other lane then
#: found those lines are `tests/test_security_boundary.py` writing a
#: portfile owned by its own parent in a temporary directory and asserting
#: that a second process does not overwrite a live engine - one process, one
#: temp dir, a passing test being loud. Not contention and not
#: cross-checkout. The blind spot is real whether or not anything was ever
#: caught in it, so this is kept on that argument and on no observation.
READ: set[str] = set()

#: Every `write_portfile` call: path, incumbent, and whether it deferred.
#: The question a deferral count cannot answer is whether the two arms
#: resolve to the SAME path or to two paths each with its own incumbent -
#: different findings behind an identical log line.
PORTFILE_CALLS: list[dict] = []

#: Paths under here belong to this checkout and cannot collide with another
#: checkout's copy of them. Normalised once, because the hook runs on every
#: single open in 4,400 tests and must stay cheap.
MINE = os.path.normcase(str(REPO))

#: This interpreter and its standard library get written to as bytecode caches
#: and are shared by construction; recording them would bury the answer under
#: several thousand .pyc files that no lane is contending for.
BORING = tuple(
    os.path.normcase(str(Path(p).resolve()))
    for p in (sys.prefix, sys.base_prefix, os.path.dirname(os.__file__))
)


def _outside(path: str) -> str | None:
    try:
        full = os.path.normcase(os.path.abspath(path))
    except (TypeError, ValueError):
        return None
    if full.startswith(MINE) or full.endswith(".pyc"):
        return None
    for boring in BORING:
        if full.startswith(boring):
            return None
    return full


def _hook(event: str, args) -> None:
    """Record writes. Deliberately does nothing else - an audit hook that raises
    takes the whole interpreter with it, and one that is slow makes the suite
    unrunnable."""
    try:
        if event == "open":
            path, mode = args[0], args[1]
            if not isinstance(path, str) or not mode:
                return
            if not any(letter in mode for letter in ("w", "a", "x", "+")):
                found = _outside(path)
                if found and not os.path.isdir(path):
                    READ.add(found)
                return
            # A DIRECTORY IS NOT A WRITE. `tempfile.NamedTemporaryFile` emits
            # an `open` audit event naming the temp DIRECTORY with mode "w"
            # before it creates a uniquely-named file inside it - verified by
            # reproduction. That one event was the ONLY name in the first two
            # collision lists, and it made an empty answer look like a
            # one-line answer. The instrument was the finding, again.
            if os.path.isdir(path):
                return
            found = _outside(path)
            if found:
                WROTE.add(found)
        elif event in ("os.mkdir", "os.remove", "os.rmdir"):
            path = args[0]
            if isinstance(path, str):
                # AN AUDIT EVENT FIRES BEFORE THE OPERATION, INCLUDING ONE
                # THAT WILL DO NOTHING. `Path(x).mkdir(exist_ok=True)` on a
                # directory that already exists raises inside mkdir and is
                # swallowed, but the event has already been recorded - and it
                # was the ONLY name in the first collision list, the system
                # temp directory, reached by 82 call sites in this tree. An
                # instrument that reports a no-op as a shared write turns an
                # empty answer into a one-line answer, which is the whole
                # question.
                if event == "os.mkdir" and os.path.isdir(path):
                    return
                found = _outside(path)
                if found:
                    WROTE.add(found)
        elif event in ("os.rename", "os.replace", "os.link", "os.symlink"):
            for path in args[:2]:
                if isinstance(path, str):
                    found = _outside(path)
                    if found:
                        WROTE.add(found)
        elif event == "socket.bind":
            address = args[1]
            if isinstance(address, tuple) and len(address) >= 2:
                port = address[1]
                # Port 0 asks the OS for a free one, which is the opposite of a
                # contended resource. It is recorded as such rather than
                # dropped, because "every bind asked for 0" is itself the
                # finding.
                BOUND.add("ephemeral" if port == 0 else f"port {port}")
    except Exception:  # noqa: BLE001 - a broken hook must not break the run
        pass


def _watch_the_portfile() -> None:
    """Wrap `write_portfile` so every call says which path and what happened.

    ITEM ONE ON THE OTHER LANE'S LIST: which path each arm resolves, whether
    the two are the same file, and which arm ends up owning the token. Those
    are different findings behind an identical log line, and a count of
    deferrals cannot separate them.
    """
    try:
        import app.security as security
    except Exception as why:  # noqa: BLE001 - a run without the app still measures paths
        PORTFILE_CALLS.append({"could_not_import": repr(why)})
        return

    #: NAMED, NOT GUESSED. The first version wrapped `publish_portfile`, which
    #: does not exist - the function is `write_portfile` - and both arms died on
    #: an AttributeError after eight minutes of suite. A wrapper that names its
    #: target wrongly fails loudly, which is the good case; the bad case is a
    #: wrapper that silently attaches to nothing.
    if not hasattr(security, "write_portfile"):
        PORTFILE_CALLS.append({"no_such_function": "app.security.write_portfile"})
        return
    real = security.write_portfile

    def watched(port=None, path=None):
        import os as _os
        asked = str(path) if path is not None else str(security.ENGINE_FILE)
        incumbent = None
        try:
            existing = security.read_portfile(Path(asked))
            incumbent = (existing or {}).get("pid")
        except Exception:  # noqa: BLE001
            pass
        answer = real(port=port, path=path)
        PORTFILE_CALLS.append({
            "path": _os.path.normcase(_os.path.abspath(asked)),
            "incumbent_pid": incumbent,
            "our_pid": _os.getpid(),
            # A DEFERRAL IS AN INCUMBENT THAT IS SOMEBODY ELSE AND ALIVE. Read
            # back rather than inferred: the file may have changed under us.
            "deferred": bool(incumbent) and incumbent != _os.getpid(),
        })
        return answer

    security.write_portfile = watched


def _the_named_paths() -> dict:
    """Resolve, by name, every path the other lane asked to see.

    ASSERTED RATHER THAN INFERRED FROM WHAT GOT TOUCHED. A path nothing happened
    to open during a run is absent from the trace and present on the machine, and
    "it did not appear" is not an answer to "where does it resolve".
    """
    import tempfile

    named: dict[str, str] = {}

    def say(key, get):
        try:
            named[key] = str(get())
        except Exception as why:  # noqa: BLE001
            named[key] = f"could not resolve: {why!r}"

    say("engine_file", lambda: __import__("app.security", fromlist=["x"]).ENGINE_FILE)
    say("data_root", lambda: __import__("app.paths", fromlist=["x"]).data_root())
    say("db_path", lambda: __import__("app.db", fromlist=["x"]).DB_PATH)
    say("recipes_root", lambda: __import__("app.jobspec", fromlist=["x"]).RECIPES_ROOT)
    say("runs_root", lambda: __import__("app.jobspec", fromlist=["x"]).RUNS_ROOT)
    say("model_config_root",
        lambda: __import__("app.feasibility", fromlist=["x"]).MODEL_CONFIG_ROOT)
    say("hub_cache_root",
        lambda: __import__("app.tools.models", fromlist=["x"]).HUB_CACHE_ROOT)
    say("temp_dir", tempfile.gettempdir)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "the_lock_here", REPO / "scripts" / "one_gate_at_a_time.py")
    try:
        lock = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = lock
        spec.loader.exec_module(lock)
        named["gate_lock"] = str(lock.LOCK)
        named["gate_legacy_lock"] = str(lock.LEGACY_LOCK)
        named["checkout_hash"] = lock._this_checkout()
    except Exception as why:  # noqa: BLE001
        named["gate_lock"] = f"could not resolve: {why!r}"

    card = REPO / "card_owner" / "the_lock.py"
    if card.is_file():
        try:
            spec = importlib.util.spec_from_file_location("the_card_lock_here", card)
            owner = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = owner
            spec.loader.exec_module(owner)
            named["gpu_lock"] = str(getattr(owner, "THE_LOCK", "not named"))
        except Exception as why:  # noqa: BLE001
            named["gpu_lock"] = f"could not resolve: {why!r}"
    return named


def _the_token_boundary() -> dict:
    """ITEM 2: which engine a client of this arm would authenticate against.

    THE ONLY ITEM THAT CATCHES THE EDITABLE INSTALL FROM THE OUTSIDE. Two arms
    authenticating against one engine is what a shared `app` package looks like
    at the boundary, and it is invisible to every path-level check: nothing
    collides, nothing fails, and a client simply talks to the wrong engine.

    So this asks the question twice - once with this checkout first on
    `sys.path`, which is what `scripts/gate.py` arranges, and once in a bare
    subprocess that does NOT arrange it, which is what any script written
    without that line gets. The difference between the two answers is the size
    of the accident.
    """
    import subprocess

    answer: dict[str, object] = {}
    try:
        import app.security as security
        answer["engine_file_with_repo_first"] = str(security.ENGINE_FILE)
        answer["app_package_with_repo_first"] = str(
            Path(security.__file__).resolve().parents[1])
        published = security.read_portfile(security.ENGINE_FILE)
        answer["published_token_present"] = bool((published or {}).get("token"))
        answer["published_by_pid"] = (published or {}).get("pid")
    except Exception as why:  # noqa: BLE001
        answer["with_repo_first"] = f"could not resolve: {why!r}"

    # The same question from a process that never put this checkout first.
    probe = (
        "import json,sys;"
        "import app.security as s, app.paths as p;"
        "print(json.dumps({"
        "'engine_file': str(s.ENGINE_FILE),"
        "'app_package': str(__import__('pathlib').Path(s.__file__).resolve().parents[1]),"
        "'data_root': str(p.data_root())}))"
    )
    try:
        import tempfile as _tempfile
        # CWD MUST NOT BE THE REPO, or the probe answers the question it was
        # written to avoid: `python -c` puts the working directory on
        # sys.path, so asking from inside the checkout puts the checkout
        # first and reproduces the CORRECT case while claiming to reproduce
        # the accident. `python scripts/foo.py` gets the scripts directory,
        # not the repo, which is the shape of the real mistake.
        done = subprocess.run(
            [sys.executable, "-c", probe], cwd=_tempfile.gettempdir(),
            capture_output=True, text=True, timeout=60,
        )
        answer["without_repo_first"] = (
            json.loads(done.stdout.strip().splitlines()[-1])
            if done.returncode == 0 and done.stdout.strip()
            else f"exit {done.returncode}: {done.stderr.strip()[-200:]}"
        )
    except Exception as why:  # noqa: BLE001
        answer["without_repo_first"] = f"could not ask: {why!r}"
    return answer


def _under_temp_without_the_hash(named: dict) -> list[str]:
    """ITEM 9: names this run WROTE directly under %TEMP% without the hash in them.

    FROM THE TRACE, NOT FROM A DIRECTORY LISTING. The first version listed the
    whole temp directory for anything containing "mlh" and returned 250 names,
    most of them random suffixes that happened to contain those three letters
    and other tools' scratch files this suite never touched. A list that large
    is not an answer, and a substring match on a random suffix is not evidence.

    A name carrying the checkout hash is scoped by construction. One that does
    not is a candidate for two lanes to share.
    """
    import tempfile

    hashed = str(named.get("checkout_hash") or "")
    root = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    naked = set()
    for path in WROTE:
        parent, _, leaf = path.rpartition(os.sep)
        if parent != root or not leaf:
            continue
        if hashed and hashed in leaf:
            continue
        naked.add(leaf)
    return sorted(naked)


def record(out: Path) -> int:
    named = _the_named_paths()
    _watch_the_portfile()
    sys.addaudithook(_hook)
    loader = unittest.defaultTestLoader
    suite = loader.discover(str(REPO / "tests"), top_level_dir=str(REPO / "tests"))
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    try:
        import app.paths as _paths
        which_app = str(Path(_paths.__file__).resolve().parents[1])
    except Exception as why:  # noqa: BLE001
        which_app = f"could not import app: {why!r}"
    payload = {
        "checkout": str(REPO),
        #: WHICH TREE THIS RUN ACTUALLY IMPORTED. A run that tested another
        #: checkout's code and said nothing is worse than a run that failed.
        "imported_app_from": which_app,
        "ran": result.testsRun,
        "green": result.wasSuccessful(),
        "failures": [str(case) for case, _ in result.failures],
        "errors": [str(case) for case, _ in result.errors],
        "resolved_by_name": named,
        "token_boundary": _the_token_boundary(),
        "under_temp_without_the_hash": _under_temp_without_the_hash(named),
        "portfile_calls": PORTFILE_CALLS,
        "wrote_outside_the_checkout": sorted(WROTE),
        "read_outside_the_checkout": sorted(READ),
        "bound": sorted(BOUND),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nran {result.testsRun}, "
          f"{'green' if result.wasSuccessful() else 'RED'}; "
          f"{len(WROTE)} path(s) outside the checkout, {len(BOUND)} bind form(s) "
          f"-> {out}")
    return 0 if result.wasSuccessful() else 1


def compare(a: Path, b: Path) -> int:
    one, two = (json.loads(p.read_text(encoding="utf-8")) for p in (a, b))
    mine = set(one["wrote_outside_the_checkout"])
    theirs = set(two["wrote_outside_the_checkout"])
    both = sorted(mine & theirs)
    #: Sets recorded before the directory filter existed carry names that
    #: are directories. A directory cannot be the thing two runs contend
    #: for - each creates distinct children in it - so they are reported
    #: separately rather than dropped silently or counted as collisions.
    shared = [name for name in both if not os.path.isdir(name)]
    directories = [name for name in both if os.path.isdir(name)]

    print(f"checkout A  {one['checkout']}")
    print(f"            ran {one['ran']}, {'green' if one['green'] else 'RED'}, "
          f"{len(mine)} path(s) outside it, binds: {', '.join(one['bound']) or 'none'}")
    print(f"            imported app from {one.get('imported_app_from', '?')}")
    print(f"checkout B  {two['checkout']}")
    print(f"            ran {two['ran']}, {'green' if two['green'] else 'RED'}, "
          f"{len(theirs)} path(s) outside it, binds: {', '.join(two['bound']) or 'none'}")
    print(f"            imported app from {two.get('imported_app_from', '?')}")
    print()
    print(f"THE COLLISION LIST: {len(shared)} name(s) written by BOTH runs")
    print("-" * 78)
    for name in shared:
        print(f"  {name}")
    if not shared:
        print("  (empty - the two runs share no writable name this can see)")
    print("-" * 78)
    if directories:
        print(f"and {len(directories)} shared DIRECTORY name(s), which are not "
              "collisions -")
        for name in directories:
            print(f"  {name}")
        print("each run creates distinct children in them; they appear because an")
        print("audit event can name a directory (NamedTemporaryFile does).")
        print("-" * 78)
    print("A name here is a CANDIDATE, not a proven collision: this says two runs")
    print("write the same name, never that they would have done so at the same")
    print("instant. It cannot see inside subprocesses, and the suite shells out.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", type=Path, help="run the suite and write the set")
    parser.add_argument("--compare", type=Path, nargs=2, help="intersect two sets")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.compare:
        return compare(*args.compare)
    if args.record:
        return record(args.record)
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
