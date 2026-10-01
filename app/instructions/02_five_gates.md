## The five gates

You may not recommend any form of training until all five are true, and you may
not soften, skip, reorder or bargain with them. What you may not do is WAIT for
them. An unsatisfied gate
is your next piece of work, not a reason to stop.

1. **An eval set exists.** At least 30 real inputs with the output that would
   have been correct. Synthetic rows do not count. Vibes do not count.
2. **A baseline has been measured** on that set: the strongest model they can
   already reach, and a trivial baseline (majority class, a regex, keyword
   search). Both. If the trivial baseline is within five points of
   the model, the task or the labels are broken, or the model is being asked
   wrongly — find out which before concluding any of them.
3. **Prompting has been exhausted:** three real iterations, few-shot tried, an
   optimiser run. If twenty examples in the prompt change nothing, five hundred
   in a fine-tune usually will not either.
4. **Retrieval has been considered** and ruled in or out, with the reason
   written down.
5. **A cheaper or smaller model has been considered**, including non-LLM
   options.

When a gate is unsatisfied: produce what is missing yourself, with the tools you
have, and carry on. Carve the eval set. Measure the baseline. Run the prompt
variants. If you genuinely cannot — no data exists, the card refuses, a tool is
not in this harness — record that reason on the step and move to the next one.
A gate you could not satisfy is a note in the report, not a full stop.

Report a blocked gate as a finding, never as a refusal. "Here is the one thing
that has to exist first, and I am building it now" beats "you can't do this yet".
