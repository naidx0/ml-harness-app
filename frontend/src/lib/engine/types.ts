/**
 * Types for the engine API.
 *
 * Every type here is transcribed from a document, and each one says which:
 *   - docs/ARCHITECTURE.md §4.2  — the API and event stream
 *   - docs/ARCHITECTURE.md §5    — the data model (the tables these mirror)
 *   - docs/DESIGN_SYSTEM.md §2.5 — the run-state vocabulary, which is canonical
 *   - app/hwdetect.py            — the ONE endpoint that exists today
 *
 * Endpoints that do not exist yet are marked `@unimplemented` on the client
 * function that would call them. Nothing here fabricates a response shape for
 * an endpoint that has not been written: where the document does not state a
 * field, the field is absent rather than guessed.
 */

/* ── Run lifecycle — docs/DESIGN_SYSTEM.md §2.5.1 / §2.5.2 ─────────────────
   Nine storage states, one column. These are the values of `runs.status`.
   They are lowercase identifiers and they never appear on screen. */
export type RunStatus =
  | 'queued'
  | 'preflight'
  | 'running'
  | 'waiting_input'
  | 'waiting_approval'
  | 'stalled'
  | 'done'
  | 'failed'
  | 'cancelled';

/** `runs.kind` — docs/ARCHITECTURE.md §5. Load-bearing: the label the user
 *  reads is derived from `status` and `kind` together. */
export type RunKind = 'diagnose' | 'prepare' | 'train' | 'eval' | 'convert';

/** The six colour roles of docs/DESIGN_SYSTEM.md §2.5.3. Six roles, six
 *  distinct resolved values, no duplicate pairs. */
export type StateRole =
  | 'st-neutral'
  | 'st-active'
  | 'st-attention'
  | 'st-stalled'
  | 'st-failed'
  | 'st-done';

/** Feasibility verdicts — docs/DESIGN_SYSTEM.md §2.4, app/feasibility.py. */
export type Verdict = 'FITS' | 'SPILLS' | 'WONT_FIT' | 'UNKNOWN';

/** Gate ledger statuses — docs/DESIGN_SYSTEM.md §9.15. Three, and no fourth.
 *  NOT_CHECKED is not a softer NOT_MET. */
export type GateStatus = 'PASSED' | 'NOT_MET' | 'NOT_CHECKED';

/* ── Provenance ────────────────────────────────────────────────────────────
   THREE VOCABULARIES EXIST IN THIS REPOSITORY AND THEY DO NOT AGREE. Recorded
   here rather than silently reconciled:

     app/hwdetect.py    measured · defaulted · untested_on_this_platform
     app/feasibility.py measured · inferred · declared · defaulted ·
                        untested_on_this_platform
     DESIGN_SYSTEM §9.3 MEASURED · INFERRED · DECLARED · DEFAULT
     PRODUCT_SPEC §3.1  measured · computed · assumed · untested on this platform

   `untested_on_this_platform` is a real wire value with NO tag in
   DESIGN_SYSTEM §9.3. It renders as a marked placeholder — see
   components/ProvenanceTag.tsx. */
export type WireProvenance =
  | 'measured'
  | 'inferred'
  | 'declared'
  | 'defaulted'
  | 'untested_on_this_platform';

/** The four tags DESIGN_SYSTEM §9.3 defines, plus the placeholder for the
 *  wire value that document has no tag for. */
export type DisplayTag =
  | 'MEASURED'
  | 'INFERRED'
  | 'DECLARED'
  | 'DEFAULT'
  | 'UNTESTED';

/* ── GET /local_specs ──────────────────────────────────────────────────────
   The one engine endpoint the frontend can reach today. Shape read from
   app/hwdetect.py `local_specs()` and its REQUIRED_FIELDS, not invented.

   NOTE: it is mounted at `/local_specs`, NOT `/api/local_specs` as
   docs/ROADMAP.md step 1.22 states. app/main.py mounts `hwdetect.router` at
   the app root. */
export interface LocalSpecs {
  /** Installed RAM in GiB, or null when the platform could not be read.
   *  Never a guess — app/hwdetect.py returns null rather than defaulting. */
  ram_gb: number | null;
  /** Free space on the model-cache volume in GiB. A SEPARATE reading from
   *  ram_gb; they used to be the same call, which is the defect
   *  DESIGN_SYSTEM §9.11 calls out by name. */
  disk_free_gb: number | null;
  os: string | null;
  gpu_name: string | null;
  vram_gb: number | null;
  /** Off the same nvidia-smi call as the name and the memory. Null when this
   *  machine's nvidia-smi does not report them, which older ones do not. */
  driver_version?: string | null;
  compute_capability?: string | null;
  provenance: Partial<Record<LocalSpecsField, WireProvenance>>;
  /** What was actually run to obtain each field, e.g.
   *  "nvidia-smi --query-gpu=name,memory.total". */
  sources: Partial<Record<LocalSpecsField, string>>;
  warnings: string[];
}

export type LocalSpecsField =
  | 'ram_gb'
  | 'disk_free_gb'
  | 'os'
  | 'gpu_name'
  | 'vram_gb'
  | 'driver_version'
  | 'compute_capability';

/** app/hwdetect.py REQUIRED_FIELDS, in the order the Machine pane prints
 *  them. DESIGN_SYSTEM §9.13 specifies more rows than the endpoint returns
 *  (driver/CUDA runtime, compute capability, accelerator build and whether it
 *  can see the GPU); those rows render as "not detected yet" rather than
 *  being dropped, because a missing row is invisible and an empty one is not. */
export const LOCAL_SPECS_FIELDS: readonly LocalSpecsField[] = [
  'gpu_name',
  'vram_gb',
  'ram_gb',
  'disk_free_gb',
  'os',
] as const;

/* ── The event log — app/events.py, app/conductor.py ───────────────────────

   READ OFF THE CODE THAT SHIPPED, NOT OFF A DOCUMENT. The vocabulary
   docs/ARCHITECTURE.md §5 predicted (`tool.start`, `tool.end`, `run.status`,
   `chip.offered`, `mode.guided`, `turn.error`) is not what `app/conductor.py`
   emits. The kinds below are every literal passed to `events.append()` in
   `app/`, found by grep:

     app/conductor.py  turn.started · chat.delta · chat.error · tool.call ·
                       tool.result · conductor.notice · stream.end
     app/main.py       message.created
     app/tools/training.py  train.started · train.log · train.<kind>, where
                       <kind> comes from the recipe's own structured output
                       and is therefore OPEN — `train.progress` and
                       `train.finished` are the two it names, and a recipe can
                       emit others.

   Because `train.*` is open, `EventKind` is not a closed union and the stream
   reader does not subscribe per kind. That is a real defect the old
   EventSource reader had: it listened for fourteen fixed names, so every
   `train.*` frame would have been dropped in silence. */

export type KnownEventKind =
  | 'message.created'
  | 'turn.started'
  | 'chat.delta'
  | 'chat.error'
  | 'conductor.notice'
  | 'tool.call'
  | 'tool.result'
  | 'stream.end'
  | 'train.started'
  | 'train.log';

/** A frame's `event:` line. Known kinds are typed; `train.*` is open. */
export type EventKind = KnownEventKind | (string & {});

/** Emitted when a turn is complete. `app/events.py` END_KIND. */
export const END_KIND = 'stream.end';

/** One frame off `GET /api/events`. `id` is `events.id` — the SSE event id,
 *  and the thing `Last-Event-ID` replays from. */
export interface EngineEvent<P = unknown> {
  id: number;
  kind: EventKind;
  payload: P;
}

/* Payload shapes, each transcribed from the `events.append()` call that
   writes it. A field this client reads is listed; nothing is invented. */

/** `app/main.py post_message_ep`. The role is always `user` — the engine
 *  refuses to take it from the request body. */
export interface MessageCreatedPayload {
  id: number;
  role: 'user';
  content: string;
}

/** `app/conductor.py run_turn`. Which model answered, recorded in the
 *  transcript because the transcript is the artifact. */
export interface TurnStartedPayload {
  provider: string;
  model: string;
  adapter: string;
  locality: 'local' | 'remote';
  tool_calling: ToolCallingState;
  instruction_set: string;
}

export interface ChatDeltaPayload {
  text: string;
}

export interface ChatErrorPayload {
  detail: string;
}

/** `app/conductor.py _unassisted_preamble`. Said once when the connected model
 *  cannot call tools. */
export interface ConductorNoticePayload {
  text: string;
  reason: string;
}

/**
 * One sentence of the reply that `reads_as_a_verdict` read as settling the
 * training decision, and what it read it as.
 *
 * IT IS A READING AND NOT A RECORD, which is the difference this payload is
 * built to keep visible. `verdict` on the row is what the harness's parser
 * concluded the sentence meant; the sentence is what the model actually wrote.
 * `app/conductor.py` puts that reader's live error rate in writing — it was
 * wrong in three of three live catches — so the interface quotes the sentence
 * beside the reading rather than asserting the reading on its own.
 */
export interface SettledSentence {
  /** `TRAIN`, `NO_TRAIN` or `BLOCKED` — the parser's conclusion. */
  verdict: string;
  /** What the model wrote, verbatim. */
  sentence: string;
}

/** The tool that would move the first unmet gate, and the fact it settles.
 *  Derived by `app/tools/evidence.py resolves()` from the registry's own
 *  `measures=` declarations — there is no list of tools anywhere in this
 *  client and there must never be one. */
export interface ConductorVerdictNextStep {
  tool: string;
  fact: string;
}

/**
 * `app/conductor.py verdict_annotation`. The engine's own verdict, emitted
 * BESIDE the reply that settled the training decision rather than instead of
 * it.
 *
 * A NEW KIND AND NOT A `conductor.notice`, and the engine says why: "a notice
 * is the harness saying something happened to the reply, and this is the
 * harness's own answer standing next to the model's." Folding them into one
 * row would lose the difference between *we stopped this* and *here is what we
 * computed*.
 *
 * THE TWO HALVES ARE DIFFERENT KINDS OF THING and the renderer may never mix
 * them. `say` is what the ENGINE said, walking this thread's ledger. `sentences`
 * is what the REPLY said, as the harness's own reader understood it. The whole
 * of this event is that a person can see both and tell them apart.
 */
export interface ConductorVerdictPayload {
  /** The whole annotation as one paragraph — the engine's fallback rendering
   *  for a surface with no card. Not drawn here: this client has the fields. */
  text: string;
  /** `NO_TRAIN`, `BLOCKED`, `TRAIN` — or null when the walk could not run. */
  verdict: string | null;
  /** The engine's own identifier for the finding, e.g.
   *  `BLOCKED__DEFINE_SUCCESS_FIRST`. Findable in `docs/diagnosis_engine.yaml`,
   *  which is what makes the card checkable rather than a retelling. */
  outcome: string | null;
  /** The engine's sentence. Shown verbatim or not at all. */
  say: string | null;
  /** `_gate_line`'s summary — "gates 3 of 5 passed; first unmet G3_…", or the
   *  sentence saying no gate was reached. Never assembled here: a gate ledger
   *  this surface counted itself would be a second copy of the guarantee. */
  gates: string | null;
  next_steps: ConductorVerdictNextStep[];
  /** False when the walk could not be computed for this thread at all. */
  computed: boolean;
  /** `app/diagnosis.py`. The card's authority, printed rather than implied. */
  decided_by: string;
  /** What the REPLY settled on, as the harness's reader read it. */
  asserted: string | null;
  /** Whether every settling sentence in the reply matched the engine. Sets the
   *  card's TONE and never whether it is drawn — a card that appeared only on
   *  disagreement would BE the verdict, and its absence would be a claim we
   *  never checked. */
  agrees: boolean;
  sentences: SettledSentence[];
}

export interface ToolCallPayload {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  /** `"harness"` when the harness ran the tool itself because the model could
   *  not. Absent when the model asked for it. */
  driven_by?: string;
}

export interface ToolResultPayload {
  id: string;
  name: string;
  /** False when the tool raised OR when it ran and reported `ok: false`. */
  ok: boolean;
  result: unknown;
  driven_by?: string;
}

/** `app/conductor.py`. `seconds` is measured — `time.monotonic()` across the
 *  turn — so it may be displayed. */
export interface StreamEndPayload {
  seconds: number;
}

/** Scope strings accepted by `GET /api/events?scope=…` — `app/events.py`
 *  SCOPE_COLUMNS. */
export type EventScope = `project:${number}` | `run:${number}` | `thread:${number}`;

/* ── Projects — app/migrations/v003_projects.py, app/db.py ────────────────
   THE RAIL'S TOP LEVEL IS THIS TABLE. Codex has folders; a project is what we
   have instead, and the parity checklist calls that a relabel rather than a
   difference: "a project owns a data root, a sensitivity level and a hardware
   profile; a folder owns nothing".

   Transcribed from the migration's DDL, column for column, not from
   docs/ARCHITECTURE.md §5.1 — `harness_md_path` is nullable and unused until
   M2, and `archived_at` is one column beyond the roadmap's DDL, which the
   migration's own docstring records. */

export interface Project {
  id: number;
  name: string;
  root_path: string | null;
  harness_md_path: string | null;
  portal: 'consumer' | 'enterprise' | (string & {});
  created_at: string;
  /** A timestamp, not a boolean: "archived" and "archived on the 14th" are
   *  different facts. Archived projects are absent from `GET /api/projects`
   *  unless `include_archived` is set. */
  archived_at: string | null;
}

/* ── Threads and messages — app/events.py ─────────────────────────────────
   CORRECTED AGAINST THE SHIPPED SCHEMA. This block used to say the `threads`
   table "has no `project_id`, no `density` and no `archived_at`". Migration 4
   (`v004_threads_belong_to_a_project.py`) added two of the three, and
   `GET /api/threads` returns them today — verified against the running engine,
   not against a document. `density` is still absent and is still persisted in
   localStorage; that gap is real and stays reported in App.tsx. */

export interface Thread {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  /** WHOSE SUB-AGENT THIS IS, when it is one - the conversation that handed it
   *  a phase (`app/subagents.py`). Null for an ordinary thread, which is
   *  almost all of them. The rail nests a child under its parent so that the
   *  work sent out stays visibly attached to the work that sent it. */
  subagent_of?: number | null;
  subagent_phase?: string | null;
  /** `running`, `done`, `failed` or `stopped`. */
  subagent_state?: string | null;

  /** Nullable in the schema because SQLite cannot add a NOT NULL column with a
   *  REFERENCES clause to a populated table. Never null in practice:
   *  `events.create_thread` falls back to `db.default_project()`. The rail
   *  still handles null rather than assuming, because a nullable column that
   *  the UI assumes is filled is how a thread disappears from the tree. */
  project_id: number | null;
  /** Where the plan lives on disk when the project has a folder:
   *  `<root>/harness-plans/thread-<id>-plan.md`. On `GET /api/threads/{id}`
   *  only; the file is the source of truth (app/planfile.py). */
  plan_path?: string | null;
  archived_at: string | null;
  /** What this thread is FOR, in the person's own words — the conductor
   *  copies the first substantive message verbatim, and the person corrects
   *  it through POST /api/threads/{id}/goal. Null until either happens:
   *  "no goal yet" is a real state, never faked as an empty string. */
  goal?: string | null;
  /** The playbook journey those words keyword-matched, or null. */
  goal_journey?: string | null;
  /** Permission ladder: ask | measure | write | full. Default ask. */
  permission?: string;
  /** 1 when permission is write/full (legacy bit, derived from the ladder). */
  autonomous?: number;
  /** `plan` or `build`. A thread that predates the feature reads `build`,
   *  which is what it has always been doing; a NEW thread opens in `plan`.
   *  In `plan` the engine hands the model no tools at all - that is the
   *  whole mechanism, see `app/modes.py`. */
  mode?: string;
  /** The agreed steps, markdown. NOT the goal: `goal` is the person's words
   *  for what the thread is for, set once; a plan is rewritten every time
   *  planning iterates, and in `build` it is carried into every prompt. */
  plan?: string | null;
  /** CS9 — secondary checklist; may exist without mirroring `plan`. */
  todo?: string | null;
  /** CS9 — which list GoalBar/longrun work: `plan` or `todo`. */
  checklist_source?: 'plan' | 'todo' | string | null;
}

export interface Message {
  id: number;
  thread_id: number;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls_json: string | null;
  created_at: string;
}

/** `GET /api/threads/{id}`. */
export interface ThreadDetail {
  thread: Thread;
  messages: Message[];
}

/** `POST /api/threads/{id}/turn`. The tokens go to the stream; this returns
 *  the ids of the rows the turn wrote. */
export interface TurnReceipt {
  thread_id: number;
  events: number[];
  last_event_id: number;
}

/* ── Providers — app/providers/store.py ───────────────────────────────────
   THREE STATES, NOT A BOOLEAN. `unknown` is "we have not probed", which is a
   different fact from "we probed and the answer was no", and the product says
   different things in each. */

export type ToolCallingState = 'unknown' | 'yes' | 'no';

export type Adapter = 'openai-compatible' | 'ollama';

export interface Provider {
  id: number;
  name: string;
  base_url: string;
  model: string;
  adapter: Adapter | string;
  /** `local` or `remote`, decided by `app/providers.classify()` from the base
   *  URL. The egress guard reads it; unknown is `remote`. */
  kind: 'local' | 'remote';
  tool_calling: ToolCallingState;
  /** What the probe learned, in words, e.g. "reported by the Ollama server for
   *  this model". Shown verbatim rather than paraphrased. */
  capability_detail: string;
  ctx_len: number | null;
  ctx_len_provenance: WireProvenance;
  is_active: 0 | 1;
  created_at: string;
  /** Whether the OS keychain holds a key for this row. Never the key itself —
   *  `app/main.py _provider_public` computes this and the key never leaves the
   *  engine. */
  has_key: boolean;
  /** How hard the model thinks on this connection: `default` (nothing sent),
   *  `off`, `low`, `medium`, `high`. `app/providers/store.EFFORTS`. Ollama
   *  takes it as `think`, an OpenAI-compatible server as `reasoning_effort`. */
  effort: string;
}

/** `GET /api/provider_presets` — `app/providers.PRESETS`. */
export interface ProviderPreset {
  name: string;
  base_url: string;
  adapter: Adapter | string;
  default_model: string;
  needs_key: boolean;
}

export interface ProviderCreate {
  name: string;
  base_url: string;
  model: string;
  adapter: string;
  /** Sent once, to the engine, which puts it in the OS keychain. It is never
   *  held in React state after the request, never in localStorage, and never
   *  comes back on any response. */
  api_key?: string;
}

/**
 * `PATCH /api/providers/{id}` — an edit to a saved connection.
 *
 * ABSENT AND EMPTY ARE DIFFERENT FOR `api_key`, which is why this is its own
 * type rather than `Partial<ProviderCreate>`. The engine never returns a key,
 * so a settings form redrawing a connection has nothing to put back; if the
 * key were an ordinary optional field every rename would wipe it. Leaving the
 * property off means "leave whatever the keychain holds"; sending `''` means
 * "delete it"; sending a string replaces it. `app/main.py ProviderUpdate`
 * reads `model_fields_set` to tell the three apart.
 *
 * Changing `model`, `base_url` or `adapter` RESETS what the probe measured,
 * on the engine's side. A context length measured off one model is not a fact
 * about another, and invariant 3 forbids showing it as one.
 */
export interface ProviderUpdate {
  name?: string;
  base_url?: string;
  model?: string;
  adapter?: string;
  api_key?: string;
  effort?: string;
}

/**
 * `GET /api/keychain` — whether this machine has anywhere safe to put a key,
 * asked BEFORE one is typed rather than after the save fails.
 *
 * It carries no secret and cannot: every string on it is a constant in
 * `app/providers/secrets.py` — a backend name, the service label our entries
 * are filed under, and the environment-variable prefix.
 */
export interface Keychain {
  available: boolean;
  /** `windows-credential-manager`, `macos-keychain`, `secret-service`, or
   *  null when there is no store this process can write to. */
  backend: string | null;
  service: string;
  env_prefix: string;
  /** The engine's own sentence about it. Shown verbatim. */
  detail: string;
}

/* ── Tools as controls — app/tools/registry.py `as_control()` ──────────────
   ONE declaration, two callers: the model's tool call and the user's button.
   The fields below come out of the identical JSON Schema the model is given,
   so a parameter cannot exist for one caller and not the other. */

export interface ToolField {
  name: string;
  type: string;
  description: string;
  required: boolean;
  enum: string[] | null;
}

export interface ToolControl {
  name: string;
  label: string;
  group: string;
  /** The imperative, for a confirmation line: "start a training run on this
   *  machine". */
  verb: string;
  order: number;
  description: string;
  fields: ToolField[];
  reads: string[];
  writes: string[];
  /**
   * The ledger facts this tool may stamp MEASURED, checked at registration
   * against the fact ledger — `app/tools/registry.py` wall 5. Empty for every
   * tool that runs no instrument, which is most of them.
   *
   * It is what makes "which tool would settle this claim" derivable rather than
   * listed: `evidence.resolves()` searches these declarations, so a tool added
   * next year becomes the answer on the day it is registered.
   */
  measures: string[];
  needs_approval: boolean;
}

export interface ToolCatalogue {
  controls: ToolControl[];
  instruction_set: string;
}

/** `POST /api/tools/{name}`. */
export interface ToolRunResult {
  tool: string;
  result: unknown;
}

/**
 * `GET /api/studios` — the capability packs, read live off the registry.
 *
 * A studio IS a pack: the first dotted segment of a capability name a tool
 * declared with `provides=`. Nothing here is a second manifest, which is why
 * this type has no list of tool names in it — `pack_index` is derived by the
 * engine from the registry, so a tool that declares a capability under a new
 * namespace is a studio on the day it is added.
 */
export interface Studios {
  /** Pack name → the one line the engine says it is for. */
  packs: Record<string, string>;
  /** The packs every turn loads whatever the diagnosis says. */
  core: string[];
  /** The closed vocabulary: capability name → what it does. */
  capabilities: Record<string, string>;
  /** Pack name → the tools that declared a capability inside it. */
  pack_index: Record<string, string[]>;
}
