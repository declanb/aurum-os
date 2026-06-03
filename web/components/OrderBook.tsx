"use client";

import { useEffect, useState } from "react";
import { fetchOrderBook } from "@/lib/api";

interface OrderBookProps {
  symbol: string; // display format e.g. "BTC/USD"
  midPrice: number;
}

interface Level {
  price: number;
  size: number;
  total: number;
}

function buildLevels(raw: { price: number; size: number }[]): Level[] {
  let total = 0;
  return raw.map((r) => {
    total += r.size;
    return { price: r.price, size: r.size, total };
  });
}

export function OrderBook({ symbol, midPrice }: OrderBookProps) {
  const [bids, setBids] = useState<Level[]>([]);
  const [asks, setAsks] = useState<Level[]>([]);
  const [lastMid, setLastMid] = useState<number>(midPrice);
  const [trend, setTrend] = useState<"up" | "down">("up");

  useEffect(() => {
    let cancelled = false;
    const apiSymbol = symbol.replace("/", "-");
    const load = async () => {
      const book = await fetchOrderBook(apiSymbol, 12);
      if (cancelled || !book) return;
      const newBids = buildLevels(book.bids);
      const newAsks = buildLevels(book.asks).reverse();
      setBids(newBids);
      setAsks(newAsks);
      const bestBid = book.bids[0]?.price ?? 0;
      const bestAsk = book.asks[0]?.price ?? 0;
      const newMid = bestBid && bestAsk ? (bestBid + bestAsk) / 2 : midPrice;
      setTrend(newMid >= lastMid ? "up" : "down");
      setLastMid(newMid);
    };
    load();
    const interval = setInterval(load, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  const decimals = midPrice < 1 ? 5 : midPrice < 100 ? 3 : 2;
  const maxBidTotal = Math.max(...bids.map((b) => b.total), 1);
  const maxAskTotal = Math.max(...asks.map((a) => a.total), 1);

  return (
    <div className="flex flex-col h-full bg-card border-r border-border">
      <div className="px-3 py-2.5 border-b border-border">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Order Book · Live</h3>
      </div>

      <div className="grid grid-cols-3 gap-2 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border-b border-border">
        <span>Price</span>
        <span className="text-right">Size</span>
        <span className="text-right">Total</span>
      </div>

      <div className="flex-1 overflow-y-auto flex flex-col-reverse">
        {asks.map((level, i) => {
          const fillPct = (level.total / maxAskTotal) * 100;
          return (
            <div
              key={`ask-${i}`}
              className="relative grid grid-cols-3 gap-2 px-3 py-0.5 text-xs font-mono hover:bg-accent/50"
            >
              <div className="absolute inset-y-0 right-0 bg-red-500/10" style={{ width: `${fillPct}%` }} />
              <span className="relative text-red-500">{level.price.toFixed(decimals)}</span>
              <span className="relative text-right text-foreground/80">{level.size.toFixed(4)}</span>
              <span className="relative text-right text-muted-foreground">{level.total.toFixed(4)}</span>
            </div>
          );
        })}
      </div>

      <div className="px-3 py-2 border-y border-border bg-muted/30 flex items-center justify-between">
        <span className={`text-lg font-mono font-bold ${trend === "up" ? "text-emerald-500" : "text-red-500"}`}>
          {lastMid.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Mid</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {bids.map((level, i) => {
          const fillPct = (level.total / maxBidTotal) * 100;
          return (
            <div
              key={`bid-${i}`}
              className="relative grid grid-cols-3 gap-2 px-3 py-0.5 text-xs font-mono hover:bg-accent/50"
            >
              <div className="absolute inset-y-0 right-0 bg-emerald-500/10" style={{ width: `${fillPct}%` }} />
              <span className="relative text-emerald-500">{level.price.toFixed(decimals)}</span>
              <span className="relative text-right text-foreground/80">{level.size.toFixed(4)}</span>
              <span className="relative text-right text-muted-foreground">{level.total.toFixed(4)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
