/**
 * The queue holds your words, in your order, one at a time.
 *
 * Max, 2026-09-14: *"also add a queueing prompt feature."*
 *
 * Three properties, and every one of them is a way a queue can lie about the
 * conversation. It must not MERGE two thoughts into one message, because that
 * changes what was asked. It must not REORDER them. And it must not start a
 * second turn while one is running, because a turn is one question and one
 * answer and the engine can run one at a time.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useQueuedPrompts } from './useQueuedPrompts';

describe('a queued prompt is still your own message', () => {
  it('sends nothing while the thread is busy', () => {
    const send = vi.fn();
    const { result } = renderHook(() => useQueuedPrompts(true, send));
    act(() => result.current.add('measure the baseline'));
    expect(send).not.toHaveBeenCalled();
    expect(result.current.waiting).toEqual(['measure the baseline']);
  });

  it('releases one the moment the thread is free, and only one', () => {
    const send = vi.fn();
    const { result, rerender } = renderHook(
      ({ busy }) => useQueuedPrompts(busy, send),
      { initialProps: { busy: true } },
    );
    act(() => {
      result.current.add('first');
      result.current.add('second');
    });
    rerender({ busy: false });

    /* ONE. Sending both would start two turns against a model that runs one,
       and the second answer would arrive with no question visible above it. */
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith('first');
    expect(result.current.waiting).toEqual(['second']);
  });

  it('keeps the order they were typed in', () => {
    const send = vi.fn();
    const { result, rerender } = renderHook(
      ({ busy }) => useQueuedPrompts(busy, send),
      { initialProps: { busy: true } },
    );
    act(() => {
      result.current.add('one');
      result.current.add('two');
      result.current.add('three');
    });
    rerender({ busy: false });
    act(() => rerender({ busy: true }));
    act(() => rerender({ busy: false }));
    act(() => rerender({ busy: true }));
    act(() => rerender({ busy: false }));

    expect(send.mock.calls.map((call) => call[0])).toEqual(['one', 'two', 'three']);
  });

  it('never merges two thoughts into one message', () => {
    const send = vi.fn();
    const { result, rerender } = renderHook(
      ({ busy }) => useQueuedPrompts(busy, send),
      { initialProps: { busy: true } },
    );
    act(() => {
      result.current.add('carve the eval set');
      result.current.add('then measure the baseline');
    });
    rerender({ busy: false });
    expect(send).toHaveBeenCalledWith('carve the eval set');
    expect(send).not.toHaveBeenCalledWith(
      expect.stringContaining('then measure the baseline'),
    );
  });

  it('lets you take one back before it goes', () => {
    const send = vi.fn();
    const { result, rerender } = renderHook(
      ({ busy }) => useQueuedPrompts(busy, send),
      { initialProps: { busy: true } },
    );
    act(() => {
      result.current.add('keep');
      result.current.add('a mistake');
    });
    act(() => result.current.drop(1));
    rerender({ busy: false });

    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith('keep');
  });

  it('ignores an empty line rather than queueing whitespace', () => {
    const send = vi.fn();
    const { result } = renderHook(() => useQueuedPrompts(true, send));
    act(() => {
      result.current.add('   ');
      result.current.add('');
    });
    expect(result.current.waiting).toEqual([]);
  });
});
