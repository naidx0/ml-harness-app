## Check, do not assume

Each of these is something people get wrong. The instruction is the same every
time: go and look, then carry on with what you found.

- **An eval set.** Most do not have one, and "we have examples" usually means a
  handful somebody remembers. Count it.
- **The labels.** If a trivial baseline matches the model, the task, the labels
  or the asking is broken. Find out which.
- **More data.** Ask what producing more would cost before planning around it.
- **The card.** Something else may be using it. Re-check before a run, not at
  intake.
- **"Fine-tune".** Ask what they mean by it. It is rarely what a paper means.
- **Where it runs.** Assume nothing about the deployment target until told.
- **The language.** Data is not always English, or one language.
- **Their reading.** They may not read a loss curve or say when they are lost.
  They will nod.
- **Benchmarks.** A published number does not transfer to their task, and a
  vendor's memory or speed figure was measured on newer hardware than this.
- **Fits vs trains.** Inference memory is not training memory: gradients,
  optimiser state and activations are not free.
- **Silence.** It is not agreement.
