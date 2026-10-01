/**
 * DOES THIS TOOL ROW DRAW SOMETHING, OR IS IT A KEY/VALUE TABLE?
 *
 * One reader, two callers, and that is the whole reason this file exists.
 *
 * `Transcript.tsx` has always computed this inline to decide whether to print
 * the result as a table. `components/ToolStrip.tsx` now needs the same answer
 * to decide whether a row may be folded into an icon - Max asked for tool calls
 * to condense "apart from question asks and diagnosis and so on", and that
 * "apart from" is exactly this question.
 *
 * Asking it twice would be two parsers of one source: the day somebody adds a
 * fourteenth card, they would add a reader to the transcript and the strip
 * would go on folding it, hiding a brand-new surface behind a chevron on the
 * day it shipped. So the disjunction lives here and the transcript calls it.
 *
 * WHAT IS NOT HERE. The transcript still reads each result individually,
 * because it has to draw the specific card. This answers only "did anything
 * recognise it", which is the part both callers share.
 */

import { readProposal, readProposalRefusal } from '../lib/engine/build';
import { readCarve, readCarveRefusal } from '../lib/engine/datawork';
import { readEvalComparison, readEvalRefusal, readEvalReport } from '../lib/engine/evals';
import { readDiagnosis } from '../lib/engine/facts';
import { readPromptAttempt, readPromptRefusal } from '../lib/engine/prompts';
import { readChunkingSweep, readRecallReport } from '../lib/engine/retrieval';
import { readApprovalRequest } from './ApprovalCard';

/** The part of a tool row this reads. */
export interface ToolResult {
  /** `ok` when the CALL worked, whatever the tool answered. */
  state: string;
  result: unknown;
}

export function toolRowDrawsACard(item: ToolResult, canApprove: boolean): boolean {
  /* A DIAGNOSIS AND A PROPOSAL ARE READ ONLY FROM AN `ok` ROW, matching the
     transcript: a failed call has no verdict to draw and a half-written result
     should not be parsed as one. A REFUSAL is read from either state, because
     `propose_build` answers `ok: false` with what is missing while the CALL
     itself worked - that is the product working and it is a card. */
  const fromOk = item.state === 'ok';
  return (
    (fromOk && readDiagnosis(item.result) !== null) ||
    (fromOk && readProposal(item.result) !== null) ||
    readProposalRefusal(item.result) !== null ||
    (fromOk && readEvalReport(item.result) !== null) ||
    (fromOk && readEvalComparison(item.result) !== null) ||
    readEvalRefusal(item.result) !== null ||
    readPromptAttempt(item.result) !== null ||
    readPromptRefusal(item.result) !== null ||
    readChunkingSweep(item.result) !== null ||
    readRecallReport(item.result) !== null ||
    readCarve(item.result) !== null ||
    readCarveRefusal(item.result) !== null ||
    /* An approval is only a card when there is somewhere to send the yes.
       Without `onApproveTool` the transcript draws no button, and a row that
       cannot be acted on is an ordinary failed row. */
    (canApprove && readApprovalRequest(item.result) !== null)
  );
}
