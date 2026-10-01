"""How much the model will accept, and how much we are about to send it.

## The defect this module exists to close

`app/providers/ollama.py` sent no `num_ctx`. The runtime context window was
therefore whatever the server happened to pick - 65,536 on the machine this was
found on, because a Modelfile said so, and 4,096 on a machine where nothing
does, which is Ollama's own default. The assembled system prompt measures 7,108
tokens on granite4-hermes's tokeniser and the 28 tool schemas add another 6,074,
so a turn puts **13,213 tokens** on the wire before the user has typed a word.

Ollama loses the excess **silently**, and it is worse than a straight overflow.
Sent that real 13,213-token turn against granite4-hermes on 127.0.0.1:11434,
measured by asking the server itself:

    num_ctx=  4,096 -> HTTP 200, no error, prompt_eval_count =  2,050
    num_ctx=  8,192 -> HTTP 200, no error, prompt_eval_count =  4,098
    num_ctx= 65,536 -> HTTP 200, no error, prompt_eval_count = 13,213

Half the window is reserved for generation, so a 4,096 window evaluates 2,050
tokens - **it keeps 15% of the prompt and answers cheerfully**. *Which* 2,050
survive is the server's business and was not measured here; what was measured is
that six sevenths of the instruction set did not reach the model and the
response carried no sign of it. A user on a default Ollama was getting a harness
missing most of its laws, with no way to tell which ones.

`tests/test_instruction_set.py` asserts that every non-negotiable law survives
assembly - it reads the ASSEMBLED STRING, in this process, and cannot see a
server discarding six sevenths of it at send time. That is this project's
recurring failure shape: a guarantee that holds where it is tested and not where
it is used.

## Two numbers, and they are not the same number

- **`ceiling`** - the most this model can ever accept. Ollama reports it as
  `model_info["<arch>.context_length"]`; it is a property of the weights.
- **`configured`** - the window the server will actually use if nobody says
  otherwise. Ollama reports it in `/api/show`'s `parameters` block as `num_ctx`
  when a Modelfile set one, and does not report it at all when the value is the
  server's own default.

The harness was reading the first and living in the second. `granite4-hermes`
reports a ceiling of 1,048,576 and a configured window of 65,536 - a factor of
sixteen between the number we could have read and the number we were subject to.

## Refuse rather than truncate

(2026-09-18: `app/observations.py` PACKS a large tool result - it rides whole
for two rounds, then as a handle and an excerpt that `read_observation` turns
back into the whole thing. That is not truncation: nothing is thrown away and
the door is named in the text. The rule below is about the prompt as a whole,
and it stands.)

`plan()` returns one of three shapes, and the third is the point:

- **fits** - send it, and when the adapter can name the window, name it. Never
  below what the user configured, never above the ceiling.
- **unknown** - send it, and say the budget is unknown. An unknown budget is a
  real state. It is not infinity and it is not a fit; nothing here is allowed
  to report it as either.
- **refused** - do not send. The user gets words.

The words matter and are written here rather than at the call site so both
adapters say the same thing. A person whose model cannot hold the instruction
set has one real move, and it is *not* the two moves this product must never
make: shipping fewer laws so it fits, or telling them to use a smaller model.
A smaller model has a smaller window more often than not. What they need is a
larger **window** - a different quantisation, a different context setting, or a
different model chosen for its context rather than its size - and in the
meantime every tool in this app is also a button and none of them need a model
at all.

## The estimate, and why it is allowed to be one

Neither Ollama nor the OpenAI-compatible endpoints expose a tokeniser. Ollama
0.32.5 answers `/api/tokenize` with a 404; the count arrives only as
`prompt_eval_count`, after the prompt has already been evaluated, which is one
round trip too late to refuse on.

So the pre-send count is inferred from length, and `CHARS_PER_TOKEN` is set
BELOW every ratio measured so the estimate errs high - a turn refused that would
have fitted is a bad day, a turn sent that silently loses the laws is the defect.
Measured on granite4-hermes: 35,348 characters of system prompt for 8,025 tokens,
a ratio of 4.41. The divisor here is 3.6, so the estimate for that prompt is
9,819 - 22% high.

Invariant 5 says never invent a number. An estimate is not an invention when it
is carried with its provenance and said out loud as an estimate, which is what
`Need.provenance` and `Need.source` are for, and why the refusal text says
"about".
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any


#: Deliberately below every ratio measured. See the module docstring: an
#: estimate that errs high refuses a turn that would have fitted; one that errs
#: low reintroduces the silent truncation this module exists to prevent.
CHARS_PER_TOKEN = 3.6

#: What a turn needs on top of the fixed prompt: the user's message, the tool
#: results that come back mid-turn, and the reply.
#:
#: THIS IS NOT PADDING, AND THE REASON IS A CLIFF. Ollama does not degrade
#: gracefully when a prompt exceeds the window - it truncates to half of it.
#: Measured against granite4-hermes with a 13,213-token turn:
#:
#:     num_ctx = 13,213 -> 6,609 evaluated   (half)
#:     num_ctx = 13,312 -> 13,213 evaluated  (whole)
#:
#: Ninety-nine tokens apart, and one of them loses six thousand. There is no
#: "slightly truncated" state to land in, so the margin has to be wide enough to
#: absorb both the estimator's error and a conversation that grows during a
#: turn. 4,096 is roughly a third of the current fixed cost.
WORKING_HEADROOM_TOKENS = 4096


@dataclass(frozen=True)
class Need:
    """How many tokens we are about to send, and how we came to that figure."""

    tokens: int
    provenance: str
    source: str

    @property
    def measured(self) -> bool:
        return self.provenance == "measured"


@dataclass(frozen=True)
class Budget:
    """What this connection will accept.

    `ceiling` is a hard limit. `configured` is what the server would use on its
    own. `settable` says whether this adapter can name the window on the
    request - Ollama can, through `options.num_ctx`; a hosted OpenAI-compatible
    endpoint cannot, and pretending otherwise would be an invented capability.
    """

    ceiling: int | None = None
    configured: int | None = None
    settable: bool = False
    provenance: str = "defaulted"
    source: str = "nothing was asked and nothing answered"

    @property
    def known(self) -> bool:
        """Do we know anything at all about the room we have?

        `False` is not "no room". It is "no idea", and the two must stay
        distinguishable - collapsing them is how an unknown budget starts being
        treated as an infinite one.
        """
        return _positive(self.ceiling) or _positive(self.configured)


#: What a connection whose window nobody could establish looks like.
UNKNOWN = Budget()


@dataclass(frozen=True)
class Plan:
    """What to do with one turn, decided before a byte is sent.

    `request` is the window to ask the server for, or `None` when this adapter
    cannot ask. `refusal` is empty unless `verdict` is `"refused"`.
    """

    verdict: str
    request: int | None = None
    refusal: str = ""

    @property
    def send(self) -> bool:
        return self.verdict != "refused"


def billable(
    wire: list[dict[str, Any]] | None, tools: list[dict[str, Any]] | None
) -> list[str]:
    """Everything that will occupy the window, as strings to be counted.

    THE TOOL SCHEMAS ARE IN HERE because they are on the wire, and they are the
    half that gets forgotten. Twenty-eight of them cost 6,074 tokens against
    granite4-hermes, next to the system prompt's 7,108 - not far off half of
    everything a turn spends before the user has typed a word, and a great deal
    more than "some JSON" suggests. A budget check that counted only the
    messages would have declared a fit for a request that does not fit.

    Both adapters share this because both send the same three things under
    different field names, and a second copy of the counting is a second place
    for one of them to be forgotten.
    """
    chunks: list[str] = []
    for message in wire or ():
        if not isinstance(message, dict):
            continue
        chunks.append(str(message.get("role") or ""))
        chunks.append(str(message.get("content") or ""))
        calls = message.get("tool_calls")
        if calls:
            chunks.append(json.dumps(calls, default=str))
    if tools:
        chunks.append(json.dumps(tools, default=str))
    return chunks


def estimate(*chunks: str) -> Need:
    """Tokens for some strings, inferred from their length.

    Whole characters, then a ceiling divide, so a short string never estimates
    at zero tokens.
    """
    characters = sum(len(chunk or "") for chunk in chunks)
    tokens = int(math.ceil(characters / CHARS_PER_TOKEN))
    return Need(
        tokens=tokens,
        provenance="inferred",
        source=(
            f"estimated from {characters:,} characters at {CHARS_PER_TOKEN} "
            "characters per token, because this endpoint exposes no tokeniser"
        ),
    )


def plan(
    need: Need,
    budget: Budget,
    *,
    model: str = "",
    headroom: int = WORKING_HEADROOM_TOKENS,
) -> Plan:
    """Decide whether this turn goes, and with what window.

    The order is the argument:

    1. If the ceiling is known and cannot hold the prompt plus room to work,
       **refuse**. There is nothing to negotiate: the adapter has already asked
       for everything the model has.
    2. If the adapter can name the window, name it - the larger of what we need
       and what the user configured, never above the ceiling. Never lower what
       somebody deliberately set, because their reason for setting it is not
       ours to overrule.
    3. Otherwise send, and let the caller say whether the budget was known.

    ## Why asking for what we need is not a cap, and must not be "fixed" into one

    Where the configured window is invisible - Ollama's `OLLAMA_CONTEXT_LENGTH`
    is an environment variable that `/api/show` does not report - step 2 asks for
    `need + headroom` and that can be below what the user set. That looks like
    lowering a ceiling and it is not, because `need` is recomputed every turn
    over the whole conversation: the window we ask for grows as the conversation
    does, and always carries the headroom with it.

    The alternative - asking for the model's ceiling so as never to lower
    anything - allocates a KV cache for 1,048,576 tokens on a 6.9B model. That
    is not caution, it is an out-of-memory error dressed as caution.
    """
    required = need.tokens + max(0, int(headroom))

    ceiling = _int_or_none(budget.ceiling)
    if ceiling is not None and required > ceiling:
        return Plan(
            verdict="refused",
            refusal=refusal(need, budget, model=model, headroom=headroom),
        )

    if not budget.settable:
        return Plan(verdict="fits" if budget.known else "unknown")

    configured = _int_or_none(budget.configured) or 0
    wanted = max(required, configured)
    if ceiling is not None:
        wanted = min(wanted, ceiling)
    return Plan(verdict="fits" if budget.known else "unknown", request=wanted)


def refusal(
    need: Need,
    budget: Budget,
    *,
    model: str = "",
    headroom: int = WORKING_HEADROOM_TOKENS,
) -> str:
    """What the user is told when the turn does not go.

    Plain words, the two numbers, and the move that is actually available. The
    two moves this product must never offer are absent on purpose: it does not
    ship fewer laws to fit, and it does not tell somebody to fetch a smaller
    model - parameter count and context window are different axes and a smaller
    model usually has a smaller window.
    """
    who = f"`{model}`" if model else "the model you connected"
    ceiling = _int_or_none(budget.ceiling)
    room = f"{ceiling:,}" if ceiling is not None else "less than that"
    about = "about " if not need.measured else ""
    return (
        f"I did not send this turn, because it would not have arrived whole. "
        f"This harness's instruction set plus room to work needs {about}"
        f"{need.tokens + max(0, int(headroom)):,} tokens and {who} can hold "
        f"{room}. Sending it anyway is not a smaller answer - the end of the "
        f"prompt is simply dropped, with no error, and the laws that stop this "
        f"product agreeing you should fine-tune are part of what falls off. "
        f"What fixes it is a larger context window, which is not the same thing "
        f"as a larger model: raise this model's window if its weights allow it, "
        f"or connect one chosen for its context. Nothing here is blocked in the "
        f"meantime - every tool in this app is also a button, and none of them "
        f"need a model. ({need.source}; {budget.source}.)"
    )


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _int_or_none(value: object) -> int | None:
    return int(value) if _positive(value) else None
