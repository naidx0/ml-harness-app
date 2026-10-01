/**
 * THE DIAGRAM IS THE PLAN, RENDERED. Not an illustration drawn beside it.
 *
 * `docs/THE_PROPOSAL_LOOP.md` §4, and this is the load-bearing sentence:
 *
 *   "If a diagram is generated from the build, it can never lie about what is
 *    going to happen. If someone edits a step in the diagram, they are editing
 *    the build. If a step fails during the storm, that node changes state in
 *    the picture, because it is the same node."
 *
 * So there is no diagram model in this file. There is no layout data on the
 * wire, no node list a second system assembled, and no id this component
 * minted. The nodes ARE `build.steps`, keyed by `Step.id` — which is the same
 * key the executor reports state under (`app/build.py`: "`id` is the node id in
 * the diagram AND the key the executor reports state under"). The lines ARE
 * `build.edges`. The rows ARE `build.waves()`, which is the executor's own
 * schedule of what may run at once. Everything below is geometry over those
 * three, and geometry is the only thing this file is allowed to invent.
 *
 * ══ WHY A PICTURE AT ALL ═══════════════════════════════════════════════════
 *
 * "A picture is also how a person who is not an ML engineer understands a
 * pipeline at all. 'Split, dedupe, index, evaluate, compare' is five words and
 * a shape, and the shape is what makes it obvious that the eval set comes off
 * the data before anything touches it."
 *
 * That is why the layout is by WAVE rather than by a prettier graph algorithm.
 * A wave is not a drawing convention; it is `Build.waves()`, the answer to
 * "what can run at the same time". Two nodes side by side means those two
 * things happen at once. A node below another means it waits. The shape is the
 * schedule.
 *
 * ══ TWO KINDS OF LINE, BECAUSE THERE ARE TWO KINDS OF DEPENDENCY ═══════════
 *
 * `app/build.py`: "A `needs` entry with no `Ref` behind it is an ordering the
 * author asserted. A `Ref` is an ordering the graph can check." Those are
 * different claims, so they are different lines: a solid line carries a named
 * output from one step into the next step's argument, and a dashed line is
 * sequence alone. Selecting a node names the output on its solid lines. Two
 * strokes, no new hue — the distinction is form, not colour, exactly as
 * Graphite page 05 requires of everything a colour could have carried.
 *
 * ══ STATE, AND WHY THERE IS NONE UNTIL A STORM SAYS SO ═════════════════════
 *
 * `app/build.py` again: "Nothing here stores state — a plan has no state — but
 * the picture and the executor key on `Step.id` and need one agreed set of
 * words for what that node is doing." So a PROPOSAL draws nodes with no status
 * dot and no state word: nothing has run, and a row of grey "Queued" pips
 * would be this surface claiming a state the plan does not have.
 *
 * Once a storm exists, the node's state IS the step's state — `storm.steps`
 * keyed by the same `Step.id`, folded by `app/storm.py` out of the event log
 * the transcript is already following. The dot, the role colour and the word
 * come from `lib/runState.ts`, which is `docs/DESIGN_SYSTEM.md` §2.5 and the
 * same nine words `build.STEP_STATES` ships. There is no second vocabulary here
 * and there must never be one.
 *
 * A step that FAILED or was SKIPPED carries the engine's own sentence for why,
 * and the node shows it on hover rather than paraphrasing it — a picture that
 * summarised a failure would be the one place a diagram could lie.
 *
 * ══ EVERY TOKEN FROM GRAPHITE ══════════════════════════════════════════════
 *
 * No hex, no rgba, no size that is not on the ramp. The node is a Graphite card
 * chassis at --r-10 (page 26's run-row radius, because a node IS a step and a
 * step is what a run row shows); lines are --edge-strong; the selected node
 * takes --accent-edge and --accent-wash, which page 05 assigns to "the product
 * asking for something" and never to a verdict.
 */

import { useId, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import type { Build, Step } from '../lib/engine/build';
import { outputsAlong, refsOf } from '../lib/engine/build';
import type { Storm, StormStep } from '../lib/engine/storm';
import type { ToolControl } from '../lib/engine/types';
import { stepStateView } from '../lib/runState';
import { Icon, groupIcon } from './Icon';
import { StatusDot } from './primitives';

/* ── Geometry. The only thing this file invents. ──────────────────────────
   Sizes are Graphite's compact scale: the node is 180x56, which holds a 12px
   label on one line and a 10px mono id under it at the same 8px padding every
   other row in this product uses. GAP_Y is 44 so an edge has room to curve and
   still land on an arrowhead that reads at 1.5px. */
const NODE_W = 180;
const NODE_H = 56;
const GAP_X = 18;
const GAP_Y = 44;
/** The wave ordinal's column. Narrow: it holds one mono digit. */
const GUTTER = 34;

interface Placed {
  step: Step;
  x: number;
  y: number;
}

interface Layout {
  nodes: Map<string, Placed>;
  width: number;
  height: number;
  rows: { wave: number; y: number }[];
}

function layout(build: Build): Layout {
  const widths = build.waves.map(
    (wave) => wave.length * NODE_W + (wave.length - 1) * GAP_X,
  );
  const widest = Math.max(...widths, NODE_W);
  const nodes = new Map<string, Placed>();
  const rows: { wave: number; y: number }[] = [];

  build.waves.forEach((wave, band) => {
    const y = band * (NODE_H + GAP_Y);
    rows.push({ wave: band + 1, y });
    /* Bands are centred so the graph reads as a SHAPE — a fan out and a fan
       back in is the thing a non-engineer takes from the picture, and
       left-aligning bands hides it. */
    const left = GUTTER + (widest - widths[band]) / 2;
    wave.forEach((id, index) => {
      const step = build.steps.find((entry) => entry.id === id);
      if (!step) return;
      nodes.set(id, { step, x: left + index * (NODE_W + GAP_X), y });
    });
  });

  return {
    nodes,
    /* The gutter is mirrored as empty space on the right so the NODES sit in
       the middle of the canvas rather than the nodes-plus-ordinal block. Caught
       by looking: with the gutter counted once the whole picture sat 34px right
       of centre, which reads as a layout bug rather than as a shape. */
    width: GUTTER * 2 + widest,
    height: build.waves.length * NODE_H + (build.waves.length - 1) * GAP_Y,
    rows,
  };
}

export function BuildDiagram({
  build,
  tools,
  storm,
  selected,
  onSelect,
}: {
  build: Build;
  /** The registry's own declarations, so a node is labelled with the tool's
   *  label rather than with a sentence this file wrote. Absent before the
   *  catalogue loads, and the node then shows the tool's name. */
  tools: Map<string, ToolControl>;
  /** The storm this plan became, if it has become one. Absent on a proposal,
   *  because a plan has no state. */
  storm?: Storm | null;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const plan = useMemo(() => layout(build), [build]);
  /* Marker ids have to be unique per instance — two proposals in one
     transcript would otherwise share an arrowhead definition. */
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');

  const neighbours = useMemo(() => {
    if (!selected) return new Set<string>();
    const near = new Set<string>([selected]);
    for (const edge of build.edges) {
      if (edge.from === selected) near.add(edge.to);
      if (edge.to === selected) near.add(edge.from);
    }
    return near;
  }, [build.edges, selected]);

  return (
    <div className="plan">
      <div className="plan__canvas">
        <div
          className="plan__stage"
          style={{ width: plan.width, height: plan.height } as CSSProperties}
        >
          <svg
            className="plan__wires"
            width={plan.width}
            height={plan.height}
            viewBox={`0 0 ${plan.width} ${plan.height}`}
            aria-hidden="true"
            focusable="false"
          >
            <defs>
              {/* Two heads rather than one recoloured: `context-stroke` is not
                  universally supported and a marker that silently falls back to
                  black would introduce a colour this product does not own. */}
              <marker
                id={`${uid}-head`}
                viewBox="0 0 8 8"
                refX="6.4"
                refY="4"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M1 1 L6.6 4 L1 7 z" fill="var(--edge-strong)" />
              </marker>
              <marker
                id={`${uid}-head-on`}
                viewBox="0 0 8 8"
                refX="6.4"
                refY="4"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M1 1 L6.6 4 L1 7 z" fill="var(--accent)" />
              </marker>
            </defs>

            {build.edges.map((edge) => {
              const from = plan.nodes.get(edge.from);
              const to = plan.nodes.get(edge.to);
              if (!from || !to) return null;
              const carries = outputsAlong(build, edge);
              const lit =
                selected !== null &&
                (edge.from === selected || edge.to === selected);
              const sx = from.x + NODE_W / 2;
              const sy = from.y + NODE_H;
              const tx = to.x + NODE_W / 2;
              const ty = to.y;
              const bend = Math.max(18, (ty - sy) * 0.55);
              return (
                <g key={`${edge.from}->${edge.to}`} data-lit={lit || undefined}>
                  <path
                    className="plan__wire"
                    data-kind={carries.length ? 'data' : 'order'}
                    data-lit={lit || undefined}
                    d={`M ${sx} ${sy} C ${sx} ${sy + bend}, ${tx} ${ty - bend}, ${tx} ${ty}`}
                    markerEnd={`url(#${uid}-head${lit ? '-on' : ''})`}
                  />
                  {/* The output's NAME, and only on the lines of the node you
                      are looking at. Drawing every label at once turns the
                      picture into a wiring diagram, and the thing a reader
                      needs from a glance is the shape. */}
                  {lit && carries.length > 0 ? (
                    <text
                      className="plan__wirelabel"
                      x={(sx + tx) / 2}
                      y={(sy + ty) / 2 + 3}
                      textAnchor="middle"
                    >
                      {carries.join(', ')}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>

          {/* The wave ordinal. Not a decoration: a row IS a wave, and the
              ordinal is what makes "these two run at the same time" readable
              without a caption under every picture. */}
          {plan.rows.map((row) => (
            <span
              className="plan__wave"
              key={row.wave}
              style={{ top: row.y, height: NODE_H } as CSSProperties}
              title={`Wave ${row.wave} — everything on this row runs at once`}
            >
              {row.wave}
            </span>
          ))}

          {[...plan.nodes.values()].map((placed) => (
            <Node
              key={placed.step.id}
              placed={placed}
              control={tools.get(placed.step.tool) ?? null}
              live={storm?.steps.get(placed.step.id) ?? null}
              selected={selected === placed.step.id}
              dimmed={selected !== null && !neighbours.has(placed.step.id)}
              onSelect={onSelect}
            />
          ))}
        </div>
      </div>

      <Legend build={build} storming={Boolean(storm)} />
    </div>
  );
}

function Node({
  placed,
  control,
  live,
  selected,
  dimmed,
  onSelect,
}: {
  placed: Placed;
  control: ToolControl | null;
  live: StormStep | null;
  selected: boolean;
  dimmed: boolean;
  onSelect: (id: string | null) => void;
}) {
  const { step, x, y } = placed;
  /* The registry's own label. When the catalogue has not loaded the node shows
     the tool's NAME rather than a sentence invented here — the same fallback
     the transcript's tool rows take. */
  const label = control?.label ?? step.tool;
  const view = live ? stepStateView(live.state) : null;
  /* One grey mark, and it is the spec's own emphasis: a step some of whose
     cost nobody could price. Grey and a glyph, never a hue — an unknown cost
     is an absence, not a problem. */
  const unpriced = Object.values(step.cost).some(
    (estimate) => estimate.provenance === 'UNKNOWN',
  );

  return (
    <button
      type="button"
      className="plannode"
      data-selected={selected || undefined}
      data-dimmed={dimmed || undefined}
      style={{ left: x, top: y, width: NODE_W, height: NODE_H } as CSSProperties}
      aria-pressed={selected}
      data-state={live?.state}
      /* The engine's own sentence when there is one — never a paraphrase of a
         failure. */
      title={live?.because ? `${step.why}

${live.because}` : step.why}
      onClick={() => onSelect(selected ? null : step.id)}
    >
      <span className="plannode__top">
        <span className="plannode__glyph">
          <Icon name={control ? groupIcon(control.group) : 'skill'} size={13} />
        </span>
        <span className="plannode__label">{label}</span>
        {unpriced ? (
          <span
            className="plannode__unpriced"
            title="Part of this step's cost is unknown. The proposal says which part and how to find out."
          >
            ?
          </span>
        ) : null}
      </span>
      <span className="plannode__foot">
        {view ? (
          <>
            <StatusDot role={view.role} shape={view.dot} />
            <span
              className="plannode__state"
              style={{ color: `var(--${view.role})` } as CSSProperties}
            >
              {view.label}
            </span>
            <span className="plannode__id mono">{step.id}</span>
          </>
        ) : (
          <span className="plannode__id mono">{step.id}</span>
        )}
      </span>
    </button>
  );
}

/**
 * What the two strokes mean, and how many of each there are.
 *
 * Counted off the build rather than described, so the legend cannot claim a
 * kind of line the picture does not contain.
 */
function Legend({ build, storming }: { build: Build; storming: boolean }) {
  const data = build.edges.filter((edge) => outputsAlong(build, edge).length > 0);
  const order = build.edges.length - data.length;

  return (
    <p className="plan__legend">
      <span className="plan__key">
        <svg width="20" height="8" aria-hidden="true" focusable="false">
          <path className="plan__wire" data-kind="data" d="M1 4 H19" />
        </svg>
        {data.length} {data.length === 1 ? 'output' : 'outputs'} feeding the next
        step
      </span>
      {order > 0 ? (
        <span className="plan__key">
          <svg width="20" height="8" aria-hidden="true" focusable="false">
            <path className="plan__wire" data-kind="order" d="M1 4 H19" />
          </svg>
          {order} ordering{order === 1 ? '' : 's'} with no output behind{' '}
          {order === 1 ? 'it' : 'them'}
        </span>
      ) : null}
      <span className="plan__key">
        <span className="plan__keynum mono">{build.waves.length}</span>
        {build.waves.length === 1 ? 'wave' : 'waves'} — a row runs at once
      </span>
      {storming ? null : (
        <span className="plan__key plan__key--quiet">
          No node has a state: nothing has run.
        </span>
      )}
    </p>
  );
}

/**
 * The step behind a node, in full.
 *
 * Selecting a node opens THE STEP, not a summary of it — the arguments
 * verbatim (Graphite page 15.2: "shown verbatim, never summarised"), what it
 * produces, what it waits for, and how it will be known to have worked. This
 * is the "editing a node edits the build" seam: there is no edit route on the
 * engine yet, so this reads the step rather than writing it, and says so.
 */
export function StepDetail({
  build,
  step,
  control,
  live,
  onSelect,
}: {
  build: Build;
  step: Step;
  control: ToolControl | null;
  /** What the storm says this node is doing, once there is a storm. */
  live?: StormStep | null;
  onSelect: (id: string | null) => void;
}) {
  const refs = refsOf(step);
  const plain = Object.entries(step.arguments).filter(
    ([key]) => !refs.some((entry) => entry.argument === key),
  );
  const feeds = build.edges.filter((edge) => edge.from === step.id);

  return (
    <div className="stepdetail">
      <div className="stepdetail__head">
        <span className="stepdetail__id mono">{step.id}</span>
        <span className="stepdetail__tool mono">{step.tool}</span>
        <button
          type="button"
          className="stepdetail__close"
          onClick={() => onSelect(null)}
        >
          <Icon name="x" size={12} />
          close
        </button>
      </div>

      {/* Why it is in the plan. A person is about to approve this. */}
      <p className="stepdetail__why">{step.why}</p>

      {/* WHAT ACTUALLY HAPPENED, in the engine's words. `because` and
          `verification.because` are sentences `app/storm.py` wrote when it
          decided; neither is re-worded here, because a step that cannot show it
          worked did not work and the showing is the sentence. */}
      {live ? <LiveStep live={live} /> : null}

      <div className="stepdetail__grid">
        <span className="stepdetail__k">Runs</span>
        <span className="stepdetail__v">
          {control ? control.verb : step.tool}
          {control ? (
            <span className="stepdetail__reads">
              {' '}
              · reads {control.reads.length ? control.reads.join(', ') : 'nothing'} ·
              writes {control.writes.length ? control.writes.join(', ') : 'nothing'}
            </span>
          ) : null}
        </span>

        {plain.map(([key, value]) => (
          <ArgumentRow key={key} name={key} value={value} />
        ))}

        {refs.map((entry) => (
          <span className="stepdetail__pair" key={entry.argument}>
            <span className="stepdetail__k mono">{entry.argument}</span>
            <span className="stepdetail__v">
              <span className="stepdetail__from">
                from{' '}
                <button
                  type="button"
                  className="stepdetail__jump mono"
                  onClick={() => onSelect(entry.ref.step)}
                >
                  {entry.ref.step}
                </button>
                <span className="mono">.{entry.ref.output}</span>
              </span>
            </span>
          </span>
        ))}

        {step.produces.length > 0 ? (
          <>
            <span className="stepdetail__k">Produces</span>
            <span className="stepdetail__v">
              {step.produces.map((output) => (
                <span className="stepdetail__out" key={output.name}>
                  <span className="mono">{output.name}</span>
                  <span className="stepdetail__type mono">{output.type}</span>
                  {output.description ? <span>{output.description}</span> : null}
                </span>
              ))}
            </span>
          </>
        ) : null}

        {feeds.length > 0 ? (
          <>
            <span className="stepdetail__k">Feeds</span>
            <span className="stepdetail__v">
              {feeds.map((edge) => (
                <button
                  type="button"
                  className="stepdetail__jump mono"
                  key={edge.to}
                  onClick={() => onSelect(edge.to)}
                >
                  {edge.to}
                </button>
              ))}
            </span>
          </>
        ) : null}
      </div>

      <div className="stepdetail__exit">
        <Icon name="check" size={12} />
        <span>
          <b>Done when</b> {step.exitCriterion.stated}{' '}
          <span className="stepdetail__check mono">
            {step.exitCriterion.source}.{step.exitCriterion.subject}{' '}
            {step.exitCriterion.comparator}
            {step.exitCriterion.value === null
              ? ''
              : ` ${String(step.exitCriterion.value)}`}
          </span>
        </span>
      </div>

      {step.risks.length > 0 ? (
        <div className="stepdetail__risks">
          {step.risks.map((risk) => (
            <p className="stepdetail__risk" key={risk.what}>
              <Icon name="alert" size={12} />
              <span>
                <b>{risk.what}</b> {risk.what_we_do}
              </span>
            </p>
          ))}
        </div>
      ) : null}

      {/* The contract fingerprint. It is what an approval binds to, so it is
          on screen rather than implied — page 15.2's "carries the tool's own
          arguments rather than a summary of them", one level up. */}
      <p className="stepdetail__contract">
        <span>contract</span>
        <span className="mono">{step.contract.slice(0, 16)}</span>
      </p>
    </div>
  );
}

function LiveStep({ live }: { live: StormStep }) {
  const view = stepStateView(live.state);
  return (
    <div className="stepdetail__live" data-state={live.state}>
      <span className="stepdetail__livehead">
        <StatusDot role={view.role} shape={view.dot} />
        <span style={{ color: `var(--${view.role})` } as CSSProperties}>
          {view.label}
        </span>
        {live.attempts > 1 ? (
          <span className="stepdetail__attempts">attempt {live.attempts}</span>
        ) : null}
      </span>
      {live.because ? <p className="stepdetail__because">{live.because}</p> : null}
      {live.verification ? (
        <p className="stepdetail__verified" data-ok={live.verification.ok}>
          <Icon name={live.verification.ok ? 'check' : 'alert'} size={12} />
          <span>
            {live.verification.stated} — {live.verification.because}
          </span>
        </p>
      ) : null}
      {Object.keys(live.outputs).length > 0 ? (
        <div className="stepdetail__outputs">
          {Object.entries(live.outputs).map(([name, value]) => (
            <span className="stepdetail__output" key={name}>
              <span className="mono">{name}</span>
              <span className="mono stepdetail__outvalue">{renderArgument(value)}</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ArgumentRow({ name, value }: { name: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  const text = renderArgument(value);
  const long = text.length > 96;
  return (
    <span className="stepdetail__pair">
      <span className="stepdetail__k mono">{name}</span>
      <span className="stepdetail__v mono stepdetail__arg">
        {long && !open ? `${text.slice(0, 95)}…` : text}
        {long ? (
          <button
            type="button"
            className="stepdetail__more"
            onClick={() => setOpen(!open)}
          >
            {open ? 'less' : 'all'}
          </button>
        ) : null}
      </span>
    </span>
  );
}

/** Verbatim. Page 15.2 on the approval card: arguments are "shown verbatim,
 *  never summarised", and a plan's arguments are the same promise one level
 *  up. Nothing here rounds, renames or prettifies. */
function renderArgument(value: unknown): string {
  if (value === null || value === undefined) return 'not set';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}
