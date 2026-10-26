import type { TradeIdea } from "@/lib/api";

/** Statuses still moving through review or execution. Every one of these is listed. */
export const PIPELINE_ACTIVE_STATUSES = ["Ready for Approval", "Needs Work", "Approved"] as const;

/** Newest sent ideas kept on Recommendations and Approvals. Older sent ideas stay in the Journal. */
export const RECENT_SENT_LIMIT = 8;

export type PipelineStatus = (typeof PIPELINE_ACTIVE_STATUSES)[number] | "Sent";

export const PIPELINE_GROUPS: { status: PipelineStatus; title: string; hint: string }[] = [
  {
    status: "Ready for Approval",
    title: "Ready for approval",
    hint: "Staged for review. Nothing is sent until you approve and then execute.",
  },
  {
    status: "Needs Work",
    title: "Needs work",
    hint: "Returned for changes before it can be approved.",
  },
  {
    status: "Approved",
    title: "Approved",
    hint: "Approved. Execute is a separate tap on Approvals.",
  },
  {
    status: "Sent",
    title: "Recently sent",
    hint: "Already sent to Revolut X. The latest ones stay on this list.",
  },
];

const RANK = new Map(PIPELINE_GROUPS.map((group, index) => [group.status, index]));

function timestamp(trade: TradeIdea): number {
  const parsed = Date.parse(trade.updated_at || trade.created_at);
  return Number.isNaN(parsed) ? 0 : parsed;
}

/**
 * Current pipeline: every ready, needs-work, and approved idea, plus the newest sent ideas.
 * Drafts, closed, and cancelled ideas stay off this list.
 */
export function pipelineIdeas(trades: TradeIdea[], sentLimit = RECENT_SENT_LIMIT): TradeIdea[] {
  const active = trades.filter((trade) =>
    (PIPELINE_ACTIVE_STATUSES as readonly string[]).includes(trade.status),
  );
  const sent = trades
    .filter((trade) => trade.status === "Sent")
    .sort((a, b) => timestamp(b) - timestamp(a))
    .slice(0, Math.max(0, sentLimit));

  return [...active, ...sent].sort((a, b) => {
    const rank =
      (RANK.get(a.status as PipelineStatus) ?? 9) - (RANK.get(b.status as PipelineStatus) ?? 9);
    if (rank !== 0) return rank;
    return timestamp(b) - timestamp(a);
  });
}
