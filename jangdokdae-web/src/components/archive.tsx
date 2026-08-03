"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Brand } from "@/components/brand";
import { ChevronRightIcon } from "@/components/icons";
import { ApiError, getLearningArchive } from "@/lib/api";
import type { LearningArchive } from "@/lib/types";

function formatLearningDate(date: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date(`${date}T00:00:00+09:00`));
}

export function Archive() {
  const [archive, setArchive] = useState<LearningArchive | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getLearningArchive()
      .then((result) => {
        if (active) setArchive(result);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof ApiError
              ? reason.message
              : "서버에 연결하지 못했어요. 네트워크를 확인한 뒤 다시 시도해주세요.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        <Link className="topbar__link" href="/">
          오늘의 이슈
        </Link>
      </header>

      <section className="archive-head">
        <p className="page-head__label">지난 장독대</p>
        <h1>놓친 날의 세 가지를 다시 봐요.</h1>
        <p>오늘을 제외한 최근 14일의 핵심 이슈를 날짜별로 모았습니다.</p>
      </section>

      {loading && (
        <div aria-live="polite" className="archive-skeleton">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index}>
              <div className="skeleton archive-skeleton__date" />
              <div className="skeleton archive-skeleton__row" />
              <div className="skeleton archive-skeleton__row" />
            </div>
          ))}
          <p className="loading-caption">지난 장독대를 꺼내고 있어요</p>
        </div>
      )}

      {!loading && error && (
        <section className="state-block">
          <h2>지난 이슈를 불러오지 못했어요.</h2>
          <p>{error}</p>
          <button className="btn btn--primary" onClick={() => location.reload()} type="button">
            다시 불러오기
          </button>
        </section>
      )}

      {!loading && !error && archive?.days.length === 0 && (
        <section className="state-block state-block--center">
          <p aria-hidden="true" className="quiet-marks">– – –</p>
          <h2>아직 꺼내볼 지난 이슈가 없어요.</h2>
          <p>새로운 학습일이 쌓이면 이곳에 날짜별로 보관할게요.</p>
        </section>
      )}

      {!loading && !error && archive && archive.days.length > 0 && (
        <div className="archive-days">
          {archive.days.map((day) => (
            <section className="archive-day" key={day.learning_date}>
              <h2>{formatLearningDate(day.learning_date)}</h2>
              <ol aria-label={`${formatLearningDate(day.learning_date)}의 이슈`}>
                {day.items.map((issue, index) => (
                  <li key={issue.id}>
                    <Link className="archive-row" href={`/archive/${issue.id}`}>
                      <span className="archive-row__num">{index + 1}</span>
                      <span className="archive-row__body">
                        <span className="archive-row__meta">{issue.category}</span>
                        <strong>{issue.title}</strong>
                        <span className="archive-row__teaser">{issue.teaser}</span>
                      </span>
                      <ChevronRightIcon className="archive-row__chev" size={18} />
                    </Link>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
