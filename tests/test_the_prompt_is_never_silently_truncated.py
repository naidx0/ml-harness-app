"""The instruction set arrives whole, or the turn does not happen.

## The hole this closes, and why the suite could not see it

`tests/test_instruction_set.py` asserts that every non-negotiable law survives
assembly. It reads the assembled string, in this process. It cannot see a
provider handing that string to a server which keeps a fraction of it and throws
the rest away - which is what `app/providers/ollama.py` allowed, because it sent
no `num_ctx` and the runtime window was therefore whatever the server happened
to choose.

That is this project's recurring failure shape and it is worth naming again: a
guarantee that holds in the place it is tested and not in the place it is used.
The laws were provably present in a Python string and provably absent from the
model's context, and nothing anywhere went red.

## The numbers these tests are built on, and where they came from

Measured against the live Ollama 0.32.5 on 127.0.0.1:11434 with
`granite4-hermes:latest`, through `/api/chat`'s own `prompt_eval_count` - the
model's tokeniser, not an estimate:

| what                                  | tokens |
| ------------------------------------- | ------ |
| system prompt, before this change      |  8,025 |
| system prompt, after                   |  7,108 |
| the 28 tool schemas                    |  6,074 |
| **a turn's fixed cost, after**         | 13,213 |

And from `/api/show` for that same model: a ceiling of 1,048,576 tokens, and a
Modelfile `num_ctx` of 65,536. Sixteen times apart, and the harness was reading
the first while being subject to the second.

Ollama's own default when nothing sets `num_ctx` is 4,096. Asked what it did
with the real 13,213-token turn at that window, the server answered HTTP 200,
no error field, `prompt_eval_count = 2,050` - **it kept 15% of the prompt and
replied as if nothing had happened.** Half the window is reserved for
generation, and the overflow is resolved by dropping prompt tokens - which
ones is the server's business, and was not measured here.

There is also no gentle version of this. 13,213 tokens into a 13,213 window
evaluates 6,609; into a 13,312 window it evaluates all 13,213. Ninety-nine
tokens apart, and one of them silently loses six thousand - which is why
`WORKING_HEADROOM_TOKENS` exists and why a check that only asked "does it fit"
would be one token from useless.

## What is asserted, and what is deliberately not

Asserted: that a window too small produces **no request at all**, that a window
large enough produces a request which **names** the window, and that a window
nobody could establish is carried as unknown rather than as room.

Not asserted: a token count. The pre-send figure is an estimate - see
`app/providers/budget.py` for why there is no tokeniser to ask - and a test that
pinned it would be pinning the estimator rather than the guarantee. What is
pinned is the estimator's *direction*: it must never come in under a ratio
actually measured, because an estimate that errs low reopens the hole.
"""

from __future__ import annotations

import json
import unittest

from app import instructions
from app.providers import budget
from app.providers import ollama, openai_compatible
from app.tools.registry import REGISTRY


#: Measured, not chosen: 35,348 characters of assembled system prompt evaluated
#: as 8,025 tokens by granite4-hermes. Any estimator that reports fewer tokens
#: than that for that many characters would have let the real prompt through a
#: window it does not fit.
MEASURED_CHARACTERS = 35_348
MEASURED_TOKENS = 8_025

#: What Ollama uses when no Modelfile and no environment variable says
#: otherwise. The window the defect was found hiding behind.
OLLAMA_DEFAULT_WINDOW = 4_096


class Recorder:
    """A fake `urlopen` that records every request instead of making it."""

    def __init__(self, bodies: dict[str, bytes], lines: dict[str, list[str]] | None = None):
        self.bodies = bodies
        self.lines = lines or {}
        self.calls: list[dict] = []

    def __call__(self, request, timeout=None):
        path = request.full_url.split("/", 3)[-1]
        path = "/" + path if not path.startswith("/") else path
        payload = None
        if request.data:
            payload = json.loads(request.data.decode("utf-8"))
        self.calls.append(
            {"url": request.full_url, "path": path, "payload": payload}
        )
        key = next((k for k in self.bodies if request.full_url.endswith(k)), None)
        line_key = next((k for k in self.lines if request.full_url.endswith(k)), None)
        return _Response(
            self.bodies.get(key, b"{}"), self.lines.get(line_key, [])
        )

    def paths(self) -> list[str]:
        return [call["url"] for call in self.calls]

    def sent_to(self, suffix: str) -> list[dict]:
        return [c for c in self.calls if c["url"].endswith(suffix)]


class _Response:
    def __init__(self, body: bytes, lines: list[str]):
        self._body = body
        self._lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return self._body


def shown(*, ceiling: int | None = None, num_ctx: int | None = None) -> bytes:
    """An `/api/show` body shaped the way the live server shapes one."""
    body: dict = {"capabilities": ["completion", "tools"]}
    if ceiling is not None:
        body["model_info"] = {"granitehybrid.context_length": ceiling}
    if num_ctx is not None:
        # The real field is the Modelfile's own text, not JSON. Reproduced
        # exactly, including the run of spaces, because parsing it is the code
        # under test.
        body["parameters"] = f"num_ctx                        {num_ctx}\nstop \"<|end|>\""
    return json.dumps(body).encode("utf-8")


def a_reply() -> list[str]:
    return [
        json.dumps({"message": {"content": "hello"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]


def a_real_turn() -> tuple[list[dict], list[dict]]:
    """The messages and tools a real first turn actually carries."""
    return (
        [
            {"role": "system", "content": instructions.assemble(tool_calling=True)},
            {"role": "user", "content": "can you actually help me build everything?"},
        ],
        REGISTRY.model_tools(),
    )


# ---------------------------------------------------------------------------
# The arithmetic, on its own.


class AnUnknownBudgetIsNotAnInfiniteOneTest(unittest.TestCase):
    """The state the whole design turns on.

    "We could not establish the window" and "the window is large enough" are
    different facts, and a type that cannot hold the difference will eventually
    report the second when it means the first.
    """

    def test_a_budget_nobody_established_is_not_known(self):
        self.assertFalse(budget.UNKNOWN.known)
        self.assertIsNone(budget.UNKNOWN.ceiling)
        self.assertEqual(budget.UNKNOWN.provenance, "defaulted")

    def test_an_unknown_budget_never_reports_a_fit(self):
        plan = budget.plan(budget.estimate("x" * 400_000), budget.UNKNOWN)
        self.assertEqual(plan.verdict, "unknown")
        self.assertNotEqual(plan.verdict, "fits")

    def test_an_unknown_budget_still_lets_the_turn_go(self):
        """Because refusing every unknown would refuse every OpenAI connection.

        The honest move is to send and to say the window is unknown - not to
        block on an absence, and not to claim a fit nobody checked.
        """
        self.assertTrue(budget.plan(budget.estimate("hi"), budget.UNKNOWN).send)

    def test_zero_and_false_are_not_windows(self):
        """`0` is not a small budget and `True` is not a budget at all."""
        for value in (0, -1, False, True, None, "65536"):
            with self.subTest(value=value):
                self.assertFalse(budget.Budget(ceiling=value).known)


class TheEstimateErrsHighTest(unittest.TestCase):
    def test_it_never_undercounts_against_a_ratio_that_was_measured(self):
        """The one property the estimator has to have.

        35,348 characters of real system prompt were evaluated as 8,025 tokens
        by granite4-hermes. An estimator that reported fewer than that for that
        many characters would declare a fit for a prompt that does not fit, and
        the silent truncation would be back.
        """
        self.assertGreaterEqual(
            budget.estimate("x" * MEASURED_CHARACTERS).tokens, MEASURED_TOKENS
        )
        self.assertLess(budget.CHARS_PER_TOKEN, MEASURED_CHARACTERS / MEASURED_TOKENS)

    def test_a_short_string_is_not_zero_tokens(self):
        self.assertGreaterEqual(budget.estimate("hi").tokens, 1)

    def test_the_estimate_says_it_is_one(self):
        need = budget.estimate("some prompt")
        self.assertEqual(need.provenance, "inferred")
        self.assertFalse(need.measured)
        self.assertIn("estimated from", need.source)


class TheToolSchemasAreCountedTest(unittest.TestCase):
    """The half that gets forgotten, and it is 6,074 tokens of the 13,213."""

    def test_the_schemas_are_part_of_what_is_billed(self):
        messages, tools = a_real_turn()
        with_tools = budget.estimate(*budget.billable(messages, tools)).tokens
        without = budget.estimate(*budget.billable(messages, None)).tokens
        self.assertGreater(with_tools, without)
        # Not a token assertion - a proportion one. The schemas are a large
        # fraction of a turn, not a rounding error, and a budget check that
        # ignored them would be wrong by roughly half.
        self.assertGreater(with_tools - without, without * 0.5)

    def test_a_turn_with_no_messages_and_no_tools_bills_nothing_much(self):
        self.assertEqual(budget.billable(None, None), [])


class TheRefusalSaysWhatToDoTest(unittest.TestCase):
    """The words a person actually gets. They are the deliverable, not a log line."""

    def setUp(self):
        messages, tools = a_real_turn()
        self.need = budget.estimate(*budget.billable(messages, tools))
        self.small = budget.Budget(
            ceiling=OLLAMA_DEFAULT_WINDOW,
            configured=OLLAMA_DEFAULT_WINDOW,
            settable=True,
            provenance="measured",
            source="/api/show reports a ceiling of 4,096",
        )
        self.text = budget.plan(self.need, self.small, model="tiny").refusal

    def test_it_refuses_rather_than_truncating(self):
        plan = budget.plan(self.need, self.small, model="tiny")
        self.assertEqual(plan.verdict, "refused")
        self.assertFalse(plan.send)
        self.assertTrue(plan.refusal)

    def test_it_names_both_numbers_and_the_model(self):
        self.assertIn("4,096", self.text)
        self.assertIn("`tiny`", self.text)
        self.assertIn("did not send", self.text)

    def test_it_carries_the_provenance_of_the_figure_it_quotes(self):
        """Invariant 3. An estimate presented as a measurement is the defect."""
        self.assertIn("about ", self.text)
        self.assertIn("estimated from", self.text)

    def test_it_does_not_offer_either_of_the_two_forbidden_moves(self):
        """Shipping fewer laws, and fetching a smaller model.

        The first is forbidden outright. The second is worse than useless -
        parameter count and context window are different axes, and the smaller
        model is usually the one with the smaller window - so the refusal says
        so in as many words rather than leaving the reader to infer it.
        """
        lowered = self.text.lower()
        self.assertNotIn("shorter instruction", lowered)
        self.assertNotIn("fewer laws", lowered)
        self.assertIn("not the same thing as a larger model", lowered)
        self.assertIn("larger context window", lowered)

    def test_it_says_the_product_still_works(self):
        """The standing true thing. Every tool in this app is also a button."""
        self.assertIn("also a button", self.text)


# ---------------------------------------------------------------------------
# Ollama: the adapter the defect lived in.


class OllamaNamesTheWindowTest(unittest.TestCase):
    def test_a_turn_now_sends_num_ctx(self):
        """The regression for the defect itself.

        Before this, `/api/chat` carried no `options` at all and the window was
        whatever the server chose. A test that only checked the refusal path
        would not have caught that, because the refusal path is the rare one.
        """
        recorder = Recorder(
            {"/api/show": shown(ceiling=1_048_576, num_ctx=65_536)},
            {"/api/chat": a_reply()},
        )
        messages, tools = a_real_turn()
        provider = ollama.OllamaProvider("http://127.0.0.1:11434", "m", opener=recorder)
        list(provider.stream(messages, tools))

        chat = recorder.sent_to("/api/chat")
        self.assertEqual(len(chat), 1)
        self.assertIn("options", chat[0]["payload"])
        self.assertIn("num_ctx", chat[0]["payload"]["options"])

    def test_it_never_lowers_a_window_the_user_set_on_purpose(self):
        """65,536 in a Modelfile is somebody's decision, not our headroom.

        The harness raises a window that is too small. It does not shrink one
        that is generous, because the reason it is generous is not ours to
        overrule and a shorter conversation is a real cost to the person having
        it.
        """
        recorder = Recorder(
            {"/api/show": shown(ceiling=1_048_576, num_ctx=65_536)},
            {"/api/chat": a_reply()},
        )
        messages, tools = a_real_turn()
        list(
            ollama.OllamaProvider(
                "http://127.0.0.1:11434", "m", opener=recorder
            ).stream(messages, tools)
        )
        asked = recorder.sent_to("/api/chat")[0]["payload"]["options"]["num_ctx"]
        self.assertGreaterEqual(asked, 65_536)

    #: The ceiling this clamp is tested at, and IT USED TO BE 32,768.
    #:
    #: `a_real_turn()` carries the WHOLE registry, which is the degenerate shape
    #: - a turn whose walk could not be computed loads every tool on purpose,
    #: and `conductor` hands `blocks.active(...).names()` on every turn that
    #: could. Measured on 2026-08-28, at 55 registered tools: that unscoped turn
    #: needs 28,955 tokens, and with `WORKING_HEADROOM_TOKENS` on top it is
    #: 33,051 - so a 32,768-window model REFUSES it, correctly, and nothing
    #: reaches `/api/chat` for this test to read.
    #:
    #: THAT REFUSAL IS THE PRODUCT WORKING AND IT IS ALSO A REAL FINDING. At 54
    #: tools the same turn came to 32,680 against the same ceiling: eighty-eight
    #: tokens of margin, which nobody had noticed was all that was left. One
    #: tool spent it. What that says is about the UNSCOPED shape only - the
    #: scoped turn a person actually gets is bounded by
    #: `test_the_diagnosis_is_not_optional.FOCUSED_BUDGET` and is a fraction of
    #: this - but "the fallback no longer fits a 32K model" is worth writing
    #: down where somebody will find it rather than leaving in a raised number.
    #:
    #: So the ceiling moves and the CLAMP is what is still being tested: the
    #: server is told 65,536 is configured, this is below it, and the assertion
    #: is that we never ask above the weights' own limit.
    A_CEILING_THIS_TURN_FITS_UNDER = 40_960

    def test_it_never_asks_for_more_than_the_weights_support(self):
        """A request above the ceiling is clamped by the server, silently.

        Which puts us straight back where we started: a window we believe we
        have and do not. So the ask is bounded here, where the bound is known.
        """
        ceiling = self.A_CEILING_THIS_TURN_FITS_UNDER
        recorder = Recorder(
            {"/api/show": shown(ceiling=ceiling, num_ctx=65_536)},
            {"/api/chat": a_reply()},
        )
        messages, tools = a_real_turn()
        list(
            ollama.OllamaProvider(
                "http://127.0.0.1:11434", "m", opener=recorder
            ).stream(messages, tools)
        )
        asked = recorder.sent_to("/api/chat")[0]["payload"]["options"]["num_ctx"]
        self.assertLessEqual(asked, ceiling)
        # NON-VACUOUS: without the clamp we would have asked for the 65,536 the
        # server reports as configured, which the weights cannot hold.
        self.assertLess(asked, 65_536)

    def test_the_unscoped_turn_no_longer_fits_a_thirty_two_thousand_window(self):
        """THE FINDING ABOVE, ASSERTED RATHER THAN LEFT IN A COMMENT.

        Two claims, and both matter. The turn that loads every tool is now over
        a 32K model's window - and it is REFUSED rather than truncated, which is
        the whole thesis of this file. If the day comes that this starts fitting
        again, the comment above has gone stale and this test says so.
        """
        messages, tools = a_real_turn()
        need = budget.estimate(*budget.billable(messages, tools))
        self.assertGreater(need.tokens + budget.WORKING_HEADROOM_TOKENS, 32_768)

        thirty_two_k = budget.Budget(
            ceiling=32_768,
            configured=32_768,
            settable=True,
            provenance="measured",
            source="/api/show reports a ceiling of 32,768",
        )
        plan = budget.plan(need, thirty_two_k, model="m")
        self.assertEqual(plan.verdict, "refused")
        self.assertFalse(plan.send)

    def test_the_window_is_asked_for_once_per_turn_not_once_per_round(self):
        """A turn is several `stream()` calls against one adapter object."""
        recorder = Recorder(
            {"/api/show": shown(ceiling=1_048_576, num_ctx=65_536)},
            {"/api/chat": a_reply()},
        )
        messages, tools = a_real_turn()
        provider = ollama.OllamaProvider("http://127.0.0.1:11434", "m", opener=recorder)
        for _ in range(3):
            list(provider.stream(messages, tools))
        self.assertEqual(len(recorder.sent_to("/api/show")), 1)
        self.assertEqual(len(recorder.sent_to("/api/chat")), 3)


class OllamaRefusesRatherThanTruncatesTest(unittest.TestCase):
    def test_the_real_instruction_set_against_ollamas_default_window_is_refused(self):
        """End to end, with the real prompt and the real 28 schemas.

        4,096 is not a hypothetical - it is what Ollama uses when no Modelfile
        and no `OLLAMA_CONTEXT_LENGTH` says otherwise, which is the state a new
        user is in. The measured cost of a turn is 13,213 tokens. This is the
        defect, expressed as the assertion that would have caught it.
        """
        recorder = Recorder(
            {"/api/show": shown(ceiling=OLLAMA_DEFAULT_WINDOW)},
            {"/api/chat": a_reply()},
        )
        messages, tools = a_real_turn()
        deltas = list(
            ollama.OllamaProvider(
                "http://127.0.0.1:11434", "granite4-hermes", opener=recorder
            ).stream(messages, tools)
        )
        self.assertEqual([d.kind for d in deltas], ["error"])
        self.assertIn("did not send", deltas[0].detail)
        self.assertIn("granite4-hermes", deltas[0].detail)

    def test_nothing_is_sent_when_the_turn_is_refused(self):
        """Refused means refused. Not sent-and-then-apologised-for.

        The point of refusing before the request is that a truncated prompt is
        never evaluated, so no reply is ever produced from a harness whose laws
        were half delivered - and on a metered endpoint, nothing is paid for.
        """
        recorder = Recorder(
            {"/api/show": shown(ceiling=OLLAMA_DEFAULT_WINDOW)},
            {"/api/chat": a_reply()},
        )
        messages, tools = a_real_turn()
        list(
            ollama.OllamaProvider(
                "http://127.0.0.1:11434", "m", opener=recorder
            ).stream(messages, tools)
        )
        self.assertEqual(recorder.sent_to("/api/chat"), [])

    def test_a_window_that_holds_the_prompt_but_leaves_no_room_is_still_refused(self):
        """Fitting and being usable are different. Headroom is not optional.

        A window that holds the instruction set exactly has nothing left for the
        user's question, the tool results or the reply, so the truncation lands
        one message later instead of never.
        """
        messages, tools = a_real_turn()
        need = budget.estimate(*budget.billable(messages, tools))
        exactly = budget.Budget(
            ceiling=need.tokens, configured=need.tokens, settable=True,
            provenance="measured", source="exactly enough and no more",
        )
        self.assertEqual(budget.plan(need, exactly).verdict, "refused")
        self.assertGreater(budget.WORKING_HEADROOM_TOKENS, 0)


class OllamaReadsBothNumbersTest(unittest.TestCase):
    """The ceiling and the configured window are different facts."""

    def budget_from(self, body: bytes):
        return ollama.OllamaProvider(
            "http://127.0.0.1:11434", "m", opener=Recorder({"/api/show": body})
        ).context_budget()

    def test_the_two_numbers_are_read_separately(self):
        got = self.budget_from(shown(ceiling=1_048_576, num_ctx=65_536))
        self.assertEqual(got.ceiling, 1_048_576)
        self.assertEqual(got.configured, 65_536)
        self.assertEqual(got.provenance, "measured")
        self.assertTrue(got.settable)

    def test_a_modelfile_with_no_num_ctx_leaves_the_configured_window_unknown(self):
        """Because the server's own default is not readable over HTTP.

        Guessing 4,096 here would be inventing a number that happens to be
        right today and wrong on the next Ollama release.
        """
        got = self.budget_from(shown(ceiling=1_048_576))
        self.assertEqual(got.ceiling, 1_048_576)
        self.assertIsNone(got.configured)

    def test_a_parameters_block_without_a_num_ctx_line_is_not_a_crash(self):
        body = json.dumps(
            {"model_info": {"x.context_length": 8192}, "parameters": 'stop "<|end|>"'}
        ).encode()
        self.assertIsNone(self.budget_from(body).configured)

    def test_a_num_ctx_that_is_not_a_number_is_not_a_window(self):
        body = json.dumps({"parameters": "num_ctx    lots"}).encode()
        self.assertIsNone(self.budget_from(body).configured)

    def test_a_server_that_says_nothing_leaves_an_unknown_budget(self):
        provider = ollama.OllamaProvider(
            "http://127.0.0.1:11434", "m", opener=_broken_opener
        )
        got = provider.context_budget()
        self.assertFalse(got.known)
        self.assertIn("did not answer", got.source)

    def test_an_unknown_window_still_gets_a_turn_and_still_names_one(self):
        """The improvement even in the dark.

        We do not know the ceiling, so we cannot refuse. But naming the window
        we need is still strictly better than inheriting a default we cannot
        read - it is the difference between a server that clamps our number and
        a server that quietly applies its own.
        """
        recorder = Recorder({"/api/show": b"not json"}, {"/api/chat": a_reply()})
        messages, tools = a_real_turn()
        deltas = list(
            ollama.OllamaProvider(
                "http://127.0.0.1:11434", "m", opener=recorder
            ).stream(messages, tools)
        )
        self.assertIn("text", [d.kind for d in deltas])
        chat = recorder.sent_to("/api/chat")
        self.assertEqual(len(chat), 1)
        self.assertIn("num_ctx", chat[0]["payload"]["options"])


def _broken_opener(request, timeout=None):
    raise OSError("nobody home")


# ---------------------------------------------------------------------------
# OpenAI-compatible: the same question, a different honest answer.


def models_body(**fields) -> bytes:
    return json.dumps({"data": [{"id": "m", **fields}]}).encode("utf-8")


class OpenAICompatibleAsksWhereItCanTest(unittest.TestCase):
    def test_each_vendors_field_name_is_read(self):
        """Four servers, four names for one number. None of them invented."""
        for field, value in (
            ("context_length", 128_000),
            ("max_model_len", 32_768),
            ("max_context_length", 8_192),
            ("context_window", 200_000),
        ):
            with self.subTest(field=field):
                got = openai_compatible.OpenAICompatibleProvider(
                    "https://api.example.com/v1",
                    "m",
                    opener=Recorder({"/models": models_body(**{field: value})}),
                ).context_budget()
                self.assertEqual(got.ceiling, value)
                self.assertEqual(got.provenance, "measured")
                self.assertIn(field, got.source)

    def test_an_endpoint_that_states_no_window_leaves_it_unknown(self):
        """OpenAI's `/models` does not report one, and that is not a failure.

        What would be a failure is deriving it from the model id. "32k" in a
        name is a marketing string; treating it as a measurement is inventing a
        number in the most literal available sense.
        """
        got = openai_compatible.OpenAICompatibleProvider(
            "https://api.openai.com/v1",
            "m",
            opener=Recorder({"/models": models_body(owned_by="openai")}),
        ).context_budget()
        self.assertFalse(got.known)
        self.assertEqual(got.provenance, "defaulted")
        self.assertIn("states no context window", got.source)

    def test_the_window_is_not_claimed_as_settable(self):
        """`/chat/completions` has no field for it, so we cannot raise it.

        Reporting otherwise would be an invented capability, which the prompt
        has a law about and the code should not need one.
        """
        got = openai_compatible.OpenAICompatibleProvider(
            "https://api.example.com/v1",
            "m",
            opener=Recorder({"/models": models_body(context_length=128_000)}),
        ).context_budget()
        self.assertFalse(got.settable)

    def test_a_known_window_that_is_too_small_refuses_before_it_is_billed(self):
        recorder = Recorder({"/models": models_body(context_length=4_096)})
        messages, tools = a_real_turn()
        deltas = list(
            openai_compatible.OpenAICompatibleProvider(
                "https://api.example.com/v1", "m", opener=recorder
            ).stream(messages, tools)
        )
        self.assertEqual([d.kind for d in deltas], ["error"])
        self.assertEqual(recorder.sent_to("/chat/completions"), [])

    def test_an_unknown_window_does_not_block_the_turn(self):
        recorder = Recorder(
            {"/models": models_body(owned_by="openai")},
            {"/chat/completions": ["data: " + json.dumps(
                {"choices": [{"delta": {"content": "hi"}}]}
            ), "data: [DONE]"]},
        )
        messages, tools = a_real_turn()
        deltas = list(
            openai_compatible.OpenAICompatibleProvider(
                "https://api.example.com/v1", "m", opener=recorder
            ).stream(messages, tools)
        )
        self.assertIn("text", [d.kind for d in deltas])
        self.assertEqual(len(recorder.sent_to("/chat/completions")), 1)

    def test_a_missing_models_endpoint_is_unknown_rather_than_fatal(self):
        got = openai_compatible.OpenAICompatibleProvider(
            "http://127.0.0.1:8080/v1", "m", opener=_broken_opener
        ).context_budget()
        self.assertFalse(got.known)

    def test_the_window_reaches_the_capability_row_with_its_provenance(self):
        """So the interface can show it, and show where it came from."""
        recorder = Recorder(
            {
                "/models": models_body(context_length=128_000),
                "/chat/completions": json.dumps(
                    {"choices": [{"message": {"tool_calls": [{"id": "1"}]}}]}
                ).encode(),
            }
        )
        caps = openai_compatible.OpenAICompatibleProvider(
            "https://api.example.com/v1", "m", opener=recorder
        ).capabilities()
        self.assertEqual(caps.ctx_len, 128_000)
        self.assertEqual(caps.provenance["ctx_len"], "measured")

    def test_an_endpoint_that_states_nothing_reports_no_window_not_a_guess(self):
        recorder = Recorder(
            {
                "/models": models_body(owned_by="openai"),
                "/chat/completions": json.dumps(
                    {"choices": [{"message": {"content": "no"}}]}
                ).encode(),
            }
        )
        caps = openai_compatible.OpenAICompatibleProvider(
            "https://api.openai.com/v1", "m", opener=recorder
        ).capabilities()
        self.assertIsNone(caps.ctx_len)
        self.assertEqual(caps.provenance["ctx_len"], "defaulted")


if __name__ == "__main__":
    unittest.main()
