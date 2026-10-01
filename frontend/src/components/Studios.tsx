/**
 * The studios frame — the capability packs, shown to a person.
 *
 * A studio is a pack, and a pack is the first dotted segment of a capability
 * name a tool declared with `provides=`. `app/tools/blocks.py` is the argument
 * for that design; this component is the window into it, and it is a WINDOW and
 * not a MENU. Nothing here is clickable in the sense of switching the product
 * into a mode:
 *
 *   "Blocks scope what the model may CALL. They never scope what the harness
 *    IS." — app/tools/blocks.py
 *
 * Which studio is live on a turn is decided by the standing diagnosis before
 * the model speaks, and the transcript already draws that as a notice strip
 * (`lib/transcript.ts`, `blocks.changed`). If this card offered a picker it
 * would be the tabbed control panel `docs/VISION.md` names as the thing we are
 * not: "Unsloth Studio is good, it is free, and it is a control panel. It has
 * tabs." A person choosing their own studio is a person having to know the
 * answer before they ask the question.
 *
 * So the card answers one question — *what is in this harness, and what always
 * loads* — and every name in it comes from `GET /api/studios`, which the engine
 * derives from the registry. There is no list of packs or tools in this file.
 */

import { useState } from 'react';
import type { Studios } from '../lib/engine/types';
import { useStudios } from '../lib/useStudios';
import { Icon } from './Icon';
import { Strip } from './primitives';

export function StudiosCard() {
  const state = useStudios();

  if (state.status === 'loading') return <StudiosSkeleton />;
  if (state.status === 'error') return <StudiosUnread message={state.message} />;
  return <StudiosList studios={state.studios} />;
}

function StudiosList({ studios }: { studios: Studios }) {
  /* Ordered by the engine's own `packs` map — insertion order, which is core
     first and then the domain packs as `blocks.py` declares them. Sorting here
     alphabetically would throw away a fact the engine spent a paragraph on. */
  const names = Object.keys(studios.packs);
  const core = new Set(studios.core);
  const [open, setOpen] = useState<string | null>(null);
  const total = names.reduce(
    (count, name) => count + (studios.pack_index[name]?.length ?? 0),
    0,
  );

  return (
    <div className="studios">
      <div className="studios__head">
        <span className="studios__title">
          <Icon name="skill" size={13} />
          Studios
        </span>
        <span className="studios__count">
          {names.length} packs · {total} tools
        </span>
      </div>

      <ul className="studios__list">
        {names.map((name) => {
          const tools = studios.pack_index[name] ?? [];
          const expanded = open === name;
          return (
            <li className="studio" key={name}>
              <button
                type="button"
                className="studio__row"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : name)}
              >
                <span className="studio__name">{name}</span>
                {/* The chip's slot is held whether or not the pack is core, so
                    the descriptions line up in one column. Twelve rows where
                    three start 34px further right reads as three kinds of row
                    rather than one label on three of them. */}
                <span className="studio__slot">
                  {core.has(name) ? (
                    <span
                      className="studio__core"
                      title="loaded on every turn, whatever the diagnosis says"
                    >
                      core
                    </span>
                  ) : null}
                </span>
                <span className="studio__what" title={studios.packs[name]}>
                  {studios.packs[name]}
                </span>
                <span className="studio__n">{tools.length}</span>
              </button>

              {expanded ? (
                <ul className="studio__tools">
                  {tools.map((tool) => (
                    <li className="studio__tool" key={tool}>
                      {tool}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>

      {/* The honest sentence, and it is the one that keeps this from reading as
          navigation. */}
      <p className="empty__note">
        A studio is not something you switch to. The diagnosis picks which packs
        the model is handed on each turn, before it speaks, and the transcript
        says so when the set moves — every tool above stays clickable in the
        controls whatever loads. Read at <code>GET /api/studios</code>.
      </p>
    </div>
  );
}

function StudiosSkeleton() {
  /* The pack count is NOT known before the read — `blocks.PACKS` lives on the
     engine — so this shows a short neutral run of rows rather than pretending
     to know how many are coming. */
  return (
    <div className="studios" aria-busy="true">
      <div className="studios__head">
        <span className="studios__title">
          <Icon name="skill" size={13} />
          Studios
        </span>
      </div>
      <ul className="studios__list">
        {[0, 1, 2].map((i) => (
          <li className="studio" key={i}>
            <span className="studio__row studio__row--skeleton" />
          </li>
        ))}
      </ul>
    </div>
  );
}

function StudiosUnread({ message }: { message: string }) {
  return (
    <div className="studios">
      <div className="studios__head">
        <span className="studios__title">
          <Icon name="skill" size={13} />
          Studios
        </span>
      </div>
      <Strip tone="spills" icon="alert">
        {message}
      </Strip>
      <p className="empty__note">
        Nothing is listed, because the engine did not answer{' '}
        <code>GET /api/studios</code>. The packs are the engine&rsquo;s, so an
        invented list here would be a claim about a registry this page has not
        read.
      </p>
    </div>
  );
}
