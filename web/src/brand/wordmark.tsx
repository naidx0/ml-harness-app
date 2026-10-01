import { createUniqueId, Show, type ComponentProps } from "solid-js"

/**
 * This product's wordmark, replacing OpenCode's.
 *
 * NOT A STYLE CHOICE - A LICENCE ONE, first. MIT grants copyright, not
 * trademark: their lettering and app icons sit outside the grant, so the
 * component is substituted rather than restyled, and their desktop icons are
 * never vendored.
 *
 * AND THEN THE HARNESS'S OWN MARK, not a stand-in: the product's name as live
 * text in its display face (brand/identity.css, --font-family-display, loaded
 * in entry.tsx), so it is the real font and not outlines. The owner,
 * 2026-09-22, retired the spaced Roman capitals and the italic serif that
 * were here ("this kind of Roman old style, and a little too spaced between
 * the words") for a clean grotesque: the name as it is written, "ML Harness",
 * at 600 and tracked tight; the line beneath, "Let's build", in the same face
 * at 400, muted.
 *
 * The prop surface matches theirs exactly (`class`, `fade`, `muted`,
 * `outline`) because their call sites pass all four; the fade is the same
 * mechanism - a gradient mask - so the mark dissolves rather than ending on a
 * hard edge. `voice` adds the line beneath, used on the new-chat title.
 */

const NAME = "ML Harness"
const VOICE = "Let’s build"

export function Wordmark(
  props: Pick<ComponentProps<"svg">, "class" | "style"> & {
    fade?: boolean
    muted?: boolean
    outline?: boolean
    voice?: boolean
  },
) {
  const mask = createUniqueId()
  const gradient = createUniqueId()

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 720 129"
      role="img"
      aria-label="ML Harness"
      class={props.class}
      style={props.style}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="white" stop-opacity="1" />
          <stop offset="64%" stop-color="white" stop-opacity="1" />
          <stop offset="100%" stop-color="white" stop-opacity="0" />
        </linearGradient>
        <mask id={mask}>
          <rect x="0" y="0" width="720" height="129" fill={`url(#${gradient})`} />
        </mask>
      </defs>

      <g
        opacity={props.muted === false ? 1 : 0.6}
        class="[[data-color-scheme=dark]_&]:opacity-100"
        mask={props.fade === false ? undefined : `url(#${mask})`}
        fill={props.outline ? "none" : "currentColor"}
        stroke={props.outline ? "currentColor" : "none"}
        stroke-width={props.outline ? 1 : 0}
      >
        <text
          x="360"
          y={props.voice ? 72 : 84}
          text-anchor="middle"
          style={{ "font-family": "var(--font-family-display)" }}
          font-size="68"
          font-weight="600"
          letter-spacing="-0.02em"
        >
          {NAME}
        </text>
        <Show when={props.voice}>
          <text
            x="360"
            y="114"
            text-anchor="middle"
            style={{ "font-family": "var(--font-family-display)" }}
            font-weight="400"
            font-size="26"
            fill-opacity={props.outline ? undefined : 0.62}
          >
            {VOICE}
          </text>
        </Show>
      </g>
    </svg>
  )
}
