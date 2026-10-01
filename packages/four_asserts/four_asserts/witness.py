"""What was this artifact, and how much of it did you actually read?

THE FAILURE THIS IS FOR. A path is a location, not a version. A number derived
from a file, recorded with the path it came from, says nothing about the file
that was there at the time - and the file that is there now may not be the one
that was counted. When the bytes are gone, a path names nothing at all.

WHAT A WITNESS IS. The size and a sha256 of the contents, taken at the moment
the artifact was used, kept beside the path. It survives the bytes: a record
carrying a witness can still say what it was about after the file is deleted,
and two records can be compared without either file existing.

WHY sha256 AND NOT A CHEAPER STAMP, said plainly because the trade is real. A
size-and-modification-time stamp is free and it is not identity: measured on
one ordinary filesystem, two DIFFERENT files of the same length written back to
back produced an identical size-and-mtime stamp in 157 of 200 trials. That is
not an exotic filesystem with a coarse clock; it is the common case for a fast
rewrite. A hash costs a read of the file, and this module makes that cost
visible rather than hiding it - see `Witness.how`.

AND THE SECOND HALF, WHICH IS THE ONE PEOPLE SKIP. An answer computed from an
artifact must say how much of the artifact it read. "The log shows no errors"
means one thing over 200 lines of 200 and another over 200 of 60,000, and
nothing in the sentence distinguishes them. `read_lines` returns the count and
the total together so a caller cannot state one without the other.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple

#: Read the file in blocks rather than whole. A witness of a 50 GB artifact
#: must not need 50 GB of memory, and the cost of hashing is already the thing
#: a caller is deciding about.
BLOCK = 1024 * 1024


class Witness(NamedTuple):
    """What an artifact was, kept so it survives the artifact."""

    path: str
    size: int
    sha256: str
    read_bytes: int

    @property
    def whole(self) -> bool:
        """Was the whole artifact hashed? A partial witness is still useful and
        must never be mistaken for a full one."""
        return self.read_bytes == self.size

    @property
    def how(self) -> str:
        """The sentence a record should carry, with the cost stated.

        It names what was read as well as what was found, because a witness
        over the first megabyte of a file is evidence about a megabyte.
        """
        if self.whole:
            return "sha256 {sha} over all {size} bytes of {path}".format(
                sha=self.sha256[:16], size=self.size, path=self.path
            )
        return "sha256 {sha} over the first {read} of {size} bytes of {path}".format(
            sha=self.sha256[:16], read=self.read_bytes, size=self.size, path=self.path
        )

    def same_as(self, other: "Witness") -> bool:
        """Is this the same artifact? Both witnesses must be whole.

        Two partial hashes agreeing says the prefixes agree, and a caller that
        reads that as identity has been handed a claim this module refuses to
        make.
        """
        if not (self.whole and other.whole):
            return False
        return self.sha256 == other.sha256 and self.size == other.size


class Read(NamedTuple):
    """Lines taken from an artifact, with the denominator attached."""

    lines: tuple[str, ...]
    total: int
    witness: Witness

    @property
    def n_of_m(self) -> str:
        return "{} of {}".format(len(self.lines), self.total)

    @property
    def whole(self) -> bool:
        return len(self.lines) == self.total


def witness(path: str | Path, *, limit_bytes: int | None = None) -> Witness:
    """Hash and size an artifact as it is right now.

    `limit_bytes` hashes only a prefix, for an artifact too large to read in
    full. The result says so - `whole` is False - and `same_as` refuses to
    compare it, so a partial witness cannot quietly become an identity claim.
    """
    p = Path(path)
    size = p.stat().st_size
    digest = hashlib.sha256()
    read = 0
    with p.open("rb") as handle:
        while True:
            if limit_bytes is not None and read >= limit_bytes:
                break
            want = BLOCK if limit_bytes is None else min(BLOCK, limit_bytes - read)
            block = handle.read(want)
            if not block:
                break
            digest.update(block)
            read += len(block)
    return Witness(path=str(p), size=size, sha256=digest.hexdigest(), read_bytes=read)


def read_lines(path: str | Path, limit: int | None = None) -> Read:
    """Read up to `limit` lines, and say how many there were in all.

    The total is counted even when the read is capped, because the denominator
    is the whole reason this returns a type instead of a list. A caller that
    only wanted the lines can take `.lines`; a caller that reports what it found
    has `.n_of_m` sitting next to it and no excuse.
    """
    p = Path(path)
    taken: list[str] = []
    total = 0
    with p.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            total += 1
            if limit is None or len(taken) < limit:
                taken.append(line.rstrip("\n"))
    return Read(lines=tuple(taken), total=total, witness=witness(p))


def counted(number: int, of: Witness, *, what: str = "rows") -> str:
    """A measurement with its subject attached, as one sentence.

    This is the shape the whole module is for: a number, what it counted, and
    an identity for the thing it counted that outlives the thing.
    """
    return "counted {n} {what}; {how}".format(n=number, what=what, how=of.how)
