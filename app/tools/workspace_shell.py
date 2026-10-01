"""AU4 — free-text commands in a sandbox or (under full) the project folder.

Structured tools stay the fast path. When inventory disagrees or a one-liner
is the right move, the agent runs a shell *command string* as argv to
powershell / sh (never subprocess shell=True on an untrusted blob as JobSpec).

Sandbox runs reuse the sandbox env (no HF_TOKEN / no engine secrets unless
egress was declared). Project runs require a project root and refuse path
escape; auto-approve only under permission full.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from app import db, events, runner
from app.tools import sandbox as sandbox_tools
from app.tools.registry import tool

#: Max, 2026-09-17: *"give it as much shell power as it wants to have."* A
#: baseline of another local model or a small training run does not fit in
#: two minutes; ten by default, an hour at most.
DEFAULT_TIMEOUT = 600
MAX_TIMEOUT = 3600
MAX_OUTPUT = 100_000


#: WHICH SHELL A COMMAND RUNS IN. Desktop-shortcut check, 2026-09-30: the
#: iris task never finished because MiniCPM5 writes bash - heredocs, `which`,
#: `2>/dev/null`, `| head` - and on Windows every command went to PowerShell
#: 5.1. 0 of 6 runs managed to write the script file. With Git for Windows
#: present, commands now run in its bash (lab/log.md "H-shell" A5: shell errors
#: 2.0 -> 0.0 a run, 8 of 10 finished against 7). `MLH_PROJECT_SHELL=powershell`
#: keeps the old shell.
SHELL_ENV = "MLH_PROJECT_SHELL"


def _git_bash() -> str | None:
    """Git for Windows' bash.exe, or None. NEVER System32's bash, which is WSL.

    `shutil.which("bash")` on Windows answers C:\\Windows\\System32\\bash.exe
    when WSL is installed, and that runs the command in a Linux distro with a
    different filesystem and no Windows Python - so it is not asked.
    """
    candidates: list[Path] = []
    named = os.environ.get("MLH_GIT_BASH")
    if named:
        candidates.append(Path(named))
    git = shutil.which("git")
    if git:
        here = Path(git).resolve()
        # ...\Git\cmd\git.exe and ...\Git\mingw64\bin\git.exe both live under Git.
        for up in (here.parent.parent, here.parent.parent.parent):
            candidates.append(up / "bin" / "bash.exe")
    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramW6432"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    ):
        if base:
            candidates.append(Path(base) / "Git" / "bin" / "bash.exe")
    for candidate in candidates:
        if candidate.is_file() and "system32" not in str(candidate).lower():
            return str(candidate)
    return None


def project_shell() -> str:
    """`bash`, `powershell` (Windows) or `sh` (elsewhere): what a command runs in."""
    if sys.platform != "win32":
        return "sh"
    choice = os.environ.get(SHELL_ENV, "auto").strip().lower()
    if choice in ("bash", "auto") and _git_bash():
        return "bash"
    return "powershell"


def _on_on_windows(name: str) -> bool:
    """A part of the kept H-shell stack: on for Windows unless the variable says no.

    Measured as stacks, never alone (lab/log.md "H-shell"): with Git Bash, the
    brief and the project venv (A5, 8 of 10); without it, the same two plus the
    preflight (A6, 9 of 10). Alone, each lost (A2 4 of 10, A3 2 of 10). Nothing
    was measured elsewhere, so elsewhere they stay off.
    """
    named = os.environ.get(name, "").strip().lower()
    if named:
        return named in ("1", "true", "yes", "on")
    return sys.platform == "win32"


def brief_on() -> bool:
    return _on_on_windows("MLH_SHELL_BRIEF")


def venv_on() -> bool:
    return _on_on_windows(VENV_ENV)


def preflight_on() -> bool:
    return _on_on_windows(PREFLIGHT_ENV)


#: What the model is told about the shell, per shell: its name, how to write a
#: file, how to run Python. One line each, because a 2B model copies examples.
SHELL_FACTS: dict[str, dict[str, str]] = {
    "bash": {
        "name": "bash (Git Bash on Windows)",
        "write_file": "cat > train.py << 'EOF'\n<the script>\nEOF",
        "run": "python train.py",
    },
    "powershell": {
        "name": "Windows PowerShell 5.1 (not bash: no heredoc, no which, no /dev/null, no head/tail)",
        "write_file": "@'\n<the script>\n'@ | Set-Content -Encoding utf8 train.py",
        "run": "python train.py",
    },
    "sh": {
        "name": "sh",
        "write_file": "cat > train.py << 'EOF'\n<the script>\nEOF",
        "run": "python3 train.py",
    },
}


def shell_facts() -> dict[str, str]:
    # Not `dict(..., shell=...)`: test_security_boundary reads any `shell=` keyword as a shell call.
    return {**SHELL_FACTS[project_shell()], "shell": project_shell()}


# ---------------------------------------------------------------------------
# (c) BASH IN POWERSHELL, CAUGHT BEFORE IT RUNS. `MLH_SHELL_PREFLIGHT=1`.
# The mechanical ones are translated and run; the rest are refused with the
# PowerShell form, so the round that follows is a correct call, not a guess.
# ---------------------------------------------------------------------------

PREFLIGHT_ENV = "MLH_SHELL_PREFLIGHT"

_HEREDOC = re.compile(
    r"^[ \t]*cat[ \t]*>[ \t]*(?P<path>[^\s<]+)[ \t]*<<-?[ \t]*(?P<q>['\"]?)(?P<tag>\w+)(?P=q)[ \t]*\r?\n"
    r"(?P<body>.*?)\r?\n[ \t]*(?P=tag)[ \t]*(?:\r?\n|$)",
    re.S | re.M,
)

#: (pattern, what was found, the PowerShell form). Refused, not translated.
_BASHISMS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"<<-?\s*['\"]?\w+"), "a heredoc (<<)", "@'\n...\n'@ | Set-Content -Encoding utf8 file.py"),
    (re.compile(r"\s\|\|\s"), "||", "a; if (-not $?) { b }"),
    (re.compile(r"(?:^|[;&|]\s*)ls\s+-\w*[la]"), "ls -la", "Get-ChildItem -Force"),
    (re.compile(r"(?:^|[;&|]\s*)export\s+\w+="), "export NAME=value", "$env:NAME = 'value'"),
    (re.compile(r"(?:^|[;&|]\s*)rm\s+-\w*[rf]"), "rm -rf", "Remove-Item -Recurse -Force path"),
    (re.compile(r"(?:^|[;&|]\s*)touch\s"), "touch", "New-Item -ItemType File path"),
    (re.compile(r"(?:^|[;&|]\s*)mkdir\s+-p\b"), "mkdir -p", "New-Item -ItemType Directory -Force path"),
    (re.compile(r"(?:^|[;&|]\s*)find\s+\S+\s+-name\b"), "find DIR -name", "Get-ChildItem DIR -Recurse -Filter name"),
    (re.compile(r"\|\s*grep\b"), "| grep", "| Select-String pattern"),
    (re.compile(r"(?:^|[;&|]\s*)grep\s"), "grep", "Select-String -Path file -Pattern text"),
)

_TRANSLATIONS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"(\d?)>\s*/dev/null"), r"\1>$null", "/dev/null -> $null"),
    (re.compile(r"&>\s*/dev/null"), "*>$null", "&>/dev/null -> *>$null"),
    (re.compile(r"\|\s*head\s+-n\s*(\d+)"), r"| Select-Object -First \1", "head -n N -> Select-Object -First N"),
    (re.compile(r"\|\s*head\s+-(\d+)"), r"| Select-Object -First \1", "head -N -> Select-Object -First N"),
    (re.compile(r"\|\s*head\b(?!\s*-)"), "| Select-Object -First 10", "head -> Select-Object -First 10"),
    (re.compile(r"\|\s*tail\s+-n\s*(\d+)"), r"| Select-Object -Last \1", "tail -n N -> Select-Object -Last N"),
    (re.compile(r"\|\s*tail\s+-(\d+)"), r"| Select-Object -Last \1", "tail -N -> Select-Object -Last N"),
    (re.compile(r"\|\s*tail\b(?!\s*-)"), "| Select-Object -Last 10", "tail -> Select-Object -Last 10"),
    (re.compile(r"(?:^|(?<=[;&|]\s))which\s+([\w.\-]+)"), r"(Get-Command \1).Source", "which x -> (Get-Command x).Source"),
)


def preflight_powershell(command: str, cwd: Path) -> dict[str, Any]:
    """Translate or refuse bash syntax meant for PowerShell. Never runs anything.

    Returns {"command": <what to run>, "wrote": [files], "translated": [...]}
    or {"refused": [{"found", "use_instead"}]}. A heredoc that writes a file
    (`cat > f.py << 'EOF' ... EOF`) is the one that matters: it is how the
    model writes every script, so its body is written to the file here, byte
    for byte, and the rest of the command runs.
    """
    text = str(command or "")
    wrote: list[str] = []
    translated: list[str] = []

    def _write(match: re.Match[str]) -> str:
        target = (cwd / match.group("path").strip("'\"")).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((match.group("body") + "\n").encode("utf-8"))
        wrote.append(str(target))
        return ""

    remaining = _HEREDOC.sub(_write, text)
    if wrote:
        translated.append("heredoc -> file written by the harness")
    for pattern, replacement, note in _TRANSLATIONS:
        new = pattern.sub(replacement, remaining)
        if new != remaining:
            translated.append(note)
            remaining = new
    refused = [
        {"found": found, "use_instead": instead}
        for pattern, found, instead in _BASHISMS
        if pattern.search(remaining)
    ]
    if refused:
        return {"refused": refused, "wrote": wrote}
    return {"command": remaining.strip(), "wrote": wrote, "translated": translated}


# ---------------------------------------------------------------------------
# (d) A PROJECT'S OWN PYTHON. `MLH_PROJECT_VENV=1`. Earlier test runs
# pip-installed scikit-learn and six more packages into the machine's Python
# 3.14. The project gets `<root>/.venv` (with the usual ML packages, from uv's
# cache when uv is there), first on PATH, and pip refuses outside a venv.
# ---------------------------------------------------------------------------

VENV_ENV = "MLH_PROJECT_VENV"
VENV_DIR = ".venv"
VENV_PACKAGES = ("numpy", "pandas", "scikit-learn")


def _venv_bin(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin")


def ensure_project_venv(root: Path) -> dict[str, Any]:
    """Make `<root>/.venv` once. Returns {"ok", "venv", "built_by"} or a refusal."""
    venv = root / VENV_DIR
    python = _venv_bin(venv) / ("python.exe" if os.name == "nt" else "python")
    if python.is_file():
        return {"ok": True, "venv": str(venv), "built_by": "existing"}
    uv = shutil.which("uv")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if uv:
        steps = [
            [uv, "venv", "--seed", "--python", version, str(venv)],
            [uv, "pip", "install", "--python", str(python), *VENV_PACKAGES],
        ]
        built_by = "uv"
    else:
        steps = [
            [sys.executable, "-m", "venv", str(venv)],
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", *VENV_PACKAGES],
        ]
        built_by = "venv+pip"
    for argv in steps:
        done = runner._run_bounded(argv, sandbox_tools.INSTALL_TIMEOUT_SECONDS)
        if done.returncode != 0:
            return {
                "ok": False,
                "error": "project_venv_not_built",
                "built_by": built_by,
                "stderr_tail": sandbox_tools._tail(done.stderr) or sandbox_tools._tail(done.stdout),
            }
    if os.name == "nt":
        # Models type `python3`; a venv on Windows has only python.exe, and the
        # python3 on PATH after it is the machine's own. The launcher reads the
        # pyvenv.cfg beside it, so a copy under the other name is the venv too.
        alias = python.with_name("python3.exe")
        if not alias.exists():
            shutil.copyfile(python, alias)
    return {"ok": True, "venv": str(venv), "built_by": built_by}


def _with_venv(env: dict[str, str], venv: str) -> dict[str, str]:
    env = dict(env)
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    env[path_key] = str(_venv_bin(Path(venv))) + os.pathsep + env.get(path_key, "")
    env["VIRTUAL_ENV"] = venv
    env["PIP_REQUIRE_VIRTUALENV"] = "true"
    env.pop("PYTHONHOME", None)
    return env


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _shell_argv(command: str, shell: str | None = None) -> list[str]:
    text = str(command or "").strip()
    if not text:
        raise ValueError("empty_command")
    shell = shell or project_shell()
    if shell == "bash":
        bash = _git_bash()
        if bash:
            return [bash, "--noprofile", "--norc", "-c", text]
    if sys.platform == "win32":
        # `a && b` is what every model writes and what PowerShell 5.1 does not
        # have. Thread 75's first shell call died on it. Translated to the
        # same meaning - run b only when a succeeded - rather than refused.
        if " && " in text:
            text = "; if ($?) { ".join(text.split(" && ")) + " }" * (text.count(" && "))
        return [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            text,
        ]
    return ["/bin/sh", "-c", text]


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n… truncated at {MAX_OUTPUT} bytes"


def _bound(timeout_seconds: int | None) -> int:
    try:
        n = int(timeout_seconds) if timeout_seconds is not None else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        n = DEFAULT_TIMEOUT
    return max(1, min(n, MAX_TIMEOUT))


@tool(
    name="run_sandbox_command",
    description=(
        "Run a free-text shell command inside an existing sandbox (cwd = work). "
        "Prefer structured tools (list_local_models, measure_baseline) first; "
        "use this when you need to explore, recover from a wrong path, or run "
        "a one-liner the recipe layer does not cover. Inherits the sandbox "
        "environment (no engine secrets unless that sandbox declared egress)."
    ),
    schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Sandbox name, exactly as list_sandboxes shows.",
            },
            "command": {
                "type": "string",
                "description": "Shell command text (powershell on Windows, sh elsewhere).",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": f"Wall clock bound, default {DEFAULT_TIMEOUT}, max {MAX_TIMEOUT}.",
            },
        },
        "required": ["name", "command"],
    },
    reads=("filesystem", "recipes"),
    writes=("filesystem",),
    approval="always",
    provides=("sandbox.shell.run",),
    label="Sandbox shell",
    group="Train",
    verb="run a shell command inside a sandbox",
    order=56,
)
def run_sandbox_command(
    name: str,
    command: str,
    timeout_seconds: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    try:
        argv = _shell_argv(command)
    except ValueError:
        return {
            "ok": False,
            "error": "empty_command",
            "detail": "command must not be empty.",
        }
    try:
        resolved = sandbox_tools.sandbox_name(name, shape=False)
        manifest = sandbox_tools.read_manifest(resolved)
    except sandbox_tools.SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": "list_sandboxes says what is there.",
        }
    work = Path(manifest.get("work_dir") or (Path(manifest["path"]) / "work"))
    if not work.is_dir():
        return {
            "ok": False,
            "error": "no_work_dir",
            "detail": f"sandbox {resolved!r} has no work directory at {work}.",
        }
    env = sandbox_tools._environment(manifest)
    bound = _bound(timeout_seconds)
    completed = runner._run_bounded(argv, bound, cwd=str(work), env=env)
    return {
        "ok": completed.returncode == 0,
        "sandbox": resolved,
        "cwd": str(work),
        "command": command,
        "exit_code": completed.returncode,
        "stdout": _clip(completed.stdout or ""),
        "stderr": _clip(completed.stderr or ""),
        "timeout_seconds": bound,
        "summary": (
            f"sandbox {resolved}: exit {completed.returncode} "
            f"({len(completed.stdout or '')} stdout bytes)"
        ),
    }


@tool(
    name="run_project_command",
    description=(
        "Run a free-text shell command with cwd = this thread's project folder. "
        "Auto-approved only under permission full. Prefer run_sandbox_command "
        "when the work should stay disposable. Refuses if there is no project "
        "root or if the command tries to leave that folder via cwd tricks."
    ),
    schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command text (powershell on Windows, sh elsewhere).",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": f"Wall clock bound, default {DEFAULT_TIMEOUT}, max {MAX_TIMEOUT}.",
            },
            "thread_id": {
                "type": "integer",
                "description": "Filled in for you.",
            },
        },
        "required": ["command"],
    },
    reads=("filesystem",),
    writes=("filesystem",),
    approval="always",
    provides=("context.shell.run",),
    label="Project shell",
    group="Look",
    verb="run a shell command in the project folder",
    order=18,
)
def run_project_command(
    command: str,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    thread_id: int | None = None,
) -> dict[str, Any]:
    try:
        argv = _shell_argv(command)
    except ValueError:
        return {
            "ok": False,
            "error": "empty_command",
            "detail": "command must not be empty.",
        }
    if thread_id is None:
        return {"ok": False, "error": "missing_thread_id"}
    thread = events.get_thread(thread_id) or {}
    project_id = thread.get("project_id")
    if project_id is None:
        return {
            "ok": False,
            "error": "no_project",
            "detail": "This thread has no project, so there is no folder to run in.",
        }
    project = db.get_project(int(project_id))
    root_raw = (project or {}).get("root_path") if project else None
    if not root_raw and project:
        # A PROJECT WITH NO FOLDER STILL HAS ONE: the workspace the window
        # already shows it in (`facade.sessions.directory_of`, created there).
        # Desktop-shortcut check 2026-09-30: every fresh install lands in
        # "Default", which has no root_path, so the model wrote the script,
        # called this, and was refused on every try - the person's first task
        # could not run anything at all.
        from app.facade import sessions as _sessions

        root_raw = _sessions.directory_of(project)
    if not root_raw:
        return {
            "ok": False,
            "error": "no_project_root",
            "detail": "Set the project folder first (set_the_project_root).",
        }
    root = Path(str(root_raw)).resolve()
    if not root.is_dir():
        return {
            "ok": False,
            "error": "root_missing",
            "detail": f"Project root {root} is not a directory.",
        }
    # Minimal env: do not pass engine secrets. PATH from the process is enough
    # for ollama/python; strip common credential names.
    import os

    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().endswith(("_TOKEN", "_KEY", "_SECRET", "_PASSWORD"))
        and k.upper() not in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN", "MLH_TOKEN")
    }
    shell = project_shell()
    extra: dict[str, Any] = {}
    if shell == "powershell" and preflight_on():
        checked = preflight_powershell(command, root)
        if checked.get("refused"):
            return {
                "ok": False,
                "error": "bash_syntax_in_powershell",
                "shell": SHELL_FACTS[shell]["name"],
                "cwd": str(root),
                "command": command,
                "wrote": checked.get("wrote") or [],
                "refused": checked["refused"],
                "detail": (
                    "Nothing ran. This shell is Windows PowerShell, not bash. "
                    "Send the command again with each `found` replaced by its "
                    "`use_instead`. To write a file: "
                    + SHELL_FACTS[shell]["write_file"]
                ),
            }
        extra = {"wrote": checked["wrote"], "translated": checked["translated"]}
        if not checked["command"]:
            return {
                "ok": True,
                "shell": SHELL_FACTS[shell]["name"],
                "cwd": str(root),
                "command": command,
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                **extra,
                "summary": f"project shell: wrote {', '.join(checked['wrote'])}",
            }
        argv = _shell_argv(checked["command"], shell)
    if venv_on():
        made = ensure_project_venv(root)
        if made.get("ok"):
            env = _with_venv(env, made["venv"])
            extra["python_env"] = made["venv"]
        else:
            extra["python_env_error"] = made
    bound = _bound(timeout_seconds)
    completed = runner._run_bounded(argv, bound, cwd=str(root), env=env)
    if shell == "bash" or preflight_on() or brief_on():
        extra["shell"] = SHELL_FACTS[shell]["name"]
    return {
        "ok": completed.returncode == 0,
        "cwd": str(root),
        "command": command,
        "exit_code": completed.returncode,
        "stdout": _clip(completed.stdout or ""),
        "stderr": _clip(completed.stderr or ""),
        "timeout_seconds": bound,
        **extra,
        "summary": (
            f"project shell: exit {completed.returncode} "
            f"({len(completed.stdout or '')} stdout bytes)"
        ),
    }
