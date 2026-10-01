/**
 * The Stage — one instrument surface, five panels, three sizes.
 *
 * docs/PHASES.md "The Stage". Drawn first as the artifact "Basilica Overview
 * Components" on thread 33's real runs; this file is that drawing as a
 * component. Everything it shows arrives in one `StagePayload` from
 * `GET /api/threads/{id}/stage` (app/stage.py) — rows per run, the paired
 * verdicts, the sandboxes and their run logs, the card, the diagnosis — plus
 * the recall and carve results the transcript already folds. It computes no
 * statistic: every p-value, delta and resolution is the engine's, quoted with
 * its run id.
 *
 * THE HUE BUDGET OF THIS SURFACE, counted the way styles/datawork.css counts
 * its own. Green (--fits) is "judged right", PASSED, and the target rule.
 * Red (--wont) is "flipped down", the card's measured-memory rule, and a
 * refusal. Amber (--spills) is a DEFAULTED tag. Blue (--info) is a running
 * state. Gold is the selected run and nothing else. Cobalt appears nowhere in
 * this file: the Stage never needs you — it is a thing you look at. Series
 * colours on the two charts come from the viz namespace, which the design
 * system keeps apart from the claim colours on purpose.
 */

import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import type { Carve } from '../lib/engine/datawork';
import type { FactOrigin } from '../lib/engine/facts';
import type { RecallReport } from '../lib/engine/retrieval';
import {
  runLabel,
  type StageComparison,
  type StagePayload,
  type StageRun,
  type StageSandbox,
  type StageSandboxRun,
} from '../lib/engine/stage';
import type { GateStatus } from '../lib/engine/types';
import {
  STAGE_PANELS,
  STAGE_PANEL_TITLE,
  type StageAction,
  type StagePanelId,
  type StageSize,
  type StageState,
} from '../lib/stageState';
import { Icon, type IconName } from './Icon';
import { GateBadge, OriginTag, StatusDot } from './primitives';
import './Stage.css';

const PANEL_ICON: Record<StagePanelId, IconName> = {
  bench: 'run',
  sandbox: 'commit',
  progression: 'chart',
  gates: 'gauge',
  retrieval: 'search',
};

/* ── formatting ─────────────────────────────────────────────────────────── */

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`;
}

function points(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '—' : value.toFixed(digits);
}

function secondsLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 90) return `${Math.round(seconds)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function shortModel(model: string | null): string {
  if (!model) return '—';
  return model.replace(/^.*\//, '').replace(':latest', '');
}

/** The eval run the Stage is showing: the picked one, or the newest complete. */
export function currentRun(payload: StagePayload, runId: number | null): StageRun | null {
  if (runId !== null) {
    const picked = payload.runs.find((run) => run.run_id === runId);
    if (picked) return picked;
  }
  for (let i = payload.runs.length - 1; i >= 0; i -= 1) {
    if (payload.runs[i].complete) return payload.runs[i];
  }
  return payload.runs[payload.runs.length - 1] ?? null;
}

function targetOf(payload: StagePayload): { value: number; origin: FactOrigin } | null {
  const facts = (payload.diagnosis?.facts ?? []) as Array<{ fact: string; value: unknown; origin: string }>;
  const fact = facts.find((f) => f.fact === 'target_score');
  if (!fact || typeof fact.value !== 'number') return null;
  return { value: fact.value, origin: (fact.origin as FactOrigin) ?? 'DEFAULTED' };
}

/* ── the surface ────────────────────────────────────────────────────────── */

export function Stage({
  payload,
  state,
  dispatch,
  size,
  recall,
  carve,
  controls,
  loading,
  error,
}: {
  payload: StagePayload | null;
  state: StageState;
  dispatch: (action: StageAction) => void;
  size: StageSize;
  /** Every recall report in the transcript, newest first, and the newest
   *  carve. The Retrieval panel lets the person pick which index to read;
   *  a thread with two indexes is two measurements, not one. */
  recall: RecallReport | RecallReport[] | null;
  carve: Carve | null;
  /** Size controls the host supplies: detach, split, close. */
  controls?: ReactNode;
  loading?: boolean;
  error?: string | null;
}) {
  const run = payload ? currentRun(payload, state.runId) : null;
  const tabsRef = useRef<HTMLElement>(null);
  const [canScroll, setCanScroll] = useState({ left: false, right: false });

  const updateScroll = () => {
    const el = tabsRef.current;
    if (!el) {
      setCanScroll({ left: false, right: false });
      return;
    }
    const max = el.scrollWidth - el.clientWidth;
    setCanScroll({
      left: el.scrollLeft > 2,
      right: max > 2 && el.scrollLeft < max - 2,
    });
  };

  useLayoutEffect(() => {
    updateScroll();
    const el = tabsRef.current;
    if (!el) return;
    const onScroll = () => updateScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(updateScroll) : null;
    ro?.observe(el);
    window.addEventListener('resize', updateScroll);
    return () => {
      el.removeEventListener('scroll', onScroll);
      ro?.disconnect();
      window.removeEventListener('resize', updateScroll);
    };
  }, [state.panel, size]);

  return (
    <section className="stage" data-size={size} aria-label={`Stage — ${STAGE_PANEL_TITLE[state.panel]}`}>
      <header className="stage__head">
        <span className="stage__mark">
          <Icon name="panelleft" />
          <span className="stage__title">Stage</span>
          {/* "· Data" WAS HERE AND SAID NOTHING THE TABS DO NOT. Max,
              2026-09-20, with a photo of it wrapping under the word Stage:
              "the descriptive mini underline text like data and run or
              selected seems repetitive and causes more and more issues with
              formatting, spacing and overlapping". The tab rail beside it
              already names the panel, and naming the surface twice is what
              pushed the rail into a second line. */}
        </span>
        <div className="stage__tabs-wrap">
          {canScroll.left ? (
            <button
              type="button"
              className="stage__tabs-arrow"
              aria-label="Earlier Stage panels"
              onClick={() => tabsRef.current?.scrollBy({ left: -120, behavior: 'smooth' })}
            >
              <Icon name="chevright" size={12} rotate={180} />
            </button>
          ) : null}
          <nav ref={tabsRef} className="stage__tabs" aria-label="Stage panels">
            {STAGE_PANELS.map((panel) => (
              <button
                key={panel}
                type="button"
                className="stage__tab"
                aria-current={panel === state.panel || undefined}
                onClick={() => dispatch({ type: 'panel', panel })}
              >
                <Icon name={PANEL_ICON[panel]} />
                <span>{STAGE_PANEL_TITLE[panel]}</span>
              </button>
            ))}
          </nav>
          {canScroll.right ? (
            <button
              type="button"
              className="stage__tabs-arrow"
              aria-label="More Stage panels"
              onClick={() => tabsRef.current?.scrollBy({ left: 120, behavior: 'smooth' })}
            >
              <Icon name="chevright" size={12} />
            </button>
          ) : null}
        </div>
        <span className="stage__controls">{controls}</span>
      </header>

      {payload ? (
        <RunStrip payload={payload} selected={run?.run_id ?? null} onPick={(id) => dispatch({ type: 'pick', runId: id })} />
      ) : null}

      <div className="stage__body">
        {error ? (
          <p className="stage__empty">The Stage could not read this thread: {error}</p>
        ) : !payload ? (
          <p className="stage__empty">{loading ? 'Reading the thread…' : 'Nothing measured in this thread yet.'}</p>
        ) : state.panel === 'bench' ? (
          <BenchPanel payload={payload} selected={run} />
        ) : state.panel === 'sandbox' ? (
          <SandboxPanel payload={payload} />
        ) : state.panel === 'progression' ? (
          <ProgressionPanel payload={payload} />
        ) : state.panel === 'gates' ? (
          <GatesPanel payload={payload} />
        ) : (
          <RetrievalPanel recalls={recall === null ? [] : Array.isArray(recall) ? recall : [recall]} carve={carve} payload={payload} />
        )}
      </div>
    </section>
  );
}

/* ── run strip: the selection, gold, shared by every size ───────────────── */

function RunStrip({
  payload,
  selected,
  onPick,
}: {
  payload: StagePayload;
  selected: number | null;
  onPick: (runId: number) => void;
}) {
  if (payload.runs.length === 0) return null;
  return (
    <div className="stage__runs" role="listbox" aria-label="Eval runs">
      {payload.runs.map((run) => (
        <button
          key={run.run_id}
          type="button"
          role="option"
          aria-selected={run.run_id === selected}
          className="stage__run"
          data-selected={run.run_id === selected || undefined}
          title={`${run.model ?? ''} · ${run.metric}`}
          onClick={() => onPick(run.run_id)}
        >
          <span className="stage__runid">{run.run_id}</span>
          <span>{runLabel(run, payload.baseline_run_id)}</span>
          <span className="stage__runscore">{run.complete ? pct(run.score) : `${run.graded}/${run.planned}`}</span>
        </button>
      ))}
    </div>
  );
}

/* ── 1 · Bench ──────────────────────────────────────────────────────────── */

function BenchPanel({ payload, selected }: { payload: StagePayload; selected: StageRun | null }) {
  const baseline = payload.runs.find((run) => run.run_id === payload.baseline_run_id) ?? null;
  const baseFail = useMemo(
    () => new Set((baseline?.rows ?? []).filter((r) => !r.correct).map((r) => r.row_index)),
    [baseline],
  );
  const width = Math.max(0, ...payload.runs.map((run) => run.planned));
  const indexes = Array.from({ length: width }, (_, i) => i);
  const paired = selected ? payload.comparisons[String(selected.run_id)] ?? null : null;
  const target = targetOf(payload);

  return (
    <div className="stage__grid stage__grid--bench">
      <div>
        <div className="lattice" style={{ ['--cols' as string]: String(width) }}>
          <div className="lattice__label" />
          {indexes.map((i) => (
            <div key={i} className="lattice__hdr">{i}</div>
          ))}
          {payload.runs.map((run) => {
            const graded = new Map(run.rows.map((r) => [r.row_index, r.correct]));
            return [
              <div key={`l${run.run_id}`} className="lattice__label" data-selected={run.run_id === selected?.run_id || undefined}>
                {runLabel(run, payload.baseline_run_id)}
                <span className="lattice__id">{run.run_id}</span>
              </div>,
              ...indexes.map((i) => {
                const verdict = graded.get(i);
                const held = verdict === undefined;
                let flip: 'up' | 'down' | null = null;
                if (!held && baseline && run.run_id !== baseline.run_id) {
                  const wasWrong = baseFail.has(i);
                  if (wasWrong && verdict) flip = 'up';
                  else if (!wasWrong && !verdict) flip = 'down';
                }
                return (
                  <div
                    key={`${run.run_id}-${i}`}
                    className="lattice__cell"
                    data-held={held || undefined}
                    data-ok={!held && verdict ? true : undefined}
                    data-flip={flip ?? undefined}
                    title={held ? `run ${run.run_id} row ${i}: not graded` : `run ${run.run_id} row ${i}: ${verdict ? 'right' : 'wrong'}`}
                  />
                );
              }),
            ];
          })}
        </div>
        <div className="stage__legend">
          <span><i className="stg-lg stg-lg--ok" />judged right</span>
          <span><i className="stg-lg" />judged wrong</span>
          <span><i className="stg-lg stg-lg--held" />not graded</span>
          <span><i className="stg-lg stg-lg--up" />flipped up vs baseline {payload.baseline_run_id ?? '—'}</span>
          <span><i className="stg-lg stg-lg--down" />flipped down</span>
        </div>
      </div>
      <aside className="stage__side">
        {/* ONE LINE WHEN NOTHING IS SELECTED, NOT TWO EMPTY ONES. Max,
            2026-09-19: "selected run shouldn't have like a no target stated
            under it, no reason to use that." With no selection the panel
            printed "selected · run —" and "no target stated" as two stacked
            eyebrows with 18px of dead air and no content between them: two
            absences where the answer is one instruction. */}
        {/* `selected · run 12` SAID SELECTED TWICE: the lattice above already
            marks the pick in gold, and this panel exists only for it. Same
            correction as the line below - the eyebrow names the thing, and the
            state is carried by colour. */}
        <div className="stage__eyebrow">
          {selected
            ? `run ${selected.run_id}${paired ? ` vs ${paired.against}` : ''}`
            : 'no run selected · pick one in the lattice'}
        </div>
        {selected ? (
          <dl className="stage__kv">
            <dt>model</dt><dd>{shortModel(selected.model)}</dd>
            <dt>judged by</dt><dd>{selected.judge_model ? shortModel(selected.judge_model) : selected.metric}</dd>
            <dt>score</dt><dd>{pct(selected.score)} <span className="stage__unit">{selected.correct} of {selected.graded}</span></dd>
            {selected.resolution ? (
              <>
                <dt>95% interval</dt>
                <dd>{pct(selected.resolution.ci_95[0])}–{pct(selected.resolution.ci_95[1])}</dd>
                <dt>resolves</dt>
                <dd>≥{points(selected.resolution.resolves_a_difference_of_at_least_points, 0)} pts</dd>
              </>
            ) : null}
            {paired ? (
              <>
                <dt>improved</dt><dd className="stage__good">{paired.improved}</dd>
                <dt>regressed</dt><dd className="stage__bad">{paired.regressed}</dd>
                <dt>McNemar p</dt><dd>{points(paired.p_value, 3)}</dd>
                <dt>verdict</dt>
                <dd><span className="vpill" data-verdict={paired.verdict}>{paired.verdict === 'different' ? 'DIFFERENT' : 'NO EVIDENCE'}</span></dd>
                {paired.rows_that_would_resolve_this_delta ? (
                  <>
                    <dt>rows to resolve</dt><dd>{paired.rows_that_would_resolve_this_delta}</dd>
                  </>
                ) : null}
              </>
            ) : null}
          </dl>
        ) : null}
        {/* The bar is drawn when there IS one. "no target stated" is a row
            about a thing that is not there, under a run that is not there. */}
        {target ? (
          /* THE VALUE IS THE ROW, AND THE ORIGIN IS ITS COLOUR. It read
             `the bar you set · 70% STATED`: five words of label, one number,
             and an uppercase pill - three typographic registers on one 10px
             line, which is what Max photographed. Now the number is the size
             of a number, the origin is the dot beside it in the same colour
             its pill would be, and the card's left edge carries that colour
             too. Hover or a screen reader still gets the word. */
          <div className="stage__bar" data-origin={target.origin}>
            <span className="stage__bar-label">bar set</span>
            <span className="stage__bar-value">{pct(target.value)}</span>
            <OriginTag origin={target.origin} compact />
          </div>
        ) : null}
        <ScoreBars payload={payload} target={target?.value ?? null} selected={selected?.run_id ?? null} />
      </aside>
      <ReadingBand items={benchReading(payload, selected, paired, target?.value ?? null)} />
      <GlossaryLine panel="bench" />
    </div>
  );
}

function ScoreBars({ payload, target, selected }: { payload: StagePayload; target: number | null; selected: number | null }) {
  const runs = payload.runs.filter((run) => run.complete && run.score !== null);
  const sorted = [...runs].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  return (
    <div className="stg-bars">
      {sorted.map((run) => (
        <div key={run.run_id} className="stg-bars__row" data-selected={run.run_id === selected || undefined}>
          <span className="stg-bars__label">{runLabel(run, payload.baseline_run_id)} <span className="lattice__id">{run.run_id}</span></span>
          <span className="stg-bars__track">
            <i className="stg-bars__fill" data-kind={/adapter/i.test(run.model ?? '') ? 'trained' : run.run_id === payload.baseline_run_id ? 'control' : 'prompt'} style={{ width: `${Math.round((run.score ?? 0) * 100)}%` }} />
            {target !== null ? <b className="stg-bars__target" style={{ left: `${Math.round(target * 100)}%` }} /> : null}
          </span>
          <span className="stg-bars__num">{pct(run.score)}</span>
        </div>
      ))}
    </div>
  );
}

/* ── 2 · Sandbox ────────────────────────────────────────────────────────── */

function SandboxPanel({ payload }: { payload: StagePayload }) {
  const gpu = payload.gpu;
  const occ = gpu.occupancy;
  const boxes = payload.sandboxes.filter((box) => box.ok !== false);
  const resident = occ?.resident ?? [];
  const usedPct = occ ? Math.min(100, Math.round((occ.used_gb / occ.total_gb) * 100)) : 0;
  return (
    <div className="stage__grid stage__grid--two">
      <div>
        {boxes.length === 0 ? <p className="stage__empty">No sandbox in this project yet.</p> : null}
        {boxes.map((box) => (
          <SandboxCard key={box.name} box={box} />
        ))}
      </div>
      <aside className="stage__side">
        <div className="stage__eyebrow">the card, now</div>
        {occ ? (
          <>
            <dl className="stage__kv">
              <dt>GPU memory</dt>
              <dd>{points(occ.used_gb)} <span className="stage__unit">of {points(occ.total_gb)} GB</span> <OriginTag origin="MEASURED" /></dd>
            </dl>
            <div className="vram" title={occ.source}>
              <i className="vram__used" style={{ width: `${usedPct}%` }} />
              <b className="vram__cap" />
            </div>
            <div className="stage__legend">
              <span><i className="stg-lg stg-lg--viz1" />in use</span>
              <span><i className="stg-lg stg-lg--cap" />{points(occ.total_gb)} GB, measured</span>
            </div>
            <dl className="stage__kv" style={{ marginTop: 'var(--sp-8)' }}>
              <dt>resident models</dt>
              <dd>{resident.length === 0 ? 'none' : resident.map((m) => `${m.name} (${m.size_gb} GB)`).join(', ')}</dd>
              <dt>guard</dt>
              <dd className={gpu.guard ? 'stage__bad' : 'stage__good'}>{gpu.guard ? 'crowded — a training run is refused' : 'card free — a run is allowed'}</dd>
            </dl>
            {gpu.guard ? <p className="stage__note">{gpu.guard}</p> : null}
          </>
        ) : (
          <p className="stage__empty">No NVIDIA card answered. The guard has nothing to read.</p>
        )}
      </aside>
      <ReadingBand items={sandboxReading(payload)} />
      <GlossaryLine panel="sandbox" />
    </div>
  );
}

function SandboxCard({ box }: { box: StageSandbox }) {
  const pinned = box.pinned ?? {};
  return (
    <div className="sbox">
      <div className="sbox__head">
        <span className="sbox__name">{box.name}</span>
        <span className="stage__eyebrow">{pinned.recipe ?? 'no recipe'}{pinned.pinned ? ' · pinned' : ''}{box.reach?.egress ? ' · egress on' : ' · no egress'}</span>
        <span className="sbox__runs"><StatusDot role="st-done" shape="filled" />{box.runs.length} run{box.runs.length === 1 ? '' : 's'}</span>
      </div>
      {box.purpose ? <p className="sbox__purpose">{box.purpose}</p> : null}
      <div className="sbox__cols">
        <div>
          <div className="stage__eyebrow">pinned</div>
          <dl className="stage__kv">
            <dt>interpreter</dt><dd>{pinned.interpreter ? pinned.interpreter.replace(/^.*[\\/]recipes[\\/]/, 'recipes/') : '—'}</dd>
            <dt>environment on disk</dt><dd>{pinned.on_disk_gb !== undefined ? <>{points(pinned.on_disk_gb, 2)} <span className="stage__unit">GB</span> <OriginTag origin="MEASURED" /></> : '—'}</dd>
          </dl>
          <div className="stage__eyebrow" style={{ marginTop: 'var(--sp-8)' }}>snapshotted</div>
          <dl className="stage__kv">
            {(box.snapshotted ?? []).map((snap) => (
              <FragmentRow key={snap.path} name={snap.path.replace(/^.*[\\/]/, '')} value={`${(snap.bytes / 1024).toFixed(1)} KB`} digest={snap.digest.slice(0, 12)} />
            ))}
          </dl>
        </div>
        <div>
          <div className="stage__eyebrow">runs inside</div>
          {box.runs.length === 0 ? <p className="stage__empty">none yet</p> : null}
          {box.runs.map((run) => (
            <SandboxRunRow key={run.name} run={run} />
          ))}
        </div>
      </div>
    </div>
  );
}

function FragmentRow({ name, value, digest }: { name: string; value: string; digest: string }) {
  return (
    <>
      <dt>{name}</dt>
      <dd>{value} <span className="stage__digest">{digest}</span></dd>
    </>
  );
}

function SandboxRunRow({ run }: { run: StageSandboxRun }) {
  const spending = run.kind === 'train' || run.kind === 'eval';
  return (
    <div className="srun">
      <span className="srun__id">{run.name}</span>
      <span className="srun__what">
        <StatusDot role="st-done" shape="filled" />
        {run.kind ?? '—'}{run.max_steps ? ` · ${run.max_steps} steps` : ''}{run.base_model ? ` · ${shortModel(run.base_model)}` : ''}
      </span>
      <span className="srun__el" data-spending={spending || undefined}>{secondsLabel(run.elapsed_seconds)}</span>
      <span className="srun__vram">{run.peak_vram_gb !== null ? `${points(run.peak_vram_gb, 2)} GB peak` : ''}</span>
    </div>
  );
}

/* ── 3 · Progression ────────────────────────────────────────────────────── */

function trainRuns(payload: StagePayload): Array<{ box: string; run: StageSandboxRun }> {
  const out: Array<{ box: string; run: StageSandboxRun }> = [];
  for (const box of payload.sandboxes) {
    for (const run of box.runs) {
      if (run.kind === 'train' && run.curve.length > 1) out.push({ box: box.name, run });
    }
  }
  return out;
}

function LossChart({ series }: { series: Array<{ box: string; run: StageSandboxRun }> }) {
  const W = 520;
  const H = 220;
  const L = 40;
  const B = 190;
  const T = 16;
  const maxStep = Math.max(1, ...series.map((s) => s.run.curve[s.run.curve.length - 1].step));
  const losses = series.flatMap((s) => s.run.curve.map((p) => p.loss));
  const maxLoss = Math.max(1, ...losses);
  const minLoss = Math.min(0, ...losses);
  const x = (step: number) => L + ((W - L - 10) * step) / maxStep;
  const y = (loss: number) => B - ((B - T) * (loss - minLoss)) / (maxLoss - minLoss || 1);
  const ticks = 4;
  return (
    <svg className="stg-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Training loss by step">
      {Array.from({ length: ticks + 1 }, (_, i) => {
        const v = minLoss + ((maxLoss - minLoss) * i) / ticks;
        return (
          <g key={i}>
            <line className="stg-chart__grid" x1={L} x2={W - 10} y1={y(v)} y2={y(v)} />
            <text className="stg-chart__tick" x={L - 6} y={y(v) + 3} textAnchor="end">{v.toFixed(1)}</text>
          </g>
        );
      })}
      <line className="stg-chart__axis" x1={L} x2={L} y1={T} y2={B} />
      <line className="stg-chart__axis" x1={L} x2={W - 10} y1={B} y2={B} />
      <text className="stg-chart__tick" x={L} y={H - 6}>0</text>
      <text className="stg-chart__tick" x={W - 10} y={H - 6} textAnchor="end">{maxStep} steps</text>
      {series.map((s, i) => (
        <polyline
          key={s.run.name}
          className="stg-chart__line"
          data-series={i === 0 ? 'a' : i === 1 ? 'b' : 'c'}
          points={s.run.curve.map((p) => `${x(p.step).toFixed(1)},${y(p.loss).toFixed(1)}`).join(' ')}
        />
      ))}
    </svg>
  );
}

function ProgressionPanel({ payload }: { payload: StagePayload }) {
  const series = trainRuns(payload).slice(0, 3);
  const target = targetOf(payload);
  const adapters = payload.runs.filter((run) => run.complete && /adapter/i.test(run.model ?? ''));
  const baseline = payload.runs.find((run) => run.run_id === payload.baseline_run_id) ?? null;
  return (
    <div className="stage__grid stage__grid--two">
      <div>
        {series.length === 0 ? (
          <p className="stage__empty">No training run with a loss curve in this project's sandboxes.</p>
        ) : (
          <>
            <LossChart series={series} />
            <div className="stage__legend">
              {series.map((s, i) => (
                <span key={s.run.name}>
                  <i className={`stg-lg stg-lg--line stg-lg--${i === 0 ? 'a' : i === 1 ? 'b' : 'c'}`} />
                  {s.box}/{s.run.name} · {s.run.steps ?? s.run.max_steps ?? '?'} steps · {secondsLabel(s.run.elapsed_seconds)}
                  {s.run.final_loss !== null ? ` · final loss ${points(s.run.final_loss, 2)}` : ''}
                </span>
              ))}
            </div>
          </>
        )}
      </div>
      <aside className="stage__side">
        <div className="stage__eyebrow">held-out, same judge, same rows</div>
        <dl className="stage__kv">
          {baseline ? (<><dt>baseline · {baseline.run_id}</dt><dd>{pct(baseline.score)}</dd></>) : null}
          {adapters.map((run) => {
            const paired = payload.comparisons[String(run.run_id)];
            return (
              <FragmentRow2 key={run.run_id} label={`${shortModel(run.model)} · ${run.run_id}`} value={pct(run.score)} delta={paired ? paired.delta : null} />
            );
          })}
        </dl>
        {target ? (
          <div className="stage__eyebrow" style={{ marginTop: 'var(--sp-8)' }}>target {pct(target.value)} <OriginTag origin={target.origin} /></div>
        ) : null}
      </aside>
      <ReadingBand items={progressionReading(series, adapters, baseline)} />
      <GlossaryLine panel="progression" />
    </div>
  );
}

function FragmentRow2({ label, value, delta }: { label: string; value: string; delta: number | null }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        {value}
        {delta !== null ? (
          <span className={delta < 0 ? 'stage__bad' : delta > 0 ? 'stage__good' : ''}> {delta < 0 ? '▾' : '▴'}{Math.abs(Math.round(delta * 100))}</span>
        ) : null}
      </dd>
    </>
  );
}

/* ── 4 · Gates ──────────────────────────────────────────────────────────── */

const GATE_ORDER = ['G0_EVAL_SET', 'G1_BASELINE_MEASURED', 'G2_PROMPT_EXHAUSTED', 'G3_RETRIEVAL_CONSIDERED', 'G4_CHEAPER_MODEL_CONSIDERED'];
const GATE_NAME: Record<string, string> = {
  G0_EVAL_SET: 'Eval set exists',
  G1_BASELINE_MEASURED: 'Baseline measured',
  G2_PROMPT_EXHAUSTED: 'Prompting exhausted',
  G3_RETRIEVAL_CONSIDERED: 'Retrieval considered',
  G4_CHEAPER_MODEL_CONSIDERED: 'Cheaper model considered',
};

/** A fact's value as the ledger would print it: whole numbers as they are,
 *  fractions to three places (0.133, not 0.13333333333333333), objects as
 *  `key count` pairs rather than JSON. */
function factValue(value: unknown): string {
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k} ${typeof v === 'number' ? v : String(v)}`)
      .join(' · ');
  }
  return String(value);
}

function gateStatus(raw: string | undefined): GateStatus {
  if (raw === 'PASSED') return 'PASSED';
  if (raw === 'FAILED' || raw === 'NOT_MET') return 'NOT_MET';
  return 'NOT_CHECKED';
}

function GatesPanel({ payload }: { payload: StagePayload }) {
  const report = payload.diagnosis as { verdict?: { outcome?: string; say?: string | null; gates?: Record<string, { status?: string; clause?: string | null }> }; facts?: Array<{ fact: string; value: unknown; origin: string; tool?: string; how?: string }> } | null;
  const gates = report?.verdict?.gates ?? {};
  const facts = report?.facts ?? [];
  const passed = GATE_ORDER.filter((g) => gates[g]?.status === 'PASSED').length;
  if (!report) return <p className="stage__empty">No diagnosis in this thread yet.</p>;
  return (
    <div className="stage__grid stage__grid--one">
      <div className="stg-gates__head">
        <span className="vpill" data-verdict={report.verdict?.outcome?.startsWith('NO_TRAIN') ? 'info' : report.verdict?.outcome?.startsWith('TRAIN') ? 'fits' : 'unknown'}>{report.verdict?.outcome ?? '—'}</span>
        <span className="stage__eyebrow">{passed} of {GATE_ORDER.length} gates passed</span>
      </div>
      <div className="stg-gates">
        {GATE_ORDER.map((g, i) => (
          <div key={g} className="stg-gate" data-status={gateStatus(gates[g]?.status)}>
            <div className="stg-gate__node">{i}</div>
            <div className="stg-gate__name">{GATE_NAME[g]}</div>
            <GateBadge status={gateStatus(gates[g]?.status)} />
            {gates[g]?.clause ? <div className="stg-gate__clause">{gates[g]?.clause}</div> : null}
          </div>
        ))}
      </div>
      {report.verdict?.say ? <p className="stage__say">“{report.verdict.say}”</p> : null}
      <div className="stage__eyebrow">facts on record</div>
      <div className="stg-facts">
        {facts.map((f) => (
          <div key={f.fact} className="stg-fact">
            <span className="stg-fact__name">{f.fact}</span>
            <span className="stg-fact__value">{factValue(f.value)}</span>
            <OriginTag origin={(f.origin as FactOrigin) ?? 'DEFAULTED'} />
            {f.tool ? <span className="stg-fact__tool">{f.tool}</span> : null}
          </div>
        ))}
      </div>
      <ReadingBand items={gatesReading(report, passed)} />
      <GlossaryLine panel="gates" />
    </div>
  );
}

/* ── 5 · Retrieval & split ──────────────────────────────────────────────── */

function RetrievalPanel({ recalls, carve, payload }: { recalls: RecallReport[]; carve: Carve | null; payload: StagePayload }) {
  /* WHICH INDEX. A thread that scored two retrievers holds two measurements,
     and the newest is not "the" one — thread 33 scored a train-side index
     (14/24, not recorded) and then the full glossary (29/30, recorded). The
     choice is the panel's own, not the shared run selection: an index is not
     a run. Newest first, picked by its index id. */
  const [pickedIndex, setPickedIndex] = useState<number | null>(null);
  const scored = recalls.filter((r) => r.curve.length > 0);
  const recall = scored.find((r) => r.indexId === pickedIndex) ?? scored[0] ?? null;
  return (
    <div className="stage__grid stage__grid--two">
      <div>
        {scored.length > 1 ? (
          <div className="stage__runs stage__runs--inline" role="listbox" aria-label="Indexes scored">
            {/* Keyed by POSITION as well as index id: one index can be scored
                twice in a thread (a second k, a corrected ground-truth column),
                and those are two measurements with one id. */}
            {scored.map((r, at) => (
              <button
                key={`${r.indexId ?? 'x'}-${at}`}
                type="button"
                role="option"
                aria-selected={r === recall}
                className="stage__run"
                data-selected={r === recall || undefined}
                onClick={() => setPickedIndex(r.indexId)}
              >
                <span className="stage__runid">{r.indexId ?? '?'}</span>
                <span>{r.indexName ?? 'index'}</span>
                <span className="stage__runscore">{pct(r.recall)}{r.stampable ? '' : ' · not recorded'}</span>
              </button>
            ))}
          </div>
        ) : null}
        {recall && recall.curve.length > 0 ? (
          <>
            <div className="stage__eyebrow">recall rises with k · {recall.indexName ?? `index ${recall.indexId ?? '?'}`}</div>
            <div className="rcurve">
              {recall.curve.map((p) => (
                <div key={p.k} className="rcurve__row">
                  <span className="rcurve__k">k={p.k}</span>
                  <span className="rcurve__track"><i style={{ width: `${Math.round((p.recall ?? 0) * 100)}%` }} /></span>
                  <span className="rcurve__num">{p.hits}/{p.of} · {pct(p.recall)}</span>
                </div>
              ))}
            </div>
            <dl className="stage__kv" style={{ marginTop: 'var(--sp-8)' }}>
              <dt>questions scored</dt><dd>{recall.questionsScored} of {recall.questionsEligible}</dd>
              <dt>recorded as a fact</dt><dd>{recall.stampable ? <OriginTag origin="MEASURED" /> : <span className="stage__bad">no — {recall.unresolvedN} row(s) name a document the index lacks</span>}</dd>
            </dl>
          </>
        ) : (
          <p className="stage__empty">No retriever scored in this thread yet.</p>
        )}
      </div>
      <aside className="stage__side">
        <div className="stage__eyebrow">where the rows went</div>
        {carve ? (
          <dl className="stage__kv">
            <dt>read</dt><dd>{carve.rowsRead} rows</dd>
            <dt>eval</dt><dd>{carve.evalRows} rows</dd>
            <dt>train</dt><dd>{carve.trainRows} rows</dd>
            <dt>leak check</dt><dd>{carve.verification ? (carve.verification.leaked === 0 ? <span className="stage__good">0 leaked</span> : <span className="stage__bad">{carve.verification.leaked ?? '?'} leaked</span>) : 'not run'}</dd>
          </dl>
        ) : (
          <p className="stage__empty">No carve in this thread.</p>
        )}
        {recall && recall.unresolvedRows.length > 0 ? (
          <>
            <div className="stage__eyebrow" style={{ marginTop: 'var(--sp-8)' }}>concepts no train-side method can reach</div>
            <p className="stage__bad">{Array.from(new Set(recall.unresolvedRows)).join(' · ')}</p>
          </>
        ) : null}
      </aside>
      <ReadingBand items={retrievalReading(recall, carve, payload)} />
      <GlossaryLine panel="retrieval" />
    </div>
  );
}

/* ── the words, in one line each — hover-cards on the terms a panel uses ── */

export const GLOSSARY: Record<string, string> = {
  'eval set': 'The held-out questions nothing trains on. The exam, not the textbook.',
  judge: 'A model answers "was this right?" per row. Sees meaning; can flatter. Every row keeps the rule verdicts beside it.',
  McNemar: 'Compares two runs only on rows that flipped. Ignores rows both got right or wrong — the honest test for a paired comparison.',
  resolution: 'The smallest difference this many rows can see. At n=30, about 25 points; below that, "no evidence" is the only honest word.',
  'recall@k': 'For each question, is the right document in the retriever\'s top k. Scores the retriever alone, before any model answers.',
  LoRA: 'Trains two small matrices on a frozen base instead of the base itself. Cheap, and it can only select what the base already knows.',
  loss: 'Surprise at the next true token. Falls as the model memorises the training sentences. Says nothing about held-out questions.',
  spill: 'Weights that do not fit the card page through system memory. Runs, and many times slower. Looks like training in the log.',
  gate: 'A question the ledger will not skip on the way to "train". Five of them; only measured or stated facts open one, never a model\'s claim.',
  baseline: 'What the connected model scores cold, under the default prompt, before anything is changed. Every later run is paired against it.',
  provenance: 'Where a number came from: MEASURED by an instrument, STATED by you, ASSERTED by a model (opens nothing), DEFAULTED (nobody measured it: the ledger’s fallback, or under Full a rule the harness applied and wrote down).',
};

/** A term with its one-line definition on hover and on focus. Dotted, not
 *  coloured: a term is not a claim. */
export function Term({ children, of }: { children: ReactNode; of: keyof typeof GLOSSARY }) {
  return (
    <span className="stg-term" tabIndex={0} data-def={GLOSSARY[of]} aria-label={`${String(of)}: ${GLOSSARY[of]}`}>
      {children}
    </span>
  );
}

const PANEL_TERMS: Record<StagePanelId, Array<keyof typeof GLOSSARY>> = {
  bench: ['eval set', 'judge', 'McNemar', 'resolution', 'baseline'],
  sandbox: ['spill', 'provenance'],
  progression: ['loss', 'LoRA', 'eval set'],
  gates: ['gate', 'provenance', 'baseline'],
  retrieval: ['recall@k', 'eval set'],
};

function GlossaryLine({ panel }: { panel: StagePanelId }) {
  return (
    <div className="stg-glossary">
      <span className="stage__eyebrow" style={{ marginBottom: 0 }}>the words</span>
      {PANEL_TERMS[panel].map((term) => (
        <Term key={String(term)} of={term}>{String(term)}</Term>
      ))}
    </div>
  );
}

/* ── reading bands: what happened, why it matters, what to do ──────────── */

interface Reading {
  k: 'what' | 'why' | 'do';
  claim: string;
  body: string;
}

const READING_ICON: Record<Reading['k'], IconName> = { what: 'eye', why: 'book', do: 'chevright' };
const READING_LABEL: Record<Reading['k'], string> = { what: 'What happened', why: 'Why it matters', do: 'What to do' };

function ReadingBand({ items }: { items: Reading[] }) {
  if (items.length === 0) return null;
  return (
    <div className="stg-reading">
      {items.map((item) => (
        <div key={item.k}>
          <Icon name={READING_ICON[item.k]} />
          <div>
            <b>{READING_LABEL[item.k]}</b>
            <span className="stg-reading__claim">{item.claim}</span> {item.body}
          </div>
        </div>
      ))}
    </div>
  );
}

function benchReading(payload: StagePayload, selected: StageRun | null, paired: StageComparison | null, target: number | null): Reading[] {
  const complete = payload.runs.filter((r) => r.complete);
  if (complete.length === 0) return [];
  const best = [...complete].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0];
  const width = best.planned;
  const out: Reading[] = [
    {
      k: 'what',
      claim: `${complete.length} run${complete.length === 1 ? '' : 's'} graded the same ${width} rows.`,
      body: `The best, run ${best.run_id}, got ${best.correct} right (${pct(best.score)}). Each green cell is one row the judge accepted.`,
    },
  ];
  if (paired && selected) {
    out.push({
      k: 'why',
      claim: 'Only rows that flipped count.',
      body: `Run ${selected.run_id} vs ${paired.against}: ${paired.improved} went right, ${paired.regressed} went wrong — p=${points(paired.p_value, 3)}, ${paired.verdict === 'different' ? 'a real difference' : 'so these rows cannot tell the two apart'}. The outlined cells are the whole argument; the percentages are not.`,
    });
  }
  if (selected?.resolution) {
    out.push({
      k: 'do',
      claim: target !== null && (best.score ?? 0) < target ? `No arm reaches your ${pct(target)} bar.` : 'Grade more rows before believing a delta.',
      body: `${selected.resolution.rows_for_a_10_point_difference} rows resolve a 10-point difference; ${width} resolve only about ${points(selected.resolution.resolves_a_difference_of_at_least_points, 0)} points.`,
    });
  }
  return out;
}

function sandboxReading(payload: StagePayload): Reading[] {
  const runs = trainRuns(payload);
  const out: Reading[] = [];
  if (runs.length >= 2) {
    const [a, b] = [runs[0].run, runs[1].run];
    const rateA = a.elapsed_seconds && a.steps ? a.steps / a.elapsed_seconds : null;
    const rateB = b.elapsed_seconds && b.steps ? b.steps / b.elapsed_seconds : null;
    if (rateA && rateB) {
      const slow = rateA < rateB ? a : b;
      const fast = rateA < rateB ? b : a;
      const ratio = Math.max(rateA, rateB) / Math.min(rateA, rateB);
      out.push({
        k: 'what',
        claim: `${slow.name} ran ${ratio.toFixed(0)}× slower per step than ${fast.name}.`,
        body: `${slow.name}: ${slow.steps} steps in ${secondsLabel(slow.elapsed_seconds)}; ${fast.name}: ${fast.steps} steps in ${secondsLabel(fast.elapsed_seconds)}. Peak memory ${points(slow.peak_vram_gb, 2)} GB and ${points(fast.peak_vram_gb, 2)} GB — read off each run's own log.`,
      });
      if (ratio > 3) {
        out.push({
          k: 'why',
          claim: 'Paging looks exactly like training.',
          body: 'A run that does not fit the card spills into system memory and still prints steps and falling loss. Nothing in the log says it is crawling; only the rate does.',
        });
      }
    }
  }
  const occ = payload.gpu.occupancy;
  if (occ) {
    out.push({
      k: 'do',
      claim: payload.gpu.guard ? 'Unload what is resident before training.' : 'The guard reads the card before every run.',
      body: payload.gpu.guard
        ? `${occ.used_gb} of ${occ.total_gb} GB is held right now. The guard names the resident model and refuses; config.share_gpu runs anyway and accepts the paging.`
        : `${occ.used_gb} of ${occ.total_gb} GB in use — under the ${payload.gpu.crowded_above_gb} GB line, so a training run starts. That line is measured, not defaulted.`,
    });
  }
  return out;
}

function progressionReading(series: Array<{ box: string; run: StageSandboxRun }>, adapters: StageRun[], baseline: StageRun | null): Reading[] {
  const out: Reading[] = [];
  if (series.length > 0) {
    const first = series[0].run;
    const start = first.curve[0].loss;
    const end = first.curve[first.curve.length - 1].loss;
    out.push({
      k: 'what',
      claim: `Loss fell from ${points(start, 2)} to ${points(end, 2)} over ${first.steps ?? first.max_steps ?? '?'} steps.`,
      body: 'Loss is how surprised the model is by the next word of the true answer. Falling loss means the training sentences are being learned.',
    });
  }
  if (adapters.length > 0 && baseline) {
    const best = [...adapters].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0];
    const behind = (best.score ?? 0) < (baseline.score ?? 0);
    out.push({
      k: 'why',
      claim: behind ? 'Reciting is not knowing.' : 'The adapter beat the baseline on held-out rows.',
      body: behind
        ? `The best adapter (run ${best.run_id}) scored ${pct(best.score)} on held-out rows against the baseline's ${pct(baseline.score)} (run ${baseline.run_id}). A falling loss with a flat held-out score is overfitting, drawn.`
        : `Run ${best.run_id} scored ${pct(best.score)} against ${pct(baseline.score)} on the same rows — read the paired verdict on the Bench before calling it a win.`,
    });
  }
  out.push({
    k: 'do',
    claim: 'Read both charts together, always.',
    body: 'A loss line alone will fool you every time. The held-out score is the one that costs something, and it is measured on rows the training never saw.',
  });
  return out;
}

function gatesReading(report: { verdict?: { outcome?: string; gates?: Record<string, { status?: string }> }; facts?: Array<{ fact: string; origin: string }> }, passed: number): Reading[] {
  const outcome = report.verdict?.outcome ?? '';
  const facts = report.facts ?? [];
  const measured = facts.filter((f) => f.origin === 'MEASURED').length;
  const stated = facts.filter((f) => f.origin === 'STATED').length;
  return [
    {
      k: 'what',
      claim: `${passed} of 5 gates opened on ${measured} measured and ${stated} stated facts.`,
      body: 'A gate is a question the ledger refuses to skip on the way to "train". Green nodes were answered by instruments or by you; a model\'s claim opens nothing.',
    },
    {
      k: 'why',
      claim: outcome.startsWith('NO_TRAIN') ? 'The verdict is not to train — and it says why.' : outcome.startsWith('TRAIN') ? 'Every gate is open; training is on the table.' : 'The walk stopped before a verdict.',
      body: outcome.startsWith('NO_TRAIN')
        ? 'The route ran through the cheaper levers first. Where it stopped is the sentence quoted above, verbatim from the ledger.'
        : 'What is still shut is listed as NOT CHECKED; the next action names the instrument that opens it.',
    },
    {
      k: 'do',
      claim: 'Grey tags are things you said; green tags are things the machine read.',
      body: 'An amber DEFAULTED tag means nobody measured it. Under Ask that is the ledger’s fallback constant; under Full it is a rule the harness applied, and the row says which. Either way a verdict resting on one is not resting on your data.',
    },
  ];
}

function retrievalReading(recall: RecallReport | null, carve: Carve | null, payload: StagePayload): Reading[] {
  const out: Reading[] = [];
  if (recall && recall.curve.length > 0) {
    const first = recall.curve[0];
    const last = recall.curve[recall.curve.length - 1];
    out.push({
      k: 'what',
      claim: `Recall rises from ${pct(first.recall)} at k=${first.k} to ${pct(last.recall)} at k=${last.k}.`,
      body: 'Recall@k asks, for each question, whether the right document is in the retriever\'s top k. It scores the retriever alone, before any model answers.',
    });
    if (recall.unresolvedN > 0) {
      out.push({
        k: 'why',
        claim: `${recall.unresolvedN} question(s) name something this index does not hold.`,
        body: 'Nothing indexed from this corpus can reach them, and nothing trained on it could either — a property of the split, and it caps every score in the thread. The harness recorded no fact rather than a recall over the rows that happened to join.',
      });
    } else {
      out.push({
        k: 'why',
        claim: recall.stampable ? 'The number is on the ledger as MEASURED.' : 'The number was not recorded.',
        body: recall.stampable ? `${recall.hits} of ${recall.questionsScored} questions had the right document in the top ${recall.k}. A retriever this good makes the generator the bottleneck.` : recall.notMeasured,
      });
    }
  }
  if (carve) {
    out.push({
      k: 'do',
      claim: carve.verification && carve.verification.leaked === 0 ? 'The split does not leak. Watch what it isolates instead.' : 'Check the split before trusting any score.',
      body: `${carve.evalRows} eval and ${carve.trainRows} train rows from ${carve.rowsRead} read. A hash split can put a whole concept on one side; split by concept when the data has one.`,
    });
  } else if (payload.runs.length > 0) {
    out.push({ k: 'do', claim: 'Index the whole knowledge base for retrieval.', body: 'A deployed retriever sits on all of it, not on a training half. The held-out questions still never enter the index.' });
  }
  return out;
}
