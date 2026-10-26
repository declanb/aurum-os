"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { exitStatusLabel, fetchExitBrackets, fetchTrades, ExitBracketView, TradeIdea } from "@/lib/api";
import { Clock, CheckCircle2, AlertCircle } from "lucide-react";

type Tab = "open" | "pending" | "history";

interface PositionsTableProps {
  refreshKey?: number;
}

export function PositionsTable({ refreshKey }: PositionsTableProps) {
  const [tab, setTab] = useState<Tab>("pending");
  const [trades, setTrades] = useState<TradeIdea[]>([]);
  const [brackets, setBrackets] = useState<ExitBracketView[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [data, exits] = await Promise.all([fetchTrades(), fetchExitBrackets()]);
        setTrades(data);
        setBrackets(exits?.brackets ?? []);
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
    <div className="flex flex-col h-full min-w-0 bg-card">
      {/* Tabs */}
      <div className="flex border-b border-border overflow-x-auto min-w-0">
        {(["pending", "open", "history"] as Tab[]).map((t) => {
          const count = trades.filter((tr) => {
            if (t === "open") return tr.status === "Sent";
            if (t === "pending") return ["Draft", "Needs Work", "Ready for Approval", "Approved"].includes(tr.status);
            return ["Closed", "Cancelled"].includes(tr.status);
          }).length;
          return (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`shrink-0 min-h-11 px-4 text-sm font-semibold uppercase tracking-wider border-b-2 transition-colors ${
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {t} {count > 0 && <span className="ml-1 text-xs text-muted-foreground">({count})</span>}
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
          <>
          <div className="md:hidden divide-y divide-border/50">
            {filtered.map((t) => {
              const risk = Math.abs(t.entry_price - t.stop_price);
              const reward = Math.abs(t.target_price - t.entry_price);
              const rr = risk > 0 ? (reward / risk).toFixed(2) : "—";
              const bracket = brackets.find(
                (b) => b.trade_idea_id === t.id || b.exit_trade_idea_id === t.id,
              );
              return (
                <article key={t.id} className="p-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-semibold text-base text-foreground">{t.symbol}</span>
                      <span className={`font-bold text-sm ${t.direction === "LONG" ? "text-emerald-500" : t.direction === "EXIT" ? "text-amber-500" : "text-red-500"}`}>
                        {t.direction}
                      </span>
                    </div>
                    {statusBadge(t.status)}
                  </div>
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-foreground">Entry</dt>
                      <dd className="font-mono break-all">{t.entry_price.toFixed(2)}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-foreground">Stop</dt>
                      <dd className="font-mono text-red-500/80 break-all">{t.stop_price.toFixed(2)}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-foreground">Target</dt>
                      <dd className="font-mono text-emerald-500/80 break-all">{t.target_price.toFixed(2)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">R:R</dt>
                      <dd className="font-mono">1:{rr}</dd>
                    </div>
                  </dl>
                  {bracket && (
                    <p className="text-sm">
                      <span className="font-semibold text-foreground">
                        {exitStatusLabel(bracket.status)}
                        {bracket.trail_armed ? " · trail" : ""}
                      </span>
                      <span className="block text-xs text-muted-foreground font-mono break-all">
                        stop {bracket.stop_price} → {bracket.target_price}
                        {bracket.exit_reason ? ` · ${bracket.exit_reason}` : ""}
                      </span>
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {new Date(t.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </p>
                </article>
              );
            })}
          </div>
          <table className="hidden md:table w-full text-xs">
            <thead className="bg-muted/30 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-2">Symbol</th>
                <th className="text-left px-4 py-2">Side</th>
                <th className="text-right px-4 py-2">Entry</th>
                <th className="text-right px-4 py-2">SL</th>
                <th className="text-right px-4 py-2">TP</th>
                <th className="text-right px-4 py-2">R:R</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Exit</th>
                <th className="text-right px-4 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => {
                const risk = Math.abs(t.entry_price - t.stop_price);
                const reward = Math.abs(t.target_price - t.entry_price);
                const rr = risk > 0 ? (reward / risk).toFixed(2) : "—";
                const bracket = brackets.find(
                  (b) => b.trade_idea_id === t.id || b.exit_trade_idea_id === t.id,
                );
                return (
                  <tr key={t.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                    <td className="px-4 py-2.5 font-semibold text-foreground">{t.symbol}</td>
                    <td className="px-4 py-2.5">
                      <span className={`font-bold text-xs ${t.direction === "LONG" ? "text-emerald-500" : t.direction === "EXIT" ? "text-amber-500" : "text-red-500"}`}>
                        {t.direction}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono">{t.entry_price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-red-500/80">{t.stop_price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-emerald-500/80">{t.target_price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-foreground">1:{rr}</td>
                    <td className="px-4 py-2.5">{statusBadge(t.status)}</td>
                    <td className="px-4 py-2.5">
                      {bracket ? (
                        <span>
                          <span className="font-semibold text-foreground">
                            {exitStatusLabel(bracket.status)}
                            {bracket.trail_armed ? " · trail" : ""}
                          </span>
                          <span className="block text-[10px] text-muted-foreground font-mono">
                            stop {bracket.stop_price} → {bracket.target_price}
                            {bracket.exit_reason ? ` · ${bracket.exit_reason}` : ""}
                          </span>
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">
                      {new Date(t.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </>
        )}
      </div>
    </div>
  );
}
