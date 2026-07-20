import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className={`brand ${compact ? "brand--compact" : ""}`} href="/" aria-label="장독대 홈">
      <span className="brand__word">장독대</span>
      <span className="brand__dot" aria-hidden="true" />
    </Link>
  );
}
