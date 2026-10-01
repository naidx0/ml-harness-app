/**
 * THE PROPOSAL SURFACE — what the harness intends to do, what it will cost,
 * and what could go wrong.
 *
 * `docs/THE_PROPOSAL_LOOP.md` §3, in Max's words: "This is what they want.
 * This is our proposed build. This is what it looks like — visual diagram.
 * This is what you need. If they say yes, we launch an intensive workflow
 * storm." An actual outcome, not an answer.
 *
 * ══ THE TRAP, WHICH THE SPEC NAMES BEFORE WE WALK INTO IT ══════════════════
 *
 * "A proposal contains estimates. Estimates are numbers. **Our first invariant
 * is that we never invent a number**… 'This will take about forty minutes and
 * cost roughly fourteen cents' is exactly the kind of sentence that makes a
 * proposal feel trustworthy and is exactly the kind of number we would be
 * making up."
 *
 * The instruction for this surface is stronger than "show provenance": **a
 * cost with no provenance must be impossible to render, not merely
 * discouraged.** Three things make that true here, and none of them is a rule
 * a reviewer has to remember:
 *
 * 1. `app/build.py` cannot CONSTRUCT one. No constructor there accepts a bare
 *    magnitude; MEASURED comes out of a `Reading` that read something, INFERRED
 *    is arithmetic on estimates that already exist, and UNKNOWN carries no
 *    number at all.
 * 2. `lib/engine/build.ts` cannot READ one. An estimate missing its provenance,
 *    a MEASURED one with no reading, or an UNKNOWN one carrying a number makes
 *    the whole build unreadable, and an unreadable build is not drawn as a plan.
 * 3. `Estimate` in this file's props is a discriminated union whose UNKNOWN arm
 *    **has no `value` field**. `estimate.value` does not compile until the code
 *    has narrowed on the provenance, so the branch that prints a magnitude
 *    always has the provenance in hand. There is one place a number is printed
 *    — `Magnitude` — and it takes the tag as a required prop.
 *
 * An UNKNOWN cost renders as the word "unknown", the reason, and **how to find
 * out**, which is the engine's `find_out_by` and is required by it. It carries
 * NO provenance tag, because Graphite page 13 is explicit that "a tag never
 * renders without a number" — a tag on an absence would be a badge on nothing.
 * "I do not know how long this takes, let me run it on 1% and find out" is
 * worth more than a guess, and it is the only version consistent with
 * everything else in this product.
 *
 * ══ THE FOUR DIMENSIONS ARE ALWAYS ALL FOUR ════════════════════════════════
 *
 * `app/build.py`: "A dimension left out would read as free, which is why none
 * of them is optional and why 'unknown' is one line to write." So the table
 * below has four rows on every card, whatever the plan is.
 *
 * ══ WHY THE REFUSAL IS ON THIS SURFACE TOO ═════════════════════════════════
 *
 * `propose_build` can answer "I know what should happen and I cannot yet write
 * a build that does it", with what is missing. That is not a failure and must
 * not render as one — `app/tools/propose.py` calls it "a refusal to draw a
 * plan that could not run". It renders here, with the same weight as a plan,
 * because a product that quietly shows nothing when it cannot help is a
 * product that has taught you not to ask.
 */

import { useState } from 'react';
import type { ReactNode } from 'react';
import type {
  Build,
  Cost,
  CostDimension,
  Estimate,
  Proposal,
  ProposalRefusal,
  Step,
} from '../lib/engine/build';
import { COST_DIMENSIONS, DIMENSION_LABEL } from '../lib/engine/build';
import type { Storm, StormDeviation } from '../lib/engine/storm';
import type { ToolControl } from '../lib/engine/types';
import type { ApproveOutcome } from '../lib/useStorms';
import type { Denial } from '../lib/useApprovals';
import { ApprovalCard, ApprovalRecord as ApprovalRecordRow, DeviationBlock } from './Approval';
import { BuildDiagram, StepDetail } from './BuildDiagram';
import { StormProgress } from './StormCard';
import { Icon, type IconName } from './Icon';
import { ProvenanceTag } from './primitives';

/* ── The card ─────────────────────────────────────────────────────────────── */

export function ProposalCard({
  proposal,
  proposalArgs,
  threadId,
  tools,
  storm,
  denial,
  onApprove,
  onDeny,
  onForgetDenial,
  onCancel,
}: {
  proposal: Proposal;
  /** The arguments `propose_build` was called with. `POST /api/storms` takes
   *  THESE and the fingerprint, never a plan, so the harness re-proposes and
   *  proves the object it is about to run is the one that was approved. */
  proposalArgs: Record<string, unknown>;
  threadId: number | null;
  tools: Map<string, ToolControl>;
  /** The storm recorded against this exact plan, once there is one. Its
   *  `build` is the manifest's blueprint — the same object, so the picture does
   *  not change when it starts running; only the nodes' states do. */
  storm: Storm | null;
  denial: Denial | null;
  onApprove: (
    fingerprint: string,
    proposalArgs: Record<string, unknown>,
    build: unknown,
  ) => Promise<ApproveOutcome>;
  onDeny: (fingerprint: string, reason: 'clicked' | 'timeout') => void;
  onForgetDenial: (fingerprint: string) => void;
  onCancel: (stormId: number) => void;
}) {
  const [open, setOpen] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [deviation, setDeviation] = useState<StormDeviation | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  /* THE PICTURE COMES FROM THE STORM ONCE THERE IS ONE. Not a merge and not a
     second copy: `app/storm.py` keeps `Build.as_dict()` verbatim as the
     manifest's blueprint precisely so that "after a restart the picture has to
     come from somewhere, and it comes from here rather than from a re-proposal
     that might differ". */
  const build = storm ? storm.build : proposal.build;

  const step = selected ? build.steps.find((entry) => entry.id === selected) ?? null : null;

  async function allow() {
    if (threadId === null) return;
    setAsking(true);
    setRefused(null);
    setDeviation(null);
    /* `proposal.raw`, not `build`: the engine compares against `Build.as_dict()`
       keys and the parsed object does not have them. See `Proposal.raw`. */
    const outcome = await onApprove(proposal.approve, proposalArgs, proposal.raw);
    setAsking(false);
    if (outcome.kind === 'deviated') setDeviation(outcome.deviation);
    if (outcome.kind === 'refused') setRefused(outcome.detail);
  }

  return (
    <div className="card card--proposal" data-open={open}>
      <div className="card__head">
        <Icon name="commit" />
        <span className="card__kicker">Proposal</span>
        {open ? null : <span className="card__clip">{build.title}</span>}
        <span className="card__headright">
          <span className="mono card__outcome">{build.forOutcome}</span>
          <button
            type="button"
            className="iconbtn"
            aria-label={open ? 'Collapse the proposal' : 'Expand the proposal'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Icon name="chevright" size={14} rotate={open ? 90 : 0} />
          </button>
        </span>
      </div>

      {open ? (
        <div className="card__body">
          <div className="card__headline">
            <span>{build.title}</span>
            <span className="mono card__outcome">{build.id}</span>
          </div>
          <p className="card__text">{build.because}</p>

          <Section title="The plan" icon="branch" hint={planHint(build)}>
            <BuildDiagram
              build={build}
              tools={tools}
              storm={storm}
              selected={selected}
              onSelect={setSelected}
            />
            {step ? (
              <StepDetail
                build={build}
                step={step}
                control={tools.get(step.tool) ?? null}
                live={storm?.steps.get(step.id) ?? null}
                onSelect={setSelected}
              />
            ) : (
              <p className="plan__prompt">
                Every box is a step in this plan and nothing else. Choose one to
                see the tool it runs, the arguments it runs with, and how it
                will be known to have worked.
              </p>
            )}
          </Section>

          <Section
            title="What it will cost"
            icon="gauge"
            hint="in your model’s tokens, your model’s requests, wall-clock time and disk"
          >
            <CostTable cost={build.cost} />
            <PerStepCost build={build} tools={tools} onSelect={setSelected} />
          </Section>

          <Section title="Where it runs" icon="folder">
            <Sandbox build={build} />
          </Section>

          {build.risks.length > 0 ? (
            <Section title="What could go wrong" icon="alert">
              {build.risks.map((risk) => (
                <p className="risk" key={risk.what}>
                  <span className="risk__what">{risk.what}</span>
                  <span className="risk__do">{risk.what_we_do}</span>
                </p>
              ))}
            </Section>
          ) : null}

          {build.questions.length > 0 ? (
            <Section
              title="What we need from you"
              icon="user"
              hint="the harness runs the steps; these are the parts only you can answer"
            >
              {build.questions.map((question) => (
                <div className="question" key={question.ask}>
                  <p className="question__ask">{question.ask}</p>
                  <p className="question__why">{question.why}</p>
                  {question.fact ? (
                    <p className="question__fact">
                      <span className="mono">{question.fact}</span>
                      <span>
                        answered through <span className="mono">{question.answered_by}</span>
                      </span>
                    </p>
                  ) : null}
                </div>
              ))}
            </Section>
          ) : null}

          <div className="planexit">
            <Icon name="check" size={12} />
            <span>
              <b>Done when</b> {build.exitCriterion.stated}
            </span>
          </div>

          {/* The approval, last, because a person should have read the plan
              before the buttons are the nearest thing to their cursor. */}
          {storm ? (
            <StormProgress storm={storm} onCancel={onCancel} />
          ) : denial ? (
            <ApprovalRecordRow
              answer="deny"
              reason={denial.reason}
              at={denial.at}
              fingerprint={proposal.approve}
              note={
                denial.reason === 'timeout'
                  ? 'Nothing ran, and nothing was recorded on the engine — a denial starts nothing, so there is no row for it to write.'
                  : 'Nothing ran. A denial starts nothing, so the engine has no row for it; this record is your browser’s.'
              }
              onAskAgain={() => onForgetDenial(proposal.approve)}
            />
          ) : (
            <ApprovalCard
              asks={
                <>
                  Run this plan: <b>{build.title}</b>
                </>
              }
              facts={approvalFacts(build, proposal)}
              disabled={asking || threadId === null}
              onAnswer={(answer, reason) => {
                if (answer === 'deny') onDeny(proposal.approve, reason);
                else void allow();
              }}
              footnote={
                <>
                  Approving binds this exact plan —{' '}
                  <span className="mono">{proposal.approve.slice(0, 16)}</span>, the
                  hash of everything above.{' '}
                  <b>What is sent is not the plan.</b> The harness is handed the
                  question this proposal was made from and that hash, proposes
                  again, and refuses to record anything if what it would run now
                  is not what you are looking at — so the object that executes is
                  always one it built and validated itself.
                  {threadId === null ? (
                    <>
                      <br />A storm belongs to a conversation, and this proposal
                      was run from the Controls panel with no thread open. Open a
                      thread and propose there to be able to approve it.
                    </>
                  ) : null}
                </>
              }
            >
              {deviation ? (
                <>
                  <DeviationBlock notes={deviation.changed} />
                  <p className="deviation__what">
                    {deviation.whatNow} You approved{' '}
                    <span className="mono">{deviation.approved.slice(0, 12)}</span>;
                    the plan now is{' '}
                    <span className="mono">{deviation.now.slice(0, 12)}</span>.
                    Nothing was recorded and nothing ran.
                  </p>
                </>
              ) : null}
              {refused ? (
                <p className="deviation__what deviation__what--refused">{refused}</p>
              ) : null}
            </ApprovalCard>
          )}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The refusal. Same weight as a plan, and it names the door.
 *
 * `app/tools/propose.py`: "This is a refusal to draw a plan that could not
 * run, not a failure. Supply what is named above and ask again, or do the part
 * that is yours." A plan that cannot execute is the exact failure the
 * proposal object exists to prevent, so a proposer that cannot run the thing
 * refuses to draw it — and the interface has to make that read as competence.
 */
export function ProposalRefusalCard({ refusal }: { refusal: ProposalRefusal }) {
  const [openWhy, setOpenWhy] = useState(false);
  const [openCovered, setOpenCovered] = useState(false);
  const defect = refusal.error === 'proposer_defect';
  /* `needs` carries two different things depending on why the proposer
     declined: the ARGUMENT it could not plan without (`eval_path`,
     `input_field`), or — when no proposer covers the outcome at all — the
     OUTCOME itself. The first is something a person can supply and the second
     is not, so an outcome repeated under a heading that says "Needs" reads as
     a missing input the reader is being asked for. It is already the sentence
     above and the badge in the header; here it is dropped. */
  const missing = refusal.needs.filter((need) => need !== refusal.outcome);
  const detail = (refusal.detail || '').trim();
  const shortDetail =
    detail.length > 320 && !openWhy ? `${detail.slice(0, 300).trim()}…` : detail;
  return (
    <div className="card card--proposal card--refusal">
      <div className="card__head">
        <Icon name="info" />
        <span className="card__kicker">
          {defect ? 'Proposal withheld' : 'No plan I could stand behind'}
        </span>
        <span className="card__headright">
          {refusal.outcome ? (
            <span className="mono card__outcome">{refusal.outcome}</span>
          ) : null}
        </span>
      </div>
      <div className="card__body">
        <p className="card__text">{shortDetail}</p>
        {detail.length > 320 ? (
          <button
            type="button"
            className="refusal__more"
            onClick={() => setOpenWhy((was) => !was)}
          >
            {openWhy ? 'Show less' : 'Read full reason'}
          </button>
        ) : null}
        {missing.length > 0 ? (
          <div className="refusal__needs">
            <span className="refusal__needslabel">Needs</span>
            {missing.map((need) => (
              <span className="refusal__need mono" key={need}>
                {need}
              </span>
            ))}
          </div>
        ) : null}
        {refusal.help ? <p className="card__absent">{refusal.help}</p> : null}
        {refusal.coveredOutcomes.length > 0 ? (
          <div className="refusal__covered">
            <button
              type="button"
              className="refusal__more"
              aria-expanded={openCovered}
              onClick={() => setOpenCovered((was) => !was)}
            >
              {openCovered
                ? 'Hide outcomes this harness can plan for'
                : `${refusal.coveredOutcomes.length} outcomes this harness can plan for`}
            </button>
            {openCovered ? (
              <p className="card__absent">
                {refusal.coveredOutcomes.map((outcome, index) => (
                  <span key={outcome}>
                    {index > 0 ? ', ' : ''}
                    <span className="mono">{outcome}</span>
                  </span>
                ))}
                .
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ── Cost ─────────────────────────────────────────────────────────────────── */

export function CostTable({ cost }: { cost: Cost }) {
  return (
    <div className="cost">
      {COST_DIMENSIONS.map((dimension) => (
        <EstimateRow key={dimension} dimension={dimension} estimate={cost[dimension]} />
      ))}
    </div>
  );
}

function EstimateRow({
  dimension,
  estimate,
}: {
  dimension: CostDimension;
  estimate: Estimate;
}) {
  const [open, setOpen] = useState(false);
  const derived = estimate.from.length > 0;

  return (
    <div className="cost__row" data-provenance={estimate.provenance}>
      <span className="cost__dim">
        {DIMENSION_LABEL[dimension]}
        <span className="cost__field mono">{dimension}</span>
      </span>

      <span className="cost__value">
        {estimate.provenance === 'UNKNOWN' ? (
          /* No tag, no number, no dash standing in for one. Page 13.5: "None of
             them is a zero, a dash with no explanation, or a plausible figure
             in italics." */
          <span className="cost__unknown">unknown</span>
        ) : (
          <Magnitude
            value={estimate.value}
            unit={estimate.unit}
            provenance={estimate.provenance}
          />
        )}
      </span>

      <span className="cost__how">
        {estimate.provenance === 'UNKNOWN' ? (
          <>
            <span>{estimate.how}</span>
            {/* The spec's own preferred answer, and the engine requires it. */}
            <span className="cost__findout">
              <Icon name="play" size={11} />
              To find out: {estimate.findOutBy}
            </span>
          </>
        ) : (
          <span>{estimate.how}</span>
        )}
        {derived ? (
          <button type="button" className="cost__more" onClick={() => setOpen(!open)}>
            {open ? 'hide' : `from ${estimate.from.length}`}
          </button>
        ) : null}
      </span>

      {open && derived ? (
        <div className="cost__from">
          {estimate.from.map((input, index) => (
            <Derivation key={index} estimate={input} depth={0} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The derivation, shown — because `docs/THE_PROPOSAL_LOOP.md` says an inference
 * must show it. Recursive, because `Estimate.summed()` of inferences of
 * measurements is three levels deep and the bottom level is the only one that
 * read anything.
 */
function Derivation({ estimate, depth }: { estimate: Estimate; depth: number }) {
  return (
    <div className="deriv" data-depth={Math.min(depth, 2)}>
      <span className="deriv__value">
        {estimate.provenance === 'UNKNOWN' ? (
          <span className="cost__unknown">unknown</span>
        ) : (
          <Magnitude
            value={estimate.value}
            unit={estimate.unit}
            provenance={estimate.provenance}
          />
        )}
      </span>
      <span className="deriv__how">{estimate.how}</span>
      {estimate.provenance === 'MEASURED' ? (
        <span className="deriv__read">read at {estimate.reading.at}</span>
      ) : null}
      {estimate.from.map((input, index) => (
        <Derivation key={index} estimate={input} depth={depth + 1} />
      ))}
    </div>
  );
}

/**
 * THE ONLY PLACE A COST MAGNITUDE IS PRINTED, and it will not compile without
 * a provenance beside it.
 *
 * `provenance` is required and is not defaulted. That is the whole point: a
 * caller who has a number but no origin has nothing to pass, and there is no
 * other component in this file that prints one.
 */
function Magnitude({
  value,
  unit,
  provenance,
}: {
  value: number;
  unit: string;
  provenance: 'MEASURED' | 'INFERRED';
}) {
  return (
    <>
      <span className="cost__num">{value.toLocaleString()}</span>
      {/* §3.6: "Units always attached, always --ink-3, always one space", and
          "the unit is never the same colour as the value". The unit is the
          engine's own word for the dimension, not one chosen here. */}
      <span className="cost__unit">{unit}</span>
      <ProvenanceTag tag={provenance} />
    </>
  );
}

/** Which steps carry which part of the bill. Collapsed, because the total is
 *  the answer and the breakdown is the check. */
function PerStepCost({
  build,
  tools,
  onSelect,
}: {
  build: Build;
  tools: Map<string, ToolControl>;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="perstep">
      <button
        type="button"
        className="perstep__toggle"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        {open ? 'Hide' : 'Show'} the {build.steps.length} steps this total is made of
      </button>
      {open ? (
        <div className="perstep__body">
          {build.steps.map((entry) => (
            <div className="perstep__step" key={entry.id}>
              <button
                type="button"
                className="perstep__name"
                onClick={() => onSelect(entry.id)}
              >
                <span className="mono">{entry.id}</span>
                <span className="perstep__tool">
                  {tools.get(entry.tool)?.label ?? entry.tool}
                </span>
              </button>
              <CostTable cost={entry.cost} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ── The sandbox ──────────────────────────────────────────────────────────── */

/**
 * `docs/THE_PROPOSAL_LOOP.md`: a sandbox is "reproducible, disposable, and
 * cannot reach anything it was not given". The third is the one that stops
 * being a promise and becomes a fact — "a sandbox that has no egress cannot
 * leak, whatever the model says" — so the egress line is the loudest row here,
 * and it is the only place on this card that takes an amber.
 */
function Sandbox({ build }: { build: Build }) {
  const env = build.environment;
  return (
    <div className="sandbox">
      <div className="sandbox__row">
        <span className="sandbox__k">Sandbox</span>
        <span className="sandbox__v">{env.name}</span>
      </div>
      <div className="sandbox__row">
        <span className="sandbox__k">Working directory</span>
        <span className="sandbox__v mono">{env.working_dir}</span>
      </div>
      <div className="sandbox__row" data-egress={env.egress ? 'yes' : 'no'}>
        <span className="sandbox__k">Can reach the network</span>
        <span className="sandbox__v">
          {env.egress ? (
            <>
              <span className="sandbox__egress">yes</span> — {env.egress_reason}
            </>
          ) : (
            <>
              no — nothing in this plan can leave this machine, whatever the
              model says
            </>
          )}
        </span>
      </div>
      {env.python ? (
        <div className="sandbox__row">
          <span className="sandbox__k">Python</span>
          <span className="sandbox__v mono">{env.python}</span>
        </div>
      ) : null}
      {env.installs.length > 0 ? (
        <div className="sandbox__row">
          <span className="sandbox__k">Installs</span>
          <span className="sandbox__v mono">{env.installs.join(', ')}</span>
        </div>
      ) : null}
      {env.data.length > 0 ? (
        <div className="sandbox__data">
          <span className="sandbox__k">Data, as it was when this was planned</span>
          {env.data.map((snapshot) => (
            <div className="snapshot" key={snapshot.path}>
              <span className="snapshot__path mono">{snapshot.path}</span>
              <span className="snapshot__size">
                <span className="cost__num">{snapshot.bytes.toLocaleString()}</span>
                <span className="cost__unit">bytes</span>
                {/* The size came through `Reading.of_file_size` — a stat() on
                    this filesystem — so it is MEASURED and says so. */}
                <ProvenanceTag tag="MEASURED" />
              </span>
              <span className="snapshot__how">{snapshot.how}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ── Small parts ──────────────────────────────────────────────────────────── */

function Section({
  title,
  icon,
  hint,
  children,
}: {
  title: string;
  icon: IconName;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="plansec">
      <div className="plansec__head">
        <Icon name={icon} size={12} />
        <span className="plansec__title">{title}</span>
        {hint ? <span className="plansec__hint">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

function planHint(build: Build): string {
  const parallel = build.waves.filter((wave) => wave.length > 1).length;
  const steps = `${build.steps.length} step${build.steps.length === 1 ? '' : 's'}`;
  const waves = `${build.waves.length} wave${build.waves.length === 1 ? '' : 's'}`;
  if (parallel === 0) return `${steps}, ${waves}, one after another`;
  return `${steps} in ${waves} — ${parallel} of them run more than one thing at once`;
}

/**
 * The facts of the call, for the approval card. Page 15.2: "carries the tool's
 * own arguments rather than a summary of them". One level up, the call is a
 * build, so these are the build's own load-bearing fields — never a
 * paraphrase, and never a number this file computed.
 */
function approvalFacts(
  build: Build,
  proposal: Proposal,
): { key: string; value: ReactNode; tone?: 'plain' | 'warn' }[] {
  return [
    {
      key: 'Runs',
      value: (
        <>
          {build.steps.length} step{build.steps.length === 1 ? '' : 's'} in{' '}
          {build.waves.length} wave{build.waves.length === 1 ? '' : 's'} —{' '}
          <span className="mono">
            {build.steps.map((step) => step.tool).join(', ')}
          </span>
        </>
      ),
    },
    {
      key: 'In',
      value: (
        <>
          {build.environment.name}
          {build.environment.egress ? (
            <span className="approval__warn"> · can reach the network</span>
          ) : (
            <span> · no network</span>
          )}
        </>
      ),
      tone: build.environment.egress ? 'warn' : 'plain',
    },
    {
      key: 'Costs',
      value: <CostLine cost={build.cost} />,
    },
    {
      key: 'Answers',
      value: <span className="mono">{proposal.outcome || build.forOutcome}</span>,
    },
    {
      key: 'Done when',
      value: build.exitCriterion.stated,
    },
  ];
}

/** The four dimensions on one line, each still wearing its origin. An unknown
 *  part says so here too: `Cost.summed` makes a total UNKNOWN wherever any part
 *  of it is, because "a total that quietly drops the term nobody could price is
 *  the most dangerous number a proposal could carry". */
function CostLine({ cost }: { cost: Cost }) {
  return (
    <span className="costline">
      {COST_DIMENSIONS.map((dimension) => {
        const estimate = cost[dimension];
        return (
          <span className="costline__item" key={dimension}>
            <span className="costline__dim">{shortDimension(dimension)}</span>
            {estimate.provenance === 'UNKNOWN' ? (
              <span className="cost__unknown">unknown</span>
            ) : (
              <Magnitude
                value={estimate.value}
                unit={estimate.unit}
                provenance={estimate.provenance}
              />
            )}
          </span>
        );
      })}
    </span>
  );
}

function shortDimension(dimension: CostDimension): string {
  switch (dimension) {
    case 'model_tokens':
      return 'tokens';
    case 'model_requests':
      return 'requests';
    case 'wall_clock':
      return 'time';
    case 'disk':
      return 'disk';
  }
}

/** Exported so the transcript can name the sentences a card has already said
 *  and the model's prose does not have to repeat them. See `Transcript.tsx`. */
export function sentencesOnProposalCard(proposal: Proposal): string[] {
  const build = proposal.build;
  return [
    build.because,
    build.say,
    build.exitCriterion.stated,
    proposal.note,
    ...build.steps.map((step: Step) => step.why),
    ...build.risks.map((risk) => `${risk.what} ${risk.what_we_do}`),
  ].filter((entry): entry is string => Boolean(entry && entry.trim()));
}
