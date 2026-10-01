/**
 * Every tool is also a control.
 *
 * `GET /api/tools` returns the SAME declaration the model is handed, described
 * for a person: label, group, verb, and the fields taken out of the identical
 * JSON Schema. `app/tools/registry.py`: "Adding a tool adds a button. Changing
 * a parameter changes the form." So nothing in this file has a list of tools
 * in it, and nothing in this file knows what any tool does. If it did, the two
 * faces could drift, and the half that drifted would be the one a user with a
 * text-only model depends on.
 *
 * `POST /api/tools/{name}` runs one. Two things about that route are worth
 * knowing before reading the UI:
 *
 * - **It writes nothing to the event log.** `run_tool_ep` calls the registry
 *   and returns; there is no `events.append`. A tool run from a button is
 *   therefore NOT part of the durable transcript, and the interface says so
 *   next to the result rather than letting it sit there looking like one.
 * - **428 is a real answer.** `approval="always"` tools refuse without a
 *   recorded approval, and the engine's message names the verb.
 */

import { useCallback, useEffect, useState } from 'react';
import { listTools, runTool } from './engine/client';
import type { ToolControl } from './engine/types';

export interface ToolsState {
  controls: ToolControl[];
  /** Groups in the order the engine returned them, which is `order` then
   *  name — the registry's own sort, not one invented here. */
  groups: { group: string; controls: ToolControl[] }[];
  byName: Map<string, ToolControl>;
  instructionSet: string;
  loading: boolean;
  error: string | null;
  run: (
    name: string,
    args: Record<string, unknown>,
    approved: boolean,
    /** Which conversation the facts belong to. `app/main.py`: "Facts measured
     *  without one are machine scope, which is right for hardware and wrong for
     *  anything about a project, so the interface sends it." An eval set counted
     *  in one thread must not open a gate in another, so a control run from
     *  inside a thread carries that thread. */
    threadId?: number | null,
  ) => Promise<{ ok: boolean; result: unknown; error: string | null }>;
}

export function useTools(): ToolsState {
  const [controls, setControls] = useState<ToolControl[]>([]);
  const [instructionSet, setInstructionSet] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    listTools()
      .then((catalogue) => {
        if (!live) return;
        setControls(catalogue.controls);
        setInstructionSet(catalogue.instruction_set);
      })
      .catch((failure: unknown) => {
        if (live) setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  const run = useCallback(
    async (
      name: string,
      args: Record<string, unknown>,
      approved: boolean,
      threadId: number | null = null,
    ) => {
      try {
        const outcome = await runTool(name, args, approved, threadId);
        /* A tool that ran and reported its own failure is a failed step, not a
           successful one — the same reading `app/conductor.py` does, so a
           button and a model call describe the same run the same way. */
        const failed =
          typeof outcome.result === 'object' &&
          outcome.result !== null &&
          (outcome.result as { ok?: unknown }).ok === false;
        return { ok: !failed, result: outcome.result, error: null };
      } catch (failure) {
        return {
          ok: false,
          result: null,
          error: failure instanceof Error ? failure.message : String(failure),
        };
      }
    },
    [],
  );

  const groups: { group: string; controls: ToolControl[] }[] = [];
  for (const control of controls) {
    const existing = groups.find((entry) => entry.group === control.group);
    if (existing) existing.controls.push(control);
    else groups.push({ group: control.group, controls: [control] });
  }

  return {
    controls,
    groups,
    byName: new Map(controls.map((control) => [control.name, control])),
    instructionSet,
    loading,
    error,
    run,
  };
}
