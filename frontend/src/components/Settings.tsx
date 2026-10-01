/**
 * SETTINGS — the deep surface, and the only "account" a local product has.
 *
 * Max, having used it:
 *
 *   "At the bottom left you just have the account and settings. I see it's just
 *    model because obviously it's local, but your local config settings can be
 *    controlled from here instead of an actual online account."
 *
 * There is no online account and there should not be one — we ship no AI, we
 * hold no data, and there is nothing to log in to. So what lives behind that
 * bottom-left row is the machine, the models connected to it, the keys, and
 * the preferences. That is the whole of "your account" for a product that runs
 * on your own computer, and saying so out loud is the first line on the page.
 *
 * ITS RELATIONSHIP TO `ConnectModel.tsx` IS THE POINT. The dialog is the fast
 * road: one click on a model this machine already has, or a key and a model id
 * for an API. This is where someone goes to "dive a little deeper" — edit a
 * saved connection, point it somewhere else, replace or remove a key, forget a
 * connection entirely. Both surfaces read the same `useProviders` state and
 * call the same engine routes; neither has a rule the other does not.
 *
 * WHAT IS DELIBERATELY NOT HERE
 *
 * - **No telemetry switch.** There is no telemetry to switch off. A toggle for
 *   a thing that does not exist is a claim, and it would be a false one in the
 *   most damaging possible direction.
 * - **No "sign in".** See above.
 * - **No portals section, and no portal switch.** DESIGN_DIRECTIVES §3, as
 *   Max rewrote it on 2026-08-19: "There is one product — consumer/enterprise
 *   is dropped… If residency, scale or from-scratch training come back, they
 *   come back as features with specifications, not as a second front door."
 *   The section that used to sit here answered his question "what's the
 *   biggest difference between consumer and enterprise" — and the answer, in
 *   the end, was that there is no difference to explain. A settings page that
 *   describes two portals in a product with one is the toggle's argument
 *   surviving the toggle, so it went with it.
 */

import { useEffect, useState } from 'react';
import { engineSession } from '../lib/engine/config';
import {
  checkAgainstCheckout,
  type Checkout,
  type EngineIdentity,
} from '../lib/engine/identity';
import { LOCAL_SPECS_FIELDS, type LocalSpecsField } from '../lib/engine/types';
import type { Provider, ProviderPreset } from '../lib/engine/types';
import { displayTag } from '../lib/format';
import { useLocalSpecs } from '../lib/useLocalSpecs';
import { useLocalModels, type ProvidersState } from '../lib/useProviders';
import { describeTools } from './ConnectModel';

/* WHO SAID SO, ON HOVER. Max, 2026-09-17: "measured isn't a thing, that's a
   status symbol for an AI. For a human it should say ready." The provenance
   is real - a context length read by a probe and one reported by a server
   are different facts - and it stays, as the sentence behind the number
   rather than a chip beside it. */
function contextTitle(provenance: string): string {
  switch ((provenance || '').toLowerCase()) {
    case 'measured':
      return 'Context length read by a probe of this connection';
    case 'declared':
      return 'Context length reported by the server for this model';
    case 'defaulted':
      return 'Context length assumed - nothing reported one';
    default:
      return 'Context length';
  }
}
import { ToolSettings } from './ToolSettings';
import { Icon, type IconName } from './Icon';
import { Button, IconButton, ProvenanceTag, Strip } from './primitives';
import type { Theme } from './Chrome';
import './connect.css';

/** Short hex for a person to read aloud — full value stays in the title tip. */
function shortHex(value: string | null | undefined, keep = 12): string {
  if (!value) return '';
  return value.length > keep ? value.slice(0, keep) : value;
}

type SectionId = 'models' | 'tools' | 'keys' | 'machine' | 'appearance' | 'about';

const SECTIONS: { id: SectionId; label: string; icon: IconName }[] = [
  { id: 'models', label: 'Models', icon: 'model' },
  /* SECOND, after the model and before the keys. What a project hands the
     model is the other half of "what is this thread running on", and it was
     the half nobody could see: measured 2026-09-14, tool schemas were 12,735
     tokens of a 29,929-token prompt. */
  { id: 'tools', label: 'Tools', icon: 'skill' },
  { id: 'keys', label: 'Keys', icon: 'key' },
  { id: 'machine', label: 'This machine', icon: 'gpu' },
  { id: 'appearance', label: 'Appearance', icon: 'sun' },
  { id: 'about', label: 'About', icon: 'info' },
];

export function Settings({
  providers,
  theme,
  onTheme,
  instructionSet,
  projectId,
  onConnect,
  onClose,
  initial = 'models',
}: {
  providers: ProvidersState;
  theme: Theme;
  onTheme: (next: Theme) => void;
  /** `GET /api/tools` reports which instruction set the engine loaded. */
  instructionSet: string;
  /** Whose settings these are. Null before a conversation is open, which the
   *  Tools section says rather than guessing at a project. */
  projectId: number | null;
  /** Back to the fast road. */
  onConnect: () => void;
  onClose: () => void;
  initial?: SectionId;
}) {
  const [section, setSection] = useState<SectionId>(initial);

  return (
    <div className="dialog__scrim" role="presentation" onClick={onClose}>
      <div
        className="dialog dialog--wide"
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="dialog__head">
          <Icon name="gear" size={16} />
          <h2 className="dialog__title">Settings</h2>
          <IconButton label="Close" icon="x" onClick={onClose} />
        </header>

        <div className="set">
          <nav className="set__nav" aria-label="Settings sections">
            {SECTIONS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                className="set__navitem"
                aria-pressed={section === entry.id}
                onClick={() => setSection(entry.id)}
              >
                <Icon name={entry.icon} />
                {entry.label}
              </button>
            ))}
          </nav>

          <div className="set__body scroll-y">
            {section === 'models' ? (
              <Models providers={providers} onConnect={onConnect} />
            ) : null}
            {section === 'tools' ? <ToolSettings projectId={projectId} /> : null}
            {section === 'keys' ? <Keys providers={providers} /> : null}
            {section === 'machine' ? <Machine /> : null}
            {section === 'appearance' ? (
              <Appearance theme={theme} onTheme={onTheme} />
            ) : null}
            {section === 'about' ? <About instructionSet={instructionSet} /> : null}

            {providers.error ? (
              <div style={{ marginTop: 'var(--sp-12)' }}>
                <Strip tone="wont" icon="alert">
                  <span className="mono">{providers.error}</span>
                </Strip>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Models ──────────────────────────────────────────────────────────────
   Every saved connection, editable in place, plus the road to a new one.

   EDITING IS WHERE THE HONESTY LIVES. Point a row at a different model and the
   engine throws away what the last probe measured — `tool_calling`, the
   capability sentence and the context length all belong to one model on one
   server. The interface says that will happen before it happens, because a
   context length tagged MEASURED beside a model nobody measured is an invented
   number, which invariant 3 forbids more strongly than a missing one. */

function Models({
  providers,
  onConnect,
}: {
  providers: ProvidersState;
  onConnect: () => void;
}) {
  const local = useLocalModels();
  const localCount = local.status === 'ok' ? local.models.length : 0;

  return (
    <>
      <p className="set__lede">
        The harness thinks with a model you lend it. Exactly one connection is
        active at a time, and it is the one every turn goes through.
      </p>

      <div className="set__group">
        <h3 className="set__h">
          <Icon name="model" size={12} />
          Connections
          <span className="set__hspace" />
          <Button kind="ghost" small icon="plus" onClick={onConnect}>
            Connect a model
          </Button>
        </h3>

        {providers.providers.length === 0 ? (
          <p className="cx-road__note">
            Nothing is connected yet.{' '}
            {localCount > 0
              ? `This machine has ${localCount} local model${localCount === 1 ? '' : 's'} you can connect in one click.`
              : 'Connect an API key or a local endpoint to get started.'}
          </p>
        ) : (
          providers.providers.map((row) => (
            <ConnectionCard key={row.id} row={row} providers={providers} />
          ))
        )}
      </div>

      <AddConnection providers={providers} />
    </>
  );
}

function ConnectionCard({
  row,
  providers,
}: {
  row: Provider;
  providers: ProvidersState;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [name, setName] = useState(row.name);
  const [baseUrl, setBaseUrl] = useState(row.base_url);
  const [model, setModel] = useState(row.model);
  const [apiKey, setApiKey] = useState('');
  const busy = providers.busy !== null;

  /* What the engine will discard if this is saved. Computed from the row the
     interface is holding rather than guessed at afterwards, so the warning is
     the same rule the engine applies. */
  const willReprobe = baseUrl !== row.base_url || model !== row.model;

  const save = async () => {
    const key = apiKey;
    setApiKey('');
    await providers.update(row.id, {
      name: name.trim() || row.name,
      base_url: baseUrl.trim() || row.base_url,
      model: model.trim() || row.model,
      /* LEFT OFF ENTIRELY when the field is empty. The engine distinguishes
         absent from empty: absent keeps the stored key, empty deletes it. A
         settings form has no key to put back, so absent is the only correct
         thing to send when nobody typed one. */
      ...(key ? { api_key: key } : {}),
    });
    setOpen(false);
  };

  return (
    <div className="set__conn" data-active={row.is_active === 1}>
      <div className="set__connhead">
        <div className="set__conntitle">
          <div className="set__connname">
            {row.name}
            <span className="set__connmodel">{row.model}</span>
          </div>
          <div className="set__connmeta">
            <span className="mono">{row.base_url}</span>
            <span className="sep">·</span>
            {row.kind}
            <span className="sep">·</span>
            {describeTools(row)}
            {row.ctx_len !== null ? (
              <>
                <span className="sep">·</span>
                <span
                  className="set__connnum"
                  title={contextTitle(row.ctx_len_provenance)}
                >
                  {row.ctx_len.toLocaleString()}
                </span>{' '}
                token context
              </>
            ) : null}
            {row.has_key ? (
              <>
                <span className="sep">·</span>
                <Icon name="sensitive" size={11} /> key in the keychain
              </>
            ) : null}
          </div>
        </div>

        <div className="rowgap-6">
          {row.is_active === 1 ? (
            <span
              className="conn__active"
              data-state={row.tool_calling === 'unknown' ? 'unprobed' : 'ready'}
              title={
                row.tool_calling === 'unknown'
                  ? 'In use, and not yet probed - the first turn will tell'
                  : 'In use, and it answered its probe'
              }
            >
              <Icon name="check" size={12} />{' '}
              {row.tool_calling === 'unknown' ? 'in use' : 'ready'}
            </span>
          ) : (
            <Button
              kind="ghost"
              small
              onClick={() => void providers.use(row.id)}
              disabled={busy}
            >
              Use this one
            </Button>
          )}
          <IconButton
            label="Re-check what this model can do"
            icon="refresh"
            size="xs"
            onClick={() => void providers.recheck(row.id)}
            disabled={busy}
          />
          <IconButton
            label={open ? 'Close the editor' : 'Edit this connection'}
            icon="sliders"
            size="xs"
            /* The fields are re-seeded from the row every time the editor is
               opened, not once when the card mounted. The card is keyed by row
               id, so React keeps this instance across refreshes — and an editor
               that opens on values a re-check or another surface has since
               changed would show the user something that is no longer true and
               then write it back. */
            onClick={() =>
              setOpen((value) => {
                if (!value) {
                  setName(row.name);
                  setBaseUrl(row.base_url);
                  setModel(row.model);
                  setApiKey('');
                }
                return !value;
              })
            }
          />
          <IconButton
            label="Forget this connection"
            icon="trash"
            size="xs"
            onClick={() => setConfirming(true)}
            disabled={busy}
          />
        </div>
      </div>

      {open ? (
        <div className="set__connedit">
          <Field label="What to call it">
            <input
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label="Endpoint">
            <input
              className="input mono"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              spellCheck={false}
            />
          </Field>
          <Field label="Model">
            <input
              className="input mono"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              spellCheck={false}
            />
          </Field>
          <Field
            label="Replace the API key"
            hint={
              row.has_key
                ? 'A key is stored for this connection. Leave this empty to keep it — the engine never gives a key back, so an empty field means "unchanged", not "delete".'
                : 'No key is stored for this connection. Leave it empty for a server that does not want one.'
            }
          >
            <input
              className="input mono"
              type="password"
              value={apiKey}
              autoComplete="off"
              onChange={(event) => setApiKey(event.target.value)}
              disabled={providers.keychain?.available === false}
              placeholder={
                providers.keychain?.available === false
                  ? 'no keychain on this machine'
                  : ''
              }
            />
          </Field>

          {willReprobe ? (
            <Strip tone="info" icon="info">
              Saving this drops what the last probe measured — whether it can
              call tools, and its context length. Those were measured on{' '}
              <span className="mono">{row.model}</span> at{' '}
              <span className="mono">{row.base_url}</span> and say nothing about
              a different one. Re-check afterwards to measure them again.
            </Strip>
          ) : null}

          <div className="dialog__actions">
            <Button kind="primary" onClick={() => void save()} disabled={busy}>
              Save
            </Button>
            <Button kind="quiet" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            {providers.busy ? <span className="meta">{providers.busy}</span> : null}
          </div>
        </div>
      ) : null}

      {confirming ? (
        <div className="set__danger">
          <Icon name="alert" size={14} />
          <span>
            Forget <strong>{row.name}</strong>? The connection goes, and{' '}
            {row.has_key
              ? 'its key is removed from this machine’s keychain with it'
              : 'there is no key to remove'}
            . Nothing else is deleted.
          </span>
          <span className="cx-road__spacer" />
          <Button
            kind="ghost"
            small
            icon="trash"
            onClick={() => void providers.remove(row.id)}
            disabled={busy}
          >
            Forget it
          </Button>
          <Button kind="quiet" small onClick={() => setConfirming(false)}>
            Keep it
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The full form — every field, no assumptions.
 *
 * The fast dialog asks for two things because it can derive the rest. This
 * asks for all of them, because "configure more models" means the case the
 * presets do not cover: a server on the network, a gateway, a proxy in front
 * of a provider. The adapter is a choice here rather than a derivation for the
 * same reason.
 */
function AddConnection({ providers }: { providers: ProvidersState }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [adapter, setAdapter] = useState('openai-compatible');
  const [apiKey, setApiKey] = useState('');

  const apply = (preset: ProviderPreset) => {
    setName(preset.name);
    setBaseUrl(preset.base_url);
    setAdapter(preset.adapter);
  };

  const ready = Boolean(name.trim() && baseUrl.trim() && model.trim());

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const key = apiKey;
    setApiKey('');
    const row = await providers.connect({
      name: name.trim(),
      base_url: baseUrl.trim(),
      model: model.trim(),
      adapter,
      api_key: key ? key : undefined,
    });
    if (row) {
      setOpen(false);
      setName('');
      setBaseUrl('');
      setModel('');
      setApiKey('');
    }
  };

  if (!open) {
    return (
      <div className="set__group">
        <Button kind="ghost" icon="plus" onClick={() => setOpen(true)}>
          Add an endpoint by hand
        </Button>
      </div>
    );
  }

  return (
    <div className="set__group">
      <h3 className="set__h">
        <Icon name="terminal" size={12} />
        Add an endpoint
      </h3>

      <div className="cx-endpoints">
        {providers.presets.map((preset) => (
          <button
            key={preset.name}
            type="button"
            className="chip"
            aria-pressed={baseUrl === preset.base_url}
            onClick={() => apply(preset)}
          >
            <Icon name={preset.needs_key ? 'key' : 'terminal'} size={12} />
            <span className="chip__stack">
              <span className="chip__label">{preset.name}</span>
            </span>
          </button>
        ))}
      </div>

      <form onSubmit={submit}>
        <Field label="What to call it">
          <input
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Endpoint">
          <input
            className="input mono"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            spellCheck={false}
            placeholder="http://…"
          />
        </Field>
        <Field
          label="How to speak to it"
          hint="Ollama has its own endpoint. Everything else — OpenAI, OpenRouter, LM Studio, llama.cpp, vLLM — is one OpenAI-compatible path driven by the base URL."
        >
          <select
            className="input"
            value={adapter}
            onChange={(event) => setAdapter(event.target.value)}
          >
            <option value="ollama">Ollama</option>
            <option value="openai-compatible">OpenAI-compatible</option>
          </select>
        </Field>
        <Field label="Model">
          <input
            className="input mono"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder="the model id this server answers to"
            spellCheck={false}
          />
        </Field>
        <Field label="API key" hint="Leave it empty for a server that does not want one.">
          <input
            className="input mono"
            type="password"
            value={apiKey}
            autoComplete="off"
            onChange={(event) => setApiKey(event.target.value)}
            disabled={providers.keychain?.available === false}
          />
        </Field>

        <div className="dialog__actions">
          <Button kind="primary" type="submit" disabled={!ready || providers.busy !== null}>
            Connect and check
          </Button>
          <Button kind="quiet" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          {providers.busy ? <span className="meta">{providers.busy}</span> : null}
        </div>
      </form>
    </div>
  );
}

/* ── Keys ────────────────────────────────────────────────────────────────
   THE ONE SCREEN IN THE PRODUCT THAT EXPLAINS WHERE A SECRET LIVES.

   `AGENTS.md` invariant 2: provider API keys go to the OS keychain, the
   database holds a reference and never the key. That is enforced by a test
   that reads the database file as bytes — but a user cannot run our test
   suite, and "trust us" is not a security property. So this section names the
   actual store on this machine, in the engine's own words, and says what to do
   on a machine that has none. */

function Keys({ providers }: { providers: ProvidersState }) {
  const keychain = providers.keychain;
  const withKeys = providers.providers.filter((row) => row.has_key);

  return (
    <>
      <p className="set__lede">
        An API key you give the harness goes to this machine&rsquo;s own secret
        store. It is never written to the database, never logged, and never
        returned to this page — the engine answers <span className="mono">has_key</span>,
        a yes or no, and nothing else.
      </p>

      <div className="set__group">
        <h3 className="set__h">
          <Icon name="sensitive" size={12} />
          Where keys go on this machine
        </h3>
        {keychain === null ? (
          <p className="cx-road__note">Asking the engine…</p>
        ) : (
          <>
            <div className="set__kv">
              <span className="set__kvk">Secret store</span>
              <span className="set__kvv" data-absent={!keychain.available || undefined}>
                {keychain.backend ?? 'none on this machine'}
              </span>
            </div>
            <div className="set__kv">
              <span className="set__kvk">Filed under</span>
              <span className="set__kvv">{keychain.service}</span>
            </div>
            <div className="set__kv">
              <span className="set__kvk">Environment override</span>
              <span className="set__kvv">
                {keychain.env_prefix}
                <span className="sep">&lt;connection id&gt;</span>
              </span>
            </div>
            {/* The engine's own sentence, verbatim. */}
            <p className="cx-road__note">{keychain.detail}</p>
            {!keychain.available ? (
              <Strip tone="spills" icon="alert">
                With no store, a key cannot be saved here. The engine refuses to
                fall back to a file or to the database — a key it cannot protect
                is a key it declines to hold.
              </Strip>
            ) : null}
          </>
        )}
      </div>

      <div className="set__group">
        <h3 className="set__h">
          <Icon name="key" size={12} />
          Connections holding a key
        </h3>
        {withKeys.length === 0 ? (
          <p className="cx-road__note">
            None. Every connection saved here reaches its model without one,
            which is what a local endpoint normally does.
          </p>
        ) : (
          withKeys.map((row) => (
            <div className="set__kv" key={row.id}>
              <span className="set__kvk">
                {row.name}
                <span className="sep"> · </span>
                <span className="mono">{row.model}</span>
              </span>
              <span className="set__kvv">
                <Icon name="check" size={12} /> stored
                <Button
                  kind="quiet"
                  small
                  icon="trash"
                  disabled={providers.busy !== null}
                  onClick={() => void providers.update(row.id, { api_key: '' })}
                >
                  Remove the key
                </Button>
              </span>
            </div>
          ))
        )}
      </div>
    </>
  );
}

/* ── This machine ────────────────────────────────────────────────────────
   The same reading the Machine pane shows, from the same shared `/local_specs`
   call. Every row carries its tag, and a field the engine could not read is
   ABSENT rather than defaulted into a number — "a failed detection never
   renders as a measurement". What is new here is `sources`: what was actually
   run to obtain each figure, which is the only version of provenance a person
   can check for themselves. */

function Machine() {
  const specs = useLocalSpecs();

  if (specs.status === 'loading') {
    return <p className="cx-road__note">Reading this machine…</p>;
  }
  if (specs.status === 'error') {
    return (
      <Strip tone="wont" icon="alert">
        The engine could not report this machine:{' '}
        <span className="mono">{specs.message}</span>
      </Strip>
    );
  }

  const labels: Record<LocalSpecsField, string> = {
    gpu_name: 'Graphics card',
    vram_gb: 'VRAM',
    ram_gb: 'System memory',
    disk_free_gb: 'Free disk',
    os: 'Operating system',
    driver_version: 'Driver',
    compute_capability: 'Compute capability',
  };
  const units: Partial<Record<LocalSpecsField, string>> = {
    vram_gb: 'GB',
    ram_gb: 'GB',
    disk_free_gb: 'GB',
  };

  return (
    <>
      <p className="set__lede">
        What the engine measured about this box. Training happens here, so these
        are the numbers every feasibility verdict is computed from.
      </p>

      <div className="set__group">
        {LOCAL_SPECS_FIELDS.map((field) => {
          const value = specs.specs[field];
          const source = specs.specs.sources[field];
          return (
            <div className="set__kv" key={field}>
              <span className="set__kvk">{labels[field]}</span>
              <span className="set__kvv" data-absent={value === null || undefined}>
                {value === null ? (
                  'not detected'
                ) : (
                  <>
                    {String(value)}
                    {units[field] ? ` ${units[field]}` : ''}
                  </>
                )}
                <ProvenanceTag tag={displayTag(specs.specs.provenance[field])} />
                {source ? <span className="set__src">{source}</span> : null}
              </span>
            </div>
          );
        })}
      </div>

      {specs.specs.warnings.length > 0 ? (
        <div className="set__group">
          <h3 className="set__h">
            <Icon name="alert" size={12} />
            What the detector could not do
          </h3>
          {specs.specs.warnings.map((warning) => (
            <p className="cx-road__note" key={warning}>
              {warning}
            </p>
          ))}
        </div>
      ) : null}
    </>
  );
}

/* ── Appearance ─────────────────────────────────────────────────────────── */

function Appearance({
  theme,
  onTheme,
}: {
  theme: Theme;
  onTheme: (next: Theme) => void;
}) {
  const options: { value: Theme; label: string; hint: string; icon: IconName }[] = [
    { value: 'dark', label: 'Dark', hint: 'The default this product ships on.', icon: 'moon' },
    { value: 'light', label: 'Light', hint: 'A separately tuned instrument, not an inversion.', icon: 'sun' },
    { value: 'system', label: 'Follow the system', hint: 'No attribute is set; the media query decides.', icon: 'refresh' },
  ];

  return (
    <>
      <p className="set__lede">
        Both themes ship at equal quality. There is no density setting: the
        interface is compact and stays compact — airy is a defect here, not a
        preference.
      </p>

      <div className="set__group">
        <h3 className="set__h">
          <Icon name="sun" size={12} />
          Theme
        </h3>
        <div className="cx-models">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              className="cx-model"
              data-active={theme === option.value || undefined}
              onClick={() => onTheme(option.value)}
            >
              <Icon name={option.icon} />
              <span className="cx-model__body">
                <span className="cx-model__name" style={{ fontFamily: 'var(--font-sans)' }}>
                  {option.label}
                </span>
                <span className="cx-model__meta">{option.hint}</span>
              </span>
              {theme === option.value ? (
                <span className="cx-model__state" data-tone="fits">
                  <Icon name="check" size={12} />
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

/* ── About ───────────────────────────────────────────────────────────────── */

function About({ instructionSet }: { instructionSet: string }) {
  const [engine, setEngine] = useState<{
    url: string | null;
    reason: string | null;
    identity: EngineIdentity | null;
    checkout: Checkout | null;
  }>({
    url: null,
    reason: null,
    identity: null,
    checkout: null,
  });

  useEffect(() => {
    let live = true;
    void engineSession().then((session) => {
      if (!live) return;
      setEngine({
        url: session.engineBaseUrl,
        reason: session.reason,
        identity: session.identity,
        checkout: session.checkout,
      });
    });
    return () => {
      live = false;
    };
  }, []);

  const build = engine.identity?.revision ?? null;
  const fingerprint = engine.identity?.codeFingerprint ?? null;
  const dirty = engine.identity?.dirty;
  const verdict = checkAgainstCheckout(engine.identity, engine.checkout);
  const matchLine =
    verdict.kind === 'matches'
      ? `matches this page (${shortHex(verdict.revision)})`
      : verdict.kind === 'differs'
        ? `engine ${shortHex(verdict.engine)} · page ${shortHex(verdict.checkout)} — restart or reinstall`
        : null;

  return (
    <>
      <p className="set__lede">
        Runs on this machine — no account, no telemetry. The model is the only
        thing that can be remote, and only if you connect one.
      </p>

      <div className="set__group">
        <h3 className="set__h">
          <Icon name="terminal" size={12} />
          Engine
        </h3>
        <div className="set__kv">
          <span className="set__kvk">Address</span>
          <span className="set__kvv" data-absent={!engine.url || undefined}>
            {engine.url ?? engine.reason ?? 'not resolved'}
          </span>
        </div>
        <div className="set__kv">
          <span className="set__kvk">Build</span>
          <span
            className="set__kvv"
            data-absent={!build || undefined}
            title={build ?? undefined}
          >
            {build
              ? `${shortHex(build)}${dirty === true ? ' (dirty tree)' : ''}`
              : 'not reported — engine is too old to say'}
          </span>
        </div>
        {matchLine ? (
          <div className="set__kv">
            <span className="set__kvk">Vs this page</span>
            <span
              className="set__kvv"
              data-absent={verdict.kind === 'differs' || undefined}
            >
              {matchLine}
            </span>
          </div>
        ) : null}
        <div className="set__kv">
          <span className="set__kvk">Code fingerprint</span>
          <span
            className="set__kvv"
            data-absent={!fingerprint || undefined}
            title={fingerprint ?? undefined}
          >
            {fingerprint ? shortHex(fingerprint, 16) : 'not reported'}
          </span>
        </div>
        <div className="set__kv">
          <span className="set__kvk">Instruction set</span>
          <span className="set__kvv" data-absent={!instructionSet || undefined}>
            {instructionSet || 'not reported'}
          </span>
        </div>
        <details className="set__details">
          <summary>More about Build and tokens</summary>
          <p className="set__prose">
            Build is the git commit the engine is running. If it does not match
            what you expect: quit the desktop app and open a fresh installer, or
            (dev) stop the engine, pull, run <code>start.ps1</code>, reload. A
            yellow strip under the app bar appears when the page and engine
            disagree.
          </p>
          <p className="set__prose">
            Token use is measured per thread from <code>turn.context</code> —
            totals sit on the usage strip above the composer; Context pane has
            the breakdown. Nothing invents a spend figure.
          </p>
        </details>
      </div>

      <div className="set__group">
        <h3 className="set__h">
          <Icon name="book" size={12} />
          Where your things are
        </h3>
        <details className="set__details">
          <summary>Data and keys on this machine</summary>
          <p className="set__prose">
            Threads, projects, and measured facts live in SQLite beside the
            engine. API keys are in this machine&rsquo;s keychain (Keys section).
            Attaching a folder records the path — nothing is copied away.
          </p>
        </details>
      </div>
    </>
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
