"""Provider API keys live in the OS keychain. Never in SQLite. Never in a file.

Invariant 2 in `AGENTS.md` says the database holds a reference, never the key.
That is easy to write and easy to violate by accident, because the obvious
place to put a key is next to the row that needs it. So the key never reaches
`app/db.py` at all: the `providers` table has no `api_key` column, this module
never imports `db`, contains no SQL, and writes no file. There is nowhere for a
key to land even if someone tries.

`tests/test_provider_key_never_reaches_sqlite.py` proves it the only way worth
proving it: it stores a key through the real path, then reads the database file
as bytes and asserts the marker is not in them.

## Why no `keyring` dependency

`AGENTS.md` says a new dependency gets its own step and does not arrive as a
side effect of a feature step. `keyring` is the obvious library and is the
right answer eventually; adding it here would be exactly the side effect that
rule forbids. So the backends below talk to the same OS stores `keyring` talks
to, using the standard library:

- **Windows** - Credential Manager via `advapi32.CredWriteW` / `CredReadW`.
  The blob is DPAPI-protected under the logged-in user account, which is what
  makes it a keychain and not a file with a nicer name.
- **macOS** - the login keychain via `/usr/bin/security`, invoked as an argv
  list. No shell, ever. This is the same rule `app/hwdetect.py` follows when it
  calls `nvidia-smi`, and it is not a violation of "no shell execution": that
  invariant is about free-text command strings, not about `subprocess` itself.
- **Linux** - `secret-tool`, when it is installed, which puts the key in the
  Secret Service (GNOME Keyring, KWallet).

When no backend is available the store says so. `set_key` raises
`KeychainUnavailable` and `get_key` returns `None`. It does not fall back to a
file, and it does not fall back to the database. A user on a locked-down
machine uses the environment variable below, which is a deliberate, visible
choice they made rather than a silent downgrade we made for them.

## The environment variable comes first

`get_key` checks `MLH_KEY_<PROVIDER_ID>` before it touches any keychain. Two
reasons, and the second is the important one: a user on a machine with no
usable secret store still has a way in, and the test suite never has to touch
a real credential store to exercise the paths that read a key.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Protocol


#: The keychain "service" all our entries are filed under, so a user can find
#: and delete them without guessing.
SERVICE = "ml-harness"

#: Environment override, e.g. `MLH_KEY_3` for the provider whose row id is 3.
ENV_PREFIX = "MLH_KEY_"

_ENV_SAFE = re.compile(r"[^A-Z0-9_]")


class KeychainUnavailable(RuntimeError):
    """No OS secret store this process can write to.

    Raised only by `set_key`. Reads degrade to `None`, because a missing key is
    a condition the product already has to handle, while a silently discarded
    key is a key the user thinks is saved.
    """


class Backend(Protocol):
    """One OS secret store."""

    name: str

    def available(self) -> bool: ...
    def set(self, service: str, account: str, secret: str) -> None: ...
    def get(self, service: str, account: str) -> str | None: ...
    def delete(self, service: str, account: str) -> None: ...


# ---------------------------------------------------------------------------
# Windows Credential Manager.


class WindowsCredentialManager:
    name = "windows-credential-manager"

    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2

    def available(self) -> bool:
        return os.name == "nt"

    def _api(self):
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        advapi32.CredWriteW.restype = wintypes.BOOL
        advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(CREDENTIAL)),
        ]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredDeleteW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        advapi32.CredDeleteW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None
        return ctypes, advapi32, CREDENTIAL

    def _target(self, service: str, account: str) -> str:
        return f"{service}:{account}"

    def set(self, service: str, account: str, secret: str) -> None:
        ctypes, advapi32, CREDENTIAL = self._api()
        blob = secret.encode("utf-16-le")
        buffer = ctypes.create_string_buffer(blob, len(blob))
        credential = CREDENTIAL()
        credential.Flags = 0
        credential.Type = self._CRED_TYPE_GENERIC
        credential.TargetName = self._target(service, account)
        credential.Comment = "ML Harness provider key"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(
            buffer, ctypes.POINTER(ctypes.c_byte)
        )
        credential.Persist = self._CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = service
        if not advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise KeychainUnavailable(
                f"CredWriteW failed with error {ctypes.get_last_error()}"
            )

    def get(self, service: str, account: str) -> str | None:
        ctypes, advapi32, CREDENTIAL = self._api()
        pointer = ctypes.POINTER(CREDENTIAL)()
        ok = advapi32.CredReadW(
            self._target(service, account),
            self._CRED_TYPE_GENERIC,
            0,
            ctypes.byref(pointer),
        )
        if not ok:
            return None
        try:
            credential = pointer.contents
            size = int(credential.CredentialBlobSize)
            if size == 0:
                return ""
            raw = ctypes.string_at(credential.CredentialBlob, size)
            return raw.decode("utf-16-le")
        finally:
            advapi32.CredFree(pointer)

    def delete(self, service: str, account: str) -> None:
        ctypes, advapi32, _ = self._api()
        advapi32.CredDeleteW(
            self._target(service, account), self._CRED_TYPE_GENERIC, 0
        )


# ---------------------------------------------------------------------------
# macOS login keychain, and the Linux Secret Service. Both are argv lists.


class _CommandBackend:
    """A backend driven by a binary. Always argv, never a shell string."""

    binary = ""

    def available(self) -> bool:
        return bool(self.binary) and shutil.which(self.binary) is not None

    @staticmethod
    def _run(argv: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(  # noqa: S603 - argv list, shell=False, fixed binary
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            shell=False,
            timeout=15,
        )


class MacOSKeychain(_CommandBackend):
    name = "macos-keychain"
    binary = "security"

    def available(self) -> bool:
        return sys.platform == "darwin" and super().available()

    def set(self, service: str, account: str, secret: str) -> None:
        # `-U` updates in place when the item already exists. `-w` takes the
        # secret as an argument; it is visible to `ps` for the lifetime of the
        # call, which is the same exposure `keyring` has and is why the local
        # process boundary is the one that matters here.
        result = self._run(
            [
                self.binary,
                "add-generic-password",
                "-a",
                account,
                "-s",
                service,
                "-w",
                secret,
                "-U",
            ]
        )
        if result.returncode != 0:
            raise KeychainUnavailable(result.stderr.strip() or "security add failed")

    def get(self, service: str, account: str) -> str | None:
        result = self._run(
            [self.binary, "find-generic-password", "-a", account, "-s", service, "-w"]
        )
        if result.returncode != 0:
            return None
        return result.stdout.rstrip("\n")

    def delete(self, service: str, account: str) -> None:
        self._run(
            [self.binary, "delete-generic-password", "-a", account, "-s", service]
        )


class SecretService(_CommandBackend):
    name = "secret-service"
    binary = "secret-tool"

    def set(self, service: str, account: str, secret: str) -> None:
        result = self._run(
            [self.binary, "store", "--label", f"{service}:{account}",
             "service", service, "account", account],
            stdin=secret,
        )
        if result.returncode != 0:
            raise KeychainUnavailable(
                result.stderr.strip() or "secret-tool store failed"
            )

    def get(self, service: str, account: str) -> str | None:
        result = self._run(
            [self.binary, "lookup", "service", service, "account", account]
        )
        if result.returncode != 0:
            return None
        return result.stdout.rstrip("\n")

    def delete(self, service: str, account: str) -> None:
        self._run([self.binary, "clear", "service", service, "account", account])


#: Tried in order. Exactly one will report itself available on any given
#: machine; the list is ordered by platform rather than preference.
BACKENDS: tuple[Backend, ...] = (
    WindowsCredentialManager(),
    MacOSKeychain(),
    SecretService(),
)


def backend() -> Backend | None:
    """The OS secret store on this machine, or `None` if there is not one."""
    for candidate in BACKENDS:
        try:
            if candidate.available():
                return candidate
        except Exception:  # noqa: BLE001 - a probe must never be the crash
            continue
    return None


def _env_name(provider_id: str) -> str:
    return ENV_PREFIX + _ENV_SAFE.sub("_", str(provider_id).upper())


def set_key(provider_id: str, key: str) -> None:
    """Store `key` for `provider_id` in the OS keychain.

    Raises `KeychainUnavailable` when there is no store. It does not fall back
    anywhere: a key we cannot protect is a key we decline to hold.
    """
    store = backend()
    if store is None:
        raise KeychainUnavailable(
            "no OS keychain available on this machine; set "
            f"{_env_name(provider_id)} in the environment instead"
        )
    store.set(SERVICE, str(provider_id), key)


def get_key(provider_id: str) -> str | None:
    """The key for `provider_id`, or `None`.

    Environment first - see the module docstring. A missing or locked keychain
    is `None`, never an exception, because "no key" is a state the product
    already renders and a crash here would take down a page.
    """
    from_env = os.environ.get(_env_name(provider_id))
    if from_env:
        return from_env
    store = backend()
    if store is None:
        return None
    try:
        return store.get(SERVICE, str(provider_id))
    except Exception:  # noqa: BLE001 - a locked keychain is not a crash
        return None


def has_key(provider_id: str) -> bool:
    return get_key(provider_id) is not None


def delete_key(provider_id: str) -> None:
    store = backend()
    if store is None:
        return
    try:
        store.delete(SERVICE, str(provider_id))
    except Exception:  # noqa: BLE001
        return
