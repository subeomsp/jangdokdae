"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { BottomBar } from "@/components/bottom-bar";
import { Brand } from "@/components/brand";
import { ArrowLeftIcon } from "@/components/icons";
import { renderParagraphWithTerms } from "@/components/inline-term";
import { TermSheet } from "@/components/term-sheet";
import { ApiError, getIssue } from "@/lib/api";
import type { IssueDetail, IssueTerm } from "@/lib/types";

function formatIssueDate(createdAt: string): string {
  const date = createdAt.slice(0, 10);
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date(`${date}T00:00:00+09:00`));
}

export function ArchiveReader({ issueId }: { issueId: number }) {
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [selectedTerm, setSelectedTerm] = useState<IssueTerm | null>(null);
  const [termsOpen, setTermsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getIssue(issueId)
      .then((issue) => {
        if (active) setDetail(issue);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof ApiError
              ? reason.message
              : "서버에 연결하지 못했어요. 네트워크를 확인한 뒤 다시 시도해주세요.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [issueId]);

  if (error && !detail) {
    return (
      <main className="shell">
        <header className="topbar">
          <Brand compact />
          <Link className="topbar__link" href="/archive">지난 이슈</Link>
        </header>
        <section className="state-block">
          <h1>이슈를 열지 못했어요.</h1>
          <p>{error}</p>
          <Link className="btn btn--primary" href="/archive">보관함으로 돌아가기</Link>
        </section>
      </main>
    );
  }

  if (!detail) {
    return (
      <main className="shell">
        <header className="topbar"><Brand compact /></header>
        <div className="reader-skeleton">
          <div className="skeleton reader-skeleton__kicker" />
          <div className="skeleton reader-skeleton__title" />
          <div className="skeleton reader-skeleton__title reader-skeleton__title--short" />
          <div className="skeleton reader-skeleton__body" />
          <div className="skeleton reader-skeleton__body" />
        </div>
      </main>
    );
  }

  const claimedTerms = new Set<string>();

  return (
    <main className="shell">
      <header className="reader-topbar archive-reader-topbar">
        <Link aria-label="지난 이슈로 돌아가기" className="icon-btn" href="/archive">
          <ArrowLeftIcon />
        </Link>
        <span className="archive-reader-topbar__brand"><Brand compact /></span>
        {detail.terms.length > 0 ? (
          <button className="reader-topbar__terms" onClick={() => setTermsOpen(true)} type="button">
            용어 {detail.terms.length}
          </button>
        ) : (
          <span className="reader-topbar__spacer" aria-hidden="true" />
        )}
      </header>

      <article className="archive-reader">
        <header className="archive-reader__head">
          <p className="step__kicker">지난 이슈 · {formatIssueDate(detail.created_at)}</p>
          <p className="step__meta">{detail.category}</p>
          <h1>{detail.title}</h1>
          <p className="step__teaser">{detail.teaser}</p>
          <p className="step__stats">기사 {detail.article_count}개 · 다시 읽기</p>
          {detail.pain_hook && (
            <aside className="reader-lens" aria-label="주린이 필터">
              <p className="reader-lens__label">주린이 필터</p>
              <p className="reader-lens__title">이 이슈는 이 질문부터 풀어볼게요.</p>
              <p className="reader-lens__copy">{detail.pain_hook}</p>
            </aside>
          )}
        </header>

        {detail.cards.map((card, cardIndex) => (
          <section className="archive-reader__card" key={`${card.head}-${cardIndex}`}>
            <p className="step__num" aria-hidden="true">{cardIndex + 1}</p>
            <h2>{card.head}</h2>
            {card.question && (
              <p className="step__question">
                <span>먼저 확인할 것</span>
                {card.question}
              </p>
            )}
            {card.paragraphs.map((paragraph, paragraphIndex) => (
              <p className="step__para" key={paragraphIndex}>
                {renderParagraphWithTerms(
                  paragraph,
                  detail.terms,
                  claimedTerms,
                  setSelectedTerm,
                )}
              </p>
            ))}
          </section>
        ))}

        {detail.sources.length > 0 && (
          <details className="sources archive-reader__sources">
            <summary>참고한 기사 {detail.sources.length}개</summary>
            <ul>
              {detail.sources.map((source) => (
                <li key={source.id}>
                  <a href={source.url} rel="noreferrer" target="_blank">
                    <span className="sources__outlet">{source.news_source}</span>
                    <span className="sources__title">{source.title}</span>
                  </a>
                </li>
              ))}
            </ul>
          </details>
        )}
      </article>

      <BottomBar>
        <Link className="btn btn--ghost btn--wide" href="/archive">지난 이슈 목록으로</Link>
      </BottomBar>

      {termsOpen && (
        <TermSheet onClose={() => setTermsOpen(false)} terms={detail.terms} />
      )}
      {selectedTerm && (
        <TermSheet
          onClose={() => setSelectedTerm(null)}
          terms={[selectedTerm]}
          title="용어 설명"
        />
      )}
    </main>
  );
}
