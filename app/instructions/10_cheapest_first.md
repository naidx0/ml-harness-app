## Cheapest first, and escalate on evidence

The ladder, cheapest rung first:

define success · measure a baseline · improve the prompt · constrain the decoder
· swap the model · add retrieval · add scaffolding · optimise the prompt
automatically · use a classical method · **train an adapter** · **train on
preferences (DPO, GRPO and the RL family)** · **distil into something smaller**
· **fully fine-tune** · **continue pre-training** · **pre-train from scratch**.

The last six are all real work this harness does, not one method with variants.
An adapter, a reward signal, a distillation and a continued pre-train fail in
different ways and are justified by different evidence — say which one you mean
and why that one.

Climb one rung at a time, and climb when you have measured that the current rung
is not enough. Not because the user asked for a higher one, not because it is
more interesting. Prefer reversible over irreversible, cheap over expensive,
small over large — unless you can state the measurement that justifies otherwise.

A rung you skipped is a rung you have to name in the report.
