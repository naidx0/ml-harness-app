import { createSignal, For, onCleanup, onMount, Show, type JSX } from "solid-js"

/**
 * The charts the harness panes draw, in inline SVG and nothing else.
 *
 * No chart library: the outgoing Stage drew its loss curve and its bars by
 * hand, the panes need three shapes in total, and a library would bring its
 * own palette and its own type scale into a panel that is otherwise entirely
 * OpenCode's. What this file does insist on is ONE SCALE PER AXIS: the mark,
 * the grid line and the tick label for a value are all placed by the same
 * function, so a label can never sit beside a line it does not describe. The
 * outgoing loss chart computed its tick positions and its line positions with
 * two copies of the same arithmetic; this is that arithmetic, once.
 *
 * Every colour is a theme token read through `var(--v2-...)`, so a chart
 * follows the light and dark themes the way the rest of their panel does.
 * The series colours are their agent colours - the one set of hues in the
 * theme that is categorical rather than a verdict - which keeps green and red
 * free to mean "right" and "flipped down" on the same surface.
 */

/** Categorical series colours, from the theme. Never a verdict colour. */
export const SERIES = [
  "var(--v2-agent-build-solid)",
  "var(--v2-agent-plan-solid)",
  "var(--v2-agent-explore-solid)",
] as const

/** Verdict colours, from the theme's state tokens. */
export const TONE = {
  good: "var(--v2-state-fg-success)",
  bad: "var(--v2-state-fg-danger)",
  info: "var(--v2-state-fg-info)",
  warn: "var(--v2-state-fg-warning)",
  // A reading's bar or meter: bone ink, neutral. NOT the accent - cobalt is
  // for send and focus only, and gold is for selection only.
  data: "var(--v2-text-text-base)",
  track: "var(--v2-background-bg-layer-02)",
  grid: "var(--v2-border-border-muted)",
  axis: "var(--v2-border-border-base)",
  label: "var(--v2-text-text-faint)",
} as const

export type Scale = {
  (value: number): number
  readonly domain: readonly [number, number]
  readonly range: readonly [number, number]
}

/**
 * A linear map from `domain` to `range`. A domain of zero width maps every
 * value to the middle of the range rather than dividing by zero, because a
 * flat loss curve is a real result and should draw as a flat line, not NaN.
 */
export function linearScale(domain: readonly [number, number], range: readonly [number, number]): Scale {
  const [d0, d1] = domain
  const [r0, r1] = range
  const width = d1 - d0
  const scale = ((value: number) => (width === 0 ? (r0 + r1) / 2 : r0 + ((value - d0) / width) * (r1 - r0))) as Scale
  Object.defineProperty(scale, "domain", { value: [d0, d1] as const })
  Object.defineProperty(scale, "range", { value: [r0, r1] as const })
  return scale
}

/**
 * A step of 1, 2 or 5 times a power of ten that puts about `count` ticks
 * across `span`. The usual nice-number rule; the point of having it is that
 * a tick reads 0.5 rather than 0.4833.
 */
export function niceStep(span: number, count = 4): number {
  if (!(span > 0) || !Number.isFinite(span)) return 1
  const raw = span / Math.max(1, count)
  const power = 10 ** Math.floor(Math.log10(raw))
  const unit = raw / power
  const nice = unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10
  return nice * power
}

/**
 * The domain a chart should draw: the data's extent widened outwards to
 * whole steps, and to zero when `zero` is asked for (a loss axis starts at
 * zero so a fall from 2.1 to 1.9 is not drawn as a collapse).
 */
export function niceDomain(values: readonly number[], options: { zero?: boolean; count?: number } = {}): [number, number] {
  const finite = values.filter((value) => Number.isFinite(value))
  if (finite.length === 0) return [0, 1]
  let min = Math.min(...finite)
  let max = Math.max(...finite)
  if (options.zero) {
    min = Math.min(0, min)
    max = Math.max(0, max)
  }
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.1
    min -= pad
    max += pad
    if (options.zero && min < 0 && Math.min(...finite) >= 0) min = 0
  }
  const step = niceStep(max - min, options.count)
  return [Math.floor(min / step + 1e-9) * step, Math.ceil(max / step - 1e-9) * step]
}

/** The ticks across a domain at a nice step, inclusive of both ends that fall on one. */
export function ticksOf(domain: readonly [number, number], count = 4): number[] {
  const [lo, hi] = domain
  const step = niceStep(hi - lo, count)
  const out: number[] = []
  const first = Math.ceil(lo / step - 1e-9)
  const last = Math.floor(hi / step + 1e-9)
  for (let i = first; i <= last; i += 1) out.push(Number((i * step).toPrecision(12)))
  return out
}

/** A tick label with as many decimals as its step needs, and no more. */
export function tickLabel(value: number, step: number): string {
  const decimals = step >= 1 ? 0 : Math.min(6, Math.ceil(-Math.log10(step) - 1e-9))
  return value.toFixed(decimals)
}

/**
 * The width of an element, kept current. Charts draw at their real pixel
 * width so an 11px label stays 11px in a narrow side panel instead of
 * shrinking with a viewBox scaled to fit.
 */
function useWidth(fallback: number) {
  const [width, setWidth] = createSignal(fallback)
  let element: HTMLDivElement | undefined
  onMount(() => {
    if (!element) return
    const read = () => {
      const measured = element?.getBoundingClientRect().width ?? 0
      if (measured > 0) setWidth(Math.round(measured))
    }
    read()
    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(read)
    observer.observe(element)
    onCleanup(() => observer.disconnect())
  })
  return { width, ref: (el: HTMLDivElement) => (element = el) }
}

export type LineSeries = {
  id: string
  color: string
  points: readonly { x: number; y: number }[]
}

/**
 * A line chart with a y grid. Both axes go through one scale each, and the
 * scales are built from nice domains so the top and bottom grid lines land on
 * labelled values.
 */
export function LineChart(props: {
  series: readonly LineSeries[]
  label: string
  xUnit?: string
  height?: number
  yZero?: boolean
}) {
  const box = useWidth(480)
  const height = () => props.height ?? 180
  const pad = { left: 36, right: 12, top: 10, bottom: 22 }

  const xs = () => props.series.flatMap((series) => series.points.map((point) => point.x))
  const ys = () => props.series.flatMap((series) => series.points.map((point) => point.y))
  const xDomain = (): [number, number] => {
    const values = xs()
    return values.length ? [Math.min(0, ...values), Math.max(1, ...values)] : [0, 1]
  }
  const yDomain = () => niceDomain(ys(), { zero: props.yZero ?? true })
  const x = () => linearScale(xDomain(), [pad.left, Math.max(pad.left + 1, box.width() - pad.right)])
  const y = () => linearScale(yDomain(), [height() - pad.bottom, pad.top])
  const yTicks = () => ticksOf(yDomain())
  const yStep = () => niceStep(yDomain()[1] - yDomain()[0])

  return (
    <div ref={box.ref} class="w-full">
      <svg
        width={box.width()}
        height={height()}
        viewBox={`0 0 ${box.width()} ${height()}`}
        role="img"
        aria-label={props.label}
        class="block"
      >
        <For each={yTicks()}>
          {(tick) => (
            <g>
              <line x1={pad.left} x2={box.width() - pad.right} y1={y()(tick)} y2={y()(tick)} stroke={TONE.grid} />
              <text x={pad.left - 6} y={y()(tick) + 3.5} text-anchor="end" font-size="11" fill={TONE.label}>
                {tickLabel(tick, yStep())}
              </text>
            </g>
          )}
        </For>
        <line
          x1={pad.left}
          x2={box.width() - pad.right}
          y1={height() - pad.bottom}
          y2={height() - pad.bottom}
          stroke={TONE.axis}
        />
        <text x={x()(xDomain()[0])} y={height() - 6} font-size="11" fill={TONE.label}>
          {xDomain()[0]}
        </text>
        <text x={x()(xDomain()[1])} y={height() - 6} text-anchor="end" font-size="11" fill={TONE.label}>
          {`${xDomain()[1]}${props.xUnit ? ` ${props.xUnit}` : ""}`}
        </text>
        <For each={props.series}>
          {(series) => (
            <polyline
              fill="none"
              stroke={series.color}
              stroke-width="1.5"
              stroke-linejoin="round"
              points={series.points.map((point) => `${x()(point.x).toFixed(1)},${y()(point.y).toFixed(1)}`).join(" ")}
            />
          )}
        </For>
      </svg>
    </div>
  )
}

/**
 * A horizontal meter on a 0..1 scale: a track, an optional interval band, a
 * fill, and an optional marker line (a target, or a card's capacity). All
 * four go through the same scale.
 */
export function Meter(props: {
  value: number | null
  color?: string
  band?: readonly [number, number] | null
  marker?: number | null
  markerColor?: string
  height?: number
  title?: string
}) {
  const box = useWidth(160)
  const height = () => props.height ?? 8
  const x = () => linearScale([0, 1], [0, box.width()])
  const clamp = (value: number) => Math.min(1, Math.max(0, value))
  return (
    <div ref={box.ref} class="w-full min-w-0" title={props.title}>
      <svg width={box.width()} height={height()} viewBox={`0 0 ${box.width()} ${height()}`} class="block" aria-hidden="true">
        <rect x={0} y={0} width={box.width()} height={height()} rx={height() / 2} fill={TONE.track} />
        <Show when={props.band}>
          {(band) => (
            <rect
              x={x()(clamp(band()[0]))}
              y={0}
              width={Math.max(0, x()(clamp(band()[1])) - x()(clamp(band()[0])))}
              height={height()}
              fill={props.color ?? TONE.data}
              opacity={0.25}
            />
          )}
        </Show>
        <Show when={props.value !== null && props.value !== undefined}>
          <rect
            x={0}
            y={0}
            width={x()(clamp(props.value ?? 0))}
            height={height()}
            rx={height() / 2}
            fill={props.color ?? TONE.data}
          />
        </Show>
        <Show when={props.marker !== null && props.marker !== undefined}>
          <line
            x1={x()(clamp(props.marker ?? 0))}
            x2={x()(clamp(props.marker ?? 0))}
            y1={0}
            y2={height()}
            stroke={props.markerColor ?? TONE.good}
            stroke-width="2"
          />
        </Show>
      </svg>
    </div>
  )
}

/** A small legend swatch and its words. */
export function Swatch(props: { color: string; line?: boolean; outline?: boolean; children: JSX.Element }) {
  return (
    <span class="inline-flex items-center gap-1.5">
      <span
        class="inline-block shrink-0"
        style={{
          width: props.line ? "12px" : "8px",
          height: props.line ? "2px" : "8px",
          "border-radius": props.line ? "1px" : "2px",
          background: props.outline ? "transparent" : props.color,
          border: props.outline ? `1.5px solid ${props.color}` : undefined,
        }}
      />
      <span>{props.children}</span>
    </span>
  )
}
