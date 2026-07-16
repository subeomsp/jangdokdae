export function ProgressDots({
  total,
  completed,
  current,
}: {
  total: number;
  completed: number;
  current?: number;
}) {
  return (
    <div
      className="progress-dots"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={completed}
      aria-label={`오늘의 학습 ${completed}/${total}`}
    >
      {Array.from({ length: total }, (_, index) => {
        const step = index + 1;
        const state =
          step <= completed ? "done" : step === current ? "current" : "upcoming";
        return <span className={`progress-dots__item is-${state}`} key={step} />;
      })}
    </div>
  );
}
