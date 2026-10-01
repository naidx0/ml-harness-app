// THE FACES, BUNDLED. §3.1's law — "a local-first product that blocks first
// paint on a CDN is contradicting itself" — forbade LINKING fonts, and the
// first Letter build obeyed it by naming faces nobody had installed, so every
// surface silently fell back to Segoe and the owner saw none of the book.
// Bundling is the answer the law allows: these imports resolve to woff2 files
// inside the build itself, no network request exists, and the faces render on
// a machine that has never seen them.
import '@fontsource/marcellus/400.css';
import '@fontsource/cormorant-garamond/500.css';
import '@fontsource/cormorant-garamond/500-italic.css';
import '@fontsource/cormorant-garamond/600-italic.css';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
/* 600 AND 700 ARE NOT DECORATION, THEY ARE THE FIX FOR SOFT NUMBERS. Max,
   2026-09-14: "make it all more HD, sometimes the text resolution looks
   blurry."

   MEASURED across every stylesheet: 13 rules set mono at weight 600 and one at
   700, against a family loaded at 400 and 500 only. When the requested weight
   has no cut, the browser SYNTHESISES the bold - it smears each glyph
   horizontally by a fraction of a pixel - and on Windows that lands as a
   soft, thick, slightly doubled edge. Every one of those 14 rules is a NUMBER
   or a verdict badge: `.evalrow__score`, `.fig__value`, `.rverdict__figure`,
   `.rrow__pct`, `.stamp__v`, `.proxy__v`, the verdict pill. They are the
   product's payload, the things the brand book says this face exists to be
   trusted about, and they were the blurriest text on the screen.

   Two real cuts cost two woff2 files and remove the synthesis entirely. */
import '@fontsource/ibm-plex-mono/600.css';
import '@fontsource/ibm-plex-mono/700.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { PaneWindow } from './components/PaneWindow';
import { StageWindow } from './components/StageWindow';
import './styles/tokens.css';
import './styles/base.css';

/* ONE PAGE, TWO WINDOWS. `?stage=<threadId>` is the detached instrument window
   (docs/PHASES.md, The Stage, size C): the same bundle, the same engine
   session, no chat box. The shell opens it as a second Tauri window; a browser
   opens it as a popup. Decided here, before any hook runs, so neither window
   pays for the other's state. */
const query = new URLSearchParams(window.location.search);
const stageThread = Number(query.get('stage'));

/* AND `?pane=<id>&thread=<id>` is a single pane in its own window, bound to
   the thread it was opened from and never re-pointed - see
   `components/PaneWindow.tsx` and `open_pane` in src-tauri/src/lib.rs. Read
   here, before any hook runs, for the reason the stage route gives: neither
   window should pay for the other's state. */
const pane = query.get('pane');
const paneThread = Number(query.get('thread'));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {Number.isFinite(stageThread) && stageThread > 0 ? (
      <StageWindow threadId={stageThread} />
    ) : pane && Number.isFinite(paneThread) && paneThread > 0 ? (
      <PaneWindow pane={pane} threadId={paneThread} />
    ) : (
      <App />
    )}
  </StrictMode>,
);
