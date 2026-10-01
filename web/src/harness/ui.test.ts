import { createRoot, createSignal } from "solid-js"
import { describe, expect, it, vi } from "vitest"

// One entry per request, so a test settles exactly the read it started.
const pending: Array<{ resolve: (value: unknown) => void; reject: (error: unknown) => void }> = []
vi.mock("./engine", () => ({
  harness: () => new Promise((resolve, reject) => pending.push({ resolve, reject })),
}))

const { useHarnessRead } = await import("./ui")

const tick = () => new Promise((done) => setTimeout(done, 0))

describe("useHarnessRead reports its state live", () => {
  it("loading goes true while a read is out and false when it answers", async () => {
    await createRoot(async (dispose) => {
      const read = useHarnessRead<{ ok: boolean }>(() => "/x")
      await tick()
      expect(read.data.loading).toBe(true)
      pending.shift()!.resolve({ ok: true })
      await tick()
      // Frozen at creation, this stayed true for ever - the stuck "Checking".
      expect(read.data.loading).toBe(false)
      expect(read.data()).toEqual({ ok: true })
      dispose()
    })
  })

  it("an error that arrives later is visible", async () => {
    await createRoot(async (dispose) => {
      const read = useHarnessRead(() => "/y")
      await tick()
      expect(read.data.error).toBeUndefined()
      pending.shift()!.reject(new Error("No model is connected."))
      await tick()
      expect((read.data.error as Error).message).toBe("No model is connected.")
      dispose()
    })
  })

  it("answered is false until the current path settles, and again after the path changes", async () => {
    await createRoot(async (dispose) => {
      const [path, setPath] = createSignal("/a")
      const read = useHarnessRead<{ n: number }>(path)
      await tick()
      // Before the answer, loading and answered must both say "not yet":
      // the empty-state line used to show here.
      expect(read.data.answered).toBe(false)
      pending.shift()!.resolve({ n: 1 })
      await tick()
      expect(read.data.answered).toBe(true)
      setPath("/b")
      await tick()
      expect(read.data.answered).toBe(false)
      pending.shift()!.reject(new Error("gone"))
      await tick()
      // An error is an answer: the pane shows it instead of "Reading…".
      expect(read.data.answered).toBe(true)
      dispose()
    })
  })
})
