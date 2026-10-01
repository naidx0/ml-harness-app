import { Show } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { isFactOrigin, ORIGIN_MEANS, type FactOrigin, type GateStatus } from "./evidence-ledger"

/**
 * The tag a fact's origin renders as, and the badge a gate's status does.
 *
 * NOT the shared `ProvenanceTag`, and the reason is one word. That tag
 * speaks the hardware vocabulary, where "Declared" covers everything a
 * person or a model said. For facts that decide whether somebody trains a
 * model, "the person said so" (STATED) and "a model said so on their behalf"
 * (ASSERTED) are exactly the difference that opens or shuts a gate, so the
 * engine's own four words are kept. The hue is only the rank: a reading is
 * green, an admission that nobody measured it is amber, a repetition of
 * something said is grey - and the word carries the rest.
 */
export function OriginTag(props: { origin: string | null | undefined; by?: string | null }) {
  const known = () => (isFactOrigin(props.origin) ? props.origin : null)
  return (
    <Show when={props.origin}>
      <span
        class="shrink-0 rounded-sm px-1.5 py-px text-12-regular bg-v2-background-bg-layer-02"
        classList={{
          "text-v2-state-fg-success": known() === "MEASURED",
          "text-v2-state-fg-warning": known() === "DEFAULTED",
          "text-v2-text-text-muted": known() === "STATED" || known() === "ASSERTED" || known() === null,
        }}
        title={
          known()
            ? `${known()}: ${ORIGIN_MEANS[known() as FactOrigin]}${props.by ? ` (${props.by})` : ""}`
            : `An origin this version does not know: ${props.origin}`
        }
      >
        {props.origin}
      </span>
    </Show>
  )
}

const GATE_WORD: Record<GateStatus, string> = { PASSED: "Passed", NOT_MET: "Not met", NOT_CHECKED: "Not checked" }

/**
 * A gate's status as a glyph and a word, so the ledger reads with no colour
 * perception at all: the glyph and the word carry what the hue does.
 */
export function GateBadge(props: { status: GateStatus }) {
  return (
    <span
      class="inline-flex shrink-0 items-center gap-1 text-12-regular"
      classList={{
        "text-v2-state-fg-success": props.status === "PASSED",
        "text-v2-state-fg-danger": props.status === "NOT_MET",
        "text-v2-text-text-faint": props.status === "NOT_CHECKED",
      }}
    >
      <Icon
        name={props.status === "PASSED" ? "check" : props.status === "NOT_MET" ? "close" : "help"}
        size="small"
      />
      {GATE_WORD[props.status]}
    </span>
  )
}
