import { notFound } from "next/navigation";

import { ArchiveReader } from "@/components/archive-reader";

export default async function ArchiveIssuePage({
  params,
}: {
  params: Promise<{ issueId: string }>;
}) {
  const { issueId } = await params;
  const numericIssueId = Number(issueId);
  if (!Number.isInteger(numericIssueId) || numericIssueId <= 0) notFound();
  return <ArchiveReader issueId={numericIssueId} />;
}
