"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Brand } from "@/components/brand";
import { getSectors } from "@/lib/api";
import { getInterests, saveInterests } from "@/lib/storage";
import type { Sector } from "@/lib/types";

const MAX_SELECTION = 3;

export function Onboarding() {
  const router = useRouter();
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const existing = getInterests();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- client-only 관심사를 hydration 뒤 복원한다.
    if (existing) setSelected(existing.sectorIds);

    let active = true;
    getSectors()
      .then((items) => {
        if (active) setSectors(items);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error ? reason.message : "섹터를 불러오지 못했어요.",
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

  function toggleSector(sectorId: number) {
    setSelected((current) => {
      if (current.includes(sectorId)) {
        return current.filter((value) => value !== sectorId);
      }
      if (current.length >= MAX_SELECTION) return current;
      return [...current, sectorId];
    });
  }

  function completeOnboarding() {
    if (selected.length === 0) return;
    saveInterests(selected);
    router.push("/");
  }

  return (
    <main className="app-shell onboarding-shell">
      <header className="topbar">
        <Brand />
        <span className="step-label">처음 한 번만</span>
      </header>

      <section className="onboarding-intro">
        <span className="eyebrow">관심 설정</span>
        <h1>어떤 산업의 흐름이<br />가장 궁금한가요?</h1>
        <p>한 개부터 세 개까지 골라주세요. 나중에 언제든 바꿀 수 있어요.</p>
      </section>

      <div className="selection-count" aria-live="polite">
        <strong>{selected.length}</strong> / {MAX_SELECTION} 선택
      </div>

      {loading ? (
        <div className="sector-grid" aria-label="섹터 불러오는 중">
          {Array.from({ length: 6 }, (_, index) => (
            <div className="sector-card sector-card--skeleton" key={index} />
          ))}
        </div>
      ) : error ? (
        <section className="empty-state empty-state--inline">
          <h2>섹터를 불러오지 못했어요.</h2>
          <p>{error}</p>
          <button className="button button--secondary" onClick={() => location.reload()}>
            다시 시도하기
          </button>
        </section>
      ) : (
        <section className="sector-grid" aria-label="관심 섹터 선택">
          {sectors.map((sector) => {
            const checked = selected.includes(sector.id);
            const disabled = !checked && selected.length >= MAX_SELECTION;
            return (
              <button
                className={`sector-card ${checked ? "is-selected" : ""}`}
                disabled={disabled}
                key={sector.id}
                onClick={() => toggleSector(sector.id)}
                type="button"
                aria-pressed={checked}
              >
                <span className="sector-card__check">{checked ? "✓" : "+"}</span>
                <strong>{sector.name_ko}</strong>
                <span>
                  {sector.industry_groups.slice(0, 2).join(" · ") || sector.name_en}
                </span>
              </button>
            );
          })}
        </section>
      )}

      <div className="sticky-action">
        <button
          className="button button--primary button--wide"
          disabled={selected.length === 0}
          onClick={completeOnboarding}
          type="button"
        >
          오늘의 세 가지 만나기
        </button>
      </div>
    </main>
  );
}
