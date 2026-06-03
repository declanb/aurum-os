"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { MarketList } from "@/components/MarketList";
import { OrderBook } from "@/components/OrderBook";
import { TradePanel } from "@/components/TradePanel";
import { PriceChart } from "@/components/PriceChart";
import { PositionsTable } from "@/components/PositionsTable";
import { SymbolHeader } from "@/components/SymbolHeader";
import { fetchTickers, fetchRxAccount, type RxTicker } from "@/lib/api";

const WATCHLIST = [
  "BTC-USD",
  "ETH-USD",
  "SOL-USD",
  "XRP-USD",
  "ADA-USD",
  "DOT-USD",
  "DOGE-USD",
  "LINK-USD",
];

export default function ExchangePage() {
  const [selectedSymbol, setSelectedSymbol] = useState("BTC/USD");
  const [tickers, setTickers] = useState<RxTicker[]>([]);
  const [balance, setBalance] = useState<number>(0);
  const [balanceCcy, setBalanceCcy] = useState<string>("EUR");
  const [refreshKey, setRefreshKey] = useState(0);
  const sessionHighRef = useRef<Record<string, { high: number; low: number; open: number }>>({});

  // Poll tickers from Revolut X every 2s
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const data = await fetchTickers(WATCHLIST);
      if (cancelled) return;
      // Track session OHLC for each symbol
      data.forEach((t) => {
        const cur = sessionHighRef.current[t.symbol];
        if (!cur) {
          sessionHighRef.current[t.symbol] = { high: t.mid, low: t.mid, open: t.mid };
        } else {
          cur.high = Math.max(cur.high, t.mid);
          cur.low = Math.min(cur.low, t.mid);
        }
      });
      setTickers(data);
    };
    load();
    const interval = setInterval(load, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // Load account balance (largest available balance shown in header)
  useEffect(() => {
    fetchRxAccount()
      .then((acc) => {
        if (!acc?.balances) return;
        const top = [...acc.balances]
          .filter((b) => (b.available ?? 0) > 0)
          .sort((a, b) => (b.available ?? 0) - (a.available ?? 0))[0];
        if (top) {
          setBalance(top.available);
          setBalanceCcy(top.currency);
        }
      })
      .catch(() => {});
  }, []);

  const selected = tickers.find((t) => t.symbol === selectedSymbol);
  const midPrice = selected?.mid ?? 0;
  const session = sessionHighRef.current[selectedSymbol];
  const change = useMemo(() => {
    if (!selected || !session) return 0;
    return ((selected.mid - session.open) / session.open) * 100;
  }, [selected, session]);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-background -m-6 lg:-m-8">
      <SymbolHeader
        symbol={selectedSymbol}
        price={midPrice}
        change24h={change}
        high24h={session?.high ?? midPrice}
        low24h={session?.low ?? midPrice}
        volume24h={0}
      />

      <div className="px-4 py-1 border-b border-border text-[11px] text-muted-foreground flex items-center gap-3">
        <span className="text-emerald-500 font-semibold">● LIVE</span>
        <span>Revolut X · {balance > 0 ? `${balanceCcy} ${balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} available` : "loading account…"}</span>
      </div>

      <div className="flex-1 grid grid-cols-[220px_240px_1fr_320px] min-h-0">
        <MarketList selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} tickers={tickers} />
        <OrderBook symbol={selectedSymbol} midPrice={midPrice || 1} />
        <div className="flex flex-col min-w-0 border-r border-border">
          <div className="flex-1 min-h-0">
            <PriceChart symbol={selectedSymbol} midPrice={midPrice || 1} />
          </div>
          <div className="h-72 border-t border-border">
            <PositionsTable refreshKey={refreshKey} />
          </div>
        </div>
        <TradePanel
          symbol={selectedSymbol}
          midPrice={midPrice || 1}
          availableBalance={balance}
          onTradeStaged={() => setRefreshKey((k) => k + 1)}
        />
      </div>
    </div>
  );
}
