/**
 * The Stage's state: one selection, three sizes.
 *
 * docs/PHASES.md "The Stage", S1. Max's decision of 2026-09-02 fixed three
 * sizes of one thing — the detached window while a run spends (C), the inline
 * transcript row when it is done (D), the split in the shell between (A) — and
 * one rule: whichever size is showing, it is the SAME Stage. So the selection
 * (which run, gold) and the panel are held once, here, and a size change is a
 * change of size and nothing else. The test holds it to that.
 *
 * `anchor` is the transcript row the inline size is unfolded under. It is
 * state rather than a DOM lookup because the transcript re-renders on every
 * event and the row a person opened has to stay open through them.
 */

export type StageSize = 'row' | 'split' | 'window';

export type StagePanelId = 'bench' | 'sandbox' | 'progression' | 'gates' | 'retrieval';

export const STAGE_PANELS: readonly StagePanelId[] = [
  'bench',
  'sandbox',
  'progression',
  'gates',
  'retrieval',
];

export const STAGE_PANEL_TITLE: Record<StagePanelId, string> = {
  bench: 'Bench',
  sandbox: 'Sandbox',
  progression: 'Progression',
  gates: 'Gate map',
  retrieval: 'Retrieval & split',
};

export interface StageState {
  /** Which sizes are showing. The window and the split can both be open; the
   *  row is open at exactly one anchor or none. */
  sizes: { row: boolean; split: boolean; window: boolean };
  /** The transcript item key the inline row is unfolded under. */
  anchor: string | null;
  panel: StagePanelId;
  /** The selected eval run, gold across every size. Null = the newest. */
  runId: number | null;
}

export type StageAction =
  | { type: 'open'; size: StageSize; anchor?: string | null }
  | { type: 'close'; size: StageSize }
  | { type: 'pick'; runId: number | null }
  | { type: 'panel'; panel: StagePanelId };

export function initialStage(): StageState {
  return {
    sizes: { row: false, split: false, window: false },
    anchor: null,
    panel: 'bench',
    runId: null,
  };
}

export function stageReducer(state: StageState, action: StageAction): StageState {
  switch (action.type) {
    case 'open': {
      const sizes = { ...state.sizes, [action.size]: true };
      return {
        ...state,
        sizes,
        anchor: action.size === 'row' ? (action.anchor ?? state.anchor) : state.anchor,
      };
    }
    case 'close': {
      const sizes = { ...state.sizes, [action.size]: false };
      return {
        ...state,
        sizes,
        anchor: action.size === 'row' ? null : state.anchor,
      };
    }
    case 'pick':
      return { ...state, runId: action.runId };
    case 'panel':
      return { ...state, panel: action.panel };
    default:
      return state;
  }
}

/** The one place a size's visibility is asked, so the three renderers agree. */
export function stageShows(state: StageState, size: StageSize): boolean {
  return state.sizes[size];
}
