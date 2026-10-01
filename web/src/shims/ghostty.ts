/**
 * A stand-in for `ghostty-web`, OpenCode's terminal emulator.
 *
 * Their app has a terminal pane. This product does not: the harness drives a
 * Python engine over HTTP and shells out nowhere the person needs to watch a
 * PTY. The real package is a WebAssembly terminal pinned to a GitHub commit,
 * and pulling it in to render a surface we never open would be several
 * megabytes of dead weight.
 *
 * So it is not installed, and this resolves in its place. Everything here
 * exists only to satisfy the imports in `session/terminal/*`; the terminal
 * component is never mounted, because nothing in the harness routes to it.
 *
 * IT THROWS RATHER THAN NO-OPS ON PURPOSE. A silent stub would let a future
 * change mount the terminal and produce a blank pane with no explanation. This
 * way the first person to try gets a sentence telling them what happened and
 * what the choice was.
 */

const ABSENT =
  "ghostty-web is not installed: the harness has no terminal surface. " +
  "See web/src/shims/ghostty.ts."

export class Ghostty {
  [member: string]: any
  constructor(..._args: unknown[]) {
    throw new Error(ABSENT)
  }
  static init(): never {
    throw new Error(ABSENT)
  }
  static load(..._args: unknown[]): never {
    throw new Error(ABSENT)
  }
}

// Their terminal reads a dozen members off these (rows, cols, write,
// textarea, scrollToLine...). Typing each one faithfully would be precision
// spent on a surface this product never mounts, and the constructors throw
// before any of it could run. The index signatures say exactly that: the
// shape is unconstrained because the object never exists.
export class Terminal {
  [member: string]: any
  constructor(..._args: unknown[]) {
    throw new Error(ABSENT)
  }
}

export class FitAddon {
  [member: string]: any
  constructor(..._args: unknown[]) {
    throw new Error(ABSENT)
  }
}

// Type-only imports in their source. Declared so `import type { ... }`
// resolves; they carry no runtime cost.
export interface ITerminalAddon {
  activate(terminal: unknown): void
  dispose(): void
}

export interface ITerminalCore {
  [key: string]: any
}

export interface IBufferRange {
  start: { x: number; y: number }
  end: { x: number; y: number }
}
