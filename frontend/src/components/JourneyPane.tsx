/**
 * THE JOURNEY PANE, COMPOSED ONCE.
 *
 * The shell used to compose `<Journey>` inline with sixty lines of handlers;
 * the pane window (`PaneWindow.tsx`) needs the same pane for the same thread
 * from its own window, and two copies of those handlers would be two places
 * for the refusal-reading rule below to drift. So the composition lives here
 * and both windows mount it with a thread id and a way to open Controls.
 */

import { runTool as runToolRequest } from '../lib/engine/client';
import { chooseJourney, type Prefilled } from '../lib/engine/journey';
import { useJourney } from '../lib/useJourney';
import { Journey } from './Journey';

export function JourneyPane({
  threadId,
  lastEventId,
  active,
  onDoStep,
  onChanged,
}: {
  threadId: number | null;
  lastEventId: number;
  /** Fetched only while the pane is showing; see `useJourney`. */
  active: boolean;
  /** "Do this step" opens Controls on that tool with the prefill. */
  onDoStep: (tool: string, prefill: Record<string, Prefilled>) => void;
  /** After a journey is chosen: the shell re-reads what it holds. */
  onChanged: () => void;
}) {
  const data = useJourney(threadId, lastEventId, active);
  if (!active) return null;
  return (
    <Journey
      payload={data.payload}
      loading={data.loading}
      error={data.error}
      onChooseJourney={(name) => {
        if (threadId === null) return;
        void chooseJourney(threadId, name).then(() => {
          data.refresh();
          onChanged();
        });
      }}
      onRunStep={async (tool, prefill, approved) => {
        /* THE BUTTON IS THE DOOR. Same route the Controls dialog uses, so the
           run is filed under this conversation and writes the same "run by
           you" rows - the route learns what happened because the transcript
           did.

           A REFUSAL IS RETURNED, NEVER THROWN. `runTool` rejects on a 4xx,
           which is how the approval refusal (428) and a rejected argument
           (400) arrive; both carry a sentence this product already wrote as a
           remedy, and the flow shows it in place. Letting it throw would put
           the one useful screen in a console nobody reads - and closes the
           gap J11 named, where a raised refusal left no event row at all. */
        const args: Record<string, unknown> = {};
        for (const [field, offered] of Object.entries(prefill)) {
          args[field] = offered.value;
        }
        try {
          const answered = await runToolRequest(tool, args, approved, threadId);
          const body = answered.result as {
            ok?: boolean;
            detail?: string;
            summary?: string;
            error?: string;
            help?: string;
          } | null;
          data.refresh();
          if (!body || body.ok !== false) return { ok: true };
          /* WHICH FIELD CARRIES THE REFUSAL IS NOT ONE FIELD. This read only
             `detail`, and the walk caught it: a tool that refuses through
             `summary`, or through `error` + `help`, came out as "it did not
             run, and said nothing about why" - a bare failure, which the
             evidence puts at d = 0.05 and below saying nothing at all. It is
             the one thing this whole goal is against, and it was mine. */
          const said = [body.detail, body.summary, body.error].find(
            (part) => typeof part === 'string' && part.trim(),
          );
          const help = typeof body.help === 'string' ? body.help.trim() : '';
          return {
            ok: false,
            detail: said ? [said.trim(), help].filter(Boolean).join(' ') : undefined,
          };
        } catch (problem) {
          data.refresh();
          return {
            ok: false,
            detail: problem instanceof Error ? problem.message : String(problem),
          };
        }
      }}
      onDoStep={onDoStep}
    />
  );
}
