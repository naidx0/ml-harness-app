"""Four things to assert about a run before its record counts.

Each one exists because it was missing and something went green that should not
have. None of them decides whether your work is good; they decide whether the
record of it says what it appears to say.

    assert_ran    as many things ran as were discovered
    hold          the resource had a named holder, still alive
    witness       the artifact has an identity that outlives its bytes
    void_unless   the verdict's reason survives a rule

No dependencies. Python 3.10 or later.
"""

from __future__ import annotations

from .assert_ran import (
    DID_NOT_SAY,
    FAILED,
    GREEN,
    Ran,
    assert_ran,
    count_leaves,
    modules_that_did_not_import,
    pending,
    unittest_suite,
)
from .hold import Hold, started_at, still_running
from .void_unless import (
    NO_RULE,
    Register,
    Ruling,
    Verdict,
    account,
    added_word,
    changed_number,
    dropped_clause,
    inverted_negation,
    standard_register,
    void_unless,
)
from .witness import Read, Witness, counted, read_lines, witness

__version__ = "0.1.0"

__all__ = [
    "DID_NOT_SAY",
    "FAILED",
    "GREEN",
    "NO_RULE",
    "Hold",
    "Ran",
    "Read",
    "Register",
    "Ruling",
    "Verdict",
    "Witness",
    "account",
    "added_word",
    "assert_ran",
    "changed_number",
    "count_leaves",
    "counted",
    "dropped_clause",
    "inverted_negation",
    "modules_that_did_not_import",
    "pending",
    "read_lines",
    "standard_register",
    "started_at",
    "still_running",
    "unittest_suite",
    "void_unless",
    "witness",
]
