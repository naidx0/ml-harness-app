import { SessionReviewToggle as TheirToggle } from "@/session/header/session-header-actions"
import { HarnessSessionMount } from "./mount"

/**
 * Their session header actions, unchanged, with the harness mounted beside
 * them.
 *
 * Substituted for `session/header/session-header-actions.tsx` by resolved
 * path (`SUBSTITUTES` in web/vite.config.ts). The import above reaches THEIR
 * module, because the substitution skips imports made from this file, so this
 * is a wrapper and never a copy.
 *
 * Why here: their review toggle is the one component inside the session tree
 * that renders on every desktop session, and the harness needs a foothold in
 * that tree - session commands, opening a panel when a run starts - that entry
 * children, which sit outside their layout, cannot have. The mount draws
 * nothing, so their header keeps its exact spacing.
 */
export * from "@/session/header/session-header-actions"

export function SessionReviewToggle() {
  return (
    <>
      <HarnessSessionMount />
      <TheirToggle />
    </>
  )
}
