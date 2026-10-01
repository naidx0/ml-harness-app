/**
 * The empty thread, drawn to Graphite.
 *
 * "Codex centres a small mark, a modest heading and a quiet selector, then puts
 * three suggestion cards above the composer. Graphite keeps that shape and adds
 * the one thing this product must say first: what it already measured about
 * this machine, tagged. It is the cheapest trust signal available, and the
 * whole differentiator is that we answer by inspecting rather than by asking."
 *
 * The heading is 20px and the mark is a 34px rounded-square outline holding one
 * 18px glyph. Nothing here is a hero. Everything about this screen is
 * calibrated to say *this is a tool you already have open* rather than *this is
 * a product you are being sold* — which is why the old 17px "Here's what I can
 * see." headline, its 48px padding and its glass card are gone.
 *
 * "Any fact whose tag would be DEFAULTED is not shown on this card at all — a
 * defaulted value inside the demonstration of measuring is worse than a
 * shorter card."
 *
 * Every number comes from `GET /local_specs` on the running engine and carries
 * the provenance tag the engine gave it. Nothing here is typed in.
 */

import type { LocalSpecs, LocalSpecsField } from '../lib/engine/types';
import { displayTag, withUnit } from '../lib/format';
import { useLocalSpecs } from '../lib/useLocalSpecs';
import { useContext } from 'react';

import { FocusTheComposer } from './Composer';
import { Icon, type IconName } from './Icon';
import { StudiosCard } from './Studios';
import { Button, ProvenanceTag, Strip } from './primitives';
import { STARTER_PROMPTS } from '../data/sample';

export function EmptyState() {
  const state = useLocalSpecs();

  return (
    <div className="empty">
      <div className="empty__inner">
        <span className="markglyph">
          <Icon name="mark" size={18} />
        </span>

        {/* 20px, weight 600, -.018em. Modest, not a hero. */}
        <div className="empty__title">Let&rsquo;s build</div>

        {state.status === 'loading' ? <HardwareSkeleton /> : null}
        {state.status === 'error' ? <DetectionFailed message={state.message} /> : null}
        {state.status === 'ok' ? <HardwareCard specs={state.specs} /> : null}

        {/* What this machine has, then what this harness has. Both are read
            rather than typed, and both are on the first screen for the same
            reason: "the whole differentiator is that we answer by inspecting
            rather than by asking." */}
        <StudiosCard />
      </div>
    </div>
  );
}

/**
 * The three suggestion cards Graphite puts above the composer — four here, and
 * the count is the one place this screen departs from the book. See the note on
 * `.suggestions` in shell.css.
 *
 * "They are real starting points in the product's own voice, and the first one
 * is deliberately the one that might end in 'don't'."
 */
const PROMPT_ICON: readonly IconName[] = ['dataset', 'gpu', 'chart', 'gauge'];

export function Suggestions({ onPrompt }: { onPrompt: (text: string) => void }) {
  /* The card writes into the composer; this puts the caret there too. Without
     it the click has no visible answer at the place it happened - see the note
     on `FocusTheComposer`. */
  const focusComposer = useContext(FocusTheComposer);
  return (
    <div className="suggestions" data-count={STARTER_PROMPTS.length}>
      {STARTER_PROMPTS.map((prompt, index) => (
        <button
          key={prompt}
          type="button"
          className="suggest"
          onClick={() => {
            onPrompt(prompt);
            focusComposer();
          }}
        >
          <span className="suggest__glyph">
            <Icon name={PROMPT_ICON[index] ?? 'gauge'} />
          </span>
          <span className="suggest__text">{prompt}</span>
        </button>
      ))}
    </div>
  );
}

/* ── The card ───────────────────────────────────────────────────────────── */

function HardwareCard({ specs }: { specs: LocalSpecs }) {
  const rows = buildRows(specs);
  const shown = rows.filter((row) => row.tag !== 'DEFAULT' && row.value !== null);
  const withheld = rows.filter((row) => row.tag === 'DEFAULT' || row.value === null);

  return (
    <div className="empty__card">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {shown.map((row) => (
          <div className="kvrow" style={{ height: 22 }} key={row.field}>
            <span className="kvrow__k" style={{ flex: '0 0 82px' }}>
              {row.label}
            </span>
            <span className="kvrow__v">
              {row.value}
              {row.unit ? <span className="kvrow__unit"> {row.unit}</span> : null}
            </span>
            <span className="kvrow__t">
              <ProvenanceTag tag={row.tag} />
            </span>
          </div>
        ))}
      </div>

      {withheld.length > 0 ? (
        <p className="empty__note">
          Not shown, because nothing measured it:{' '}
          {withheld.map((row) => row.label).join(', ')}.
        </p>
      ) : null}

      {specs.warnings.length > 0 ? (
        <div style={{ marginTop: 'var(--sp-8)' }}>
          {specs.warnings.map((warning) => (
            <Strip key={warning} tone="spills" icon="alert">
              {warning}
            </Strip>
          ))}
        </div>
      ) : null}

      {/* "The 'what that means' line is generated, never written... If the
          engine cannot produce the sentence, the card shows the facts and no
          interpretation, which is still a demonstration that we looked."
          `app/feasibility.py` exists but is served by no route, so there is no
          sentence to render and none is invented. */}
      <p className="empty__note">
        What this machine can run and train is not shown, because nothing
        computed it — the estimator in <code>app/feasibility.py</code> is served
        by no HTTP route yet. Every figure above was read at{' '}
        <code>GET /local_specs</code>
        {sourcesLine(specs)}
      </p>
    </div>
  );
}

interface Row {
  field: LocalSpecsField;
  label: string;
  value: string | null;
  unit: string | null;
  tag: ReturnType<typeof displayTag>;
}

function buildRows(specs: LocalSpecs): Row[] {
  const vram = withUnit(specs.vram_gb, 'GB');
  const ram = withUnit(specs.ram_gb, 'GB');
  const disk = withUnit(specs.disk_free_gb, 'GB');

  return [
    {
      field: 'gpu_name',
      label: 'GPU',
      value: specs.gpu_name,
      unit: null,
      tag: displayTag(specs.provenance.gpu_name),
    },
    {
      field: 'vram_gb',
      label: 'VRAM',
      value: vram?.value ?? null,
      unit: vram?.unit ?? null,
      tag: displayTag(specs.provenance.vram_gb),
    },
    {
      field: 'ram_gb',
      label: 'RAM',
      value: ram?.value ?? null,
      unit: ram?.unit ?? null,
      tag: displayTag(specs.provenance.ram_gb),
    },
    {
      /* The free-disk figure is a SEPARATE reading from RAM. The engine reads
         it with shutil.disk_usage on the model cache volume. */
      field: 'disk_free_gb',
      label: 'Free disk',
      value: disk?.value ?? null,
      unit: disk?.unit ?? null,
      tag: displayTag(specs.provenance.disk_free_gb),
    },
    {
      field: 'os',
      label: 'System',
      value: specs.os,
      unit: null,
      tag: displayTag(specs.provenance.os),
    },
  ];
}

function sourcesLine(specs: LocalSpecs): string {
  const gpuSource = specs.sources.gpu_name;
  return gpuSource ? `, the graphics card via “${gpuSource}”.` : '.';
}

/* ── States ─────────────────────────────────────────────────────────────── */

/** "detecting (skeleton rows at the known row count, never a spinner)". The
 *  row count is known — app/hwdetect.py REQUIRED_FIELDS. */
function HardwareSkeleton() {
  return (
    <div className="empty__card" aria-busy="true">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {[0, 1, 2, 3, 4].map((i) => (
          <div className="kvrow" style={{ height: 22 }} key={i}>
            <span
              style={{
                display: 'block',
                height: 'var(--t-11)',
                width: '64px',
                background: 'var(--surface-3)',
                borderRadius: 'var(--r-4)',
              }}
            />
            <span
              style={{
                display: 'block',
                height: 'var(--t-11)',
                width: '96px',
                background: 'var(--surface-3)',
                borderRadius: 'var(--r-4)',
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The `detection failed` state, with the sentence the design system specifies
 *  verbatim, plus the reason the request failed so the user can act on it. */
function DetectionFailed({ message }: { message: string }) {
  return (
    <div className="empty__card">
      <p className="empty__body" style={{ marginBottom: 'var(--sp-8)' }}>
        I couldn&rsquo;t find a graphics card. That might mean you don&rsquo;t
        have one, or that the driver isn&rsquo;t installed. Either way I&rsquo;ll
        plan for CPU until we know.
      </p>
      <Strip tone="spills" icon="alert">
        {message}
      </Strip>
      <div className="rowgap-6" style={{ marginTop: 'var(--sp-8)' }}>
        <Button kind="ghost" small icon="gpu">
          Tell me what you have
        </Button>
        <Button kind="ghost" small icon="refresh">
          Plan for CPU
        </Button>
      </div>
    </div>
  );
}
