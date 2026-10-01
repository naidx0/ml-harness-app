/**
 * A no-op stand-in for `@sentry/solid`.
 *
 * OpenCode's app reports errors to Sentry from three places: `init` at
 * startup, and two dynamic `import("@sentry/solid").then(captureException)`
 * calls in the error boundary and the error screen.
 *
 * This product does not phone home. The honest way to hold that line is not to
 * install the package and then leave the DSN unset - that ships a telemetry
 * client and trusts a config value to keep it quiet. It is to make the module
 * unable to send anything, which is what this is: the dependency is absent from
 * `package.json` entirely, and Vite aliases the import here.
 *
 * `captureException` still logs, because an error boundary that swallows the
 * error silently is worse than one that reports it somewhere useless. The
 * console is where a local-first product's crash reports belong.
 *
 * If this ever stops matching their call sites the build breaks rather than
 * silently dropping errors, because the alias is on the module name and any
 * new named import would be undefined at the point it is called.
 */

/** Always false: there is no client to be enabled. Their error screen asks. */
export function isEnabled(): boolean {
  return false
}

export function init(_options?: unknown): void {
  // Deliberately nothing. See above.
}

export function captureException(error: unknown, _hint?: unknown): string {
  console.error("[unreported]", error)
  return ""
}

export function captureMessage(message: string, _level?: unknown): string {
  console.warn("[unreported]", message)
  return ""
}

export function setTag(_key: string, _value: unknown): void {}
export function setContext(_key: string, _context: unknown): void {}
export function addBreadcrumb(_breadcrumb: unknown): void {}

export const withSentryErrorBoundary = <T,>(component: T): T => component
