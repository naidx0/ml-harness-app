/**
 * THE BUILDLOOP CHIP — no surprise auto-chain (CS8); CS15 sentence-case copy.
 *
 * `theBuildKeepsGoing` returns go:false whenever open steps remain and asks
 * the person to press Run the plan. These tests pin the chrome that follows,
 * not the old browser auto-loop that CS8 retired.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useCallback, useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { TheBuildWorksDown } from './TheBuildWorksDown';

afterEach(cleanup);

const ACTED = [{ kind: 'user' }, { kind: 'assistant' }, { kind: 'tool' }];
const STEPPED = '## Phase 1 - Data\n- [ ] Carve the eval set\n- [ ] Measure the baseline';

function Harness({
  items = ACTED,
  plan = STEPPED,
  onTurn,
}: {
  items?: { kind: string; text?: string }[];
  plan?: string;
  onTurn: () => void;
}) {
  const [running, setRunning] = useState(false);
  const onContinue = useCallback(async () => {
    onTurn();
    setRunning(true);
    await Promise.resolve();
    setRunning(false);
  }, [onTurn]);
  return (
    <TheBuildWorksDown
      threadId={1}
      mode="build"
      plan={plan}
      items={items}
      running={running}
      failed={false}
      lastEventId={0}
      onContinue={onContinue}
    />
  );
}

describe('CS8/CS15 — no auto-chain; Run the plan is the longrun door', () => {
  it('does not start turns by itself when steps are open', async () => {
    const onTurn = vi.fn();
    await act(async () => {
      render(<Harness onTurn={onTurn} />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(onTurn).not.toHaveBeenCalled();
    expect(screen.getByText(/2 open · press Run the plan/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Run the plan/i })).toBeTruthy();
  });

  it('Continue spends exactly one turn by hand', async () => {
    const onTurn = vi.fn();
    await act(async () => {
      render(<Harness onTurn={onTurn} />);
    });
    fireEvent.click(screen.getByRole('button', { name: /^Continue$/i }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(onTurn).toHaveBeenCalledTimes(1);
  });

  it('says so when the plan has no steps under its phases', async () => {
    const onTurn = vi.fn();
    await act(async () => {
      render(<Harness plan="## Phase 1 - Data" onTurn={onTurn} />);
    });
    expect(onTurn).not.toHaveBeenCalled();
    expect(screen.getByText(/no steps to work down/i)).toBeTruthy();
  });

  it('shows Working the plan copy while a turn is in flight', async () => {
    await act(async () => {
      render(
        <TheBuildWorksDown
          threadId={1}
          mode="build"
          plan={STEPPED}
          items={ACTED}
          running
          failed={false}
          lastEventId={0}
          onContinue={async () => {}}
        />,
      );
    });
    expect(screen.getByText(/Working the plan · 0 done, 2 left/)).toBeTruthy();
  });
});

describe('it draws nothing it has no business drawing', () => {
  it('is absent while planning', () => {
    const { container } = render(
      <TheBuildWorksDown
        threadId={1}
        mode="plan"
        plan={STEPPED}
        items={ACTED}
        running={false}
        failed={false}
        lastEventId={0}
        onContinue={async () => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('is absent when the thread has no plan', () => {
    const { container } = render(
      <TheBuildWorksDown
        threadId={1}
        mode="build"
        plan={null}
        items={ACTED}
        running={false}
        failed={false}
        lastEventId={0}
        onContinue={async () => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
