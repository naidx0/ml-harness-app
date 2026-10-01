/**
 * The transcript — DESIGN_SYSTEM §9.1 (chat message), §9.21 (density),
 * DESIGN_DIRECTIVES §4 (icons on tool rows).
 *
 * Everything here is folded out of the event log by `lib/transcript.ts`. There
 * are no fixtures in this file and no branch that renders something the engine
 * did not send. A row that is on screen is a row that is on disk.
 *
 * THE TWO RULES THAT SHAPE IT
 *
 * 1. **Heavy results never stream into the chat column** (§9.1). A tool call
 *    is a one-line row that expands; a training run is a one-line row that
 *    counts its log lines rather than printing them. "Streaming raw training
 *    logs into the chat column is forbidden; it is the single fastest way to
 *    destroy the calm the reference tools achieve."
 * 2. **Never raw JSON.** A tool result expands into a table (see
 *    `ResultView`), which is the same information without the punctuation.
 *
 * A tool row is labelled with the registry's own `verb` — "read this machine's
 * hardware", "check whether train rows appear in the eval set" — so the row
 * says what the harness *did*, not which Python function ran. When the
 * registry has not loaded, the row falls back to the tool's name rather than
 * inventing a sentence for it.
 *
 * THE BUBBLE CORRECTION, MADE. The previous build carried this note: "Codex
 * bubbles the USER side and leaves the assistant full-width. That change is
 * not made in this step; it is a design change, this is the wiring step." This
 * is the design step, and it is made. The user message is a rounded grey
 * bubble inset from the right; the assistant message is plain full-width prose
 * with no bubble, no avatar and no name label. The 2px role markers are gone
 * with the rule that asked for them.
 *
 * ══ THE VERBATIM ECHO, AND WHERE IT ACTUALLY COMES FROM ════════════════════
 *
 * Max, from a screenshot of the running app: the verdict card states the
 * blocked fact and the reasoning, and then the model repeats it word for word
 * underneath. His note is "the text can be a bit much", and it has a cause
 * rather than a styling problem.
 *
 * THE CAUSE IS NOT IN THIS FILE AND IS NAMED HERE SO THE NEXT READER DOES NOT
 * RE-DERIVE IT. `app/conductor.py` hands every tool result back to the model
 * inside a data envelope, so the model receives `run_diagnosis`'s `say` and
 * `help` verbatim — and `app/instructions/cond_tools_available.md` then tells
 * it: *"`run_diagnosis` walks the tree itself and returns the verdict; you
 * report what it returned."* A model that is told to report what a field
 * contains reports what that field contains, character for character. The
 * engine is meanwhile rendering the same two strings on the card. One sentence
 * arrives twice because two different systems were each told to say it.
 *
 * The real repair is one line in that instruction — the card already carries
 * the engine's sentence, so the model should be told to add what the card
 * cannot (what it means for this person, what it would do next) and never to
 * restate `say`. That file is `app/`, which this lane does not own; it is
 * reported rather than edited.
 *
 * WHAT THIS FILE DOES ABOUT IT, AND WHY THIS IS NOT STYLING AROUND IT. The
 * card is the durable, checkable rendering — it survives a restart, it carries
 * the ledger and the origins, and it is what a reader six months later comes
 * back to. A prose paragraph whose every sentence is already on a card above
 * it, character for character, carries no information at all. So it is not
 * rendered twice. The match is EXACT, per sentence, after whitespace and case
 * are normalised — never a paraphrase judgement, because deciding that two
 * differently-worded sentences mean the same thing is precisely the kind of
 * call this product does not let a renderer make. A model that says something
 * of its own keeps every word of it.
 *
 * THE SAME MACHINERY NOW POINTS THE OTHER WAY TOO, AND ONLY UPWARDS.
 * `conductor.verdict` arrives AFTER the reply it annotates, so a rule that
 * suppressed prose because of a card below it would be deleting a sentence the
 * reader had already started reading — and deletion is the thing the engine
 * just stopped doing, at a measured cost of one interrupted turn in seven. So
 * the verdict card never touches the reply. What it does instead is stand its
 * OWN engine half down when a diagnosis card ABOVE it is already drawing that
 * outcome, which is every turn where the model ran `run_diagnosis`, because
 * the two are one payload. `outcomesAlreadyOnCards` is that lookup, and
 * `EngineVerdictCard` carries the argument.
 */

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { ToolControl } from '../lib/engine/types';
import type { SubAgentItem } from '../lib/transcript';
import type {
  AssistantItem,
  ErrorItem,
  NoticeItem,
  StormItem,
  ToolItem,
  TrainItem,
  TranscriptItem,
  TurnItem,
  UserItem,
} from '../lib/transcript';
import { PlanDiff } from './PlanDiff';
import { parseMarkdown, type Block, type Span } from '../lib/markdown';
import { isFactOrigin, readDiagnosis, type FactOrigin } from '../lib/engine/facts';
import { readProposal, readProposalRefusal } from '../lib/engine/build';
import {
  readEvalComparison,
  readEvalReport,
  readEvalRefusal,
} from '../lib/engine/evals';
import { readPromptAttempt, readPromptRefusal } from '../lib/engine/prompts';
import type { Storm } from '../lib/engine/storm';
import type { DenialsState } from '../lib/useApprovals';
import type { ApproveOutcome } from '../lib/useStorms';
import { Icon, groupIcon } from './Icon';
import { ResultView } from './ResultView';
import { DiagnosisCard, EngineVerdictCard } from './DiagnosisCard';
import { QuestionCard, type Question } from './QuestionCard';
import { ApprovalCard, readApprovalRequest } from './ApprovalCard';
import { WhatChangedCard } from './WhatChangedCard';
import { toolRowDrawsACard } from './cards';
import { ToolStrip } from './ToolStrip';
import { howToDrawEachRow } from '../lib/foldTheToolRows';
import {
  EvalCard,
  EvalCompareCard,
  EvalRefusalCard,
  EvalRunRow,
} from './EvalCard';
import { PromptCard, PromptRefusalCard } from './PromptCard';
import { ChunkingSweepCard, RetrieverRecallCard } from './RetrievalCard';
import {
  readChunkingSweep,
  readRecallReport,
  type ChunkingSweep,
} from '../lib/engine/retrieval';
import { CarveCard, CarveRefusalCard } from './CarveCard';
import {
  SynthesisCard,
  VerificationCard,
  VerificationSampleCard,
} from './SynthesisCard';
import {
  readCarve,
  readCarveRefusal,
  readSynthesis,
  readVerificationRecord,
  readVerificationSample,
} from '../lib/engine/datawork';
import {
  ProposalCard,
  ProposalRefusalCard,
  sentencesOnProposalCard,
} from './ProposalCard';
import type { RunTool } from './NextStep';
import { OriginTag, Strip } from './primitives';

/** §9.21. Three levels, and they govern how much of a turn is shown — never
 *  how tightly anything is set, and never what the product claims. */
/** ONE LEVEL. Max, 2026-09-10: "Remove the summary in normal. That doesn't
 *  make any sense. Just have it on normal always."
 *
 *  Three levels became two when Verbose went - its only job was seeding every
 *  tool row open, which is a click on the row that wants it. The same argument
 *  finished the job: Summary's only job was HIDING a turn's arguments, which
 *  is the same click. The type keeps its name and its single member so the
 *  prop threading stays honest about what it carries, and so the compiler
 *  finds anything that still branches on a level that no longer exists. */
export type Density = 'normal';

export function Transcript({
  items,
  streaming,
  tools,
  density,
  threadId,
  runTool,
  storms,
  denials,
  onApprove,
  onCancelStorm,
  question,
  frontierExhausted,
  workspaceRoot,
  onApproveTool,
  onAnswered,
  stageAnchor = null,
  stageNode = null,
  onStage,
  board,
  onEffectsReverted,
  onOpenThread,
  permission = 'ask',
}: {
  items: TranscriptItem[];
  streaming: boolean;
  tools: Map<string, ToolControl>;
  density: Density;
  /**
   * THE STAGE, SIZE D — docs/PHASES.md "The Stage". A finished tool row whose
   * result the Stage can draw gains an opener; the row it is open under is
   * `stageAnchor`, and `stageNode` is the Stage itself, composed by the shell
   * so that this inline size, the split and the window show one selection.
   * The transcript owns neither the state nor the data: it places the node
   * under the row where the result landed, which is what makes the transcript
   * the record.
   */
  stageAnchor?: string | null;
  stageNode?: ReactNode;
  onStage?: (anchor: string | null) => void;
  /** The sub-agent board, composed by the shell. Rendered at the end of the
   *  column so it scrolls with the conversation it belongs to. */
  board?: ReactNode;
  /** CS5 — after Revert ticks, refresh the thread row so Plan pane updates. */
  onEffectsReverted?: () => void;
  /** Open a sub-agent's own conversation from its row in the stream. */
  onOpenThread?: (threadId: number) => void;
  /** Which conversation. Sent with every control the diagnosis card runs, so a
   *  measurement lands in this thread rather than in machine scope. */
  threadId: number | null;
  runTool: RunTool;
  /** The storm recorded against a build fingerprint, when there is one. A
   *  proposal that has been approved shows its own storm rather than the three
   *  buttons again. */
  storms: (fingerprint: string) => Storm | null;
  /** The one answer the engine has no row for. See `lib/useApprovals.ts`. */
  denials: DenialsState;
  onApprove: (
    fingerprint: string,
    proposalArgs: Record<string, unknown>,
    build: unknown,
  ) => Promise<ApproveOutcome>;
  onCancelStorm: (stormId: number) => void;
  /**
   * THE QUESTION THE ENGINE PICKED — `GET /api/next_step`, `app/asking.py`.
   *
   * Null when the engine has not answered, when it would not, or when the
   * frontier has nothing answerable left. `QuestionCard` falls back to its own
   * client-side derivation in that case, which is what it did before this prop
   * existed; the engine's card is the path and the derivation is the fallback,
   * never the other way round.
   *
   * It carries no answer and no origin. The card sends the person's answer to
   * `POST /api/tools/{name}` — `state_facts` for a field, the named measuring
   * tool for a pointer — and that route hard-codes `actor=user`. Nothing on
   * this prop can change what an answer is worth.
   */
  question: Question | null;
  /** THE ENGINE ANSWERED AND HAD NOTHING TO ASK. Distinct from `question` being
   *  null because the engine has not answered at all - see `App.tsx`. When this
   *  is true the fallback derivation is SUPPRESSED, because the engine has just
   *  said the frontier is exhausted and a card derived from the frozen snapshot
   *  would contradict the ledger. */
  frontierExhausted?: boolean;
  /** The open project's folder, offered on the question card's path fields. */
  workspaceRoot?: string | null;
  /**
   * Approve one tool the model was refused, and run it AS THE PERSON.
   *
   * Absent means no approval card is drawn at all, which is what keeps
   * every existing caller of this component unchanged.
   */
  onApproveTool?: (
    name: string,
    args: Record<string, unknown>,
    threadId: number | null,
  ) => Promise<{ ok: boolean; result: unknown; error: string | null }>;
  /** An answer landed. The shell re-asks the engine; this component does not,
   *  because a transcript is not entitled to spend the user's tokens. */
  onAnswered?: (fact: string) => void;
  /** AU1 — permission `full` hides QuestionCard (zero-ask bypass). */
  permission?: 'ask' | 'measure' | 'write' | 'full';
}) {
  const lastAssistant = lastIndexOfAssistant(items);
  /* WHERE THE QUESTION GOES: under the LAST diagnosis in the thread, and under
     no other.

     A question is derived from the evidence as it stands NOW. Every diagnosis
     card above the last one is a record of what the engine thought at the time,
     and hanging a live question off one of them would ask about a frontier that
     has already moved — the card would offer to measure something two turns
     after it was measured. Scrolling back has to show what happened, not a
     control that acts on the present. */
  const lastDiagnosis = useMemo(() => lastIndexOfDiagnosis(items), [items]);
  /* Every sentence a card in this thread already states, and the index of the
     row that first stated it. A model can only echo what it has already been
     handed, so "already said" means "said by a card ABOVE this reply". */
  const saidAt = useMemo(() => sentencesAlreadyOnCards(items), [items]);
  /* Which OUTCOME each diagnosis card in this thread is showing, and where.
     `conductor.verdict` and a `run_diagnosis` card on the same turn are built
     from one payload — `_Standing` is replaced by any tool result stamped
     `decided_by: app/diagnosis.py` — so the second one to render would repeat
     the first's sentence, its gate ledger and its controls. The engine's own
     identifier is the join: exact, checkable in `docs/diagnosis_engine.yaml`,
     and no judgement about whether two things "mean the same". */
  const outcomeAt = useMemo(() => outcomesAlreadyOnCards(items), [items]);

  /* WHICH TOOL ROWS COLLAPSE INTO A STRIP. Max: "the tool calling, while
     it's nice and transparent, is too loud - apart from question asks and
     diagnosis and so on... showing just icons for the thinking path, and
     when the icon is clicked on we see the tool call in detail."

     The "apart from" is enforced in `foldTheToolRows`, which breaks a run
     on any row that draws a card, so a diagnosis can never end up behind an
     icon. The predicate is the SAME reader the rows use one screen down. */
  const folded = useMemo(
    () =>
      howToDrawEachRow(items, (index) => {
        const row = items[index];
        return row.kind === 'tool'
          ? !toolRowDrawsACard(row as ToolItem, onApproveTool !== undefined)
          : false;
      }),
    [items, onApproveTool],
  );
  /* Which folded calls the person has opened, by `item.key`. Held here
     rather than in the strip because the ROW is what expands - the strip
     draws no tool row of its own, so a second copy of an approval button
     cannot exist to disagree with the first. */
  const [openedTools, setOpenedTools] = useState<ReadonlySet<string>>(new Set());
  const toggleTool = (key: string) =>
    setOpenedTools((open) => {
      const next = new Set(open);
      if (!next.delete(key)) next.add(key);
      return next;
    });

  return (
    <div className="column">
      {items.map((item, index) => {
        switch (item.kind) {
          case 'user':
            return <UserRow key={item.key} item={item} />;
          case 'assistant':
            return (
              <AssistantRow
                key={item.key}
                item={item}
                index={index}
                saidAt={saidAt}
                caret={streaming && index === lastAssistant}
              />
            );
          case 'turn':
            return <TurnRow key={item.key} item={item} />;
          case 'tool': {
            /* FOLDED, OR NOT. A run of plain tool rows draws one strip at
               its first index and nothing at the others, unless the person
               has opened that call - in which case the row below renders
               exactly as it always has, under the strip. Everything after
               this block is untouched, which is the point: a tool row that
               is on screen is the same tool row it was before. */
            const fold = folded.get(index);
            const strip =
              fold && fold.leads ? (
                <ToolStrip
                  key={`strip-${item.key}`}
                  run={fold.run.map((at) => items[at] as ToolItem)}
                  tools={tools}
                  working={streaming && fold.run.includes(items.length - 1)}
                  /* The turn this fold belongs to is the next `turn` row after
                     it: the engine writes one at `stream.end`, after every
                     tool row the turn produced. */
                  seconds={secondsAfter(items, fold.run[fold.run.length - 1])}
                  opened={openedTools}
                  onToggle={toggleTool}
                />
              ) : null;
            if (fold && !openedTools.has(item.key)) return strip;
            /* A DIAGNOSIS IS NOT A TOOL RESULT ROW. Graphite page 23.2 draws it
               exactly this way: a one-line "Ran the diagnosis" tool row, and
               then the card as its SIBLING in the column. Rendering the card
               inside the row's expanded body — which is where the first cut put
               it — hides the most important surface in the product behind a
               chevron, and page 23.8 rule 8 is that consumer never collapses
               this card at all. Caught by screenshotting the thread at Normal
               density and finding the verdict was not on screen.

               A PROPOSAL IS THE SAME SHAPE, for the same reason and one step
               further: a plan a person is about to approve cannot live behind a
               chevron, and it must never render as the key/value table — a
               build drawn as JSON is a build nobody read before saying yes. */
            const verdict = item.state === 'ok' ? readDiagnosis(item.result) : null;
            const proposal = item.state === 'ok' ? readProposal(item.result) : null;
            /* A refusal is not a failure: `propose_build` returns `ok: false`
               with what is missing, and the row's state is still `ok` because
               the CALL worked. Read from either state for that reason. */
            const refusal = readProposalRefusal(item.result);
            /* AN EVAL RESULT IS THE SAME SHAPE AS A DIAGNOSIS AND FOR THE SAME
               REASON. A score, its resolution, and the rows that failed cannot
               live behind a chevron or render as the key/value table: the whole
               argument for the bench is that the interesting part is not the
               number, and a wall of JSON keys buries the part that matters
               under the part that does not.

               `compare()` declining is a card too, and grey rather than red.
               The engine refusing to subtract two scores measured on different
               eval sets is the product working. */
            const evalReport = item.state === 'ok' ? readEvalReport(item.result) : null;
            const evalCompare = item.state === 'ok' ? readEvalComparison(item.result) : null;
            const evalRefusal = readEvalRefusal(item.result);
            /* Read from either state: `try_prompt` returns `ok: false` for the
               `incomplete` verdict and it is still a whole attempt to draw. */
            const attempt = readPromptAttempt(item.result);
            const promptRefusal = readPromptRefusal(item.result);
            /* THE RETRIEVAL BENCH, AND IT HAD NO SURFACE AT ALL UNTIL NOW.
               Both tools fell through to `ResultView`: a real chunking sweep
               is 40 top-level keys and 614 flattened rows nesting six deep
               against that component's MAX_DEPTH of 3, so `comparisons` — the
               twenty-eight pairwise tests the verdict is made of — rendered as
               the words "28 items, not shown here".

               READ FROM EITHER STATE, for the reason the eval refusal is:
               `compare_chunkings` returns `ok: false` when it declines to
               choose a family size for you, and `measure_retriever_recall`
               returns a fully-shaped reply with `measured: []` when the eval
               set does not say which passage is right. Neither is a failure
               and both are the product working. */
            const sweep = readChunkingSweep(item.result);
            const recall = readRecallReport(item.result);
            /* THE FIRST TOOL IN THIS PRODUCT THAT CHANGES THE USER'S DISK.
               Measured against `ResultView` before this card was built, by
               running `carve_eval_set` on a real file: 22 top-level keys, 83
               rows in a flat table, and - on the reply where the split LEAKS -
               seven containers deep against that component's MAX_DEPTH of 3,
               so 103 of 186 rows do not render. What does not render is
               `leakage.examples`: the pairs of rows found on both sides of a
               file we wrote. Its 320-character fold takes the tool's own
               `summary` too, which on that payload is the 1,221 characters
               beginning "LEAKAGE IN WHAT THIS JUST WROTE".

               READ FROM EITHER STATE, for the reason the eval refusal is: a
               carve that leaks returns `ok: false` and is still a whole thing
               to draw, and every refusal returns `ok: false` with
               `nothing_was_written`, which is the product working. The two
               readers are disjoint on that field. */
            /* THE MODEL ASKED FOR A YES. Fourteen tools need one and six
               of the seventeen steps in the train-on-my-files journey are
               among them; before this the refusal was a dead end drawn as
               a failed row. See components/ApprovalCard.tsx. */
            const approval =
              onApproveTool !== undefined ? readApprovalRequest(item.result) : null;
            const carve = readCarve(item.result);
            const carveRefusal = readCarveRefusal(item.result);
            /* Phase 2's three surfaces. Each reader keys on fields no other
               tool in this registry returns, the same way readCarve does, so
               nothing here has to know which tool produced the row. */
            const synthesis = readSynthesis(item.result);
            const sample = readVerificationSample(item.result);
            const verification = readVerificationRecord(item.result);
            /* ONE READER, TWO CALLERS. `components/cards.ts` answers "did
               anything recognise this result", and the tool strip asks it
               the same question to decide what may be folded into an icon.
               Asking it twice would mean the day somebody adds a
               fourteenth card, the strip goes on folding it - hiding a
               brand-new surface behind a chevron on the day it ships. */
            const card = toolRowDrawsACard(item, onApproveTool !== undefined);
            /* WHICH ROWS CAN OPEN THE STAGE: the ones whose result it draws —
               an eval, a comparison, a prompt attempt, a recall, a carve, a
               diagnosis, and the sandbox tools (a run, a scored adapter),
               which the readers above do not key on and this surface does by
               the two fields no other tool returns together. */
            const staged =
              onStage !== undefined &&
              item.state !== 'running' &&
              (verdict !== null ||
                evalReport !== null ||
                evalCompare !== null ||
                attempt !== null ||
                recall !== null ||
                carve !== null ||
                isSandboxResult(item.result));
            const stageOpen = stageAnchor === item.key;
            /* THE ROW, NAMED RATHER THAN RETURNED, so a strip can be
               returned beside it when this call is an opened member of a
               folded run. Everything inside it is unchanged. */
            const row = (
              /* NAMED, so the transcript's rhythm can see it. A tool row and the
                 card it produced are one block; a tool row alone is narration.
                 `.column`'s spacing rules distinguish those two cases and could
                 not while this wrapper had no class. */
              <div
                key={item.key}
                className={card ? 'turnblock turnblock--card' : 'turnblock'}
              >
                <ToolRow
                  item={item}
                  control={tools.get(item.name) ?? null}
                  density={density}
                  hasCard={card}
                  /* A REFUSAL IS NOT A FAILURE, AND THE ROW SAID IT WAS.
                     `compare()` declining returns `ok: false`, so the row
                     rendered "⚠ failed" in --wont directly above a grey card
                     reading COMPARISON DECLINED — the engine refusing to
                     subtract two scores that must not be subtracted, announced
                     as a broken tool. That is this lane's own defect pointed
                     the other way: the product working, drawn as the product
                     breaking. Measured in the running app on a real
                     `no_shared_rows` result.

                     Keyed off the refusal READER, so it is exactly as narrow
                     as the set of refusals this surface has a card for; a
                     genuine error still says failed, because nothing parses it.

                     NOT WIDENED TO THE PROPOSAL AND PROMPT REFUSALS, which
                     have the same shape and almost certainly the same defect —
                     `ProposalRefusalCard` and `PromptRefusalCard` are grey
                     cards under red rows too. I did not reproduce those, and
                     changing a row I have not watched is guessing. Reported. */
                  /* WIDENED, AND ONLY BECAUSE IT WAS REPRODUCED. The note
                     below records that this was deliberately NOT widened to
                     the proposal and prompt refusals, which were not driven.
                     `compare_chunkings` declining to pick a family size WAS
                     driven — `sweep_no_settings` in
                     `.fleet-verify-shell/retrieval/story-data.json` is that
                     reply, captured off the real registry — and it returns
                     `ok: false`, so the row said "failed" directly above a
                     grey card explaining that nothing was built on purpose.
                     Keyed off the reader, so it is exactly as narrow as the
                     set of replies this surface has a card for. */
                  declined={evalRefusal !== null || sweepDeclined(sweep)}
                  onStage={staged ? () => onStage?.(stageOpen ? null : item.key) : undefined}
                  stageOpen={stageOpen}
                />
                {approval && permission !== 'full' ? (
                  <ApprovalCard
                    name={item.name}
                    args={item.args}
                    control={tools.get(item.name) ?? null}
                    detail={approval.detail}
                    onApprove={(name, args) => onApproveTool!(name, args, threadId)}
                  />
                ) : null}
                {verdict ? (
                  <DiagnosisCard
                    result={verdict}
                    threadId={threadId}
                    tools={tools}
                    runTool={runTool}
                    defaultOpen={index === lastDiagnosis}
                    permission={permission}
                  />
                ) : null}
                {/* THE QUESTION, AS A SIBLING OF THE VERDICT AND NOT INSIDE IT.
                    The same argument page 23.2 makes for the diagnosis card
                    itself: the one thing the person is being asked to DO cannot
                    live behind a chevron, and it is a second card rather than a
                    section of the first because "here is what I concluded" and
                    "here is what I need from you" are two thoughts and the
                    second one is the one with a control on it.

                    Only under the last diagnosis — see `lastDiagnosis`. */}
                {verdict && index === lastDiagnosis && permission !== 'full' ? (
                  <QuestionCard
                    from={verdict}
                    question={question}
                    frontierExhausted={frontierExhausted}
                    threadId={threadId}
                    tools={tools}
                    runTool={runTool}
                    workspaceRoot={workspaceRoot}
                    onAnswered={onAnswered}
                  />
                ) : null}
                {proposal && permission !== 'full' ? (
                  <ProposalCard
                    proposal={proposal}
                    /* The call's own arguments, straight off the row. This is
                       what `POST /api/storms` re-proposes from, so the plan
                       that runs is one the engine built and validated itself. */
                    proposalArgs={item.args}
                    threadId={threadId}
                    tools={tools}
                    storm={storms(proposal.approve)}
                    denial={denials.forFingerprint(proposal.approve)}
                    onApprove={onApprove}
                    onDeny={denials.deny}
                    onForgetDenial={denials.forget}
                    onCancel={onCancelStorm}
                  />
                ) : null}
                {refusal && permission !== 'full' ? (
                  <ProposalRefusalCard refusal={refusal} />
                ) : null}
                {evalReport ? <EvalCard report={evalReport} /> : null}
                {evalCompare ? <EvalCompareCard comparison={evalCompare} /> : null}
                {evalRefusal ? <EvalRefusalCard refusal={evalRefusal} /> : null}
                {attempt ? <PromptCard attempt={attempt} /> : null}
                {promptRefusal ? <PromptRefusalCard refusal={promptRefusal} /> : null}
                {sweep ? <ChunkingSweepCard sweep={sweep} /> : null}
                {recall ? <RetrieverRecallCard report={recall} /> : null}
                {carve ? <CarveCard carve={carve} /> : null}
                {carveRefusal ? <CarveRefusalCard refusal={carveRefusal} /> : null}
                {synthesis ? <SynthesisCard synthesis={synthesis} /> : null}
                {sample ? <VerificationSampleCard sample={sample} /> : null}
                {verification ? <VerificationCard record={verification} /> : null}
                {/* Size D: the Stage unfolds under the row where the result
                    landed, at the reading column's width, and it is the same
                    Stage the split and the window show. */}
                {stageOpen ? stageNode : null}
              </div>
            );
            return strip ? [strip, row] : row;
          }
          case 'notice':
            return <NoticeRow key={item.key} item={item} />;
          case 'effects':
            return (
              <div key={item.key} className="turnblock turnblock--card">
                <WhatChangedCard
                  threadId={threadId}
                  effects={{
                    effectsId: item.id,
                    stepsDone: item.stepsDone,
                    stepsParked: item.stepsParked,
                    facts: item.facts,
                    files: item.files,
                    planWrites: item.planWrites,
                    canRevert: item.canRevert,
                  }}
                  onReverted={onEffectsReverted}
                />
              </div>
            );
          case 'verdict':
            return (
              /* A CARD, so the column's own rhythm gives it the --sp-24 both
                 ways that every other card gets. The engine's verdict standing
                 at paragraph distance from the paragraph it is annotating
                 would read as the next sentence of the reply, which is the one
                 thing this row may not do. */
              <div key={item.key} className="turnblock turnblock--card">
                <EngineVerdictCard
                  item={item}
                  /* Whether a diagnosis card ABOVE this row is already
                     showing this outcome — which is the case whenever the
                     model ran `run_diagnosis` this turn, because that card and
                     this event come from one payload. Only ever true upwards,
                     which is the honest direction: nothing is ever suppressed
                     in the REPLY, and the copy that survives is the fuller one.
                     Two independent tests, because `say` can repeat without
                     the whole payload repeating: `outcomeAt` says the ENGINE
                     HALF is drawn above, `allSaidAbove` says only the sentence
                     is (a `run_diagnosis` card from an EARLIER turn that
                     reached the same finding). */
                  engineIsOnACardAbove={
                    item.outcome !== null &&
                    (outcomeAt.get(item.outcome) ?? Infinity) < index
                  }
                  sayIsOnACardAbove={allSaidAbove(item.say, saidAt, index)}
                  threadId={threadId}
                  tools={tools}
                  runTool={runTool}
                />
              </div>
            );
          case 'error':
            return <ErrorRow key={item.key} item={item} />;
          case 'train':
            return <TrainRow key={item.key} item={item} />;
          case 'storm':
            return <StormRow key={item.key} item={item} />;
          case 'eval':
            return <EvalRunRow key={item.key} item={item} />;
          case 'subagent':
            return (
              <SubAgentRow
                key={item.key}
                item={item}
                onOpen={onOpenThread}
              />
            );
          default:
            /* An event this surface has no row for is bookkeeping between the
               engine and itself - `thread.permission` printed three times on
               one screen, 2026-09-18. The person did nothing to see it and can
               do nothing about it, so it draws nothing. The event is still in
               the stream for the Inspector. */
            return null;
        }
      })}

      {/* The caret has to belong to something. A turn that has begun but whose
          first token has not arrived gets an empty streaming row rather than
          nothing at all, so the interface is never silent while the engine is
          working. A blinking caret was that row's whole content, which held
          for a fast endpoint and failed for the one this product is built
          around: measured on a stranger walk against a local granite4 on a
          2060 Super, 80 seconds passed with the caret as the only sign, and
          nothing on screen separated working from hung. */}
      {/* ...AND ON EVERY TURN AFTER THE FIRST. `lastAssistant === -1` was
          true only before the thread's first reply; on the second turn the
          previous answer counted as "the assistant has spoken" and the
          twenty seconds before the next first token showed nothing. Max,
          2026-09-12: "the loading's better, sometimes doesn't really load,
          it doesn't really spin." The row shows whenever the turn is running
          and the last thing on screen is the person's message or the
          turn's own opening rows - which is when there is nothing else to
          look at. A tool row shows its own spinner, so it is not counted. */}
      {streaming && waitingForTheFirstToken(items) ? (
        <WaitingForTheFirstToken status={liveWorkStatus(items, tools)} />
      ) : null}
      {/* A turn that stopped when the engine did. See `ATurnThatNeverFinished`. */}
      {!streaming && endsOnAnUnansweredAsk(items) ? <ATurnThatNeverFinished /> : null}

      {/* THE SUB-AGENT BOARD, INSIDE THE COLUMN. It belongs to the
          conversation's own flow: the column is what gives the transcript its
          reading width and its padding, and a sibling OUTSIDE it was a flex
          item in a scroll container that crushed it to two pixels - measured.
          Last, because it is the state of the work rather than a thing that
          was said, so a person reading down arrives at it after the talk. */}
      {board}
    </div>
  );
}

/** The row that stands in for a turn whose first token has not arrived.
 *
 *  It says one measured thing: how long this has been going. That is enough to
 *  tell working from hung, which is the only question a person has while they
 *  wait, and it is a number this surface is allowed to show because a clock is
 *  an instrument - nothing here is estimated or predicted. There is
 *  deliberately no progress bar: the engine cannot know how many tokens are
 *  coming, and a bar that fills at a made-up rate would be inventing one.
 *
 *  Quiet, not cobalt. Cobalt means the product needs you, and this is the
 *  product working - the wrong hue here would read as a prompt to act.
 *
 *  The count appears only after a few seconds so a fast endpoint never flashes
 *  a timer that is gone before it can be read.
 */
/** ONE LINE PER HAND-OFF, IN THE ORDER IT HAPPENED.
 *
 * The board above the composer answers "what is out right now". This answers
 * "what went out, when, and what came back" - which is a question about the
 * conversation, so it belongs in the conversation. Gold for a worker, the
 * same gold the board and the rail use, because a sub-agent is one colour
 * everywhere in this product.
 */
function SubAgentRow({
  item,
  onOpen,
}: {
  item: SubAgentItem;
  onOpen?: (threadId: number) => void;
}) {
  const open = item.childThreadId !== null && onOpen
    ? () => onOpen(item.childThreadId as number)
    : undefined;
  const counts: string[] = [];
  if (item.event === 'sent' && item.steps) {
    counts.push(`${item.steps} step${item.steps === 1 ? '' : 's'}`);
  }
  if (item.ticked) counts.push(`${item.ticked} done`);
  if (item.parked) counts.push(`${item.parked} parked`);
  if (item.unreached) counts.push(`${item.unreached} never reached`);

  const said =
    item.event === 'sent'
      ? 'Handed out'
      : item.event === 'back'
        ? 'Came back'
        : 'Folded into the plan';

  return (
    <div className="subrow" data-event={item.event} data-state={item.state || undefined}>
      <span className="subrow__dot" aria-hidden="true" />
      <span className="subrow__said">{said}</span>
      {open ? (
        <button
          type="button"
          className="subrow__phase"
          onClick={open}
          title="Open this sub-agent's own conversation"
        >
          {item.phase}
        </button>
      ) : (
        <span className="subrow__phase">{item.phase}</span>
      )}
      {counts.length ? (
        <span className="subrow__counts num">{counts.join(' · ')}</span>
      ) : null}
      {item.detail ? (
        <span className="subrow__why" title={item.detail}>
          {item.detail}
        </span>
      ) : null}
    </div>
  );
}

function WaitingForTheFirstToken({
  status,
}: {
  status: { word: string; detail?: string };
}) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const tick = window.setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(tick);
  }, [status.word, status.detail]);
  /* SEQUENCE / Codex idiom: braille orbit + gleaming word. Detail names the
     live tool so a person can tell thinking from tool-calling without reading
     GPU meters (CS17). */
  return (
    <div className="prose thinking" data-live="true" aria-live="polite">
      <span className="toolstrip__spin" aria-hidden="true" />
      <span className="thinking__word">{status.word}</span>
      {status.detail ? (
        <code className="thinking__tool" title={status.detail}>
          {status.detail}
        </code>
      ) : null}
      {seconds >= 3 ? (
        <span className="waiting">
          <span className="waiting__t">{elapsed(seconds)}</span>
        </span>
      ) : null}
    </div>
  );
}

/** Seconds as a person reads them. Whole seconds under a minute, then minutes
 *  and seconds - never a decimal, because a clock read to the tenth implies a
 *  precision that means nothing to somebody waiting. */
export function elapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${String(seconds % 60).padStart(2, '0')}s`;
}

/** A measured turn duration, read back the way a person reads a clock.
 *
 *  Sub-second resolution is kept below ten seconds and nowhere else: the
 *  difference between a 0.8s turn and a 4s turn is real and worth seeing,
 *  while the difference between 337.219s and 337s is noise on a wall clock
 *  that started and stopped around a network call. Past a minute it reads as
 *  minutes and seconds, matching what the waiting row counts up in, so one
 *  quantity does not wear two formats in a single transcript.
 */
export function duration(seconds: number): string {
  if (seconds < 10) return `${Math.round(seconds * 10) / 10}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return elapsed(Math.round(seconds));
}

/** Did this conversation stop after the person spoke, with nothing answering?
 *
 *  Tool rows may follow the ask - a turn can run tools and die before writing a
 *  word - so this looks for an assistant message after the last user one rather
 *  than at the very last item.
 */
/** The measured wall time of the turn that produced the rows ending at
 *  `from`, or null while it is still running.
 *
 *  The `turn` row is written at `stream.end`, so it is the first one AFTER the
 *  turn's tool rows. The scan stops at the next tool or user row, which would
 *  belong to a different turn: a fold must never borrow a neighbour's clock.
 */
export function secondsAfter(items: TranscriptItem[], from: number): number | null {
  for (let index = from + 1; index < items.length; index += 1) {
    const item = items[index];
    if (item.kind === 'turn') return item.seconds;
    if (item.kind === 'tool' || item.kind === 'user') return null;
  }
  return null;
}

export function endsOnAnUnansweredAsk(items: TranscriptItem[]): boolean {
  let lastUser = -1;
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (items[index].kind === 'user') {
      lastUser = index;
      break;
    }
  }
  if (lastUser === -1) return false;
  for (let index = lastUser + 1; index < items.length; index += 1) {
    if (items[index].kind === 'assistant') return false;
  }
  return true;
}

/** The row for a turn that stopped when the engine did.
 *
 *  FOUND ON THE RETURNING-USER WALK. A person who ran yesterday, closed
 *  everything and came back opened a thread that ends on their own message with
 *  seventeen thousand characters of tool output after it and no reply. Nothing
 *  said the turn had died. They cannot tell "still running" from "it stopped"
 *  from "that was all there was", and those are three different next moves.
 *
 *  THE PRODUCT ALREADY HAS THE WORDS. When the model connection fails while the
 *  engine is watching, the thread gets "The connection to the model failed part
 *  way through this turn, so the answer never arrived ... Anything that did
 *  reach us is above, and nothing was lost." Nobody writes that when the ENGINE
 *  is the thing that stopped, because the process that would have written it is
 *  the one that went away. So the surface says it instead, from what it can
 *  see: the person spoke, nothing answered, and no turn is running now.
 *
 *  IT CLAIMED ONE THING TOO MANY, AND THE SECOND WALK CAUGHT IT. The first
 *  wording said "the engine stopped before one arrived". This window cannot
 *  know that. `turn` is local state set when THIS page sends; the only event
 *  that moves it is `stream.end`, so a turn started in another window - and
 *  this product ships a detached Stage window - leaves this one with
 *  `streaming` false and no assistant message yet. Measured on this hardware,
 *  that gap is as long as the model takes to produce a first token: 5m 37s on
 *  the slowest turn walked. For all of that time the marker would have told a
 *  person their running turn had died.
 *
 *  The condition cannot be strengthened from here - a turn that is running and
 *  a turn that stopped look identical to a client that has received neither
 *  tokens nor `stream.end` - so the CLAIM is what changes. It now names both
 *  possibilities and says they are indistinguishable from this page, and still
 *  says the work above is intact, which is the question a returning person
 *  actually has.
 */
/** What the marker may say. A constant so a test can call it, the way
 *  `scripts/gate.py` keeps its own sentence callable for the same reason. */
export const NO_ANSWER_WAS_WRITTEN =
  'No answer was written for this. Either it is still being written somewhere else — a ' +
  'second window, or a turn this page did not start — or it stopped before one arrived; ' +
  'from here those look the same. Anything above is what really ran and is still on the ' +
  'record.';

function ATurnThatNeverFinished() {
  return (
    <div className="prose unfinished">
      <p className="unfinished__say">{NO_ANSWER_WAS_WRITTEN}</p>
    </div>
  );
}

/** Is the model working with nothing on screen to show for it?
 *
 *  Max, 2026-09-13: *"it's tough to see when the model's working or not.
 *  Looking at my GPU I'm at ninety percent, so I know it's thinking, but the
 *  last thing I see is a tool call that failed and I don't see a loaded
 *  spinner. I'm not sure if the model's working."*
 *
 *  The old rule was "nothing after the last user message" - true only before
 *  a turn's FIRST token, so a turn that had already run a tool showed nothing
 *  for the whole of the next reply. The rule now: while the turn is running,
 *  the only thing that speaks for itself is assistant text arriving. Anything
 *  else last on screen - a tool row, a notice, a verdict, a stopped reply -
 *  means the model is working and the screen is still.
 */
export function waitingForTheFirstToken(items: TranscriptItem[]): boolean {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const kind = items[index].kind;
    if (kind === 'turn' || kind === 'notice') continue;
    return kind !== 'assistant';
  }
  return true;
}

/** CS17 — what the live turn is doing right now, for the gleaming status row. */
export function liveWorkStatus(
  items: TranscriptItem[],
  tools?: Map<string, ToolControl>,
): {
  word: string;
  detail?: string;
} {
  /* IN THE PRODUCT'S OWN WORDS, NOT THE FUNCTION'S NAME. This printed
     `Calling` beside a raw `run_diagnosis`, and Max, 2026-09-19: "those fonts
     aren't centered and they're a little bit undescriptive." The roster
     already carries the sentence every tool row uses - `control.verb` - and
     this was the one surface that never looked it up. */
  const said = (name: string) => tools?.get(name)?.verb ?? name;
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind === 'turn' || item.kind === 'notice') continue;
    if (item.kind === 'tool') {
      if (item.state === 'running') {
        return { word: 'Working', detail: said(item.name) };
      }
      return { word: 'Read', detail: said(item.name) };
    }
    if (item.kind === 'assistant') {
      return { word: 'Writing' };
    }
    break;
  }
  return { word: 'Thinking' };
}

function lastIndexOfAssistant(items: TranscriptItem[]): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (items[index].kind === 'assistant') return index;
  }
  return -1;
}

/**
 * Is this sweep a REFUSAL, as opposed to a sweep that ran or a plan?
 *
 * The tool row above a refusal is what tells a person whether their tool broke,
 * and `compare_chunkings` refusing to invent a family size returns `ok: false`
 * like a crash does. The two states below are the ones where nothing is wrong:
 * `refused` is every pre-build refusal — no settings, a duplicate setting, a
 * name already taken, a window that would truncate the index — and
 * `nothing_compared` is a sweep that built indexes and then declined to compare
 * them, which is the passage-level ground truth case. A plan is not a refusal
 * and neither is a finished sweep, so neither is here.
 */
function sweepDeclined(sweep: ChunkingSweep | null): boolean {
  if (sweep === null) return false;
  return sweep.state === 'refused' || sweep.state === 'nothing_compared';
}

/**
 * The last row in this thread that produced a diagnosis, or -1.
 *
 * This is where the live question hangs. Read with `readDiagnosis` rather than
 * off the tool NAME, for the same reason `outcomesAlreadyOnCards` does: a
 * diagnosis is any payload stamped `decided_by: app/diagnosis.py`, which is
 * `run_diagnosis` today and is whatever else the engine decides to answer with
 * tomorrow. Matching on `item.name === 'run_diagnosis'` would put the question
 * under the wrong card the day that changes, and nothing would say so.
 */
function lastIndexOfDiagnosis(items: TranscriptItem[]): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind !== 'tool' || item.state !== 'ok') continue;
    if (readDiagnosis(item.result) !== null) return index;
  }
  return -1;
}

/* ── Messages ───────────────────────────────────────────────────────────────
   The user is a bubble, the assistant is not.

   The old law's concern — that the transcript carries plans, tables, diffs and
   log excerpts and needs the width — survives, because the half that needs the
   width is the assistant half, and that half is now full-width. The user half
   is short, so bubbling it costs nothing.

   Neither side carries a name label. The bubble says who is speaking by where
   it sits, and a "Harness" caption above every reply is noise in a two-party
   conversation. */

function UserRow({ item }: { item: UserItem }) {
  return (
    <div className="userbubble">
      <Markdown source={item.text} />
    </div>
  );
}

function AssistantRow({
  item,
  index,
  saidAt,
  caret,
}: {
  item: AssistantItem;
  index: number;
  /** sentence → index of the first row whose CARD stated it. */
  saidAt: Map<string, number>;
  caret: boolean;
}) {
  const blocks = parseMarkdown(item.text);
  /* While the reply is still arriving, nothing is dropped: a half-streamed
     paragraph is not yet the sentence it is going to be, and a paragraph that
     vanished and came back would be the worst reading experience in the
     product. The comparison happens once the text has stopped moving. */
  const kept = caret ? blocks : blocks.filter((block) => !isEcho(block, saidAt, index));
  const echoed = !caret && kept.length === 0 && blocks.length > 0;

  if (echoed) {
    /* Not silence: the card immediately above IS the reply, and this line says
       so in ten words rather than printing the same paragraph a second time. */
    return (
      <div className="prose">
        <p className="echoed">
          <Icon name="info" size={11} />
          <span>The model’s reply repeated the card above word for word.</span>
        </p>
      </div>
    );
  }

  return (
    <div className="prose">
      {kept.map((block, position) => (
        <BlockView key={position} block={block} />
      ))}
      {/* A 2px x 1em --accent caret at the insertion point, 1s step-end blink.
          Text appears by replacement of the trailing run — never by fading in
          per character. */}
      {caret ? <span className="caret" /> : null}
    </div>
  );
}

/* ── The turn row ───────────────────────────────────────────────────────────
   Which model answered, whether it can call tools, and how long it took. This
   is provenance for the reply itself, and the transcript is the artifact: a
   notebook that does not record which instrument took the reading is a diary. */

function TurnRow({ item }: { item: TurnItem }) {
  const tools =
    item.toolCalling === 'yes'
      ? 'can call tools'
      : item.toolCalling === 'no'
        ? 'cannot call tools'
        : 'tool calling not probed';
  return (
    <div className="metarow">
      <Icon name="key" />
      <span>
        Asked <span className="mono">{item.model}</span> · {item.locality} ·{' '}
        {tools}
        {item.seconds !== null ? (
          <>
            {' · '}
            {/* Measured: time.monotonic() across the turn. Read back at a
                precision a person can use - this line was printing 337.219s
                for a five-and-a-half-minute turn, which is three decimals of
                invented precision on a wall clock and still makes the reader
                divide by sixty to learn what it means. The exact measurement
                stays on the title, so nothing is lost by rounding it. */}
            <span className="metarow__num" title={`${item.seconds}s measured`}>
              {duration(item.seconds)}
            </span>
          </>
        ) : null}
      </span>
    </div>
  );
}

/* ── Tool rows — one line, collapsed, expandable ──────────────────────────── */

function ToolRow({
  item,
  control,
  density,
  hasCard,
  declined = false,
  onStage,
  stageOpen = false,
}: {
  item: ToolItem;
  control: ToolControl | null;
  density: Density;
  /** Present when this row's result can be drawn on the Stage. Toggles the
   *  inline size under this row; see `Transcript`'s `stageAnchor`. */
  onStage?: () => void;
  stageOpen?: boolean;
  /** True when a diagnosis card is rendered directly beneath this row. The row
   *  then does not print the result as a table, because the card IS the
   *  result and two renderings of one answer make a reader arbitrate between
   *  us and ourselves. */
  hasCard: boolean;
  /** True when the tool returned a REFUSAL this surface recognises rather than
   *  an error. The row then reads "declined" in grey instead of "failed" in
   *  red, because the engine declining to compute a number that would mean
   *  nothing is the product working. See the call site. */
  declined?: boolean;
}) {
  /* §9.21's `mixed` state, which is why this is not a plain boolean: "a single
     turn manually expanded inside Summary; the control shows no active segment
     change, because one expanded turn is not a mode". So `null` means "follow
     the density", and a click pins the row until the density itself changes.
     A first cut seeded `useState(density === 'verbose')` and Verbose then did
     nothing to a row that was already on screen — caught by screenshotting the
     Verbose segment and seeing an unchanged row. */
  const [manual, setManual] = useState<boolean | null>(null);
  const [followed, setFollowed] = useState(density);
  if (followed !== density) {
    /* React's documented way to adjust state when a prop changes: do it during
       render, not in an effect that would start a second one. */
    setFollowed(density);
    setManual(null);
  }
  /* Neither level opens a row on its own now that Verbose is gone. `manual` is
     still per-row and still cleared when the level changes, which is §9.21's
     `mixed`: "a single turn manually expanded inside Summary; the control shows
     no active segment change, because one expanded turn is not a mode." */
  const open = (followed === density ? manual : null) ?? false;

  const label = control ? sentence(control.verb) : item.name;
  /* §9.21: Summary hides mechanics. The arguments are mechanics; the label,
     the state and every number inside the result are not, and they render
     identically at all three levels. */
  /* Every level shows the arguments now, because there is one. A row that
     wants them hidden is a click, which is what removed the level. */
  const args = Object.entries(item.args);

  /* The facts this CALL carried, and what the engine says they were worth.
     This is the transcript half of the fact-origin work: a model that supplies
     `eval_size_n` is making an unverified claim, and the row it made it on
     says so — at every density, because "17 facts, asserted" is not mechanics,
     it is the claim. */
  const supplied = suppliedFacts(item);
  /* `facts 16 fields` next to `16 facts ASSERTED` is the same count twice, and
     the second one says something the first does not. The generic summary drops
     the key the origin badge already speaks for. */
  const headArgs = supplied ? args.filter(([key]) => key !== 'facts') : args;

  return (
    <div
      className="toolrow"
      data-state={declined && item.state === 'failed' ? 'declined' : item.state}
      data-open={open}
    >
      <button
        type="button"
        className="toolrow__head"
        aria-expanded={open}
        onClick={() => setManual(!open)}
      >
        <span className="toolrow__glyph">
          <Icon name={control ? groupIcon(control.group) : 'skill'} />
        </span>
        <span className="toolrow__label">{label}</span>
        {headArgs.length > 0 ? (
          <span className="toolrow__args">
            {headArgs
              .map(([key, value]) => `${key} ${short(value)}`)
              .join(' · ')}
          </span>
        ) : null}
        <span className="toolrow__state">
          {item.state === 'running' ? (
            <>
              <span className="dot" data-shape="filled-pulse" style={{ ['--st-colour' as string]: 'var(--st-active)' }} />
              working
            </>
          ) : item.state === 'ok' ? (
            <>
              <Icon name="check" size={12} /> done
            </>
          ) : declined ? (
            /* `eye`, not `alert`. The glyph is the second channel page 05.1
               requires, and an alert triangle would carry the claim the word
               has just stopped making. */
            <>
              <Icon name="eye" size={12} /> declined
            </>
          ) : (
            <>
              <Icon name="alert" size={12} /> failed
            </>
          )}
        </span>
        {item.drivenBy === 'harness' ? (
          <span className="toolrow__driver" title="The connected model cannot call tools, so the harness ran this itself.">
            run by the harness
          </span>
        ) : null}
        {item.drivenBy === 'user' ? (
          <span className="toolrow__driver" title="Run from a control through the user's own door - the engine recorded it on this thread.">
            run by you
          </span>
        ) : null}
        {supplied ? (
          <span className="toolrow__supplied">
            <span className="toolrow__suppliednum">{supplied.names.length}</span>{' '}
            {supplied.names.length === 1 ? 'fact' : 'facts'}
            <OriginTag origin={supplied.origin} by={supplied.by} />
          </span>
        ) : null}
        {onStage ? (
          /* A span with a role, not a nested button: the head IS a button and
             a button inside a button is invalid HTML that browsers repair
             unpredictably. Stops the click so the head does not also toggle. */
          <span
            role="button"
            tabIndex={0}
            className="toolrow__stage"
            aria-pressed={stageOpen}
            title={stageOpen ? 'Fold the Stage back into this row' : 'Open this result on the Stage'}
            onClick={(event) => {
              event.stopPropagation();
              onStage();
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                event.stopPropagation();
                onStage();
              }
            }}
          >
            <Icon name="panelleft" size={11} /> {stageOpen ? 'on stage' : 'stage'}
          </span>
        ) : null}
        <span className="toolrow__chev">
          {/* One glyph pointed two ways rather than two glyphs that can
              disagree about weight. */}
          <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        </span>
      </button>

      {open ? (
        <div className="toolrow__body">
          {control ? <p className="toolrow__desc">{control.description}</p> : null}

          {supplied ? (
            <Section title={`Claimed — ${supplied.sentence}`}>
              <div className="claims">
                {supplied.names.map((name) => (
                  <div className="claim" key={name}>
                    <span className="claim__name mono">{name}</span>
                    <span className="claim__value mono">
                      {short(supplied.values[name])}
                    </span>
                    <OriginTag origin={supplied.origin} />
                  </div>
                ))}
              </div>
            </Section>
          ) : args.length > 0 ? (
            <Section title="Asked for">
              <ResultView value={item.args} />
            </Section>
          ) : null}

          {item.state === 'running' ? (
            <p className="toolrow__desc">Still running.</p>
          ) : hasCard ? (
            <p className="toolrow__desc">
              What this returned is drawn as itself on the card below this row —
              a verdict with its ledger, or a plan with its diagram, its costs
              and their origins. It is not repeated here as a table.
            </p>
          ) : (
            <Section title="Found">
              <ResultView value={item.result} />
            </Section>
          )}

          {/* §9.21 gave this to Verbose: "expanded with what each read and
              wrote". Verbose is gone and the sentence still has a home — an
              EXPANDED row is the deliberate ask Verbose was a mode for, so what
              was behind a level is now behind the chevron of the one row that
              wanted it. The registry declares both; they are not
              documentation. */}
          {control ? (
            <p className="toolrow__reads">
              reads {control.reads.length ? control.reads.join(', ') : 'nothing'} ·
              writes {control.writes.length ? control.writes.join(', ') : 'nothing'}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** A sandbox tool's reply — `run_in_sandbox`, `score_the_adapter`,
 *  `score_a_candidate_model` — keyed on the two fields no other tool returns
 *  together: the sandbox it ran in and what it reached. */
function isSandboxResult(value: unknown): boolean {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return typeof record.sandbox === 'string' && ('reach' in record || 'adapter' in record || 'run_dir' in record);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="toolrow__section">
      <div className="toolrow__sectiontitle">{title}</div>
      {children}
    </div>
  );
}

/* ── Notices, errors, training ──────────────────────────────────────────── */

function NoticeRow({ item }: { item: NoticeItem }) {
  /* A PLAN CHANGE IS A LOG LINE, NOT A FINDING. Max, 2026-09-14, with a
     transcript of two ticked steps in it: *"I'm also seeing a lot of blue, and
     overall expanded tool calling - I want it condensed, icons, more minimised
     view by default which can be expanded and seen if clicked on."*

     The blue was `--info`, and `--info` means "read this, it is a finding
     about your situation". A step being ticked is not that: it is the plan
     doing exactly what the plan is for, recorded. Wearing a finding's colour
     and a finding's box, twice per turn, it was louder than the tool rows it
     was describing - in his screenshot the two notices took more column than
     the four tool calls above them.

     So a notice that carries a plan change draws as one quiet line: the
     glyph, the sentence, and the diff disclosure. AU2 (2026-09-15): the same
     quiet line for housekeeping (`quiet`) — mode switch, blocks.changed,
     memory ticks, compaction success. Compaction failure and run stop stay
     blue: those ARE findings. */
  if (item.diff || item.quiet) {
    return (
      <p className="planline">
        <Icon name="skill" size={11} />
        <span className="planline__text" title={item.reason || undefined}>
          {item.text}
        </span>
        {item.diff ? <PlanDiff change={item.diff} /> : null}
      </p>
    );
  }
  return (
    <Strip tone="info" icon="info">
      {item.text}
      {item.reason ? (
        <span style={{ color: 'var(--ink-3)' }}> ({item.reason})</span>
      ) : null}
      {/* A LIST IS DRAWN AS A LIST. Seven parked steps joined by commas inside
          a parenthesis is the paragraph Max photographed. Capped at five with
          the remainder counted, because the plan is where all of them live and
          this is a notice, not the plan. */}
      {item.points && item.points.length ? (
        <ul className="strip__points">
          {item.points.slice(0, 5).map((one) => (
            <li key={one}>{one}</li>
          ))}
          {item.points.length > 5 ? (
            <li className="strip__points-more">
              and {item.points.length - 5} more — the plan keeps every one as [!]
            </li>
          ) : null}
        </ul>
      ) : null}
    </Strip>
  );
}

function ErrorRow({ item }: { item: ErrorItem }) {
  return (
    <Strip tone="wont" icon="alert">
      The model&rsquo;s server returned an error, and the turn stopped here.{' '}
      <span className="mono">{item.detail}</span>
    </Strip>
  );
}

/**
 * One line per storm, and the picture is where a person looks.
 *
 * The card above already draws every state this row could report, off the same
 * events. This says which storm and how many of its own frames have landed, so
 * the transcript records that work happened here without narrating it twice.
 */
function StormRow({ item }: { item: StormItem }) {
  return (
    <div className="metarow">
      <Icon name="branch" />
      <span>
        Storm <span className="mono">{item.stormId}</span> ·{' '}
        <span className="metarow__num">{item.events}</span>{' '}
        {item.events === 1 ? 'event' : 'events'}, kept out of the transcript ·{' '}
        {item.finishedAs
          ? `finished ${item.finishedAs}`
          : item.latest
            ? item.latest.split('.').join(' ')
            : 'declared'}
        . Its plan is the picture of it.
      </span>
    </div>
  );
}

function TrainRow({ item }: { item: TrainItem }) {
  return (
    <div className="metarow">
      <Icon name="run" />
      <span>
        Training job <span className="mono">{item.jobId}</span>
        {item.latest ? <> · {item.latest.kind}</> : null} ·{' '}
        <span className="metarow__num">{item.logLines}</span> log lines, held out
        of the transcript
      </span>
    </div>
  );
}

/* ── Markdown ────────────────────────────────────────────────────────────── */

/* Exported for the plan document (components/PlanDocument.tsx), which renders
   the same markdown the transcript does - one renderer, so a plan reads the
   way the reply that wrote it read. */
export function Markdown({ source }: { source: string }) {
  if (!source) return null;
  return (
    <>
      {parseMarkdown(source).map((block, index) => (
        <BlockView key={index} block={block} />
      ))}
    </>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case 'p':
      return (
        <p>
          <Spans spans={block.spans} />
        </p>
      );
    case 'h': {
      const Tag = (`h${block.level + 2}`) as 'h3' | 'h4' | 'h5';
      return (
        <Tag className="md__h">
          <Spans spans={block.spans} />
        </Tag>
      );
    }
    case 'ul':
      return (
        <ul className="md__list">
          {block.items.map((spans, index) => (
            <li key={index}>
              <Spans spans={spans} />
            </li>
          ))}
        </ul>
      );
    case 'ol':
      return (
        <ol className="md__list">
          {block.items.map((spans, index) => (
            <li key={index}>
              <Spans spans={spans} />
            </li>
          ))}
        </ol>
      );
    case 'pre':
      return (
        <pre className="md__pre">
          <code>{block.text}</code>
        </pre>
      );
    /* A PLAN IS A LIST OF THINGS TO DO, and a checkbox is how that reads.
       Rendered read-only on purpose: this draws what the document SAYS,
       and a box that could be ticked here would be an edit the markdown
       never received. The plan panel is where a plan is changed. */
    case 'tasks':
      return (
        <ul className="md__tasks">
          {block.items.map((item, index) => (
            <li key={index} data-done={item.done} data-parked={item.parked || undefined}>
              {/* A parked step is neither open nor done - the run could not
                  do it and wrote why into the line (planning.park_step). */}
              <Icon name={item.parked ? 'alert' : item.done ? 'check' : 'x'} size={12} />
              <span>
                <Spans spans={item.spans} />
              </span>
            </li>
          ))}
        </ul>
      );
    case 'quote':
      return (
        <blockquote className="md__quote">
          <Spans spans={block.spans} />
        </blockquote>
      );
    case 'hr':
      return <hr className="md__hr" />;
    default:
      return null;
  }
}

function Spans({ spans }: { spans: Span[] }) {
  return (
    <>
      {spans.map((span, index) => {
        if (span.kind === 'strong') return <strong key={index}>{span.text}</strong>;
        if (span.kind === 'em') return <em key={index}>{span.text}</em>;
        if (span.kind === 'code')
          return (
            <code className="md__code" key={index}>
              {span.text}
            </code>
          );
        return <span key={index}>{span.text}</span>;
      })}
    </>
  );
}

/* ── The verbatim echo ───────────────────────────────────────────────────
   See the header for the cause, which is in `app/instructions/`, and for why
   the card rather than the prose is the copy that survives. Everything here is
   EXACT matching: no stemming, no similarity, no paraphrase judgement. */

/**
 * Every sentence a card in this thread states, mapped to the index of the row
 * that first stated it.
 *
 * The strings come from the SAME fields the cards render — the diagnosis's
 * `say` and `help`, the proposal's own sentences — so this cannot drift into
 * suppressing something no card is showing. If a card stops printing a field,
 * it stops appearing here, and the model's version of it survives.
 */
function sentencesAlreadyOnCards(items: TranscriptItem[]): Map<string, number> {
  const said = new Map<string, number>();
  items.forEach((item, index) => {
    if (item.kind !== 'tool' || item.state !== 'ok') return;
    for (const text of cardSentences(item.result)) {
      for (const one of splitSentences(text)) {
        if (one && !said.has(one)) said.set(one, index);
      }
    }
  });
  return said;
}

/**
 * Every outcome a diagnosis card in this thread is drawing, mapped to the index
 * of the first row that drew it.
 *
 * READ OFF THE ENGINE'S OWN IDENTIFIER — `NO_TRAIN__SHIP_AS_IS`,
 * `ACTION__SUBSTANTIATE_CLAIMED_FACTS` — which is the string
 * `docs/diagnosis_engine.yaml` declares and `DiagnosisCard` prints in mono at
 * the top of the card. So "is the engine's answer already on screen?" is a
 * lookup rather than a similarity judgement, and it stays right on the day the
 * engine reaches an outcome this file has never heard of.
 */
function outcomesAlreadyOnCards(items: TranscriptItem[]): Map<string, number> {
  const seen = new Map<string, number>();
  items.forEach((item, index) => {
    if (item.kind !== 'tool' || item.state !== 'ok') return;
    const verdict = readDiagnosis(item.result);
    if (verdict?.outcome && !seen.has(verdict.outcome)) seen.set(verdict.outcome, index);
  });
  return seen;
}

function cardSentences(result: unknown): string[] {
  const out: string[] = [];
  const verdict = readDiagnosis(result);
  if (verdict) {
    if (verdict.say) out.push(verdict.say);
    if (verdict.help) out.push(verdict.help);
    for (const row of verdict.unsubstantiated) {
      if (row.substantiation) out.push(row.substantiation);
    }
  }
  const proposal = readProposal(result);
  if (proposal) out.push(...sentencesOnProposalCard(proposal));
  const refusal = readProposalRefusal(result);
  if (refusal) {
    out.push(refusal.detail);
    if (refusal.help) out.push(refusal.help);
  }

  /* THE EVAL BENCH ARRIVES WITH THE SAME DEFECT ALREADY BUILT IN, and it is
     worth naming rather than waiting to rediscover. `evals.py` returns
     `summary` — which for a reused run is four sentences long — plus
     `resolution.says` and, on a comparison, `says`. `conductor.py` hands every
     one of those to the model inside the result envelope, and the model does
     what a model handed a finished sentence does.

     The comparison is the case that actually matters. `compare()`'s NO
     EVIDENCE sentence is the most important sentence this product produces,
     the card sets it in 26px grey, and a model repeating it underneath in body
     prose is a second, quieter copy of a refusal that works by being loud. So
     the card's copy is the one that survives, exactly as it is for a verdict.

     Same exactness as everything else here: the strings pushed are the strings
     the card RENDERS, so a field the card stops printing stops being
     suppressed. */
  const report = readEvalReport(result);
  if (report) {
    if (report.summary) out.push(report.summary);
    if (report.resolution.says) out.push(report.resolution.says);
    if (report.bucketsDecidedBy) out.push(report.bucketsDecidedBy);
  }
  const comparison = readEvalComparison(result);
  if (comparison) {
    if (comparison.says) out.push(comparison.says);
    if (comparison.resolution.says) out.push(comparison.resolution.says);
  }
  const evalRefusal = readEvalRefusal(result);
  if (evalRefusal) out.push(evalRefusal.detail);

  return out;
}

/**
 * Whether every sentence of a string is already on a card ABOVE this row.
 *
 * The same predicate `isEcho` applies to a paragraph, applied instead to the
 * engine's own `say` — and used the other way round. `isEcho` drops a
 * paragraph because a card is the durable copy; this drops the CARD's copy
 * because the sentence is already on a card. Neither one ever touches the
 * model's reply, which is the whole point of the event this serves: the wall
 * that used to delete true sentences from the transcript was interrupting one
 * turn in seven, and a renderer that deleted paragraphs instead would be the
 * same defect one layer down.
 */
function allSaidAbove(
  text: string | null,
  saidAt: Map<string, number>,
  index: number,
): boolean {
  if (!text) return false;
  const parts = splitSentences(text);
  if (parts.length === 0) return false;
  return parts.every((part) => {
    const at = saidAt.get(part);
    return at !== undefined && at < index;
  });
}

/** A paragraph with at least one sentence, every one of which a card above
 *  this row already stated. A single new sentence keeps the whole paragraph. */
function isEcho(block: Block, saidAt: Map<string, number>, index: number): boolean {
  if (block.kind !== 'p') return false;
  const parts = splitSentences(flatten(block.spans));
  if (parts.length === 0) return false;
  return parts.every((part) => {
    const at = saidAt.get(part);
    return at !== undefined && at < index;
  });
}

function flatten(spans: Span[]): string {
  return spans.map((span) => span.text).join('');
}

/** Sentences, normalised for comparison only — the text a reader sees is never
 *  passed through this. Case and whitespace are levelled because a model that
 *  re-wraps a paragraph has still not added anything; nothing else is. */
function splitSentences(text: string): string[] {
  return String(text)
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .split(/(?<=[.!?])\s+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

/* ── Small helpers ───────────────────────────────────────────────────────── */

/** The registry's verbs are written in the imperative and lower case ("read
 *  this machine's hardware"). A row starts with a capital. */
function sentence(verb: string): string {
  return verb.charAt(0).toUpperCase() + verb.slice(1);
}

/**
 * The facts a tool call carried, and what the ENGINE says they were worth.
 *
 * "A model asserting a fact in the transcript is visible as an assertion. It is
 * not a lie and it is not an error; it is an unverified claim, and the
 * interface should look neither alarmed nor credulous."
 *
 * THE ORIGIN IS READ OFF THE RESULT, NEVER DECIDED HERE. `run_diagnosis`
 * returns `your_facts_were_recorded_as` and `state_facts` returns `origin`;
 * both are computed from the actor, which comes from the call site, which is
 * the only place that knows whether a person or a model is speaking
 * (`app/tools/evidence.py`, wall 4). A version of this that assumed "a
 * transcript row means a model said it" would be a second, weaker copy of that
 * rule sitting in the interface — right today, and wrong on the day the engine
 * writes a control run into the event log.
 *
 * So a call still running shows no tag at all. Its origin is not yet a fact.
 */
function suppliedFacts(item: ToolItem): {
  names: string[];
  values: Record<string, unknown>;
  origin: FactOrigin;
  by: string;
  sentence: string;
} | null {
  const facts = item.args.facts;
  if (typeof facts !== 'object' || facts === null || Array.isArray(facts)) return null;
  const values = facts as Record<string, unknown>;
  const names = Object.keys(values);
  if (names.length === 0) return null;

  if (item.state !== 'ok' || typeof item.result !== 'object' || item.result === null) {
    return null;
  }
  const result = item.result as Record<string, unknown>;
  const raw = result.your_facts_were_recorded_as ?? result.origin;
  if (!isFactOrigin(raw)) return null;

  const by =
    item.drivenBy === 'harness'
      ? "the harness's own fixed script, which is not a witness to your week either"
      : item.drivenBy === 'user'
        ? 'you, through your own door - which is why it lands STATED'
        : 'the model, answering on your behalf';

  return {
    names: names.sort(),
    values,
    origin: raw,
    by: raw === 'ASSERTED' ? by : 'you, in your own person',
    sentence:
      raw === 'ASSERTED'
        ? 'recorded as ASSERTED, which opens no gate on its own'
        : `recorded as ${raw}`,
  };
}

/** One argument, short enough to sit on a collapsed row. */
function short(value: unknown): string {
  if (value === null || value === undefined) return 'not set';
  if (typeof value === 'string') {
    return value.length > 40 ? `${value.slice(0, 39)}…` : value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return `${value.length} items`;
  return `${Object.keys(value as object).length} fields`;
}
