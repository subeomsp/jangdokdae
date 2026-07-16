import { notFound } from "next/navigation";

import { LearningReader } from "@/components/learning-reader";

export default async function LearnPage({
  params,
}: {
  params: Promise<{ issueId: string }>;
}) {
  const { issueId } = await params;
  const numericIssueId = Number(issueId);
  if (!Number.isInteger(numericIssueId) || numericIssueId <= 0) notFound();
  return <LearningReader issueId={numericIssueId} />;
}
