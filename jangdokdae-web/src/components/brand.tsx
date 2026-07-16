import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" href="/" aria-label="장독대 홈">
      <svg
        className="brand__mark"
        viewBox="0 0 32 32"
        role="img"
        aria-hidden="true"
      >
        <path d="M8.8 10.2h14.4l1.6 3.2-1.4 13.1H8.6L7.2 13.4l1.6-3.2Z" />
        <path d="M10.1 7.8c1.7-2.5 10.1-2.5 11.8 0v2.4H10.1V7.8Z" />
        <path d="M10.2 16.1c3.7 1.6 7.9 1.6 11.6 0" />
      </svg>
      {!compact && <span>장독대</span>}
    </Link>
  );
}
