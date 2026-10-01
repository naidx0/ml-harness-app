/**
 * CS4 — Agents inspector pane: SubAgentBoard at full pane width, with packs
 * and last digest. Empty when nothing has been delegated yet.
 */

import { SubAgentBoard } from './SubAgentBoard';
import type { SubAgentRead } from '../lib/engine/subagents';

export function AgentsPane({
  read,
  onOpen,
  onStop,
}: {
  read: SubAgentRead;
  onOpen: (threadId: number) => void;
  onStop: (id: number) => void;
}) {
  if (!read.subagents.length) {
    return (
      <div className="planpane planpane--empty">
        <p>
          No sub-agents yet. When a Build turn hands a phase to a worker, it
          appears here with its status, aimed packs, and Stop — the same board
          that also sits at the foot of the transcript.
        </p>
      </div>
    );
  }

  return (
    <div className="agents-pane">
      <SubAgentBoard
        read={read}
        onOpen={onOpen}
        onStop={onStop}
        detailed
      />
    </div>
  );
}
