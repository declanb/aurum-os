"use client";

import { useEffect, useState } from "react";
import { fetchTradesResult, fetchRxAccount, fetchTickers, fetchOpenAIBalance, type TradeIdea, type RxAccount, type RxTicker, type OpenAIBalance } from "@/lib/api";
import { PipelineIdeas } from "@/components/PipelineIdeas";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TrendingUp, AlertCircle, Clock, RefreshCw, Sparkles, Bot } from "lucide-react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

type AgentStatus = {
  total_agents: number;
  running: number;
  stale: number;
  paused: boolean;
};

export default function Dashboard() {
  const [account, setAccount] = useState<RxAccount | null>(null);
  const [trades, setTrades] = useState<TradeIdea[]>([]);
  const [tradesError, setTradesError] = useState<string | null>(null);
  const [tickers, setTickers] = useState<RxTicker[]>([]);
  const [openaiBalance, setOpenaiBalance] = useState<OpenAIBalance | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [tradesReady, setTradesReady] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadTrades = async () => {
      const tradeResult = await fetchTradesResult();
      if (cancelled) return;
      setTrades(tradeResult.trades);
      setTradesError(tradeResult.error);
      setTradesReady(true);
    };

    const loadAccount = async () => {
      const [acc, oai] = await Promise.all([
        fetchRxAccount(),
        fetchOpenAIBalance(),
      ]);
      if (cancelled) return;
      setAccount(acc);
      setOpenaiBalance(oai);

      try {
        const agentRes = await fetch(`${API_URL}/agent/status`);
        if (!cancelled && agentRes.ok) {
          setAgentStatus(await agentRes.json());
        }
      } catch {
        // Agent endpoint unavailable
      }

      if (acc?.balances) {
        const cryptoCcys = acc.balances
          .filter((b) => b.balance > 0 && b.currency !== "EUR" && b.currency !== "USD" && b.currency !== "GBP")
          .map((b) => `${b.currency}-USD`);
        if (cryptoCcys.length > 0) {
          const tix = await fetchTickers(cryptoCcys);
          if (!cancelled) setTickers(tix);
        } else if (!cancelled) {
          setTickers([]);
        }
      }

      if (!cancelled) {
        setLastUpdated(new Date());
        setLoading(false);
      }
    };

    void loadTrades();
    void loadAccount();
    const i = setInterval(() => {
      void loadTrades();
      void loadAccount();
    }, 15_000);
    return () => {
      cancelled = true;
      clearInterval(i);
    };
  }, []);

  const pendingApproval = trades.filter((t) => t.status === "Ready for Approval" || t.status === "Needs Work");
  const approved = trades.filter((t) => t.status === "Approved");
  const executed = trades.filter((t) => t.status === "Sent");
  const rejected = trades.filter((t) => t.status === "Cancelled");

  // Approximate EUR/USD parity for display (Revolut X quotes in USD for crypto)
  const USD_TO_EUR = 0.92;

  const usdValueOf = (currency: string, amount: number): number => {
    if (currency === "EUR") return amount / USD_TO_EUR;
    if (currency === "USD") return amount;
    if (currency === "GBP") return amount * 1.27;
    const t = tickers.find((x) => x.symbol === `${currency}/USD`);
    return t ? amount * t.mid : 0;
  };

  const totalUsd =
    account?.balances.reduce((sum, b) => sum + usdValueOf(b.currency, b.balance), 0) ?? 0;
  const totalEur = totalUsd * USD_TO_EUR;

  const enrichedBalances =
    account?.balances
      .filter((b) => b.balance > 0)
      .map((b) => ({
        ...b,
        usdValue: usdValueOf(b.currency, b.balance),
        eurValue: usdValueOf(b.currency, b.balance) * USD_TO_EUR,
      }))
      .sort((a, b) => b.usdValue - a.usdValue) ?? [];

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground mb-1">
            {greeting}, Declan.
          </h1>
          <p className="text-muted-foreground">Live from your Revolut X account.</p>
        </div>
        {lastUpdated && (
          <div className="text-xs text-muted-foreground flex items-center gap-1.5 sm:text-right">
            <RefreshCw className="w-3 h-3" />
            Updated {lastUpdated.toLocaleTimeString()}
          </div>
        )}
      </div>

      <section aria-labelledby="recommendations-heading" className="min-w-0">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between mb-3">
          <div className="min-w-0">
            <h2 id="recommendations-heading" className="text-lg font-semibold text-foreground">
              Recommendations
            </h2>
            <p className="text-sm text-muted-foreground">
              Staged ideas stay listed here after a refresh. Approve and execute on Approvals.
            </p>
          </div>
          <Button variant="outline" size="sm" className="gap-2 w-full sm:w-auto min-h-11" asChild>
            <Link href="/app/recommendations">Full list</Link>
          </Button>
        </div>
        <PipelineIdeas trades={trades} error={tradesError} loading={!tradesReady} groupAs="h3" />
      </section>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading account…</p>
      ) : (
      <>
      {/* Account Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Total Portfolio Value
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-foreground">
              €{totalEur.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              ${totalUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} · Live mid prices
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              OpenAI Credits
            </CardTitle>
          </CardHeader>
          <CardContent>
            {openaiBalance?.connected ? (
              <>
                <div className="text-3xl font-bold text-foreground">
                  ${openaiBalance.total_available?.toFixed(2) ?? "—"}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {openaiBalance.total_used !== null
                    ? `$${openaiBalance.total_used.toFixed(2)} used this period`
                    : openaiBalance.plan || "Active"}
                </p>
              </>
            ) : (
              <>
                <div className="text-3xl font-bold text-muted-foreground">—</div>
                <p className="text-xs text-muted-foreground mt-1">API key not configured</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Bot className="w-3.5 h-3.5" />
              Agents Running
            </CardTitle>
          </CardHeader>
          <CardContent>
            {agentStatus ? (
              <>
                <div className="text-3xl font-bold text-emerald-500">{agentStatus.running}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {agentStatus.paused ? "⏸ Paused" : `${agentStatus.total_agents} total, ${agentStatus.stale} stale`}
                </p>
              </>
            ) : (
              <>
                <div className="text-3xl font-bold text-muted-foreground">0</div>
                <p className="text-xs text-muted-foreground mt-1">No agents detected</p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Pending Approvals
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-primary">{pendingApproval.length}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {pendingApproval.length === 1 ? "Trade awaiting your call" : "Trades awaiting review"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Asset Breakdown */}
      {enrichedBalances.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg font-semibold text-foreground">Your Holdings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {enrichedBalances.map((bal) => {
                const pct = totalUsd > 0 ? (bal.usdValue / totalUsd) * 100 : 0;
                const ticker = tickers.find((t) => t.symbol === `${bal.currency}/USD`);
                return (
                  <div key={bal.currency} className="flex items-center justify-between gap-3 py-3 border-b border-border last:border-0">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm">
                        {bal.currency.substring(0, 3)}
                      </div>
                      <div>
                        <p className="font-semibold text-foreground">{bal.currency}</p>
                        <p className="text-xs text-muted-foreground font-mono break-all">
                          {bal.balance.toFixed(bal.currency === "EUR" || bal.currency === "USD" ? 2 : 8)}
                          {ticker && (
                            <span className="ml-2 text-muted-foreground">
                              @ ${ticker.mid.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                            </span>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="font-mono text-foreground font-semibold">
                        €{bal.eurValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </p>
                      <p className="text-xs text-muted-foreground">{pct.toFixed(1)}% of portfolio</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-sm text-muted-foreground">No holdings yet. Fund your Revolut X account to get started.</p>
          </CardContent>
        </Card>
      )}

      {/* Recent Activity Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Clock className="w-4 h-4" /> Approved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">{approved.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Awaiting execution</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <TrendingUp className="w-4 h-4" /> Executed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-500">{executed.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Live positions</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <AlertCircle className="w-4 h-4" /> Rejected
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">{rejected.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Did not meet criteria</p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="flex flex-col sm:flex-row gap-3">
        <Button className="w-full gap-2 flex-1" size="lg" asChild>
          <Link href="/app/approvals">
            <AlertCircle className="w-4 h-4" />
            Review Pending Trades
          </Link>
        </Button>
        <Button variant="outline" className="w-full gap-2 flex-1" size="lg" asChild>
          <Link href="/app/planner">
            Plan New Trade
          </Link>
        </Button>
      </div>
      </>
      )}
    </div>
  );
}
