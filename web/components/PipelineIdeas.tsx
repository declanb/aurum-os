import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { TradeIdea } from "@/lib/api";
import { PIPELINE_GROUPS, pipelineIdeas, type PipelineStatus } from "@/lib/pipeline";

const STATUS_CLASS: Record<PipelineStatus, string> = {
  "Ready for Approval": "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  "Needs Work": "border-orange-500/40 bg-orange-500/10 text-orange-700 dark:text-orange-300",
  Approved: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  Sent: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

function formatPx(value: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function formatWhen(iso: string): string {
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "";
  return new Date(parsed).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function directionClass(direction: TradeIdea["direction"]): string {
  if (direction === "LONG") return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  if (direction === "EXIT") return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
}

export function PipelineIdeas({
  trades,
  error = null,
  loading = false,
  groupAs = "h2",
}: {
  trades: TradeIdea[];
  error?: string | null;
  loading?: boolean;
  groupAs?: "h2" | "h3" | "h4";
}) {
  const Heading = groupAs;
  const ideas = pipelineIdeas(trades);
  const archiveCount = Math.max(0, trades.length - ideas.length);

  if (loading) {
    return <p className="text-sm text-muted-foreground py-6">Loading staged ideas…</p>;
  }

  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive py-6">
        {error}
      </p>
    );
  }

  if (ideas.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center">
        <p className="text-sm text-foreground">No staged ideas in the pipeline.</p>
        <p className="text-xs text-muted-foreground mt-1">
          Ready for approval, approved, and recently sent trades show up here.
          {archiveCount > 0 ? " Older ideas are in the Journal." : ""}
        </p>
      </div>
    );
  }

  const summary = PIPELINE_GROUPS.map((group) => {
    const count = ideas.filter((trade) => trade.status === group.status).length;
    return count > 0 ? `${count} ${group.title.toLowerCase()}` : null;
  })
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-6 min-w-0" data-testid="pipeline-ideas">
      <p className="text-xs font-medium text-muted-foreground">{summary}</p>
      {PIPELINE_GROUPS.map((group) => {
        const rows = ideas.filter((trade) => trade.status === group.status);
        if (rows.length === 0) return null;
        return (
          <section key={group.status} aria-label={group.title} className="space-y-3 min-w-0">
            <div>
              <Heading className="text-sm font-semibold text-foreground">{group.title}</Heading>
              <p className="text-xs text-muted-foreground mt-0.5">{group.hint}</p>
            </div>
            <ul className="space-y-3">
              {rows.map((trade) => (
                <li key={trade.id} data-testid={`pipeline-idea-${trade.id}`}>
                  <Link
                    href={`/app/approvals?idea=${trade.id}`}
                    aria-label={`Open idea ${trade.id} ${trade.symbol} ${trade.direction}, status ${trade.status}, in Approvals`}
                    className="block rounded-xl border border-border bg-card p-4 min-w-0 transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                      <div className="flex flex-wrap items-center gap-2 min-w-0">
                        <span className="font-bold text-foreground break-all">{trade.symbol}</span>
                        <span className="text-xs font-mono text-muted-foreground">#{trade.id}</span>
                        <Badge variant="outline" className={directionClass(trade.direction)}>
                          {trade.direction}
                        </Badge>
                      </div>
                      <Badge variant="outline" className={STATUS_CLASS[trade.status as PipelineStatus]}>
                        {trade.status}
                      </Badge>
                    </div>
                    <p className="text-sm text-foreground/90 leading-relaxed mb-3 whitespace-pre-wrap break-words">
                      {trade.thesis || "No thesis yet."}
                    </p>
                    <div className="grid grid-cols-3 gap-2 mb-3 text-xs text-muted-foreground">
                      <span className="min-w-0">
                        Entry
                        <span className="block font-mono text-sm text-foreground break-all">{formatPx(trade.entry_price)}</span>
                      </span>
                      <span className="min-w-0">
                        Stop
                        <span className="block font-mono text-sm text-foreground break-all">{formatPx(trade.stop_price)}</span>
                      </span>
                      <span className="min-w-0">
                        Target
                        <span className="block font-mono text-sm text-foreground break-all">{formatPx(trade.target_price)}</span>
                      </span>
                    </div>
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <span className="text-xs text-muted-foreground">
                        {formatWhen(trade.updated_at || trade.created_at)}
                      </span>
                      <span className="inline-flex items-center gap-1 text-sm font-medium text-primary min-h-11">
                        Open in Approvals
                        <ArrowRight className="w-3.5 h-3.5" />
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {archiveCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {archiveCount} older or draft idea{archiveCount === 1 ? "" : "s"} stay in the Journal and Planner.
        </p>
      )}
    </div>
  );
}
