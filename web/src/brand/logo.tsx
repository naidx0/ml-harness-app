import type { ComponentProps } from "solid-js"
import { Wordmark } from "./wordmark"

/**
 * This product's marks, in place of `@opencode/ui/logo`.
 *
 * Same reason as `wordmark.tsx`: MIT covers their code, not their trademark,
 * and their `Logo` IS the "opencode" lettering. It appears on the new-chat
 * screen (twice: a faint base copy, and a copy under a light sweep) and on
 * their error screen.
 *
 * THE NEW-CHAT TITLE IS THE PRODUCT SPEAKING, so it is drawn legibly. Their
 * call site sets the base copy to 16% opacity, which suits their lettering
 * and left the harness's name a ghost. The base copy is drawn at a
 * reading strength here (an inline style beats their class); the sweep copy,
 * recognised by its class, keeps their animation untouched.
 *
 * The three exports keep their prop surfaces, because their call sites are
 * byte-identical and pass exactly these.
 */

export const Logo = (props: { class?: string }) => {
  const sweep = props.class?.includes("wordmark-shimmer") ?? false
  return (
    <Wordmark
      class={props.class}
      style={sweep ? undefined : { opacity: 0.82 }}
      fade={false}
      muted={false}
      voice
    />
  )
}

/**
 * The small mark: the product's initials in the display face, inside the
 * rounded square the outgoing rail drew its glyph in.
 */
export const Mark = (props: { class?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="ML Harness" class={props.class}>
    <rect x="2" y="2" width="60" height="60" rx="12" fill="none" stroke="currentColor" stroke-width="2" />
    <text
      x="32"
      y="41"
      text-anchor="middle"
      style={{ "font-family": "var(--font-family-display)" }}
      font-size="24"
      font-weight="600"
      letter-spacing="-0.02em"
      fill="currentColor"
    >
      ML
    </text>
  </svg>
)

/** Their splash takes a ref; the mark stands in for it. */
export const Splash = (props: Pick<ComponentProps<"svg">, "ref" | "class">) => (
  <svg ref={props.ref} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" class={props.class} aria-hidden="true">
    <rect x="2" y="2" width="60" height="60" rx="12" fill="none" stroke="currentColor" stroke-width="2" />
    <text
      x="32"
      y="41"
      text-anchor="middle"
      style={{ "font-family": "var(--font-family-display)" }}
      font-size="24"
      font-weight="600"
      letter-spacing="-0.02em"
      fill="currentColor"
    >
      ML
    </text>
  </svg>
)
