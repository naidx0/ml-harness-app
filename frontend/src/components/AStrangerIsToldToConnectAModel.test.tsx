/**
 * The one thing a stranger must be told, and the one place they will be.
 *
 * ## Measured, not imagined
 *
 * 2026-09-10, Windows Sandbox, nothing on the machine but the installer. The
 * install succeeded, the engine published itself, `GET /health` answered HTTP
 * 200 with every check green — and `/api/providers` returned an **empty list**.
 * A working product that could not diagnose anything, on a machine that had
 * been told it was ready.
 *
 * That run drove the ENGINE over HTTP and never opened the window, so it could
 * not see what the window says. This is what the window says, held in place:
 * the composer is the first screen, the banner sits above it before any
 * message, and with no connection it says so and offers the way out.
 *
 * ## Why the real `Composer` and not a stand-in
 *
 * `AStrangerCanStart.test.tsx` beside this file uses a stand-in, because what
 * it holds is a relationship between two components. What THIS holds is that a
 * sentence reaches the screen at all — and a stand-in that renders the banner
 * would prove the banner renders, which was never in doubt. The defect class
 * here is "the composition dropped it", so the composition is what renders.
 *
 * The heavy hooks inside `Composer` reach the engine and there is none in
 * jsdom; every one of them catches its own failure, so they settle into their
 * "could not read" states and say nothing about a model.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { Composer } from './Composer';
import type { Provider } from '../lib/engine/types';

afterEach(cleanup);

const NOTHING = async () => ({ ok: false, result: null, error: 'no engine in jsdom' });

function draw(overrides: {
  provider?: Provider | null;
  providersLoading?: boolean;
  onConnect?: () => void;
  onControls?: () => void;
}) {
  return render(
    <Composer
      workspace={null}
      onAssignFolder={() => {}}
      value=""
      onChange={() => {}}
      onSend={() => {}}
      mode="build"
      permission="ask"
      plan={null}
      items={[]}
      onThreadChanged={() => {}}
      onConnect={overrides.onConnect ?? (() => {})}
      onControls={() => {}}
      runTool={NOTHING}
      threadId={null}
      provider={overrides.provider ?? null}
      providers={overrides.provider ? [overrides.provider] : []}
      onUseProvider={async () => {}}
      presetNames={['Ollama']}
      onSetEffort={async () => {}}
      providersLoading={overrides.providersLoading ?? false}
      turn="idle"
      error={null}
    />,
  );
}

/** A connected, tool-calling model. Only the fields the banner reads matter,
 *  and they are spelled out rather than cast from `{}` so a field the banner
 *  starts reading tomorrow fails to compile here rather than silently
 *  arriving as undefined. */
const CONNECTED: Provider = {
  id: 1,
  name: 'Ollama',
  base_url: 'http://127.0.0.1:11434',
  model: 'granite4-hermes:latest',
  effort: 'default',
  adapter: 'ollama',
  kind: 'local',
  tool_calling: 'yes',
  capability_detail: 'reported by the Ollama server for this model',
  ctx_len: 8192,
  /* `measured`, lower case. `WireProvenance` has always been lower case and
     `tsc` has always said so; vitest does not type-check, so this fixture ran
     green for as long as it existed while `npm run build` was red. Found on
     2026-09-10 by running `tsc` in this checkout for the first time. */
  ctx_len_provenance: 'measured',
  is_active: 1,
  created_at: '2026-09-10T00:00:00Z',
  has_key: false,
};

describe('the first screen, with nothing connected', () => {
  it('says a model is needed, in the product\u2019s own terms', () => {
    draw({ provider: null });
    expect(screen.getByText(/No model connected/i)).toBeTruthy();
    /* NOT "configure a provider". The sentence has to explain why there is
       nothing to configure out of the box: we ship no AI. */
    expect(screen.getByText(/thinks with a model you lend it/i)).toBeTruthy();
  });

  it('offers both roads in one line, so neither is a dead end', () => {
    draw({ provider: null });
    const out = screen.getByRole('button', {
      name: /Pick one on this machine, or connect an API key/i,
    });
    expect(out).toBeTruthy();
  });

  it('the way out is wired, not decorative', () => {
    /* THE DEFECT THIS IS FOR. A banner that names the problem and whose button
       does nothing is worse than no banner: it spends the one moment the person
       is willing to act. */
    const opened = vi.fn();
    draw({ provider: null, onConnect: opened });
    fireEvent.click(
      screen.getByRole('button', { name: /Pick one on this machine/i }),
    );
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it('the model selector reads "Connect a model" rather than a name', () => {
    /* The second door, and the one a person who dismissed the banner will look
       for. It must not read as a chosen-model chip when nothing is chosen. */
    draw({ provider: null });
    expect(screen.getByText('Connect a model')).toBeTruthy();
  });

  it('says nothing about a missing model while it is still looking', () => {
    /* "Not read yet" and "read, and there is none" are different facts, and
       the first must not be printed as the second. A banner that accuses the
       machine during the load flickers on every page open for someone who
       does have a model connected. */
    draw({ provider: null, providersLoading: true });
    expect(screen.queryByText(/No model connected/i)).toBeNull();
    expect(screen.getByText(/Checking what this machine is connected to/i)).toBeTruthy();
  });
});

describe('the first screen, with a model connected', () => {
  it('drops the banner entirely and names the model', () => {
    /* The row has to be able to go quiet, or it is a permanent scold. */
    draw({ provider: CONNECTED });
    expect(screen.queryByText(/No model connected/i)).toBeNull();
    expect(screen.getByText(CONNECTED.model)).toBeTruthy();
  });

  it('warns when the connected model cannot call tools', () => {
    /* Connected is not the same as usable, and this is the single most
       confusing state a new person can land in: the chat answers, and nothing
       it promises to do happens. */
    draw({ provider: { ...CONNECTED, tool_calling: 'no' } });
    expect(screen.getByText(/can.{0,3}t call tools/i)).toBeTruthy();
    expect(
      screen.getByRole('button', { name: /Connect a tool-calling model/i }),
    ).toBeTruthy();
    expect(
      screen.getByRole('button', { name: /click the tools yourself/i }),
    ).toBeTruthy();
  });

  it('does not warn when nobody has asked the model what it can do', () => {
    /* Three states, not two. `unknown` means unprobed, and printing it as "no"
       would claim a limitation this product never measured. */
    draw({ provider: { ...CONNECTED, tool_calling: 'unknown' } });
    expect(screen.queryByText(/can.{0,3}t call tools/i)).toBeNull();
  });

  it('never warns about the QUALITY of an answer that already arrived', () => {
    /* THE FOURTH STATE IS GONE, 2026-09-14, and this is what replaced five
       tests of it. Max: "remove the failed or live AI status symbol as well
       please."

       What it reported was real and well measured - a daemon saying
       `tool_calling: "yes"`, a confident plan naming these tools in prose, and
       `tool_calls_json` null, on a 0.5B, by ML BUILD on 2026-09-10. What it was
       not is a thing to hang over the chat box every turn. The three states
       this file still pins are about a CONNECTION a person must fix before
       anything works at all; that one was about an answer that already
       arrived, which the transcript shows better than a strip can - the turn is
       right there, with its tool rows or without them.

       Asserted ABSENT rather than deleted, so the banner cannot quietly come
       back: `saidNothing` is not a prop any more, and no shape of provider
       makes this row speak about tool silence. */
    for (const provider of [CONNECTED, { ...CONNECTED, tool_calling: 'unknown' as const }]) {
      cleanup();
      draw({ provider });
      expect(screen.queryByText(/called none on/i)).toBeNull();
      expect(screen.queryByText(/reported that it can/i)).toBeNull();
      expect(screen.queryByText(/describing work rather than doing it/i)).toBeNull();
    }
  });

  it('says the probe answer when the probe said no', () => {
    /* `no` is a MEASURED fact about the model and the one thing in this row a
       person has to act on before anything works. */
    draw({ provider: { ...CONNECTED, tool_calling: 'no' } });
    expect(screen.getByText(/can.{0,3}t call tools/i)).toBeTruthy();
    expect(screen.queryByText(/called none on/i)).toBeNull();
  });
});
