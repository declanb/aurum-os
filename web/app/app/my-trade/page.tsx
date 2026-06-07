"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchLivePositions } from "@/lib/api";

// Asset → emoji map (cosmetic only — backend is source of truth for everything else)
const ASSET_EMOJI: Record<string, string> = {
  BTC: "🟠",
  ETH: "⟠",
  SOL: "🌞",
  SHIB: "🐕",
  AVAX: "🔺",
  ATOM: "⚛️",
  ENA: "⚡",
  XRP: "💧",
  DOGE: "🐶",
  ADA: "🔷",
};

// Default profit target — gain N% net of fees triggers the auto-sell
const TARGET_PROFIT_PCT = 0.025; // 2.5%
const TAKER_FEE = 0.0009;

interface PositionView {
  symbol: string;
  asset: string;
  emoji: string;
  bid: number;
  ask: number;
  pnl: number;
  pnlPct: number;
  triggerBid: number | null;
  distancePct: number | null;
  entryPrice: number;
  qty: number;
  costEur: number;
  currentValue: number;
  hasDbRecord: boolean;
  isStaked: boolean;
  staked: number;
  available: number;
  type?: string;
}

export default function MyTradeDashboard() {
  const [positions, setPositions] = useState<PositionView[]>([]);
  const [cashEur, setCashEur] = useState(0);
  const [totalPnl, setTotalPnl] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const data = await fetchLivePositions();
      if (!data) {
        setError("Failed to load live positions");
        return;
      }
      setError(null);
      setCashEur(data.cash_eur);
      setTotalPnl(data.total_pnl_eur);

      const views: PositionView[] = data.positions.map((p) => {
        const entryPrice = p.entry_price ?? 0;
        const costEur = p.cost_eur ?? 0;
        // Target bid that yields TARGET_PROFIT_PCT net P&L on costEur (when DB record exists)
        let triggerBid: number | null = null;
        let distancePct: number | null = null;
        if (costEur > 0 && p.qty > 0) {
          const targetSaleNet = costEur * (1 + TARGET_PROFIT_PCT);
          triggerBid = targetSaleNet / (p.qty * (1 - TAKER_FEE));
          distancePct = p.bid > 0 ? ((triggerBid - p.bid) / p.bid) * 100 : null;
        }
        return {
          symbol: p.symbol,
          asset: p.asset,
          emoji: ASSET_EMOJI[p.asset] ?? "🪙",
          bid: p.bid,
          ask: p.ask,
          pnl: p.pnl_eur ?? 0,
          pnlPct: p.pnl_pct ?? 0,
          triggerBid,
          distancePct,
          entryPrice,
          qty: p.qty,
          costEur,
          currentValue: p.current_value_eur,
          hasDbRecord: p.has_db_record,
          isStaked: p.is_staked,
          staked: p.staked,
          available: p.available,
        };
      });

      setPositions(views);
      setLastUpdated(new Date());
    } catch (err) {
      console.error(err);
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">Loading live positions…</div>;
  }
  if (error && positions.length === 0) {
    return (
      <div className="p-8 text-center">
        <p className="text-rose-500 font-semibold mb-2">Could not load positions</p>
        <p className="text-xs text-muted-foreground font-mono">{error}</p>
      </div>
    );
  }
  if (positions.length === 0) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        No open positions on Revolut X. Cash balance: €{cashEur.toFixed(2)}
      </div>
    );
  }

  const totalValue = positions.reduce((sum, p) => sum + p.currentValue, 0);
  const totalCost = positions.reduce((sum, p) => sum + p.costEur, 0);
  const totalAccount = totalValue + cashEur;
  const isProfitable = totalPnl > 0;
  const isFlat = Math.abs(totalPnl) < 0.01;
  const unmatchedCount = positions.filter((p) => !p.hasDbRecord).length;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* HERO — total account + P&L */}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-background to-muted/40 p-8">
        <div className="absolute top-4 right-6 text-xs text-muted-foreground font-mono">
          {lastUpdated ? `live · ${lastUpdated.toLocaleTimeString()}` : "loading…"}
        </div>

        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
          {/* LEFT: Total + P&L */}
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Total Account</p>
            <div className="flex items-baseline gap-3">
              <h1 className="text-6xl md:text-7xl font-bold tracking-tight tabular-nums">
                €{totalAccount.toFixed(2)}
              </h1>
              <span
                className={`text-2xl font-bold tabular-nums ${
                  isProfitable
                    ? "text-emerald-500"
                    : isFlat
                    ? "text-muted-foreground"
                    : "text-rose-500"
                }`}
              >
                {totalPnl >= 0 ? "▲" : "▼"} {totalPnl >= 0 ? "+" : "−"}€{Math.abs(totalPnl).toFixed(2)}
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              {isProfitable ? "🎉 In profit" : isFlat ? "⚪ At break-even" : "🔴 Below entry"}
              <span className="mx-2">·</span>
              {totalCost > 0 ? ((totalPnl / totalCost) * 100).toFixed(2) : "0.00"}% on €{totalCost.toFixed(2)} invested
            </p>
          </div>

          {/* RIGHT: Cash + Invested breakdown */}
          <div className="flex gap-6">
            <div className="text-right">
              <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">Cash</p>
              <p className="text-2xl font-semibold tabular-nums text-emerald-400">€{cashEur.toFixed(2)}</p>
            </div>
            <div className="w-px bg-border" />
            <div className="text-right">
              <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">Invested</p>
              <p className="text-2xl font-semibold tabular-nums">€{totalValue.toFixed(2)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* ALL POSITIONS */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {positions.map((pos) => {
          const posIsProfitable = pos.pnl > 0;
          const posIsFlat = Math.abs(pos.pnl) < 0.001;

          // Progress to target: 0% = at entry, 100% = at trigger bid
          const progressPct =
            pos.triggerBid && pos.triggerBid > pos.entryPrice
              ? Math.max(0, Math.min(100, ((pos.bid - pos.entryPrice) / (pos.triggerBid - pos.entryPrice)) * 100))
              : 0;

          return (
            <Card
              key={pos.symbol}
              className={`p-5 transition-all hover:scale-[1.01] ${
                pos.isStaked
                  ? "border-violet-500/30 bg-violet-500/2"
                  : posIsProfitable
                  ? "border-emerald-500/40 shadow-emerald-500/5 shadow-lg"
                  : posIsFlat
                  ? "border-border"
                  : "border-rose-500/30"
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-3xl">{pos.emoji}</span>
                  <div>
                    <h3 className="font-bold text-lg leading-tight">{pos.asset}</h3>
                    <p className="text-xs text-muted-foreground font-mono">{pos.symbol}</p>
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={
                    pos.isStaked
                      ? "border-violet-500/40 text-violet-400 bg-violet-500/5"
                      : posIsProfitable
                      ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/5"
                      : posIsFlat
                      ? ""
                      : "border-rose-500/30 text-rose-400 bg-rose-500/5"
                  }
                >
                  {pos.isStaked ? "🔒 STAKED" : posIsProfitable ? "▲ PROFIT" : posIsFlat ? "FLAT" : "▼ LOSS"}
                </Badge>
              </div>

              {/* Hero P&L for this position */}
              <div className="mb-4">
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Position value</p>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold tabular-nums">€{pos.currentValue.toFixed(2)}</span>
                  <span
                    className={`text-sm font-semibold tabular-nums ${
                      posIsProfitable ? "text-emerald-500" : posIsFlat ? "text-muted-foreground" : "text-rose-500"
                    }`}
                  >
                    {pos.pnl >= 0 ? "+" : "−"}€{Math.abs(pos.pnl).toFixed(4)}
                    <span className="ml-1 opacity-70">({pos.pnlPct >= 0 ? "+" : ""}{pos.pnlPct.toFixed(2)}%)</span>
                  </span>
                </div>
              </div>

              {/* Progress to target — hide for staked positions (can't be sold) */}
              {!pos.isStaked && pos.triggerBid && pos.distancePct !== null && (
                <div className="mb-4">
                  <div className="flex justify-between items-center mb-1.5">
                    <span className="text-xs text-muted-foreground">🎯 Auto-sell at €{pos.triggerBid.toFixed(pos.triggerBid < 0.01 ? 8 : 2)}</span>
                    <span
                      className={`text-xs font-semibold tabular-nums ${
                        pos.distancePct <= 0 ? "text-emerald-400" : "text-amber-400"
                      }`}
                    >
                      {pos.distancePct <= 0 ? "READY" : `+${pos.distancePct.toFixed(2)}% to go`}
                    </span>
                  </div>
                  <div className="relative w-full h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`absolute inset-y-0 left-0 rounded-full transition-all duration-700 ${
                        progressPct >= 100
                          ? "bg-linear-to-r from-emerald-500 to-emerald-400"
                          : "bg-linear-to-r from-amber-500 to-amber-400"
                      }`}
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Progress: {progressPct.toFixed(0)}% of way to target
                  </p>
                </div>
              )}

              {/* Staked notice — replaces the progress bar */}
              {pos.isStaked && (
                <div className="mb-4 rounded-lg border border-violet-500/30 bg-violet-500/5 p-3">
                  <p className="text-xs font-semibold text-violet-300 mb-1">🔒 Locked — staked</p>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    {pos.staked.toLocaleString(undefined, { maximumFractionDigits: 6 })} {pos.asset} earning staking rewards.
                    Cannot be sold by hunter until unstaked in the Revolut app (~21-day unbonding for Cosmos).
                  </p>
                </div>
              )}

              {/* Compact details */}
              <div className="grid grid-cols-2 gap-2 pt-3 border-t border-border text-xs">
                <div>
                  <p className="text-muted-foreground">Entry</p>
                  <p className="font-mono">€{pos.entryPrice.toFixed(pos.entryPrice < 0.01 ? 8 : 2)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Now</p>
                  <p className="font-mono">€{pos.bid.toFixed(pos.bid < 0.01 ? 8 : 2)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Qty</p>
                  <p className="font-mono">{pos.qty < 1 ? pos.qty.toFixed(6) : pos.qty.toLocaleString(undefined, { maximumFractionDigits: 2 })}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Cost</p>
                  <p className="font-mono">€{pos.costEur.toFixed(2)}</p>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* FOOTER — minimal helper line */}
      <p className="text-center text-xs text-muted-foreground pt-2">
        ⚡ Refreshes every 5s · Source: Revolut X balances ⨝ DB fills · {positions.length} held
        {unmatchedCount > 0 && (
          <span className="text-amber-400 ml-1">
            · ⚠ {unmatchedCount} position{unmatchedCount === 1 ? "" : "s"} not yet in DB (entry/cost unknown)
          </span>
        )}
      </p>
    </div>
  );
}
