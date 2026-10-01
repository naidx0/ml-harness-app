# ML Harness — frontend

The chat surface and the three-column shell around it. React + TypeScript + Vite, styled
entirely by the CSS custom properties in `docs/DESIGN_SYSTEM.md` §13.

**The chat box works.** You connect your own model, type into the composer, and the reply
streams into the transcript as the engine commits it. Tool calls render as one-line rows
that expand into a table. Every tool is also a button. Nothing on screen is a fixture.

---

## Running it

The engine must be running first — the front door reads real hardware from it, and every
other surface reads the event log.

```bash
# terminal 1, from the repository root
python -m uvicorn app.main:app --host 127.0.0.1 --port 8078

# terminal 2
cd frontend
npm install      # first time only
npm run dev      # → http://localhost:5199
```

**Port 5199, pinned, with `strictPort`.** Not a preference. A stale process on Vite's
default 5173 was serving a *different* app in this project and a screenshot taken against
it was reported as evidence for this one. Vite's normal behaviour makes that easy: if the
port is taken it silently moves to the next free one, so "I ran the dev server" and "I
looked at the dev server I ran" stop being the same sentence. With `strictPort`, a second
instance fails loudly instead of landing somewhere nobody checked.

`npm run build` type-checks and builds. `npm run lint` runs oxlint.

If the engine is not running, the app still loads: the hardware card renders its
`detection failed` state with the reason, and no number appears anywhere. It does not
substitute a default — `docs/DESIGN_SYSTEM.md` §9.13, "a failed detection never renders
as a measurement."

### How the browser reaches the engine, and why it needs a proxy

`app/security.py allowed_origins()` permits exactly two origins, both on the **engine's**
port. A dev server is not one of them. Verified:

```
$ curl -i -H "Origin: http://localhost:5199" http://127.0.0.1:8078/local_specs
HTTP/1.1 403 Forbidden
{"detail":"cross-site request refused"}
```

So every engine call goes to `/engine/*` on the dev server's own origin and is proxied
(`vite.config.ts`). The proxy strips `Origin`, which `origin_is_allowed()` explicitly
treats as "the caller is not a browser — a curl, the launcher, a test". Authentication is
still the bearer token. Nothing is bypassed: no page can reach the engine without going
through a server this user started.

The token comes from `engine.json` at the repository root, which the engine writes at
startup. A browser cannot read a file, so a dev-only Vite middleware serves it at
`/__engine/session`. The token never enters the URL bar or browser history.

---

## The loop, and the one rule about its order

```
1. POST /api/threads                    only when there is no thread yet
2. GET  /api/events?scope=thread:N      opened, and kept open
3. POST /api/threads/N/messages         writes a message.created event
4. POST /api/threads/N/turn             blocks for the whole turn
```

**Step 4 is not where the reply comes from.** It returns the ids of the rows the turn
wrote, after the turn is over. Every token arrives on the stream from step 2, because
`app/conductor.py` commits each delta before it yields it. That separation is the entire
reason a closed laptop costs nothing.

It also means there is no race to defend against. The stream is opened with `since=0` and
replays the thread from the beginning, and events are kept in a `Map` keyed by `events.id`,
so a replay is idempotent by construction rather than by timing.

### The transcript is folded out of the event log, and only out of the event log

`lib/transcript.ts` is a pure function from an ordered event list to rows. It does not read
`GET /api/threads/{id}`'s `messages`, because it does not need to: `app/conductor.py`
writes the assistant's reply as `"".join(text_parts)` — the exact concatenation of the
`chat.delta` payloads it already committed. Replaying from 0 reconstructs the assistant
turns character for character, and there is no second source that could disagree.

### The stream reader is `fetch`, not `EventSource`

The previous version used `EventSource` and argued that a reconnect loop would defeat the
reason SSE was chosen. Three facts about the engine that shipped make that wrong, and each
alone would be enough:

1. **Every `/api/*` path requires `Authorization: Bearer …`.** `EventSource` has no API for
   request headers. In dev the Vite proxy fills it in, so the gap is invisible; packaged,
   there is no proxy and the stream is a 401. A fetch reader sets the header itself, and
   the gap closes rather than moving.
2. **The engine ends the response on purpose, roughly every 25 seconds**
   (`event_stream(timeout: float = 25.0)`), and immediately on `stream.end`. Reconnecting
   is the ordinary path through this code, and a local model answering a real question
   takes longer than one connection lasts.
3. **`EventSource` only delivers frames you subscribed to by name.** The old reader listed
   fourteen fixed kinds. `app/tools/training.py` emits `train.<kind>` where the kind comes
   from the recipe's own structured output, so every one of those frames would have been
   dropped in silence.

`Last-Event-ID` goes on the header, which the engine prefers over the `since` query
parameter; `since` carries the same number so a proxy that strips the header cannot lose
the client's place. Verified against the running engine:

```
$ curl -H "Last-Event-ID: 180" ".../api/events?scope=thread:1&since=0&follow=false"
id: 181
id: 182
id: 183
id: 184
id: 185
```

The header wins over `since=0`, and the replay is exact.

---

## What is real

Everything on screen, with three exceptions listed in the next section.

| Surface | Source |
|---|---|
| The transcript | `GET /api/events`, folded by `lib/transcript.ts` |
| Tool rows and their results | `tool.call` / `tool.result` events |
| The turn line — which model, local or remote, whether it can call tools, seconds | `turn.started` and `stream.end` |
| The rail | `GET /api/threads` |
| The controls panel | `GET /api/tools`, the registry's own declaration |
| The connection surface | `GET /api/providers`, `/api/provider_presets`, `POST /api/providers/{id}/probe` |
| The local model list in that surface | the `list_local_models` tool, reading GGUF metadata from the Ollama daemon |
| The hardware card, the Machine pane, the composer's hardware chip | `GET /local_specs` |
| Every `MEASURED` tag | the engine's own `provenance` map |

Nothing on those surfaces is typed into this repository.

### The API key

Typed into the connection dialog, sent once to `POST /api/providers`, and put in the OS
keychain by the engine. It is not held in React state after the request, not in
`localStorage`, not in a URL, not in an event payload, and it never comes back on any
response — `_provider_public` returns `has_key`, a boolean. A 503 from that route means the
row was saved and the key was **not**, and the engine says so in words this surface prints
verbatim.

### Tool results are never raw JSON

A result expands into a table (`components/ResultView.tsx`). Keys are set in mono exactly
as the engine wrote them and are deliberately **not** prettified into English: `params_b`,
`on_disk_gb` and `max_seq_len` carry units in their names, and a renderer that guessed at
"On disk (GB)" would eventually guess a unit wrong. A `null` renders as *not reported*,
never as `0` or an empty cell.

### The three densities do different things — §9.21

| Level | Tool row |
|---|---|
| Summary | label and outcome only; the arguments are mechanics and are dropped |
| Normal | label, arguments preview, outcome |
| Verbose | expanded, with the result table and what the tool reads and writes |

A row expanded by hand stays expanded until the density itself changes — §9.21's `mixed`
state, "because one expanded turn is not a mode".

---

## Still a placeholder, and marked as such on screen

| Thing | Why | How it is marked |
|---|---|---|
| The composer's Autonomy selector | no engine route has an autonomy field | its profile line reads `not wired yet` |
| The "what this machine can run" sentence | `app/feasibility.py` exists; no HTTP route serves it | an `--info` strip saying exactly that, and **no** capability sentence |
| Four Machine-pane rows | driver/CUDA, compute capability, accelerator build, and whether the build sees the GPU have no field in `/local_specs` | rows reading `not detected yet`, never dropped |
| The `UNTESTED` provenance tag | the engine returns `untested_on_this_platform`; §9.3 defines no tag for it | dashed underline and a tooltip naming the gap |
| The Evidence pane's gate ledger | no diagnosis has been run through a route that persists one | five rows, all `NOT CHECKED` |

`GET /api/runs` exists and is deliberately **not** used: it returns the legacy run-tracker
shape — no `kind`, no lifecycle `status` from the nine-value set, no `archived_at`. A run
row built from it would be a real row wearing a design it cannot satisfy. The rail lists
threads instead, which are real. `src/lib/runState.ts` keeps §2.5's vocabulary ready for
the day that route grows the §5 shape.

---

## Known gaps and disagreements, found while building this

Reported rather than worked around.

1. **A tool run from the Controls panel is not in the transcript.**
   `POST /api/tools/{name}` calls the registry and returns; it appends no event. So a
   result from a button is not durable, and the panel says so above the list and again next
   to every result. A tool the *model* calls during a turn is in the transcript. Closing
   this properly is an engine change, not a frontend one.
2. **`threads` has no `density` column.** §9.21 says density is "per thread and persisted,
   because it is a property of the conversation". The shipped table is
   `id · title · created_at · updated_at`, so density is persisted in `localStorage` keyed
   by thread id. That is per thread and it survives a reload, but it does not travel with
   the thread.
3. **`docs/DESIGN_DIRECTIVES.md` overrules §9.1 on bubbles, and this build has not made
   that change.** The directive records that Codex bubbles the *user* side and leaves the
   assistant full-width, and that the design system is wrong. This step wired the chat box;
   the messages still render as §9.1's full-width rows with a 2px role marker. Mixing a
   design change into a wiring step would make it impossible to tell which one broke
   something. It is the next obvious piece of work.
4. **`docs/DESIGN_DIRECTIVES.md` §5 asks for a round send button**; §9.2 specifies `28px`
   square at `--r-6`, and that is what is here. Same reason as gap 3.
5. **The event vocabulary in `docs/ARCHITECTURE.md` §5 is not what shipped.** It predicts
   `tool.start`, `tool.end`, `run.status`, `chip.offered`, `mode.guided`, `turn.error`.
   `app/conductor.py` emits `turn.started`, `chat.delta`, `chat.error`, `tool.call`,
   `tool.result`, `conductor.notice`, `stream.end`; `app/main.py` emits `message.created`;
   `app/tools/training.py` emits `train.started`, `train.log` and `train.<kind>` where the
   kind is open-ended. `src/lib/engine/types.ts` types what shipped and says so.
6. **`docs/ARCHITECTURE.md` §5's `threads` has `project_id`, `density` and `archived_at`.**
   The shipped table has none of them, and there is no `projects` table reachable over
   HTTP. The rail therefore has no project switcher.
7. **The endpoint is `/local_specs`, not `/api/local_specs`.** `docs/ROADMAP.md` step 1.22
   says the latter. `app/main.py` mounts `hwdetect.router` at the app root.
8. **Three provenance vocabularies.** `app/hwdetect.py` returns three values, §9.3 defines
   four tags, `app/feasibility.py` has five, PRODUCT_SPEC §3.1 lists four different words.
   `untested_on_this_platform` has no tag in the design system at all.
9. **The composer's selector row.** §9.2's sketch puts it below the textarea; §9.2's prose
   and PRODUCT_SPEC §3.2 both say above. The sketch is followed.
10. **Three starter prompts or four.** §9.11 says one to three; PRODUCT_SPEC §3.1 gives
    four and argues the fourth is load-bearing. Four are rendered.
11. **§12.1a versus §9.1.** §12.1a allows the chrome at most one accent element; §9.1 makes
    the harness role marker `--accent` on every harness message. A transcript with a
    harness reply and an enabled send button carries two.
12. **The run row cannot hold everything §12.3 asks of it at §4.1's default rail width**,
    and **compact rows cannot carry the cost signal at all**. Both measured in the previous
    pass; both still true, and both now dormant because the rail lists threads.
13. **No Markdown library.** A connected model writes Markdown whether or not we asked, so
    `lib/markdown.ts` renders a deliberate subset — paragraphs, headings, lists, fenced
    code, `**strong**`, `` `code` `` — and leaves everything else as literal text. A
    library would be the obvious answer and `AGENTS.md` says a new dependency gets its own
    step. Nothing here produces HTML: the renderer builds React elements, and there is no
    `dangerouslySetInnerHTML` anywhere in this frontend.

---

## Layout

```
src/
  App.tsx                    the three zones, the dialogs, resize, theme/density state
  main.tsx
  styles/
    tokens.css               §13, transcribed. Light on :root, dark twice.
    base.css                 §13 root rules, §8 focus/selection/scroll, §10 reduced motion
    shell.css                the three-column frame and its components
    chat.css                 the chat surface: tool rows, result tables, dialogs, controls
  lib/
    engine/config.ts         engine.json discovery, and why the proxy exists
    engine/client.ts         fetch wrapper, every route, the engine's own error detail
    engine/events.ts         the SSE reader: fetch, Last-Event-ID, reconnect, interrupt
    engine/types.ts          transcribed from the code that shipped, not from a document
    transcript.ts            events → rows. Pure. The only place the transcript is built.
    markdown.ts              the subset a model's reply uses. Returns elements, not HTML.
    useChat.ts               one turn: create, post, run, follow
    useProviders.ts          connect, activate, probe. The key never lands here.
    useTools.ts              GET /api/tools, POST /api/tools/{name}
    useThreads.ts            the rail's contents, and day bucketing that respects UTC
    runState.ts              (status, kind) → label · role · dot · spending — §2.5
    format.ts                §3.6 number rules, §9.3 provenance mapping
    useLocalSpecs.ts         GET /local_specs
  components/
    Transcript.tsx           §9.1 messages, tool rows, turn lines, §9.21 density
    ResultView.tsx           a tool result as a table. Never raw JSON.
    ConnectModel.tsx         the connection surface
    Controls.tsx             every tool as a button, including approvals
    Icon.tsx                 one stroke weight, currentColor, no hue — DIRECTIVES §4
    Rail.tsx                 §9.6 rows, day groups — real threads
    EmptyState.tsx           §9.11 + PRODUCT_SPEC §3.1 — the front door
    Composer.tsx             §9.2, and the connection banner's four true states
    PaneStack.tsx            §9.12 container + §9.13/§9.15 and the rest
    Chrome.tsx               theme, row size, segmented control
    primitives.tsx           dot, verdict badge, gate badge, provenance tag, chips
  data/sample.ts             the five gates and the four starter prompts — specified
                             content, not fixtures
```

Screenshots from the verification pass are in `.fleet-verify-shell/` (gitignored).
