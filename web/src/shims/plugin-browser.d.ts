/**
 * Types for `@opencode/plugin-browser/rpc`, which is not installed.
 *
 * Their app imports `Browser` from it in three places, all `import type`, so
 * the runtime never reaches it and the Vite build is unaffected - the type
 * checker still has to resolve the name. The package drives an Electron
 * WebContentsView with no Tauri equivalent and is dropped; see
 * scripts/build_app_manifest.py.
 *
 * Loosely typed on purpose. The browser pane is never mounted here, and
 * modelling every member of a surface that cannot exist is precision with
 * nothing to protect. What IS guarded is the runtime: nothing in this product
 * routes to that pane.
 */
declare module "@opencode/plugin-browser/rpc" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export namespace Browser {
    type Client = any
    type State = any
    type Event = any
    type Target = any
    type Tab = any
    type Page = any
    type Request = any
    type Response = any
    type Snapshot = any
    type TabID = any
    type Action = any
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type Browser = any
}
