"use client";

import { useEffect, useRef } from "react";

import { CloseIcon } from "@/components/icons";
import type { IssueTerm } from "@/lib/types";

export function TermSheet({
  terms,
  onClose,
  title = "알아두면 좋은 용어",
}: {
  terms: IssueTerm[];
  onClose: () => void;
  title?: string;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="term-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="용어 설명"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="term-sheet__head">
          <h2>{title}</h2>
          <button
            aria-label="닫기"
            className="icon-btn"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            <CloseIcon />
          </button>
        </div>
        <ul className="term-sheet__list">
          {terms.map((term) => (
            <li key={term.name}>
              <strong>{term.name}</strong>
              <p>{term.definition}</p>
              {term.ai_generated && (
                <p className="term-sheet__provenance">
                  AI가 정리한 설명
                  {term.source_label ? ` · ${term.source_label}` : ""}
                </p>
              )}
              {(term.original_url || term.source_url) && (
                <a
                  className="term-sheet__source"
                  href={term.original_url ?? term.source_url ?? undefined}
                  rel="noreferrer"
                  target="_blank"
                >
                  한국은행 원문 보기
                  {term.source_page ? ` · ${term.source_page}쪽` : ""} ↗
                </a>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
