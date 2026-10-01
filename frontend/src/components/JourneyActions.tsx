/**
 * Journey report and export — Phase C/F surfaces wired into the shell.
 *
 * The engine serves a printable page, a self-describing JSON bundle, and — the
 * owner's direction — a route that writes both into the project's own folder:
 * "it should write all this journal stuff into this path workspace because
 * people can actually reference that."
 *
 * WHY THE SHELL SAVES TO THE WORKSPACE INSTEAD OF DOWNLOADING. A packaged
 * webview does not run browser downloads, so in the desktop app the download
 * button was the owner's "glitched" journal control: a click that produced
 * nothing findable. In the shell the same click now lands the report next to
 * the project's data, and the status line says the actual path it wrote.
 */

import { useCallback, useState } from 'react';
import {
  downloadThreadExport,
  saveThreadReport,
  threadReportUrl,
} from '../lib/engine/client';
import { hasNativeShell } from '../lib/engine/shell';
import { Icon } from './Icon';

export function JourneyActions({ threadId }: { threadId: number }) {
  const [busy, setBusy] = useState<'report' | 'export' | null>(null);
  const [note, setNote] = useState<{ text: string; failed: boolean } | null>(
    null,
  );

  const openReport = useCallback(async () => {
    setNote(null);
    setBusy('report');
    try {
      const url = await threadReportUrl(threadId);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (failure) {
      setNote({
        text: failure instanceof Error ? failure.message : String(failure),
        failed: true,
      });
    } finally {
      setBusy(null);
    }
  }, [threadId]);

  const saveExport = useCallback(async () => {
    setNote(null);
    setBusy('export');
    try {
      if (hasNativeShell()) {
        const outcome = await saveThreadReport(threadId);
        setNote({ text: outcome.detail, failed: false });
      } else {
        await downloadThreadExport(threadId);
      }
    } catch (failure) {
      setNote({
        text: failure instanceof Error ? failure.message : String(failure),
        failed: true,
      });
    } finally {
      setBusy(null);
    }
  }, [threadId]);

  return (
    <span className="journey-actions">
      <button
        type="button"
        className="iconbtn iconbtn--bordered"
        aria-label="View journey report"
        title="View journey report (opens printable page)"
        disabled={busy !== null}
        onClick={() => void openReport()}
      >
        <Icon name="book" />
      </button>
      {/* THE SAVE BUTTON IS GONE from the shell (2026-09-12, Max: "it should
          automatically save, you shouldn't have to even click that"): the
          build loop writes the report into the project's folder the moment
          every step is ticked - see TheBuildWorksDown. In a browser there is
          no folder to write to, so the download stays there and only there. */}
      {hasNativeShell() ? null : (
        <button
          type="button"
          className="iconbtn iconbtn--bordered"
          aria-label="Download journey export"
          title="Download journey export (JSON bundle with provenance)"
          disabled={busy !== null}
          onClick={() => void saveExport()}
        >
          <Icon name="download" />
        </button>
      )}
      {note ? (
        <span
          className="journey-actions__error"
          role="status"
          style={note.failed ? undefined : { color: 'var(--fits)' }}
        >
          {note.text}
        </span>
      ) : null}
    </span>
  );
}
