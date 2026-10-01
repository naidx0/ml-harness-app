/**
 * The small subset of Markdown a model's reply actually uses.
 *
 * WHY THIS EXISTS AND WHY IT IS SMALL. A connected model writes Markdown
 * whether or not we asked it to, so the choice is between rendering a subset
 * and printing `**this**` at the user. A library would be the obvious answer
 * and is not available: `AGENTS.md` says a new dependency gets its own step
 * and does not arrive as a side effect of a feature step.
 *
 * WHY IT IS SAFE. This module returns a *description* of blocks and spans.
 * Nothing here produces HTML, and the renderer builds React elements from it —
 * there is no `dangerouslySetInnerHTML` anywhere in this frontend. That is not
 * incidental: this repository has already shipped one live reflected XSS, and
 * the fix for the next one is to never have a string that becomes markup.
 *
 * WHAT IT DELIBERATELY DOES NOT DO. No tables, no links, no images, no inline
 * HTML, no nested lists. Anything it does not recognise is left as literal
 * text, which is the failure direction that loses nothing.
 */

export type Span =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'em'; text: string }
  | { kind: 'code'; text: string };

export type Block =
  | { kind: 'p'; spans: Span[] }
  | { kind: 'h'; level: 1 | 2 | 3; spans: Span[] }
  | { kind: 'ul'; items: Span[][] }
  | { kind: 'ol'; items: Span[][] }
  /** `- [ ]` and `- [x]`. A plan is a list of things to do and a checkbox
   *  is how that reads; rendered as literal text it read `- [ ] carve`. */
  | { kind: 'tasks'; items: { done: boolean; parked?: boolean; spans: Span[] }[] }
  /** `> ` - what `conductor._plan_note` and `_goal_note` quote WITH, so a
   *  plan carrying its own goal back showed the marks. */
  | { kind: 'quote'; spans: Span[] }
  /** `---` on its own line. A phased plan uses it between phases. */
  | { kind: 'hr' }
  | { kind: 'pre'; language: string; text: string };

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];

  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let tasks: { done: boolean; parked?: boolean; text: string }[] | null = null;
  /**
   * A blank line was seen and it is not yet known what it separated.
   *
   * THIS EXISTS BECAUSE OF A DEFECT SOMEBODY LOOKED AT. A blank line used to
   * close the open list outright, and a LOOSE list — items separated by blank
   * lines, which is ordinary Markdown and is what a model writes when the items
   * are sentences rather than words — became one `<ol>` per item. Every one of
   * them then started its own numbering, so a four-point answer rendered as
   * "1. 1. 1. 1." on screen. Caught by reading a real reply in the transcript,
   * not by any assertion about the parser.
   *
   * So a blank line now ends the PARAGRAPH and only defers the question about
   * the list: another item of the same kind continues it, and anything else
   * closes it.
   */
  let blankSeen = false;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push({ kind: 'p', spans: parseSpans(paragraph.join('\n')) });
    paragraph = [];
  };
  const flushList = () => {
    blankSeen = false;
    if (!list) return;
    blocks.push({
      kind: list.ordered ? 'ol' : 'ul',
      items: list.items.map(parseSpans),
    });
    list = null;
  };
  const flushTasks = () => {
    if (!tasks) return;
    blocks.push({
      kind: 'tasks',
      items: tasks.map((task) => ({ done: task.done, parked: task.parked, spans: parseSpans(task.text) })),
    });
    tasks = null;
  };
  const flushAll = () => {
    flushParagraph();
    flushTasks();
    flushList();
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];

    /* Fenced code. Everything up to the closing fence is literal, including
       anything that looks like other Markdown. An unterminated fence runs to
       the end of the text, which is what a half-streamed reply looks like. */
    const fence = /^```(\w*)\s*$/.exec(line.trim());
    if (fence) {
      flushAll();
      const language = fence[1] ?? '';
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index].trim())) {
        body.push(lines[index]);
        index += 1;
      }
      blocks.push({ kind: 'pre', language, text: body.join('\n') });
      continue;
    }

    if (line.trim() === '') {
      /* The paragraph is over either way. Whether the LIST is over depends on
         what comes next, so that question is deferred rather than answered
         wrongly here. */
      flushParagraph();
      blankSeen = true;
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      flushAll();
      blocks.push({
        kind: 'h',
        level: heading[1].length as 1 | 2 | 3,
        spans: parseSpans(heading[2]),
      });
      continue;
    }

    /* A RULE, which a phased plan puts between phases. Checked before the
       bullet rule because `---` also matches `[-*]` followed by nothing
       useful, and reading it as an empty bullet was what put a stray dot
       between every phase. */
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      flushAll();
      blocks.push({ kind: 'hr' });
      continue;
    }

    /* A CHECKBOX ITEM. Before the bullet rule, because `- [ ] x` is a
       bullet as far as that rule is concerned and would swallow the box. */
    const task = /^\s*[-*]\s+\[([ xX!])\]\s+(.*)$/.exec(line);
    if (task) {
      flushParagraph();
      flushList();
      if (!tasks) tasks = [];
      blankSeen = false;
      tasks.push({
        done: task[1].toLowerCase() === 'x',
        /* `[!]` is a step the run could not do - `planning.park_step`.
           Neither open nor done, and drawn as neither. */
        parked: task[1] === '!',
        text: task[2],
      });
      continue;
    }

    const quote = /^\s*>\s?(.*)$/.exec(line);
    if (quote) {
      flushAll();
      blocks.push({ kind: 'quote', spans: parseSpans(quote[1]) });
      continue;
    }

    /* Anything that is not another checkbox ends the checkbox list. */
    flushTasks();

    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      flushParagraph();
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      blankSeen = false;
      list.items.push(bullet[1]);
      continue;
    }

    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      flushParagraph();
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      blankSeen = false;
      list.items.push(numbered[1]);
      continue;
    }

    /* Anything that is not another item ends the list the blank line left
       open. */
    if (blankSeen) flushList();

    /* A plain line inside a list continues the last item rather than starting
       a paragraph in the middle of it. After a blank line it does not: the
       blank is what separates a continuation from a new paragraph, and the
       list has just been closed above. */
    if (list && list.items.length > 0) {
      list.items[list.items.length - 1] += ` ${line.trim()}`;
      continue;
    }

    paragraph.push(line);
  }

  flushAll();
  return blocks;
}

/** `**strong**` and `` `code` ``. Nothing else, and an unmatched marker stays
 *  as the character the model typed. */
export function parseSpans(text: string): Span[] {
  const spans: Span[] = [];
  /* ORDER IS THE WHOLE RULE HERE. `**bold**` is tried before `*em*` at
     every position, so the two-star form never loses its second star to
     the one-star form. `_em_` is accepted too and `[^_]` keeps it from
     eating snake_case_identifiers, which a plan is full of. */
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`|\*([^*\s][^*]*)\*|(?<![A-Za-z0-9_])_([^_\s][^_]*)_(?![A-Za-z0-9_])/g;
  let cursor = 0;

  for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
    if (match.index > cursor) {
      spans.push({ kind: 'text', text: text.slice(cursor, match.index) });
    }
    if (match[1] !== undefined) spans.push({ kind: 'strong', text: match[1] });
    else if (match[2] !== undefined) spans.push({ kind: 'code', text: match[2] });
    else spans.push({ kind: 'em', text: match[3] ?? match[4] ?? '' });
    cursor = match.index + match[0].length;
  }

  if (cursor < text.length) spans.push({ kind: 'text', text: text.slice(cursor) });
  return spans.length ? spans : [{ kind: 'text', text }];
}
