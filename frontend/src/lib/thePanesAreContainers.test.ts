/**
 * THE PANES ARE CONTAINERS, AND THE RULES INSIDE THEM ASK THE PANE.
 *
 * Max: "when we have the different sections open side by side ... it all
 * condenses, some of the text starts stacking and overlapping."
 *
 * The overlap was never a width bug in any one row. It was a RULER bug: every
 * responsive rule in this product but two keyed off the viewport, and a pane
 * the person can drag has nothing to do with the viewport. A 1680px monitor
 * with the inspector at its 320px floor leaves 292px of card, and a
 * `@media (max-width: 900px)` sees 1680 and does nothing.
 *
 * ── WHY THIS IS A TEST AND NOT A COMMENT ──────────────────────────────────
 *
 * A `@container` query whose element has no `container-type` ancestor does not
 * error. It does not warn. It silently never matches — so deleting the one
 * declaration below would leave every rule this phase added looking present in
 * the file and doing nothing on screen, and no render test could see it: jsdom
 * does not do layout and `test.css` is `false` in this project's vitest config
 * by deliberate choice. The stylesheet is therefore read as TEXT, which is the
 * same thing `tests/test_the_stylesheets_parse.py` does and for the same
 * reason: it is the only way this suite can see a whole language the product
 * ships in.
 *
 * `?raw` rather than `node:fs` because `tsconfig.app.json` sets
 * `types: ["vite/client"]` and node's own types are not in scope — an import
 * of `node:fs` here fails `tsc -b`, and the build is part of the gate.
 */
import { describe, expect, it } from 'vitest';

import chatCss from '../styles/chat.css?raw';
import evalsCss from '../styles/evals.css?raw';
import planCss from '../styles/plan.css?raw';
import shellCss from '../styles/shell.css?raw';
import stageCss from '../components/Stage.css?raw';

/** Prose in this codebase has braces and selectors in it. Strip it first. */
const COMMENT = /\/\*[\s\S]*?\*\//g;

function withoutProse(sheet: string): string {
  return sheet.replace(COMMENT, '');
}

/**
 * The declarations of one rule, by selector. Good enough for a flat stylesheet
 * and honest about it: a selector nested inside `@container` is found by
 * searching the body after that at-rule instead (see `containerRule`).
 */
function ruleBody(sheet: string, selector: string): string {
  const body = withoutProse(sheet);
  const at = body.indexOf(`\n${selector} {`);
  expect(at, `${selector} is not in this stylesheet`).toBeGreaterThan(-1);
  const open = body.indexOf('{', at);
  const close = body.indexOf('}', open);
  return body.slice(open + 1, close);
}

describe('the pane bodies declare themselves containers', () => {
  it('the docked inspector card is an inline-size container', () => {
    expect(ruleBody(shellCss, '.inspector__card')).toContain(
      'container-type: inline-size',
    );
  });

  it('the popped-out pane body is an inline-size container', () => {
    expect(ruleBody(chatCss, '.panewindow__body')).toContain(
      'container-type: inline-size',
    );
  });

  it('the reading column is one too, for the starting prompts', () => {
    expect(ruleBody(shellCss, '.composer-dock__inner')).toContain(
      'container-type: inline-size',
    );
  });

  it('the Stage keeps the one it already had', () => {
    /* It is written inline on one line rather than as a block, so this asks the
       whole sheet rather than a rule body. Named here so that removing it goes
       red: three phases of container queries now sit inside it. */
    expect(withoutProse(stageCss)).toContain('.stage { container-type: inline-size; }');
  });
});

describe('the rows that overlapped now ask the card, not the window', () => {
  it('the starting prompts no longer stack on a 900px WINDOW', () => {
    /* The exact query this phase replaced. Narrow on purpose: `shell.css` has
       one other width media query (`.studio__tools` at 520px, a padding nudge
       on a phone) and this test does not pretend to have ruled on it. */
    expect(withoutProse(shellCss)).not.toContain('@media (max-width: 900px)');
  });

  it('the four rows that stacked have a container query', () => {
    for (const selector of ['.cost__row', '.sandbox__row', '.approval__fact', '.stepdetail__grid']) {
      expect(containerRuleFor(planCss, selector), `${selector} has no @container`).toBe(true);
    }
    expect(containerRuleFor(shellCss, '.subagent__open')).toBe(true);
    expect(containerRuleFor(shellCss, '.ctxrow__why')).toBe(true);
    expect(containerRuleFor(shellCss, '.suggestions')).toBe(true);
  });

  it('no fixed track is left without a minmax on the rows that collided', () => {
    /* A `@container` stack only helps below its threshold. Above it the row is
       still a grid, and a track that refuses to shrink is what put the text on
       top of the text in the first place. */
    expect(ruleBody(planCss, '.cost__row')).toContain(
      'minmax(0, 150px) minmax(0, auto) minmax(0, 1fr)',
    );
    expect(ruleBody(planCss, '.sandbox__row')).toContain('minmax(0, 150px) minmax(0, 1fr)');
    expect(ruleBody(planCss, '.approval__fact')).toContain('minmax(0, 96px) minmax(0, 1fr)');
    expect(ruleBody(planCss, '.stepdetail__grid')).toContain('minmax(0, 96px) minmax(0, 1fr)');
    expect(ruleBody(shellCss, '.subagent__open')).toContain('minmax(0, 72px)');
    expect(ruleBody(evalsCss, '.subtract')).toContain(
      'minmax(0, 4.5rem) minmax(0, auto) minmax(0, 1fr)',
    );
  });

  it('the lattice header clips instead of drawing over its neighbour', () => {
    const header = ruleBody(stageCss, '.lattice__hdr');
    expect(header).toContain('overflow: hidden');
    expect(header).toContain('text-overflow: ellipsis');
  });

  it('the glossary tooltip is bounded by its pane, not by the screen', () => {
    const sheet = withoutProse(stageCss);
    expect(sheet).toContain('max-width: min(240px, 92cqw)');
    expect(sheet).not.toContain('60vw');
  });
});

/** True when `selector` appears inside some `@container` block in `sheet`. */
function containerRuleFor(sheet: string, selector: string): boolean {
  const body = withoutProse(sheet);
  const blocks = body.split('@container').slice(1);
  return blocks.some((block) => {
    /* Only the first balanced block after the at-rule belongs to it. Depth is
       enough here: these queries hold one or two flat rules. */
    let depth = 0;
    for (let index = 0; index < block.length; index += 1) {
      if (block[index] === '{') depth += 1;
      else if (block[index] === '}') {
        depth -= 1;
        if (depth === 0) return block.slice(0, index).includes(selector);
      }
    }
    return false;
  });
}
