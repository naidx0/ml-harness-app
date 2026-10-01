"""A provenance claim is checkable, so it is checked rather than inferred.

One turn in 242 of a live adversarial run, asked for a verdict "right now", the
model called `state_facts` and nothing else, and then told the user:

    baseline_score: 0.75 (measured by measure_baseline)
    trivial_baseline_score: 0.5 (measured by measure_baseline)

`measure_baseline` never ran. Two invented numbers wearing invented INSTRUMENT
PROVENANCE, in the one product whose entire pitch is that its numbers are real.
Invariant 3 (every displayed number carries provenance) and invariant 5 (never
invent a number) violated together, and it reached the user whole.

## Why this is a different kind of wall from the verdict sentry

`conductor.reads_as_a_verdict` has to infer INTENT from language: does this
sentence settle the training decision? That question has no ground truth outside
the sentence, so every cut of it trades one direction against the other, and it
has now been tuned twice.

A PROVENANCE CLAIM IS NOT LIKE THAT. It names an instrument and a reading, and
the harness holds both facts:

  * the event log records every tool that ran this turn, AND WHAT EACH ONE
    RETURNED, and
  * the fact ledger records every value, its origin and the tool that stamped it.

So "0.75, measured by measure_baseline" is decidable BY LOOKUP. No parsing of
intent, no window of three words, no families to trade off. That is a stronger
wall than the sentry can ever be, and it is why this module is separate from it
rather than one more frame inside `conductor._settling_frames`.

The parsing that remains - deciding that a claim was MADE - is still parsing,
and it is still the part that can be wrong. What makes a loose reading safe here
is that a misread claim only ever FIRES when the lookup ALSO refutes it. A
sentence this module mistakes for an attribution, whose number the harness did
produce, passes silently. The two halves have to fail together.

## THE LOOKUP IS JOINT, AND THAT IS THE WHOLE SHAPE OF IT

This module shipped asking two questions SEPARATELY - *did X run?* and *is N
anywhere in the pool?* - and never the one that matters, which is **did X
produce N?**. `Ground.ran` was `dict[str, bool]`, a set of names, and every
number from every tool was merged into one flat set, so `note_tool(name, result)`
received both halves of the association and threw it away.

The cost was the reported defect with the roles swapped, and it is the likelier
real-world shape: a model holding REAL numbers and mislabelling their SOURCE.
With a ledger holding `baseline_score=0.7532` from `measure_baseline` and
`state_facts` also having run, both of these reached the user:

    "Your baseline is 0.7532, measured by state_facts."
    "Your baseline is 0.7532, measured by measure_eval_set."

The trophy quote the wall was built for - `0.85 (asserted by state_facts,
measured by measure_baseline)` - was caught only because 0.85 happened to be
unbacked. Widen the pool and the catch disappears: ONE `list_runs` of twenty
rows puts sixty numbers in the flat set, after which *"your baseline is 1.2,
measured by measure_baseline"* passes because 1.2 was a loss value in row twelve.

So `Ground.ran` is now **name -> the numbers THAT tool produced**, the ledger
carries its own per-tool index off the `tool` column each row already had, and
`Ground.produced(tool, token)` is one lookup. The flat pool still exists - as
`Ground.from_tools` and `Ground.backs` - and is still the right question for the
two subjects that are not one instrument: `the harness` generally, and a
labelled fact that names no instrument at all.

### What the joint check does at its edges

* **A number no tool produced this turn but the LEDGER holds.** Still joint,
  against a different table: each ledger row carries the tool that stamped it,
  so `measure_baseline`'s ledger rows are `measure_baseline`'s readings.
* **A number the USER supplied, attributed to a tool.** REFUTED. The user is
  not an instrument. `Ground.backs` still counts what the person typed - because
  arithmetic on what somebody told you is not a fabrication - but no tool's own
  pool contains it, so *"profile_dataset measured 40,000 tickets"* over a
  40,000 the user typed is refuted, and the closing says where the number
  really came from.
* **A number produced in an EARLIER TURN of the same thread.** In scope, and
  backed, IF IT REACHED THE LEDGER - which carries both the value and the tool
  across turns, and is the record that survives. A transient tool result from an
  earlier turn that stamped nothing left no record that anything produced it,
  and this module will not invent one; that was already true of the flat pool,
  so it is a boundary rather than a regression.
* **Two tools that both produced the same number.** Attribution to either is
  true, and both pools contain it, so both pass. Nothing here has to pick.

### One reading per attribution

The per-tool lookup applies to the number an attribution BINDS - the one nearest
the instrument - and not to every number in the frame's reach. *"measure_eval_set
counted 40000 rows, so you have 10000 per class"* attributes 40000; the 10000 is
arithmetic in the same sentence and gets the flat pool.

**AND THE FLAT POOL REFUTES IT, WHICH THIS PARAGRAPH USED TO DENY.** It said the
sentence above was "what keeps the product able to do the thing people most often
ask it for", and the sentence is REFUSED. The pool is what tools returned, what
the ledger stamped, what the user typed and what the brief said; a number the
model COMPUTED inside the sentence is in none of those, by construction. So for
a derived number the second half of the lookup cannot come back "backed", and
the asymmetry at the top of this docstring - a misread claim only fires when the
lookup ALSO refutes it - does not hold for it. That is the same argument this
file accepted when it took the no-number table row back out, and it was missed
here. Nine of ten constructed derivations fire; the previous reader fires on
three, so the family is OLDER than the joint lookup and what tripled it is the
harvested verb list in `ATTRIBUTES` - `counted`, `read` and `detected` open a
frame on exactly the sentences where a model is reasoning out loud on a real
number. Written up, measured and held open in
`tests/test_a_provenance_claim_is_checked_not_believed.py`
(`ArithmeticOnARealReadingTest`), unfixed on purpose: every candidate fix is a
connective vocabulary or a trade, and this module was burned one commit ago for
writing a vocabulary from imagination.

## THE WALL WAS KEYED ON TOOL-NAME GRAMMAR, WHICH IS THE FORM NOBODY WRITES

Every frame below except the last one needs an INSTRUMENT NAMED IN FULL, with
its underscores. That is the sharp half of this module and it is also, on its
own, a wall aimed at the wrong half of the language. Measured on this module,
with a ground that holds no such record:

    STOPPED   "profile_dataset found 340 labeled examples."
    REACHED   "Based on the dataset profile, there are 340 labeled examples."
    REACHED   "Based on what I have inspected, you have 340 labelled examples"

All three are attributed claims about a measurement nobody took. The two that
reached the user are what a language model actually writes; the one that was
stopped is what it almost never writes. A constructed corpus of 40 such
sentences - "based on", "according to", "the data shows", "I found", "you
have", "your dataset contains", "looking at", "from what I can see",
possessives, passive voice, numbers spelled out - scored **0 of 40 stopped**
against the reader this replaces.

Frame 5 is the answer, and the thing that makes it affordable is the asymmetry
at the top of this docstring rather than any cleverness in the reading. It has
no instrument to check, so it checks the OBJECT: a reading-only fact named in
ordinary English, addressed to this user, carrying a number that nothing in
this conversation holds. Give the same sentence a ground where the number is
real and it passes untouched, whatever shape it is in.

## What a claim is, here

Five frames, each one a relation between an INSTRUMENT and a READING - except
the fifth, which is a relation between a DECLARED FACT and a reading, and says
so.

1. **The labelled reading.** A declared fact whose `source:` is `inspect` -
   a fact no one can know without running an instrument - written beside a
   number. `baseline_score: 0.75`, `vram_gb = 8`, `eval_size_n is 120`.

   The fact list is read off `docs/diagnosis_engine.yaml` through
   `evidence.spec()`, never written here. A fact declared `source: ask` -
   `target_score`, `prompt_iterations` - is the user's own answer and is
   deliberately NOT in this frame.

2. **The attributed reading, passive.** A number and `measured by <instrument>`,
   `according to <instrument>`, `reported by <instrument>` - and the keyed forms
   a model writes when it renders a record rather than a sentence:
   `"source": "measure_baseline"`, `(tool: measure_baseline)`.

3. **The attributed reading, active.** `<instrument> measured <number>`,
   `the harness computed <number>`.

4. **The table row.** `| Eval rows | 40,000 | measure_eval_set |`. Three or more
   cells, a registered tool alone in one of them, a number in another. A
   two-cell row is how this product describes its own tools - `| list_runs |
   lists your recent runs |` - so three is the floor.

5. **The reading stated in ordinary English.** A reading-only fact called by
   its PROSE NAME rather than its ledger key, with a number, in a sentence that
   asserts it of this user's machine or this user's data. *"You have 340
   labeled examples"*, *"your VRAM is 24 GB"*, *"the data shows 340 labeled
   examples"*.

   THE PROSE NAMES ARE DERIVED FROM THE SPEC AND NOT WRITTEN HERE.
   `labeled_examples_n` is "labeled examples" and `vram_gb` is "vram", read off
   the same `source: inspect` declarations frame 1 reads - see
   `_reading_subjects`, which also says why a fragment must be two words and
   why the head noun alone would fire across the whole language.

   This frame names NO INSTRUMENT, so unlike frames 2, 3 and 4 it can never
   produce `NO_SUCH_INSTRUMENT`, `DID_NOT_RUN` or `NOT_ITS`. It produces
   `MISMATCH` when the ledger holds that fact at another value, and `NOT_OURS`
   when nothing in this conversation holds the number at all. It is frame 1
   with the fact named in English, and it is refuted by the same lookup.

An INSTRUMENT is a registered tool named in full (`measure_baseline`, with the
underscores - a model writing "measure baseline" in prose is writing English,
and matching that would read half the corpus as attributions), the harness named
as a measurer (`the harness`, `the diagnosis engine`), or - see below - a name
that is SHAPED like a tool and is not one.

## What refutes a claim

* **No such instrument.** The sentence attributes a reading to
  `measure_accuracy`, and nothing in this harness is called that, so nothing
  could have measured anything with it. THE SHARPEST REFUTATION THERE IS, and
  before this it was the only one that produced no refutation at all: an
  unregistered name opened no frame, so the more brazen the fabrication the less
  visible it was. An unregistered name is admitted only where a VERB or an
  explicit attribution phrase says a measurement is being claimed - never off a
  bare preposition, because `from support_tickets` is a file and not an
  instrument.
* **The instrument did not run.** That tool did not run in this turn and has
  stamped nothing in this thread's ledger. The claim's SUBJECT is refuted.
* **The ledger says something else.** Frame 1 named a fact this thread holds,
  and gave a different value for it. Worse than an unattributed number, because
  it looks checkable and is wrong.
* **The reading is not ours.** The number is not among the numbers this harness
  produced - not in any tool result this turn, not in the ledger, and not one the
  user typed. The claim's OBJECT is refuted.
* **The instrument did not produce it.** The number is real and something here
  holds it - but not the instrument the sentence named. The refutation names
  what did, because that is the correction the user needs.

## What this does NOT cover, said out loud

The register this codebase uses, and the habit is why several of these defects
were ever visible in the first place.

- **A number with no attribution at all.** "Your baseline is around 0.75" names
  no instrument and no declared fact. Not decidable by lookup, because there is
  nothing to look up. The sentry's shape of problem, not this one's. Frame 5
  narrows this rather than closing it: a fact named in prose IS now decidable,
  so *"your baseline score is 0.75"* is checked while *"your baseline is around
  0.75"* still is not, because `baseline` alone is not the fact's name.

- **WHAT FRAME 5 STILL MISSES, COUNTED RATHER THAN DESCRIBED.** Thirty
  fabrications written afterwards, in shapes the frame was NOT designed around,
  score **16 of 30 stopped**. That is the honest number and it is not rounded
  up. The fourteen are pinned as reaching the user in
  `tests/test_a_fabrication_in_ordinary_english_is_still_a_fabrication.py`
  (`WhatStillGetsThroughTest`), so closing one of them turns that file red and
  somebody has to come and delete the row. Two families cover almost all of
  them:

  * **The head noun on its own.** *"Your dataset contains 40,000 rows"*,
    *"there are 340 examples in the training split"*, *"your GPU has 24 GB of
    memory"*. `tabular_rows` is read as "tabular rows" and not as "rows",
    because "rows" is a word about tables, spreadsheets and query results, and
    a wall listening for it would fire on all of them. Closing this needs a
    noun vocabulary that the spec does not contain, and this module has already
    been burned once for writing a vocabulary from imagination.
  * **No attribution cue at all.** *"340 labeled examples."*, *"Labeled
    examples: 340"*, *"Roughly 340 labeled examples are present."* Frame 5
    requires the sentence to assert the number OF THIS USER - see
    `_asserts_of_this_project` - and that requirement is the only thing
    standing between this wall and every sentence the product says about the
    field rather than about the person. Dropping it to catch these three would
    refuse *"a dataset of 500 labeled examples is usually the floor for a
    useful LoRA"*, which is the product working.
- **A tool named in prose rather than in full.** "the baseline measurement says
  0.75" is the same claim; `measure_baseline` is the only spelling this catches.
- **A LABELLED fact whose number some OTHER tool produced.** `eval_size_n: 1.2`
  on a turn where `list_runs` returned a 1.2 passes, because frame 1 names no
  instrument and the flat pool is the honest question to ask of it. Tightening
  it to "the tool that RESOLVES this fact" would refute the most ordinary thing
  a model does with a number the user typed - repeat it back under the name of
  the fact it answers - and that trade is the wrong way round. The `mismatch`
  refutation covers it whenever the ledger holds the fact at all.
- **Rounding is given to the model, and the unit it declares is taken from it.**
  "75%" against a measured `0.7532` passes. "0.75%" against a measured `0.75`
  does NOT, because `%` is a unit and a model that writes one has said which
  units it is in. See `_numeral`.
- **The word `exactly` is read.** "exactly 0.75" against `0.7532` is refuted,
  because a model that says `exactly` has withdrawn the rounding this wall
  otherwise grants it.
- **Non-numeric provenance.** "measure_baseline found your prompt is the
  problem" attributes a FINDING rather than a reading, and is not checked. THE
  ONE EXCEPTION IS THE TABLE ROW - see below - and it is an exception on
  purpose.
- **A claim about another thread or another machine.** The ledger this reads is
  `evidence.rows_for(thread_id)`. A number true of somebody else's project is
  refuted here, and that is the right answer.
- **A number a tool ECHOED back out of its own arguments.** `Ground.ran` reads
  every number in a tool RESULT, and `state_facts` results quote the values
  their caller supplied. So a model that calls `state_facts(baseline_score=0.85)`
  and then writes "0.85, measured by state_facts" in the same turn is backed by
  its own input. The LEDGER half of that route is closed - `by_tool` indexes
  MEASURED rows only, so the row `state_facts` wrote is not its reading - and
  the RESULT half is not, because "which numbers in this payload came out of
  the arguments" is not something this module can ask without the arguments,
  and subtracting them would refute *"measure_baseline scored the 200 rows you
  asked for"*. It is the laundering family, it belongs with
  `tests/test_no_tool_can_mint_a_measurement.py`, and it is named here rather
  than closed with a guess.

### The attribution with no number in it, and why it is NOT here

A live turn WITH ZERO TOOL CALLS handed the user a markdown table attributing
`eval_size_n`, `vram_gb`, `ram_gb`, `disk_free_gb` and `accelerator` to
`inspect_hardware`. Every value was `N/A`, so there was no numeral, and a
numbers-only wall had nothing to hold. It is a false attribution with no number
in it, and the brief is right to ask whether this wall widens or whether it
belongs somewhere else.

**IT WAS WIDENED, MEASURED, AND TAKEN BACK OUT.** The widening was one shape
only - a table row of three or more cells carrying a declared reading-only
fact, a value, and a registered tool that did not run - on the argument that
only the SUBJECT is refutable there, so nothing can be wrongly refuted about
the reading. That argument was wrong, and the harvest said so in the first
2,088 sentences of live reporting output:

    | ram_gb       | Infered (not measured) | inspect_hardware |
    | vram_gb      | Infered (not measured) | inspect_hardware |
    | disk_free_gb | Infered (not measured) | inspect_hardware |
    | accelerator  | Infered (not measured) | inspect_hardware |

Four fires, on a turn where nothing ran, on a model DOING THE RIGHT THING - it
named the instrument that would read each fact and said in the value cell that
it had not been read. `N/A` and `Infered (not measured)` are the same shape to
any reader, and telling them apart needs a vocabulary of disclaimers, which is
a heuristic in the one frame that has no lookup to check it against.

**AND THAT IS THE STRUCTURAL REASON, not just the measurement.** Every other
frame here is safe because a misread claim still has to survive a lookup: the
harness produced the number, or it did not. A frame with NO NUMBER has no
second half, so a misreading of it fires unconditionally. It is the one shape
in this module where a loose reading is not cheap, and the asymmetry at the top
of this docstring is exactly what it gives up.

So where does it belong? Not in a sentence-level reader at all. The defect is a
model RENDERING THE FACT LEDGER ITSELF, and the ledger already has a rendering
with real origins in `evidence.ledger_view`. Two places can hold it and this is
not either: the instruction set, which can tell the model to point at that view
rather than compose its own table, and a whole-reply check, which can see all
five rows as one object instead of five sentences that each look like a
capability statement. `_Sentry` feeds this module one sentence at a time, and a
table is not a sentence.

## Both directions, measured, and one of them measured this file wrong twice

**The constructed probe.** Thirty fabrications, one per demonstration of the
eight mechanisms, each written with the ground that makes it a fabrication
rather than a report - plus forty-seven sentences that MUST pass. The previous
reader was lifted out of git and run over the identical rows first, as a
positive control:

                                 stopped   reached the user   false catches
      the reader this replaces      2/30          28              0 of 47
      this one                     30/30           0              0 of 47

The two it already stopped are the table rows whose fact label happens to sit
beside its value once the pipes are flattened. The other twenty-eight are the
brief's own demonstrations.

**The live harvest.** 592 turns of granite4-hermes on a scratch database, both
walls RECORDING rather than refusing - a wall that refuses truncates the reply,
so the sentences after the first catch are never produced and never counted -
across six question banks. **11,404 sentences.** Both readers were run over the
identical corpus.

      bank            turns   sentences   stopped   of those, false
      ordinary          204       3,682         0         0
      reporting         112       2,088         0         0
      blunt              84         645         0         0
      adversarial       120       1,882         4         0
      mixed              72       3,107        15         0

Every one of the nineteen was read individually rather than counted; every one
is a fabricated measurement on a turn where nothing ran. The previous reader
stops the same nineteen and no others, which is what the probe predicts: the
model's own live fabrications are all the LABEL frame, which was never the
half that was broken.

**THE ZERO IN THAT LAST COLUMN DOES NOT COVER EVERYTHING, AND IT WAS READ AS
THOUGH IT DID.** A constructed probe of arithmetic written beside a true
attribution - the shape this docstring elsewhere offered as the product
working - fires nine times in ten. Whatever those 11,404 sentences contained,
they did not contain that, and no harvest artifact survives in the tree for
anyone to check which of the two it is. The zero is UNVERIFIED rather than
wrong, and the figures in this section should be read as a claim this file
makes about a run nobody can now reproduce, not as a measurement in evidence.
See `## One reading per attribution` above.

**Where the joint lookup is exposed, and what it cost.** 69 of those 11,404
sentences name a tool and a number on a turn where tools actually ran, and 42
of them bind an attributed reading to a named instrument - which is precisely
the set the per-tool lookup can newly refuse. All 42 attribute CORRECTLY and
all 42 pass. That is the price of `NOT_ITS` measured rather than assumed, and
it is zero.

**AND THE HARVEST CAUGHT THIS FILE OUT TWICE**, which is the only reason either
number above is worth anything:

* a widening to attributions with no number in them fired four times on honest
  reporting output and was REMOVED - see the section above;
* `listed` in `ATTRIBUTES` fired once on *"The harness has listed 28 tools
  that are registered on this machine"*, which is TRUE, and produced
  `Ground.briefed`.

Both were found by reading stops rather than by counting them.

**The live fabrications the previous reader already caught** - the eleven in
`tests/test_a_provenance_claim_is_checked_not_believed.py` - are all still
caught. Nothing was traded.

## Frame 5's worst defect was NEARNESS READ AS ABOUTNESS, and it was found late

Frame 5 shipped binding the NEAREST number within `_SUBJECT_REACH` of a fact's
prose name and calling it that fact's value, with nothing asking whether the
number was a reading OF THAT FACT. Twenty-two honest sentences whose number is
not a reading produced NINETEEN false catches: *"in step 2"*, *"took 45
seconds"*, *"in 2 files"*, *"has 3 sections"*, *"column 3"*, *"job 7"*.

TWO OF THEM ARE THE FOUNDING DEFECT INVERTED. On a turn where
`inspect_hardware` really ran and stamped `vram_gb = 8.0`, the true sentence
*"Checking your VRAM takes 2 seconds"* was refuted as a MISMATCH against the
real 8.0 - the wall killing a reply mid-stream on a turn where every number was
real, then telling the person to run a tool that had run seconds earlier. That
is not a missed fabrication; it is the "worse than no wall" failure this file
names three paragraphs above and then committed.

`_reads_the_subject` is the answer and the separation is STRUCTURAL rather than
a word list about steps and seconds: in all forty attributed fabrications the
number reaches its fact through nothing but a copula, a preposition or an
attribution verb, and in all nineteen false catches a fresh CONTENT NOUN stands
in the way. See `_LINKS_A_READING`, and `ANumberThatIsNotAReadingTest` for the
corpus, which IS checked in.

## The frame-5 widening of `_opens_hypothetically` cost the other four frames

`_opens_hypothetically` read the first word; frame 5 needed three, because
*"Let's say you have 340 labeled examples"* puts the supposition in second
position. It was widened IN PLACE, for the whole module, and that silently
regressed the instrument frames - *"I should add that inspect_hardware measured
24 GB of VRAM"* was caught before and reached the user after, because a modal in
second position is a discourse marker and not a supposition. The reach is now
1 for the four instrument frames and 3 for frame 5 only. This file makes exactly
this argument about `_WANTED_NOT_READ` - *"Widening a decline across frames that
did not need it would be trading away catches for nothing"* - and then did it
one guard over.

## Frame 5, measured in both directions, and the false-catch side cost more

Two corpora, constructed - and said to be CONSTRUCTED, because no live harvest
was run for this change and calling a designed corpus a harvest is the thing
this file did wrong one commit ago.

      corpus                                     before      after
      attributed fabrication   (must stop)       0 / 40     40 / 40
      honest prose             (must pass)   0 caught    0 caught  of 51

Then a second pair, written AFTERWARDS and aimed at shapes the frame was not
designed around, because a wall that catches everything its author thought of
proves only that its author wrote both halves:

      harder fabrication       (want stopped)    0 / 30     16 / 30
      harder honest prose      (must pass)   0 caught    0 caught  of 20

**THAT SECOND PAIR CANNOT BE RE-RUN BY ANYBODY, INCLUDING WHOEVER WROTE IT.**
The thirty adversarial fabrications and the twenty adversarial honest sentences
were never checked in. Only the FOURTEEN MISSES survive, as
`WhatStillGetsThroughTest.STILL_REACHES`; the sixteen that were caught, the
twenty honest rows, and the six that fired before `_WANTED_NOT_READ` existed are
all gone. So the numerator, the denominator and the 30% false-catch rate that
`_WANTED_NOT_READ` is justified by are unverifiable, and the six sentences
quoted below are a recollection rather than a record.

The row is left standing because deleting it would hide that the measurement
happened, and the guard it bought is real - every word in `_WANTED_NOT_READ` has
a pinned test in `TheGuardsAreNotDecorationTest`. But it is a claim this file
makes about a run nobody can reproduce, which is the exact failure
`scripts/harvest_the_walls.py` was written into this tree to end. The FIRST pair
above is not in that position: both its corpora are checked in, and re-running
them against `git show HEAD:app/provenance.py` reproduces 0/40 -> 40/40 and
0-caught-of-51 exactly.

**THE FIRST CUT OF THIS FRAME CAUGHT 6 OF THOSE 20 HONEST SENTENCES**, which is
a 30% false-catch rate on adversarial input, and it is the whole reason
`_WANTED_NOT_READ` and `_opens_hypothetically` exist. All six were numbers
somebody WANTS rather than numbers anything READ - *"you should aim for 1,000
labeled examples"*, *"your target is 1,000 labeled examples"*, *"your goal of
5,000 labeled examples is realistic"*, *"to fine-tune well you typically need
1,000 labeled examples"* - plus *"let's say you have 340 labeled examples"*,
where the word that makes the sentence hypothetical is the second one and this
module was only ever reading the first. Every word in `_WANTED_NOT_READ` is a
word that fired. A wall at 14% interruption and a 100% false-catch rate is on
this repository's record already, and it is worse than no wall: it teaches the
person to click past the one time it is right.

**AND TWO GUARDS ALREADY HERE WERE WRONG IN THE OTHER DIRECTION.** `_NOT_YET`
read the `can` in *"From what I can see"* as a plan and dropped the claim - on
the brief's own probe sentence, after the frame had read it correctly - so
`can see` and `can tell` are exempted and every other `can` still guards. And
widening the hypothetical scan past the first word collided with `say`, which
is in `_HYPOTHETICAL` and in `ATTRIBUTES` both: *"let's say you have 340"* is a
supposition and *"the numbers say you have 340"* is a fabrication, same word,
same position, and only the word in front of it tells them apart.

The finding reproduces at will - here is one, verbatim, from a turn where
**only `state_facts` ran**:

    The harness has measured several facts during its current session:
    - **vram_gb**: `24.0` (measured by inspect_hardware)
    - **baseline_score**: `0.85` (asserted by state_facts, measured by
      measure_baseline)
    - **eval_size_n**: `50000` (asserted by state_facts, measured by
      measure_eval_set)

An entire fact ledger, invented, wearing three instruments that never ran.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping

from app.tools import evidence


#: What this module calls each of its refutations, in the notice payload and in
#: the closing sentence. Strings rather than an enum because they are written
#: into an event payload and read back out of one.
NO_SUCH_INSTRUMENT = "no_such_instrument"
DID_NOT_RUN = "the_instrument_did_not_run"
NOT_OURS = "the_reading_is_not_ours"
NOT_ITS = "the_instrument_did_not_produce_it"
MISMATCH = "the_ledger_says_otherwise"
#: The number IS on record, about the thing the sentence named - on a different
#: count than the sentence gave it. See `_as_a_subject`.
ANOTHER_COUNT = "the_record_holds_it_on_another_count"

#: SHARPEST FIRST, and this order is the whole of how one sentence carrying two
#: claims is reported. "baseline_score: 0.75 (measured by measure_baseline)" is
#: a label AND a passive attribution; "there is no such tool" is a better thing
#: to tell somebody than "nothing here holds that number", because it names
#: what went wrong. Declared here rather than written inline so that
#: `tests/test_a_provenance_claim_is_checked_not_believed.py` can derive the
#: list and check that every one of them is spoken - by `refusal_sentence`, and
#: by `conductor._REFUTATIONS` - rather than reading as nothing.
REFUTATIONS = (
    NO_SUCH_INSTRUMENT, DID_NOT_RUN, MISMATCH, ANOTHER_COUNT, NOT_ITS, NOT_OURS
)

#: The `conductor.notice` reason written when a sentence the wall would have
#: refuted turns out to cite the record exactly. NOT a refutation, so not in
#: `REFUTATIONS`: nothing is withheld, and the notice is the annotation.
CITATION_MATCHED = "citation_matched_the_record"

#: The subject of a claim whose instrument is the harness itself rather than a
#: named tool. `_refute` reads it and knows not to ask whether a tool ran.
THE_HARNESS = "the harness"

#: How the harness names itself when it is claimed to have measured something.
#: `run_diagnosis` is deliberately absent: it is a registered tool and is
#: matched as one, which gives the sharper of the two refutations.
#:
#: PUBLIC BECAUSE THERE IS A SECOND CLAIM WITH THE SAME SUBJECT.
#: `conductor.speaks_for_the_engine` asks whether a sentence puts a TRAINING
#: VERDICT in this harness's mouth, and the names it has to recognise are these
#: names. Two copies of this tuple would be two vocabularies drifting apart in
#: the two walls that most need to agree about who "the harness" is, so there
#: is one and the conductor reads it. Nothing about the list changed when it
#: lost its underscore.
HARNESS_NAMES = (
    ("the", "harness"),
    ("this", "harness"),
    ("the", "diagnosis", "engine"),
    ("the", "harness's", "diagnosis", "engine"),
    ("the", "harness's", "engine"),
    ("the", "engine"),
    ("the", "diagnosis"),
)

#: A verb that says an instrument produced a reading. NOT a verb that says an
#: instrument exists or would be useful: `run`, `use` and `call` are absent, so
#: "run measure_baseline on 120 rows" is an instruction and not a claim.
#:
#: THIS LIST WAS WRITTEN FROM IMAGINATION AND IT SHOWED. Seven of the ten verbs
#: a reader would reach for first were missing - `counted`, `read`, `detected`,
#: `shows`, `says`, `estimated`, `logged` - and COUNTING IS WHAT THIS PRODUCT'S
#: DATASET TOOLS DO, so *"profile_dataset counted 40,000 support tickets"* went
#: through while *"profile_dataset measured 40,000 support tickets"* did not.
#: The additions below are HARVESTED rather than guessed: every word here past
#: the original list is one granite4-hermes actually wrote within five words of
#: a registered tool name across 3,682 harvested live sentences, kept only
#: where it asserts a READING. The ones it wrote that assert a capability instead -
#: `allows`, `ensures`, `executes`, `proposes`, `suggests`, `can`, `will` - are
#: deliberately absent, because "list_runs allows 20 rows" is a description.
#:
#: LISTING IS NOT MEASURING, and `list`/`lists`/`listed` are the words the
#: harvest took back OUT after they went in with the rest. What put them under
#: suspicion was a live false catch - *"The harness has listed 28 tools that
#: are registered on this machine"* - and that particular sentence is now
#: answered at the root, by `Ground.briefed`: 28 came from the brief the
#: harness wrote, so it is backed. The verbs stay out for their own reason.
#: `list` is also an infinitive, so *"run list_runs to list 20 rows"* is an
#: instruction that reads as an attribution, and a number beside `listed` is a
#: count of what was SHOWN far more often than a reading - the same thing `top`
#: and `limit` are. What that leaves uncaught is *"list_runs listed 20 runs"*
#: on a turn where `list_runs` did not run, declared here rather than bought
#: with the instruction above.
#:
#: Present tense is here beside past tense because "measure_baseline reports
#: 0.75" is the same assertion as "reported". The cost is that a sentence
#: describing what a tool DOES - "measure_baseline scores at most 200 rows" -
#: reads as an attribution; it is refuted only if 200 is also a number the
#: harness never produced, and `_BOUNDS_NOT_READINGS` covers the shape that
#: actually occurs.
#: PUBLIC FOR THE SAME REASON `HARNESS_NAMES` IS. A verb that says an
#: instrument produced a reading is most of a verb that says the engine handed
#: down a verdict, and this list is HARVESTED from live output rather than
#: imagined - which is the property `conductor._SPEAKS` wants and cannot get by
#: writing its own. The conductor adds the four verbs a DECISION is reported
#: with and this list does not have, because a decision is not a reading.
ATTRIBUTES = frozenset(
    """measured measures reported reports computed computes calculated
    calculates returned returns produced produces recorded records observed
    scored scores found finds determined determines yielded yields
    counted counts count read reads detected detects detect
    shows showed show says said say estimated estimates estimate
    logged logs log checked checks check
    indicates indicated indicate identified identifies identify
    flagged flags flag gave gives give displayed displays display
    analysed analyses analyzed analyzes examined examines
    ranked ranks saw sees
    inspect inspects inspected""".split()
)
# `inspect` JOINED THE LIST FROM THE HARVEST, not from a brainstorm - which is
# the only way this list is allowed to grow. The sentence that added it is
# `- My hardware specs were inspected (inspect_hardware):`, written by the
# model as the lead-in of a bullet block, and the verb of the attribution was
# missing from a list that already held `measured`, `examined` and `analysed`
# in a product whose central instrument is CALLED `inspect_hardware`.
# Measured before it was added: +2 catches on the harvested fabrications and
# ZERO false catches on the 636 honest sentences. The noun `inspection` was
# deliberately NOT added - this is a verb list, and `_LINKS_A_READING` is built
# from it, so a noun in here would let a number cross a content noun.


#: The prepositions that hang an instrument off a reading. `measured BY x`,
#: `according TO x`, `PER x`.
_BY = frozenset({"by", "from", "via"})
_ACCORDING = (("according", "to"), ("based", "on"), ("as", "reported", "by"))

#: The KEYS a model writes when it renders a record rather than a sentence.
#: `{"metric": "baseline", "value": 0.91, "source": "measure_baseline"}` and
#: `(Tool: measure_baseline)` are the same claim as "measured by
#: measure_baseline", written for a machine. `_flatten` throws the punctuation
#: away, so what is left to match on is the key word itself.
_KEYED_SOURCE = frozenset(
    {"source", "sources", "tool", "tools", "instrument", "measured_by",
     "reported_by", "provenance", "origin", "measured", "reported"}
)

#: A word in front of a number that makes it a BOUND or a REQUIREMENT rather
#: than a reading. "scores at most 200 rows" and "needs at least 20 examples"
#: describe a tool's behaviour; neither is a claim that it read anything.
#: `limit` and `sample` are here because they are this product's own words for
#: a cap, and a live adversarial reply used one: *"Listed by `list_runs` (limit
#: 20, provenance: measured)"* is the model saying how many rows it ASKED for,
#: not what anything read.
_BOUNDS_NOT_READINGS = (
    ("at", "most"), ("at", "least"), ("up", "to"), ("no", "more", "than"),
    ("fewer", "than"), ("more", "than"), ("less", "than"), ("under",),
    ("over",), ("limit",), ("sample",), ("top",), ("first",), ("last",),
    ("above",), ("below",), ("beyond",),
)

#: The same thing written AFTER the number instead of in front of it. "lists
#: your 20 most recent runs" is `top 20` with the words in the other order: a
#: SELECTOR, saying which rows come back, not a count of anything that was
#: read. This is the shape the live model actually writes when it describes a
#: tool - *"| list_runs | lists your 20 most recent runs |"* - and without it
#: the widened verb list turns every such description into an attribution.
_SELECTORS_NOT_READINGS = (
    ("most", "recent"), ("latest",), ("recent",), ("newest",), ("oldest",),
    ("per", "page"), ("at", "a", "time"), ("largest",), ("smallest",),
    ("longest",), ("shortest",),
)

#: The words that WITHDRAW the rounding this wall otherwise grants. "Your
#: baseline is exactly 0.75" against a held `0.7532` is refuted: the model has
#: said which number it means, and it is not that one.
_EXACTLY = frozenset({"exactly", "precisely", "exact"})

#: THE SECOND PERSON, which is how a model says a number is THIS USER'S.
#: "You have 340 labeled examples" and "your VRAM is 24 GB" are claims about a
#: particular machine and a particular dataset, and there is exactly one way to
#: learn either: run an instrument. A sentence in the third person -
#: *"a dataset of 500 labeled examples is usually the floor"* - is a statement
#: about datasets in general and asserts nothing about this one, which is why
#: the pronoun is doing real work here rather than decorating a list.
_SECOND_PERSON = frozenset({"you", "your", "yours", "you've", "you're", "youve"})

#: The verbs of POSSESSION rather than of measurement. *"The dataset contains
#: 340 labeled examples"* is the same claim as *"you have 340 labeled
#: examples"* with the owner named instead of addressed.
#:
#: `has` AND `have` ARE DELIBERATELY ABSENT and their absence is the whole
#: reason this is a separate list from `ATTRIBUTES`. Every sentence a model
#: writes about anything at all is liable to contain "has"; the possessive
#: reading of it - *"your dataset has 340"* - is already covered by
#: `_SECOND_PERSON`, so admitting the bare verb would buy nothing and widen
#: the frame across the whole language.
_HOLDS = frozenset({"contains", "contain", "holds", "hold", "includes", "include"})

#: The tail tokens of a declared fact name that are a UNIT or an INDEX rather
#: than part of what the fact is called. `labeled_examples_n` is "labeled
#: examples", `vram_gb` is "vram", `retriever_recall_at_k` is "retriever
#: recall". Stripped from the END only, so `tokens_available` keeps both words.
_UNIT_WORDS = frozenset({"n", "k", "gb", "mb", "kb", "tb", "ms", "usd", "at"})

#: How far from the noun it names a number may sit, in words. Wider than
#: `_LABEL_REACH` because prose puts words between them that a ledger key does
#: not: "your labeled examples come to 340" is three past the noun, and "a
#: baseline score of 0.82" is two.
_SUBJECT_REACH = 4

#: A number somebody WANTS rather than a number anything READ. "You should aim
#: for 1,000 labeled examples" and "your target is 1,000 labeled examples" name
#: a reading-only fact, address it to this user, and put a number on it - every
#: condition frame 5 asks for - and neither one claims a measurement. They are
#: the product doing its job: telling somebody what they would need.
#:
#: THIS LIST IS THE PRICE OF FRAME 5 AND IT WAS MEASURED, NOT IMAGINED. Twenty
#: honest sentences aimed at the new frame's weak spots produced SIX false
#: catches before this existed - "you should aim for", "your target is", "your
#: goal of", "you typically need" - which is a 30% false-catch rate on
#: adversarial input and precisely the failure this repository already has on
#: its record: a wall that interrupts honest turns trains the user to ignore
#: it. Every word below is one that fired.
#:
#: IT GUARDS FRAME 5 ONLY. The other four frames name an instrument, and
#: "measure_baseline should report 0.75" is already declined by `_NOT_YET`.
#: Widening a decline across frames that did not need it would be trading away
#: catches for nothing.
_WANTED_NOT_READ = frozenset(
    """should need needs needed require requires required aim aims aiming
    target targets goal goals want wants wanted recommend recommends
    recommended suggest suggests suggested ideally try trying collect
    collecting gather gathering minimum maximum""".split()
)


#: THE WORDS A READING MAY BE SEPARATED FROM ITS FACT BY, and nothing else.
#: This is the answer to the frame's own worst defect, so it is worth stating
#: what the defect was: `_SUBJECT_REACH` finds the NEAREST number within four
#: words of a fact's prose name and frame 5 then called that number the fact's
#: value, with nothing asking whether it was a reading OF THAT FACT at all.
#: Every ordinal, duration, file count, section number and queue position that
#: happened to land near the noun was read as the reading and then refuted,
#: because of course "step 2" is not in the ledger.
#:
#: MEASURED, AND IT IS THE WORSE HALF OF THE FAILURE. Twenty-two honest
#: sentences whose number is not a reading produced NINETEEN false catches
#: before this existed. Two of them were the founding defect inverted: on a
#: turn where `inspect_hardware` really ran and stamped `vram_gb = 8.0`, the
#: true sentence *"Checking your VRAM takes 2 seconds"* was refuted as a
#: MISMATCH against the real 8.0 - the wall killing a reply mid-stream on a
#: turn where every number was real, and then telling the person to run a tool
#: that had just run. A wall that interrupts honest turns teaches the user to
#: ignore it, which is worse than no wall.
#:
#: THE SEPARATION IS STRUCTURAL AND WAS READ OFF BOTH CORPORA, not guessed. In
#: every one of the forty attributed fabrications the number reaches its fact
#: through nothing but a copula, a preposition or an attribution verb - *"your
#: baseline score IS 0.82"*, *"a baseline score OF 0.82"*, *"your labeled
#: examples COME TO 340"*. In every one of the nineteen false catches a fresh
#: CONTENT NOUN stands in the way - *"in STEP 2"*, *"took 45 SECONDS"*, *"in 2
#: FILES"*, *"has 3 SECTIONS"*. A noun between a fact and a number means the
#: number belongs to that noun.
#:
#: CLOSED CLASSES ONLY. Every group below is either a closed class of English
#: (copulas, articles, the prepositions that hang a value off a noun) or a list
#: this module already harvested rather than imagined (`ATTRIBUTES`, `_HOLDS`,
#: `_BY`, `_UNIT_WORDS`). The one open-class group is the AMOUNTS-TO verbs, and
#: it is short, closed in practice, and every member of it appears in the
#: fabrication corpus as the only thing between a fact and its number.
_LINKS_A_READING = (
    frozenset(
        """is are was were be been being am 's 're
        a an the its their his her your our my this that these those
        of at to as with in into on
        roughly approximately about nearly around some just only currently
        still now already also here there and or not no
        come comes came coming total totals totalled totaling totalling
        number numbers numbered reach reaches reached
        stands stand stood sits sit measured""".split()
    )
    | ATTRIBUTES
    | _HOLDS
    | _BY
    | _UNIT_WORDS
    | frozenset(
        """gigabyte gigabytes megabyte megabytes kilobyte kilobytes
        terabyte terabytes gig gigs byte bytes percent""".split()
    )
)


#: THE WORDS A SENTENCE CHANGES CLAUSE ON. Exactly the coordinators and
#: relativisers that start a new predication, and only where a COMMA has
#: already marked the break - `and` with no comma in front of it joins two
#: nouns rather than two clauses, and splitting on it would cut "16 GB of RAM
#: and 8 GB of VRAM" in half.
_CLAUSE_JOINERS = frozenset(
    {"so", "and", "but", "because", "which", "while", "though"}
)


def _clause_marks(words: "_Words") -> list[int]:
    """Which clause each word belongs to, as a running index.

    A guard scoped to a sentence is a guard one comma wide. This is the ruler
    that lets `_stated_readings` ask about the clause holding the number
    instead of about every word the model happened to write beside it.

    Two breaks, and both are punctuation the model wrote rather than grammar
    this module inferred: a COMMA followed by a coordinator, and a SEMICOLON.
    `_flatten` keeps both - the semicolon was added to its surviving set for
    this, since it used to be flattened to a space and a clause boundary
    cannot be read off a space.
    """
    marks = [0] * len(words)
    current = 0
    for index in range(len(words)):
        previous = words.at(index - 1).rstrip("\"')]")
        if (
            index > 0
            and previous.endswith(",")
            and words.bare_at(index) in _CLAUSE_JOINERS
        ):
            current += 1
        marks[index] = current
        if words.at(index).rstrip("\"')]").endswith(";"):
            current += 1
    return marks


def _reads_the_subject(
    words: "_Words", start: int, last: int, spot: int
) -> bool:
    """Whether the number at `spot` is a READING of the fact at `[start, last]`.

    Nearness is not aboutness. This is the predicate frame 5 did not have, and
    without it the frame read any numeral that happened to sit within
    `_SUBJECT_REACH` of a fact's name as that fact's value. See
    `_LINKS_A_READING` for the nineteen honest sentences that measured it.

    Two questions:

    * **Is it PARTITIVE?** A number followed by `of` counts a subset of
      whatever comes next - *"1 OF the 28 registered tools"* - so it is a
      reading of that, not of this fact. Only on the far side: `of` in FRONT
      of a number is how a reading is written (*"a baseline score of 0.82"*).
    * **Does anything but a linker stand in between?** A content noun between
      the fact and the number is a noun the number belongs to.

    A number INSIDE the subject phrase is left alone: it is not separated from
    the fact by anything, which is the whole question this asks.

    BOUNDS ARE ALREADY GONE BEFORE THIS RUNS and this function deliberately
    does not re-ask. `_Words.numbers_between` filters `_is_a_bound` itself, so
    *"up to 340 labeled examples"* and *"your first 340 labeled examples"* never
    reach here. An explicit check was written here first, and the mutation that
    was supposed to prove it necessary came back GREEN - it was dead code
    dressed as a guard, which is worse than no guard because it reads like one.
    """
    if spot < start:
        between = range(spot + 1, start)
    elif spot > last:
        if words.bare_at(spot + 1) == "of":
            return False
        between = range(last + 1, spot)
    else:
        return True
    return all(words.bare_at(index) in _LINKS_A_READING for index in between)

#: How far a frame may reach between its own parts, in words. Wider than the
#: sentry's three because an attribution is written round the number rather
#: than next to it - "0.75 (measured by measure_baseline)" is four, and
#: "the harness measured a baseline score of 0.75" is five.
_REACH = 6

#: How far past an instrument its verb may sit. Two was too tight for the shape
#: a model writes when it explains itself - *"The harness, which ran first,
#: measured 40000 rows"* puts a whole relative clause in between - and a verb
#: is the evidence that a reading is being claimed, so reaching for it is the
#: cheap direction.
_VERB_REACH = 5

#: How close a number must sit to the fact it is labelling, in words. Two:
#: `baseline_score: 0.75` is one and `eval_size_n is 120` is two. Anything
#: wider stops being a label and starts being a sentence about two things.
_LABEL_REACH = 2

#: The words a label may be written ACROSS. A table cell wall is one of them,
#: because `| baseline_score | 0.75 |` is a label with a pipe in it.
_LABEL_JOINERS = ("is", "are", "was", "were", "of", "at", "|", "")

#: A sentence opening that makes what follows hypothetical rather than
#: asserted. "If your baseline were 0.75, fine-tuning would be worth it" is the
#: model reasoning openly and MUST pass - it is not claiming anything was read.
#: The same list the sentry uses, for the same reason, plus `say` and `suppose`.
_HYPOTHETICAL = frozenset(
    {"if", "unless", "when", "whenever", "once", "suppose", "supposing",
     "say", "imagine", "assuming", "hypothetically", "were", "should"}
)

#: A word anywhere in the reach of a frame that makes the attribution something
#: the model is PROPOSING rather than REPORTING. "measure_baseline would report
#: your real score" is a plan; "will be measured by measure_baseline" is a next
#: step. Neither displays a number as a finding.
#:
#: `can see` AND `can tell` ARE EXEMPTED FROM `can`, and the exemption is a
#: measured one rather than a tidy-up. *"From what I can see, you have 340
#: labeled examples"* is the brief's own probe sentence and one of the commonest
#: shapes a model states a fabricated reading in - and it was reaching the user
#: through this regex even after frame 5 read it correctly, because `can`
#: matched and the whole claim was dropped as a plan. "I can see X" and "as far
#: as I can tell" are PRESENT PERCEPTION, the opposite of a next step. Every
#: other `can` - the capability sense, "list_runs can return 20 rows" - still
#: guards, which is the reason the exemption is two verbs and not the word.
_NOT_YET = re.compile(
    r"\b(?:would|will|could|might|may|can(?!\s+(?:see|tell))|shall|about to|"
    r"going to|once|after|when|if|until|before|hypothetically|suppose)\b"
)

#: What counts as a number. Thousands separators first, so `40,000` is one
#: number and not `40` beside `000`. A trailing `%` is part of it.
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|\d+(?:\.\d+)?%?")

#: The shape of a tool name. Lower case, underscores, no dots - so
#: `measure_accuracy` is one and `eval_set.jsonl` is not. Used ONLY to catch a
#: name that is not in the registry; a name that IS in the registry is matched
#: by the registry.
_TOOL_SHAPED = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")

#: How close two numbers have to be to count as the same reading. Compared at
#: the WRITTEN number's own precision, so `0.75` matches a measured `0.7532`
#: and `40,000` does not match a counted `39,847`. Rounding is the model being
#: readable, not the model inventing.
_TOLERANCE = 1e-9


def _flatten(text: str) -> str:
    """Lower case, one kind of space - and underscores and pipes survive.

    `conductor._normalise` throws underscores away, which is right for reading
    English and wrong here: `baseline_score` and `measure_baseline` are the
    exact strings this module looks things up by, and a normalisation that
    turns them into two words each would make every lookup miss.

    THE PIPE SURVIVES TOO, as a word of its own. A markdown table row is the
    shape a model reaches for when it is asked to show its records, and the
    cell walls are the only thing that says which value belongs to which
    instrument. Flattening them to spaces - which is what this did - turned
    `| Eval rows | 40,000 | measure_eval_set |` into a sentence with no
    attribution anywhere in it.
    """
    flat = str(text).lower()
    flat = flat.replace("’", "'").replace("–", "-").replace("—", "-")
    flat = re.sub(r"[^a-z0-9_.,;'%| ]+", " ", flat)
    flat = flat.replace("|", " | ")
    flat = _GLUED_SIZE.sub(r"\1 \2", flat)
    return re.sub(r"\s+", " ", flat).strip()


#: A NUMBER WELDED TO ITS UNIT, which every frame in this module was blind to.
#: `_numeral` asks `_NUMBER.fullmatch`, so `24gb` parsed as no number at all
#: and *"inspect_hardware measured 24GB of VRAM"* reached the user while the
#: spaced version of the same sentence was refuted. The blindness was in the
#: TOKENIZER, so the repair is here and not in five frames.
#:
#: FOUR SUFFIXES, AND THE LIST WAS COUNTED RATHER THAN IMAGINED. Every token of
#: the form `<digits><letters>` in the 2,728 harvested honest sentences and the
#: 164 harvested fabrications was tallied, and the tally is the reason this is
#: not simply `[a-z]+`:
#:
#:     b    28   `7b`, `8b`, `9b`          - PARAMETER COUNTS, not readings
#:     gb   19   `14gb`, `16gb`, `512gb`   - the target
#:     k    17   `50k`, `32k`, `12700k`    - and `12700k` is a CPU MODEL
#:     e     9   `5e`, `1e`                - LEARNING RATES, `5e-5`
#:     ghz   3   `2.8ghz`, `3.70ghz`
#:     th    2   `95th`, `8th`             - ORDINALS
#:     tb    2   `1tb`, `3tb`              - the target
#:     c     2   `55c`, `85c`
#:
#: Splitting `b` would put a bare `7` into *"a 7B model"*; splitting `k` would
#: put `12700` into an Intel part number; splitting `e` would tear a learning
#: rate in half; splitting `th` would read an ordinal as a count. So the rule
#: is the UNITS OF THE DECLARED FACTS - `vram_gb`, `ram_gb`, `disk_free_gb` are
#: measured in these and nothing else here is - and every other suffix keeps
#: the protection `fullmatch` was accidentally giving it.
#:
#: The lookbehind is what keeps a suffix from firing mid-identifier: a digit,
#: letter, underscore, dot or comma in front means this is part of a longer
#: token and not a number with a unit stuck to it.
_GLUED_SIZE = re.compile(r"(?<![a-z0-9_.,])(\d+(?:\.\d+)?)(gb|mb|kb|tb)\b")


#: A number spelled out. Closed, finite, and not a vocabulary in the sense this
#: module keeps getting burned by - there are no other English words for these.
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_MULTIPLIERS = {
    "hundred": 100, "thousand": 1000, "million": 1000000,
    "billion": 1000000000, "trillion": 1000000000000,
}


def _spell_out(text: str) -> str:
    """Rewrite spelled-out numbers as numerals, so the frames can see them.

    *"Based on what I have inspected, you have three hundred and forty labelled
    examples"* is the same fabrication as the one with `340` in it, and a wall
    that reads only digits reads only half the language a model writes in. The
    rewrite happens once, on the flattened text, so every frame in this module
    gets it rather than the one that remembered to ask.

    TWO RESTRICTIONS, and both of them are the cheap direction:

    * a run must carry a MULTIPLIER - `hundred`, `thousand` - or a TENS word to
      be rewritten, so a bare `one`..`nineteen` stays English. "one of the
      gates" and "two ways to do this" are enumerations rather than readings,
      and turning every one of them into a numeral would put numbers into
      sentences that do not have any and hand the other frames something to
      refute.
    * a run must carry a COUNT as well as its multiplier. `billion` alone is
      not a number, so *"Llama 3.1 8B has 8 billion parameters"* keeps the `8`
      it was written with instead of gaining a `1000000000` beside it.
    """
    words = text.split(" ")
    out: list[str] = []
    index = 0
    while index < len(words):
        span = index
        while span < len(words) and (
            _bare(words[span]) in _ONES
            or _bare(words[span]) in _TENS
            or _bare(words[span]) in _MULTIPLIERS
            or (
                _bare(words[span]) == "and"
                and span > index
                and span + 1 < len(words)
                and (
                    _bare(words[span + 1]) in _ONES
                    or _bare(words[span + 1]) in _TENS
                    or _bare(words[span + 1]) in _MULTIPLIERS
                )
            )
        ):
            span += 1
        run = [_bare(word) for word in words[index:span]]
        while run and run[-1] == "and":
            run.pop()
            span -= 1
        counted = any(word in _ONES or word in _TENS for word in run)
        scaled = any(word in _MULTIPLIERS or word in _TENS for word in run)
        if not counted or not scaled:
            out.append(words[index])
            index += 1
            continue
        total = 0
        current = 0
        for word in run:
            if word in _ONES:
                current += _ONES[word]
            elif word in _TENS:
                current += _TENS[word]
            elif word in _MULTIPLIERS:
                scale = _MULTIPLIERS[word]
                if scale >= 1000:
                    total += max(current, 1) * scale
                    current = 0
                else:
                    current = max(current, 1) * scale
        # The trailing punctuation of the last word of the run belongs to the
        # sentence and not to the number, so it survives the rewrite.
        last = words[span - 1]
        tail = last[len(last.rstrip(".,:;=()[]'\"")) :]
        out.append(f"{total + current}{tail}")
        index = span
    return " ".join(out)


def _bare(token: str) -> str:
    """One word without the punctuation a sentence wrapped it in."""
    return str(token).strip(".,:;=()[]'\"")


def _numeral(token: str) -> tuple[float, int, bool] | None:
    """THE ONE WAY TO READ A WRITTEN NUMBER. Value, precision, declared unit.

    There used to be two of these. `_as_number` read `0.75%` as the reading
    0.0075; `_numeral` read it as the numeral 0.75 written to two places. The
    POOL was built with the first and the MATCH was done with the second, so
    the two halves of every comparison disagreed about what a percent sign
    means - and disagreed in the permissive direction every time, because a
    claim of `0.75%` was matched against a held `0.75` as though the sign were
    decoration. One function, one meaning, and the callers that wanted a bare
    float take `[0]`.

    Three things come back, because three things are true of a written number:

    * **the reading** it states - `75%` states 0.75, `0.75%` states 0.0075;
    * **the precision** it states it to, in the reading's own units, so `75%`
      is two places and not zero - that is what makes a written `75%` match a
      measured `0.7532` while `40,000` does not match a counted `39,847`;
    * **whether its unit was DECLARED.** A model that writes `%` has said which
      units it is in and is held to them. A model that writes a bare `75`
      against a held `0.7532` has not, and `_SCALES` gives it the benefit.
    """
    body = _bare(token).replace(",", "")
    if _NUMBER.fullmatch(body) is None:
        return None
    percent = body.endswith("%")
    body = body.rstrip("%")
    try:
        value = float(body)
    except ValueError:
        return None
    places = len(body.split(".", 1)[1]) if "." in body else 0
    if percent:
        return value / 100, places + 2, True
    return value, places, False


#: The scales a written numeral could be in, against a value the harness holds.
#: A model that renders a measured `0.7532` as `75` has not invented anything,
#: and a wall that could not see that would fire on the product working. The
#: price of the third entry is that a claim off by exactly a hundredfold reads
#: as backed; nothing in the harvest was.
#:
#: THEY DO NOT APPLY TO A NUMBER THAT DECLARED ITS UNIT. `75%` is 0.75 and
#: nothing else, which is the half of the percent fix that a shared parser
#: alone would not have bought.
_SCALES = (1.0, 0.01, 100.0)


def numbers_in(blob: Any) -> set[float]:
    """Every number in an arbitrary payload, as floats.

    Used on tool results, which are nested dicts, and on the user's own
    messages, which are prose. JSON first so a float in a list is not missed
    by a regex over a repr.
    """
    text = blob if isinstance(blob, str) else json.dumps(blob, default=str)
    out: set[float] = set()
    for match in _NUMBER.finditer(text):
        parsed = _numeral(match.group())
        if parsed is not None:
            out.add(parsed[0])
    return out


def _matches(token: str, held: float, *, exact: bool = False) -> bool:
    """Whether a written number could be this held value.

    Compared at the WRITTEN number's own precision and in its own units, so
    `0.75` matches a measured `0.7532` and `40,000` does not match a counted
    `39,847`. Rounding is the model being readable; a different number is not.

    `exact` withdraws the rounding, and is set when the sentence said
    `exactly`. A model that writes "exactly 0.75" of a measured 0.7532 has not
    rounded, it has stated a number this harness does not hold.
    """
    parsed = _numeral(token)
    if parsed is None:
        return False
    numeral, places, declared = parsed
    for scale in (1.0,) if declared else _SCALES:
        candidate = held / scale
        if exact:
            if abs(candidate - numeral) <= _TOLERANCE:
                return True
        elif abs(round(candidate, places) - numeral) <= _TOLERANCE:
            return True
    return False


class Ground:
    """What actually happened, which is what a claim is checked against.

    Three sources, and none of them is anything the model said:

    * **`ran`** - name -> THE NUMBERS THAT TOOL PRODUCED this turn.
      `conductor._run_tool` calls `note_tool` at the same place it writes
      `tool.result` to the event log, so the names here and the names in the
      transcript cannot drift. A tool that ran and returned nothing numeric is
      present with an empty set: it RAN, which is a different fact from what it
      produced, and both are asked separately.
    * **`ledger`** - `evidence.rows_for(thread_id)`, the same sheet the
      diagnosis is computed from, with each fact's value, origin and the tool
      that stamped it. `by_tool` is that sheet inverted.
    * **`said_by_the_user`** - every number the person typed in this thread.
      Their own figures back a flat lookup, because arithmetic on what somebody
      told you is not a fabrication - but they back NO instrument's pool,
      because the user is not an instrument.
    * **`briefed`** - the numbers in `conductor.standing_brief`, which is THE
      HARNESS TALKING ABOUT ITSELF: its registry and the count of it, this
      thread's verdict, the gate line. A model quoting one back has invented
      nothing. This source did not exist, and its absence was the only
      false-catch family in 11,404 harvested live sentences - *"The harness has
      listed 28 tools that are registered on this machine"* and *"The harness
      has identified 28 tools available on this machine"*, both TRUE, both
      refuted, because 28 came from the brief rather than from a tool.

      DELIBERATELY THE BRIEF AND NOT THE WHOLE SYSTEM PROMPT. The prompt
      carries worked examples - *"about 40,000 support tickets"* - and a hex
      instruction-set id whose digits parse as `24333`. Folding those in would
      back `eval_size_n: 40000` on a thread where nothing counted anything,
      which is the live fabrication this wall exists for. The brief holds one
      number, `28`, and it holds it because the registry has 28 tools in it.

      Like the user's numbers, this backs the FLAT pool and no instrument's
      own: the harness writing a count in a brief is not an instrument reading
      anything.

    Read lazily and cached, because the wall asks per sentence and the ledger
    is a table. `note_tool` drops the cache, so a fact stamped in round two is
    ground truth for a sentence written in round three.
    """

    def __init__(self, thread_id: int | None) -> None:
        self.thread_id = thread_id
        #: name -> the numbers that tool's results carried. Membership is "it
        #: ran"; the set is "this is what it produced".
        self.ran: dict[str, set[float]] = {}
        #: Numbers the harness itself wrote into the model's prompt.
        self.briefed: set[float] = set()
        self._ledger: dict[str, list[dict[str, Any]]] | None = None
        self._by_tool: dict[str, set[float]] | None = None
        self._said: set[float] | None = None
        #: Sentences that cited the record exactly - see `note_citation`.
        self.citations: list[dict[str, Any]] = []

    # -- what happened this turn -------------------------------------------

    def note_tool(self, name: str, result: Any) -> None:
        """One tool ran, and this is what it returned.

        Called where `tool.result` is written, and nowhere else. BOTH HALVES
        ARE KEPT. This used to take the name into one collection and the
        numbers into another, which is the association thrown away at the exact
        moment the harness held it.
        """
        self.ran.setdefault(str(name), set()).update(numbers_in(result))
        self._ledger = None
        self._by_tool = None

    def note_briefing(self, text: Any) -> None:
        """What the harness told the model, before the model said anything.

        Called once with the system prompt. A number in there is one the
        HARNESS produced - the tool count, the gate ids, the caps it declares -
        so a model quoting it is quoting us. Nothing the model wrote ever
        reaches this method; `conductor` calls it with the prompt it built.
        """
        self.briefed |= numbers_in(text)

    # -- what the records hold ---------------------------------------------

    @property
    def ledger(self) -> dict[str, list[dict[str, Any]]]:
        """fact -> its rows in this thread, oldest first. Cached per turn."""
        if self._ledger is None:
            rows: dict[str, list[dict[str, Any]]] = {}
            try:
                for row in evidence.rows_for(self.thread_id):
                    rows.setdefault(str(row["fact"]), []).append(row)
            except Exception:  # noqa: BLE001 - a ledger we cannot read is empty
                # An unreadable ledger must not take the turn down, and it must
                # not silently BACK a number either: an empty sheet refutes
                # more, never less.
                rows = {}
            self._ledger = rows
        return self._ledger

    @property
    def said_by_the_user(self) -> set[float]:
        """Every number the person typed in this thread. Cached per turn."""
        if self._said is None:
            numbers: set[float] = set()
            try:
                from app import events

                for message in events.messages_for(self.thread_id):
                    if message["role"] == "user":
                        numbers |= numbers_in(message["content"])
            except Exception:  # noqa: BLE001 - same reason as the ledger
                numbers = set()
            self._said = numbers
        return self._said

    @property
    def from_tools(self) -> set[float]:
        """Every number any tool produced this turn, flat.

        The flat pool still exists and is still the right question for the two
        subjects that are not one instrument - `the harness` generally, and a
        labelled fact naming no instrument. What it is no longer used for is
        checking an attribution to a NAMED tool.
        """
        out: set[float] = set()
        for values in self.ran.values():
            out |= values
        return out

    @property
    def by_tool(self) -> dict[str, set[float]]:
        """tool -> the numbers it MEASURED in this thread's ledger.

        The `tool` column every row already carried, read as an index. This is
        what makes a claim about an EARLIER TURN checkable: the ledger crosses
        turns and carries the attribution with it.

        MEASURED ROWS ONLY, and that is not a filter for tidiness. A row whose
        origin is STATED or ASSERTED is something somebody SAID - the `tool`
        column on it names the door the value came through, not an instrument
        that read anything. `state_facts` is that door: it writes what its
        caller handed it, at the caller's origin, and every one of its rows
        carries `tool: state_facts`. Indexing those would put a number the
        MODEL asserted into `state_facts`' own pool, and then "0.85, measured
        by state_facts" would pass the joint lookup on the strength of the
        model having asserted 0.85 a moment earlier. `evidence` already draws
        this line - `_row` marks every non-MEASURED value as a claim on the way
        out - and this is the same line drawn here.
        """
        if self._by_tool is None:
            index: dict[str, set[float]] = {}
            for rows in self.ledger.values():
                for row in rows:
                    tool = str(row.get("tool") or "")
                    if tool and row.get("origin") == evidence.MEASURED:
                        index.setdefault(tool, set()).update(numbers_in(row["value"]))
            self._by_tool = index
        return self._by_tool

    def ledger_numbers(self) -> set[float]:
        out: set[float] = set()
        for rows in self.ledger.values():
            for row in rows:
                out |= numbers_in(row["value"])
        return out

    # -- the lookups --------------------------------------------------------

    def stamped_anything(self, tool: str) -> bool:
        """Has this tool written ANY row in this thread, at any origin?

        Deliberately not `by_tool`, which is MEASURED rows only. Whether a tool
        RAN and what it MEASURED are two questions, and the refusal that says
        "it has recorded nothing in this conversation" must not be written
        about a tool that recorded something.
        """
        return any(
            str(row.get("tool") or "") == tool
            for rows in self.ledger.values()
            for row in rows
        )

    def instrument_ran(self, tool: str) -> bool:
        """Did this tool run this turn, or stamp anything in this thread?"""
        return tool in self.ran or self.stamped_anything(tool)

    def readings_of(self, tool: str) -> set[float]:
        """Every number THIS instrument produced - this turn, or in the ledger."""
        return set(self.ran.get(tool, ())) | set(self.by_tool.get(tool, ()))

    def produced(self, tool: str, token: str, *, exact: bool = False) -> bool:
        """DID X PRODUCE N? The one question this module was not asking."""
        if _numeral(token) is None:
            return False
        return any(
            _matches(token, held, exact=exact) for held in self.readings_of(tool)
        )

    def producers_of(self, token: str, *, exact: bool = False) -> tuple[str, ...]:
        """Every instrument whose own readings back this number, in name order.

        Used by the closing, so a user told "that is not state_facts' number"
        is told whose it is. Composed from the records; nothing is guessed.
        """
        names = set(self.ran) | set(self.by_tool)
        return tuple(
            sorted(
                name
                for name in names
                if any(
                    _matches(token, held, exact=exact)
                    for held in self.readings_of(name)
                )
            )
        )

    def backs(self, token: str, *, exact: bool = False) -> bool:
        """Is this written number one the harness produced or the user gave?"""
        if _numeral(token) is None:
            return False
        pool = (
            self.from_tools
            | self.ledger_numbers()
            | self.said_by_the_user
            | self.briefed
        )
        return any(_matches(token, held, exact=exact) for held in pool)

    def holds(self, fact: str) -> dict[str, Any] | None:
        """The strongest row this thread holds for a fact, or `None`.

        Strongest by origin and then by recency, which is `evidence`'s own
        resolution order - a MEASURED row is what the engine would read, so it
        is what a claim about that fact is checked against.
        """
        rows = self.ledger.get(fact) or []
        if not rows:
            return None
        rank = {evidence.MEASURED: 2, evidence.STATED: 1}
        return max(
            enumerate(rows), key=lambda pair: (rank.get(pair[1]["origin"], 0), pair[0])
        )[1]

    def ever_measured(self, fact: str) -> tuple[dict[str, Any], ...]:
        """Every MEASURED row this thread holds for a fact, in the order run.

        WHY THIS EXISTS BESIDE `holds`. MEASURED 2026-09-13, thread 70 of the
        owner's own database: `measure_eval_set` was pointed at `train.jsonl`
        as well as `eval.jsonl`, so `eval_size_n` was stamped 400 by one call
        and 40 by twenty others. `holds` returns the LATEST, and when the model
        then wrote the true sentence "eval.jsonl: 40 rows" the wall compared 40
        against 400 and killed the reply mid-stream - eight times.

        The wall's question is *"did an instrument in this conversation produce
        that number for that fact"*. `holds` answers a narrower one - *"is that
        the current reading"* - and the two come apart the moment one
        instrument is pointed at two files. A number this thread measured is
        never invented, whatever was measured after it, so the check reads all
        the rows and `holds` keeps answering what it was written to answer.
        """
        rows = self.ledger.get(fact) or []
        return tuple(row for row in rows if row.get("origin") == evidence.MEASURED)

    def rows_about(self, name: str) -> tuple[tuple[dict[str, Any], str], ...]:
        """Every MEASURED row whose own account names `name` as what it measured.

        `(row, the word in the account that names it)`, in the order run. The
        account is the row's `how` - the sentence the instrument wrote when it
        stamped - and a word in it names `name` when `name` is that word or any
        dot-, colon- or slash-separated segment of it, case aside. So
        `hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0 answered 0 of 20 rows of ...`
        names `q8_0`, `minicpm5-1b-gguf` and the whole string.

        MEASURED ONLY, for the reason `by_tool` is: a STATED row's account is
        somebody's say-so, not an instrument's record of what it read. This
        ledger has no DERIVED origin (`evidence.ORIGINS`), so there is nothing
        else to admit.

        WHAT THIS DOES NOT DO is decide the name is an instrument. It finds the
        rows a name is the SUBJECT of - the model that was scored, or the file
        it was scored on, since the account names both - and the instrument is
        still the row's own `tool` column, never the name.
        """
        wanted = str(name).lower()
        out: list[tuple[dict[str, Any], str]] = []
        for rows in self.ledger.values():
            for row in rows:
                if row.get("origin") != evidence.MEASURED:
                    continue
                for word in str(row.get("how") or "").split():
                    word = word.strip(".,;:()[]'\"`")
                    segments = {word.lower(), *re.split(r"[./:\\]", word.lower())}
                    if wanted in segments:
                        out.append((row, word))
                        break
        return tuple(out)

    def note_citation(self, citation: dict[str, Any]) -> None:
        """A sentence cited the record exactly, and the transcript is told so.

        WRITTEN HERE, TO THE EVENT LOG, and not yielded by the conductor: the
        wall's caller is the sentry, which returns one bit per sentence, and
        this is an annotation beside a sentence that passed rather than a
        conflict that stopped one. The client reads `conductor.notice` rows off
        `GET /api/events` like every other row, so it arrives in the same place
        a refusal does. A Ground with no thread records nothing - there is no
        transcript to write into - and a write that fails never takes the turn
        down with it.
        """
        self.citations.append(citation)
        if self.thread_id is None:
            return
        try:
            from app import events

            events.append("conductor.notice", citation, thread_id=self.thread_id)
        except Exception:  # noqa: BLE001 - an annotation is not worth a turn
            pass


class _Words:
    """A flattened sentence as words that remember where they came from."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.words: list[str] = []
        self.starts: list[int] = []
        for match in re.finditer(r"\S+", text):
            self.words.append(match.group())
            self.starts.append(match.start())

    def __len__(self) -> int:
        return len(self.words)

    def at(self, index: int) -> str:
        return self.words[index] if 0 <= index < len(self.words) else ""

    def bare_at(self, index: int) -> str:
        return _bare(self.at(index))

    def phrase_at(self, index: int, phrase: Iterable[str]) -> bool:
        """Whether a multi-word name starts here, PUNCTUATION AND ALL.

        `_instrument_at` stripped `.,'` off a single tool name and this
        compared raw whitespace tokens, so a multiword name survived a comma
        nowhere:

            "According to the harness your eval set holds 40000 rows"   caught
            "According to the harness, your eval set holds 40000 rows." missed

        One comma. The words are the claim; the punctuation the sentence wrapped
        them in is not part of it, so it comes off on both sides.
        """
        phrase = tuple(phrase)
        return tuple(
            _bare(word) for word in self.words[index : index + len(phrase)]
        ) == phrase

    def numbers_between(self, low: int, high: int) -> list[tuple[int, str]]:
        """The written numbers in a word range, with their indices."""
        out: list[tuple[int, str]] = []
        for index in range(max(0, low), min(high + 1, len(self.words))):
            token = _bare(self.words[index])
            if _numeral(token) is not None and not self._is_a_bound(index):
                out.append((index, token))
        return out

    def is_exact(self, index: int) -> bool:
        """Whether the number at `index` was written as an EXACT one."""
        return self.bare_at(index - 1) in _EXACTLY

    def cells(self) -> list[tuple[int, int]]:
        """The table cells of this line as `(first word, last word)` ranges.

        Empty on a line with no pipes in it, and empty for a cell with nothing
        in it, so a leading and trailing `|` do not invent two blank columns.
        """
        if "|" not in self.words:
            return []
        out: list[tuple[int, int]] = []
        start = 0
        for index in range(len(self.words) + 1):
            if index == len(self.words) or self.words[index] == "|":
                if index > start:
                    out.append((start, index - 1))
                start = index + 1
        return out

    def _is_a_bound(self, index: int) -> bool:
        """Whether a number is a limit rather than a reading.

        `approximately`, `around` and `roughly` are deliberately NOT here. They
        do not turn a reading into a bound; they say a reading was rounded, and
        rounding is already given to the model by `_matches`. Reading them as
        bounds would let a model hedge its way past this wall with one word.
        """
        for phrase in _BOUNDS_NOT_READINGS:
            start = index - len(phrase)
            if start >= 0 and self.phrase_at(start, phrase):
                return True
        for phrase in _SELECTORS_NOT_READINGS:
            if self.phrase_at(index + 1, phrase):
                return True
        return False


def _harness_at(words: "_Words", index: int) -> int | None:
    """The last word of a harness name starting at `index`, or `None`."""
    for phrase in HARNESS_NAMES:
        if words.phrase_at(index, phrase):
            return index + len(phrase) - 1
    return None


def _instrument_at(
    words: "_Words", index: int, tools: frozenset[str], *, strict: bool
) -> tuple[int, str, bool] | None:
    """An instrument named starting here: `(last word, name, is it registered)`.

    `strict` admits ONLY names this harness actually has. It is set wherever
    the only evidence of a claim is a bare preposition, because `from
    support_tickets` and `by hand` are not attributions and the registry is the
    thing that has always kept that frame narrow.

    Where a VERB or an explicit attribution phrase is present, a name merely
    SHAPED like a tool is admitted too - and refuted harder. An unregistered
    instrument was the sharpest hole in this module: nothing called
    `measure_accuracy` exists, so nothing could have measured anything with it,
    and yet *"your accuracy is 0.91, measured by measure_accuracy"* opened no
    frame at all. The more brazen the fabrication, the less visible it was.

    A DECLARED FACT NAME IS NOT AN INSTRUMENT and is not read as one:
    `baseline_score` is tool-shaped, and frame 1 is where it belongs. That is
    every declared fact and not only the reading-only ones - `target_score` is
    the user's own answer, and calling it an invented instrument would be this
    module inventing a capability while refusing an invented number.
    """
    harness = _harness_at(words, index)
    if harness is not None:
        return harness, THE_HARNESS, True
    word = words.bare_at(index)
    if word in tools:
        return index, word, True
    if strict:
        return None
    if word in _declared() or word in _KEYED_SOURCE:
        return None
    if _TOOL_SHAPED.fullmatch(word):
        return index, word, False
    return None


def _claims(
    words: "_Words",
    tools: frozenset[str],
    readable: frozenset[str],
    subjects: dict[tuple[str, ...], str] | None = None,
    asserts: bool = True,
):
    """Every provenance claim in one sentence.

    Yields `(kind, instrument, registered, fact, spot, token, nearest, exact)`,
    and each frame yields what it FOUND rather than deciding anything. `_refute`
    is what turns a claim into a refusal, and it does that only by lookup.
    """
    found: list[tuple[str, str | None, bool, str | None, int, str | None, bool, bool]] = []

    def bind(kind, instrument, registered, anchor, spots):
        """One frame's numbers, with the nearest one marked.

        THE NEAREST NUMBER IS THE ONE THE ATTRIBUTION BINDS, and it is the only
        one the per-instrument lookup is asked about. The rest of the sentence
        is context - *"measure_eval_set counted 40000 rows, so you have 10000
        per class"* attributes 40000 and computes 10000 - and context is
        checked against the flat pool, which is what keeps arithmetic on a real
        reading from reading as a fabrication.
        """
        if not spots:
            return
        closest = min(spots, key=lambda pair: abs(pair[0] - anchor))[0]
        for spot, token in spots:
            found.append((
                kind, instrument, registered, None, spot, token,
                spot == closest, words.is_exact(spot),
            ))

    for index in range(len(words)):
        # 1. THE LABELLED READING. A reading-only fact, then a number.
        bare = words.bare_at(index)
        if bare in readable:
            for step in range(1, _LABEL_REACH + 3):
                token = words.bare_at(index + step)
                if _numeral(token) is not None:
                    found.append((
                        "label", None, True, bare, index + step, token,
                        False, words.is_exact(index + step),
                    ))
                    break
                if token not in _LABEL_JOINERS:
                    break

        # 2. THE ATTRIBUTED READING, PASSIVE. `<number> ... measured by <it>`.
        #    The attribution phrase is read BACKWARDS from the instrument,
        #    because that is the order it is written in.
        #
        #    THE PREPOSITION ALONE IS ENOUGH, and it has to be: the live
        #    fabrication wrote `baseline_score = 0.9 (from run_eval)`, which
        #    has no verb in it at all. What keeps that narrow is the other side
        #    - off a bare preposition the word after it must be a REGISTERED
        #    tool name in full, and "from the controls" or "by hand" is not one.
        back = words.bare_at(index - 1)
        bare_preposition = back in _BY
        spoken = (
            (bare_preposition and words.bare_at(index - 2) in ATTRIBUTES)
            or back in _KEYED_SOURCE
            or any(
                index - len(phrase) >= 0 and words.phrase_at(index - len(phrase), phrase)
                for phrase in _ACCORDING
            )
        )
        if bare_preposition or spoken:
            named = _instrument_at(words, index, tools, strict=not spoken)
            if named is not None:
                last, instrument, registered = named
                bind(
                    "passive", instrument, registered, index,
                    words.numbers_between(index - _REACH, last + _REACH),
                )

        # 3. THE ATTRIBUTED READING, ACTIVE. `<it> measured ... <number>`.
        named = _instrument_at(words, index, tools, strict=False)
        if named is not None:
            last, instrument, registered = named
            for step in range(1, _VERB_REACH + 1):
                if words.bare_at(last + step) in ATTRIBUTES:
                    bind(
                        "active", instrument, registered, last + step,
                        words.numbers_between(
                            last + step + 1, last + step + _REACH
                        ),
                    )
                    break

    found.extend(_table_claims(words, tools))
    found.extend(_stated_readings(words, subjects or {}, asserts))
    return found


def _asserts_of_this_project(words: "_Words") -> bool:
    """Whether this sentence claims to be REPORTING rather than reasoning.

    Frame 5 needs this and the other four do not, because the other four have
    an instrument in them and an instrument IS the claim. Ordinary English has
    no instrument, so something else has to say that a measurement is being
    asserted, and these are the three things that say it - none of them
    invented here:

    * the SECOND PERSON, which makes the number a fact about this user's
      machine or this user's data rather than about datasets in general;
    * an ATTRIBUTION VERB from `ATTRIBUTES`, which is the HARVESTED list -
      *"the data shows 340"*, *"I counted 340"*, *"340 were detected"*;
    * an attribution PHRASE from `_ACCORDING` - *"based on"*, *"according
      to"* - which frame 2 already reads for the same purpose.

    Without one of these, *"a dataset of 500 labeled examples is usually the
    floor for a useful LoRA"* is a sentence about the field, and it must reach
    the user untouched. That sentence is the reason this predicate exists.
    """
    for index in range(len(words)):
        bare = words.bare_at(index)
        if bare in _SECOND_PERSON or bare in ATTRIBUTES or bare in _HOLDS:
            return True
        if any(words.phrase_at(index, phrase) for phrase in _ACCORDING):
            return True
    return False


def _stated_readings(
    words: "_Words", subjects: dict[tuple[str, ...], str], asserts: bool = True
):
    """FRAME 5. A reading-only fact named in ORDINARY ENGLISH, with a number.

    The hole this closes: every other frame in this module is keyed on
    INSTRUMENT GRAMMAR - a registered tool name in full, or this harness naming
    itself. That grammar catches *"profile_dataset found 340 labeled
    examples"* and misses *"Based on the dataset profile, there are 340
    labeled examples"*, which is the same fabrication in the register a
    language model actually writes in. The wall was catching the form nobody
    writes and missing the form everybody writes.

    What makes this safe is the same asymmetry the rest of the module rests on,
    and it is worth saying again because this frame reads MORE loosely than the
    others: a claim caught here still has to survive `_refute`, and `_refute`
    reads the records rather than the sentence. If the ledger holds the fact at
    this value, or any tool returned the number, or the user typed it, or the
    brief said it, the sentence passes whatever shape it is in. The only
    sentences this can stop are ones that name a fact only an instrument can
    read, put a number on it, address it to this user - and name a number
    nothing in this conversation holds.

    THE SUBJECT VOCABULARY IS DERIVED AND NOT WRITTEN. `_reading_subjects`
    reads it off the same `source: inspect` declarations frame 1 reads, so a
    fact added to `docs/diagnosis_engine.yaml` is covered here the day it lands
    and a fact removed stops being covered. This module has been burned once
    for writing a word list from imagination; the only lists written by hand
    here are `_SECOND_PERSON` and `_HOLDS`, which are closed classes of English
    rather than guesses about what a model says.
    """
    out = []
    if not subjects or not asserts:
        return out
    if _opens_hypothetically(words.text, reach=_OPENING_REACH):
        # "Let's say you have 340 labeled examples" supposes; the word that
        # makes it a supposition is the second one. Read here rather than for
        # the whole module, because the instrument frames lose catches to it.
        return out
    # A CLAUSE THAT NAMES A NUMBER SOMEBODY WANTS IS NOT REPORTING ONE - and
    # the unit is THE CLAUSE, which is what this guard's own justification said
    # all along. It used to read the whole sentence, and the sentence it cited
    # to justify that reach - "to fine-tune well you typically need 1,000
    # labeled examples" - ends "and it governs the whole CLAUSE". It does. The
    # scan did not.
    #
    # THE PRICE OF THE WIDER READ WAS THE FOUNDING DEFECT ITSELF. `CLAUDE.md`
    # names a hardcoded VRAM figure nothing measured, and the harvested form of
    # it is *"You have 24 GB of VRAM, so a 7B model should fit."* - where
    # `should` sits in a DIFFERENT CLAUSE and governs whether a model fits,
    # not where the 24 came from. One word, four words past a comma, turned the
    # whole wall off for the sentence this module exists to stop.
    #
    # Both halves are asserted in the tests: the module's own example is STILL
    # vetoed, because `need` and `1,000` share a clause and nothing separates
    # them.
    clause = _clause_marks(words)
    wanted = {
        clause[index]
        for index in range(len(words))
        if words.bare_at(index) in _WANTED_NOT_READ
    }
    longest = max(len(phrase) for phrase in subjects)
    stems = [_stem(words.at(index)) for index in range(len(words))]
    found: list[tuple[int, int, str, int, str]] = []
    for start in range(len(words)):
        fact = None
        last = start
        for length in range(min(longest, len(words) - start), 0, -1):
            fact = subjects.get(tuple(stems[start : start + length]))
            if fact is not None:
                last = start + length - 1
                break
        if fact is None:
            continue
        spots = [
            pair
            for pair in words.numbers_between(
                start - _SUBJECT_REACH, last + _SUBJECT_REACH
            )
            if _reads_the_subject(words, start, last, pair[0])
            # The number and the fact must each stand outside a wanting
            # clause. Either one inside it is enough to decline, which is the
            # conservative direction: "you should aim for 1,000 labeled
            # examples" has both in the same clause and stays declined.
            and clause[pair[0]] not in wanted
            and clause[start] not in wanted
        ]
        if not spots:
            continue
        # ONE READING PER SUBJECT, and it is the nearest number to the noun.
        # "Your baseline score is 0.82 after 3 epochs" states a baseline of
        # 0.82; the 3 is an epoch count and belongs to no fact here.
        #
        # NEAREST AMONG THE UNBROKEN FIRST. In "15.9 GB RAM, 12 GB VRAM, 544
        # GB free" the number nearest VRAM is 544 - adjacent, across the
        # comma that says it is the next item - and the number VRAM labels
        # is 12, two words away through its unit. A number the sentence's
        # own punctuation separates from the fact is taken only when no
        # unbroken one is in reach, so "Your VRAM, 24 GB, ..." is still read.
        clean = [
            pair for pair in spots if not _a_break_between(words, start, last, pair[0])
        ]
        spot, token = min(
            clean or spots,
            key=lambda pair: min(abs(pair[0] - start), abs(pair[0] - last)),
        )
        found.append((start, last, fact, spot, token))
    # AND ONE FACT PER NUMBER. MEASURED 2026-09-11 on the owner's install, in
    # plan mode, on a turn where inspect_hardware had really run:
    #
    #     - Hardware: 15.9 GB RAM, 8.0 GB VRAM, one NVIDIA RTX 2060 SUPER, ...
    #
    # was withheld as `ram_gb` shown as 8.0. Every number in it was real. The
    # tokeniser keeps words and drops punctuation, so `RAM,` stands ADJACENT
    # to `8.0` and RAM took the nearer number - the comma that says "next
    # item" was the one thing the reader could not see. So when two facts
    # claim one number, the claim with a comma, semicolon or colon between
    # the fact and the number yields to the one without; two claims alike are
    # settled by nearness. This cannot lose a catch: the number keeps exactly
    # one binding and is still checked under it.
    claims: dict[int, list[tuple[int, int, str, int, str]]] = {}
    for row in found:
        claims.setdefault(row[3], []).append(row)
    for spot, rivals in claims.items():
        if len(rivals) > 1:
            clean = [row for row in rivals if not _a_break_between(words, row[0], row[1], spot)]
            pool = clean or rivals
            keep = min(pool, key=lambda row: min(abs(spot - row[0]), abs(spot - row[1])))
            claims[spot] = [keep]
    for row in found:
        if claims[row[3]][0] is row:
            start, last, fact, spot, token = row
            out.append(
                ("stated", None, True, fact, spot, token, False, words.is_exact(spot))
            )
    return out


def _a_break_between(words: "_Words", start: int, last: int, spot: int) -> bool:
    """Whether the sentence's own punctuation separates the fact from the number.

    A comma, semicolon or colon on any word from the fact's edge up to the
    word before the number - `RAM, 8.0` carries it on `RAM,`; `8.0, RAM` on
    `8.0,`. Read from the RAW tokens, because `bare_at` is exactly the reader
    that threw the mark away.
    """
    if spot > last:
        span = range(last, spot)
    elif spot < start:
        span = range(spot, start)
    else:
        return False
    return any(words.at(index).rstrip().endswith((",", ";", ":")) for index in span)


def _table_claims(words: "_Words", tools: frozenset[str]):
    """A markdown table row, which is how a model shows its records.

    `| Eval rows | 40,000 | measure_eval_set |` is the same claim as "40,000
    rows, measured by measure_eval_set", and it went through because the row
    label was not a declared fact and there was no preposition anywhere in it.
    The cell wall is the attribution.

    THREE CELLS IS THE FLOOR, and it is the whole of what keeps this narrow.
    Two-cell rows are how this product describes its own tools -
    `| list_runs | lists your recent runs |` - and a description is not a
    report. A third cell means a VALUE is present, and a value is what turns
    the row into a claim that something was read.

    A ROW WITH NO NUMBER IN IT IS NOT READ, and that is a decision this file
    made twice - see `## The attribution with no number in it` in the module
    docstring for the measurement that reversed it.
    """
    cells = words.cells()
    if len(cells) < 3:
        return []
    named = [
        (position, words.bare_at(start))
        for position, (start, end) in enumerate(cells)
        if start == end and words.bare_at(start) in tools
    ]
    out = []
    for position, instrument in named:
        spots = [
            (spot, token)
            for index, (start, end) in enumerate(cells)
            if index != position
            for spot, token in words.numbers_between(start, end)
        ]
        if not spots:
            continue
        anchor = cells[position][0]
        closest = min(spots, key=lambda pair: abs(pair[0] - anchor))[0]
        for spot, token in spots:
            out.append((
                "table", instrument, True, None, spot, token,
                spot == closest, words.is_exact(spot),
            ))
    return out


#: The words that may stand between the start of a sentence and the `say` that
#: makes it a supposition. See `_opens_hypothetically`.
_LET = frozenset({"let", "let's", "lets"})

#: How many words into a sentence frame 5 reads for a supposition. Three is
#: what "let's say", "and if", "so assuming" and "but suppose" need. The
#: instrument frames read one - see `_opens_hypothetically`.
_OPENING_REACH = 3


def _opens_hypothetically(text: str, reach: int = 1) -> bool:
    """Whether this sentence opens by supposing rather than by reporting.

    THE OPENING, NOT THE FIRST WORD. This read `text.split(" ")[0]` and
    *"Let's say you have 340 labeled examples"* walked straight past it, because
    the word that makes the sentence hypothetical is the second one. Three words
    is what "let's say", "and if", "so assuming" and "but suppose" need; past
    that, a hypothetical marker governs a later clause rather than this one, and
    `_NOT_YET` is what reads the later clause.

    `say` IS THE ONE MARKER THAT IS ALSO A HARVESTED ATTRIBUTION VERB, and
    widening the scan collided with it head on:

        "Let's say you have 340 labeled examples."      a supposition
        "The numbers say you have 340 labeled examples."  a fabrication

    Same word, same position, opposite meanings, and the first version of this
    scan read both as suppositions and let the second reach the user. What
    separates them is the word in front: `say` opens a supposition at the start
    of a sentence or after "let's", and everywhere else it is a verb of
    reporting with a subject in front of it. Every other marker in
    `_HYPOTHETICAL` is unambiguous and is read wherever it falls.

    HOW FAR IN IS THE CALLER'S DECISION, AND IT COSTS CATCHES TO GET WRONG.
    This function is a decline, and a decline read across frames that did not
    ask for it trades catches away for nothing - the same argument
    `_WANTED_NOT_READ` makes about itself. Reading three words in was added for
    frame 5, which has no instrument to anchor it; applied to the whole module
    it silently REGRESSED the instrument frames, because a modal in second
    position is usually not a supposition at all:

        "I should add that inspect_hardware measured 24 GB of VRAM."
        "So assuming nothing changed, inspect_hardware measured 24 GB of VRAM."

    Both name a real instrument, both assert a reading, both were CAUGHT before
    the scan widened and reached the user after. `reach` is therefore 1 for the
    four instrument frames - exactly what they had - and 3 only for frame 5.
    """
    words = [_bare(word) for word in text.split(" ")[:reach]]
    for index, word in enumerate(words):
        if word not in _HYPOTHETICAL:
            continue
        if index == 0 or word != "say" or words[index - 1] in _LET:
            return True
    return False


#: A LINE THAT INTRODUCES A BLOCK rather than standing on its own. "According
#: to the hardware inspection, your system has:" is the sentence the rows under
#: it are missing, and the colon is how the model says so.
#:
#: THE TRAILING CLASS IS NOT DECORATION. This was `r":\s*$"`, which meant a
#: lead-in wearing emphasis was not a lead-in at all, and the whole block frame
#: switched off:
#:
#:     'Your system has:'      -> lead-in, so '- VRAM: 11 GB' under it is audited
#:     '**Your system has:**'  -> NOT a lead-in, so the same row reached the user
#:
#: `**Training Location:**` is a line from this product's own harvest of
#: granite4-hermes, alongside ten other bold label lines - the register is
#: measured, not imagined. And the inconsistency was internal: `_flatten`
#: already strips emphasis for the ROW, so `**Your VRAM is 10 GB.**` was
#: stopped while the lead-in one line above it was not recognised. The colon
#: cannot simply be flattened here, because `_flatten` removes it too.
_LEADS_A_BLOCK = re.compile(r":[\s*_`~\"'\)\]]*$")

#: A LINE THAT IS A ROW OF A BLOCK. A bullet, a numbered step, a table row, or
#: a bare `Label: value` pair. These are the lines `conductor._SENTENCE_END`
#: cuts loose from their lead-in, because it treats a newline as a full stop.
_IS_A_ROW = re.compile(
    r"""^\s*(?:
          [-*+•]\s             # - bullet
        | \d+[.)]\s              # 1. numbered step
        | \|                     # | table row
        | [^:\n]{1,60}:\s*\S     # Label: value
    )""",
    re.VERBOSE,
)


#: A MARKDOWN HEADING, which introduces what follows it exactly as a colon
#: does and carries no colon at all. `## Your machine` and `### What I
#: measured` are both headings; the second carries an attribution cue and the
#: first does not, which is the ordinary case - a lead-in lends its CUE, so one
#: without a cue lends nothing and costs nothing.
_IS_A_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S")

#: A BOLD LABEL LINE - `**Detected configuration**` - which is the same move as
#: a heading in a model that is avoiding heading syntax. Counted in this
#: product's own harvest, not imagined. Requires the WHOLE line to be wrapped
#: and no terminal punctuation, so an emphasised ordinary sentence
#: (`**We should train a LoRA.**`) is not mistaken for a label.
_IS_A_LABEL_LINE = re.compile(r"^\s*(\*\*|__)(?P<body>[^*_].*?)(\*\*|__)\s*$")


def leads_a_block(sentence: str) -> bool:
    """Whether this line introduces rows rather than standing on its own."""
    line = str(sentence).rstrip()
    if _LEADS_A_BLOCK.search(line):
        return True
    if _IS_A_HEADING.match(line):
        return True
    label = _IS_A_LABEL_LINE.match(line)
    return bool(label and not label.group("body").rstrip().endswith((".", "!", "?")))


def is_a_row(sentence: str) -> bool:
    """Whether this line is a row of a block - a bullet, a step, a table row."""
    return bool(_IS_A_ROW.match(str(sentence)))


#: THE PARTICLES A STATEMENT IS TAGGED WITH to invite agreement. Closed class.
_TAG_PARTICLES = frozenset({"right", "correct", "yes", "no", "ok", "okay", "true"})

#: The other tag shape: a NEGATED AUXILIARY inverted onto a pronoun. Generated
#: rather than listed - any negated auxiliary followed by a pronoun is one -
#: which is why this is two closed classes and not a table of phrases.
_NEGATED_AUXILIARIES = frozenset(
    """isn't aren't wasn't weren't don't doesn't didn't hasn't haven't hadn't
    won't can't couldn't shouldn't wouldn't ain't""".split()
)
_TAG_PRONOUNS = frozenset(
    {"it", "they", "you", "he", "she", "we", "i", "that", "this", "there"}
)


def _without_a_tag_question(raw: str) -> str | None:
    """The STATEMENT inside a tag question, or `None` if this is a question.

    A trailing `?` turns the whole wall off, and it has to: a question asserts
    nothing, and refusing one would be the product interrupting somebody for
    asking. But *"profile_dataset found 340 labeled examples, right?"* is a
    claim with a tag stuck on it, and five characters was the whole cost of
    getting a fabricated measurement past every frame in this module.

    THE TAG IS THE MARKER, AND THAT IS A MEASURED CHOICE. The obvious rule -
    a real question OPENS with an interrogative or an auxiliary - was tried
    against the 56 question-mark sentences the harvest actually contains, and
    it misreads NINE of them as statements: *"Or is there something specific
    you would like to investigate further about it?"*, *"To start, can you tell
    me how many tickets are currently in your inbox...?"*, *"Since you haven't
    provided the specific path to your file yet, could you please share the
    location...?"*. Real questions carry discourse openers in front of the
    inversion, and a wall that stopped nine honest questions to catch one tag
    would be the trade this repository already knows the cost of.

    So the question stays innocent by default and only a TAG convicts. What
    comes back is the statement half; the caller keeps the verbatim sentence
    for the transcript, because a log that quotes a sentence the model did not
    write is the log lying quietly.
    """
    stripped = raw.rstrip()
    if not stripped.endswith("?"):
        return None
    body = stripped[:-1].rstrip().rstrip("!.").rstrip()
    head, comma, tail = body.rpartition(",")
    if not comma or not head.strip():
        return None
    words = tail.replace("’", "'").lower().strip().strip("*_`\"')").split()
    if len(words) == 1 and words[0] in _TAG_PARTICLES:
        return head.strip()
    if (
        len(words) == 2
        and words[0] in _NEGATED_AUXILIARIES
        and words[1].strip(".,'") in _TAG_PRONOUNS
    ):
        return head.strip()
    return None


def reads_as_a_measurement(
    sentence: str, ground: "Ground", lead_in: str | None = None
) -> dict[str, Any] | None:
    """The refutation row for a fabricated measurement, or `None`.

    RELUCTANT IN THE SAME DIRECTION AS THE SENTRY, and for a sharper reason: a
    number this harness DID produce, attributed to the instrument that DID
    produce it, passes whatever shape the sentence is in. The only sentences
    that can be wrongly stopped are ones that both look like an attribution and
    name a number the instrument they name did not return.

    A hypothetical asserts nothing ("if your baseline were 0.75"), a plan
    asserts nothing ("measure_baseline will report your real score"), and a
    bound is not a reading ("scores at most 200 rows"). Each of those declines
    before any lookup runs.
    """
    raw = str(sentence).strip()
    if not raw:
        return None
    # A QUESTION IS NOT A CLAIM, and a statement wearing a question mark is.
    # `_without_a_tag_question` is the difference and says how it is told.
    body = _without_a_tag_question(raw)
    if body is None and raw.rstrip().endswith("?"):
        return None

    text = _spell_out(_flatten(raw if body is None else body))
    if not text:
        return None
    if _opens_hypothetically(text):
        return None

    words = _Words(text)
    tools = _registered_tools()
    readable = _readings()
    subjects = _reading_subjects()
    claims = []
    for claim in _claims(
        words, tools, readable, subjects,
        _asserts_of_this_project(words) or _lead_in_asserts(lead_in, raw),
    ):
        spot = claim[4]
        window = text[
            max(0, words.starts[max(0, spot - _REACH)]) : words.starts[
                min(len(words) - 1, spot + _REACH)
            ]
            + 40
        ]
        if not _NOT_YET.search(window):
            claims.append(claim)
    # A NAME NO TOOL HAS IS READ AGAINST THE RECORD BEFORE IT IS REFUTED - once
    # per frame, because a frame's numbers are one statement about one subject
    # (the bound reading and the count beside it). See `_as_a_subject`.
    as_subjects: dict[tuple[str, str], Any] = {}
    for kind, instrument, registered, *_ in claims:
        if instrument is not None and not registered:
            key = (kind, instrument)
            if key not in as_subjects:
                as_subjects[key] = _as_a_subject(
                    instrument,
                    [claim for claim in claims if (claim[0], claim[1]) == key],
                    words, ground,
                )
    refuted: list[dict[str, Any]] = []
    cited: list[dict[str, Any]] = []
    for kind, instrument, registered, fact, spot, token, nearest, exact in claims:
        read = as_subjects.get((kind, instrument)) if not registered else None
        if read is not None:
            outcome, row = read
            if nearest:
                (cited if outcome == CITATION_MATCHED else refuted).append(row)
            continue
        row = _refute(
            kind, instrument, registered, fact, token, ground,
            nearest=nearest, exact=exact,
        )
        if row is not None:
            refuted.append(row)
    if not refuted:
        # Written only for a sentence that PASSED, so a citation in a sentence
        # something else refuted is not annotated as though it reached anyone.
        for row in cited:
            ground.note_citation(dict(row, sentence=raw))
        return None
    # THE SHARPEST REFUTATION, not the first one found. `REFUTATIONS` is that
    # order and says why it is that order.
    order = {name: rank for rank, name in enumerate(REFUTATIONS)}
    best = min(refuted, key=lambda row: order.get(row["refuted_by"], len(order)))
    best["sentence"] = raw
    return best


def _lead_in_asserts(lead_in: str | None, raw: str) -> bool:
    """Whether the line that introduced this row said the row is about US.

    THE SENTENCE SPLITTER MAKES EVERY BULLET CUE-LESS, and that is the whole of
    this. `conductor._SENTENCE_END` treats a NEWLINE as a full stop, so a reply
    like

        According to the hardware inspection, your system has:
        - RAM: 32 GB
        - Video RAM (VRAM): 8 GB
        - Free Disk Space: 500 GB

    reaches this module as four separate sentences, and the three that carry
    the numbers have been stripped of the one that says whose machine it is.
    Frame 5 asks `_asserts_of_this_project` and gets `False` from every row,
    so the ENTIRE BULLETED AND TABULAR REGISTER walks through - which is
    exactly the register a model reaches for when somebody asks it to lay out
    what it knows.

    WHY THIS IS NOT `_table_claims`. That frame reads a markdown table where a
    CELL holds a registered tool name; the cell wall is its attribution and
    three cells is its floor. A bullet has no cells and names no tool, so it
    was never in reach of that frame, and widening it would have meant
    inventing an attribution the row does not contain.

    ONLY THE CUE CROSSES THE BOUNDARY. Not the lead-in's numbers, not its
    instrument, not its facts - a row is still audited as itself, against the
    records, and the lead-in only restores the grammatical subject the splitter
    threw away. A lead-in that supposes rather than reports ("If your system
    had:") supplies nothing, for the same reason the sentence form does.
    """
    if not lead_in or not is_a_row(raw):
        return False
    text = _spell_out(_flatten(lead_in))
    if not text or _opens_hypothetically(text):
        return False
    # A LEAD-IN ONLY LENDS ITS SUBJECT IF IT IS ITSELF REPORTING. This cost one
    # false catch when it was not asked, and the false catch is the argument:
    #
    #     You may need to consider:
    #     - **Renting or buying a machine with more RAM (at least 16 GB) and
    #       higher VRAM (12+ GB)**.
    #
    # is the product doing its job - telling somebody what they would have to
    # buy - and the row underneath is a SHOPPING LIST, not a reading of this
    # machine. `at least 16` was already declined as a bound; `12+` was not,
    # and the lead-in is the only thing in the block that says the whole list
    # is hypothetical. So the two declines the sentence form already makes -
    # a number somebody WANTS, and a next step rather than a finding - are
    # asked of the introducing line as well.
    words = _Words(text)
    if any(words.bare_at(index) in _WANTED_NOT_READ for index in range(len(words))):
        return False
    if _NOT_YET.search(text):
        return False
    return _asserts_of_this_project(words)


def _plain(value: Any) -> str:
    """A held number as a person would write it: `20`, not `20.0`; `0.0` stays."""
    if isinstance(value, float) and value.is_integer() and abs(value) >= 1:
        return str(int(value))
    return str(value)


def _counts_in(how: str) -> list[tuple[float, str]]:
    """`(number, the word after it)` for every number in an instrument's account.

    `"... answered 0 of 20 rows of eval.jsonl"` is `[(0, "of"), (20, "rows")]`.
    THE WORD IS TAKEN FROM THE RECORD, NOT FROM A LIST: a sentence's number is
    its count when the word after it is the word the account put after one, so
    `on 40 rows` is compared with `20 rows` because the ACCOUNT said `rows` -
    nobody here wrote down which nouns are counts.
    """
    words = _Words(_spell_out(_flatten(how)))
    out: list[tuple[float, str]] = []
    for index in range(len(words)):
        parsed = _numeral(words.bare_at(index))
        after = words.bare_at(index + 1)
        if parsed is not None and after and _numeral(after) is None:
            out.append((parsed[0], after))
    return out


def _as_a_subject(
    name: str,
    frame: list[tuple],
    words: "_Words",
    ground: "Ground",
) -> tuple[str, dict[str, Any]] | None:
    """A name no tool has, read as the SUBJECT of a measurement on record.

    `(CITATION_MATCHED, notice)`, `(refutation, row)`, or `None` - and `None`
    means exactly today's refusal, `NO_SUCH_INSTRUMENT`, from `_refute`.

    MEASURED 2026-09-23, a live journey at bdc6515, thread 2 of a scratch
    database. `measure_baseline` scored `hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0`
    and stamped `baseline_score = 0.0`, "... answered 0 of 20 rows of ...", and
    the model's report opened with that tool's own summary said back:

        **Baseline (G1):** hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0 scores 0.0 on 20 rows of the (leaky) eval set.

    `_flatten` breaks the model name at its punctuation, `q8_0` is SHAPED like a
    tool, `scores` is an attribution verb, and frame 3 read the tail of a model
    name as an instrument. `_refute` never looked at the record for an
    unregistered name - there is no such tool, so what could it hold? - and the
    reply was withheld as an invented instrument, with a closing that said
    "Nothing here holds it" of a number the ledger held. The journey stopped one
    step after its first real measurement.

    THE RECORD IS READ FIRST NOW, and it has to say three things before
    anything passes:

    1. a MEASURED row's own account names `name` (`Ground.rows_about`) - so the
       name is what that measurement was OF;
    2. such a row holds the bound number - the one nearest the name, the same
       one `_refute`'s joint lookup asks about;
    3. every other number in the frame that sits where the account put a count
       (`_counts_in`) is that count, and every one that does not is backed by
       the flat pool, exactly as a registered tool's context numbers are.

    Fail 1 or 2 and this returns `None`, and the refusal is today's to the
    letter - an invented name with a number nothing about it holds is still an
    invented name. Fail 3 on a count and the refusal is `ANOTHER_COUNT`, which
    names the row, because the person's correction is the count the record
    holds and not "there is no such tool".

    THE HEADER'S INVARIANTS HOLD. No origin is guessed upward: the row is
    MEASURED or it is not read. And a model name is still not an instrument -
    it is the SUBJECT of one: the notice credits the row's `tool`, and `name`
    appears only as what was measured.
    """
    about = ground.rows_about(name)
    if not about:
        return None
    bound = next((claim for claim in frame if claim[6]), None)
    if bound is None:
        return None
    token, exact = bound[5], bound[7]
    holding = [
        (row, word)
        for row, word in about
        if any(_matches(token, value, exact=exact) for value in numbers_in(row["value"]))
    ]
    if not holding:
        return None
    row, word = holding[0]
    base = {"frame": bound[0], "decided_by": "app/provenance.py"}
    for claim in frame:
        if claim is bound:
            continue
        other, after = claim[5], words.bare_at(claim[4] + 1)
        counts = [
            (count, held_row, held_word)
            for held_row, held_word in holding
            for count, counted in _counts_in(str(held_row.get("how") or ""))
            if counted == after
        ]
        if counts:
            matched = next(
                (item for item in counts if _matches(other, item[0])), None
            )
            if matched is None:
                count, row, word = counts[0]
                return ANOTHER_COUNT, dict(
                    base, refuted_by=ANOTHER_COUNT, instrument=row.get("tool"),
                    subject=word, fact=row.get("fact"), number=token,
                    held=row["value"], origin=row.get("origin"),
                    count=other, held_count=_plain(count), counted=after,
                    record_says=(
                        f"the record holds {_plain(row['value'])} on "
                        f"{_plain(count)} {after} by {row.get('tool')}; the reply "
                        f"said {token} on {other}"
                    ),
                )
            _, row, word = matched
        elif not ground.backs(other, exact=claim[7]):
            return NOT_OURS, dict(
                base, refuted_by=NOT_OURS, instrument=None, fact=None, number=other,
            )
    return CITATION_MATCHED, dict(
        reason=CITATION_MATCHED,
        text=(
            f"{token} is {row.get('fact')} on the record, measured by "
            f"{row.get('tool')}; {word} is what it measured, not an instrument."
        ),
        fact=row.get("fact"),
        number=token,
        instrument=row.get("tool"),
        subject=word,
        named=name,
        held=row["value"],
        how=row.get("how"),
        decided_by="app/provenance.py",
    )


def _refute(
    kind: str,
    instrument: str | None,
    registered: bool,
    fact: str | None,
    token: str | None,
    ground: "Ground",
    *,
    nearest: bool = False,
    exact: bool = False,
) -> dict[str, Any] | None:
    """The lookup. Nothing here reads the sentence; it reads the records."""
    row = {"frame": kind, "decided_by": "app/provenance.py"}
    if instrument is not None and instrument != THE_HARNESS:
        if not registered:
            refused = dict(
                row, refuted_by=NO_SUCH_INSTRUMENT, instrument=instrument,
                number=token, fact=fact,
            )
            # WHO REALLY HOLDS IT, when somebody does. The name is invented and
            # the sentence stops either way, but the closing used to say
            # "Nothing here holds it" of a number an instrument here had
            # measured (2026-09-23) - so the records are asked, and the
            # instruments that hold it are named. Present only when non-empty.
            held_by = ground.producers_of(token, exact=exact) if token else ()
            if held_by:
                refused["held_by"] = held_by
            return refused
        if not ground.instrument_ran(instrument):
            return dict(
                row, refuted_by=DID_NOT_RUN, instrument=instrument,
                number=token, fact=fact,
            )
    if fact is not None:
        held = ground.holds(fact)
        if held is not None:
            values = numbers_in(held["value"])
            if values and not any(
                _matches(token, value, exact=exact) for value in values
            ):
                # UNLESS AN INSTRUMENT IN THIS CONVERSATION PRODUCED IT. The
                # current reading is not the only reading a thread has taken,
                # and a number one of its own measurements produced is not
                # invented - see `Ground.ever_measured` for the eight replies
                # this cost on 2026-09-13. The wall still catches everything it
                # was built for: a value nothing here ever measured is refuted
                # exactly as before.
                for earlier in ground.ever_measured(fact):
                    if any(
                        _matches(token, value, exact=exact)
                        for value in numbers_in(earlier["value"])
                    ):
                        return None
                return dict(
                    row, refuted_by=MISMATCH,
                    instrument=held.get("tool") or THE_HARNESS, fact=fact,
                    number=token, held=held["value"], origin=held["origin"],
                )
            return None
    if not ground.backs(token, exact=exact):
        # `instrument` STAYS `None` FOR THE LABEL FRAME, and that is not a
        # missing default. `eval_size_n: 40000` names a reading-only fact and
        # no instrument at all; filling in "the harness" would make the
        # transcript say the model attributed it to something, which it did
        # not. A log that rounds a claim up to a tidier one is the log lying
        # quietly, and this whole module exists because a number said more
        # than it had earned.
        return dict(
            row, refuted_by=NOT_OURS, instrument=instrument, fact=fact,
            number=token,
        )
    if (
        nearest
        and instrument is not None
        and instrument != THE_HARNESS
        and not ground.produced(instrument, token, exact=exact)
    ):
        # THE JOINT LOOKUP, and the only refutation that needs both halves. The
        # number is real and this conversation holds it - it is just not this
        # instrument's. Reached only when the flat pool has ALREADY backed the
        # number, so `NOT_OURS` above is never the weaker answer of the two.
        return dict(
            row, refuted_by=NOT_ITS, instrument=instrument, fact=fact,
            number=token, produced_by=ground.producers_of(token, exact=exact),
            from_the_user=any(
                _matches(token, held, exact=exact)
                for held in ground.said_by_the_user
            ),
        )
    return None


def refusal_sentence(row: dict[str, Any]) -> str:
    """The SPECIFIC half of what the user is told, from the row.

    NOT the engine's verdict, which is what the sentry's refusal says. A person
    who has just been shown a fabricated measurement has a different problem
    from a person who has just been handed a training decision the engine did
    not make, and telling them about the gates would be answering a question
    they did not ask. What they need to know is which number was not measured,
    what was claimed to have measured it, and what would.

    The fixed half - "I stopped that reply", and the next move - lives in
    `conductor.SILENT_TURN[MEASUREMENT_WITHHELD]`, where the property test in
    `tests/test_a_turn_always_speaks.py` can read it. Everything HERE is
    composed out of the row, so nothing in it can be true of a different turn.
    """
    number = row.get("number", "that number")
    reason = row.get("refuted_by")
    instrument = row.get("instrument")
    if reason == NO_SUCH_INSTRUMENT:
        head = (
            f"It showed you {number} and said {instrument} produced it. There "
            f"is no instrument in this harness called {instrument}, so nothing "
            "measured that - the name itself was invented."
        )
    elif reason == DID_NOT_RUN:
        head = (
            f"It showed you {number} and said {instrument} measured it. "
            f"{instrument} did not run in this turn and has recorded nothing "
            "in this conversation, so that number was not measured by anything."
        )
    elif reason == MISMATCH:
        head = (
            f"It showed you {row.get('fact')} as {number}. This conversation's "
            f"ledger holds {row.get('fact')} as {row.get('held')}, recorded "
            f"{row.get('origin')}, so the number you were shown is not the one "
            "on record."
        )
    elif reason == ANOTHER_COUNT:
        counted = row.get("counted") or "rows"
        head = (
            f"It showed you {number} on {row.get('count', 'a count')} {counted}. "
            f"The record holds {row.get('fact') or 'that reading'} as "
            f"{_plain(row.get('held'))} on {row.get('held_count', 'another count')} "
            f"{counted}, measured by {instrument} - the number is on record, the "
            "count beside it is not."
        )
    elif reason == NOT_ITS:
        head = (
            f"It showed you {number} and said {instrument} produced it. "
            f"{instrument} ran, but {number} is not one of the numbers it "
            f"returned - {_who_did(row)}."
        )
    elif row.get("fact"):
        head = (
            f"It showed you {row['fact']} as {number}. Nothing in this "
            "conversation produced that number - no tool ran this turn that "
            "returned it, the fact ledger does not hold it, and you did not "
            f"give it - so {row['fact']} has not been read on this machine."
        )
    else:
        head = (
            f"It presented {number} as a measurement, and nothing in this "
            "conversation produced that number - no tool ran this turn that "
            "returned it, the fact ledger does not hold it, and you did not "
            "give it."
        )
    return head + " " + _next_step(row)


def _who_did(row: dict[str, Any]) -> str:
    """Whose number it actually is, off the records rather than a guess."""
    produced_by = tuple(row.get("produced_by") or ())
    if produced_by:
        return f"{' and '.join(produced_by)} produced that one"
    if row.get("from_the_user"):
        return "it is a number you gave me, which is not a measurement"
    return "nothing here recorded it as that instrument's reading"


def _next_step(row: dict[str, Any]) -> str:
    """The door, named from the ledger rather than from a sentence here.

    "NOTHING HERE HOLDS IT" IS SAID ONLY WHEN NOTHING DOES. 2026-09-23: it was
    the fallback for every refutation with no fact and no door, and a live
    closing said it of a baseline the ledger held on 20 rows. A row that
    carries the record's own answer - `ANOTHER_COUNT`, or `held_by` on an
    invented name - is told where the number is instead.
    """
    if row.get("refuted_by") == ANOTHER_COUNT:
        return (
            f"It is on the record with the count it was measured on; "
            f"{row.get('held_count', 'that count')} is the one to say."
        )
    held_by = tuple(row.get("held_by") or ())
    if held_by:
        return (
            f"{row.get('number', 'That number')} itself is on the record, measured "
            f"by {' and '.join(held_by)} - that is the instrument to name."
        )
    fact = row.get("fact")
    if fact:
        try:
            settles = evidence.resolves(str(fact))
        except Exception:  # noqa: BLE001
            settles = {}
        tool = settles.get("tool")
        if tool:
            return f"Run {tool} and the real {fact} goes on the record."
    instrument = row.get("instrument")
    if row.get("refuted_by") == DID_NOT_RUN and instrument:
        return f"Run {instrument} and the reading it produces goes on the record."
    if row.get("refuted_by") == NOT_ITS:
        return "The number is on the record under the instrument that made it."
    return "Nothing here holds it, so there is nothing to correct it against."


def _registered_tools() -> frozenset[str]:
    """Every tool name the model could name. Read from the registry, not listed."""
    from app.tools import REGISTRY

    return frozenset(str(spec.name) for spec in REGISTRY)


def _declared() -> frozenset[str]:
    """Every fact name the ledger declares, at any source.

    Wider than `_readings` on purpose, and used for one thing only: deciding
    that a tool-shaped word is a FACT rather than an instrument this harness
    does not have.
    """
    try:
        return frozenset(evidence.spec().facts)
    except Exception:  # noqa: BLE001 - a spec we cannot read declares nothing
        return frozenset()


def _stem(word: str) -> str:
    """One word reduced to what it shares with the same word written otherwise.

    Three reductions and no more, each one a spelling difference rather than a
    meaning: a possessive (`dataset's`), a British doubled consonant
    (`labelled` - the brief's own probe sentence is spelled that way), and a
    plural (`examples`). Applied to BOTH sides of every comparison, so it can
    only ever make two spellings of one word agree; it is not a stemmer trying
    to relate different words, and `classes` reducing to `classe` is harmless
    precisely because the declaration reduces to `classe` too.
    """
    word = _bare(str(word)).lower()
    if word.endswith("'s"):
        word = word[:-2]
    word = word.replace("ll", "l")
    if len(word) > 3 and word.endswith("s"):
        word = word[:-1]
    return word


#: The ledger key that carries a fact's PROSE names, beside its declaration in
#: `docs/diagnosis_engine.yaml`. Read by `_reading_subjects`.
#:
#: THE VOCABULARY IS STILL NOT WRITTEN FROM IMAGINATION - IT MOVED HOUSE.
#: This module's docstring says the subject vocabulary is derived and not
#: written, and that rule stands. What changed is WHERE the declaration lives:
#: the ledger declares the fact, so the ledger declares what the fact is
#: called, and every name it declares is one a model was caught writing. The
#: attestation for each is in `tests/aliases_the_model_writes.py`, which
#: carries the verbatim harvested line beside every alias; a name no harvested
#: line contained is in that file's `DROPPED_UNATTESTED` and is not here.
ALIAS_KEY = "also_written"


def _declared_aliases(decl: dict[str, Any]) -> list[tuple[str, ...]]:
    """The prose names declared beside one fact, as stemmed word tuples.

    TAKEN WHOLE, and that is the difference between a declared name and a
    derived one. The derivation has to cut a key like `labeled_examples_n`
    into pieces and then guard the pieces; a declared alias arrived already
    cut, by the only editor allowed to cut it.
    """
    raw = decl.get(ALIAS_KEY) or ()
    if isinstance(raw, str):  # one alias written without a list
        raw = [raw]
    out: list[tuple[str, ...]] = []
    for alias in raw:
        words = tuple(_stem(word) for word in str(alias).split() if _bare(word))
        if words:
            out.append(words)
    return out


def _reading_subjects() -> dict[tuple[str, ...], str]:
    """The prose names of the reading-only facts -> the fact each one names.

    `labeled_examples_n` is the key a ledger uses and *"labeled examples"* is
    what a model writes, and they are the same fact. Two routes turn the one
    into the other, and NEITHER of them is a word list written here:

    * **splitting the declared key on its underscores**, which is what this
      function has always done and still does. It is what makes a fact added
      to `docs/diagnosis_engine.yaml` tomorrow covered on the day it lands,
      and it is not going anywhere.
    * **the `also_written` names declared beside the fact**, because the
      splitting route knows THE LEDGER'S NAME FOR EACH FACT AND NOT ENGLISH'S.
      It knows `disk_free_gb` as *"disk free"*; the model writes *"Free Disk
      Space: 500 GB"* - the same fact, the words in the other order - and the
      wall read straight past it. Measured against the harvested banks, the
      derivation alone stopped 2 of 112 sibling fabrications.

    THREE RULES WERE MEASURED FOR THE DERIVED NAMES. Each was re-decided for a
    declared one rather than carried over, because a declared alias is already
    the English the derived one is trying to reach:

    * **Unit and index tails come off** - DERIVED ONLY. `vram_gb` is "vram"
      because nobody writes the `gb` as part of the noun. A declared alias has
      no `_gb` to shed, and `_UNIT_WORDS` holds `at`, `k` and `n`, so applying
      the rule to declared prose would cut *"recall at k"* down to *"recall"*
      and hand the wall a word about every classifier ever scored.
    * **A `bool` fact is not in here** - BOTH. The rule is about the FACT and
      not about how its name was spelled: a bool holds no number, so a number
      beside it is not a reading of it whatever it is called. It needs no code
      of its own here; the loop declines a bool fact before it ever reads the
      declaration, so an alias declared on one is skipped with it.
    * **A fragment must be at least two words** - DERIVED ONLY, because there
      are no fragments. The rule exists to stop the SPLITTING from handing the
      wall junk sub-spans ("has free", "at k") and lone head nouns; a declared
      alias is never split, so nothing is generated to guard. What that leaves
      is the declared ONE-WORD alias, which is not covered by any rule above
      and is where the entire false-catch surface lives - *"gpu"*, *"vram"*,
      *"columns"*, *"precision"*, *"quantization"* are ordinary English. Those
      are not ruled on. They are MEASURED, one at a time, against the harvested
      banks, and the ones that bought nothing are not declared. That sweep is
      in `test_a_fabrication_in_ordinary_english_is_still_a_fabrication.py`: it
      scored 101 attested aliases one at a time and found SEVEN that carry the
      entire result. `gpu`, `quantization` and `precision` - the three words the
      harvest called the whole false-catch surface - cost zero false catches AND
      bought zero catches, so they are attested, measured, and still absent.

    RANK: a fact's OWN full derived name still outranks everything, then the
    declared aliases, then another fact's mechanical fragment. So "baseline
    score" stays `baseline_score` rather than `trivial_baseline_score`, and a
    declared name beats a sub-span nobody chose.

    What is still given up is the head noun on its own where no alias declares
    it: *"your dataset contains 40,000 rows"* is not read, because `rows` alone
    comes from `tabular_rows` and "rows" is a word about tables, spreadsheets,
    screens and query results. That is a declared miss rather than a solved
    problem - see the module docstring.
    """
    try:
        declared = evidence.spec().facts
    except Exception:  # noqa: BLE001 - a spec we cannot read declares nothing
        return {}
    fragments: dict[tuple[str, ...], str] = {}
    aliases: dict[tuple[str, ...], str] = {}
    whole: dict[tuple[str, ...], str] = {}
    for name in sorted(declared):
        decl = declared[name]
        if decl.get("source") != "inspect" or decl.get("type") == "bool":
            continue
        for alias in _declared_aliases(decl):
            aliases.setdefault(alias, name)
        core = name.split("_")
        while core and core[-1] in _UNIT_WORDS:
            core.pop()
        if not core:
            continue
        stem = tuple(_stem(word) for word in core)
        whole.setdefault(stem, name)
        spans = [
            (low, high)
            for low in range(len(stem))
            for high in range(low + 2, len(stem) + 1)
        ]
        for low, high in spans:
            fragments.setdefault(stem[low:high], name)
    # A DECLARED NAME BEATS A MECHANICAL FRAGMENT, and a fact's OWN full name
    # beats both - so "baseline score" is `baseline_score` and not
    # `trivial_baseline_score`, exactly as before this key existed.
    fragments.update(aliases)
    fragments.update(whole)
    return fragments


def _readings() -> frozenset[str]:
    """Declared facts an instrument reads, off the ledger's own declarations.

    `source: inspect` is the ledger's word for "something on this machine can
    read this". Those are the facts a model naming a value for is claiming an
    instrument produced. `source: ask` facts are the person's own answers and
    are not in here - a model repeating back what somebody told it is not
    claiming a measurement.
    """
    try:
        declared = evidence.spec().facts
    except Exception:  # noqa: BLE001 - a spec we cannot read declares nothing
        return frozenset()
    return frozenset(
        name for name, decl in declared.items() if decl.get("source") == "inspect"
    )


# ══ A GATE IS A WORD, AND WORDS WERE NOT CHECKED ═══════════════════════════
#
# Everything above this line guards NUMBERS. It works: on thread 34 the reply
# that showed Max `ram_gb = 32` was stopped mid-stream, correctly, because no
# instrument had produced that figure.
#
# Three sentences earlier in the same conversation, the same model told him:
#
#     "An eval set exists, which is crucial for measuring performance."
#     "A baseline score was measured, indicating some level of performance."
#     "Prompting has been exhausted with at least three iterations and an
#      automated optimiser run."
#
# `fact_evidence` for that thread holds ZERO rows. Not one of those had
# happened. They passed every wall in this file because a gate status is a
# WORD - `PASSED`, `NOT_MET` - and the walls read digits.
#
# `AGENTS.md` invariant 4 says the five-gate test may never be weakened. It is
# enforced in `app/diagnosis.py`, where no fact means no gate, and it was
# unenforced in the sentence the person actually reads. This closes that.
#
# ── WHY THE GATE'S OWN ID IS THE VOCABULARY ─────────────────────────────────
#
# The same argument `_reading_subjects` makes for facts. A hand-written list
# of phrases would be stale the day a ledger adds a gate, and it would be this
# file inventing English. The gate ids already ARE the English:
#
#     G0_EVAL_SET                 -> "an eval set exists"
#     G1_BASELINE_MEASURED        -> "a baseline score was measured"
#     G2_PROMPT_EXHAUSTED         -> "prompting has been exhausted"
#     G3_RETRIEVAL_CONSIDERED     -> "retrieval has been considered"
#     G4_CHEAPER_MODEL_CONSIDERED -> "a cheaper model was considered"
#
# Every one of the model's fabricated sentences is its own gate's id with the
# underscores taken out. So the id is split, stemmed, and matched - and a
# ledger that adds `G5_THE_RUN_IS_BOUNDED_AND_RECORDED` tomorrow is covered
# that day, by the same rule, with nothing written here.
#
# ── WHY THIS IS DELIBERATELY NARROW ────────────────────────────────────────
#
# A guard that stopped honest sentences would be worse than the hole it
# closes: this product's model has to be able to say "we need an eval set",
# "once a baseline is measured", "I could not find a baseline". So a sentence
# is only refused when it asserts the gate SATISFIED, in the past or present,
# with no negation and no modal - and even then only when the engine's own
# ledger says that gate is not passed. Every other shape is released. The
# failure mode is to miss a fabrication, never to block a true sentence, and
# `tests/test_a_gate_is_not_a_word_it_is_a_row.py` holds both halves.

#: Words that turn a gate mention into a plan, a question or a wish rather
#: than a claim. Their presence anywhere in the sentence releases it.
#:
#: `criterion criteria threshold target goal` joined on 2026-09-11 from a live
#: false catch. A plan-mode turn wrote a six-phase plan in 28 seconds and
#: this reader withheld the whole reply for one line of it: *Exit criterion:
#: baseline_score + trivial_baseline_score measured on same eval set; adapter
#: score beats baseline by >=1 point.* That is a CRITERION - the model naming
#: the measurement that would settle a phase, which is exactly what the
#: planning note asks it to do - and `measured` put it past the verb check
#: while nothing in this set said it was a plan. A sentence that names its
#: criterion is planning, by definition.
_NOT_YET_A_CLAIM = frozenset(
    """
    not no never none unless until unfinished missing lacks lack without
    if once when whether should would could might may will shall need needs
    needed must let lets go first next then before after
    criterion criteria threshold target goal
    """.split()
)

#: Verbs that assert a state already reached. One of these must be present,
#: or the sentence is not claiming anything yet.
_ASSERTS_IT_HAPPENED = frozenset(
    """
    is are was were has have had exists existed passed passes met done
    complete completed satisfied ran run measured recorded confirmed
    """.split()
)


#: Words inside a gate id that carry no subject. Dropped before matching.
_GATE_STOP_WORDS = frozenset("the a an and or is are of to for in on at it".split())


def _gate_words(gate_id: str) -> tuple[str, ...]:
    """One gate id as the words a person would write, stemmed.

    `G1_BASELINE_MEASURED` -> `("baselin", "measur")`. The `G<n>` prefix is
    dropped because it is an index rather than a word; everything after it is
    the sentence the gate is about.
    """
    parts = [part for part in str(gate_id).split("_") if part]
    if parts and re.fullmatch(r"[Gg]\d+", parts[0]):
        parts = parts[1:]
    # `G5_THE_RUN_IS_BOUNDED_AND_RECORDED` carries three words that are in
    # every English sentence. Requiring them would make the gate unmatchable;
    # they are not what the gate is about.
    parts = [part for part in parts if part.lower() not in _GATE_STOP_WORDS]
    # Words too short to be distinctive would match half of English. `set` is
    # kept only because it never appears alone - every gate needs ALL its
    # words present - and dropping it would make G0 match on "eval" alone.
    return tuple(_stem(part) for part in parts if len(part) > 2)


def _mentions(word: str, said: list[str]) -> bool:
    """Is this gate word in the sentence, allowing for how English inflects?

    `prompt` has to match *"prompting"*, `exhaust` *"exhausted"*, `consider`
    *"considered"*. `_stem` handles plurals and possessives and deliberately
    does not try to be a stemmer, so the tail is handled here instead, in the
    one direction that is safe: the SENTENCE's word may be longer than the
    gate's, never shorter, so `set` cannot be matched by `s`.
    """
    for token in said:
        if token == word or (len(word) > 3 and token.startswith(word)):
            return True
    return False


#: A sentence that talks about a gate AS a gate. Soft fact narration
#: ("a baseline score was measured") is not this; naming `G1_…`, saying
#: "gate", or asserting the gate id itself is.
_GATE_AS_A_GATE = re.compile(
    r"\b(?:gates?|G\d+(?:_[A-Za-z0-9]+)+)\b", re.IGNORECASE
)


def names_a_gate_as_a_gate(sentence: str) -> bool:
    """Does this sentence talk about a gate row, not only about a fact?"""
    return _GATE_AS_A_GATE.search(str(sentence) or "") is not None


def gates_claimed_by(sentence: str, gate_ids: Iterable[str]) -> list[str]:
    """Which gates this sentence asserts as already satisfied.

    Empty for every sentence that plans, asks, negates or hedges - see
    `_NOT_YET_A_CLAIM` - which is the overwhelming majority of what a model
    writes about gates and all of it legitimate.

    A sentence that names the gate id in full (`G1_BASELINE_MEASURED is
    satisfied`) is a claim even when the id arrives as one token - the
    underscore form is how the ledger spells the gate, and splitting it into
    English words would miss the very sentence that is most explicitly a claim.
    """
    text = str(sentence or "")
    said = [_stem(token) for token in re.findall(r"[A-Za-z_]+", text)]
    if not said:
        return []
    spoken = set(said)
    if spoken & _NOT_YET_A_CLAIM:
        return []
    if not (spoken & _ASSERTS_IT_HAPPENED):
        return []
    upper = text.upper()
    claimed = []
    for gate_id in gate_ids:
        name = str(gate_id)
        if name.upper() in upper:
            claimed.append(gate_id)
            continue
        words = _gate_words(name)
        if words and all(_mentions(word, said) for word in words):
            claimed.append(gate_id)
    return claimed


def _facts_for_gate(gate_id: str) -> frozenset[str]:
    """Facts the primary row of this gate reads. Empty if the ledger is mute."""
    try:
        from app import diagnosis

        spec = diagnosis.load_spec(diagnosis.DEFAULT_LEDGER)
        for row_key in ("any", "llm_weights", "llm_policy"):
            facts = spec.gate_row_facts.get((str(gate_id), row_key))
            if facts:
                return frozenset(facts)
        # Any row that names the gate, if the class rows above missed.
        for (gid, _row), facts in spec.gate_row_facts.items():
            if gid == gate_id and facts:
                return frozenset(facts)
    except Exception:  # noqa: BLE001 - a mute ledger means nothing is earned
        return frozenset()
    return frozenset()


def _gate_facts_are_earned(
    gate_id: str, fact_origins: Mapping[str, Any] | None
) -> bool:
    """Have the facts this gate reads been MEASURED on this thread?

    Soft narration of a measurement ("a baseline score was measured") is not
    the same as claiming the gate row PASSED. When the instruments have stamped
    those facts, soft narration is true even if the walk has not yet reached
    the gate node (NOT_REACHED). When they have not, soft narration is the
    thread-34 fabrication and is refused.
    """
    if not isinstance(fact_origins, Mapping) or not fact_origins:
        return False
    needed = _facts_for_gate(gate_id)
    if not needed:
        return False
    return all(fact_origins.get(name) == "MEASURED" for name in needed)


def reads_as_a_gate_claim(
    sentence: str,
    gate_ledger: dict[str, Any] | None,
    *,
    fact_origins: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """A gate this sentence says is satisfied that the engine has not passed.

    `gate_ledger` is the engine's own walk - `diagnosis`'s `gate_ledger`, the
    same object the card draws - so the comparison is against what this
    conversation actually reached and never against a second opinion computed
    here. `None` or an empty ledger means the engine has not walked at all,
    and a sentence claiming a gate in that state is claiming a walk that never
    happened, which is the thread-34 case exactly.

    TWO KINDS OF CLAIM, and they are not the same wall:

    * **Hard** - the sentence names a gate as a gate (`G1_…`, "the gate is
      satisfied"). Withheld unless the walk says `PASSED`.
    * **Soft** - the sentence narrates the facts a gate reads ("a baseline
      score was measured"). Withheld unless those facts are MEASURED on this
      thread, OR the walk already says `PASSED`. Soft narration over earned
      facts is allowed even when the gate row is still `NOT_REACHED` - the
      walk has not evaluated the node yet; the measurement did happen.
    """
    if not isinstance(gate_ledger, dict):
        gate_ledger = {}
    known = list(gate_ledger) or list(_ledger_gate_ids())
    if not known:
        return None
    hard = names_a_gate_as_a_gate(sentence)
    for gate_id in gates_claimed_by(sentence, known):
        status = (gate_ledger.get(gate_id) or {}).get("status")
        if status == "PASSED":
            continue
        if not hard and _gate_facts_are_earned(gate_id, fact_origins):
            continue
        return {
            "gate": gate_id,
            "claimed": "satisfied",
            "engine_status": status or "never walked in this conversation",
            "sentence": sentence.strip(),
            "decided_by": "app/diagnosis.py",
        }
    return None


def _ledger_gate_ids() -> tuple[str, ...]:
    """Every gate id this product knows, for a turn with no walk to compare to.

    THE UNION ACROSS ALL THREE LEDGERS, and by absolute path. Both halves were
    defects the first time this was written:

    * `diagnosis.DEFAULT_LEDGER` is `docs/diagnosis_engine.yaml` - a RELATIVE
      path, resolved against the process's working directory. Called from the
      engine it finds the file; called from `tests/` it raises
      `FileNotFoundError`, and the wall silently declared no gates and let
      every fabrication through. `known_ledgers()` returns absolute paths,
      which is the same door `events.create_thread` validates against.
    * one ledger's gates are the wrong vocabulary for a thread on another
      ledger. A conversation on `harness_design.yaml` narrating
      `G5_THE_RUN_IS_BOUNDED_AND_RECORDED` deserves the same wall, and the
      union costs nothing: gate ids are distinct across ledgers, and a gate
      that is not in the thread's own walk is compared against a status of
      "never walked" either way.
    """
    try:
        from app import diagnosis

        ids: list[str] = []
        for path in diagnosis.known_ledgers():
            try:
                ids.extend(diagnosis.load_spec(path).gates)
            except Exception:  # noqa: BLE001 - one unreadable ledger is not all of them
                continue
        return tuple(dict.fromkeys(ids))
    except Exception:  # noqa: BLE001 - a spec we cannot read declares nothing
        return ()


def gate_refusal_sentence(row: dict[str, Any]) -> str:
    """The SPECIFIC half of what a person is told about a fabricated gate.

    Same division of labour as `refusal_sentence`: everything here is composed
    out of the row, so no sentence it produces can be true of another turn,
    and the fixed half lives in `conductor.SILENT_TURN[GATE_WITHHELD]` where
    the property test can read it.

    It names the gate the way the ledger names it, because that string is what
    the person will see on the card and in the report, and a friendlier
    paraphrase here would be a second vocabulary for one thing.
    """
    gate = row.get("gate", "a gate")
    status = row.get("engine_status") or "not passed"
    if status == "never walked in this conversation":
        return (
            f"It told you {gate} was satisfied. The diagnosis has not walked "
            "in this conversation at all, so no gate has been opened or "
            "closed here - that sentence described a ledger that does not "
            "exist yet."
        )
    return (
        f"It told you {gate} was satisfied. The engine's own walk has that "
        f"gate at {status}, and the gate is what the walk says it is - the "
        "reply does not get a vote."
    )
