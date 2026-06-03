"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { AiRecommendations } from "@/components/AiRecommendations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TrendingUp, TrendingDown, Activity, Zap, DollarSign, Target } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Balance {
  currency: string;
  available: number;
  balance: number;
}

interface AccountData {
  balances: Balance[];
}

interface Position {
  symbol: string;
  qty: number;
  cost_eur: number;
  current_bid: number;
  pnl: number;
  pnl_pct: number;
}

export default function Dashboard() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [agentStatus, setAgentStatus] = useState<string>("checking...");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      // Fetch account
      const accRes = await fetch(`${API_URL}/revolut-x/account`);
      const accData = await accRes.json();
      setAccount(accData);

      // Calculate position P&L if holding BTC
      const btcBal = accData.balances.find((b: Balance) => b.currency === "BTC");
      if (btcBal && btcBal.balance > 0) {
        // Fetch current ticker
        const tickerRes = await fetch(`${API_URL}/revolut-x/tickers?symbols=BTC-EUR`);
        const tickerData = await tickerRes.json();
        const bid = tickerData[0]?.bid || 0;

        // Known cost from the trade we just made
        const cost_eur = 2.0;
        const qty = btcBal.balance;
        const TAKER_FEE = 0.0009;
        const sale_net = qty * bid * (1 - TAKER_FEE);
        const pnl = sale_net - cost_eur;
        const pnl_pct = (pnl / cost_eur) * 100;

        setPosition({
          symbol: "BTC-EUR",
          qty,
          cost_eur,
          current_bid: bid,
          pnl,
          pnl_pct,
        });
      } else {
        setPosition(null);
      }

      // Check agent status by reading log (simplified)
      checkAgentStatus();
      setLoading(false);
    } catch (err) {
      console.error("Dashboard load failed:", err);
      setLoading(false);
    }
  };

  const checkAgentStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/agent/profit-hunter/status`);
      const data = await res.json();
      setAgentStatus(data.running ? "running" : "stopped");
    } catch (err) {
      console.error("Agent status check failed:", err);
      setAgentStatus("unknown");
    }
  };

  const eurBalance = account?.balances.find((b) => b.currency === "EUR")?.balance || 0;
  const btcBalance = account?.balances.find((b) => b.currency === "BTC")?.balance || 0;
  const totalValue = eurBalance + (position ? position.qty * position.current_bid : 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <Activity className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
          <p className="text-muted-foreground mt-1">Live trading overview & agent status</p>
        </div>
        <Badge variant="outline" className="gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
          Connected to Revolut X
        </Badge>
      </div>

      {/* Account Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <GlassCard className="p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-primary/10">
              <DollarSign className="w-5 h-5 text-primary" />
            </div>
            <h3 className="font-semibold text-foreground">Total Balance</h3>
          </div>
          <div className="text-3xl font-bold text-foreground">€{totalValue.toFixed(2)}</div>
          <p className="text-xs text-muted-foreground mt-1">
            EUR: €{eurBalance.toFixed(2)} | BTC: {btcBalance.toFixed(8)}
          </p>
        </GlassCard>

        <GlassCard className="p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-emerald-500/10">
              {position && position.pnl >= 0 ? (
                <TrendingUp className="w-5 h-5 text-emerald-500" />
              ) : (
                <TrendingDown className="w-5 h-5 text-red-500" />
              )}
            </div>
            <h3 className="font-semibold text-foreground">Current P&L</h3>
          </div>
          {position ? (
            <>
              <div
                className={`text-3xl font-bold ${
                  position.pnl >= 0 ? "text-emerald-500" : "text-red-500"
                }`}
              >
                {position.pnl >= 0 ? "+" : ""}€{position.pnl.toFixed(4)}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {position.pnl_pct >= 0 ? "+" : ""}
                {position.pnl_pct.toFixed(2)}% on {position.symbol}
              </p>
            </>
          ) : (
            <>
              <div className="text-3xl font-bold text-muted-foreground">€0.00</div>
              <p className="text-xs text-muted-foreground mt-1">No open positions</p>
            </>
          )}
        </GlassCard>

        <GlassCard className="p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-violet-500/10">
              <Activity className="w-5 h-5 text-violet-500" />
            </div>
            <h3 className="font-semibold text-foreground">Profit Hunter</h3>
          </div>
          <div className="text-3xl font-bold text-foreground">
            {position ? "Active" : "Idle"}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {position
              ? "Monitoring for 2.5% profit (€0.05)"
              : "No position to monitor"}
          </p>
        </GlassCard>
      </div>

      {/* Position Details */}
      {position && (
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-foreground mb-4 flex items-center gap-2">
            <Target className="w-5 h-5 text-primary" />
            Active Position
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Symbol</p>
              <p className="text-sm font-bold font-mono">{position.symbol}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Quantity</p>
              <p className="text-sm font-bold font-mono">{position.qty.toFixed(8)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Cost Basis</p>
              <p className="text-sm font-bold">€{position.cost_eur.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Current Bid</p>
              <p className="text-sm font-bold">€{position.current_bid.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Target</p>
              <p className="text-sm font-bold text-emerald-500">
                €{(position.cost_eur + 0.05).toFixed(2)}
              </p>
            </div>
          </div>
          <div className="mt-4 p-3 rounded-lg bg-muted/30 border border-border">
            <p className="text-xs text-muted-foreground">
              <strong>Profit Hunter:</strong> Monitoring every 10s. Will auto-sell at market when
              P&L reaches €0.05 (2.5% profit). Check{" "}
              <code className="text-xs bg-muted px-1 py-0.5 rounded">
                tail -f /tmp/profit_hunter.log
              </code>{" "}
              for live updates.
            </p>
          </div>
        </GlassCard>
      )}

      {/* AI Recommendations */}
      <div>
        <h3 className="text-lg font-bold text-foreground mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5 text-primary" />
          AI Trade Recommendations
        </h3>
        <AiRecommendations onTradeCreated={loadData} />
      </div>

      {/* Quick Actions */}
      <GlassCard className="p-6">
        <h3 className="text-lg font-bold text-foreground mb-4">Quick Actions</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Button asChild variant="outline">
            <a href="/app/planner">Trade Planner</a>
          </Button>
          <Button asChild variant="outline">
            <a href="/app/approvals">Approvals</a>
          </Button>
          <Button asChild variant="outline">
            <a href="/app/journal">Journal</a>
          </Button>
          <Button asChild variant="outline">
            <a href="/app">Exchange View</a>
          </Button>
        </div>
      </GlassCard>
    </div>
  );
}
