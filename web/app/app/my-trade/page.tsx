"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// Portfolio positions
const POSITIONS = [
  {
    symbol: "BTC-EUR",
    asset: "BTC",
    entryPrice: 58023.30,
    qty: 0.00003443,
    costEur: 2.00,
    targetProfitEur: 0.05,
    type: "ACTIVE_TRADE",
    emoji: "🟠"
  },
  {
    symbol: "SHIB-EUR",
    asset: "SHIB",
    entryPrice: 0.0000045,
    qty: 333337,
    costEur: 1.50,
    targetProfitEur: 0.0075,
    type: "ACTIVE_TRADE",
    emoji: "🐕"
  },
  {
    symbol: "AVAX-EUR",
    asset: "AVAX",
    entryPrice: 7.11,
    qty: 0.210928,
    costEur: 1.50,
    targetProfitEur: 0.0075,
    type: "ACTIVE_TRADE",
    emoji: "🔺"
  },
  {
    symbol: "SOL-EUR",
    asset: "SOL",
    entryPrice: 64.25,
    qty: 0.023346,
    costEur: 1.50,
    targetProfitEur: 0.0075,
    type: "ACTIVE_TRADE",
    emoji: "🌞"
  }
];

const TAKER_FEE = 0.0009;

interface PositionStatus {
  symbol: string;
  asset: string;
  type: string;
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
}

export default function MyTradeDashboard() {
  const [positions, setPositions] = useState<PositionStatus[]>([]);
  const [cashEur, setCashEur] = useState(0);
  const [totalPnl, setTotalPnl] = useState(0);

  const loadData = async () => {
    try {
      const symbols = "BTC-EUR,ATOM-EUR,SHIB-EUR,ENA-EUR,AVAX-EUR";
      const [tickerRes, accRes] = await Promise.all([
        fetch(`${API_URL}/revolut-x/tickers?symbols=${symbols}`),
        fetch(`${API_URL}/revolut-x/account`),
      ]);
      
      const tickers = await tickerRes.json();
      const acc = await accRes.json();
      
      const eur = acc.balances.find((b: any) => b.currency === "EUR")?.balance || 0;
      setCashEur(eur);
      
      const posStatuses: PositionStatus[] = POSITIONS.map(pos => {
        const ticker = tickers.find((t: any) => t.symbol === pos.symbol.replace("-", "/"));
        const bid = ticker?.bid || 0;
        const ask = ticker?.ask || 0;
        
        // Calculate P&L
        const saleNet = pos.qty * bid * (1 - TAKER_FEE);
        const pnl = saleNet - pos.costEur;
        const pnlPct = (pnl / pos.costEur) * 100;
        
        // Trigger price (only for active trades)
        let triggerBid = null;
        let distancePct = null;
        if (pos.targetProfitEur && pos.targetProfitEur > 0) {
          triggerBid = (pos.costEur + pos.targetProfitEur) / (pos.qty * (1 - TAKER_FEE));
          distancePct = ((triggerBid - bid) / bid) * 100;
        }
        
        return {
          symbol: pos.symbol,
          asset: pos.asset,
          type: pos.type,
          emoji: pos.emoji,
          bid,
          ask,
          pnl,
          pnlPct,
          triggerBid,
          distancePct,
          entryPrice: pos.entryPrice,
          qty: pos.qty,
          costEur: pos.costEur,
          currentValue: saleNet,
        };
      });
      
      setPositions(posStatuses);
      setTotalPnl(posStatuses.reduce((sum, p) => sum + p.pnl, 0));
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  if (positions.length === 0) {
    return <div className="p-8 text-center text-muted-foreground">Loading...</div>;
  }

  const totalValue = positions.reduce((sum, p) => sum + p.currentValue, 0);
  const totalCost = positions.reduce((sum, p) => sum + p.costEur, 0);
  const isProfitable = totalPnl > 0;
  const isFlat = Math.abs(totalPnl) < 0.01;
  
  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* HEADER */}
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-2">My Portfolio</h1>
        <p className="text-muted-foreground">
          {positions.length} positions • Invested: €{totalCost.toFixed(2)} • Current: €{totalValue.toFixed(2)} • Cash: €{cashEur.toFixed(2)}
        </p>
      </div>

      {/* BIG P&L CARD */}
      <Card className={`p-8 text-center ${
        isProfitable ? "bg-emerald-500/10 border-emerald-500/30" :
        isFlat ? "bg-muted border-border" :
        "bg-red-500/10 border-red-500/30"
      }`}>
        <p className="text-sm text-muted-foreground mb-2">Total Portfolio P&L</p>
        <h2 className={`text-6xl font-bold mb-2 ${
          isProfitable ? "text-emerald-500" :
          isFlat ? "text-foreground" :
          "text-red-500"
        }`}>
          {totalPnl >= 0 ? "+" : ""}€{Math.abs(totalPnl).toFixed(4)}
        </h2>
        <p className="text-xl font-semibold">
          {isProfitable ? "PROFITABLE 🎉" : isFlat ? "BREAK-EVEN ⚪" : "LOSING 🔴"}
        </p>
        <p className="text-sm text-muted-foreground mt-2">
          ({((totalPnl / totalCost) * 100).toFixed(2)}%)
        </p>
      </Card>

      {/* ALL POSITIONS */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {positions.map((pos) => {
          const posIsProfitable = pos.pnl > 0;
          const posIsFlat = Math.abs(pos.pnl) < 0.001;
          
          return (
            <Card key={pos.symbol} className={`p-5 ${
              posIsProfitable ? "border-emerald-500/30" :
              posIsFlat ? "border-border" :
              "border-red-500/30"
            }`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{pos.emoji}</span>
                  <div>
                    <h3 className="font-bold text-lg">{pos.asset}</h3>
                    <Badge variant="outline" className="text-xs">
                      {pos.type === "STAKING" ? "Staking 22.77% APY" : "Active Trade"}
                    </Badge>
                  </div>
                </div>
              </div>

              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Qty:</span>
                  <span className="font-mono">{pos.qty < 1 ? pos.qty.toFixed(8) : pos.qty.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Entry:</span>
                  <span className="font-mono">€{pos.entryPrice.toFixed(pos.entryPrice < 0.01 ? 8 : 4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Now:</span>
                  <span className="font-mono">€{pos.bid.toFixed(pos.bid < 0.01 ? 8 : 4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Invested:</span>
                  <span className="font-mono">€{pos.costEur.toFixed(2)}</span>
                </div>
                
                <div className="pt-2 border-t border-border"></div>
                
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground font-semibold">P&L:</span>
                  <span className={`font-mono font-bold ${
                    posIsProfitable ? "text-emerald-500" :
                    posIsFlat ? "text-foreground" :
                    "text-red-500"
                  }`}>
                    {pos.pnl >= 0 ? "+" : ""}€{pos.pnl.toFixed(4)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">%:</span>
                  <span className={`font-mono ${
                    posIsProfitable ? "text-emerald-500" :
                    posIsFlat ? "text-muted-foreground" :
                    "text-red-500"
                  }`}>
                    {pos.pnlPct >= 0 ? "+" : ""}{pos.pnlPct.toFixed(2)}%
                  </span>
                </div>

                {pos.triggerBid && pos.distancePct !== null && (
                  <>
                    <div className="pt-2 border-t border-border"></div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">🎯 Sell at:</span>
                      <span className="font-mono text-emerald-500">€{pos.triggerBid.toFixed(pos.triggerBid < 0.01 ? 8 : 4)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Distance:</span>
                      <Badge variant="outline">
                        +{pos.distancePct.toFixed(2)}%
                      </Badge>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2 overflow-hidden mt-1">
                      <div 
                        className="h-full bg-blue-500 transition-all"
                        style={{ 
                          width: `${Math.max(0, Math.min(100, ((pos.bid - pos.entryPrice) / (pos.triggerBid - pos.entryPrice)) * 100))}%`
                        }}
                      />
                    </div>
                  </>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {/* QUICK SUMMARY */}
      <Card className="p-6 bg-blue-500/5 border-blue-500/20">
        <h3 className="font-bold mb-3">📊 Strategy Summary</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <p className="font-semibold mb-2">Active Trades ({positions.filter(p => p.type === "ACTIVE_TRADE").length})</p>
            <ul className="space-y-1 text-muted-foreground">
              {positions.filter(p => p.type === "ACTIVE_TRADE").map(p => (
                <li key={p.symbol}>• {p.emoji} {p.asset}: Agent watching, sells at +€{(p.costEur * (p.triggerBid! - p.entryPrice) / p.entryPrice).toFixed(4)}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="font-semibold mb-2">Staking ({positions.filter(p => p.type === "STAKING").length})</p>
            <ul className="space-y-1 text-muted-foreground">
              {positions.filter(p => p.type === "STAKING").map(p => (
                <li key={p.symbol}>• {p.emoji} {p.asset}: Earning ~€{(p.costEur * 0.2277 / 365).toFixed(4)}/day</li>
              ))}
            </ul>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-4">
          ⚡ This page refreshes every 5 seconds. Agents check prices every 10 seconds and sell automatically when targets hit.
        </p>
      </Card>
    </div>
  );
}
