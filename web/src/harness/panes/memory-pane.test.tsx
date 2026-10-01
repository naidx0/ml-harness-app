import { createSignal } from "solid-js"
import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"

/**
 * Memory is saved as a whole-text PUT. A box a person could type into before
 * the stored text arrived would save their few words over everything the
 * model and they had stored - so until /api/memory answers, the boxes and
 * Save are shut. And a project draft survives a switch to another thread of
 * the SAME project; it is dropped only for a different project.
 */

const pending = new Map<string, { resolve: (value: unknown) => void; reject: (error: unknown) => void }>()
vi.mock("../engine", () => ({
  harness: (path: string) => new Promise((resolve, reject) => pending.set(path, { resolve, reject })),
}))

const { default: MemoryPane } = await import("./memory")

const tick = () => new Promise((done) => setTimeout(done, 0))

async function answer(path: string, value: unknown, fail = false) {
  await tick()
  const request = pending.get(path)
  if (!request) throw new Error(`no read of ${path} is out; out: ${[...pending.keys()].join(", ")}`)
  pending.delete(path)
  if (fail) request.reject(value)
  else request.resolve(value)
  await tick()
  await tick()
}

const block = (text: string) => ({ entries: [], text, used: text.length, limit: 2200 })
const memory = (project: string, user: string) => ({ project: block(project), user: block(user) })
const thread = (id: number, project_id: number | null) => ({ thread: { id, project_id } })

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  pending.clear()
  document.body.innerHTML = ""
})

function mount(first: number | undefined) {
  const [threadId, setThreadId] = createSignal<number | undefined>(first)
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <MemoryPane threadId={threadId()} />, host)
  const box = (label: string) => host.querySelector(`textarea[aria-label="${label}"]`) as HTMLTextAreaElement
  const save = () =>
    [...host.querySelectorAll("button")].filter((button) => button.textContent === "Save") as HTMLButtonElement[]
  const type = (label: string, text: string) => {
    const element = box(label)
    element.value = text
    element.dispatchEvent(new InputEvent("input", { bubbles: true }))
  }
  return { host, setThreadId, box, save, type }
}

describe("Memory before its read answers", () => {
  it("shuts both boxes and Save, says Reading…, and opens them when the text arrives", async () => {
    const pane = mount(undefined)
    await tick()
    expect(pane.box("About you").disabled).toBe(true)
    expect(pane.box("About you").placeholder).toBe("Reading…")
    expect(pane.save().every((button) => button.disabled)).toBe(true)

    await answer("/api/memory", memory("", "Prefers short answers."))
    expect(pane.box("About you").disabled).toBe(false)
    expect(pane.box("About you").value).toBe("Prefers short answers.")
  })

  it("stays shut after a failed read, so nothing can be saved over the store", async () => {
    const pane = mount(undefined)
    await answer("/api/memory", new Error("database is locked"), true)
    expect(pane.box("About you").disabled).toBe(true)
    expect(pane.box("About you").placeholder).not.toBe("Reading…")
    expect(pane.save().every((button) => button.disabled)).toBe(true)
  })
})

describe("a project draft across a thread switch", () => {
  async function withDraft() {
    const pane = mount(1)
    await answer("/api/threads/1", thread(1, 5))
    await answer("/api/memory?project_id=5", memory("Data lives in C:/data.", ""))
    pane.type("This project knows", "Data lives in C:/data. § Ruled out: LoRA r=64 (declared).")
    await tick()
    expect(pane.box("This project knows").value).toContain("Ruled out")
    return pane
  }

  it("is kept when the next thread is in the same project", async () => {
    const pane = await withDraft()
    pane.setThreadId(2)
    await answer("/api/threads/2", thread(2, 5))
    await answer("/api/memory?project_id=5", memory("Data lives in C:/data.", ""))
    await tick()
    expect(pane.box("This project knows").value).toContain("Ruled out")
  })

  it("is dropped when the next thread is in another project", async () => {
    const pane = await withDraft()
    pane.setThreadId(3)
    await answer("/api/threads/3", thread(3, 7))
    await answer("/api/memory?project_id=7", memory("Project seven.", ""))
    expect(pane.box("This project knows").value).toBe("Project seven.")
  })
})
