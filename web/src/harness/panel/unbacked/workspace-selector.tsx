import { PromptGitStatus } from "@/new-session/workspace/selector"

export { PromptGitStatus }

/**
 * Stands in for their `new-session/workspace/selector.tsx` (SUBSTITUTES in
 * web/vite.config.ts). Their selector, under the new-chat composer and in
 * its summary, picks Local or a worktree and offers "New workspace", which
 * creates one; the harness has no worktrees and refuses every call that
 * would. What it keeps is the part that works: the branch the project is on,
 * drawn by their own `PromptGitStatus` - the line their screen already shows
 * for a project with no workspaces to choose.
 *
 * Same export and props as theirs, so both call sites compile unchanged.
 */
export function PromptWorkspaceSelector(props: {
  value: string
  projectRoot: string
  workspaces: string[]
  branches: string[]
  branch?: string
  onboarding?: boolean
  variant?: "inline" | "summary"
  onChange: (value: string) => void
  onCreate: (branch: string) => void
  onSearch: (search: string) => void
  onDone?: () => void
  onViewAll: () => void
}) {
  return (
    <PromptGitStatus
      branch={props.branch}
      class={props.variant === "summary" ? "session-summary-row" : "ms-1"}
    />
  )
}
