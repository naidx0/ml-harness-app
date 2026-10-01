/**
 * WHICH TOOL ROWS COLLAPSE INTO A STRIP, AND WHICH NEVER DO.
 *
 * Max, watching a turn go past: *"the tool calling, while it's nice and
 * transparent, is too loud - apart from question asks and diagnosis and so on.
 * Can we find some way to hide or condense that while the model is thinking and
 * loading? Like an animated loading or ASCII spinner working while the model
 * thinks, showing just icons for the thinking path, and when the icon is
 * clicked on we see the tool call in detail. Otherwise that way we don't
 * pollute the user's chat."*
 *
 * The exception he names - "apart from question asks and diagnosis and so on" -
 * is the important half, and it is not a list of tool names. It is whether the
 * row DRAWS SOMETHING: a diagnosis, a proposal, an approval, an eval report, a
 * carve. Those rows are the product answering, and folding one into an icon
 * would hide the most important surface in the application behind a click.
 * `components/cards.ts` is the single reader for that question and the
 * transcript uses the same one to decide what to draw, so the strip cannot
 * disagree with the row about what a row is.
 *
 * ## WHY A RUN OF TWO AND NOT OF ONE
 *
 * One tool row is not noise; it is the turn telling you the one thing it did.
 * A strip in its place would be a chevron over a single line - strictly more to
 * click and strictly less to read. The loudness Max is describing is eight of
 * them in a column, which is what a diagnosis-heavy turn produces.
 */

/** The part of a transcript row this module reads. */
export interface Row {
  kind: string;
}

/** How many consecutive plain tool rows it takes before folding is a kindness
 *  rather than an extra click. */
export const A_RUN_WORTH_FOLDING = 2;

/**
 * Runs of consecutive plain tool rows, as index lists, longest-first in the
 * order they appear.
 *
 * `plain(index)` answers "this row draws nothing but the key/value table", and
 * is passed in rather than computed here so that this module never has to know
 * what a card is - the transcript already knows, and one reader is the whole
 * point.
 */
export function toolRunsIn(
  items: readonly Row[],
  plain: (index: number) => boolean,
  least: number = A_RUN_WORTH_FOLDING,
): number[][] {
  const runs: number[][] = [];
  let current: number[] = [];

  const close = () => {
    if (current.length >= least) runs.push(current);
    current = [];
  };

  for (let index = 0; index < items.length; index += 1) {
    if (items[index].kind === 'tool' && plain(index)) {
      current.push(index);
    } else {
      close();
    }
  }
  close();
  return runs;
}

/**
 * What each index should do: lead a strip, hide inside one, or render as it
 * always has.
 *
 * Returned as one map rather than two sets because a render loop asks both
 * questions at the same index, and two structures are two chances to disagree.
 */
export function howToDrawEachRow(
  items: readonly Row[],
  plain: (index: number) => boolean,
  least: number = A_RUN_WORTH_FOLDING,
): Map<number, { leads: boolean; run: number[] }> {
  const how = new Map<number, { leads: boolean; run: number[] }>();
  for (const run of toolRunsIn(items, plain, least)) {
    for (const index of run) {
      how.set(index, { leads: index === run[0], run });
    }
  }
  return how;
}
