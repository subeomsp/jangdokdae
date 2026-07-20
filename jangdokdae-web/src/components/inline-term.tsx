import type { ReactNode } from "react";

import type { IssueTerm } from "@/lib/types";

interface Occurrence {
  index: number;
  alias: string;
  term: IssueTerm;
}

function findOccurrence(text: string, term: IssueTerm, fromIndex: number): Occurrence | null {
  const lowerText = text.toLocaleLowerCase();
  let best: Occurrence | null = null;
  for (const alias of term.aliases.length > 0 ? term.aliases : [term.name]) {
    const index = lowerText.indexOf(alias.toLocaleLowerCase(), fromIndex);
    if (
      index >= 0 &&
      (best === null || index < best.index || (index === best.index && alias.length > best.alias.length))
    ) {
      best = { index, alias, term };
    }
  }
  return best;
}

export function termAppearsInText(text: string, term: IssueTerm): boolean {
  return findOccurrence(text, term, 0) !== null;
}

export function renderParagraphWithTerms(
  text: string,
  terms: IssueTerm[],
  claimedTerms: Set<string>,
  onSelect: (term: IssueTerm) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    let next: Occurrence | null = null;
    for (const term of terms) {
      if (claimedTerms.has(term.name)) continue;
      const occurrence = findOccurrence(text, term, cursor);
      if (
        occurrence &&
        (next === null ||
          occurrence.index < next.index ||
          (occurrence.index === next.index && occurrence.alias.length > next.alias.length))
      ) {
        next = occurrence;
      }
    }

    if (next === null) {
      nodes.push(text.slice(cursor));
      break;
    }
    if (next.index > cursor) nodes.push(text.slice(cursor, next.index));

    const matchedText = text.slice(next.index, next.index + next.alias.length);
    nodes.push(
      <button
        aria-label={`${next.term.name} 용어 설명 열기`}
        className="inline-term"
        key={`${next.term.name}-${next.index}`}
        onClick={() => onSelect(next.term)}
        type="button"
      >
        {matchedText}
        <span aria-hidden="true" className="inline-term__tooltip" role="tooltip">
          <strong>{next.term.name}</strong>
          <span>{next.term.definition}</span>
          {next.term.source_label && (
            <small>AI 요약 · {next.term.source_label}</small>
          )}
        </span>
      </button>,
    );
    claimedTerms.add(next.term.name);
    cursor = next.index + next.alias.length;
  }
  return nodes;
}
