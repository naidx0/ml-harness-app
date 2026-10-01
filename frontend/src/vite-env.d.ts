/// <reference types="vite/client" />

/**
 * The commit this bundle was built from, injected by `vite.config.ts`.
 *
 * `null` when the build could not read `.git`. It exists so an installed
 * window - which has no checkout beside it - can still answer "is the engine
 * I am talking to running the same code I was built from". See the `define`
 * block in the vite config for the incident that required it.
 */
declare const __UI_REVISION__: string | null;
