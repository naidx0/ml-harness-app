import { For, Show } from "solid-js"
import { Block, Facts, Fold, Note, Pill } from "./frame"
import type { CarveCardData, SandboxResult, Synthesis, VerificationRecord, VerificationSample, WrittenFile } from "./readers"
import { baseName, bytes, count } from "./result"

/**
 * The tools that write to the person's disk, and the sandbox runs - parity
 * 5.20 (carve, synthesis, verification) and 5.12 (the Stage inline).
 *
 * Ported from the outgoing `CarveCard.tsx` and `SynthesisCard.tsx`. The first
 * thing each says is what was written and where, because these are the only
 * tools in the product that change files the person owns.
 */

function Written(props: { files: readonly WrittenFile[]; role?: string }) {
  return (
    <div class="flex flex-col gap-0.5">
      <For each={props.files}>
        {(file) => (
          <div class="flex flex-wrap items-center gap-x-3 text-12-regular">
            <Show when={props.role}>
              <span class="w-16 shrink-0 text-v2-text-text-muted">{props.role}</span>
            </Show>
            <span class="text-12-mono text-v2-text-text-base" title={file.path}>
              {file.file}
            </span>
            <span class="tabular-nums text-v2-text-text-muted">{count(file.rows)} rows</span>
            <span class="tabular-nums text-v2-text-text-faint">{bytes(file.bytes)}</span>
            <span class="text-12-mono text-v2-text-text-faint" title={file.sha256 ?? undefined}>
              {file.sha256 ? file.sha256.slice(0, 12) : "no digest"}
            </span>
          </div>
        )}
      </For>
    </div>
  )
}

export function CarveBody(props: { carve: CarveCardData }) {
  const c = () => props.carve
  const leaked = () => c().leakage?.leaked ?? null
  return (
    <>
      <div class="flex flex-wrap items-center gap-2">
        <Show
          when={c().leakage?.ran}
          fallback={<Pill tone="warn" title="check_split_leakage did not run on what this wrote.">NOT CHECKED</Pill>}
        >
          <Pill tone={leaked() ? "bad" : "good"}>{leaked() ? `${leaked()} rows leak` : "no leakage found"}</Pill>
        </Show>
        <span class="text-12-regular tabular-nums text-v2-text-text-muted">
          {count(c().evalRows)} eval rows · {count(c().trainRows)} train rows · from {count(c().rowsRead)} read
        </span>
      </div>
      <Show when={c().summary}>
        <p class="text-[13px] text-v2-text-text-base">{c().summary}</p>
      </Show>
      <Block title="Written" hint={c().into}>
        <Show
          when={c().wrote.length > 0}
          fallback={
            <Facts
              rows={[
                ["eval", c().evalPath],
                ["train", c().trainPath],
              ]}
            />
          }
        >
          <Written files={c().wrote} />
        </Show>
        <Show when={c().manifestPath}>
          <Note>How it was split, and the seed, are written beside them in {baseName(c().manifestPath!)}.</Note>
        </Show>
      </Block>
      <Show when={c().leakage && c().leakage!.examples.length > 0}>
        <Fold summary="Rows found on both sides" hint={`${c().leakage!.examples.length} shown`}>
          <div class="flex flex-col gap-0.5">
            <For each={c().leakage!.examples}>
              {(pair) => (
                <div class="flex flex-wrap gap-x-3 text-12-regular text-v2-text-text-muted">
                  <span class="tabular-nums">
                    train #{pair.trainRow ?? "?"} / eval #{pair.evalRow ?? "?"}
                  </span>
                  <Show when={pair.basis}>
                    <span>{pair.basis}</span>
                  </Show>
                  <Show when={pair.similarity !== null}>
                    <span class="tabular-nums">similarity {pair.similarity!.toFixed(2)}</span>
                  </Show>
                </div>
              )}
            </For>
          </div>
        </Fold>
      </Show>
      <Show when={c().leakage?.summary}>
        <Note tone={leaked() ? "bad" : "muted"}>{c().leakage!.summary}</Note>
      </Show>
      <Show when={c().method}>
        {(method) => <Facts rows={[["method", method().how], ["seed", method().seed], ["answer column", c().answerColumn]]} />}
      </Show>
      <Show when={c().gradingIsStillYours}>
        <Note>{c().gradingIsStillYours}</Note>
      </Show>
    </>
  )
}

export function SynthesisBody(props: { synthesis: Synthesis }) {
  const s = () => props.synthesis
  return (
    <>
      <Show when={s().summary}>
        <p class="text-[13px] text-v2-text-text-base">{s().summary}</p>
      </Show>
      <Note>
        Every one of these {count(s().rowsWritten)} rows carries synthetic: true, the row it was sampled from, and the seed
        that chose it. Nothing here opened a gate: the harness refuses to measure eval_size_n off a file it generated, and
        refuses to train on one until you have read a sample of it.
      </Note>
      <Block title="What was amplified" hint={`seed ${s().seed || "(none)"}`}>
        <Facts
          rows={[
            ["rows read", count(s().rowsRead)],
            ["answered rows", count(s().answeredRows)],
            ["rows written", count(s().rowsWritten)],
            ["answer column", s().answerColumn ?? "—"],
          ]}
        />
        <Note>
          {count(s().answeredRows)} real answered rows became {count(s().rowsWritten)} by sampling with replacement. The answer on
          every written row was copied from its source row and never generated.
        </Note>
      </Block>
      <Show when={s().wrote.length > 0}>
        <Block title="Written">
          <Written files={s().wrote} role="synthetic" />
        </Block>
      </Show>
      <Note>Before anything trains on this file, a person has to read 10% of it. Run draw_verification_sample on it.</Note>
    </>
  )
}

export function SampleBody(props: { sample: VerificationSample }) {
  const s = () => props.sample
  return (
    <>
      <Show when={s().summary}>
        <p class="text-[13px] text-v2-text-text-base">{s().summary}</p>
      </Show>
      <Block title="Your turn" hint={baseName(s().samplePath)}>
        <Facts
          rows={[
            ["rows written", count(s().rowsWritten)],
            ["rows total", count(s().rowsTotal)],
            ["seed", s().seed || "(none)"],
            ["file", s().samplePath],
          ]}
        />
        <Note>
          Open that file, put yes or no in the verified column of every row - yes if the answer on that row is right for that
          input - and run record_verification on it. Nothing here judged anything: this harness cannot tell whether a generated
          answer is right, which is the whole reason you are in this loop.
        </Note>
      </Block>
    </>
  )
}

export function VerificationBody(props: { record: VerificationRecord }) {
  const r = () => props.record
  return (
    <>
      <Show when={r().summary}>
        <p class="text-[13px] text-v2-text-text-base">{r().summary}</p>
      </Show>
      <Block title="What you recorded" hint={baseName(r().dataset)}>
        <Facts
          rows={[
            ["judged", count(r().judged)],
            ["wrong", count(r().wrong)],
          ]}
        />
        <Show
          when={r().wrong > 0}
          fallback={
            <Note>
              {baseName(r().dataset)} can be trained on. This record is bound to the file's exact bytes: rewrite the file and it
              stops applying.
            </Note>
          }
        >
          <Note tone="bad">
            Nothing will train on this file while the sample says some of it is wrong. Amplification copies answers verbatim,
            so a wrong generated row is a wrong source row.
          </Note>
        </Show>
      </Block>
    </>
  )
}

/**
 * The Stage inline, size S - parity 5.12. A compact line for a sandbox run;
 * the lattice, the loss curve and the gate map are the Stage's, one click away.
 */
export function SandboxBody(props: { run: SandboxResult }) {
  const r = () => props.run
  return (
    <>
      <div class="flex flex-wrap items-center gap-2">
        <Pill tone={r().ok ? (r().timedOut ? "warn" : "good") : "bad"}>
          {r().timedOut ? "timed out" : r().ok ? "ran" : r().exitCode !== null ? `exit ${r().exitCode}` : "did not run"}
        </Pill>
        <span class="text-12-mono text-v2-text-text-base">{r().sandbox}</span>
        <Show when={r().kind || r().recipe}>
          <span class="text-12-regular text-v2-text-text-muted">{[r().kind, r().recipe].filter(Boolean).join(" · ")}</span>
        </Show>
      </div>
      <Show when={r().says}>
        <Note>{r().says}</Note>
      </Show>
      <Facts
        rows={[
          ["adapter", r().adapter],
          ["base model", r().baseModel],
          ["network", r().egress === null ? null : r().egress ? "allowed" : "none"],
          ["run folder", r().runDir],
          ["log", r().logPath],
        ]}
      />
    </>
  )
}
