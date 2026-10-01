import { createMemo, createSignal, For, onCleanup, onMount } from "solid-js"
import { linearScale, niceStep, Swatch, TONE } from "./chart"
import { latticeRow, runLabel, type Cell, type StagePayload, type StageRun } from "./stage-data"

/**
 * Every run's rows, side by side: the Bench's lattice.
 *
 * One column per eval row, one line per run, in SVG. The column scale places
 * the cells and the row-index labels above them, so a label always sits over
 * its own column however narrow the panel gets. Below a few pixels a cell
 * stops being legible, so the lattice keeps a floor width and scrolls
 * sideways rather than shrinking into noise.
 *
 * The selected run's label takes gold - this product's selection colour,
 * as the outgoing Stage drew it. Cobalt (their accent) is for send and focus
 * only, so it is not used for a selection here.
 *
 * Each run label is a button: focusable, and Enter or Space picks the run,
 * so the lattice is not a mouse-only way to choose one. The SVG is a group,
 * not an image - an image's children are hidden from assistive technology,
 * which would hide the buttons with them.
 */

/** Selection, in this product's gold (brand/identity.css). */
const SELECTED = "var(--harness-gold)"

const LABEL_WIDTH = 104
const ROW_HEIGHT = 16
const HEADER = 14
const MIN_CELL = 4
const MAX_CELL = 14

const FILL: Record<Cell, string> = {
  held: "transparent",
  right: TONE.good,
  wrong: "var(--v2-background-bg-layer-04)",
  up: TONE.good,
  down: "var(--v2-background-bg-layer-04)",
}

const STROKE: Partial<Record<Cell, string>> = {
  held: TONE.grid,
  up: "var(--v2-text-text-base)",
  down: TONE.bad,
}

const WORD: Record<Cell, string> = {
  held: "not graded",
  right: "right",
  wrong: "wrong",
  up: "right, and wrong at the baseline",
  down: "wrong, and right at the baseline",
}

export function Lattice(props: { payload: StagePayload; selected: StageRun | null; onPick: (runId: number) => void }) {
  const [available, setAvailable] = createSignal(360)
  let element: HTMLDivElement | undefined
  onMount(() => {
    if (!element) return
    const read = () => {
      const width = element?.getBoundingClientRect().width ?? 0
      if (width > 0) setAvailable(Math.round(width))
    }
    read()
    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(read)
    observer.observe(element)
    onCleanup(() => observer.disconnect())
  })

  const columns = () => Math.max(0, ...props.payload.runs.map((run) => run.planned))
  const cell = () => Math.max(MIN_CELL, Math.min(MAX_CELL, (available() - LABEL_WIDTH) / Math.max(1, columns())))
  const width = () => LABEL_WIDTH + cell() * columns()
  const height = () => HEADER + ROW_HEIGHT * props.payload.runs.length
  const x = () => linearScale([0, Math.max(1, columns())], [LABEL_WIDTH, width()])
  const baseline = createMemo(() => props.payload.runs.find((run) => run.run_id === props.payload.baseline_run_id) ?? null)
  // Label every column when they fit, otherwise every nice step of them.
  const labelled = () => {
    const step = cell() >= 12 ? 1 : Math.max(1, niceStep(columns(), Math.floor((available() - LABEL_WIDTH) / 28)))
    const out: number[] = []
    for (let i = 0; i < columns(); i += step) out.push(i)
    return out
  }

  return (
    <div class="flex flex-col gap-2 px-4">
      <div ref={element} class="w-full overflow-x-auto">
        <svg width={width()} height={height()} viewBox={`0 0 ${width()} ${height()}`} class="block" role="group" aria-label="Every run's graded rows">
          <For each={labelled()}>
            {(index) => (
              <text x={x()(index + 0.5)} y={HEADER - 4} text-anchor="middle" font-size="10" fill={TONE.label}>
                {index}
              </text>
            )}
          </For>
          <For each={props.payload.runs}>
            {(run, line) => {
              const cells = () => latticeRow(run, baseline(), columns())
              const top = () => HEADER + line() * ROW_HEIGHT
              const selected = () => run.run_id === props.selected?.run_id
              return (
                <g>
                  <text
                    x={0}
                    y={top() + ROW_HEIGHT / 2 + 4}
                    font-size="11"
                    fill={selected() ? SELECTED : "var(--v2-text-text-muted)"}
                    font-weight={selected() ? 600 : 400}
                    style={{ cursor: "pointer" }}
                    class="outline-none focus-visible:outline-2 focus-visible:outline-v2-border-border-focus"
                    tabindex={0}
                    role="button"
                    aria-pressed={selected()}
                    aria-label={`Show run ${run.run_id}`}
                    onClick={() => props.onPick(run.run_id)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter" && event.key !== " ") return
                      event.preventDefault()
                      props.onPick(run.run_id)
                    }}
                  >
                    <title>{`Show run ${run.run_id}`}</title>
                    {`${runLabel(run, props.payload.baseline_run_id)} ${run.run_id}`}
                  </text>
                  <For each={cells()}>
                    {(kind, index) => (
                      <rect
                        x={x()(index()) + 0.5}
                        y={top() + 2}
                        width={Math.max(1, cell() - 1.5)}
                        height={ROW_HEIGHT - 4}
                        rx={1.5}
                        fill={FILL[kind]}
                        stroke={STROKE[kind] ?? "none"}
                        stroke-width={kind === "held" ? 1 : 1.5}
                      >
                        <title>{`Run ${run.run_id}, row ${index()}: ${WORD[kind]}`}</title>
                      </rect>
                    )}
                  </For>
                </g>
              )
            }}
          </For>
        </svg>
      </div>
      <div class="flex flex-wrap gap-x-3 gap-y-1 text-12-regular text-v2-text-text-muted">
        <Swatch color={TONE.good}>judged right</Swatch>
        <Swatch color="var(--v2-background-bg-layer-04)">judged wrong</Swatch>
        <Swatch color={TONE.grid} outline>
          not graded
        </Swatch>
        <Swatch color="var(--v2-text-text-base)" outline>
          flipped up vs baseline {props.payload.baseline_run_id ?? "—"}
        </Swatch>
        <Swatch color={TONE.bad} outline>
          flipped down
        </Swatch>
      </div>
    </div>
  )
}
