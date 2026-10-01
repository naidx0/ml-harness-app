/**
 * The model connection, from the browser's side.
 *
 * We ship no AI; the user lends us theirs. Everything here is about making
 * that exchange honest:
 *
 * - **The key is never in this file's state after the request.** It is passed
 *   once to `POST /api/providers` or `PATCH /api/providers/{id}`, which hands
 *   it to the OS keychain, and the local variable is dropped. It is never put
 *   in `localStorage`, never in a URL, never in an event payload, and it never
 *   comes back on any response — `_provider_public` returns `has_key`, a
 *   boolean, and nothing else.
 * - **`tool_calling` is three states, not a boolean.** `unknown` means nobody
 *   has probed, which is a different fact from "probed, and no". Collapsing
 *   them would let the interface claim a limitation it never measured.
 * - **Connecting and probing are separate.** The probe is a real network call
 *   to the model's own server and can be slow; a row that exists but has not
 *   been probed is a legitimate state and is shown as one.
 *
 * WHAT MAX'S FEEDBACK ADDED, AND WHY EACH ONE IS HERE RATHER THAN IN A
 * COMPONENT
 *
 * 1. **`connectLocal` — one click on a model this machine already has.** "The
 *    model thing should be like 'Connect the model'… Click on what you already
 *    have on this machine right away." One click has to do the whole
 *    create → activate → probe sequence, and it has to be idempotent: clicking
 *    the same model twice must not leave two identical rows behind. The reuse
 *    check is here rather than in the dialog because the dialog is not the only
 *    caller — Settings connects the same way — and a rule that lives in two
 *    components is a rule that will disagree with itself.
 * 2. **`keychain` — where a key would go, read before one is typed.** The
 *    engine already refuses a key it cannot protect, with a 503, one step
 *    after the user has typed it into a field. Reading `GET /api/keychain` up
 *    front is what lets the API path say what will happen to the key it is
 *    asking for. It carries no secret; see the route.
 * 3. **`update` and `remove` — because a settings surface that can only add is
 *    not a settings surface.** Both are engine routes now; the key deletion
 *    happens there, alongside the row, so a forgotten connection cannot leave
 *    an orphaned secret in the user's keychain.
 * 4. **`localModels` — the Ollama library, read once per page.** It was a
 *    private hook inside the connect dialog. Two surfaces need it now, and two
 *    independent effects reading the same daemon is the defect
 *    `lib/useLocalSpecs.ts` documents at length for `/local_specs`. Same
 *    answer: a module-level promise, resolved once, shared.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  activateProvider,
  createProvider,
  deleteProvider,
  getKeychain,
  listProviderPresets,
  listProviders,
  probeProvider,
  runTool,
  updateProvider,
} from './engine/client';
import type {
  Keychain,
  Provider,
  ProviderCreate,
  ProviderPreset,
  ProviderUpdate,
} from './engine/types';

/** One row of `list_local_models`. The geometry is read from the GGUF file by
 *  the tool, so `capabilities` is measured rather than assumed — a model can
 *  be known to support tool calling BEFORE it is connected. */
export interface LocalModel {
  name: string;
  family: string | null;
  params_b: number | null;
  capabilities: string[];
  on_disk_gb: number | null;
}

export type LocalModelsState =
  | { status: 'loading' }
  | { status: 'ok'; models: LocalModel[]; source: string }
  | { status: 'error'; message: string };

export interface ProvidersState {
  providers: Provider[];
  presets: ProviderPreset[];
  /** The one provider the engine will use. Exactly one, or none. */
  active: Provider | null;
  /** Where a key would go on this machine, or null while it is being read. */
  keychain: Keychain | null;
  loading: boolean;
  busy: string | null;
  error: string | null;
  refresh: () => Promise<void>;
  /** Create, activate and probe, in that order. Returns the finished row. */
  connect: (payload: ProviderCreate) => Promise<Provider | null>;
  /** The one-click path: connect a model already on this machine, reusing the
   *  row if this exact endpoint and model is already saved. */
  connectLocal: (model: string, endpoint?: ProviderPreset) => Promise<Provider | null>;
  use: (id: number) => Promise<void>;
  recheck: (id: number) => Promise<void>;
  update: (id: number, patch: ProviderUpdate) => Promise<Provider | null>;
  remove: (id: number) => Promise<boolean>;
  clearError: () => void;
}

/** The Ollama preset, which is the endpoint the one-click path connects to.
 *  Read off `GET /api/provider_presets` rather than written here, so the URL
 *  has one definition (`app/providers.PRESETS`) and this file cannot drift
 *  from it. The fallback is used only if that route fails. */
const OLLAMA_FALLBACK: ProviderPreset = {
  name: 'Ollama',
  base_url: 'http://127.0.0.1:11434',
  adapter: 'ollama',
  default_model: '',
  needs_key: false,
};

/**
 * WHAT A NEW LOCAL CONNECTION IS CALLED.
 *
 * Every one-click local connection used to be named after the ENDPOINT,
 * which is the same string for all of them. Max, with nine models set up:
 * *"let me add a nickname for each model just to make it very simple."* His
 * database had seven rows and six of them read `Ollama`.
 *
 * A connection to a local daemon is identified by its MODEL - the endpoint
 * is `localhost` for every one - so that is what it is named after. The tag
 * is dropped because `:latest` is on nearly all of them and a suffix every
 * row shares distinguishes nothing; a non-`latest` tag is kept, because then
 * it is the thing telling two rows apart. A namespaced id keeps only its
 * last segment, so `hf.co/prism-ml/Bonsai-27B-gguf` reads `Bonsai-27B-gguf`.
 *
 * It is a DEFAULT and not a rule. The name is an ordinary editable field on
 * the connection - this only decides what it says before anybody renames it.
 */
export function nameForALocalModel(model: string): string {
  const withoutTag = model.replace(/:latest$/i, '');
  const lastSegment = withoutTag.split('/').filter(Boolean).pop() ?? withoutTag;
  /* A BLANK LABEL IS WORSE THAN A REPEATED ONE. It is a row in the picker
     with nothing written on it, and no way to tell what activating it would
     do. An empty or all-whitespace model id is not a real model, but this
     runs on whatever the daemon reported and the picker still has to draw
     something, so it falls back through the raw id to a plain word. */
  return lastSegment.trim() || model.trim() || 'local model';
}

export function useProviders(): ProvidersState {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [keychain, setKeychain] = useState<Keychain | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProviders(await listProviders());
      setError(null);
    } catch (failure) {
      setError(message(failure));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    listProviderPresets()
      .then(setPresets)
      .catch(() => {
        /* Presets are a convenience. Losing them costs the user a typed URL,
           not the feature, so this failure is not worth a banner. */
      });
    getKeychain()
      .then(setKeychain)
      .catch(() => {
        /* Null stays null, and the surfaces that read it say nothing rather
           than claiming a machine has a keychain nobody asked about. */
      });
  }, [refresh]);

  const connect = useCallback(
    async (payload: ProviderCreate): Promise<Provider | null> => {
      setBusy('Saving the connection…');
      setError(null);
      try {
        const row = await createProvider(payload);
        setBusy('Making it the active one…');
        await activateProvider(row.id);
        setBusy(`Asking ${row.model} what it can do…`);
        const probed = await probeProvider(row.id);
        await refresh();
        return probed;
      } catch (failure) {
        setError(message(failure));
        /* The row may exist even when the key or the probe failed — a 503 from
           `POST /api/providers` means exactly that, and the engine says so.
           Re-reading the list is how the interface stays truthful about what
           is actually stored. */
        await refresh();
        return null;
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  /**
   * ONE CLICK, AND IT DOES NOT PILE UP ROWS.
   *
   * A model already on this machine needs no URL, no adapter choice and no
   * key, so the fast path asks for none of them. What it does need is to be
   * safe to press twice: the same endpoint, adapter and model is the same
   * connection, so an existing row is activated and re-probed rather than
   * duplicated. Without that, a user comparing two local models by clicking
   * back and forth ends up with a settings list of identical entries.
   */
  const connectLocal = useCallback(
    async (model: string, endpoint?: ProviderPreset): Promise<Provider | null> => {
      const target =
        endpoint ??
        presets.find((preset) => preset.adapter === 'ollama') ??
        OLLAMA_FALLBACK;
      const existing = providers.find(
        (row) =>
          row.model === model &&
          row.adapter === target.adapter &&
          row.base_url === target.base_url,
      );
      if (!existing) {
        return connect({
          /* The model, not the endpoint. See `nameForALocalModel`. */
          name: nameForALocalModel(model),
          base_url: target.base_url,
          model,
          adapter: target.adapter,
        });
      }
      setBusy('Switching…');
      setError(null);
      try {
        await activateProvider(existing.id);
        setBusy(`Asking ${model} what it can do…`);
        const probed = await probeProvider(existing.id);
        await refresh();
        return probed;
      } catch (failure) {
        setError(message(failure));
        await refresh();
        return null;
      } finally {
        setBusy(null);
      }
    },
    [connect, presets, providers, refresh],
  );

  const use = useCallback(
    async (id: number) => {
      setBusy('Switching…');
      setError(null);
      try {
        await activateProvider(id);
        await refresh();
      } catch (failure) {
        setError(message(failure));
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const recheck = useCallback(
    async (id: number) => {
      setBusy('Asking the model what it can do…');
      setError(null);
      try {
        await probeProvider(id);
        await refresh();
      } catch (failure) {
        setError(message(failure));
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  /**
   * Edit a saved connection.
   *
   * `patch.api_key` is dropped from this closure the moment the request is
   * made, exactly as `connect` drops it. LEAVING THE PROPERTY OFF is how a
   * form says "I have no key to send, leave the stored one alone" — the engine
   * distinguishes absent from empty, and a settings form has nothing to put
   * back because the engine never returns a key.
   */
  const update = useCallback(
    async (id: number, patch: ProviderUpdate): Promise<Provider | null> => {
      setBusy('Saving…');
      setError(null);
      try {
        const row = await updateProvider(id, patch);
        await refresh();
        return row;
      } catch (failure) {
        setError(message(failure));
        await refresh();
        return null;
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: number): Promise<boolean> => {
      setBusy('Forgetting the connection…');
      setError(null);
      try {
        await deleteProvider(id);
        await refresh();
        return true;
      } catch (failure) {
        setError(message(failure));
        await refresh();
        return false;
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  return {
    providers,
    presets,
    active: providers.find((row) => row.is_active === 1) ?? null,
    keychain,
    loading,
    busy,
    error,
    refresh,
    connect,
    connectLocal,
    use,
    recheck,
    update,
    remove,
    clearError: () => setError(null),
  };
}

/* ── The models already on this machine ────────────────────────────────────
   `list_local_models` reads the local Ollama daemon and the real geometry out
   of each GGUF file. "A model that is already here needs no download and is
   proven to run, which is the strongest fit evidence available" — the tool's
   own words, and the reason this is the fast path rather than a shortcut.

   Cached at module level for the same reason `useLocalSpecs` is: the connect
   dialog and the settings surface both read it, and two components remounting
   should not mean two round trips to a daemon for a list that has not changed.
   `forgetLocalModels()` is what a re-scan control calls. */

let cachedModels: Promise<LocalModelsState> | null = null;
let settledModels: LocalModelsState | null = null;
/** Every mounted `useLocalModels`, so a re-scan reaches all of them. A cache
 *  that can be cleared but not un-cleared is a re-scan button that does
 *  nothing until the component happens to remount, which is worse than no
 *  button: it reports a reading it did not take. */
const modelListeners = new Set<() => void>();

function readLocalModels(): Promise<LocalModelsState> {
  if (cachedModels) return cachedModels;
  cachedModels = runTool('list_local_models')
    .then((outcome): LocalModelsState => {
      const result = outcome.result as {
        ok?: boolean;
        models?: LocalModel[];
        source?: string;
        error?: string;
        detail?: string;
      };
      if (result?.ok === false) {
        return {
          status: 'error',
          message: result.detail ?? result.error ?? 'the tool reported a failure',
        };
      }
      return {
        status: 'ok',
        models: result?.models ?? [],
        source: result?.source ?? '',
      };
    })
    .catch(
      (failure: unknown): LocalModelsState => ({
        status: 'error',
        message: failure instanceof Error ? failure.message : String(failure),
      }),
    )
    .then((state) => {
      settledModels = state;
      return state;
    });
  return cachedModels;
}

export function useLocalModels(): LocalModelsState {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<LocalModelsState>(
    () => settledModels ?? { status: 'loading' },
  );

  useEffect(() => {
    const bump = () => setNonce((value) => value + 1);
    modelListeners.add(bump);
    return () => {
      modelListeners.delete(bump);
    };
  }, []);

  useEffect(() => {
    if (settledModels) {
      setState(settledModels);
      return;
    }
    setState({ status: 'loading' });
    let live = true;
    void readLocalModels().then((next) => {
      if (live) setState(next);
    });
    return () => {
      live = false;
    };
  }, [nonce]);

  return state;
}

/** Drop the reading and ask again, everywhere it is on screen. For the re-scan
 *  control, and for after a user has pulled a model in another window. */
export function forgetLocalModels(): void {
  cachedModels = null;
  settledModels = null;
  for (const notify of modelListeners) notify();
}

function message(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}
