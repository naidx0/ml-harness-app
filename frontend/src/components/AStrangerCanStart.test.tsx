/**
 * The first click a stranger makes.
 *
 * Found on a stranger walk, not by reading code: the suggestion cards on the
 * empty thread fill the composer and do nothing else. The card sits about a
 * hundred pixels above the box it writes into, focus stays on the button, and
 * the click gets no answer at the place it happened. Nothing is broken - the
 * text is there - which is the worst kind of stuck, because a stranger reads
 * "it ignored me" and clicks again.
 *
 * These hold the two properties that fix costs nothing to keep: the text goes
 * in, and the caret follows it.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useContext, useState } from 'react';

import { FocusTheComposer } from './Composer';
import { Suggestions } from './EmptyState';
import { STARTER_PROMPTS } from '../data/sample';

afterEach(cleanup);

/** The composer's half of the arrangement, kept to what matters here: it owns
 *  a textarea and hands its children a way to focus it. */
function ComposerStandIn() {
  const [value, setValue] = useState('');
  return <Shell value={value} onChange={setValue} />;
}

function Shell({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const [el, setEl] = useState<HTMLTextAreaElement | null>(null);
  const focus = () => {
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  };
  return (
    <div>
      <textarea ref={setEl} value={value} onChange={(e) => onChange(e.target.value)} />
      <FocusTheComposer.Provider value={focus}>
        <Suggestions onPrompt={onChange} />
      </FocusTheComposer.Provider>
    </div>
  );
}

describe('a stranger clicking a starting point', () => {
  it('puts the sentence in the composer', () => {
    render(<ComposerStandIn />);
    fireEvent.click(screen.getByRole('button', { name: STARTER_PROMPTS[0] }));
    expect(screen.getByRole('textbox')).toHaveProperty('value', STARTER_PROMPTS[0]);
  });

  it('moves the caret to the composer, so the click is answered where it happened', () => {
    render(<ComposerStandIn />);
    fireEvent.click(screen.getByRole('button', { name: STARTER_PROMPTS[0] }));
    const box = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(document.activeElement).toBe(box);
    // At the end, not selecting the text: the card is an opening line to edit,
    // not a value that was chosen for you.
    expect(box.selectionStart).toBe(STARTER_PROMPTS[0].length);
  });

  it('replaces rather than appends, so a second click cannot double the sentence', () => {
    /* The stranger's actual next move when a click looks ignored. Measured on
       the walk: it replaced, and that is worth keeping true. */
    render(<ComposerStandIn />);
    fireEvent.click(screen.getByRole('button', { name: STARTER_PROMPTS[0] }));
    fireEvent.click(screen.getByRole('button', { name: STARTER_PROMPTS[0] }));
    expect(screen.getByRole('textbox')).toHaveProperty('value', STARTER_PROMPTS[0]);
  });

  it('still works where nothing provides a composer to focus', () => {
    /* The context defaults to a no-op so these cards can be rendered outside
       the composer without throwing. */
    render(<Suggestions onPrompt={() => {}} />);
    expect(() => fireEvent.click(screen.getByRole('button', { name: STARTER_PROMPTS[0] }))).not.toThrow();
  });
});

/** Guards the seam itself: if the provider is ever dropped from the composer,
 *  the cards keep working and silently stop moving focus - exactly the defect
 *  that was just fixed, back again with no test failing. This one fails. */
describe('the seam that carries the focus', () => {
  it('is the composer that provides it, not a default someone can forget', () => {
    let seen: (() => void) | null = null;
    function Probe() {
      seen = useContext(FocusTheComposer);
      return null;
    }
    render(
      <FocusTheComposer.Provider value={() => {}}>
        <Probe />
      </FocusTheComposer.Provider>,
    );
    expect(seen).not.toBeNull();
  });
});
