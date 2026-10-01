/**
 * THE PANES — what each one is, and what it says when it has nothing.
 *
 * DESIGN_SYSTEM §9.13-§9.19 for the bodies; the SHELL that holds them is
 * `components/Inspector.tsx`, which is Graphite page 18.4's single 44px header
 * rather than §9.12's nine-accordion stack. See that file for why.
 *
 * "Order is fixed and not user-sortable: Machine · Data · Evidence · Recipe ·
 * Log · Metrics · Network · Artifacts · Terminal. A stack that reorders itself
 * cannot be learned, and muscle memory is most of what makes a dense shell
 * feel calm." That survives the change: it is now the order of the picker.
 */

import { type ReactNode } from 'react';
import { displayTag } from '../lib/format';
import { useLocalSpecs } from '../lib/useLocalSpecs';
import type { EvidenceState } from '../lib/useEvidence';
import { scoreIsAnOpinion, type EvalReport } from '../lib/engine/evals';
import { EvalReportBody } from './EvalCard';
import {
  actorName,
  factsInClause,
  isFactOrigin,
  weakestOrigin,
  type DiagnosisPayload,
} from '../lib/engine/facts';
import type { GateStatus, LocalSpecs } from '../lib/engine/types';
import {
  Button,
  GateBadge,
  GateIcon,
  OriginTag,
  ProvenanceTag,
  Strip,
} from './primitives';
import { Icon, type IconName } from './Icon';
import { FilesPane } from './FilesPane';
import { MemoryPane } from './MemoryPane';
import { FIVE_GATES } from '../data/sample';

export type PaneId =
  | 'journey'
  | 'context'
  | 'plan'
  | 'agents'
  | 'machine'
  | 'memory'
  | 'files'
  | 'data'
  | 'evidence'
  | 'eval'
  | 'stage'
  | 'recipe'
  | 'log'
  | 'metrics'
  | 'network'
  | 'artifacts'
  | 'terminal';

/**
 * Fixed order. §9.12.
 *
 * EVAL SITS AFTER EVIDENCE BECAUSE THAT IS WHAT IT IS. The evidence pane draws
 * the five gates; `G1_BASELINE_MEASURED` is opened by an eval run and by
 * nothing else, and the failure histogram this pane draws is the input to stage
 * 1 of the diagnosis tree. Reading the gates and then the run that opened one
 * of them is the order a person asks the questions in, which §9.12's own
 * argument for a fixed order — "muscle memory is most of what makes a dense
 * shell feel calm" — is about.
 */
export const PANE_ORDER: readonly PaneId[] = [
  /* THE ROUTE COMES FIRST because it is the question under all the others:
     what am I doing, and what is next. Max, relayed 2026-09-02 - "a person
     opens the app, says what they have, and is walked from data to a trained
     adapter or an honest do-not-train, without needing to know which of
     sixty-seven tools to reach for." Machine's own argument - that this
     product measures your box rather than asking you about it - is made on
     the first-run empty state, where a person meets it before any of this. */
  'journey',
  /* THE PLAN SITS SECOND, under the route and above the machine: it is
     the answer to the same question Journey asks - what am I doing and
     what is next - once a person has agreed one. A thread with no plan
     draws the empty state saying where a plan comes from, which is the
     only place in the product that explains what Build saves. */
  'plan',
  /* CS4 — workers beside the plan they are working: status, packs, digest. */
  'agents',
  /* THE CONTEXT WINDOW. Max, 2026-09-13: "we need a context window showcase
     for ML Harness." Beside Plan because they answer the same person at the
     same moment - what is this turn carrying, and is there room for another
     one. Every figure on it was counted on a prompt that was sent
     (app/contextwindow.py); nothing here is an estimate of a prompt that
     was never built. */
  'context',
  'machine',
  /* MEMORY SITS AFTER MACHINE: what this box is, then what this project
     already knows and who is asking - the two things every turn is handed
     before the person types (conductor._memory_note). Hermes' MEMORY.md
     and USER.md, editable here rather than in a file. */
  'memory',
  /* FILES SITS BETWEEN MACHINE AND DATA because that is the order of the
     questions: what is this box, what is in my folder, what does the dataset
     hold. The owner's direction (2026-08-31): "If we ask people to pull up a
     file, we can actually open it on the sidebar somewhere, like where
     machine is... and they can edit it as well." */
  'files',
  /* CS11 — Data merged into Stage (Data ∪ Stage). Id kept on PaneId for
     deep-links; resolvePaneId('data') → 'stage'. Not in the rail picker. */
  'data',
  'evidence',
  'eval',
  /* THE STAGE SITS AFTER EVAL because it is the eval pane at full width: the
     same runs, every row, side by side, plus the sandbox, the loss curve, the
     gate route and the retriever — and, since CS11, the Data empty/tools home. */
  'stage',
  /* FIVE PANES LEFT THE PICKER on 2026-09-12. Max, reading the rail: "Recipe,
     this is just a plan, do we need another one of those? Log, how often do
     we really see that? Metrics is also kind of part of the stage. Artifacts,
     we haven't really made any, and this is just kind of a file thing."
     Network went with them for the same reason. The pane ids and their
     bodies stay - the Stage composes the log, the metrics and the loss curve
     itself, and a pane that is not in the picker is one click less to
     find the one you meant. */
  'terminal',
];

export const PANE_TITLE: Record<PaneId, string> = {
  journey: 'Journey',
  plan: 'Plan',
  agents: 'Agents',
  context: 'Context window',
  machine: 'Machine',
  memory: 'Memory',
  files: 'Files',
  data: 'Data',
  evidence: 'Evidence',
  eval: 'Eval',
  stage: 'Stage',
  recipe: 'Recipe',
  log: 'Log',
  metrics: 'Metrics',
  network: 'Network',
  artifacts: 'Artifacts',
  terminal: 'Terminal',
};

/** DESIGN_DIRECTIVES §4: pane headers carry icons. Every one of these is a
 *  Graphite symbol drawn for the thing it names.
 *
 *  A COLLISION THE INSPECTOR EXPOSED. Log and Terminal both read `terminal`
 *  here. That was invisible while the nine panes were a stack — the two headers
 *  were 300px apart — and it is glaring in the subject picker, where they are
 *  two rows apart with identical glyphs. Terminal keeps `terminal`, which is
 *  literally its glyph; Log takes `clock`, because a run log is a time-ordered
 *  record and the fifty-eight-glyph sheet has no stack-of-lines symbol. Page 09
 *  reserves drawing a fifty-ninth for a meaning the sheet cannot carry, and
 *  `clock`'s only other use is the inline "connecting…" status in
 *  ConnectModel, which never appears on this surface. */
export const PANE_ICON: Record<PaneId, IconName> = {
  /* `branch` is a route with a fork in it and no other pane claims it. */
  journey: 'branch',
  /* `skill` IS THE PLAN SEGMENT'S OWN GLYPH in ModeSwitch, and this pane
     is what that mode produces. Two surfaces for one idea should not be
     drawn with two symbols. Unclaimed at pane level. */
  plan: 'skill',
  /* CS4 — sub-agents; `robot` is the worker glyph drawn for that meaning. */
  agents: 'robot',
  /* `gauge` is Evidence and `chart` is Metrics; `clock` is unclaimed at pane
     level and is what this product already draws for "how much of something
     is spent". */
  context: 'clock',
  machine: 'gpu',
  /* `book` - what has been written down. Unclaimed at pane level; its
     inline uses (a journey's reading, a settings link) never sit in the
     picker beside this. */
  memory: 'book',
  /* `folder` is the workspace's own glyph everywhere else in the product —
     the chip under the composer, the attach popover — and no other pane
     claims it. */
  files: 'folder',
  data: 'dataset',
  evidence: 'gauge',
  /* `run`, THE WAVEFORM, AND NOT `chart`. Chart is Metrics and the two would
     sit two rows apart in the picker with identical glyphs — the exact
     collision this file already records between Log and Terminal, which was
     invisible in a nine-pane stack and glaring in a list. `gauge` is Evidence,
     `dataset` is Data, `filter` labels the buckets inside the pane. The
     waveform is unclaimed at pane level and it is the glyph this product
     already uses for "a run happened", which is what this pane is a list of. */
  eval: 'run',
  /* `panelleft` — the split glyph, unclaimed at pane level, and literally what
     the Stage does to the shell. */
  stage: 'panelleft',
  recipe: 'commit',
  log: 'clock',
  metrics: 'chart',
  network: 'model',
  artifacts: 'download',
  terminal: 'terminal',
};

/* ── What used to sit here: the stack ─────────────────────────────────────
   `StackState`, `initialStack`, `openPane`, `PaneStack`, `PaneTabs` and the
   `Pane` accordion have been removed. They implemented DESIGN_SYSTEM §9.12 —
   nine collapsible panes in one column, at most three expanded — which
   Graphite page 08 and page 18.4 contradict by naming ONE inspector pane with
   ONE 44px header. See `components/Inspector.tsx` for the argument and for
   what was measured in the running app before the change.

   This file keeps what was never in dispute: what each pane IS. The order, the
   titles, the icons, the provenance line and the bodies are unchanged. ────── */

/** §9.12: "Any pane whose content is derived carries one --text-2xs --ink-3
 *  line under the header naming its source and when it was read... the strip
 *  is not optional and not hover-revealed." */
export function paneProvenance(
  pane: PaneId,
  specs: LocalSpecs | null,
  /** What the Stage read, when it is the pane on screen. The route carries a
   *  thread id, so the line cannot be written without one. */
  where?: { threadId: number | null },
): string | null {
  if (pane === 'machine') {
    return specs
      ? `from GET /local_specs · read this session`
      : 'source not read yet';
  }
  if (pane === 'context') {
    const thread = where?.threadId ?? null;
    if (thread === null) return null;
    return `from GET /api/threads/${thread}/context · counted when each prompt was assembled`;
  }
  if (pane === 'journey') {
    const thread = where?.threadId ?? null;
    if (thread === null) return null;
    return `from GET /api/threads/${thread}/journey · re-read when the thread moves`;
  }
  if (pane === 'agents') {
    const thread = where?.threadId ?? null;
    if (thread === null) return null;
    return `from GET /api/threads/${thread}/subagents · re-read when the thread moves`;
  }
  if (pane === 'stage') {
    /* §9.12, and the Stage is the case the rule is about: everything on it —
       nine runs' rows, the paired verdicts, the sandbox, the card, the
       diagnosis — arrives in ONE request, and a surface showing that many
       figures without naming where they came from is this product's own
       defect wearing its own colours.
       No thread means no request was made. A route with a placeholder in it
       would be a source line for data that does not exist. */
    const thread = where?.threadId ?? null;
    if (thread === null) return null;
    return `from GET /api/threads/${thread}/stage · re-read when the thread moves`;
  }
  return null;
}

/* ── Pane bodies ────────────────────────────────────────────────────────── */

/**
 * A label and a chevron, with the paragraph behind it.
 *
 * MAX: "sometimes the text can be a bit much."
 *
 * Three surfaces in this file explained themselves at length in a 392px
 * column: why four Machine rows are empty, why the evidence ledger never
 * updates a row in place, and where the harness reads data from. All three are
 * true, all three are worth saying once, and none of them is worth four lines
 * of standing prose beside the thing it is about. `<details>` rather than a
 * hand-rolled toggle, because the browser already implements the disclosure
 * pattern including its keyboard and its screen-reader semantics, and this
 * product has no reason to reimplement either.
 *
 * It is NOT used for anything load-bearing. A number, a provenance tag, a
 * verdict or a gate row never moves behind a chevron — page 14.6's rule that a
 * fact is never only in a surface you can miss is the same rule.
 */
function Note({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="note">
      <summary className="note__head">
        <Icon name="chevright" size={12} />
        <span>{summary}</span>
      </summary>
      <div className="note__body">{children}</div>
    </details>
  );
}

export function PaneBody({
  id,
  diagnosis,
  evidence,
  evals,
  pickedEval,
  onPickEval,
  onControls,
  workspace,
  stage,
  journey,
  plan,
  context,
  agents,
  projectId,
  liveRunId,
  sandboxId,
}: {
  id: PaneId;
  diagnosis: DiagnosisPayload | null;
  evidence: EvidenceState;
  /** The open project and its folder — the Files pane's whole subject. */
  workspace?: { id: number; name: string; root: string | null } | null;
  /** The open project, for the Memory pane: its notes are per project, the
   *  person's profile is not. `null` on an unfiled thread. */
  projectId?: number | null;
  /** The Stage at its split size, already composed by the shell, which owns
   *  its state so the inline row, the split and the window show one thing. */
  stage?: ReactNode;
  /** The plan editor, composed by the shell: it reads the open thread's
   *  `plan` column and writes it back, and the shell is what holds the
   *  thread. Same argument as `journey` below. */
  plan?: ReactNode;
  /** The context-window pane, composed by the shell for the same reason: it
   *  reads one thread, and the shell is what knows which thread is open. */
  context?: ReactNode;
  /** CS4 — sub-agent board, composed by the shell (useSubAgents). */
  agents?: ReactNode;
  /** The journey overview, composed by the shell for the same reason: it reads
   *  the thread, and the shell is what knows which thread is open. */
  journey?: ReactNode;
  /** CS6 — bind Terminal to the live longrun / recipe sandbox when present. */
  liveRunId?: number | null;
  sandboxId?: string | null;
  /** Every eval run this conversation has read back, newest first. */
  evals: EvalReport[];
  /** Which run the eval pane is showing, or null for the newest. Held by the
   *  inspector rather than by the pane so the header's qualifier and the body
   *  resolve it once; see `currentEvalReport`. */
  pickedEval: number | null;
  onPickEval: (runId: number) => void;
  onControls: () => void;
}) {
  const liveRunLabel = liveRunId != null ? String(liveRunId) : null;
  const sandboxLabel = sandboxId ? String(sandboxId) : null;
  switch (id) {
    case 'journey':
      return <>{journey ?? null}</>;
    case 'plan':
      return <>{plan ?? null}</>;
    case 'agents':
      return <>{agents ?? null}</>;
    case 'context':
      return <>{context ?? null}</>;
    case 'machine':
      return <MachinePane />;
    case 'memory':
      return <MemoryPane projectId={projectId ?? null} />;
    case 'stage':
      return <>{stage ?? null}</>;
    case 'files':
      return <FilesPane workspace={workspace ?? null} />;
    case 'evidence':
      return <EvidencePane diagnosis={diagnosis} evidence={evidence} />;
    case 'eval':
      return (
        <EvalPane
          reports={evals}
          picked={pickedEval}
          onPick={onPickEval}
          onControls={onControls}
        />
      );
    case 'data':
      /* CS11 — Data ∪ Stage. Opening data redirects to stage; this body is
         only reached from a stale deep-link before resolvePaneId runs. */
      return (
        <PaneEmpty
          title="Data lives on Stage."
          body="Open Stage for the instruments and the data tools. Tell the harness a path in the chat, or run the data tools yourself."
          action="Open the data tools"
          actionIcon="dataset"
          onAction={onControls}
        />
      );
    case 'recipe':
      return (
        <PaneEmpty
          title="No plan yet."
          body="A plan revision enters the thread as a badge reading “Plan revised · +4 −2”, and that badge opens this pane."
        />
      );
    case 'log':
      /* §9.11's table: Log pane empty copy is "Waiting for output…" — never
         "No data". */
      return (
        <div className="log">
          <div className="log__line">
            <span className="log__no">1</span>
            <span style={{ color: 'var(--ink-3)' }}>Waiting for output…</span>
          </div>
        </div>
      );
    case 'metrics':
      return (
        <PaneEmpty
          title="No metrics logged for loss."
          body="Your training script reports metrics by calling HarnessRun.log."
        />
      );
    case 'network':
      /* §9.16: the pane states which tier it is showing at all times, and the
         `unavailable` state says what would enable it and what it would cost.
         The cost figure is MEASURED on this machine or it is not shown. */
      return (
        <PaneEmpty
          title="Not instrumented."
          body="Layer statistics need the run to be instrumented. Turning it on taxes throughput, and this pane will print the measured cost on this machine rather than a figure from a table."
        />
      );
    case 'artifacts':
      return (
        <PaneEmpty
          title="No artifacts yet."
          body="They appear when a run finishes."
        />
      );
    case 'terminal':
      /* §9.18: the input row is present, disabled, and says why.
         CS6 binds this pane to a live run when App focuses it. */
      return (
        <div>
          <div className="log">
            <div className="log__line">
              <span className="log__no">1</span>
              <span style={{ color: 'var(--ink-3)' }}>
                {liveRunLabel
                  ? `Following run ${liveRunLabel}${sandboxLabel ? ` · sandbox ${sandboxLabel}` : ''}.`
                  : 'No commands yet.'}
              </span>
            </div>
          </div>
          <div style={{ marginTop: 'var(--sp-8)' }}>
            <Strip tone="info" icon="info">
              Read-only. The harness runs commands; this is the record.
            </Strip>
          </div>
        </div>
      );
  }
}

/** §9.11's three-part structure, in pane form. No empty state is a shrug. */
function PaneEmpty({
  title,
  body,
  action,
  actionIcon = 'folder',
  onAction,
  children,
}: {
  title: string;
  body: string;
  /** Only ever passed with an `onAction`. A label with nothing behind it is the
   *  fixture problem in a different costume, and this file shipped one. */
  action?: string;
  actionIcon?: IconName;
  onAction?: () => void;
  /** A `Note` — the sentence the body no longer carries, behind a chevron. */
  children?: ReactNode;
}) {
  /* Every empty state is three parts and none of them is a shrug: what is
     true, what that means, what to do. No illustrations, no mascots, no large
     glyphs, and never the word "Oops". */
  return (
    <div className="empty empty--pane">
      <p className="empty__title" style={{ marginBottom: 'var(--sp-4)' }}>
        {title}
      </p>
      <p className="empty__body">{body}</p>
      {action && onAction ? (
        <div className="rowgap-6" style={{ marginTop: 'var(--sp-8)' }}>
          <Button kind="ghost" small icon={actionIcon} onClick={onAction}>
            {action}
          </Button>
        </div>
      ) : null}
      {children}
    </div>
  );
}

/* ── §9.13 Machine pane ─────────────────────────────────────────────────── */

export function MachinePane() {
  const state = useLocalSpecs();

  if (state.status === 'loading') {
    /* "detecting (skeleton rows at the known row count, never a spinner)" */
    return (
      <div>
        {MACHINE_ROWS.map((row) => (
          <div className="kvrow" key={row.key}>
            <span className="kvrow__k">{row.label}</span>
            <span
              style={{
                display: 'block',
                width: '72px',
                height: 'var(--t-11)',
                background: 'var(--surface-3)',
                borderRadius: 'var(--r-4)',
              }}
            />
          </div>
        ))}
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div>
        <Strip tone="spills" icon="alert">
          {state.message}
        </Strip>
        <p className="empty__body" style={{ marginTop: 'var(--sp-8)' }}>
          I couldn&rsquo;t find a graphics card. That might mean you don&rsquo;t
          have one, or that the driver isn&rsquo;t installed. Either way
          I&rsquo;ll plan for CPU until we know.
        </p>
        <div className="rowgap-6" style={{ marginTop: 'var(--sp-8)' }}>
          <Button kind="ghost" small icon="gpu">
            Tell me what you have
          </Button>
          <Button kind="ghost" small icon="refresh">
            Plan for CPU
          </Button>
        </div>
      </div>
    );
  }

  const specs = state.specs;

  return (
    <div>
      {MACHINE_ROWS.map((row) => {
        const value = row.read(specs);
        const tag = row.provenanceKey
          ? displayTag(specs.provenance[row.provenanceKey])
          : null;
        return (
          <div className="kvrow" key={row.key}>
            <span className="kvrow__k">{row.label}</span>
            <span className="kvrow__v" data-absent={value === null || undefined}>
              {value ?? 'not detected yet'}
            </span>
            <span className="kvrow__t">
              <ProvenanceTag tag={tag} />
            </span>
          </div>
        );
      })}

      {/* MAX: "sometimes the text can be a bit much." This was a full info
          strip — a bordered, tinted, two-line box — explaining why four rows
          read "not detected yet". The rows themselves already say it. The
          reason is worth one line behind a chevron and no more, and an info
          strip is a hue in a pane whose only other hues are provenance tags.

          §9.13: "Recheck is an explicit control in the header, and the pane
          prints when it last ran." The header control is not built; the fact
          that it is missing is stated rather than hidden. */}
      <Note summary="Why two rows say “not detected yet”">
        The driver and the capability are read now, off the same{' '}
        <code>nvidia-smi</code> call as the name and the memory. The last two
        are not this process’s to answer: they ask what a TRAINING
        environment can do, and the engine has no accelerator build by design
        — every recipe carries its own pinned venv and the engine never
        imports one. They stay as rows rather than disappearing: a missing row
        is invisible, an empty one is not. There is no recheck control in the
        header either, which §9.13 asks for.
      </Note>
    </div>
  );
}

/** §9.13's fixed row order. The last four have no source in the engine yet;
 *  they are still rows.
 *
 *  THE LABELS ARE THE BRAND BOOK'S, not the design system's longer ones.
 *  "Driver / CUDA runtime" and "Build can see the GPU" wrapped to two lines
 *  inside a 26px compact row and spilled over the row beneath — found by
 *  looking at the running pane, not by reading the diff. Graphite's own Machine
 *  card writes them short for exactly this reason. The free-disk row is still a
 *  SEPARATE reading from RAM; the pane's provenance strip carries where it was
 *  read from, so the label does not have to. */
const MACHINE_ROWS: {
  key: string;
  label: string;
  provenanceKey?: keyof LocalSpecs['provenance'];
  read: (specs: LocalSpecs) => string | null;
}[] = [
  { key: 'gpu', label: 'GPU', provenanceKey: 'gpu_name', read: (s) => s.gpu_name },
  {
    key: 'vram',
    label: 'VRAM',
    provenanceKey: 'vram_gb',
    read: (s) => (s.vram_gb === null ? null : `${s.vram_gb} GB`),
  },
  {
    key: 'driver',
    label: 'Driver',
    provenanceKey: 'driver_version',
    read: (s) => s.driver_version ?? null,
  },
  {
    key: 'cc',
    label: 'Capability',
    provenanceKey: 'compute_capability',
    read: (s) => s.compute_capability ?? null,
  },
  {
    key: 'ram',
    label: 'RAM',
    provenanceKey: 'ram_gb',
    read: (s) => (s.ram_gb === null ? null : `${s.ram_gb} GB`),
  },
  {
    key: 'disk',
    label: 'Free disk',
    provenanceKey: 'disk_free_gb',
    read: (s) => (s.disk_free_gb === null ? null : `${s.disk_free_gb} GB`),
  },
  { key: 'os', label: 'OS', provenanceKey: 'os', read: (s) => s.os },
  /* THESE TWO ARE ABOUT A DIFFERENT PROCESS, and that is why they are still
     empty here. "Accel build" and "sees the GPU" ask what the TRAINING
     environment can do - torch's build, and whether it opens the card - and
     the engine has no torch by design: every recipe carries its own pinned
     venv (docs/THE_PLAN.md V.3 A1b) and the engine never imports one. So the
     honest answer is not a reading this pane can take; it is a reading a
     recipe's environment takes, and the Note below says so rather than
     leaving two rows looking like a detection that failed. */
  { key: 'accel', label: 'Accel build', read: () => null },
  { key: 'sees', label: 'Sees the GPU', read: () => null },
];

/* ── §9.15 Evidence pane, and the gate ledger ─────────────────────────────
   This pane used to draw five NOT CHECKED rows and a paragraph about where the
   walk would eventually render. It draws the real ledger of the last diagnosis
   in this thread now, and beneath it the real evidence ledger — one append-only
   row per claim or measurement, with who said it and how.

   §9.15's rule survives the change and is what makes the empty case correct
   rather than blank: "A ledger that shows only the gates that ran cannot be
   read as a guarantee, and the guarantee is the product." So all five rows
   render before anything has been diagnosed, at NOT CHECKED, which is not a
   softer NOT MET. */

function EvidencePane({
  diagnosis,
  evidence,
}: {
  diagnosis: DiagnosisPayload | null;
  evidence: EvidenceState;
}) {
  const statuses: GateStatus[] = FIVE_GATES.map((gate) => {
    const entry = diagnosis?.gate_ledger[gate.id];
    if (!entry) return 'NOT_CHECKED';
    if (entry.status === 'PASSED') return 'PASSED';
    if (entry.status === 'NOT_REACHED') return 'NOT_CHECKED';
    return 'NOT_MET';
  });
  const passed = statuses.filter((s) => s === 'PASSED').length;

  return (
    <div>
      <div className="gates">
        <div className="gates__head">
          <Icon name="check" size={12} />
          <span>Gate ledger</span>
          {/* "The counter in the header is n/5 and never a percentage. Three of
              five gates is not 60% of a guarantee." */}
          <span className="gates__count">
            {passed} of {FIVE_GATES.length} passed
          </span>
        </div>

        {FIVE_GATES.map((gate, index) => {
          const entry = diagnosis?.gate_ledger[gate.id];
          /* The second fact on every row: not "did it pass" but "on what". The
             weakest origin among the facts the gate's own clause names, which
             is the only honest summary — a gate is exactly as substantiated as
             its worst load-bearing input. */
          const origin = entry
            ? weakestOrigin(
                factsInClause(entry.clause, diagnosis?.fact_origins ?? {}),
                diagnosis?.fact_origins ?? {},
              )
            : null;
          return (
            <div className="gate" key={gate.id} title={gate.asks}>
              {/* The glyph carries the status as well as the colour does, so the
                  ledger is readable with no colour perception at all. */}
              <GateIcon status={statuses[index]} />
              <span className="gate__no">{index + 1}</span>
              <span className="gate__name">{gate.name}</span>
              <span className="gate__right">
                {origin ? <OriginTag origin={origin} /> : null}
                <GateBadge status={statuses[index]} />
              </span>
            </div>
          );
        })}
      </div>

      {diagnosis ? null : (
        <p className="empty__body">
          Nothing decided yet. This fills in when a diagnosis runs in this
          thread.
        </p>
      )}

      <hr className="hr" />

      <div className="gates__head gates__head--plain">
        <Icon name="eye" size={12} />
        <span>Why the harness believes this</span>
        <span className="gates__count">{evidence.ledger.rows.length} rows</span>
      </div>

      {evidence.error ? (
        <Strip tone="spills" icon="alert">
          The evidence ledger could not be read.{' '}
          <span className="mono">{evidence.error}</span>
        </Strip>
      ) : evidence.ledger.rows.length === 0 ? (
        <p className="empty__body">
          Nothing has been claimed or measured in this thread yet. Rows appear
          here the moment a tool measures something or somebody says something.
        </p>
      ) : (
        <div className="evidence">
          {evidence.ledger.rows.map((row) => (
            <div className="evrow" key={row.id}>
              <span className="evrow__fact mono">{row.fact}</span>
              <span className="evrow__value mono">{showValue(row.value)}</span>
              {isFactOrigin(row.origin) ? (
                <OriginTag origin={row.origin} by={actorName(row.actor) ?? row.actor} />
              ) : (
                <span className="tag tag--raw">{String(row.origin)}</span>
              )}
              {/* The engine's own sentence of how. `Instrument.measured`
                  refuses a stamp without one, so a MEASURED row always has
                  something real to say here. */}
              <span className="evrow__how">{row.how}</span>
              <span className="evrow__who">
                {actorName(row.actor) ?? row.actor}
                {row.tool ? (
                  <>
                    {' · '}
                    <span className="mono">{row.tool}</span>
                  </>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      )}

      <Note summary="Why two rows can disagree">
        Rows are append-only and nothing is ever updated in place, so a
        measurement taken after a claim sits beside it rather than replacing it.
        The engine resolves them &mdash; measured beats stated beats asserted,
        recency breaking ties &mdash; and this pane does not, because a second
        resolution here could disagree with the one that decided the gates.
      </Note>
    </div>
  );
}

/* ── The eval result pane ─────────────────────────────────────────────────
   Milestone 3: "Results render as an artifact in a pane, opened from a
   one-line badge in the thread. Nothing heavy streams into the transcript;
   that rule is what keeps the box calm while it is doing a lot, and it is not
   negotiable." And the risk named beside it: "The artifact pane is its first
   real consumer, and a pane that is not ready is the pressure that puts an
   eval table into the transcript."

   Before this, per-row results were reachable only by calling
   `read_eval_results` and reading the card it produced in the chat column —
   which is a 940px card of failing rows in the measure, i.e. exactly the shape
   the rule forbids. The pane is where a person goes to look at rows.

   WHAT IT DRAWS IS `EvalReportBody`, THE CARD'S OWN BODY, not a second
   rendering of the same run. See `components/EvalCard.tsx`. */

/**
 * Which run the eval pane is showing.
 *
 * ONE RESOLUTION, EXPORTED, BECAUSE TWO OF THEM DISAGREED. The pane held the
 * pick in its own state and the inspector's header computed its qualifier from
 * `reports[0]`; selecting run 5 in the picker left the header reading "run 4 ·
 * 26 rows graded" over a body showing run 5's thirty. A header making a claim
 * about a different subject than the body under it is the defect this whole
 * lane is about, committed in the fix for it — found by clicking the picker and
 * looking at the header, which is the only way it could have been found.
 *
 * `null` means "the newest", so a run that arrives while the pane is open
 * becomes the subject without the pane fighting the user for it, and an
 * explicit pick sticks.
 */
export function currentEvalReport(
  reports: EvalReport[],
  picked: number | null,
): EvalReport | null {
  if (reports.length === 0) return null;
  return (
    (picked === null ? null : reports.find((entry) => entry.runId === picked)) ??
    reports[0]
  );
}

function EvalPane({
  reports,
  picked,
  onPick,
  onControls,
}: {
  reports: EvalReport[];
  picked: number | null;
  onPick: (runId: number) => void;
  onControls: () => void;
}) {
  if (reports.length === 0) {
    return (
      <PaneEmpty
        title="No eval run in this conversation yet."
        body="Run one and its score, its interval, the failure buckets and the rows that actually failed appear here."
        action="Open the eval tools"
        actionIcon="run"
        onAction={onControls}
      >
        <Note summary="Why the rows live here and not in the thread">
          A run returns twenty failing rows, and twenty expanded rows is a wall
          in a 640px chat measure. The transcript keeps the one-line result; the
          rows are a thing you come and look at.
        </Note>
      </PaneEmpty>
    );
  }

  const report = currentEvalReport(reports, picked);
  if (!report) return null;

  return (
    <div className="evalpane">
      {/* THE OTHER RUNS, as Graphite page 26's rows. Only when there is more
          than one: a picker offering one choice is furniture. */}
      {reports.length > 1 ? (
        <div className="evalpane__runs">
          {reports.map((entry) => {
            /* THE SAME QUESTION THE CARD ASKS, ASKED AGAIN HERE. A picker that
               prints a judge's 30% in the same ink as a rule's 96% has
               reintroduced the defect one level up: three runs, one column of
               percentages, and nothing saying that one of them is a model's
               opinion of its own homework. The row marks it the same two ways
               the card does — the number loses the ink, and a word says why. */
            const opinion = scoreIsAnOpinion(entry);
            return (
              <button
                type="button"
                key={entry.runId}
                className="evalpick"
                data-current={entry.runId === report.runId || undefined}
                onClick={() => onPick(entry.runId)}
                title={
                  opinion
                    ? `Run ${entry.runId} was graded by a model, so its score is a judgement rather than a reading.`
                    : `Run ${entry.runId}, graded by ${entry.metric}.`
                }
              >
                <span className="evalpick__id mono">#{entry.runId}</span>
                <span className="evalpick__meta">
                  {opinion ? 'judged by a model' : entry.metric}
                  {entry.promptIsDefault ? ' · baseline' : ' · custom prompt'}
                </span>
                <span className="evalpick__score mono" data-opinion={opinion || undefined}>
                  {entry.score === null
                    ? `${entry.graded}/${entry.planned}`
                    : `${(entry.score * 100).toFixed(0)}%`}
                </span>
              </button>
            );
          })}
        </div>
      ) : null}

      <EvalReportBody report={report} />
    </div>
  );
}

/** A ledger value, printed as the engine stored it. */
function showValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'string') return value.length > 40 ? `${value.slice(0, 39)}…` : value;
  return JSON.stringify(value);
}
