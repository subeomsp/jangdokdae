export function SegmentProgress({
  total,
  value,
  label,
}: {
  total: number;
  value: number;
  label: string;
}) {
  return (
    <div
      className="seg-progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={Math.min(value, total)}
      aria-label={label}
    >
      {Array.from({ length: total }, (_, index) => (
        <span
          className={`seg-progress__seg ${index < value ? "is-filled" : ""}`}
          key={index}
        />
      ))}
    </div>
  );
}
