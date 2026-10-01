import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("./engine", () => ({ harness: () => new Promise(() => {}) }))

const { Row, rowTitle } = await import("./ui")

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

function mount(view: () => any) {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(view, host)
  return host
}

describe("Row shows a truncated value on hover", () => {
  it("a plain-text value is its own title", () => {
    const host = mount(() => <Row label="Model">qwen2.5-coder-32b-instruct-q4_k_m</Row>)
    const value = host.querySelector(".truncate")!
    expect(value.getAttribute("title")).toBe("qwen2.5-coder-32b-instruct-q4_k_m")
  })

  it("mixed text and numbers join into one title", () => {
    const n = 42
    const host = mount(() => <Row label="Run">#{n}</Row>)
    expect(host.querySelector(".truncate")!.getAttribute("title")).toBe("#42")
  })

  it("an explicit title wins, and an element value is built once", () => {
    const host = mount(() => (
      <Row label="File" title="C:/data/rows.jsonl">
        <span data-testid="v">rows.jsonl</span>
      </Row>
    ))
    expect(host.querySelector(".truncate")!.getAttribute("title")).toBe("C:/data/rows.jsonl")
    expect(host.querySelectorAll('[data-testid="v"]').length).toBe(1)
  })

  it("an element value with no title gets no title", () => {
    expect(rowTitle(undefined, document.createElement("span"))).toBeUndefined()
  })
})
