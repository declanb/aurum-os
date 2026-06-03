"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchTrades, TradeIdea } from "@/lib/api";
import { Clock, CheckCircle2, AlertCircle } from "lucide-react";

type Tab = "open" | "pending" | "history";

interface PositionsTableProps {
  refreshKey?: number;
}

export function PositionsTable({ refreshKey }: PositionsTableProps) {
  const [tab, setTab] = useState<Tab>("pending");
  const [trades, setTrades] = useState<TradeIdea[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await fetchTrades();
        setTrades(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [refreshKey]);

  const filtered = trades.filter((t) => {
    if (tab === "open") return t.status === "Sent";
    if (tab === "pending") return ["Draft", "Needs Work", "Ready for Approval", "Approved"].includes(t.status);
    return ["Closed", "Cancelled"].includes(t.status);
  });

  const statusBadge = (status: string) => {
    const map: Record<string, { color: string; icon?: React.ReactNode }> = {
      "Ready for Approval": { color: "border-amber-500/50 text-amber-500 bg-amber-500/10", icon: <Clock className="w-3 h-3" /> },
      "Approved": { color: "border-blue-500/50 text-blue-500 bg-blue-500/10", icon: <CheckCircle2 className="w-3 h-3" /> },
      "Sent": { color: "border-emerald-500/50 text-emerald-500 bg-emerald-500/10", icon: <CheckCircle2 className="w-3 h-3" /> },
      "Needs Work": { color: "border-red-500/50 text-red-500 bg-red-500/10", icon: <AlertCircle className="w-3 h-3" /> },
      "Draft": { color: "border-border text-muted-foreground bg-muted/30" },
      "Closed": { color: "border-border text-muted-foreground bg-muted/30" },
      "Cancelled": { color: "border-border text-muted-foreground bg-muted/30" },
    };
    const cfg = map[status] || map["Draft"];
    return (
      <Badge variant="outline" className={`gap-1 ${cfg.color}`}>
        {cfg.icon}
        {status}
      </Badge>
    );
  };

  return (
    <div className="flex flex-col h-full bg-card">
      {/* Tabs */}
      <div className="flex border-b border-border">
        {(["pending", "open", "history"] as Tab[]).map((t) => {
          const count = trades.filter((tr) => {
            if (t === "open") return tr.status === "Sent";
            if (t === "pending") return ["Draft", "Needs Work", "Ready for Approval", "Approved"].includes(tr.status);
            return ["Closed", "Cancelled"].includes(tr.status);
          }).length;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors ${
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {t} {count > 0 && <span className="ml-1 text-[10px] text-muted-foreground">({count})</span>}
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">No {tab} trades</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-muted/30 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-2">Symbol</th>
                <th className="text-left px-4 py-2">Side</th>
                <th className="text-right px-4 py-2">Entry</th>
                <th className="text-right px-4 py-2">SL</th>
                <th className="text-right px-4 py-2">TP</th>
                <th className="text-right px-4 py-2">R:R</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-right px-4 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => {
                const risk = Math.abs(t.entry_price - t.stop_price);
                const reward = Math.abs(t.target_price - t.entry_price);
                const rr = risk > 0 ? (reward / risk).toFixed(2) : "—";
                return (
                  <tr key={t.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                    <td className="px-4 py-2.5 font-semibold text-foreground">{t.symbol}</td>
                    <td className="px-4 py-2.5">
                      <span className={`font-bold text-xs ${t.direction === "LONG" ? "text-emerald-500" : "text-red-500"}`}>
                        {t.direction}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono">{t.entry_price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-red-500/80">{t.stop_price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-emerald-500/80">{t.target_price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-foreground">1:{rr}</td>
                    <td className="px-4 py-2.5">{statusBadge(t.status)}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">
                      {new Date(t.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
