# How to verify

Laws about checking work, each one learned from a defect that shipped or nearly
shipped. Sequence keeps a page like this; the harness needs one because the
same mistakes recur across agents who never met each other.

One paragraph per law. Every law cites the commit where it was learned, so the
reasoning can be read back rather than taken on trust. Add to this page when a
check turns out to have been the wrong check — that is the only kind of entry
worth having here. Do not add advice nobody has been bitten by.

`AGENTS.md` carries the execution discipline (branch first, one step per run,
the full gate before a commit). This page is narrower: it is about whether a
check proves what you think it proves.

`docs/walks.md` is this page's neighbour: the walks themselves, what each one
found, and where the next one starts. Read it before walking, so a moment
somebody already fixed is not found twice.

**If you arrived here to review rather than to build, start with the claim.**
This page and its neighbour are about whether a check proves what it says; they
do not state what the product asserts, and a reader who has only these two
cannot tell what any of it is in service of. The claim is in `README.md` and
`docs/VISION.md`, in one sentence: this decides whether you should train a model
at all, and refuses to say yes on anything it has not measured. What the pages
here are for is the second half of that sentence - the evidence, and the
occasions it turned out to be worth less than it looked.

## The laws, in one screen

Thirty-one laws is past what anyone reads to find the one that applies to
them, and item 31 had just finished proving this page's neighbour was ordered
for its writer rather than its reader. The section names are italic and the laws are not, because the check in
`tests/test_every_law_is_cited_to_something_real.py` reads a law as a line
opening in bold - an index that dressed its own headings as laws would
inflate the count that test reports. Each claim below is the law's own first
sentence, so this index cannot drift into a paraphrase of what the law says.

*The refusal laws*

- An empty refusal is a defect.
- Nothing failed is not nothing was checked, and the two need different words.
- Prove each gate can fail before trusting the screen that reports it.
- Denominators travel with the number.
- One fact wears one number.
- Weigh the clause that says the material does not exist, and let nothing that produces nothing from nothing look like a way out.

*The stranger laws*

- A click is answered where it happened.
- A wait says how long.

*The instrument laws*

- Verbatim is a floor, not a guarantee of meaning.
- A tool's handler must accept what its schema advertises.
- A guard that knows only half of what it guards will wave the danger through.
- A guard is not trusted until it has been seen to fail.
- A covering is measured, not claimed.
- Verify the instrument before reporting a defect.
- The four questions that would have caught thirteen of fourteen.
- Measure after a real reload, against the code you are testing.
- A fixture carries the engine's real sentence, not a paraphrase.
- A UI change is not done until someone has looked at it.
- A citation you did not open is a rumour.
- A gate that can say no cheaply is worth more than an experiment that says maybe expensively.
- One `sys.path` line decides which engine a client trusts.
- If an import HANGS, check whether the working directory is outside the checkout.
- A pid is not an identity, and a device that decides on one is deciding on a number somebody else may be using.
- A filter tightened against one wrong answer can be loosened into another, and the second one is quieter.
- A negative test survives a corrupted fixture, so a fixture must be checked against something other than its own assertion.
- A suite that reads its own repository cannot be trusted through a commit.
- A lock that prevents a collision buys the prevention with a queue, and the queue has to be measured rather than assumed.
- The instrument that catches it:
- A suite that reports OK must also report how many it ran against how many exist.
- Read a key row by row before you measure against it.
- Two label sets that disagree are a rubric that did not decide.
- An arm comparison needs a "B must beat A" condition.
- `ran == discovered` cannot see a module that did not import.
- Prove the mutation landed before believing a test caught it.
- A judge whose stated reason can contradict the text it judged has no reason, only a verdict.
- Build both halves of a defence and put both on the path people use.
- The day's one red push came from a shell operator, not from the gate.
- A verdict is only about the tree it was computed on, so the lock's scope is gate-plus-push.  *(2026-09-06: the lock cannot stop the remote moving - see the law below.)*
- Do not move HEAD under a running gate; the lock serialises suites, not git.
- A start time compared as a number is not compared at all.
- One machine can have two true names, so compare by membership.
- A lock that cannot stop the ref moving protects the gate, not the push.
- When a shared resource mis-resolves, it mis-resolves toward one lane, and that lane cannot see the harm.
- A count without its denominator is a ceiling, and should be named one.
- A gate that skipped a check is not a gate that ran it, and the skip says so where nobody reads.
- Call the function. A copy is a fork that agrees for now.
- A suite that only passes on a prepared machine is testing the preparation.
- A law's instance list is a count, and nobody audits it.
- A guard inside the thing it audits must decide from runtime facts on BOTH sides.
- A check that cannot identify its subject must not convict it.


## The refusal laws

**An empty refusal is a defect.** A screen that exists to explain a refusal
must never render nothing. `blocked_by` read the first gate whose status was
FAILED, which is correct for every route where something failed and silent for
every route where nothing did — and a route can be blocked with all five gates
NOT_REACHED, because the engine writes a gate's clause only when it evaluates
one. Thread 39 was `BLOCKED__DEFINE_SUCCESS_FIRST` in exactly that state and
the block rendered empty. If a surface's whole job is to say why, then "no
reason available" is a bug in the surface, not a fact about the route.
Learned in `3a0556e`.

**Nothing failed is not nothing was checked, and the two need different
words.** An unreached gate is not a gate that came back false; they call for
different next moves, and a screen that labels the first unchecked rule "the
rule that stopped this" states something the reader can act on and be wrong
about. Where the applicable rule depends on a class the run has not chosen,
say the class is undecided rather than quoting one — naming the wrong class's
rule teaches a rule the run is not being judged by. Learned in `3a0556e`.

**Prove each gate can fail before trusting the screen that reports it.** A
refusal format is only as good as its worst gate. Reading the first FAILED
gate is worth nothing if some gate can never reach FAILED, or reaches it
carrying no clause: the screen is then silently empty on exactly the refusal it
exists for, and no test notices. There is now a case per gate, and the clauses
those cases quote are checked against `docs/diagnosis_engine.yaml` itself, so
editing a rule in the ledger without editing the test fails rather than leaving
the screen quoting a rule the engine no longer applies. Learned in `3a0556e`.

**Denominators travel with the number.** "3 passed" carries "of 5". Two
percentages carry the row count they were computed over, because 7% against
13% is a different claim on 30 rows than on 300. The denominator belongs on
the same line as the number, not in prose two lines below — prose near a
figure is not the same as a figure that carries its own scale. In the case
that prompted this the engine had measured the denominator all along and the
card simply dropped it. Learned in `3a0556e`.

**One fact wears one number.** The outcome card stated the same next move
twice in different units — the engine's "Grade 403 more rows" beside a newly
added "about 433 paired rows". Both were correct and agreed; a reader still
has to stop and work out that they agree. An added line must yield when
something else is already saying it. Learned in `3a0556e`.

**Weigh the clause that says the material does not exist, and let nothing that
produces nothing from nothing look like a way out.** "I want to fine-tune a
model so it writes product copy in our brand voice. I don't have a dataset yet"
mapped to the route whose first step is "record where your material lives": the
words `fine-tune` and `model` were weighed and the sentence saying there was
nothing to point at was not. Step five of that route then offered
`synthesize_rows`, "data generation: amplify the training half" - a sampler
that copies existing answers verbatim and yields nothing from an empty input,
which is exactly what somebody with no data will read as an offer to make the
first examples. Say the route cannot start, quote the words they used to say
so, name what makes it passable, and say plainly that the sampler produces
nothing from nothing - the first examples have to be real, and theirs. And do
not switch their goal while doing it: telling somebody what is missing is a
different product from quietly choosing a different destination for them.
Learned in `5801797`, table corrected in `4aee292`.

## The stranger laws

**A click is answered where it happened.** The suggestion cards on the empty
thread filled the composer and did nothing else — the card sits about a
hundred pixels above the box it writes into, and focus stayed on the button.
Nothing was broken, the text was there, which is the worst kind of stuck: it
reads as "the product ignored me" and the next move is to click again. If an
action's only effect is off where the person is not looking, the action needs
to move them to it. Learned in `838fd1a`.

**A wait says how long.** After sending, the transcript's whole account of a
running turn was a blinking caret. Against a local model on an 8 GB card, 80
seconds passed with nothing else on screen and nothing separating working from
hung — which is the only question a person has while they wait. The caret was
put there so the interface would never be silent while the engine works; the
intent was right and a blinking cursor did not carry it. Show the one measured
thing available, elapsed time. Not a progress bar: the engine cannot know how
many tokens are coming, and a bar filling at a made-up rate invents the number
this product refuses to invent. Learned in `838fd1a`.

## The instrument laws

**One `sys.path` line decides which engine a client trusts.** The chain is
four links and nobody had drawn it end to end: `sys.path` decides which `app` is
imported, the imported `app` decides `data_root()`, `data_root()` decides
`ENGINE_FILE`, and `ENGINE_FILE` holds the token a local client presents. So a
single missing line moves the package, the data root, the engine file and the
secret together. Measured 2026-09-06 across the two checkouts on this machine:
they share one virtualenv whose editable install maps `app` to one specific
tree, so a process in EITHER tree that does not put its own checkout first
imports the other lane's code, resolves the other lane's data root, and
authenticates against the other lane's engine. The benign reading - a launcher
pinning one `MLH_TOKEN` for both - was ruled out rather than assumed: the two
published token digests differ and `MLH_TOKEN` is unset. Two engines, two
secrets, and a bare import picks the wrong one. **No lock prevents this**: two
lanes serialised by a mutex still import the same package, which is a different
axis from everything the suite lock is about. `scripts/gate.py` inserts its own
repository at line 61 and is correct; anything written without that line is
correct only by accident, and the accident points at one lane - so the lane
positioned to notice is the lane that cannot be hurt. Recorded in
`docs/judge_runs/2026-09-06-two-suites-two-checkouts-result.md`, found by the
one item the affected lane wrote down before the run and the reconstruction of
its list did not contain.

**If an import HANGS, check whether the working directory is outside the
checkout.** Unexplained as of 2026-09-06 and written down because it will be the
cause of something else: a bare `import app.security` from a working directory
inside no checkout did not complete in six attempts - three timed out at 60
seconds under the load of two concurrent suites, three at 180 seconds on a quiet
machine, and one ran more than eight minutes **with the CPU at 0%** before it
was abandoned. The same import answers in seconds from inside a checkout, and
4,406 tests importing it finish in under twelve minutes. One probe under the
same conditions did succeed, earlier the same evening, which is why this is an
anomaly rather than a rule. No diagnosis is offered here on purpose: what is
recorded is the symptom, the conditions, and that it is not understood.

**Verbatim is a floor, not a guarantee of meaning.** A wall that enforces
"nothing invented" does not enforce "nothing false". Carving this repository's
own stylesheets into training rows produced: q "In styles_shell.css, what value
is declared for `--r-18`?", a "a rounded rectangle with a circular send reads as
a composer". Every word of that answer is in the file - it is a sentence from a
comment discussing the token - so every data wall held and the row is still
false. It says a token's declared value is a sentence about composers, and a
model trained on it learns exactly that. The corollary is the uncomfortable
half: prose about tokens is what produces these, so the better documented a
file is, the more of them it yields, and a careful author's work poisons a
corpus fastest. Where a file type has a grammar, read the grammar: a value is
what a declaration parse says it is, never what a search finds near the name.
Measured before overselling it - across all fourteen stylesheets in
`frontend/src` the pattern carved 169 rows and exactly 1 was not a declaration,
0.6%; the class of defect is what matters here, not its rate in one corpus.
Learned in `f9de826`, where the first fix stripped comments from the text and
left two further shapes of the same bug; fixed at the grammar in `cf9754d`,
which is also where the planted test earned its keep - the first draft of it
passed with and without the fix.


**A tool's handler must accept what its schema advertises.** A decorator binds
to whatever function follows it. A plain helper added directly beneath
`@tool(name="map_the_ask", ...)` took the decorator, so the registry advertised
a tool requiring `ask` whose handler took no arguments at all, and the real
implementation sat below it undecorated. `map_the_ask` is the first tool the
conductor calls on the first message of every new thread, so every stranger's
opening turn ended in an apology about a broken tool - while 3,827 tests
passed. The guard is general because the defect class is: for all 67 tools, a
required property the handler cannot accept, and a handler argument with no
default the schema never mentions, are both errors. Only `instrument` and
`ledger` may appear on a handler without being in its schema, and only when
the spec says it wants them. Learned in `8d7776e`.

**A guard that knows only half of what it guards will wave the danger
through.** `scripts/one_gate_at_a_time.py` exists so two full suites cannot run
on this machine at once, and it recorded one pid: its own. `Stop-Process
-Force` on that wrapper does not touch the suite it started, so the wrapper
died, the run kept going, and `--status` reported the lock **stale** — because
stale was defined as "the pid I wrote down is gone", and the pid it wrote down
was never the thing that needed to be gone. A second lane reading that would
have taken the lock and started a suite beside a live one: the collision the
file exists to prevent, arriving through the file itself, and arriving quietly,
because a stale lock is exactly what a correct lock looks like after a clean
finish. The rule is not "record more pids" — it is that a device asserting
something is finished must be able to see every process whose finishing it is
asserting. The lock now records the child, a holder is gone only when **both**
are gone, and an orphaned lock says which pid is still running and is waited for
rather than taken. The instrument is a planted case: a dead wrapper with a live
child, where `acquire` must refuse; and it was watched live, a second caller
waiting while `SECOND SUITE STARTED` never printed. Learned in `4abaa3a`.

**A guard is not trusted until it has been seen to fail.** The check above was
run against the defect exactly as it shipped, and reports "map_the_ask
advertises 'ask' but its handler (journey_names) does not accept it". A test
written after a fix, never run against the bug, is a test that passes for
reasons nobody has checked - the same argument as proving each gate can fail.
Learned in `8d7776e`, and it is the same law as `3a0556e`'s at a different
scale.

**A covering is measured, not claimed.** An eval set is a covering of its axes,
and a coverage table written by hand drifts from the briefs within a week and
then quietly lies. `tools/coverage.py` in the frontend-eval repository
regenerates the table and fails on a stale one, on a brief with no tags, or on
a tag naming a value the axes do not declare. It also made an uncovered cell
visible that nobody would have written down: no brief asks for expressive
motion, so that eval cannot tell a restrained model from an incapable one.
Learned on the design-model eval set, which lives in a `frontend-eval`
repository on this machine with no remote — so a reader cannot open it, and
this paragraph carries its own evidence rather than a pointer nobody can
follow: fifty briefs, nine axes, every axis value covered except
`motion=expressive`, and the generator refusing a stale table, an untagged
brief, or a tag naming a value the axes do not declare. Recorded here because
the law is not specific to that set.

**Verify the instrument before reporting a defect.** Four times now a product
has been accused of a fault belonging to the harness testing it. A walk script
clicked before the confirm had rendered, so no HTTP request was ever made and
the product looked broken. A synthetic Return never reached React's handler, so
the composer looked like it ignored Enter - a click sent immediately and the
handler was correct all along. A thread URL appeared to load an empty thread,
and there is no such route: the URL was invented and the dev server serves
index.html for any path. A coordinate click on the send button, on the button's
measured centre, did not submit; the same button submitted at once when
clicked directly. Every one of these looked exactly like a product bug. When a
check fails, the check is the first suspect, not the second, and a defect is
reported only after the instrument has been shown to work. Learned in
`e791403` and `838fd1a`, and the count is kept current on purpose - a law that
miscounts its own evidence is the drift this page exists to prevent.

**The four questions that would have caught thirteen of fourteen.** The
instrument faults from one night of walks were grouped by cause: fourteen
faults, six causes, the largest four. They are not fourteen different
mistakes, so they are worth a checklist rather than more suspicion.

- *Is the view real?* Three faults were a stale or partial view — a screenshot
  taken mid-transition, a dialog that had restored an earlier scroll, and a
  browser pane collapsed to a **zero-size viewport**, which made every geometry
  number read 2px and produced a convincing "the tool is 1,950px off screen".
  Read `innerWidth`/`innerHeight` before believing any measurement of layout.
- *Did the action reach the product?* Four were an instrument that could not
  drive it — a synthetic keypress that never reached React, a coordinate click
  on a button's own measured centre that did not submit, a test invoked so its
  helper could not import, a module reloaded into a registry that refuses
  duplicates. Confirm the request happened before calling the response wrong.
- *Am I reading all of the answer?* Two were self-inflicted truncation — a
  print cut at 1,600 characters that hid `ignored_arguments`, and reading only
  `summary` from a refusal that carried `missing`, `detail` and the full
  parameter docs. Both nearly became reports of defects that did not exist.
- *Does the thing I am measuring against exist?* Two were measuring against
  nothing — an invented URL for a route that was never defined, and a gate
  script run from a scratchpad so `sys.path[0]` was not the repository.

Learned across `e791403` through `29d7114`; the counts are in `docs/walks.md`.

**Measure after a real reload, against the code you are testing.** A stale
engine served pre-change code and made a correct UI look broken; the same
session later restarted an engine that wrote a portfile naming a different
port than the one it was listening on, because the portfile takes its port from
config rather than from the flag. The product now shows a banner when the
engine's revision differs from the page's, and that banner is evidence, not
noise — if it is on screen, stop and restart before believing anything else you
see. Learned in `e791403`, and the banner earned its keep in `838fd1a`.

**A fixture carries the engine's real sentence, not a paraphrase.** A test
fixture held a shortened stand-in for an engine message. Every assertion
passed while the real string on screen said something the tests could not see
— which is how a screen passes its suite and reads wrong in the product. Copy
what the engine actually served. Learned in `3a0556e`.

**A UI change is not done until someone has looked at it.** `AGENTS.md` states
this and it keeps paying: two defects in `3a0556e` and both moments in
`838fd1a` were invisible to a passing test suite. A count that broke across
three lines at the pane's real width, and a duplicated next move, were each
caught by a screenshot with every test green. When a screenshot shows a layout
fault, measure it — `getBoundingClientRect()` after a real load — fix it, and
measure again, so the record carries numbers rather than an opinion.
Learned in `3a0556e`.

**A citation you did not open is a rumour.** Three claims were repeated across
two sessions on 2026-09-04 before anybody read the line they pointed at, and
each was wrong in a different way: `recipe.toml` asserted "the harness asserts
exactly one recipe may score an adapter" and cited a test whose docstring says
it a hundred lines from where the citation implied; a merge was credited to
`dpo_trainer.py:578-580`, which a test at
`test_a_preference_run_continues_an_sft_pass.py:496` records as DELIBERATELY
REMOVED because the merge is the recipe's now, so citing trl credits the wrong
code; and "a DPO adapter cannot be scored" survived two rewrites before anyone
called `score_the_adapter` and found it takes `adapter_dir` as a parameter. The
prose in a file is not evidence about the file, including prose you wrote
yourself an hour earlier. Open the line. Learned in `78b00ee`.

The cleanest example came an hour later, and it cost two lanes and the
orchestrator half an hour. A portfile line appeared in a gate's stderr -
`engine.json` "already belongs to pid N, which is still running, so this
process did NOT publish its token" - and was quoted as the mechanism by which
two suites collided. It was reasoned from three times, and a ruling was issued
on it: make the second process fail loudly instead of deferring. Nobody had
opened the line. It is asserted output -
`tests/test_the_engine_publishes_what_it_is.py:375` plants a portfile owned by
a live pid and expects exactly that sentence. The isolation the ruling asked
for already existed, in `support.sandbox()`, with a guard that derives the
sandboxed globals from the modules so the next one cannot be forgotten; and the
change would have broken a documented, incident-driven deferral that exists
because a second engine once rewrote the token and handed every local client a
401. A string that looks like a symptom is not a symptom. Grep tells you the
text exists; only opening the file tells you who wrote it and why.

The honest coda: **the mechanism of the 3,315-of-3,822 collision is still
unknown.** It was not the portfile. That is precisely why the count assertion
in `scripts/gate.py` is the right guard - it does not depend on knowing the
cause. A guard that needs a diagnosis first is a guard that fails on the next
cause nobody diagnosed.

**A gate that can say no cheaply is worth more than an experiment that says
maybe expensively.** A preregistered instrument costed 1,700 calls at 15-24
hours on this hardware, with a 2x2 designed to separate shared weights from
priming. Its own stage 0 — ten items, each a real answer beside an EMPTY
rewrite, where any quote at all is fabricated by construction — killed it in
ten calls: the judge quoted text that did not exist 4 times in 10, and a
different-family judge 2.4x its size did the same thing 2 times in 10 by the
same mechanism, quoting the real answer as though it came from the empty
rewrite. So the expensive arm's leading hypothesis was refuted by the cheap
gate that was only supposed to decide whether to run it. Design the floor case
first and make it decidable without a model; if the floor fails, the ceiling
does not need measuring. Learned in `docs/judge_runs/2026-09-04-e-set-stage0.md`.

**A pid is not an identity, and a device that decides on one is deciding on a
number somebody else may be using.** The gate lock read "is the holder still
alive?" as "does a process exist with that number", and in `ceede9d` that
returned True for `explorer.exe` on pid 8932. A lock left behind by a run whose
number was later handed to a long-lived program would have read as HELD for as
long as that program stayed up, wedging every gate on this machine for the full
timeout - the failure the lock's own docstring calls worse than the collision it
prevents, arriving through the lock. **How it fails:** silently and in the
comfortable direction, because "still held" looks like the safe answer. **The
instrument that catches it:** record what makes the process THAT process - on
Windows its creation instant, from `GetProcessTimes` - and compare it, so a
reused number is a different process rather than the same one. **And the
direction of the doubt is half the design:** an unreadable or missing start time
is no evidence, not a mismatch, and falls back to the number alone. Treating
"cannot tell" as "gone" would start a second suite beside a live one, which is
the thing being prevented. The same rule reaches further than locks: any check
that decides whether something is still running - a portfile, a pidfile, a
supervisor - is holding a number and calling it a thing.

**A filter tightened against one wrong answer can be loosened into another, and
the second one is quieter.** The neighbour check in `scripts/gate.py` first
reported seven concurrent suites where two were real, catching the shells that
carried the search pattern by carrying the query (`d15b756`). The tightening
read the executable as the text before the first FLAG - correct for `python -m
unittest discover`, and wrong for `python scripts/gate.py`, which has no flag,
so the whole command line became the "program" and ended in `gate.py`. It then
reported ZERO neighbours while four gates ran on this machine. **How it fails:**
the over-count announces itself and the under-count does not - seven suites
where two are real is obviously wrong, nothing is obviously right. **The
instrument that catches it:** measure the tightened filter against the case it
was NOT tightened for, not only the case it was. Both numbers here were wrong
and only one of them looked it.

**A negative test survives a corrupted fixture, so a fixture must be checked
against something other than its own assertion.** Two process-list fixtures in
`d15b756` had Windows paths typed with real backslashes, so `bash.exe` began
with a BACKSPACE and a drive path carried a VERTICAL TAB. They passed - they
assert an EMPTY result, and corrupted input matches nothing exactly as well as
real input does. The fixtures had already been "fixed" once, which is how far a
note gets you: five of these landed in one night against a standing rule saying
not to write them. **How it fails:** as a pass, on a test whose subject no
longer exists. **The instrument that catches it:**
`tests/test_no_literal_backslash_eats_a_fixture.py` reads every string literal
in `app/`, `tests/` and `scripts/` and refuses the five control characters
nobody types on purpose - bell, backspace, vertical tab, form feed, escape.
Carriage return is deliberately absent: measured over 354 files, six literals
carried one of these and four were real newline handling. A rule kept in memory
is not where the hand reads it.

**A suite that reads its own repository cannot be trusted through a commit.**
The gate on the merged tree reported one failure - `identity.git_head()` said
`1cec60f` while `git rev-parse HEAD` said `1d29f22` - and the test was right
both times. I had committed while the gate was running, so HEAD moved
underneath a suite whose subject is the repository it is running in. **How it
fails:** as a product defect. Nothing in that failure says "the operator moved
the tree"; it reads as a provenance bug in the engine, and the natural next
move is to go looking in `app/identity.py` for a caching error that is not
there. **The instrument that catches it:** re-run the named test with a still
tree before believing it - 26 of 26 passed immediately - and do not commit
between the start of a gate and its verdict. The rule is narrower than "do not
touch the tree": edits to files already imported are invisible to a running
suite, and this repository has tests that read `docs/`, `AGENTS.md` and git
itself, so those are the ones a mid-run change can turn red or, worse, green.

**A lock that prevents a collision buys the prevention with a queue, and the
queue has to be measured rather than assumed.** `1828b7f` made the documented
gate take the machine lock, which is the right call - the count check only
DETECTS a collision, and a detector is a worse thing to own than a preventer.
The first time this lane met it, the gate waited **about 18 minutes** behind a
holder that ran about 28, against a 1,800-second timeout. It ended in a real
run rather than an expiry, so the design worked. **How it fails:** silently
becoming the dominant cost. Three to five suites were live on this machine
tonight; serialising them turns a 13-minute gate into an hour, and a lane that
waits 30 minutes and then exits 2 has spent half an hour to learn nothing.
**The instrument that catches it:** the wait is announced by name and by pid,
so it is visible while it happens - but nothing records how long it lasted.
Until it does, the number in this law is one observation, not a rate.

**A suite that reports OK must also report how many it ran against how many
exist.** Two full suites ran in this checkout at once — two lanes gate in this
repository — and the second printed `Ran 3315 tests ... OK (expected
failures=4)` when discovery finds 3822. Five hundred and seven tests never ran:
no failure, no error, no skip line, a green tick over 87% of the suite and one
command from being pushed on. Remembering not to overlap runs is not a fix,
because the next collision is a different lane on a different night. `scripts/
gate.py` discovers once, counts that suite, runs that same suite and asserts the
two numbers match — a mismatch is red with both numbers and names the likely
causes, so the next reader looks for a second suite rather than a broken test. A
count mismatch outranks a failure, because if tests went missing the failures
that did run are not the whole story. Learned in `8d7776e`'s successor; the run
that caught it is in `docs/judge_runs/2026-09-04-e-set-stage0.md`.

**Read a key row by row before you measure against it.** Two judge numbers were
withdrawn in two days and both had the same cause: the key was checked for
whether it RAN and never for whether each row said what its label claimed. The
first was circular — precision measured against pairs the judge itself had kept.
The second was mislabelled — a `constraint` edit that removed "a qualifying
clause" and called every result a defect, when four of its six pairs were lossy
but TRUE (deleting "If you give me your order number I can check the tracking"
removes an OFFER, so the rewrite promises less, not more) and two were
ungrammatical splices. The judge dropped exactly one of the six and it was one
of the fragments: a correct judge, scored against a wrong key, published as
"blind to deletions". The generators had tests, the tests passed, and the tests
asserted the edit APPLIED rather than that the label was true. A truth path may
only emit a label it can guarantee, so `plant_the_defects.py` now carries only
substitutions — each leaves a statement standing and makes that statement false
— and deletion moved to `over_promise_deletions.py`, where twelve spans are
written out by hand with the promise each one widens, stamped ASSERTED, small
enough that a reader can reject a row and take it out of the denominator. Nine
rows a person has read beat sixty a rule produced. Learned in
`docs/judge_runs/2026-09-05-name-the-absence-cancelled.md`.

**Two label sets that disagree are a rubric that did not decide.** The same
edit — `Only secondhand CD sets` with `Only` deleted, character zero — was KEEP
in one generator and DROP in another, and seven of thirteen rows in one set
deleted a span the other treats as a defect. Neither generator was wrong: the
rubric said "KEEP if worse-but-faithful, DROP if it states something the real
answer does not support", and a rewrite that stops asserting a limit ASSERTS
nothing false while plainly promising more. Two honest readers split on the
silence. Before running a set, check it against every other set it will be
reported beside: a decision rule that asks for a DROP and a KEEP on the same
operation cannot be satisfied by any change, and finding that out costs nothing
compared to finding it out from the numbers. And label sets are not portable —
a full stop removed is DROP under the degradation contract (merely different,
not more permissive) and KEEP under the faithfulness one (nothing false added).
Running a set against the wrong rubric scores correct answers as misses.
Learned in `docs/judge_runs/2026-09-05-does-the-rubric-decide-deletions-result.md`.

**An arm comparison needs a "B must beat A" condition.** A preregistered rule
asked whether the new arm cleared three thresholds and never asked whether it
improved on the old one. The shipped rubric turned out to be already perfect —
25 of 25 — so the rule passed trivially and the script printed PROPOSE THE
CLAUSE for a change that moved nothing, on a scoring path that would have
altered every user's historical numbers. A threshold on the treatment arm alone
is not a comparison. Learned in
`docs/judge_runs/2026-09-05-the-product-scorer-and-dropped-conditions-result.md`.

**`ran == discovered` cannot see a module that did not import.** Two test
modules read a gitignored artifact at import time. Gated on a clone without it,
`ran 3923 of 3923 discovered` — the count matched, while 35 real tests had been
replaced by two `_FailedTest` placeholders that are discovered and run like
anything else. The run was red, so nothing shipped on it, but the assertion the
gate exists for was structurally blind: the loss showed only in errors printed
four thousand lines above where a reader looks. The gate now names unimported
modules at the end and exits 2 rather than 1, because a module that did not
import means the run does not say what the tree does. A test module that reads
an artifact `.gitignore` excludes must skip with the reason, never read at
import. Learned in `d6fe7e6`.

**Prove the mutation landed before believing a test caught it.** Red by
mutation is only evidence if the mutation happened. Reverting a fix to check
that its test goes red, the edit silently did nothing - `\b` written through a
shell heredoc into a non-raw Python string became a literal backspace byte, so
the "old behaviour" was never restored and the suite stayed green. One step from
concluding the test did not catch the bug and weakening a test that was fine.
The same escape ate a `
` twice the same night and produced two SyntaxErrors,
so throwaway sources now live in triple quotes and every mutation asserts the
mutated text is actually in the file before the suite is run. Learned in
`a4663e9`'s successor.

**A judge whose stated reason can contradict the text it judged has no reason,
only a verdict.** Asked to grade 72 rewrites that are not degradations at all,
the pipeline's judge kept 19, and every one of the 19 named a clause the rewrite
still contained word for word - "the rewrite drops the 'over 25.00' condition"
about a rewrite whose only difference from its source is a removed full stop.
The day before, the same instrument invented a QUOTATION from a rewrite that
contained nothing. The prose fabricates in both directions, so it is evidence of
nothing: not shown to a user as the reason, not read by the harness as a signal,
not quoted in a record as an explanation. The verdict is a bit; the reason is
the deterministic diff of what changed, computed in code and printed beside it.
Where a record needs a sentence, the sentence is generated from the diff.

The one place this repository read prose as a signal was
`FEWEST_REASONING_CHARS`, which refuses a row whose account is under forty
characters on the theory that "a verdict with no account is a verdict nobody can
check". On the 72 rows, 0 fell under the floor and 19 were fabrications: the
floor measures verbosity, and caught none of them.

And the corollary that made it cheap: whether a change of the named KIND
happened is a question about two strings, so clause (1) of the contract is
decided before the judge is asked. 106 non-degradations were refused by rule
with zero calls, every one of 39 planted defects and 16 over-promise deletions
was still admitted, and recall on admitted rows held at 35 of 39. Learned in
`4c915ac` and measured in
`docs/judge_runs/2026-09-05-clause-one-before-the-judge-result.md`.

**Build both halves of a defence and put both on the path people use.**
`one_gate_at_a_time.py` PREVENTS two suites sharing a machine; `gate.py`'s count
check DETECTS the loss afterwards. Both were written for the same 2026-09-04
collision that ran 3,315 of 3,822 tests and reported OK. But the wrapper's
docstring shows it in front of `python -m unittest discover`, while the gate
this repository documents - and every lane actually runs - is `python
scripts/gate.py`, which took no lock at all. Dozens of gate runs on 2026-09-05
went with the detector and without the mutual exclusion, and the count would
have caught the loss having not prevented it. The documented gate now acquires
the lock itself and exits 2 when another lane holds it, because a run that never
started says nothing about the tree - a different fact from a test being red.
`--no-lock` exists, because a gate that cannot run without its lock is a gate
nobody can run, but it has to be asked for. Learned in `0f93c4b`'s successor,
after the Practical lane's item 19 fixed the same file's orphan case.

**The day's one red push came from a shell operator, not from the gate.** On
2026-09-05 a commit reached main on a failing gate, from this step:

    grep -E "GATE IS|GATE EXIT" gate70.txt && git push origin main

The grep SUCCEEDED - it found the lines it was searching for - so the push ran.
It was chained to grep's exit status rather than to the gate's verdict, and the
verdict was exit 1. Every earlier push that day happened to be green, so the
mistake had never shown itself. The counting gate worked, the machine lock
worked, and the hand-typed step between them did not.

A step retyped by hand each time cannot be made reliable by care, so it is a
program: `scripts/push_if_green.py` runs the gate, reads its EXIT CODE, and
refuses on anything but zero - including exit 2, which is the gate saying the
run does not describe the tree. It never reads the gate's output, because
"GATE IS RED" matches a search for "GATE IS" exactly as well as a green line
does, and one of its tests feeds it a runner that prints GREEN while returning
1. It never passes `--no-lock` for you; type it yourself and it is printed in
the record.

And a test in that file nearly did the same damage from the other side: its
first version called the script's `main()`, which builds its own subprocess
runner, so it would have run the real thirteen-minute gate and then really
pushed to origin. A test that can push is not a test. It exercises the decision
function with a fake runner instead. Learned in `9098eb4`'s successor.

**A verdict is only about the tree it was computed on, so the lock's scope is
gate-plus-push.** The first version of `push_if_green.py` gated and then pushed,
and its second real use was refused as a non-fast-forward: main had moved during
the thirteen-minute gate. Rebasing and pushing anyway would push a tree the gate
never saw; an unbounded retry spends the machine. So the machine lock that
already serialises gating is held from the START of the gate through the push,
and because every lane's gate takes the same lock, no lane can land between a
green verdict and the push that follows it - one that arrives waits.

That is also why the step now passes `--no-lock` to the gate, having said in
bold that it never would: the gate would otherwise wait on a lock its own parent
holds. The words changed because the design did, and the guarantee is stronger.

If origin moves anyway - a push from a worktree that never gated, which the
record says has happened - it rebases and re-gates ONCE and then refuses for a
person, because a second automatic attempt is a loop that does not converge.
And only a REJECTED REF is retried: `git push` exits 1 when the remote refuses,
while 128 is no credentials or no network, and answering one of those by
rewriting a branch is worse than reporting it. That distinction came from a test
written before the retry existed, which fed 128 and expected it back.

Two of this step's own tests reached for real resources before they were caught:
one called `main()` and would have run the real gate and really pushed from
inside the suite, and one passed `lock=None` and blocked on the actual machine
lock. A test that can push, or that can hold the lock a real gate is waiting on,
is not a test. Learned in `3a50ec0`'s successor.

**Do not move HEAD under a running gate; the lock serialises suites, not git.**
Twice in one hour a commit landed while the suite was running, and
`test_the_real_repository_answers_with_a_real_sha` went red both times - it
reads `identity.git_head()` and `git rev-parse HEAD` and compares them, and HEAD
moved between the two reads. The test was right; the behaviour was mine, and the
second time came after I had already diagnosed the first and written that I
would rather build a check than remember not to do it.

So `gate.py` records HEAD at the start, reads it again at the end, and exits 2
when it moved - the same family as a count mismatch and an unimported module:
the run does not describe a tree, which is a different fact from a test being
red. Either sha being unreadable is "cannot decide", and cannot decide is not
moved, so a checkout without git still gates.

The lock could not have caught this. It stops a second SUITE, and what moved
here was the branch under the first one. Learned in `76602af`'s successor, and
the two tests that first covered it had to be rewritten because they called
`the_gate` itself - thirty-eight seconds, a `fileno` error from a redirected
stream, and a gate discovering the suite that was discovering it.

**A start time compared as a number is not compared at all.**

MEASURED 2026-09-05, on myself, mid-run. The GPU lane held the card and I
checked whether its holder was still the process that took it:

    born_when(4264) == 134331322491779160     ->  False

The lane was alive, correct, and 24 rows into its second pass. `born_when`
returns that value AS A STRING, and a string never equals an int in Python
however identical the digits read. One unquoted literal, and a live holder reads
as a stranger.

The consequence runs the wrong way from the failure the check exists for.
`one_gate_at_a_time` compares start times to catch pid recycling: a dead
holder's number handed to some long-lived program, whose lock would otherwise
read as HELD forever. A wrong "recycled" is the mirror image - it CLEARS a live
lock and starts a second run beside the first, which is the collision the whole
module exists to prevent. The cheap slip produces the expensive outcome.

It is also the direction this repository's own law already forbade, arriving in
a form the law did not cover. `_alive` was written so that a missing or
unreadable start time falls back to the pid alone, because **cannot tell is not
evidence of absence**. An int IS "cannot tell" from the comparison's point of
view - a format it does not understand - and it was answering "gone" instead of
falling back. The law was right; only the shapes it recognised were too narrow.

Both sides are now coerced with `str().strip()` before comparing, and
`tests/test_a_pid_is_not_an_identity.py` pins three things: `born_when` returns
a string, the write-then-read-back round trip holds, and a start time handed
over as a number does not read as a mismatch. The third was red before the fix
and green after, on the same test.

Third time this session an identity check misread a live lane, each in a
different disguise: ISO against FILETIME compared as strings said DEAD; a pid
alive but recycled said HELD; str against int said RECYCLED. The pattern is not
carelessness about locks, it is that **every one of these compares two values
that arrived from different places, and no comparison of that kind is safe until
both sides are normalised at the boundary they enter through.** That is the
check to reach for, rather than remembering not to make the slip.

**One machine can have two true names, so compare by membership.**

MEASURED 2026-09-06, building the host field, by running it rather than reading
it:

    COMPUTERNAME          29733
    platform.node()       DESKTOP-AKGMH12
    socket.gethostname()  DESKTOP-AKGMH12

Both are stable, both are this box, and they are not equal. The NetBIOS name and
the DNS hostname simply differ here, and PowerShell agrees with the environment
while Python's two calls agree with each other.

The first draft compared one chosen name with `==`. That would have made a lane
writing `host=DESKTOP-AKGMH12` and a lane reading `host=29733` conclude they
were on different machines and refuse each other's locks **on one card** - the
collision the host field was written to prevent, produced by the host field.
The fix is `the_names_of_this_host()`: every name the machine answers to, and
membership rather than equality. `this_host()` still picks one name to WRITE,
because a line has to say something, and it picks the one a person can read -
but nothing compares with it.

That makes it the fourth identity check in two days to misread something on
the strength of one representation. ISO against FILETIME said a live lane was
dead; a recycled pid said a dead lane was held; a str against an int said a live
holder was recycled; and now one of a machine's two names says a machine is not
itself. Every one is the same shape: **two values that arrived from different
places, compared before either was normalised.** The check is not to remember
the trap, it is to ask, at every boundary, what else this value could truthfully
be called - and if the answer is "more than one thing", to compare against the
set and not the pick.

**A lock that cannot stop the ref moving protects the gate, not the push.**

MEASURED 2026-09-06. `push_if_green` holds the machine lock across the gate and
the push, on the law above - a verdict is only about the tree it was computed
on, so nothing may move the tree between them. It went green at 4,392 of 4,392,
attempted the push, and was refused non-fast-forward: **origin had moved while
the lock was held.**

The lock did its job and the job was not enough. It serialises SUITES on this
machine. It cannot serialise pushes to a remote, because the thing it guards is
a file in this machine's temp directory and the thing that moved is a ref on a
server. Those are different windows and only one of them is locked:

* between gate start and gate end, the local tree is protected - that is what
  the lock is for and it works
* between gate end and push, the REMOTE may have moved for reasons no local lock
  can see - another checkout, another machine, a lane that no longer takes this
  lock at all

The last of those was live at the time: a peer lane had moved to a per-checkout
lock, so it waits for this lane's lock but never writes it, and this lane cannot
see the peer gating.

A CORRECTION TO HOW THIS WAS FIRST DIAGNOSED, kept because the route matters.
When a peer's publishing gate reported the pushed hash as absent from origin, I
explained it as a stale remote-tracking ref - a cached name for someone else's
branch, re-resolved only when asked. That explanation was CORRECT ABOUT THE GATE,
which never fetched at all and resolved every hash against `origin/main`. It was
WRONG ABOUT THE PEER'S HAND CHECKS, which did fetch each time and were reporting
the remote accurately: the hash genuinely was not on origin when they looked, and
the push landed between their last check and my reply.

So a real defect was found through a wrong account of who was affected. Worth
recording in that order, because the tempting summary - "I was right and they
were reading a cache" - is false, and the true one is narrower: the mechanism was
real, the observer I attributed it to was not the one suffering from it. During a transition where one lane has upgraded and the
other has not, **the unupgraded lane is the one that cannot see anything**, and
the cost lands on it.

The right conclusion is not a bigger lock: a push can always be refused by a
remote that moved, and the answer already exists: `push_if_green` rebases and
re-gates once, then pushes. That is the mechanism that makes a moving remote
safe, and it ran here and worked - two gates, one push, both green.

What has to change is what a reader is told. This page said the lock's scope is
gate-plus-push, which reads as though the lock makes the push safe. It does not.
The rebase-and-re-gate is what makes the push safe; the lock only makes the
gate mean something. A reader who trusted the old sentence would think a green gate
guaranteed a clean push, and would be surprised by a refusal that is in fact the
system working.

**When a shared resource mis-resolves, it mis-resolves toward one lane, and that
lane cannot see the harm.**

MEASURED 2026-09-06 by the practical lane, on this machine. Two checkouts share
one virtualenv carrying an editable install that maps `app` to ONE of them - this
one. A process in either tree that does not put its own repository first on
`sys.path` imports this checkout's `app`. And because `ENGINE_FILE` is
`data_root()/engine.json` and `data_root()` prefers the checkout of whichever
`app` was imported, the mis-resolution compounds:

Measured from the OTHER lane's checkout, twice:

    with its own repo first (what gate.py arranges, line 61)
      app package   <the other lane's checkout>
      engine file   <the other lane's checkout>/engine.json

    without it (what any script written without that line gets)
      app package   <THIS checkout>            <- not its own
      engine file   <THIS checkout>/engine.json
      data root     <THIS checkout>

So a stage-lane process that forgets one line authenticates against this lane's
engine and writes to this lane's data root.

THE ASYMMETRY IS THE FINDING, NOT THE MAPPING. Everything mis-resolves toward
one tree. That tree therefore sees correct behaviour always - its own code, its
own engine, its own data - while the other tree silently operates on someone
else's. **The lane positioned to notice is the lane that cannot be hurt, and the
lane being hurt sees nothing wrong with its own results.** A defect with a
direction is not found by whoever is downstream of it.

Two things follow. A serialising lock does not help: two lanes taking turns still
import the same package, so this is a different axis from everything a suite lock
was ever about. And the check that finds it has to be run FROM the exposed side -
this lane could sweep its own tree forever and find nothing, because from here
there is nothing to find.

THE SAME SHAPE ON A SECOND AXIS, found the same day. The other lane's tree is
not an independent checkout - it is a **git worktree of this one**:

    $ git worktree list
    <this checkout>                               [main]
    <this checkout>/.claude/worktrees/…           (detached)
    <the other lane's checkout>                   [a branch of its own]

Three working trees, one object database, one ref store, all of it inside this
directory. So every ref either lane writes lands in this `.git`; the other lane's
gate reads its HEAD from a file in this directory; a `gc` in either touches
objects the other depends on. **Direction toward this tree again, blindness on
this side again.** And the practical lane's addition, which is the operative
half: the exposed lane is not merely the one that cannot see the harm, it is the
one that must run the check. This lane's sweep of its own tree could only ever
come back clean. Their trace is what settled it - zero writes, three reads, all
under `.git`. **A defect with a direction has to be measured from the downstream
end, and downstream is whoever is not protected.** It is not a fault - worktrees are meant to work this way - but
it means "two separate checkouts" was never the thing being measured, and an
experiment that used a genuine clone could not have found it.

What this lane can check, and did: whether the protected tree carries foreign
writes. `engine.json` here is four days stale, from 2026-09-02, and every
`runs/` output has a modification time matching a run of this lane's own. That is
consistent with nothing having been written and is **not proof that nothing
was** - mtimes and one stale file cannot show what a process did and cleaned up,
and the instrument that would show it runs on the other side.

**A count without its denominator is a ceiling, and should be named one.**

REACHED TWICE ON 2026-09-06, from unrelated incidents in two lanes, which is why
it is here rather than on two incident pages.

This lane: `kept: 164` was read as 164 training examples for two days and was 127
distinct triples, because the count was over rows and rows repeat. The practical
lane: 194 minutes of queueing could not be normalised onto twenty gate runs,
because the old instrument never recorded how many runs the 194 minutes were
drawn from.

The two failures are the same failure. A number counted over something is
meaningless until the something is named, and when the denominator is missing
the number is not merely imprecise - **it is an upper bound wearing the clothes
of a measurement.** 164 is the most examples the corpus could hold; 194 is the
most queueing twenty runs could have suffered.

The practical lane's handling is the model: it called its baseline a ceiling
rather than a figure, said which direction the error runs, and said it runs in
its own favour. That is three sentences and it makes an unusable number usable,
because a reader knows which way to lean. This lane's handling was worse - the
number was simply wrong for two days and every decision about whether the corpus
was large enough was taken against it.

So: name the denominator, or name the number a ceiling and say which way it errs.
The second is honest when the first is unavailable. Neither is optional.

**A gate that skipped a check is not a gate that ran it, and the skip says so
where nobody reads.**

MEASURED ON MYSELF, 2026-09-06. A commit of mine turned main red on a rule my own
gate had passed twenty minutes earlier. The rule is a denylisted path name in
`scripts/release/identifiers.json`, and that file is **gitignored** - so it lives
in a working tree, and separate working trees do not have it. The other lane's
checkout has one. **This checkout does not.**

So the identifier half of the scan SKIPPED here and RAN there, and the same
commit was green in one tree and red in the other with no difference in the code.

The test was not silent about it. It skipped with this reason:

> no identifier list on this machine, so the personal-identifier rules did not
> run; 4 shape rules did, and they are asserted separately. **This is NOT a clean
> bill.**

and printed a warning four times. I read `OK (skipped=1)` and moved on. The check
told me exactly what it had not done, in the words I would have wanted, and the
summary line said OK.

Two things follow, and the second is the uncomfortable one. **A skip is a partial
result wearing a pass**, so a gate's own summary is not enough when any check can
disable itself for a reason outside the repository. And this repository already
has the law - *nothing failed is not nothing was checked, and the two need
different words* - which I wrote about somebody else's suite and then walked past
in my own, because the words were in a skip reason rather than in the total.

The narrower lesson for anyone editing shipped prose: sanitising a home directory
is not sanitising a path. The denylist here has three path rules and the pasted
output tripped the one that is not a home directory - the checkout's NAME - after
I had carefully replaced the part before it with `...\`.

**Call the function. A copy is a fork that agrees for now.**

MEASURED 2026-09-07. Asked what the other checkout's suite lock is called, I
reimplemented the derivation rather than importing it - `sha256` of the resolved
path, eight hex characters - and got one lock name. The real function lowercases the
path first, so the true name is a different one. My copy disagreed with the
original the first time it was used, and the values are not quoted here because
an eight-character hex token on this page reads as an abbreviated commit and a
reader would try to resolve it - which is a check this page already enforces and
which caught this paragraph.

The copy was not wrong when written. It was wrong because the original had a
detail the copy did not, and nothing anywhere compares them - two functions that
agree today and drift the moment either is touched. That is the whole hazard:
a reimplementation is a fork with no merge, and no test that the two still
match.

The repair is not "be more careful reading the original", it is not to have two.
Where the value must be computed outside the module, import the module and call
it; where that is impossible, one of the two has to assert against the other.

Three lanes hit this in one night, and the useful instance is the one that
avoided it: another lane extracted a reachability check into a named function
and had its pre-read CALL that function rather than copy its logic, precisely so
the two could not diverge.

*A correction to my own first telling of this.* I claimed a wrong `engine.json`
finding earlier the same night came from the same cause. **It did not.** That one
was reading a test's stderr as a production condition - an instrument accurate
about what it measured and silent about what it did not. Two different errors,
and folding them together would have made this law look better attested than it
is, which is the denominator error arriving in the evidence for a law rather than
in a measurement.

**A suite that only passes on a prepared machine is testing the preparation.**

MEASURED 2026-09-07, twice in one night in two repositories. Here: a check I
added exited 2 whenever a gitignored denylist was absent, so **no fresh clone
could ever be green** - the file holds personal identifiers and a visitor cannot
legitimately have one. Elsewhere the same night: a docs suite that could not pass
a fresh checkout of its own repository, because a parser wanted one line-ending
convention on a platform that checks out the other.

Different causes, one class. Both suites passed everywhere they were run, because
everywhere they were run had already been prepared - and in this case the two
checkouts that could have noticed had both acquired the missing file within the
hour.

The test is easy to state and was not being asked: **would this pass on a clone?**
Not "does it pass here", and not "does it pass on the other machine", both of
which had been prepared by the same hands. The repair for this instance was to
separate the claims - a green gate is a statement about code, and a push is an
act of publication - and to put the refusal on the release path where a missing
release rule genuinely does block, leaving the gate able to tell a stranger that
the tests pass.

**A law's instance list is a count, and nobody audits it.**

2026-09-07. Every count on this page has been fought over: rows against distinct
rows, tests ran against tests discovered, calls answered against calls requested.
Then a law was written on this page citing three instances, and one of them was
not an instance.

The law was *call the function; a copy is a fork that agrees for now*. Its
evidence was given as three lanes hitting the same rule in one night. Two held. The
third - an earlier wrong finding of mine about a shared engine file - had a
different cause entirely: reading a test's stderr as a production condition, an
instrument accurate about what it measured and silent about what it did not.
The two errors resemble each other in the retelling and not in the mechanism,
and folding them together made the law better attested than the truth.

What actually stands is one instance and one avoidance: a key derivation
reimplemented and immediately wrong, and another lane extracting a check into a
named function so its second caller could not diverge. An instance plus an
avoidance is real evidence. Three instances was a number nobody had audited,
because *the evidence for a law is not the kind of thing anyone counts*.

So the discipline applies to its own record. **When a law here cites N instances,
N is a measurement**, and it decays the same way any count decays: by attracting
things that look like it. Before adding an instance, the question is not "is this
the same lesson" but **"is this the same mechanism"** - the first is a matter of
how it reads, the second of what happened.


**A guard inside the thing it audits must decide from runtime facts on BOTH
sides.** Built 2026-09-07 as `app/import_boundary.py`, and the point is not
obvious until you ask what is running at the moment it fires. If checkout B's
process wrongly imports checkout A's `app`, then the guard that catches it *is
A's guard* - the wrong tree's copy, loaded from the wrong tree's disk. It can
still be right, but only because it compares two things it discovers at
runtime: where this package actually is, and where the calling code actually
is. **A guard that carried any constant about "my tree" in its own source would
be quoting the wrong tree's opinion of itself**, with total confidence, in the
one situation it exists for. The general form: when a check can be reached by
the very confusion it detects, every fact it reasons from must be measured in
the process, not written in the file.

**A check that cannot identify its subject must not convict it**, and this is a
separate law from the one above it, with a separate failure. The same
guard must stay silent wherever it cannot name its subject - an installed
package, a notebook, the REPL, a script outside any checkout. **A check that
cannot identify its subject must not convict it**: a complaint where the answer
was right teaches people to ignore the check, and a check people ignore is worse
than no check, because it also consumes the attention a real one would have got.
Both halves need their own red case. The inert guard and the guard that convicts
everything are different defects, they are caught by different tests, and a suite
that only ever proves one of them has verified half an instrument.
