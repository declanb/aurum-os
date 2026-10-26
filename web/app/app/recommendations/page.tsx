"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

import { PipelineIdeas } from "@/components/PipelineIdeas";
import { Button } from "@/components/ui/button";
import { fetchTradesResult, type TradeIdea } from "@/lib/api";

export default function RecommendationsPage() {
  const [trades, setTrades] = useState<TradeIdea[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const result = await fetchTradesResult();
    setTrades(result.trades);
    setError(result.error);
    setLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const result = await fetchTradesResult();
      if (cancelled) return;
      setTrades(result.trades);
      setError(result.error);
      setLoading(false);
    };
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="space-y-5 max-w-3xl min-w-0">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">Recommendations</h1>
          <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
            Ideas Helm has staged. Ready for approval, approved, and recently sent trades stay on this list after a refresh.
            Approving and executing still happens on Approvals.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
          <Button variant="outline" className="min-h-11 w-full sm:w-auto" onClick={() => void load()}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
          <Button className="min-h-11 w-full sm:w-auto" asChild>
            <Link href="/app/approvals">Open Approvals</Link>
          </Button>
        </div>
      </div>
      <PipelineIdeas trades={trades} error={error} loading={loading} />
    </div>
  );
}
