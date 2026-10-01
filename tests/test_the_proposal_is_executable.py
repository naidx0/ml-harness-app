"""A build is executable by construction, or it is not a plan.

`docs/THE_PROPOSAL_LOOP.md` makes three claims that only mean something if they
are mechanical, and this file is where each one either holds or turns the suite
red.

1. **The proposal is the object the executor consumes.** So every step in every
   build any proposer can produce names a registered tool, satisfies that tool's
   schema, and depends on steps that really produce what it asks for. The
   mutation check is the part that proves this is checking rather than
   describing: take one tool out of the registry and the build must refuse to
   validate, naming the step that named it.
2. **Approval is a contract.** So a build has a fingerprint, a step has a
   narrower one covering what it DOES, and a changed plan reports what changed
   rather than running.
3. **We never invent a number.** So an estimate with no provenance must be
   impossible to construct, not merely absent - `Cost(minutes=40)` and
   `Estimate.measured("wall_clock", 40)` are both tried here, and both have to
   fail.

The fourth thing it checks is honesty about coverage: every outcome the engine
declares is either covered by a proposer or carries a written reason why not,
and the two reasons that read as excuses (`ACTION__COUNT_THE_ROWS` and
`NO_TRAIN__OFF_THE_SHELF_MODEL`) are verified against the registry rather than
believed.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import diagnosis_fixtures

from app import build, diagnosis
from app.build import (
    Build,
    BuildInvalid,
    Cost,
    CostError,
    Environment,
    Estimate,
    ExitCriterion,
    Output,
    Question,
    Reading,
    Ref,
    Risk,
    Step,
    Subject,
)
from app.tools import REGISTRY, evidence, propose
from app.tools.registry import Registry

import support

#: The second ledger's fixtures, shared with the Phase-B journey test. A build
#: for somebody else's agent is only exercisable against files shaped like what
#: the instruments actually accept.
AGENT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"
#: The outputs-and-schema pair `measure_the_format` reads. Twenty rows, of
#: which fourteen satisfy the schema - see
#: `tests/test_the_format_stage_gets_a_build.py` for what the other six are.
FORMAT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "format"
AI_LEDGER_PATH = "docs/ledgers/ai_engineering.yaml"


# ---------------------------------------------------------------------------
# Scaffolding.


def registry_without(name: str) -> Registry:
    """A copy of the live registry with one tool taken out.

    `Registry` has no `remove`, on purpose - nothing in the product may
    unregister a tool at runtime - so the mutation is expressed as a smaller
    registry built from the same declarations.
    """
    smaller = Registry()
    for spec in REGISTRY:
        if spec.name != name:
            smaller.add(spec)
    return smaller


def a_subject(name: str = "somewhere/eval.jsonl") -> Subject:
    """A subject for a test that is about something other than subjects.

    `of_recorded_path` rather than `of_path` because it does not stat, so a test
    about arithmetic does not need a file on disk. Tests that ARE about subjects
    live in `tests/test_a_measurement_carries_its_subject.py` and use the real
    doors.
    """
    return Subject.of_recorded_path(name, how="a subject this test supplies")


def a_cost() -> Cost:
    """The cheapest honest cost: nothing known, everything said."""
    return Cost(
        model_tokens=Estimate.none(build.MODEL_TOKENS, because="it never asks the model"),
        model_requests=Estimate.none(
            build.MODEL_REQUESTS, because="it never asks the model"
        ),
        wall_clock=Estimate.unknown(
            build.WALL_CLOCK, why="never timed", find_out_by="time one run"
        ),
        disk=Estimate.none(build.DISK, because="it writes no file"),
    )


def an_exit(subject: str = "ok") -> ExitCriterion:
    return ExitCriterion(
        stated="the tool reported success",
        source="tool_result",
        subject=subject,
        comparator="is_true",
    )


def a_step(step_id: str, tool: str = "list_context", **overrides) -> Step:
    fields = dict(
        id=step_id,
        tool=tool,
        why="a step used by this test",
        arguments={},
        cost=a_cost(),
        exit_criterion=an_exit(),
    )
    fields.update(overrides)
    return Step(**fields)


def a_build(steps, **overrides) -> Build:
    fields = dict(
        id="a_test_build",
        title="A build used by this test",
        for_outcome="ACTION__MEASURE_BASELINE",
        because="this test needs a build",
        steps=tuple(steps),
        environment=Environment(name="test", working_dir="runs/test"),
        exit_criterion=ExitCriterion(
            stated="the test build finished",
            source="diagnosis",
            subject="fact_origins.eval_size_n",
            comparator="is_measured",
        ),
    )
    fields.update(overrides)
    return Build(**fields)



#: THE THIRD LEDGER'S FIXTURE FILES, on disk rather than written per test. The
#: harness instruments read a checker, a task set, two ablation arms and a tool
#: definitions file, and every one of them has to be a REAL file of the right
#: shape - a temporary file written inline would be four more things to keep in
#: step with the tools that parse them.
def _harness_fixture(name: str) -> str:
    return str(Path(__file__).resolve().parent / "fixtures" / "harness" / name)


def _harness_builds(case) -> list:
    """One real build from every harness proposer, driven through the engine.

    The sheet for each outcome comes from `harness_fixtures.SHEETS`, which is
    itself driven - `test_the_harness_ledger_refuses_before_it_builds` walks
    every one of them and asserts it lands on its own key - so a plan drawn here
    is a plan drawn for the situation the engine actually produces rather than
    for one assembled to reach a proposer.

    `spec` is not passed and cannot be: `Situation.spec` is a PROPERTY over the
    diagnosis, because "an answer carries the knowledge it was computed from" is
    how this file avoided threading a ledger handle through 9,800 lines. So the
    ledger reaches the proposer through `result`, which is where it belongs.
    """
    import harness_fixtures
    from app import diagnosis as _diagnosis
    from app.tools import propose as _propose

    spec = _diagnosis.spec_at("docs/ledgers/harness_design.yaml")
    tasks = _harness_fixture("journey-tasks.jsonl")
    arms = [
        {
            "component": "reranker",
            "with_answers": _harness_fixture("journey-with-reranker.jsonl"),
            "without_answers": _harness_fixture("journey-without-reranker.jsonl"),
        }
    ]
    shared = {
        "checker_path": _harness_fixture("journey-checker.py"),
        "tasks_path": tasks,
        "answers_path": _harness_fixture("journey-solo-answers.jsonl"),
        "tooldefs_path": _harness_fixture("journey-tools.json"),
        "trace_path": str(
            Path(__file__).resolve().parent / "fixtures" / "agent" / "journey-traces.jsonl"
        ),
        "ablation_arms": tuple(arms),
        "input_field": "task",
        "expected_field": "expected",
        "answer_field": "answer",
    }

    out = []
    for outcome in sorted(harness_fixtures.SHEETS):
        if outcome not in _propose.PROPOSERS:
            continue
        facts = harness_fixtures.SHEETS[outcome]
        result = _diagnosis.diagnose(facts, spec)
        case.assertEqual(result.outcome, outcome, "the fixture stopped reaching it")
        out.append(
            _propose.propose(
                _propose.Situation(
                    outcome=result.outcome,
                    result=result,
                    values={name: fact.value for name, fact in facts.items()},
                    origins=dict(result.fact_origins),
                    **shared,
                )
            )
        )
    return out

class ProposalTestCase(unittest.TestCase):
    """Every test here gets its own database, because proposing reads the ledger."""

    def setUp(self):
        self.root = support.sandbox(self)

    def eval_file(self, rows: int = 40, name: str = "eval.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def retrieval_eval_file(self, rows: int = 40, name: str = "questions.jsonl") -> Path:
        """An eval set shaped for recall: a question and the document that answers it."""
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "doc": f"doc_{i % 3}.txt"})
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def corpus(self, name: str = "corpus") -> Path:
        """A folder of documents to index. Not the eval file - the proposer refuses that."""
        folder = self.root / name
        folder.mkdir(exist_ok=True, parents=True)
        for index in range(3):
            (folder / f"doc_{index}.txt").write_text(
                f"document {index}: the refund window is thirty days\n",
                encoding="utf-8",
            )
        return folder

    def retrieval_situation(self, outcome: str, **paths) -> propose.Situation:
        """A situation for one of the two outcomes the retrieval bench answers.

        Built the way `bench_situation` is and for the same reason: the engine
        decides, and what is bypassed is the ledger round trip rather than the
        tree. `retriever_recall_at_k` is `source: inspect` and `retrieval_tried`
        is `source: ask`, so the fixtures in `tests/diagnosis_fixtures.py` are
        the honest way to reach these two nodes without a corpus, an index and a
        real run behind them.
        """
        sheet = dict(
            diagnosis_fixtures.REACHING.get(outcome)
            or diagnosis_fixtures.REACHING["ACTION__MEASURE_RETRIEVER_RECALL"]
        )
        if outcome == "NO_TRAIN__RAG":
            # S3_BUILD_RAG is `not retrieval_tried`, and it sits above the node
            # that asks for the recall figure - there is no recall to measure
            # until a retriever exists.
            sheet["retrieval_tried"] = diagnosis.stated(False)
        for name, value in paths.pop("facts", {}).items():
            sheet[name] = value
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, outcome)
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={
                name: getattr(value, "value", value) for name, value in sheet.items()
            },
            origins=dict(result.fact_origins),
            **paths,
        )

    def situation(self, facts, *, actor="user", thread_id=1, **paths) -> propose.Situation:
        sheet, trail = evidence.assemble_facts(thread_id, dict(facts), actor)
        result = diagnosis.diagnose(sheet)
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={row["fact"]: row["value"] for row in trail},
            origins={row["fact"]: row["origin"] for row in trail},
            hows={row["fact"]: row.get("how") or "" for row in trail},
            **paths,
        )

    def bench_situation(self, histogram, *, outcome: str, **paths) -> propose.Situation:
        """A situation for one of the outcomes the eval and prompt benches unlock.

        THE ENGINE STILL DECIDES. What is bypassed here is the ledger round
        trip, not the tree: `diagnosis.diagnose` runs for real over a fact sheet
        built the way `tests/diagnosis_fixtures.py` builds one, and the outcome
        asserted below is whatever it returned.

        The round trip is bypassed because `failure_histogram` is `source:
        derive` and admits MEASURED alone, so the only honest way to put one in
        the ledger is to run `run_eval` against a model - and a test that needs
        somebody's model running is a test that fails on a fresh checkout.
        `tests/test_the_eval_bench_keeps_its_rows.py` drives that end with a
        scripted model; this file is about whether the resulting BUILD is
        executable, which is a different question and does not need the tokens.
        """
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
        sheet["failure_histogram"] = diagnosis.measured(histogram)
        for name, value in paths.pop("facts", {}).items():
            sheet[name] = value
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, outcome)
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            # Filled the way `propose_build` fills it, so a proposer that reads
            # a fact to decide an argument is exercised here rather than only
            # in the branch where it cannot read one.
            values={
                name: getattr(value, "value", value) for name, value in sheet.items()
            },
            origins=dict(result.fact_origins),
            **paths,
        )

    def training_file(self, rows: int = 200, name: str = "train.jsonl") -> Path:
        """Data to fine-tune ON. Not the eval file - the proposer refuses that.

        JSONL with a `text` field, because that is what `hf-peft-lora` reads and
        the proposer refuses anything else rather than drawing a step that fails
        on the format at minute one.
        """
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"text": f"a training example, number {i}"})
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def preference_file(self, rows: int = 4000, name: str = "pairs.jsonl") -> Path:
        """What preference optimisation trains on, which is NOT `training_file`.

        prompt/chosen/rejected rather than a `text`, because that is
        `hf-peft-dpo`'s contract and the difference is the whole objective:
        imitate this answer, against prefer this answer to that one. Four
        thousand of them because the ledger's own condition for this route is
        `preference_pairs_n >= 1000` and a fixture under the floor would be a
        fixture that never reaches the build.
        """
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "prompt": f"ticket {i}",
                        "chosen": "the reply we want",
                        "rejected": "the reply we do not",
                    }
                )
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def sft_adapter(self, name: str = "sft_adapter") -> Path:
        """The pass a preference run continues from. The ledger requires one.

        `docs/diagnosis_engine.yaml` declares `DPO: {prerequisite: LORA_SFT}`
        and the proposer refuses without it, so a sweep that skipped this would
        be sweeping a refusal. A directory with an `adapter_config.json` in it
        is what the proposer checks for; nothing here loads weights.
        """
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        (directory / "adapter_config.json").write_text("{}", encoding="utf-8")
        return directory

    def tabular_file(self, rows: int = 3000, name: str = "table.csv") -> Path:
        """A table to fit a tree on: two features and a label column.

        CSV rather than JSONL, because `fit_a_tree_model` reads both and a table
        is what a tabular user actually has. Three classes so the fit has
        something to separate and the trivial baseline is not the whole answer.
        """
        path = self.root / name
        path.write_text(
            "\n".join(
                ["size,region,label"]
                + [
                    f"{index},{index % 7},{('yes', 'no', 'maybe')[index % 3]}"
                    for index in range(rows)
                ]
            ),
            encoding="utf-8",
        )
        return path

    def after_answers_file(self, name: str = "after.jsonl") -> Path:
        """The 'after' recording the six workbench builds compare against.

        THE SAME QUESTIONS WITH DIFFERENT ANSWERS, and that is not decoration:
        the pairing key is a digest of input+expected, so a file whose
        questions differed would be a different question set and the
        comparison would refuse it. Copied off the journey fixture with every
        answer set to the expected one - this file is validating a PLAN, and
        what it needs is a real path shaped like what the step will open.
        """
        path = self.root / name
        rows = [
            json.loads(line)
            for line in (AGENT_FIXTURES / "journey-failures.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        for row in rows:
            row["answer"] = row["expected"]
        path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
        )
        return path

    def tabular_situation(self, **paths) -> propose.Situation:
        """A situation for `NO_DEEP__GRADIENT_BOOSTED_TREES`, the same way.

        THE ENGINE STILL DECIDES. `diagnosis_fixtures.SPREAD['tabular_default']`
        is the fact set that lands on `S8_TABULAR_STANDARD` - five million rows,
        a hundred and twenty columns, no free text - and `diagnose` runs over it
        for real. `REACHING` has no entry for this outcome, which is why the
        SPREAD case is used: it is the same shape and it is already asserted
        against its node there.
        """
        sheet = dict(diagnosis_fixtures.SPREAD["tabular_default"]["facts"])
        for name, value in paths.pop("facts", {}).items():
            sheet[name] = value
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "NO_DEEP__GRADIENT_BOOSTED_TREES")
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={
                name: getattr(value, "value", value) for name, value in sheet.items()
            },
            origins=dict(result.fact_origins),
            **paths,
        )

    def agent_situation(self, **paths) -> propose.Situation:
        """A situation for either tool-layer verdict, the second-ledger ones.

        THE ENGINE STILL DECIDES, ON THE SECOND LEDGER. `from_zero=True` is
        the S3_NO_TOOLS_AT_ALL world - choice failures, zero tools declared -
        which mints the sibling outcome and makes the plan lead with the
        definitions reader. The fact sheet is the Phase-B journey's shape:
        instruments' MEASURED readings plus a person's stated half, pointed at
        the same fixtures the journey test drives, because a build for
        somebody else's agent is only exercisable against files shaped like
        what the instruments actually accept.
        """
        from_zero = paths.pop("from_zero", False)
        ai = diagnosis.spec_at(AI_LEDGER_PATH)
        raw = {
            "failing_cases_n": 12,
            "can_rerun_failures": True,
            "failure_rate_measured": True,
            "baseline_success_rate": 1 / 12,
            "target_success_rate": 0.9,
            "failure_reproduces": True,
            "has_traces": True,
            "tokens_per_run": 250.0,
            "run_terminates": True,
            "simple_version_tried": True,
            "workflow_tried": True,
            "tool_count": 0 if from_zero else 3,
            "tool_call_success_rate": None if from_zero else 2 / 3,
            "control_flow_is_dynamic": True,
            "one_context_is_insufficient": False,
            "failure_buckets": (
                {"tool_choice": 12}
                if from_zero
                else {"reasoning": 9, "format": 1, "tool_execution": 1}
            ),
        }
        expected = (
            "BUILD__TOOLS_FOR_AN_EXISTING_LOOP"
            if from_zero
            else "BUILD__AGENT_WITH_TOOLS"
        )
        # ATTRIBUTED THE WAY THE INSTRUMENTS AND THE PERSON ACTUALLY STAMPED
        # THEM: inspect/derive readings are MEASURED, the person's half is
        # STATED. Bare values would all arrive ASSERTED and the walk would
        # refuse at the substantiation door instead of minting.
        _origin = {"inspect": diagnosis.MEASURED, "derive": diagnosis.MEASURED, "ask": diagnosis.STATED}
        sheet = {
            name: diagnosis.Fact(value, _origin[ai.facts[name]["source"]])
            for name, value in raw.items()
        }
        result = diagnosis.diagnose(sheet, ai)
        self.assertEqual(result.outcome, expected)
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=sheet,
            origins=dict(result.fact_origins),
            traces_path=str(AGENT_FIXTURES / "journey-traces.jsonl"),
            failures_path=str(AGENT_FIXTURES / "journey-failures.jsonl"),
            tooldefs_path=str(AGENT_FIXTURES / "journey-tools.json"),
            input_field="input",
            expected_field="expected",
            answer_field="answer",
            **paths,
        )

    def agent_action_situation(self, outcome: str) -> propose.Situation:
        """A situation for one of the second ledger's ACTION__/BLOCKED__ builds.

        THE PATHS ARE THE POINT AND THEY ARE NOT ALL THE SAME. Each of these
        four refuses on the path it needs rather than filling one in - which is
        driven in
        `tests/test_the_ai_ledger_builds_what_it_asks_for.py::TheyRefuseRatherThanGuessTest`
        - so handing every one of them every path would validate a build nobody
        can reach and would hide a proposer that had quietly stopped asking.
        The trace reader gets a trace path and no failures; the failure runner
        gets failures and no traces; the bucketer needs both and says so in
        `the_agent_bucketer_is_registered`.
        """
        wants_traces = outcome in ("BLOCKED__NO_TRACES", "ACTION__CLASSIFY_THE_FAILURES")
        wants_failures = outcome != "BLOCKED__NO_TRACES"
        paths: dict[str, str] = {}
        # THE SIX WORKBENCH OUTCOMES NEED A SECOND RECORDING, and they refuse
        # by name without one. That refusal is the product working - this
        # harness never runs somebody's agent - so the fixture supplies the
        # file rather than the sweep skipping the build.
        if outcome in propose._THE_FIXES_WORTH_PROVING:
            paths["after_answers_path"] = str(self.after_answers_file())
        if wants_traces:
            paths["trace_path"] = str(AGENT_FIXTURES / "journey-traces.jsonl")
        if wants_failures:
            paths["failures_path"] = str(AGENT_FIXTURES / "journey-failures.jsonl")
            paths["input_field"] = "input"
            paths["expected_field"] = "expected"
            paths["answer_field"] = "answer"
        ai = diagnosis.spec_at(AI_LEDGER_PATH)
        return propose.Situation(
            outcome=outcome,
            result=diagnosis.diagnose({}, ai),
            **paths,
        )

    def agent_multi_situation(self, **paths) -> propose.Situation:
        ai = diagnosis.spec_at(AI_LEDGER_PATH)
        raw = {
            "failing_cases_n": 12,
            "can_rerun_failures": True,
            "failure_rate_measured": True,
            "baseline_success_rate": 1 / 12,
            "target_success_rate": 0.9,
            "failure_reproduces": True,
            "has_traces": True,
            "tokens_per_run": 250.0,
            "run_terminates": True,
            "simple_version_tried": True,
            "workflow_tried": True,
            "single_agent_tried": True,
            "tool_count": 3,
            "tool_call_success_rate": 2 / 3,
            "control_flow_is_dynamic": True,
            "one_context_is_insufficient": True,
            "failure_buckets": {"reasoning": 9, "format": 1, "tool_execution": 1},
        }
        _origin = {"inspect": diagnosis.MEASURED, "derive": diagnosis.MEASURED, "ask": diagnosis.STATED}
        sheet = {n: diagnosis.Fact(v, _origin[ai.facts[n]["source"]]) for n, v in raw.items()}
        result = diagnosis.diagnose(sheet, ai)
        self.assertEqual(result.outcome, "BUILD__MULTI_AGENT")
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=sheet,
            origins=dict(result.fact_origins),
            traces_path=str(AGENT_FIXTURES / "journey-traces.jsonl"),
            failures_path=str(AGENT_FIXTURES / "journey-failures.jsonl"),
            tooldefs_path=str(AGENT_FIXTURES / "journey-tools.json"),
            input_field="input",
            expected_field="expected",
            answer_field="answer",
            **paths,
        )

    def training_situation(self, **paths) -> propose.Situation:
        """A situation for `TRAIN__LORA_SFT`, built the way `bench_situation` is.

        THE ENGINE STILL DECIDES: `diagnosis.diagnose` runs for real over
        `tests/diagnosis_fixtures.py`'s minting fact set, and the outcome
        asserted below is whatever it returned. What is bypassed is the ledger
        round trip, exactly as it is for the eval and retrieval benches - and
        one thing more, which is worth being explicit about because this is the
        build that spends a GPU: `hows` is filled with the derivation
        `measure_eval_set` writes, because the proposer refuses unless
        `eval_size_n` is a measured count OF THE FILE the fine-tune would be
        judged on, and a count of some other file does not do.
        """
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
        for name, value in paths.pop("facts", {}).items():
            sheet[name] = value
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "TRAIN__LORA_SFT")
        values = {
            name: getattr(value, "value", value) for name, value in sheet.items()
        }
        evaluation = paths.get("eval_path", "")
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=dict(result.fact_origins),
            hows={"eval_size_n": f"counted {values['eval_size_n']} rows in {evaluation}"},
            **paths,
        )

    def preference_situation(self, **paths) -> propose.Situation:
        """A situation for `TRAIN__DPO`, built the way `training_situation` is.

        Same bypass, same reason, one different fact: `hows` carries the
        derivation `count_preference_pairs` writes, because the preference build
        refuses unless `preference_pairs_n` is a MEASURED count of the file this
        run would train on. A fixture that faked that shape would be a fixture
        that stopped exercising the refusal.
        """
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__DPO"])
        for name, value in paths.pop("facts", {}).items():
            sheet[name] = value
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "TRAIN__DPO")
        values = {
            name: getattr(value, "value", value) for name, value in sheet.items()
        }
        pairs = paths.get("dataset_path", "")
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=dict(result.fact_origins),
            hows={
                "preference_pairs_n": (
                    "preference pairs, meaning rows carrying all of "
                    "['prompt', 'chosen', 'rejected']: counted "
                    f"{values['preference_pairs_n']} rows in {pairs}"
                )
            },
            **paths,
        )

    def count_for_real(self, path: Path, thread_id: int = 1) -> None:
        """Make `eval_size_n` genuinely MEASURED, by counting a real file."""
        support.a_conversation(thread_id)
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(path), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=thread_id,
        )
        self.assertTrue(result.get("exact"), result)


# ---------------------------------------------------------------------------
# THE TEST THE INSTRUCTION ASKED FOR.


class ABuildIsExecutableByConstructionTest(ProposalTestCase):
    """Every step's tool is registered, its inputs fit, the graph is acyclic,
    and every cost carries a provenance - checked against every build every
    proposer in this product can actually produce."""

    def every_build(self):
        """One real build from each proposer, driven through the real engine."""
        evaluation = self.eval_file()
        builds = []

        # BLOCKED__BUILD_EVAL_SET - nothing counted yet.
        situation = self.situation(
            {"goal_text": "route tickets", "modality": "text", "target_score": 0.9},
            thread_id=11,
            eval_path=str(evaluation),
        )
        self.assertEqual(situation.outcome, "BLOCKED__BUILD_EVAL_SET")
        builds.append(propose.propose(situation))

        # ACTION__SUBSTANTIATE_CLAIMED_FACTS - a model claimed a count.
        situation = self.situation(
            {
                "goal_text": "route tickets",
                "modality": "text",
                "task_family": "classification",
                "need_type": ["behaviour"],
                "target_score": 0.9,
                "eval_size_n": 400,
            },
            actor=evidence.MODEL,
            thread_id=12,
            eval_path=str(evaluation),
        )
        self.assertEqual(situation.outcome, "ACTION__SUBSTANTIATE_CLAIMED_FACTS")
        builds.append(propose.propose(situation))

        # The two that need a real measurement behind them.
        self.count_for_real(evaluation, thread_id=13)

        situation = self.situation(
            {
                "goal_text": "route tickets",
                "modality": "text",
                "task_family": "classification",
                "need_type": ["behaviour"],
                "target_score": 0.9,
            },
            thread_id=13,
            eval_path=str(evaluation),
            input_field="q",
            expected_field="a",
        )
        self.assertEqual(situation.outcome, "ACTION__MEASURE_BASELINE")
        builds.append(propose.propose(situation))

        situation = self.situation(
            {
                "goal_text": "route tickets",
                "target_score": 0.9,
                "baseline_measured": True,
                "baseline_score": 0.5,
            },
            thread_id=13,
            dataset_path=str(evaluation),
        )
        self.assertEqual(situation.outcome, "ACTION__NAME_THE_MODALITY")
        builds.append(propose.propose(situation))

        # THE ROW COUNT, WHICH COUNTS RATHER THAN ASKS. Its `NOT_COVERED` entry
        # said "the fix is a tool that measures tabular_rows, not a proposer"
        # until `profile_dataset` grew that stamp on 2026-08-28. The build is
        # here rather than beside the modality one above because the two are
        # opposite shapes on purpose: modality ends in a Question, this ends in
        # a measurement.
        situation = self.situation(
            {
                "goal_text": "route tickets",
                "target_score": 0.9,
                "baseline_measured": True,
                "baseline_score": 0.5,
                "modality": "tabular",
                "task_family": "classification",
                "labeled_examples_n": 400,
                "eval_size_n": 40,
            },
            thread_id=13,
            dataset_path=str(evaluation),
        )
        self.assertEqual(situation.outcome, "ACTION__COUNT_THE_ROWS")
        builds.append(propose.propose(situation))

        # THE METRIC, WHICH ASKS AND SCORES NOTHING. The counterpart to the row
        # count above: `run_eval` would return a number here and it would be
        # answering a different question, so this build's only step is a look.
        # `bench_situation` rather than `situation` for the reason its own
        # docstring gives - `failure_histogram` admits MEASURED alone, and a
        # user-stated one is challenged into ACTION__SUBSTANTIATE_CLAIMED_FACTS.
        builds.append(
            propose.propose(
                self.bench_situation(
                    {"wrong_style": 30},
                    outcome="ACTION__MAKE_THE_METRIC_PROGRAMMATIC",
                    facts={
                        "metric_is_programmatic": diagnosis.measured(False),
                        "prompt_optimizer_tried": diagnosis.stated(False),
                    },
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )

        # THE THREE THE BENCHES UNLOCKED. Each one's reason in `NOT_COVERED`
        # said "the tool does not exist yet" until `app/tools/evals.py` landed.
        builds.append(
            propose.propose(
                self.bench_situation(
                    {},
                    outcome="ACTION__CLASSIFY_FAILURES",
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )
        builds.append(
            propose.propose(
                self.bench_situation(
                    {"wrong_style": 30},
                    outcome="NO_TRAIN__BETTER_PROMPT",
                    facts={"prompt_iterations": 0},
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                    prompt="Answer with the label only, in lower case.",
                )
            )
        )
        builds.append(
            propose.propose(
                self.bench_situation(
                    {"wrong_style": 30},
                    outcome="NO_TRAIN__FEW_SHOT",
                    facts={"prompt_iterations": 3, "fewshot_tried": False},
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )

        # THE TWO THE RETRIEVAL BENCH UNLOCKED, and the guard is the same
        # question `propose.PROPOSERS` asks. `app/tools/retrieval.py` is written
        # in a lane of its own and registers the three tools these steps name;
        # while it is absent both outcomes sit in `NOT_COVERED`, there is no
        # proposer to sweep, and the identity below still holds exactly. It is
        # not a way for the sweep to skip them quietly: the moment the tools are
        # registered, both builds are produced here and every check in this class
        # runs over them.
        if propose.the_retrieval_bench_is_registered():
            corpus = self.corpus()
            questions = self.retrieval_eval_file()
            builds.append(
                propose.propose(
                    self.retrieval_situation(
                        "NO_TRAIN__RAG",
                        corpus_path=str(corpus),
                        eval_path=str(questions),
                        input_field="q",
                        expected_field="doc",
                    )
                )
            )
            builds.append(
                propose.propose(
                    self.retrieval_situation(
                        "ACTION__MEASURE_RETRIEVER_RECALL",
                        corpus_path=str(corpus),
                        eval_path=str(questions),
                        input_field="q",
                        expected_field="doc",
                        query="how long is the refund window",
                    )
                )
            )

        # THE ONE THE CHUNKING SWEEP UNLOCKED, behind the same question. Its
        # outcome became reachable when the retrieval bench gave
        # `retriever_recall_at_k` an instrument, and it stayed uncovered until
        # `compare_chunkings` registered - so the guard is the registry, exactly
        # as it is above, and the moment the tool is there this build is
        # produced here and every check in this class runs over it.
        if propose.the_chunking_sweep_is_registered():
            builds.append(
                propose.propose(
                    self.retrieval_situation(
                        "NO_TRAIN__FIX_RETRIEVAL",
                        corpus_path=str(self.corpus("bottleneck")),
                        eval_path=str(self.retrieval_eval_file(rows=40)),
                        input_field="q",
                        expected_field="doc",
                        # The settings are the person's - the proposer refuses
                        # to choose them, because their number is the family
                        # size every p-value is corrected against.
                        chunk_settings=(400, 900, 2000),
                    )
                )
            )

        # THE ONE THE TRAINING BENCH UNLOCKED, behind the same question and
        # with one extra piece of staging. `TRAIN__LORA_SFT` is the first
        # training outcome with a build behind it, and the build refuses unless
        # the backend the engine hands off to is BUILT on this machine - which
        # inside a test sandbox it is not, because `support.FIXTURE_RECIPES`
        # ships a tree with no pinned environment in it. `pin_a_training_recipe`
        # stages that state and nothing else; every check in this class then
        # runs over the build exactly as it does over the other ten.
        if propose.the_training_bench_is_registered():
            support.pin_a_training_recipe()
            builds.append(
                propose.propose(
                    self.training_situation(
                        dataset_path=str(self.training_file()),
                        eval_path=str(evaluation),
                        # Both are the person's and the proposer refuses without
                        # them: which model to fine-tune carries a licence, and
                        # the example length decides the memory the fit answer
                        # is computed at AND the run is executed at.
                        base_model="Qwen/Qwen3-4B",
                        max_seq_len=512,
                    )
                )
            )

        # THE SECOND TRAINING BACKEND, behind the same question and the same
        # staging - a DIFFERENT recipe, pinned separately, because two recipes
        # sharing one environment are two plans that could drift apart with
        # nowhere to put the difference. The roster counts PROPOSERS entries, so
        # a build nothing draws here is a build nothing in this class checks.
        if propose.the_training_bench_is_registered():
            support.pin_a_training_recipe(propose.THE_DPO_RECIPE)
            builds.append(
                propose.propose(
                    self.preference_situation(
                        dataset_path=str(self.preference_file()),
                        eval_path=str(evaluation),
                        base_model="Qwen/Qwen3-4B",
                        max_seq_len=512,
                        # The ledger's prerequisite, and the proposer is the only
                        # thing in this product that enforces it.
                        adapter_dir=str(self.sft_adapter()),
                    )
                )
            )

        # THE ONE THE TREE FIT UNLOCKED, behind the same question. It is the
        # first build on the classical branch and the first one whose step is
        # only pointed at a table, so the fixtures above are no use to it: it
        # needs a real CSV with a real label column, because the proposer READS
        # that column at proposal time and refuses on what it finds.
        if propose.the_tabular_bench_is_registered():
            builds.append(
                propose.propose(
                    self.tabular_situation(
                        dataset_path=str(self.tabular_file()),
                        # The person's, and the proposer refuses without it:
                        # which column is the right answer is the definition of
                        # correct for their task.
                        expected_field="label",
                    )
                )
            )

        # THE ONE THE AGENT INSTRUMENTS UNLOCKED, behind the same question and
        # on the SECOND ledger. `the_agent_instruments_are_registered` gates
        # it, exactly as the benches above are gated; the situation points at
        # the same fixtures the journey test drives, because a plan whose
        # steps read traces and failure rows must be validated against files
        # shaped like what those steps will actually be handed.
        if propose.the_agent_instruments_are_registered():
            builds.append(propose.propose(self.agent_situation()))
            builds.append(propose.propose(self.agent_situation(from_zero=True)))
            builds.append(propose.propose(self.agent_multi_situation()))

        # THE FOUR WIRED ON 2026-08-27, and they are gated one at a time rather
        # than on the whole instrument set. `_PROPOSERS_THE_AGENT_INSTRUMENTS_
        # BRING` needs all four instruments because a BUILD__ on that ledger
        # reads traces AND definitions AND re-runs AND bounds; these do not, so
        # each is drawn behind the predicate for the tools it actually names.
        #
        # They are called DIRECTLY rather than through `propose.propose`, and
        # that is the one departure in this fixture worth reading: `propose`
        # walks from a fact sheet to an outcome, and these four outcomes are
        # reached from sheets that are INCOMPLETE by construction - an
        # ACTION__ or a BLOCKED__ is what the engine says when a fact is
        # missing. Building a sheet that mints each of them would be four more
        # fact tables in this file whose only job is to be wrong in one
        # specific way. The situation each is handed is the same shape the
        # walk would hand it, which is what these sweeps are actually about.
        if propose.the_failure_runner_is_registered():
            for outcome in sorted(propose._PROPOSERS_THE_FAILURE_RUNNER_BRINGS):
                builds.append(
                    propose.PROPOSERS[outcome](self.agent_action_situation(outcome))
                )
        if propose.the_trace_reader_is_registered():
            builds.append(
                propose.PROPOSERS["BLOCKED__NO_TRACES"](
                    self.agent_action_situation("BLOCKED__NO_TRACES")
                )
            )
        if propose.the_agent_bucketer_is_registered():
            builds.append(
                propose.PROPOSERS["ACTION__CLASSIFY_THE_FAILURES"](
                    self.agent_action_situation("ACTION__CLASSIFY_THE_FAILURES")
                )
            )

        # THE SIX THE WORKBENCH WIRED, drawn the same way and for the same
        # reason: these are `NO_*` outcomes, which the engine reaches from a
        # COMPLETE fact sheet saying the answer is a cheap local fix, and
        # building six such sheets here would be six fact tables whose only
        # job is to land on a particular leaf. What these sweeps are about is
        # the SHAPE of what comes out, and the situation each is handed is the
        # one the walk would hand it.
        if propose.the_paired_proof_is_possible():
            for outcome in sorted(propose._PROPOSERS_THE_PAIRED_PROOF_BRINGS):
                builds.append(
                    propose.PROPOSERS[outcome](self.agent_action_situation(outcome))
                )

        # THE FORMAT METER, on the FIRST ledger, which is why it is drawn here
        # rather than beside the six above. `ACTION__MEASURE_THE_FORMAT` is the
        # ask node of `stage_4_format`, a stage that had zero builds until
        # `app/tools/shapes.py` shipped; it is reached from an INCOMPLETE fact
        # sheet like every other ACTION__, so it is called directly for the
        # reason written out above.
        if propose.the_format_can_be_measured():
            builds.append(
                propose.PROPOSERS["ACTION__MEASURE_THE_FORMAT"](
                    propose.Situation(
                        outcome="ACTION__MEASURE_THE_FORMAT",
                        result=diagnosis.diagnose({}, diagnosis.default_spec()),
                        outputs_path=str(FORMAT_FIXTURES / "outputs.jsonl"),
                        schema_path=str(FORMAT_FIXTURES / "schema.json"),
                    )
                )
            )


        # THE CANDIDATE SCORER'S TWO OUTCOMES. Both take the same proposer and
        # differ only in the question at the end, so both are drawn here - the
        # roster counts PROPOSERS entries, not distinct functions, and a build
        # that is never drawn is a build nothing checks.
        #
        # A real completed eval run has to exist first: this proposer REFUSES
        # without one, because a candidate's score is only worth having as a
        # paired comparison against the same rows.
        support.a_completed_eval_run(13, evaluation)
        for _outcome in ("NO_TRAIN__SWAP_MODEL", "NO_TRAIN__USE_EXISTING_BASE"):
            builds.append(
                propose.PROPOSERS[_outcome](
                    propose.Situation(
                        outcome=_outcome,
                        result=diagnosis.diagnose(
                            dict(diagnosis_fixtures.REACHING["NO_TRAIN__USE_EXISTING_BASE"])
                        ),
                        eval_path=str(evaluation),
                        input_field="q",
                        expected_field="a",
                        base_model="Qwen/Qwen3-4B",
                        thread_id=13,
                    )
                )
            )

        # THE THIRD LEDGER'S TWELVE, drawn from its own driven fixtures. A loop
        # over PROPOSERS rather than a written list, so the next harness outcome
        # arrives in this sweep by existing.
        if propose.the_harness_bench_is_registered():
            builds.extend(_harness_builds(self))

        self.assertEqual(len(builds), len(propose.PROPOSERS))
        return builds

    def test_every_step_names_a_registered_tool(self):
        for plan in self.every_build():
            for step in plan.steps:
                self.assertIn(
                    step.tool,
                    REGISTRY,
                    f"{plan.id}.{step.id} names an unregistered tool",
                )

    def test_every_step_satisfies_its_tools_schema(self):
        for plan in self.every_build():
            for step in plan.steps:
                spec = REGISTRY.get(step.tool)
                properties = spec.schema.get("properties") or {}
                required = set(spec.schema.get("required") or ())
                self.assertLessEqual(
                    set(step.arguments), set(properties), f"{plan.id}.{step.id}"
                )
                self.assertLessEqual(
                    required, set(step.arguments), f"{plan.id}.{step.id}"
                )

    def test_every_argument_would_be_accepted_by_the_registry_itself(self):
        """The strongest version of the schema check: no argument would be dropped.

        `Registry.call` filters unknown arguments and reports a missing required
        one as a failed call. A build whose arguments survive that filter intact
        is a build whose steps will not silently run on defaults.
        """
        for plan in self.every_build():
            for step in plan.steps:
                spec = REGISTRY.get(step.tool)
                allowed = set((spec.schema.get("properties") or {}).keys())
                given = {
                    key: value
                    for key, value in step.arguments.items()
                    if not isinstance(value, Ref)
                }
                self.assertEqual(
                    set(given) - allowed, set(), f"{plan.id}.{step.id} would be filtered"
                )

    def test_the_graph_is_acyclic_and_schedules(self):
        for plan in self.every_build():
            waves = plan.waves()
            scheduled = [step for wave in waves for step in wave]
            self.assertEqual(
                sorted(scheduled), sorted(step.id for step in plan.steps), plan.id
            )
            seen = set()
            for wave in waves:
                for step_id in wave:
                    self.assertLessEqual(set(plan.step(step_id).needs), seen, plan.id)
                seen.update(wave)

    def test_every_cost_carries_a_provenance(self):
        for plan in self.every_build():
            for step in plan.steps:
                for estimate in step.cost.estimates:
                    self.assertIn(
                        estimate.provenance, build.PROVENANCES, f"{plan.id}.{step.id}"
                    )
                    self.assertTrue(estimate.how.strip(), f"{plan.id}.{step.id}")
                    if estimate.provenance == build.UNKNOWN:
                        self.assertIsNone(estimate.value)
                        self.assertTrue(estimate.find_out_by.strip())
                    else:
                        self.assertIsNotNone(estimate.value)

    def test_every_step_and_every_build_says_how_we_will_know_it_worked(self):
        for plan in self.every_build():
            self.assertTrue(plan.exit_criterion.stated.strip(), plan.id)
            for step in plan.steps:
                self.assertTrue(step.exit_criterion.stated.strip(), step.id)

    def test_the_environment_snapshots_the_data_as_it_was(self):
        """A measured size, read at proposal time, so the run is reproducible."""
        for plan in self.every_build():
            for snapshot in plan.environment.data:
                self.assertTrue(Path(snapshot.path).exists())
                self.assertEqual(
                    snapshot.bytes, float(Path(snapshot.path).stat().st_size)
                )
                self.assertIn("stat()", snapshot.how)

    def test_a_build_serialises_to_json_for_the_diagram_and_the_storm(self):
        for plan in self.every_build():
            payload = plan.as_dict()
            json.dumps(payload)  # raises if anything in here is not JSON-safe
            self.assertEqual(
                [node["id"] for node in payload["steps"]],
                [step.id for step in plan.steps],
            )
            for edge in payload["edges"]:
                self.assertIn(edge["from"], {step.id for step in plan.steps})
                self.assertIn(edge["to"], {step.id for step in plan.steps})

    # -- THE MUTATION CHECK ----------------------------------------------

    def test_removing_a_tool_from_the_registry_makes_the_build_refuse(self):
        """Take the tool away and the build must refuse, naming the step.

        This is what separates a validator from a docstring. Every other
        assertion in this class passes just as well if `validate()` returns
        without looking at anything.

        **THE REFUSAL NAMES A STEP THAT USED THE TOOL, NOT NECESSARILY THIS
        ONE**, and the difference only appeared when a build ran one tool
        twice. The prompt bench is `run_eval` called twice with a different
        prompt, so removing `run_eval` from the registry makes both the
        `before` and the `after` step unrunnable and `validate` names the first
        it reaches. Requiring it to name the specific step this loop is holding
        would be asserting that no build may ever use a tool twice, which is a
        claim about builds rather than about the validator. What must not
        weaken is the rest: it still has to raise, still has to name the tool,
        and still has to name a real step that called it.
        """
        for plan in self.every_build():
            for step in plan.steps:
                smaller = registry_without(step.tool)
                with self.assertRaises(BuildInvalid) as raised:
                    plan.validate(registry=smaller)
                message = str(raised.exception)
                callers = [
                    other.id for other in plan.steps if other.tool == step.tool
                ]
                self.assertTrue(
                    any(name in message for name in callers),
                    f"the refusal named no step that runs {step.tool}: {message}",
                )
                self.assertIn(
                    step.tool, message, f"the refusal did not name tool {step.tool}"
                )

    def test_a_build_naming_a_tool_that_never_existed_cannot_be_constructed(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build([a_step("only", tool="summon_a_gpu")])
        self.assertIn("only", str(raised.exception))
        self.assertIn("summon_a_gpu", str(raised.exception))


# ---------------------------------------------------------------------------
# The graph.


class TheGraphIsADagTest(ProposalTestCase):
    def test_a_cycle_is_rejected_at_construction_and_named(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [
                    a_step("first", needs=("second",)),
                    a_step("second", needs=("first",)),
                ]
            )
        message = str(raised.exception)
        self.assertIn("cycle", message)
        self.assertIn("first", message)
        self.assertIn("second", message)

    def test_a_longer_cycle_is_still_rejected(self):
        with self.assertRaises(BuildInvalid):
            a_build(
                [
                    a_step("one", needs=("three",)),
                    a_step("two", needs=("one",)),
                    a_step("three", needs=("two",)),
                ]
            )

    def test_a_step_cannot_depend_on_itself(self):
        with self.assertRaises(BuildInvalid):
            a_step("alone", needs=("alone",))

    def test_a_dependency_on_a_step_that_is_not_here_is_refused(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build([a_step("here", needs=("elsewhere",))])
        self.assertIn("elsewhere", str(raised.exception))

    def test_independent_steps_share_a_wave(self):
        plan = a_build(
            [a_step("left"), a_step("right"), a_step("after", needs=("left", "right"))]
        )
        self.assertEqual(plan.waves(), (("left", "right"), ("after",)))


class OutputsAreWhatTheNextStepNeedsTest(ProposalTestCase):
    """A `Ref` is what makes a dependency checkable rather than asserted."""

    def producer(self) -> Step:
        return a_step(
            "attach",
            tool="attach_context",
            arguments={"path": str(self.root)},
            produces=(Output("path", "string", at="what_it_is.path"),),
        )

    def test_a_reference_to_a_real_output_validates(self):
        plan = a_build(
            [
                self.producer(),
                a_step(
                    "count",
                    tool="measure_eval_set",
                    arguments={"path": Ref("attach", "path")},
                    needs=("attach",),
                ),
            ]
        )
        self.assertEqual(plan.waves(), (("attach",), ("count",)))

    def test_a_reference_to_an_output_that_is_not_produced_is_refused(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [
                    self.producer(),
                    a_step(
                        "count",
                        tool="measure_eval_set",
                        arguments={"path": Ref("attach", "rows")},
                        needs=("attach",),
                    ),
                ]
            )
        self.assertIn("rows", str(raised.exception))

    def test_a_reference_without_the_dependency_declared_is_refused(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [
                    self.producer(),
                    a_step(
                        "count",
                        tool="measure_eval_set",
                        arguments={"path": Ref("attach", "path")},
                    ),
                ]
            )
        self.assertIn("needs", str(raised.exception))

    def test_a_reference_of_the_wrong_type_is_refused(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [
                    a_step(
                        "attach",
                        tool="attach_context",
                        arguments={"path": str(self.root)},
                        produces=(Output("rows", "integer"),),
                    ),
                    a_step(
                        "count",
                        tool="measure_eval_set",
                        arguments={"path": Ref("attach", "rows")},
                        needs=("attach",),
                    ),
                ]
            )
        self.assertIn("string", str(raised.exception))

    def test_an_argument_of_the_wrong_type_is_refused(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [a_step("count", tool="measure_eval_set", arguments={"path": 7})]
            )
        self.assertIn("count", str(raised.exception))

    def test_an_argument_outside_a_declared_enum_is_refused(self):
        with self.assertRaises(BuildInvalid):
            a_build(
                [
                    a_step(
                        "find",
                        tool="find_models",
                        arguments={"method": "telepathy"},
                    )
                ],
                environment=Environment(
                    name="test",
                    working_dir="runs/test",
                    egress=True,
                    egress_reason="find_models reads the hub",
                ),
            )

    def test_bind_resolves_a_reference_and_harvest_extracts_an_output(self):
        """The executor's two calls, checked as a pair."""
        plan = a_build(
            [
                self.producer(),
                a_step(
                    "count",
                    tool="measure_eval_set",
                    arguments={"path": Ref("attach", "path")},
                    needs=("attach",),
                ),
            ]
        )
        harvested = plan.step("attach").harvest(
            {"ok": True, "what_it_is": {"path": "C:/data/eval.jsonl"}}
        )
        self.assertEqual(harvested, {"path": "C:/data/eval.jsonl"})
        bound = plan.step("count").bind({"attach": harvested})
        self.assertEqual(bound, {"path": "C:/data/eval.jsonl"})

    def test_harvesting_an_output_the_tool_did_not_return_raises(self):
        step = self.producer()
        with self.assertRaises(BuildInvalid):
            step.harvest({"ok": True})

    def test_binding_a_reference_nothing_produced_raises_rather_than_running(self):
        plan = a_build(
            [
                self.producer(),
                a_step(
                    "count",
                    tool="measure_eval_set",
                    arguments={"path": Ref("attach", "path")},
                    needs=("attach",),
                ),
            ]
        )
        with self.assertRaises(BuildInvalid):
            plan.step("count").bind({})


# ---------------------------------------------------------------------------
# THE TRAP: a number that will not say where it came from.


class ACostCannotBeConstructedWithoutItsOriginTest(unittest.TestCase):
    """`docs/THE_PROPOSAL_LOOP.md`: we never invent a number, and a proposal is
    where we would. Each of these is a way somebody would do it by accident."""

    def test_a_cost_of_forty_minutes_is_not_a_thing_that_can_be_written(self):
        with self.assertRaises(TypeError):
            Cost(minutes=40)  # noqa

    def test_a_cost_slot_refuses_a_bare_number(self):
        with self.assertRaises(CostError) as raised:
            Cost(model_tokens=40, model_requests=1, wall_clock=2400, disk=0)  # noqa
        self.assertIn("not a number", str(raised.exception))

    def test_an_estimate_cannot_be_constructed_directly(self):
        with self.assertRaises(CostError):
            Estimate(
                dimension=build.WALL_CLOCK,
                unit="seconds",
                provenance=build.MEASURED,
                value=2400.0,
                how="I remember it taking about forty minutes",
            )

    def test_measured_will_not_take_a_number(self):
        with self.assertRaises(CostError):
            Estimate.measured(build.WALL_CLOCK, reading=2400)  # noqa

    def test_a_reading_cannot_be_constructed_directly(self):
        with self.assertRaises(CostError):
            Reading(
                dimension=build.WALL_CLOCK,
                value=2400.0,
                unit="seconds",
                how="from experience",
                at="now",
            )

    def test_a_reading_refuses_a_fact_that_was_only_claimed(self):
        with self.assertRaises(CostError) as raised:
            Reading.of_measured_fact(
                "eval_size_n",
                400,
                diagnosis.ASSERTED,
                "a model said so",
                subject=a_subject(),
            )
        self.assertIn("ASSERTED", str(raised.exception))

    def test_a_reading_accepts_a_fact_the_harness_measured(self):
        reading = Reading.of_measured_fact(
            "eval_size_n",
            400,
            diagnosis.MEASURED,
            "counted 400 rows",
            subject=a_subject(),
        )
        self.assertEqual(reading.value, 400.0)
        self.assertEqual(
            Estimate.measured(build.ROWS, reading=reading).provenance, build.MEASURED
        )

    def test_an_unknown_estimate_carries_no_number(self):
        estimate = Estimate.unknown(
            build.WALL_CLOCK, why="never timed", find_out_by="run it on 1%"
        )
        self.assertIsNone(estimate.value)
        self.assertIn("run it on 1%", estimate.say())

    def test_an_unknown_estimate_must_say_how_to_find_out(self):
        with self.assertRaises(CostError):
            Estimate.unknown(build.WALL_CLOCK, why="never timed", find_out_by="")

    def test_a_zero_needs_a_reason_that_makes_it_zero(self):
        with self.assertRaises(CostError):
            Estimate.none(build.MODEL_TOKENS, because="")

    def test_a_total_containing_an_unknown_is_unknown(self):
        """The most dangerous number a proposal could carry is a partial total."""
        measured = Estimate.measured(
            build.DISK,
            reading=Reading.of_measured_fact(
                "eval_size_n",
                1024,
                diagnosis.MEASURED,
                "stat",
                subject=a_subject(),
                dimension=build.DISK,
            ),
        )
        unknown = Estimate.unknown(
            build.DISK, why="nobody measured it", find_out_by="measure it"
        )
        total = Estimate.summed([measured, unknown], dimension=build.DISK)
        self.assertEqual(total.provenance, build.UNKNOWN)
        self.assertIsNone(total.value)

    def test_an_inference_from_an_unknown_stays_unknown(self):
        unknown = Estimate.unknown(
            build.ROWS, why="not counted", find_out_by="count it"
        )
        for derived in (
            unknown.capped_at(20, because="a cap"),
            unknown.scaled_by(2, because="twice"),
            unknown.counted_as(build.MODEL_REQUESTS, because="one each"),
        ):
            self.assertEqual(derived.provenance, build.UNKNOWN)
            self.assertIsNone(derived.value)

    def test_a_derivation_records_the_rule_it_applied(self):
        rows = Estimate.measured(
            build.ROWS,
            reading=Reading.of_measured_fact(
                "eval_size_n",
                40,
                diagnosis.MEASURED,
                "counted 40 rows",
                subject=a_subject(),
            ),
        )
        requests = rows.capped_at(20, because="the sample cap").counted_as(
            build.MODEL_REQUESTS, because="one request per row"
        )
        self.assertEqual(requests.provenance, build.INFERRED)
        self.assertEqual(requests.value, 20.0)
        self.assertIn("counted 40 rows", requests.how)
        self.assertIn("the sample cap", requests.how)
        self.assertIn("one request per row", requests.how)

    def test_a_reading_of_a_file_that_is_not_there_is_refused(self):
        with self.assertRaises(CostError):
            Reading.of_file_size("no/such/file/anywhere.jsonl")

    def test_a_measurement_in_the_wrong_unit_cannot_measure_a_dimension(self):
        rows = Reading.of_measured_fact(
            "eval_size_n",
            40,
            diagnosis.MEASURED,
            "counted 40 rows",
            subject=a_subject(),
        )
        with self.assertRaises(CostError):
            Estimate.measured(build.WALL_CLOCK, reading=rows)

    def test_a_step_with_no_cost_is_not_a_step(self):
        with self.assertRaises(BuildInvalid):
            Step(
                id="free",
                tool="list_context",
                why="it does not say what it costs",
                exit_criterion=an_exit(),
            )


class TheProposersOwnNumbersTest(ProposalTestCase):
    """The costs the shipped proposers actually produce, not synthetic ones."""

    def test_a_measured_count_becomes_a_derived_request_count(self):
        evaluation = self.eval_file(rows=40)
        self.count_for_real(evaluation, thread_id=21)
        situation = self.situation(
            {
                "goal_text": "route tickets",
                "modality": "text",
                "task_family": "classification",
                "need_type": ["behaviour"],
                "target_score": 0.9,
            },
            thread_id=21,
            eval_path=str(evaluation),
            input_field="q",
            expected_field="a",
        )
        plan = propose.propose(situation)
        requests = plan.step("baseline").cost.model_requests
        self.assertEqual(requests.provenance, build.INFERRED)
        self.assertEqual(requests.value, float(situation.sample))
        self.assertIn("counted 40 rows", requests.how)

    def test_an_uncounted_eval_set_makes_the_request_cost_unknown(self):
        """And the unknown says the build's own first step is what settles it."""
        evaluation = self.eval_file(rows=40)
        situation = propose.Situation(
            outcome="ACTION__MEASURE_BASELINE",
            result=self.situation({"goal_text": "x"}, thread_id=22).result,
            eval_path=str(evaluation),
            input_field="q",
            expected_field="a",
        )
        plan = propose.propose(situation)
        requests = plan.step("baseline").cost.model_requests
        self.assertEqual(requests.provenance, build.UNKNOWN)
        self.assertIn("count the eval set", requests.find_out_by)
        self.assertEqual(plan.steps[0].tool, "measure_eval_set")

    def test_a_step_that_cannot_reach_the_model_costs_nothing_in_tokens(self):
        evaluation = self.eval_file()
        situation = self.situation(
            {"goal_text": "route tickets", "modality": "text", "target_score": 0.9},
            thread_id=23,
            eval_path=str(evaluation),
        )
        plan = propose.propose(situation)
        for step in plan.steps:
            spec = REGISTRY.get(step.tool)
            self.assertNotIn("providers", spec.reads)
            self.assertEqual(step.cost.model_tokens.value, 0.0)
            self.assertEqual(step.cost.model_tokens.provenance, build.INFERRED)
            self.assertIn("providers", step.cost.model_tokens.how)

    def test_no_shipped_proposal_carries_a_measured_wall_clock(self):
        """The named gap, asserted so it is noticed the day it closes.

        Nothing in this harness stores how long a tool took, so no wall-clock
        estimate can honestly be MEASURED today. When a timing history lands,
        this test fails - and the right response is to delete it, not to
        loosen it.
        """
        evaluation = self.eval_file()
        situation = self.situation(
            {"goal_text": "route tickets", "modality": "text", "target_score": 0.9},
            thread_id=24,
            eval_path=str(evaluation),
        )
        plan = propose.propose(situation)
        for step in plan.steps:
            self.assertEqual(
                step.cost.wall_clock.provenance,
                build.UNKNOWN,
                f"{step.id} claims to know how long it takes; where did that come from?",
            )
            self.assertTrue(step.cost.wall_clock.find_out_by.strip())


# ---------------------------------------------------------------------------
# What a build may not contain.


class WhatABuildMayNotContainTest(ProposalTestCase):
    def test_a_step_may_not_be_a_tool_only_a_person_can_mean(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [a_step("say", tool="state_facts", arguments={"facts": {}})]
            )
        self.assertIn("state_facts", str(raised.exception))
        self.assertIn("question", str(raised.exception))

    def test_state_facts_is_still_the_person_only_tool_this_assumes(self):
        self.assertIn("state_facts", build.PERSON_ONLY_TOOLS)
        for name in build.PERSON_ONLY_TOOLS:
            self.assertIn(name, REGISTRY)

    def test_a_networked_step_may_not_run_in_a_sandbox_that_declared_no_egress(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [
                    a_step(
                        "score",
                        tool="measure_baseline",
                        arguments={
                            "eval_path": str(self.eval_file()),
                            "input_field": "q",
                            "expected_field": "a",
                        },
                    )
                ]
            )
        self.assertIn("egress", str(raised.exception))
        self.assertIn("score", str(raised.exception))

    def test_an_environment_with_egress_must_say_what_for(self):
        with self.assertRaises(BuildInvalid):
            Environment(name="leaky", working_dir="runs/x", egress=True)

    def test_every_reads_value_in_the_registry_is_classified(self):
        """A tool added with a new `reads` word must not slip past the egress check.

        The egress rule is only a guarantee if every read is known to be local
        or known to leave. A tool registered next year with `reads=("s3",)`
        turns this red rather than running quietly inside a sandbox that
        promised no egress.
        """
        known = build.LOCAL_READS | build.NETWORK_READS
        for spec in REGISTRY:
            for read in spec.reads:
                self.assertIn(
                    read,
                    known,
                    f"{spec.name} reads {read!r}, which app/build.py has not "
                    "classified as local or networked",
                )

    def test_a_question_the_harness_could_answer_by_looking_is_refused(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build(
                [a_step("look")],
                questions=(
                    Question(
                        ask="How many rows does your eval set have?",
                        why="the gate asks for thirty",
                        fact="eval_size_n",
                    ),
                ),
            )
        self.assertIn("measure_eval_set", str(raised.exception))

    def test_a_question_about_a_fact_that_does_not_exist_is_refused(self):
        with self.assertRaises(BuildInvalid):
            a_build(
                [a_step("look")],
                questions=(
                    Question(ask="What?", why="because", fact="vibes_per_epoch"),
                ),
            )

    def test_a_question_no_tool_can_answer_is_allowed(self):
        plan = a_build(
            [a_step("look")],
            questions=(
                Question(
                    ask="Which kind of data is this?",
                    why="it is the first fork in the tree",
                    fact="modality",
                ),
            ),
        )
        self.assertEqual(len(plan.questions), 1)

    def test_a_risk_needs_both_halves(self):
        with self.assertRaises(BuildInvalid):
            Risk(what="it might fail", what_we_do="")

    def test_a_build_with_no_steps_is_refused(self):
        with self.assertRaises(BuildInvalid) as raised:
            a_build([])
        self.assertIn("no steps", str(raised.exception))


# ---------------------------------------------------------------------------
# Approval is a contract.


class ApprovalIsAContractTest(ProposalTestCase):
    def plan(self) -> Build:
        return a_build([a_step("look"), a_step("then", needs=("look",))])

    def test_the_same_build_fingerprints_the_same(self):
        self.assertEqual(self.plan().fingerprint(), self.plan().fingerprint())

    def test_an_unchanged_build_reports_no_deviation(self):
        self.assertEqual(self.plan().deviations_from(self.plan()), ())

    def test_an_added_step_is_a_deviation_that_names_it(self):
        approved = self.plan()
        changed = a_build(
            [a_step("look"), a_step("then", needs=("look",)), a_step("extra")]
        )
        deviations = changed.deviations_from(approved)
        self.assertTrue(any("extra" in note for note in deviations))

    def test_a_step_that_does_something_different_is_a_deviation(self):
        approved = self.plan()
        changed = a_build(
            [
                a_step("look", tool="list_recipes"),
                a_step("then", needs=("look",)),
            ]
        )
        deviations = changed.deviations_from(approved)
        self.assertTrue(any("look" in note for note in deviations))

    def test_a_better_cost_estimate_is_not_a_deviation_from_the_contract(self):
        """What runs is the contract. A cost that improved is not a change to it."""
        approved = self.plan()
        cheaper = a_cost()
        changed = a_build(
            [
                a_step("look", cost=cheaper),
                a_step("then", needs=("look",)),
            ]
        )
        self.assertEqual(
            changed.step("look").contract_fingerprint(),
            approved.step("look").contract_fingerprint(),
        )

    def test_a_build_says_which_of_its_steps_need_an_approval(self):
        plan = a_build([a_step("look")])
        self.assertEqual(plan.approvals_required(), ())
        self.assertEqual(plan.as_dict()["needs_approval"], [])


class ExitCriteriaAreCheckedRatherThanReadTest(unittest.TestCase):
    def test_a_criterion_decides_from_an_observation(self):
        criterion = ExitCriterion(
            stated="at least thirty rows",
            source="tool_result",
            subject="rows",
            comparator="at_least",
            value=30,
        )
        self.assertTrue(criterion.met({"rows": 40}).ok)
        self.assertFalse(criterion.met({"rows": 12}).ok)

    def test_a_missing_subject_is_a_failure_and_says_so(self):
        criterion = ExitCriterion(
            stated="it said ok", source="tool_result", subject="ok", comparator="is_true"
        )
        verification = criterion.met({})
        self.assertFalse(verification.ok)
        self.assertIn("ok", verification.because)

    def test_a_dotted_subject_reaches_into_the_observation(self):
        criterion = ExitCriterion(
            stated="the count is measured",
            source="diagnosis",
            subject="fact_origins.eval_size_n",
            comparator="is_measured",
        )
        self.assertTrue(
            criterion.met({"fact_origins": {"eval_size_n": diagnosis.MEASURED}}).ok
        )
        self.assertFalse(
            criterion.met({"fact_origins": {"eval_size_n": diagnosis.ASSERTED}}).ok
        )

    def test_a_comparator_that_needs_a_value_and_has_none_is_refused(self):
        with self.assertRaises(BuildInvalid):
            ExitCriterion(
                stated="at least",
                source="tool_result",
                subject="rows",
                comparator="at_least",
            )

    def test_a_comparator_that_takes_no_value_refuses_one(self):
        with self.assertRaises(BuildInvalid):
            ExitCriterion(
                stated="it said ok",
                source="tool_result",
                subject="ok",
                comparator="is_true",
                value=True,
            )

    def test_an_unobservable_source_is_refused(self):
        with self.assertRaises(BuildInvalid):
            ExitCriterion(
                stated="somebody feels good about it",
                source="vibes",
                subject="ok",
                comparator="is_true",
            )

    def test_the_state_vocabulary_is_the_one_the_design_system_declares(self):
        """One list, referenced, so the diagram and the executor cannot differ."""
        self.assertEqual(
            build.STEP_STATES,
            (
                "queued",
                "preflight",
                "running",
                "waiting_input",
                "waiting_approval",
                "stalled",
                "done",
                "failed",
                "cancelled",
            ),
        )


# ---------------------------------------------------------------------------
# The proposer's own promises.


class YouDoNotGetToNameTheOutcomeTest(ProposalTestCase):
    def test_the_tool_has_no_argument_that_selects_a_remedy(self):
        spec = REGISTRY.get("propose_build")
        self.assertIsNotNone(spec)
        properties = set((spec.schema.get("properties") or {}).keys())
        for forbidden in ("outcome", "verdict", "diagnosis", "method", "recipe", "plan"):
            self.assertNotIn(forbidden, properties)

    def test_the_tool_decides_nothing_and_measures_nothing(self):
        spec = REGISTRY.get("propose_build")
        self.assertEqual(spec.measures, ())
        self.assertEqual(spec.writes, ())

    def test_a_proposer_exists_only_for_an_outcome_the_engine_actually_mints(self):
        """The rewritten half of "no proposer produces a training plan".

        THAT TEST WAS TRUE WHEN IT WAS WRITTEN AND IT WAS NEVER THE INVARIANT.
        It read: *for every outcome in PROPOSERS, assertFalse
        outcome.startswith("TRAIN__")* - which is a claim that this product may
        never act on its own flagship verdict, and `docs/VISION.md` says the
        opposite in as many words: *"If it was training, it trains."* What the
        sentence was really protecting is that nothing a proposer does may make
        a training verdict reachable, and that is asserted directly - here, and
        in `tests/test_a_trained_adapter_is_measured_or_not_trained.py`, which
        drives the gates.

        So this is the strictly stronger version: every outcome with a proposer
        is an outcome the ENGINE declares, derived from the spec rather than
        listed, so a proposer for an invented outcome fails whatever it is
        called. A proposer keyed on something the tree cannot reach is a plan
        for a verdict nobody can get.
        """
        # WIDENED 2026-08-25: "the engine" was the first ledger alone, which
        # made a proposer for the second ledger's verdict read as an invented
        # outcome. The invariant is unchanged and now says what it means: an
        # outcome with a proposer is one SOME ledger this product ships can
        # reach, derived from the specs rather than listed.
        declared = set()
        for path in diagnosis.known_ledgers():
            declared |= set(diagnosis.spec_at(path).declared_outcomes())
        self.assertTrue(declared)
        for outcome in propose.PROPOSERS:
            self.assertIn(
                outcome,
                declared,
                f"{outcome} has a proposer and no ledger declares that outcome",
            )

    def test_every_training_outcome_is_covered_or_explicitly_not_covered(self):
        """One statement about every training outcome, and never two.

        The old version required every `TRAIN__` outcome to be in `NOT_COVERED`
        and in no proposer. `TRAIN__LORA_SFT` has a build now, so the half that
        went false is gone and the half that never could is kept and tightened:
        each training outcome is on exactly one of the two tables, so a reader
        asking "can this product act on my verdict" gets one answer.
        """
        training = set(diagnosis.default_spec().train_outcomes)
        self.assertTrue(training)
        for outcome in training:
            covered = outcome in propose.COVERAGE
            explained = outcome in propose.NOT_COVERED
            self.assertTrue(
                covered or explained,
                f"{outcome} is neither covered nor explained",
            )
            self.assertFalse(
                covered and explained,
                f"{outcome} is both covered and explained away",
            )
            self.assertEqual(
                covered,
                outcome in propose.PROPOSERS,
                f"{outcome}: COVERAGE and PROPOSERS disagree",
            )

    def test_the_training_outcomes_with_no_backend_stay_uncovered(self):
        """`recipes/` holds two trainers, so seven of the nine cannot be planned.

        Derived from the spec's own list minus the ones that have a proposer,
        so a tenth training outcome added next year arrives here rather than
        being silently absent - and each one's reason has to name why, which is
        the backend and not the proposer.

        IT SAID EIGHT AND IT WAS RIGHT WHEN IT SAID IT. `recipes/hf-peft-dpo/`
        made `TRAIN__DPO` plannable, which is exactly the event this shape is
        built to survive: the number is derived from two sets, so a recipe
        landing moves it without anybody remembering to.
        """
        training = set(diagnosis.default_spec().train_outcomes)
        without = sorted(training - set(propose.PROPOSERS))
        _WITH_A_BACKEND = training & set(propose.PROPOSERS)
        # MINUS TWO NOW, AND THE SECOND ONE IS A DIRECTORY IN THE TREE.
        # `recipes/hf-peft-dpo/` is the second real trainer, so `TRAIN__DPO`
        # left this group the day it shipped. The arithmetic is written as
        # "every training outcome except the ones with a backend" rather than as
        # a literal, so the next recipe moves this number by existing.
        self.assertEqual(len(without), len(training) - len(_WITH_A_BACKEND), without)
        self.assertFalse(set(without) & _WITH_A_BACKEND)
        for outcome in without:
            self.assertIn(outcome, propose.NOT_COVERED)
            self.assertIn("backend", propose.NOT_COVERED[outcome])

    def test_a_model_asking_for_a_plan_still_goes_through_the_engine(self):
        """A model's asserted facts cannot reach a plan the gates would not allow."""
        evaluation = self.eval_file()
        result = REGISTRY.call(
            "propose_build",
            {
                "facts": {
                    "goal_text": "make it better",
                    "modality": "text",
                    "task_family": "classification",
                    "need_type": ["behaviour"],
                    "target_score": 0.9,
                    "eval_size_n": 5000,
                    "baseline_measured": True,
                    "baseline_score": 0.4,
                    "labeled_examples_n": 50000,
                },
                "eval_path": str(evaluation),
            },
            actor=evidence.MODEL,
            thread_id=31,
        )
        self.assertFalse(result.get("verdict") == "TRAIN")
        self.assertEqual(result.get("outcome"), "ACTION__SUBSTANTIATE_CLAIMED_FACTS")


class TheProposerRefusesRatherThanDrawingTest(ProposalTestCase):
    def test_an_outcome_with_no_proposer_comes_back_as_a_refusal_with_a_reason(self):
        result = REGISTRY.call(
            "propose_build",
            {"facts": {"goal_text": "x"}},
            actor=evidence.USER,
            thread_id=41,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_honest_build")
        self.assertIn(result["outcome"], propose.NOT_COVERED)
        self.assertIn(
            propose.NOT_COVERED[result["outcome"]][:40], result["detail"]
        )

    def test_a_missing_path_is_named_rather_than_guessed(self):
        result = REGISTRY.call(
            "propose_build",
            {
                "facts": {
                    "goal_text": "route tickets",
                    "modality": "text",
                    "target_score": 0.9,
                }
            },
            actor=evidence.USER,
            thread_id=42,
        )
        self.assertFalse(result["ok"])
        self.assertIn("eval_path", result["needs"])

    def test_a_path_that_is_not_there_is_refused(self):
        with self.assertRaises(propose.NotEnoughToPropose):
            propose.Situation(
                outcome="x",
                result=self.situation({"goal_text": "x"}, thread_id=43).result,
                eval_path=str(self.root / "nothing_here.jsonl"),
            ).require_path("eval_path")

    def test_counting_an_eval_set_twice_is_refused_as_a_plan(self):
        """A build that would change nothing is not a build."""
        small = self.eval_file(rows=4, name="small.jsonl")
        self.count_for_real(small, thread_id=44)
        situation = self.situation(
            {"goal_text": "route tickets", "modality": "text", "target_score": 0.9},
            thread_id=44,
            eval_path=str(small),
        )
        self.assertEqual(situation.outcome, "BLOCKED__BUILD_EVAL_SET")
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            propose.propose(situation)
        self.assertIn("more graded examples", str(raised.exception))

    def test_the_g0_threshold_is_read_from_the_spec_rather_than_typed(self):
        self.assertEqual(
            propose.g0_minimum(),
            int(
                diagnosis.default_spec()
                .gate_row("G0_EVAL_SET", "any")["requires"]
                .split(">=")[1]
                .strip()
            ),
        )


class TheCoverageStatementIsCompleteAndTrueTest(unittest.TestCase):
    """Say plainly which outcomes were not covered and why - and mean it."""

    def test_every_declared_outcome_is_either_covered_or_explained(self):
        # "DECLARED" MEANS EVERY LEDGER THIS PRODUCT SHIPS. The tables were
        # first-ledger-only by history; the agent instruments' proposer made
        # a second-ledger key real, and an accounting that calls a covered
        # outcome undeclared would be the one-directional-bound defect again.
        declared = set()
        for path in diagnosis.known_ledgers():
            declared |= set(diagnosis.spec_at(path).declared_outcomes())
        covered = set(propose.COVERAGE)
        explained = set(propose.NOT_COVERED)
        self.assertEqual(
            declared - covered - explained,
            set(),
            "an outcome exists that this product says nothing about",
        )
        self.assertEqual((covered | explained) - declared, set())
        self.assertEqual(covered & explained, set())

    def test_the_covered_list_is_the_proposer_table(self):
        self.assertEqual(set(propose.COVERAGE), set(propose.PROPOSERS))

    def test_every_reason_is_a_reason(self):
        for outcome, reason in propose.NOT_COVERED.items():
            self.assertGreater(len(reason), 60, f"{outcome} has no real reason")

    def test_the_row_count_outcome_took_the_fix_its_old_reason_prescribed(self):
        """This test fired on 2026-08-28 and was rewritten by its own instruction.

        It used to assert that nothing measures `tabular_rows` and that the
        outcome has no proposer, with a docstring saying: *"the moment somebody
        registers a tool that stamps `tabular_rows` the honest answer changes
        from 'we cannot' to 'we have not'. Then this fails, and writing the
        proposer is the fix."* The tool landed, this failed, and the proposer
        was written in the same step.

        NOT LOOSENED - it asserts the same thing from the other side, and adds
        the half the old version could not: that the build COUNTS rather than
        ASKS. A plan that asked the person to type a number the harness can read
        would satisfy "has a proposer" and would be the exact shape
        `tests/test_a_stated_quantity_becomes_an_offer_to_count_it.py` refuses.
        """
        measurers = [spec.name for spec in REGISTRY if "tabular_rows" in spec.measures]
        self.assertEqual(measurers, ["profile_dataset"])
        self.assertIn("ACTION__COUNT_THE_ROWS", propose.PROPOSERS)
        self.assertNotIn("ACTION__COUNT_THE_ROWS", propose.NOT_COVERED)

    def test_the_reason_given_for_the_off_the_shelf_outcome_is_actually_true(self):
        """`NO_TRAIN__OFF_THE_SHELF_MODEL` is uncovered because nothing here can
        score Whisper, SAM or CLIP on an eval set. The canary is the roster of
        tools that talk to a model at all: a third one appearing means somebody
        should re-read whether that is still true.

        IT HAS FIRED TWICE NOW - at `run_eval`, then at `try_prompt` - AND THE
        CONCLUSION DID NOT CHANGE EITHER TIME. The evaluation bench is a second
        scorer and the prompt bench a third, and all three are the same kind of
        scorer: they send text to a chat provider and grade by exact match,
        containment, or a chat model judging. None can measure an audio or an
        image model, so the outcome stays uncovered for the reason `NOT_COVERED`
        gives, and that entry names all three.

        The roster is asserted exactly rather than by length so that a fourth
        tool cannot arrive without somebody re-reading the reason. If the fourth
        one is an adapter that sends audio or pixels, the honest response is to
        cover the outcome - not to extend this list.
        """
        self.assertNotIn("NO_TRAIN__OFF_THE_SHELF_MODEL", propose.PROPOSERS)
        # 2026-09-12: two tools now read a connection WITHOUT scoring a model
        # (generate_rows writes rows, judge_rows grades rows); propose names
        # them in NOT_A_SCORER with reasons, and the roster of SCORERS - the
        # thing this reason is about - is still the three text scorers.
        scorers = sorted(
            spec.name
            for spec in REGISTRY
            if "providers" in spec.reads and spec.name not in propose.NOT_A_SCORER
        )
        self.assertEqual(scorers, ["measure_baseline", "run_eval", "try_prompt"])
        reason = propose.NOT_COVERED["NO_TRAIN__OFF_THE_SHELF_MODEL"]
        for name in scorers:
            self.assertIn(name, reason, f"the reason does not name {name}")

    def test_the_data_bench_reason_names_the_data_tools_that_do_exist(self):
        """It said they did not exist, and two of them did.

        The entry read *"the tools that would split, deduplicate, label, convert
        or join a dataset do not exist yet"* while `carve_eval_set` and
        `drop_duplicates` were registered and writing files - so a person who
        carved an eval set with this product and then landed on
        BLOCKED__FIX_LABELS_OR_TASK was told, in the same session, that it has
        no tool that splits a dataset. That is the class of sentence this file
        has now caught three times: a written claim about what the harness
        cannot do, going stale the day it could.

        The roster is asserted exactly, like the scorers above, so a third
        dataset writer cannot arrive without somebody re-reading whether these
        three outcomes are still uncovered.
        """
        writers = propose.tools_that_write_a_dataset()
        # 2026-08-27, and this equality did exactly its job: adding
        # draw_verification_sample reddened it, and re-reading the three
        # outcomes is what the failure asked for. The answer for
        # BLOCKED__COLLECT_OR_SYNTHESIZE_DATA is that it is STILL uncovered and
        # the reason is now sharper than it was - the ledger's recipe is
        # "synthesize with a teacher model, then verify a tenth by hand", the
        # verifying half ships as of today, and the teacher does not. Sampling
        # rows you already have answers a shortage of information with the same
        # shortage of information, which is not a build.
        # 2026-09-12, and the equality did its job again: generate_rows and
        # judge_rows reddened it, and re-reading found the reason had gone
        # FALSE - "the teacher is the part that does not [ship]" - because
        # generate_rows IS the teacher. The outcome stays uncovered for a
        # different, true reason (no proposer chains generate, judge, the
        # tenth read by hand and a measured comparison into one build), and
        # the reason now says so.
        self.assertEqual(
            writers,
            (
                "carve_eval_set",
                "carve_rows",
                "draw_verification_sample",
                "drop_duplicates",
                "generate_rows",
                # 2026-09-18, and the equality did its job a third time:
                # generate_tool_rows (chain-first tool-use rows) reddened it.
                # Re-read: the three outcomes stay uncovered for the reason the
                # sentence gives - the rows it writes teach tool use, not the
                # missing column, the labels or the missing data.
                "generate_tool_rows",
                "judge_rows",
                "synthesize_rows",
            ),
        )
        for outcome in (
            "BLOCKED__COLLECT_OR_SYNTHESIZE_DATA",
            "BLOCKED__FIX_LABELS_OR_TASK",
            "NO_DEEP__FIND_THE_MISSING_FEATURE",
        ):
            reason = propose.NOT_COVERED[outcome]
            self.assertNotIn("do not exist yet", reason)
            for name in writers:
                self.assertIn(name, reason, f"{outcome}'s reason omits {name}")

    def test_the_dataset_writers_are_the_tools_that_really_write_datasets(self):
        """The positive control: the roster is read, not typed."""
        for name in propose.tools_that_write_a_dataset():
            self.assertIn(propose.THE_DATASET_WRITE, REGISTRY.get(name).writes)
        self.assertTrue(propose.tools_that_write_a_dataset())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
