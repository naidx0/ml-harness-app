import { createResource, createSignal, For, Show, type JSX } from "solid-js"
import { Button } from "@opencode/ui/button"
import { SettingsList } from "@/settings/list"
import { SettingsRow } from "@/settings/row"
import "@/settings/settings.css"
import { harness, HarnessError } from "../engine"
import { tauriInvoke } from "../../platform/tauri"
import {
  buildLine,
  checkoutVerdict,
  failedChecks,
  formatUptime,
  healthFailure,
  notReadyHealth,
  portfileVerdict,
  restartOutcome,
  schemaLine,
  shortHex,
  type Bootstrap,
  type Health,
  type ShellStatus,
  type Verdict,
} from "./engine-identity"
import { BusyText, ErrorText, message, PageHeader, SettingsSection } from "./connections-parts"

/**
 * Settings > Engine (PARITY 6.3, 8.6): which engine this window talks to, what
 * code it runs, and the one button that replaces it.
 *
 * From the outgoing About section and EngineNotice. Everything here is read
 * off `GET /health` - the process (`engine.pid`, `engine.engine_id`), the code
 * (`build.sha`, `build.code_fingerprint`), the schema and the database - plus
 * the instruction set from `GET /api/tools`, and inside the desktop shell the
 * portfile via `engine_status`.
 *
 * Restarting the engine is an explicit act behind a confirmation, because the
 * engine outlives the window on purpose: what it is doing is often a long run,
 * and a restart stops it.
 */
export default function Section() {
  const [health, { refetch: recheck }] = createResource(async () => {
    try {
      return await harness<Health>("/health")
    } catch (failure) {
      // Up but not ready: the 503 carries the whole readout, failing checks
      // included, and that is what this page is for.
      const readout = notReadyHealth(failure)
      if (readout) return readout
      throw new Error(healthFailure(failure instanceof HarnessError ? failure.status : undefined, message(failure)))
    }
  })
  const [tools] = createResource(() => harness<{ instruction_set?: string }>("/api/tools"))
  const invoke = tauriInvoke()
  const [shell, { refetch: rereadShell }] = createResource(async () =>
    invoke ? ((await invoke("engine_status").catch(() => undefined)) as ShellStatus | undefined) : undefined,
  )

  const reading = () => (health.error ? undefined : health.latest)
  const status = () => (shell.error ? undefined : shell.latest)
  const instructionSet = () => (tools.error ? undefined : tools.latest?.instruction_set)

  const address = () => status()?.base_url ?? (invoke ? undefined : window.location.origin)
  const build = () => reading()?.build
  const failed = () => failedChecks(reading())

  const [confirming, setConfirming] = createSignal(false)
  const [busy, setBusy] = createSignal<string>()
  const [restartError, setRestartError] = createSignal<string>()

  const restart = async () => {
    if (!invoke) return
    setConfirming(false)
    setRestartError(undefined)
    setBusy("Restarting the engine…")
    const boot = (await invoke("restart_engine").catch((failure: unknown) => ({
      started: false,
      already_running: false,
      detail: message(failure),
    }))) as Bootstrap
    const outcome = restartOutcome(boot)
    // A new engine has a new token, so the window reloads to pick it up.
    if (outcome.ok) {
      window.location.reload()
      return
    }
    setBusy(undefined)
    setRestartError(outcome.why)
  }

  return (
    <>
      <PageHeader
        title="Engine"
        description="Runs on this computer - no account, no telemetry. The model is the only thing that can be remote, and only if you connect one."
      />
      <div class="settings-tab-body settings-tab-body--sectioned">
        <SettingsSection
          title="This window's engine"
          action={
            <Button
              size="small"
              variant="ghost"
              icon="refresh"
              disabled={health.loading}
              onClick={() => {
                void recheck()
                void rereadShell()
              }}
            >
              {health.loading ? "Checking…" : "Check again"}
            </Button>
          }
        >
          <Show when={health.error}>{(failure) => <ErrorText error={failure()} />}</Show>
          <Show when={failed().length > 0}>
            <div data-slot="engine-failing-checks" class="flex flex-col gap-1 pb-2 text-[13px]">
              <p class="text-v2-state-fg-danger">
                The engine is running but not ready: {failed().length === 1 ? "one of its checks" : `${failed().length} of its checks`}{" "}
                failed.
              </p>
              <ul class="flex flex-col gap-0.5">
                <For each={failed()}>
                  {(check) => (
                    <li class="text-v2-text-text-base">
                      <span class="font-mono">{check.name}</span>
                      <span class="text-v2-text-text-muted">{check.detail ? ` - ${check.detail}` : ""}</span>
                    </li>
                  )}
                </For>
              </ul>
            </div>
          </Show>
          <SettingsList>
            <Readout
              title="Address"
              description={
                invoke
                  ? "Where the desktop app found its engine, from engine.json."
                  : "This dev server, which forwards requests to the engine."
              }
              value={address()}
              missing={status()?.error ?? "not resolved"}
            />
            <Readout
              title="Process"
              description={
                reading()?.engine?.started_at ? `Started ${reading()?.engine?.started_at}` : "The process answering /health."
              }
              value={
                reading()?.engine?.pid !== undefined
                  ? `pid ${reading()?.engine?.pid}${
                      formatUptime(reading()?.engine?.uptime_seconds)
                        ? `, up ${formatUptime(reading()?.engine?.uptime_seconds)}`
                        : ""
                    }`
                  : undefined
              }
              tip={reading()?.engine?.engine_id}
              missing="not reported"
            />
            <Readout
              title="Build"
              description={
                build()?.sha_source
                  ? `The git commit the engine is running, read from ${build()?.sha_source}.`
                  : "The git commit the engine is running."
              }
              value={buildLine(build())}
              tip={build()?.sha ?? undefined}
              missing="not reported - the engine is too old to say"
            />
            <VerdictRow title="Vs this app" verdict={checkoutVerdict(build()?.sha, status()?.checkout)} />
            <Show when={portfileVerdict(status(), reading())}>
              {(verdict) => <VerdictRow title="engine.json" verdict={verdict()} />}
            </Show>
            <Readout
              title="Code fingerprint"
              description={
                build()?.code_files
                  ? `A sha256 over the engine's own ${build()?.code_files} source files. Two engines with the same one run the same code.`
                  : "A sha256 over the engine's own source files. Two engines with the same one run the same code."
              }
              value={build()?.code_fingerprint ? shortHex(build()?.code_fingerprint, 16) : undefined}
              tip={build()?.code_fingerprint ?? undefined}
              missing="not reported"
            />
            <Readout
              title="Instruction set"
              description="The version of the harness's instructions the engine loaded."
              value={instructionSet()}
              missing={tools.error ? message(tools.error) : "not reported"}
            />
            <Readout
              title="Database schema"
              description="The schema version the code knows, against the one the database is at."
              value={schemaLine(reading()?.schema)}
              missing="not reported"
            />
            <Readout
              title="Python"
              description={build()?.executable ?? "The interpreter running the engine."}
              value={build()?.python}
              missing="not reported"
            />
            <Readout
              title="Health"
              description={
                failed().length > 0
                  ? failed()
                      .map((check) => `${check.name}: ${check.detail}`)
                      .join("; ")
                  : `${(reading()?.checks ?? []).length} checks: this process, this build, this schema, this database.`
              }
              value={
                reading()?.status === "ok" ? "Ready" : reading()?.status === "not_ready" ? "Not ready" : reading()?.status
              }
              tone={failed().length > 0 ? "danger" : undefined}
              missing={health.error ? "not answering" : "…"}
            />
          </SettingsList>
        </SettingsSection>

        <SettingsSection title="Restart">
          <BusyText text={busy()} />
          <Show when={restartError()}>{(why) => <ErrorText error={why()} />}</Show>
          <SettingsList>
            <SettingsRow
              title="Restart the engine"
              description={
                invoke
                  ? "Stops the engine and starts a fresh one on this build, then reloads the window. Anything running in it - a training run, an eval, a turn - stops."
                  : "Only the desktop app can restart its engine. From a terminal: stop the engine, run start.ps1 (or scripts/launch.py), then reload this page."
              }
            >
              <Show
                when={confirming()}
                fallback={
                  <Button
                    size="normal"
                    variant="neutral"
                    icon="refresh"
                    disabled={!invoke || busy() !== undefined}
                    onClick={() => setConfirming(true)}
                  >
                    Restart the engine
                  </Button>
                }
              >
                <div class="flex flex-wrap items-center gap-2">
                  <Button size="normal" variant="danger" onClick={() => void restart()}>
                    Restart and stop what is running
                  </Button>
                  <Button size="normal" variant="ghost" onClick={() => setConfirming(false)}>
                    Keep it running
                  </Button>
                </div>
              </Show>
            </SettingsRow>
          </SettingsList>
        </SettingsSection>

        <SettingsSection title="Where your things are">
          <SettingsList>
            <SettingsRow
              title="Data"
              description="Threads, projects and measured facts live in SQLite beside the engine. Attaching a folder records its path - nothing is copied away."
            >
              <span class="max-w-[280px] truncate font-mono text-12-regular text-v2-text-text-base" title={reading()?.database?.path ?? undefined}>
                {reading()?.database?.path ?? "not reported"}
              </span>
            </SettingsRow>
            <SettingsRow
              title="Keys"
              description="API keys are in this computer's keychain, never in the database. Settings > Connections says which store and lets you remove one."
            >
              <span class="text-[13px] text-v2-text-text-muted">OS keychain</span>
            </SettingsRow>
            <SettingsRow
              title="Token use"
              description="Measured per conversation from what was actually sent. The Context pane has the breakdown; nothing invents a spend figure."
            >
              <span class="text-[13px] text-v2-text-text-muted">Per conversation</span>
            </SettingsRow>
          </SettingsList>
        </SettingsSection>
      </div>
    </>
  )
}

function Readout(props: {
  title: string
  description: JSX.Element
  value: string | undefined
  missing: string
  tip?: string
  tone?: "danger"
}) {
  return (
    <SettingsRow title={props.title} description={props.description}>
      <span
        class="max-w-[280px] truncate text-[13px] tabular-nums"
        classList={{
          "text-v2-text-text-base": props.value !== undefined && props.tone !== "danger",
          "text-v2-state-fg-danger": props.tone === "danger",
          "text-v2-text-text-faint": props.value === undefined,
        }}
        title={props.tip ?? props.value}
      >
        {props.value ?? props.missing}
      </span>
    </SettingsRow>
  )
}

const TONE: Record<Verdict["kind"], string> = {
  matches: "text-v2-state-fg-success",
  differs: "text-v2-state-fg-warning",
  unknown: "text-v2-text-text-faint",
}

const LABEL: Record<Verdict["kind"], string> = { matches: "Matches", differs: "Differs", unknown: "Cannot tell" }

function VerdictRow(props: { title: string; verdict: Verdict }) {
  return (
    <SettingsRow title={props.title} description={props.verdict.text}>
      <span class={`text-[13px] ${TONE[props.verdict.kind]}`}>{LABEL[props.verdict.kind]}</span>
    </SettingsRow>
  )
}

