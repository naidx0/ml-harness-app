/**
 * THE THINKING PATH, AS ICONS.
 *
 * Max: *"the tool calling, while it's nice and transparent, is too loud... can
 * we find some way to hide or condense that while the model is thinking and
 * loading - like an animated loading or ASCII spinner working while the model
 * thinks, showing just icons for the thinking path, and when the icon is
 * clicked on we see the tool call in detail. Otherwise that way we don't
 * pollute the user's chat."*
 *
 * One icon per call, in the order they ran, with the name of the last one and a
 * spinner while the turn is still going. Clicking an icon does not open
 * anything here - it tells the transcript to render that row where it always
 * was, under the strip. That is deliberate: a tool row carries an approval
 * button, a stage link and a refusal reader, and a second copy of it inside
 * this component would be a second set of buttons that could disagree with the
 * first about what has been approved.
 *
 * THE SPINNER IS SEQUENCE'S. Max, 2026-09-11: *"add a better loading prompt
 * animation, if you can read my sequence project they have a good example of
 * spinning or working prompt loading spinners and tool calls minimized."*
 * Read: `packages/web2/src/chat/ThinkingMark.tsx` and its CSS - a braille
 * orbit (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) stepping in a 14px mono cell, and the live row's name
 * carrying a slow shimmer. Both are here, in this product's tokens: the glyph
 * is `.toolstrip__spin` (the class the tests know), the shimmer is on the name
 * while `working`. A braille orbit reads as "working" the way a ring reads as
 * "wait", which is the difference his note was pointing at.
 *
 * WHAT NEVER REACHES THIS COMPONENT. A row that draws a card - a diagnosis, a
 * proposal, an approval, an eval. `lib/foldTheToolRows.ts` breaks a run on
 * one, so the exception Max named is enforced before this is called rather
 * than checked again inside it.
 */

import { Icon, groupIcon } from './Icon';
import type { ToolItem } from '../lib/transcript';
import type { ToolControl } from '../lib/engine/types';

export function ToolStrip({
  run,
  tools,
  working,
  seconds,
  opened,
  onToggle,
}: {
  /** The calls this strip stands for, in the order they ran. */
  run: ToolItem[];
  /** The roster, for each call's group glyph. The transcript already
   *  holds it, so the strip reads the same map the rows do rather than
   *  keeping a second opinion about which tool is which. */
  tools: Map<string, ToolControl>;
  /** True while the turn that produced the last of them is still running. */
  working: boolean;
  /** THE TURN'S MEASURED WALL TIME, from `stream.end`, or null until it
   *  arrives. `null` is drawn as nothing rather than as a zero: a turn whose
   *  duration has not landed has no duration, and printing `0s` would be a
   *  measurement nobody took. */
  seconds?: number | null;
  /** Which of them are currently expanded, by `item.key`. */
  opened: ReadonlySet<string>;
  onToggle: (key: string) => void;
}) {
  const failed = run.filter((item) => item.state !== 'ok').length;

  return (
    <div className="toolstrip" data-working={working || undefined}>
      {/* ONE ORBIT ON SCREEN, AND IT IS NOT THIS ONE. Max, 2026-09-13: "look
          at the spinner - I don't like the repetitiveness where it's double
          loading symbols; have one big one and then the tool call
          differently." A running tool row and the working row underneath it
          both spun the same braille glyph, so two things moved and neither
          was clearly the answer to "is it working". The big orbit stays with
          the working row (`Transcript.tsx`), which is the one that means the
          model is thinking; a tool that is still running gets a pulse - a
          different shape for a different fact. */}
      {working ? <span className="toolstrip__pulse" aria-hidden="true" /> : null}
      <span className="toolstrip__icons">
        {run.map((item) => (
          <button
            key={item.key}
            type="button"
            className="toolstrip__icon"
            aria-pressed={opened.has(item.key)}
            data-failed={item.state !== 'ok' || undefined}
            title={`${item.name}${item.state === 'ok' ? '' : ' — failed'}`}
            aria-label={`Show the ${item.name} call`}
            onClick={() => onToggle(item.key)}
          >
            <Icon name={iconFor(tools, item.name)} size={13} />
          </button>
        ))}
      </span>
      {/* HOW MANY, AND HOW LONG. The fold is the line a person actually
          reads when a turn has settled, and it carried only the count - the
          measured duration was one line further down, on the metarow beside
          the model and the locality, so one turn's identity was split across
          two lines and the fold was the half without the number. It is the
          same `TurnItem.seconds` the metarow prints, read rather than
          recomputed, so the two can never disagree. Rounded here and exact on
          the hover, the rounding rule the metarow already documents. */}
      <span
        className="toolstrip__said"
        data-live={working || undefined}
        title={
          !working && seconds != null ? `${run.length} steps in ${seconds}s` : undefined
        }
      >
        {working
          ? (tools.get(run[run.length - 1].name)?.verb ?? run[run.length - 1].name)
          : `${run.length} steps${failed ? `, ${failed} failed` : ''}${
              seconds != null ? ` · ${Math.round(seconds)}s` : ''
            }`}
      </span>
    </div>
  );
}

/** A call's glyph: its group's, or the generic tool mark when the roster
 *  has not been read yet - the transcript renders before `/api/tools`
 *  answers on a cold start, and an icon-less strip is worse than a generic
 *  one. `skill` is what a row with no control already draws. */
function iconFor(tools: Map<string, ToolControl>, name: string) {
  const control = tools.get(name);
  return control ? groupIcon(control.group) : ('skill' as const);
}
