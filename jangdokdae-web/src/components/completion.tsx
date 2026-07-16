"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Brand } from "@/components/brand";
import { getDailyPlan } from "@/lib/storage";
import type { StoredDailyPlan } from "@/lib/types";

export function Completion() {
  const [plan, setPlan] = useState<StoredDailyPlan | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage는 hydration 뒤에만 읽는다.
    setPlan(getDailyPlan());
  }, []);

  const completed = plan?.completedIssueIds.length ?? 0;
  const total = plan?.learning.total_count ?? 3;

  return (
    <main className="completion-shell">
      <header className="topbar">
        <Brand />
      </header>
      <section className="completion-card">
        <div className="completion-seal" aria-hidden="true">
          <span>오늘</span>
          <strong>{completed}/{total}</strong>
        </div>
        <span className="eyebrow">오늘의 장독대 완료</span>
        <h1>오늘 알아야 할 만큼은<br />충분히 알았어요.</h1>
        <p>
          더 많은 뉴스를 읽지 않아도 괜찮아요.<br />내일 다시 중요한 세 가지만 담아둘게요.
        </p>
        <div className="completion-line" />
        <blockquote>많이 보는 것보다, 제대로 이해하는 하루.</blockquote>
        <Link className="button button--secondary button--wide" href="/">
          오늘의 이슈 다시 보기
        </Link>
      </section>
    </main>
  );
}
