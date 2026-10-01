import { describe, expect, it } from "vitest"
import { engineSessionId, resolveThreadSession, sessionForThread, type SessionLike } from "./thread-session"

type Row = SessionLike & { parentID?: string }

const session = (id: string, threadID: number | string | undefined, parentID?: string): Row => ({
  id,
  parentID,
  metadata: threadID === undefined ? {} : { harness: { threadID, projectID: 1 } },
})

describe("finding a thread's session in a list", () => {
  it("matches on metadata.harness.threadID, never on the id", () => {
    // A client-minted id that looks like another thread's engine id.
    const rows = [session("ses_7", 9), session("ses_01JABC", 7)]
    expect(sessionForThread(rows, 7)?.id).toBe("ses_01JABC")
    expect(sessionForThread(rows, 9)?.id).toBe("ses_7")
    expect(sessionForThread(rows, 3)).toBeUndefined()
  })

  it("reads a string thread id the way the panes do", () => {
    expect(sessionForThread([session("ses_x", "12")], 12)?.id).toBe("ses_x")
  })

  it("ignores sessions with no harness metadata", () => {
    expect(sessionForThread([session("ses_12", undefined)], 12)).toBeUndefined()
  })
})

describe("resolving a thread to a session", () => {
  const never = () => Promise.reject(new Error("should not be asked"))

  it("takes what the window already holds, asking nobody", async () => {
    const found = await resolveThreadSession(7, {
      known: () => [session("ses_a", 7)],
      children: never,
      get: never,
    })
    expect(found?.id).toBe("ses_a")
  })

  it("then the current session's children", async () => {
    const found = await resolveThreadSession(7, {
      known: () => [session("ses_parent", 3)],
      children: async () => [session("ses_8", 8, "ses_parent"), session("ses_7", 7, "ses_parent")],
      get: never,
    })
    expect(found?.id).toBe("ses_7")
    expect(found?.parentID).toBe("ses_parent")
  })

  it("then asks for the engine-made id, and accepts it only for the same thread", async () => {
    const asked: string[] = []
    const found = await resolveThreadSession(7, {
      known: () => [],
      children: async () => [],
      get: async (id) => {
        asked.push(id)
        return session("ses_client_minted", 7)
      },
    })
    expect(asked).toEqual([engineSessionId(7)])
    expect(found?.id).toBe("ses_client_minted")
  })

  it("refuses an answer that names a different thread", async () => {
    const found = await resolveThreadSession(7, {
      known: () => [],
      get: async () => session("ses_7", 9),
    })
    expect(found).toBeUndefined()
  })

  it("survives a failed list and a failed get, and says it found nothing", async () => {
    const found = await resolveThreadSession(7, {
      known: () => [],
      children: () => Promise.reject(new Error("offline")),
      get: () => Promise.reject(new Error("404")),
    })
    expect(found).toBeUndefined()
  })

  it("still asks directly when the children list fails", async () => {
    const found = await resolveThreadSession(7, {
      known: () => [],
      children: () => Promise.reject(new Error("offline")),
      get: async () => session("ses_7", 7),
    })
    expect(found?.id).toBe("ses_7")
  })
})
