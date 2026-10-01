/**
 * One attempt at a better prompt, and whether it earned the crown.
 *
 * ══ WHAT THIS CARD IS FOR, IN ONE SENTENCE ═════════════════════════════════
 *
 * The eval bench can say two runs differ. Only this bench decides whether that
 * is enough to PROMOTE a prompt — and the moment worth designing for is the one
 * where it measures a fifteen-point gap and refuses.
 *
 * So the headline is not the score and not the delta. It is the crown: **was
 * this version made the one to beat, or not.** `champion_changed: false` beside
 * a real, measured, fifteen-point improvement is the entire product in one
 * boolean, and it is the thing a person scanning the thread must read first.
 *
 * ══ THE COMPARISON IS NOT REDRAWN HERE ═════════════════════════════════════
 *
 * `try_prompt` returns its pairing under `comparison`, and that value is an
 * `evals.compare()` payload — so `EvalCompareCard` draws it, unchanged. There
 * is one noise band, one paired strip and one definition of "resolved" in the
 * interface, because there is one in the engine.
 *
 * A second comparison layout for prompts would be a second chance to disagree
 * with the first about when a difference is real. `prompts.py` refuses that on
 * its own side — *"`attempt` never decides significance itself"* — and this
 * file refuses it on ours.
 *
 * ══ SIX VERDICTS, NONE OF THEM A FALLTHROUGH ═══════════════════════════════
 *
 * `first` and `no_evidence` and `different` are the ordinary three. The other
 * three are the ones a lesser surface drops: `incomplete` (the run hit its
 * deadline — and `prompts.py` marks it `ok: false`, which is why the reader
 * deliberately does not check `ok`), `not_comparable` (no shared graded rows),
 * and `different_models`. Each states its own true thing. None of them is red:
 * not one is a failure, and three of them are the bench declining to conclude,
 * which is the behaviour being paid for.
 */

import { useState } from 'react';
import type { CSSProperties } from 'react';
import type { PromptAttempt, PromptRefusal } from '../lib/engine/prompts';
import { failureModeWord } from '../lib/engine/evals';
import { Icon } from './Icon';
import { EvalCompareCard } from './EvalCard';
import { ProvenanceTag } from './primitives';

/** How each verdict reads, and the token it reads in.
 *
 *  ONLY `different` IS GREEN. Everything else is `--unknown` grey, because
 *  everything else is the bench not concluding — and Graphite page 13.5 §3 is
 *  explicit that grey is for an absence rather than a problem. Nothing here is
 *  `--wont` red: a prompt that did not win is not an error, and a run that ran
 *  out of clock is not one either. */
const VERDICT: Record<string, { word: string; token: string; says: string }> = {
  first: {
    word: 'First version',
    token: 'unknown',
    says: 'There was nothing to compare this against yet, so it becomes the one to beat.',
  },
  different: {
    word: 'Better',
    token: 'fits',
    says: 'The eval set could resolve this difference, and more rows improved than regressed.',
  },
  no_evidence: {
    word: 'No evidence',
    token: 'unknown',
    says: 'This eval set cannot tell the two versions apart, so nothing was promoted.',
  },
  incomplete: {
    word: 'Unfinished',
    token: 'unknown',
    says: 'The run stopped before it graded every row, so it has no score to compare.',
  },
  not_comparable: {
    word: 'Not comparable',
    token: 'unknown',
    says: 'The two versions share no graded row, so there is nothing to pair.',
  },
  different_models: {
    word: 'Different models',
    token: 'unknown',
    says: 'These two versions were scored on different models, so the difference is not the prompt.',
  },
};

export function PromptCard({ attempt }: { attempt: PromptAttempt }) {
  const [open, setOpen] = useState(true);
  const look = VERDICT[attempt.verdict] ?? {
    word: attempt.verdict,
    token: 'unknown',
    says: 'The bench returned a verdict this surface has no treatment for.',
  };

  return (
    <div className="card card--prompt" data-open={open}>
      <div className="card__head">
        <Icon name="skill" />
        <span className="card__kicker">Prompt</span>
        <span className="card__clip">{attempt.line.name}</span>
        <span className="promptver">v{attempt.variant.version}</span>
        <span className="card__headright">
          <ProvenanceTag tag="MEASURED" />
          <button
            type="button"
            className="iconbtn"
            aria-label={open ? 'Collapse this attempt' : 'Expand this attempt'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Icon name="chevright" size={14} rotate={open ? 90 : 0} />
          </button>
        </span>
      </div>

      {open ? (
        <div className="card__body">
          {/* ══ THE CROWN, AND IT IS THE HEADLINE ═══════════════════════════
              Not the score. A person scanning this thread is asking one
              question — did my change stick — and the honest answer is a
              boolean the bench already computed. */}
          <div className="crown" data-crowned={String(attempt.championChanged)}>
            <Icon name={attempt.championChanged ? 'check' : 'eye'} size={16} />
            <span className="crown__word">
              {attempt.championChanged
                ? `Version ${attempt.variant.version} is the new one to beat`
                : attempt.verdict === 'first'
                  ? `Version ${attempt.variant.version} is the one to beat`
                  : 'Not promoted'}
            </span>
            <span
              className="vpill vpill--sm"
              style={
                {
                  '--v-colour': `var(--${look.token})`,
                  '--v-wash': `var(--${look.token}-wash)`,
                  '--v-edge': `var(--${look.token}-edge)`,
                } as CSSProperties
              }
            >
              {look.word}
            </span>
          </div>

          {/* The rival that kept the crown, named. "Not promoted" without
              saying what still holds the title is half a sentence. */}
          {!attempt.championChanged && attempt.against ? (
            <p className="crown__holds">
              Version {attempt.against.version} is still the one to beat.
            </p>
          ) : null}

          <p className="card__text">{look.says}</p>

          {attempt.variant.changeNote ? (
            <div className="changenote">
              <span className="changenote__k">what changed</span>
              <span className="changenote__v">{attempt.variant.changeNote}</span>
            </div>
          ) : null}

          {/* The bucket a targeted change was aimed at, and what it did to it.
              The engine's own sentence — this surface has no opinion about
              whether fixing four of nine rows is good. */}
          {attempt.targeted ? (
            <p className="targeted" data-resolved={String(attempt.targeted.resolved)}>
              <Icon name="filter" size={13} />
              <span>
                <b>{failureModeWord(attempt.targeted.mode)}</b> was the target:{' '}
                {attempt.targeted.fixed} of {attempt.targeted.rows} fixed.
                {attempt.targeted.says ? ` ${attempt.targeted.says}` : ''}
              </span>
            </p>
          ) : null}

          {/* ONE COMPARISON COMPONENT IN THE PRODUCT. See the header. */}
          {attempt.comparison ? (
            <EvalCompareCard comparison={attempt.comparison} />
          ) : null}

          <PromptText attempt={attempt} />

          {/* A PROMPT THAT WINS IS NOT A MEASUREMENT THE GATES READ, and the
              engine says so in its own words rather than leaving the reader to
              assume a crown opened something. */}
          {attempt.measuredNothing ? (
            <p className="measurednothing">{attempt.measuredNothing}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** The prompt itself. Collapsed, because it is long and it is not the news. */
function PromptText({ attempt }: { attempt: PromptAttempt }) {
  const [open, setOpen] = useState(false);
  if (!attempt.variant.text) return null;
  return (
    <div className="runfacts" data-open={open}>
      <button
        type="button"
        className="runfacts__toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        <span>Version {attempt.variant.version} in full</span>
        <span className="runfacts__sum">
          {attempt.variant.author ? `by ${attempt.variant.author}` : null}
          {attempt.variant.exemplars > 0
            ? ` · ${attempt.variant.exemplars} exemplars`
            : null}
        </span>
      </button>
      {open ? <pre className="prompttext">{attempt.variant.text}</pre> : null}
    </div>
  );
}

/**
 * The prompt bench declining, drawn as an answer.
 *
 * Grey, never red, and the header above it says "Not run, and why" rather than
 * "Failed" — because in all three cases the bench did its job. It recognised a
 * prompt it had already scored and spent nothing; or it refused to score a
 * version against a different eval set, which is `evals.compare`'s
 * `different_eval_sets` argument one level up; or it was asked to build
 * exemplars out of failures before anything had failed.
 */
export function PromptRefusalCard({ refusal }: { refusal: PromptRefusal }) {
  const WORD: Record<string, string> = {
    nothing_changed: 'Nothing changed',
    different_instrument: 'Different instrument',
    no_failures_to_learn_from: 'Nothing to learn from yet',
  };
  return (
    <div className="card card--evalrefusal">
      <div className="card__head">
        <Icon name="info" />
        <span className="card__kicker">Prompt bench</span>
      </div>
      <div className="card__body">
        <div className="card__headline">
          <span
            className="vpill"
            style={
              {
                '--v-colour': 'var(--unknown)',
                '--v-wash': 'var(--unknown-wash)',
                '--v-edge': 'var(--unknown-edge)',
              } as CSSProperties
            }
          >
            {WORD[refusal.error] ?? refusal.error}
          </span>
        </div>
        <p className="card__text">{refusal.detail}</p>
      </div>
    </div>
  );
}
