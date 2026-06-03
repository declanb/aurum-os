"use client";

import { useEffect, useRef, useState } from "react";
import { TrendingUp, TrendingDown, Search } from "lucide-react";
import type { RxTicker } from "@/lib/api";

interface MarketListProps {
  selectedSymbol: string;
  onSelect: (symbol: string) => void;
  tickers: RxTicker[];
}

const NAME_MAP: Record<string, string> = {
  "BTC/USD": "Bitcoin",
  "ETH/USD": "Ethereum",
  "SOL/USD": "Solana",
  "XRP/USD": "XRP",
  "ADA/USD": "Cardano",
  "DOT/USD": "Polkadot",
  "DOGE/USD": "Dogecoin",
  "LINK/USD": "Chainlink",
  "AVAX/USD": "Avalanche",
  "MATIC/USD": "Polygon",
};

export function MarketList({ selectedSymbol, onSelect, tickers }: MarketListProps) {
  const [search, setSearch] = useState("");
  const baselineRef = useRef<Record<string, number>>({});

  useEffect(() => {
    tickers.forEach((t) => {
      if (baselineRef.current[t.symbol] === undefined) {
        baselineRef.current[t.symbol] = t.mid;
      }
    });
  }, [tickers]);

  const markets = tickers.map((t) => {
    const base = baselineRef.current[t.symbol] || t.mid;
    const change = base > 0 ? ((t.mid - base) / base) * 100 : 0;
    return {
      symbol: t.symbol,
      name: NAME_MAP[t.symbol] || t.symbol.split("/")[0],
      price: t.mid,
      change24h: change,
    };
  });

  const filtered = markets.filter(
    (m) =>
      m.symbol.toLowerCase().includes(search.toLowerCase()) ||
      m.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-card border-r border-border">
      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search markets"
            className="w-full h-9 pl-9 pr-3 text-sm bg-muted/50 border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-ring text-foreground placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <div className="grid grid-cols-[1fr_auto_auto] gap-3 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border-b border-border">
        <span>Pair</span>
        <span className="text-right">Last</span>
        <span className="text-right w-16">Session</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="px-3 py-6 text-xs text-muted-foreground text-center">
            Connecting to Revolut X…
          </div>
        )}
        {filtered.map((m) => {
          const isSelected = m.symbol === selectedSymbol;
          const isUp = m.change24h >= 0;
          const decimals = m.price < 1 ? 5 : m.price < 100 ? 3 : 2;
          return (
            <button
              key={m.symbol}
              onClick={() => onSelect(m.symbol)}
              className={`w-full grid grid-cols-[1fr_auto_auto] gap-3 px-3 py-2.5 text-sm border-l-2 transition-colors text-left ${
                isSelected
                  ? "bg-accent border-l-primary"
                  : "border-l-transparent hover:bg-accent/50"
              }`}
            >
              <div className="min-w-0">
                <p className="font-semibold text-foreground truncate">{m.symbol}</p>
                <p className="text-[10px] text-muted-foreground truncate">{m.name}</p>
              </div>
              <span className="text-right font-mono text-foreground self-center">
                {m.price.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
              </span>
              <span
                className={`text-right font-mono text-xs self-center w-16 flex items-center justify-end gap-0.5 ${
                  isUp ? "text-emerald-500" : "text-red-500"
                }`}
              >
                {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {isUp ? "+" : ""}
                {m.change24h.toFixed(2)}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
