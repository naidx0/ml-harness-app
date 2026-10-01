/**
 * "Connect a model" — the FAST surface. The deep one is `Settings.tsx`.
 *
 * WHAT CHANGED AND WHY. Max used the product and said this:
 *
 *   "The model thing should be like 'Connect the model'… Click on what you
 *    already have on this machine right away… to make it easy, and then if
 *    they want to dive a little deeper they can go to settings to configure
 *    more models, configure API keys, configure stuff like that."
 *
 *   "What if they don't want to choose a local model? Want to just choose some
 *    API model."
 *
 * This screen used to be a form. It opened on an empty name field, a base URL,
 * an adapter dropdown and a model box — four decisions before a question could
 * be asked, and every one of them already answered by the machine. The model
 * list existed, but as a picker that filled in the fourth field of the form
 * rather than as the thing you were choosing.
 *
 * So there are TWO ROADS and nothing else:
 *
 * 1. **On this machine.** Every model the local Ollama daemon has, each row a
 *    single click that creates the connection, makes it active and probes it.
 *    No URL, no adapter, no key — the machine already knows all three. The
 *    capabilities beside each name come from the GGUF metadata the tool read,
 *    so a row can say whether a model supports tool calling BEFORE it is
 *    connected.
 * 2. **An API or another server.** Equal weight, same surface, not behind a
 *    disclosure and not below a fold. Someone with an OpenAI or OpenRouter key
 *    and no local model at all has an obvious road in, which is exactly what
 *    the second quote asks for. The OpenAI-compatible adapter already covered
 *    this; the missing thing was the surface, and the assumption that local
 *    comes first.
 *
 * THREE THINGS THIS SCREEN IS STILL RESPONSIBLE FOR BEING HONEST ABOUT
 *
 * 1. **Where the key goes.** It is typed here, sent once to the engine, and
 *    put in the OS keychain. It is not held in React state after the request,
 *    not in `localStorage`, not in a URL, and it never comes back — the engine
 *    returns `has_key`, a boolean. NEW: the machine is asked whether it even
 *    HAS a keychain before the field is drawn, so "there is nowhere safe to
 *    put this" is said before the key is typed rather than after the save
 *    fails with a 503.
 * 2. **Whether it connected.** Saving a row and reaching a model are different
 *    events. The probe is a real call to the model's own server, so it gets
 *    its own result rather than being implied by the dialog closing.
 * 3. **Whether the model can call tools.** Three states, not two. `unknown`
 *    means nobody asked, which is not the same as "asked, and no" — and the
 *    product behaves differently in all three. The engine's own sentence for
 *    how it found out is shown verbatim, because a paraphrase of a measurement
 *    is not a measurement.
 */

import { useEffect, useMemo, useState } from 'react';
import type { Provider, ProviderPreset } from '../lib/engine/types';
import {
  forgetLocalModels,
  useLocalModels,
  type LocalModel,
  type LocalModelsState,
  type ProvidersState,
} from '../lib/useProviders';
import {
  discoverProviders,
  updateProvider,
  type DiscoveryCandidate,
} from '../lib/engine/client';
import { Icon } from './Icon';
import { Button, IconButton, Strip } from './primitives';
import './connect.css';

/**
 * THE NAME OF A CONNECTION, EDITABLE WHERE YOU CHOOSE ONE.
 *
 * Max, with nine models set up: *"let me add a nickname for each model just
 * to make it very simple."*
 *
 * The field was never missing - `PATCH /api/providers/{id}` has always taken
 * a name and Settings has always had a box for it. What was missing was
 * putting it where the question is asked. You notice that two rows are
 * indistinguishable at the moment you are trying to pick between them, and
 * being sent to another screen to fix it is how a thirty-second job becomes
 * one nobody does.
 *
 * Escape abandons, Enter and blur save, and an empty name is a no-op rather
 * than a row with no label - see `nameForALocalModel` for the same rule
 * applied to the default.
 */
function Nickname({ row, onSaved }: { row: Provider; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(row.name);
  const [busy, setBusy] = useState(false);

  async function save() {
    const wanted = draft.trim();
    if (busy) return;
    if (!wanted || wanted === row.name) {
      setDraft(row.name);
      setEditing(false);
      return;
    }
    setBusy(true);
    try {
      await updateProvider(row.id, { name: wanted });
      onSaved();
      setEditing(false);
    } catch {
      /* The engine refused or is gone. The box STAYS OPEN with what was
         typed in it: discarding somebody's words because a request failed
         is the one thing this control must not do. */
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        className="conn__rename"
        onClick={() => {
          setDraft(row.name);
          setEditing(true);
        }}
        title="Rename this connection"
      >
        {row.name}
      </button>
    );
  }

  return (
    <input
      className="conn__renamebox"
      value={draft}
      autoFocus
      disabled={busy}
      spellCheck={false}
      aria-label={`Name for ${row.model}`}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => void save()}
      onKeyDown={(event) => {
        if (event.key === 'Enter') void save();
        if (event.key === 'Escape') {
          setDraft(row.name);
          setEditing(false);
        }
      }}
    />
  );
}

export function ConnectModel({
  providers,
  onClose,
  onSettings,
}: {
  providers: ProvidersState;
  onClose: () => void;
  /** The deep surface. Every "configure more" road in here leads to it. */
  onSettings: () => void;
}) {
  const [connected, setConnected] = useState<Provider | null>(null);
  /* Which local model is mid-connect, so the row that was clicked is the row
     that reports. A single global "busy" would light up all of them. */
  const [pending, setPending] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<DiscoveryCandidate[] | null>(null);

  const local = useLocalModels();
  const active = providers.active;

  useEffect(() => {
    void discoverProviders()
      .then((result) => setDiscovered(result.candidates))
      .catch(() => setDiscovered([]));
  }, []);

  const connectLocal = async (model: string) => {
    setPending(model);
    const row = await providers.connectLocal(model);
    setPending(null);
    if (row) setConnected(row);
  };

  return (
    <div className="dialog__scrim" role="presentation" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Connect a model"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="dialog__head">
          <Icon name="model" size={16} />
          <h2 className="dialog__title">Connect a model</h2>
          <IconButton label="Close" icon="x" onClick={onClose} />
        </header>

        <div className="dialog__body scroll-y">
          <p className="dialog__lede">
            The harness ships no AI. It thinks with a model you lend it — one
            already on this machine, or a key you already pay for. Pick either.
          </p>

          {discovered !== null && discovered.some((c) => c.reachable) ? (
            <section className="cx-road">
              <div className="cx-road__head">
                <Icon name="search" size={14} />
                <h3 className="cx-road__title">Already running here</h3>
              </div>
              <p className="cx-road__note">
                We looked on this machine and found:
              </p>
              <div className="cx-models">
                {discovered
                  .filter((c) => c.reachable)
                  .map((candidate) => (
                    <div key={candidate.base_url} className="cx-model" data-active={undefined}>
                      <span className="cx-model__body">
                        <span className="cx-model__name">{candidate.name}</span>
                        <span className="cx-model__meta">
                          <span className="mono">{candidate.base_url}</span>
                          {candidate.models.length > 0 ? (
                            <>
                              <span className="sep">·</span>
                              {candidate.models.slice(0, 3).join(', ')}
                              {candidate.models.length > 3 ? ` +${candidate.models.length - 3} more` : ''}
                            </>
                          ) : (
                            <>
                              <span className="sep">·</span>no models listed yet
                            </>
                          )}
                        </span>
                      </span>
                      <span className="cx-model__state">
                        <Icon name="check" size={12} /> listening
                      </span>
                    </div>
                  ))}
              </div>
            </section>
          ) : null}

          {/* ── Road one: one click, no form ───────────────────────────── */}
          <section className="cx-road">
            <div className="cx-road__head">
              <Icon name="gpu" size={14} />
              <h3 className="cx-road__title">On this machine</h3>
              <span className="cx-road__spacer" />
              <IconButton
                label="Look again for local models"
                icon="refresh"
                size="xs"
                onClick={forgetLocalModels}
              />
            </div>

            <LocalModels
              state={local}
              active={active}
              pending={pending}
              busy={providers.busy !== null}
              onPick={(model) => void connectLocal(model)}
            />
          </section>

          {/* ── Road two: equal weight, not an afterthought ─────────────── */}
          <ApiRoad
            providers={providers}
            onConnected={(row) => setConnected(row)}
          />

          {providers.providers.length > 0 ? (
            <SavedConnections providers={providers} />
          ) : null}

          {providers.error ? (
            <Strip tone="wont" icon="alert">
              <span className="mono">{providers.error}</span>
            </Strip>
          ) : null}

          {connected ? (
            <Strip tone={connected.tool_calling === 'yes' ? 'fits' : 'info'}>
              Connected to <span className="mono">{connected.model}</span> —{' '}
              {describeTools(connected)}
              {connected.capability_detail ? `. ${connected.capability_detail}` : '.'}
            </Strip>
          ) : null}

          <div className="cx-deeper">
            <Button kind="ghost" icon="gear" onClick={onSettings}>
              Settings
            </Button>
            <span className="cx-deeper__text">
              Add another endpoint, edit a connection, or manage keys.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Road one ────────────────────────────────────────────────────────────
   The whole row is the button. Not a row with a "connect" control on the end:
   the click target is the thing being chosen, which is the difference between
   picking a model and operating a form about models. */

function LocalModels({
  state,
  active,
  pending,
  busy,
  onPick,
}: {
  state: LocalModelsState;
  active: Provider | null;
  pending: string | null;
  busy: boolean;
  onPick: (model: string) => void;
}) {
  if (state.status === 'loading') {
    return <p className="cx-road__note">Reading the models on this machine…</p>;
  }

  /* A daemon that is not running is the ordinary case for someone who has
     never installed one, and it is not an error to have made a different
     choice. It is said plainly, in the tool's own words, and the road beneath
     is the one that works for them. */
  if (state.status === 'error') {
    return (
      <p className="cx-road__note">
        No local models could be read: <span className="mono">{state.message}</span>
        <br />
        That is fine if you do not run one — connect an API below instead.
      </p>
    );
  }

  if (state.models.length === 0) {
    return (
      <p className="cx-road__note">
        The local daemon answered and has no models pulled yet, so there is
        nothing to click. Connect an API below, or pull a model and look again.
      </p>
    );
  }

  return (
    <>
      <div className="cx-models">
        {state.models.map((entry) => (
          <LocalModelRow
            key={entry.name}
            entry={entry}
            active={active !== null && active.model === entry.name}
            pending={pending === entry.name}
            busy={busy}
            onPick={() => onPick(entry.name)}
          />
        ))}
      </div>
      {/* Where the list came from, in the tool's own words. */}
      <p className="cx-road__note">{state.source}</p>
    </>
  );
}

function LocalModelRow({
  entry,
  active,
  pending,
  busy,
  onPick,
}: {
  entry: LocalModel;
  active: boolean;
  pending: boolean;
  busy: boolean;
  onPick: () => void;
}) {
  const tools = entry.capabilities?.includes('tools');
  return (
    <button
      type="button"
      className="cx-model"
      data-active={active || undefined}
      disabled={busy || active}
      onClick={onPick}
      title={active ? 'This is the model the harness is thinking with' : 'Connect this model'}
    >
      <span className="cx-model__body">
        <span className="cx-model__name">{entry.name}</span>
        <span className="cx-model__meta">
          {entry.params_b !== null ? (
            <>
              <span className="cx-model__num">{entry.params_b}</span>B params
              <span className="sep">·</span>
            </>
          ) : null}
          {entry.on_disk_gb !== null ? (
            <>
              <span className="cx-model__num">{entry.on_disk_gb}</span> GB on disk
              <span className="sep">·</span>
            </>
          ) : null}
          {/* Measured off the GGUF before anything is connected, which is why
              it can be said here at all. */}
          {tools ? 'can call tools' : 'no tool calling'}
        </span>
      </span>

      {active ? (
        <span className="cx-model__state" data-tone="fits">
          <Icon name="check" size={12} /> in use
        </span>
      ) : pending ? (
        <span className="cx-model__state">
          <Icon name="clock" size={12} /> connecting…
        </span>
      ) : (
        <span className="cx-model__state">
          <Icon name="chevright" size={12} />
        </span>
      )}
    </button>
  );
}

/* ── Road two ────────────────────────────────────────────────────────────
   THE API PATH IS FIRST-CLASS. It is not "advanced", it is not behind a
   "custom" link, and it does not require reading past a local list to find.

   The endpoint chips come from `GET /api/provider_presets` — the engine's own
   list, so this component has no URLs in it and cannot drift from
   `app/providers.PRESETS`. Ollama is filtered out because it has its own road
   above; everything else is one OpenAI-compatible path driven by a base URL,
   which is why the adapter is derived from the chip rather than asked for. */

function ApiRoad({
  providers,
  onConnected,
}: {
  providers: ProvidersState;
  onConnected: (row: Provider) => void;
}) {
  const options = useMemo(
    () => providers.presets.filter((preset) => preset.adapter !== 'ollama'),
    [providers.presets],
  );
  const [choice, setChoice] = useState<ProviderPreset | null>(null);
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');

  /* Remote endpoints first inside this road: someone who came here for an API
     key wants OpenAI before vLLM. `kind` is decided by the engine from the
     URL, so "needs a key" is the honest proxy for "not on this box". */
  const ordered = useMemo(
    () => [...options].sort((a, b) => Number(b.needs_key) - Number(a.needs_key)),
    [options],
  );

  useEffect(() => {
    if (!choice && ordered.length > 0) {
      setChoice(ordered[0]);
      setBaseUrl(ordered[0].base_url);
    }
  }, [choice, ordered]);

  const keychain = providers.keychain;
  const wantsKey = choice?.needs_key ?? true;
  const ready = Boolean(baseUrl.trim() && model.trim()) && providers.busy === null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready || !choice) return;
    const key = apiKey;
    /* Dropped from this component's state before the request is even awaited.
       There is no path from here to storage. */
    setApiKey('');
    const row = await providers.connect({
      name: choice.name,
      base_url: baseUrl.trim(),
      model: model.trim(),
      adapter: choice.adapter,
      api_key: key ? key : undefined,
    });
    if (row) onConnected(row);
  };

  return (
    <section className="cx-road">
      <div className="cx-road__head">
        <Icon name="cloud" size={14} />
        <h3 className="cx-road__title">With an API key, or another server</h3>
      </div>

      <div className="cx-endpoints">
        {ordered.map((option) => (
          <button
            key={option.name}
            type="button"
            className="chip"
            aria-pressed={choice?.name === option.name}
            onClick={() => {
              setChoice(option);
              setBaseUrl(option.base_url);
            }}
          >
            <Icon name={option.needs_key ? 'key' : 'terminal'} size={12} />
            <span className="chip__stack">
              <span className="chip__label">{option.name}</span>
            </span>
          </button>
        ))}
      </div>

      <form onSubmit={submit}>
        <Field label="Model">
          <input
            className="input mono"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder="the model id this endpoint answers to"
            spellCheck={false}
            autoComplete="off"
          />
        </Field>

        {wantsKey ? (
          <Field label="API key">
            <input
              className="input mono"
              type="password"
              value={apiKey}
              autoComplete="off"
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={keychain?.available === false ? 'no keychain on this machine' : ''}
              disabled={keychain?.available === false}
            />
            {/* WHAT WILL HAPPEN TO THIS KEY, SAID BEFORE IT IS TYPED. The
                engine's own sentence, verbatim — it names the actual store on
                this machine, or says there is not one and what to do instead. */}
            <span className="cx-keynote">
              <Icon name={keychain?.available === false ? 'alert' : 'sensitive'} size={12} />
              <span>
                {keychain
                  ? keychain.detail
                  : 'Asking this machine where a key would go…'}{' '}
                It is never written to the database, never logged, and never
                returned to this page.
              </span>
            </span>
          </Field>
        ) : null}

        {/* The URL is shown rather than hidden: it is the one field that
            decides whether the request leaves this machine, and `kind` — which
            the egress guard reads — is derived from it. */}
        <Field
          label="Endpoint"
          hint="Everything except Ollama is one OpenAI-compatible path driven by this URL."
        >
          <input
            className="input mono"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            spellCheck={false}
          />
        </Field>

        <div className="dialog__actions">
          <Button kind="primary" type="submit" disabled={!ready}>
            Connect and check
          </Button>
          {providers.busy ? <span className="meta">{providers.busy}</span> : null}
        </div>
      </form>
    </section>
  );
}

/* ── What is already saved ───────────────────────────────────────────────── */

function SavedConnections({ providers }: { providers: ProvidersState }) {
  return (
    <section className="cx-road">
      <div className="cx-road__head">
        <Icon name="commit" size={14} />
        <h3 className="cx-road__title">Already connected</h3>
      </div>
      <div className="conn__list">
        {providers.providers.map((row) => (
          <div className="conn" key={row.id} data-active={row.is_active === 1}>
            <div className="conn__main">
              <div className="conn__title">
                <Nickname row={row} onSaved={() => void providers.refresh()} />
                <span className="conn__model mono">{row.model}</span>
              </div>
              <div className="conn__meta">
                <span className="mono">{row.base_url}</span>
                <span className="sep">·</span>
                {row.kind}
                <span className="sep">·</span>
                {describeTools(row)}
                {row.has_key ? (
                  <>
                    <span className="sep">·</span>key in the keychain
                  </>
                ) : null}
              </div>
            </div>
            <div className="rowgap-6">
              {row.is_active === 1 ? (
                <span className="conn__active">
                  <Icon name="check" size={12} /> in use
                </span>
              ) : (
                <Button
                  kind="ghost"
                  onClick={() => void providers.use(row.id)}
                  disabled={providers.busy !== null}
                >
                  Use this one
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {hint ? <span className="field__hint">{hint}</span> : null}
    </label>
  );
}

export function describeTools(row: Provider): string {
  if (row.tool_calling === 'yes') return 'it can call tools';
  if (row.tool_calling === 'no') return 'it cannot call tools';
  return 'tool calling not probed yet';
}
