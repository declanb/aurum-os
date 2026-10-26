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
    <div className="flex flex-col min-w-0 bg-background -mx-4 -mt-4 md:-mx-6 md:-mt-6 lg:-mx-8 lg:-mt-8 lg:-mb-8 lg:h-[calc(100dvh-4rem)]">
      <SymbolHeader
        symbol={selectedSymbol}
        price={midPrice}
        change24h={change}
        high24h={session?.high ?? midPrice}
        low24h={session?.low ?? midPrice}
        volume24h={0}
      />

      <div className="px-4 py-2 border-b border-border text-xs text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-emerald-500 font-semibold">● LIVE</span>
        <span>Revolut X · {balance > 0 ? `${balanceCcy} ${balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} available` : "loading account…"}</span>
      </div>

      <div className="lg:hidden border-b border-border">
        <MarketList variant="strip" selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} tickers={tickers} />
      </div>

      <div className="flex flex-col lg:grid lg:grid-cols-[220px_240px_minmax(0,1fr)_320px] lg:grid-rows-[minmax(0,1fr)_18rem] lg:flex-1 lg:min-h-0">
        <div className="hidden lg:block lg:row-span-2 lg:h-full min-h-0 overflow-hidden">
          <MarketList selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} tickers={tickers} />
        </div>
        <div className="order-4 lg:order-0 lg:row-span-2 h-80 lg:h-full min-h-0 overflow-hidden border-t lg:border-t-0">
          <OrderBook symbol={selectedSymbol} midPrice={midPrice || 1} />
        </div>
        <div className="order-1 lg:order-0 h-64 sm:h-80 lg:h-full min-h-0 min-w-0">
          <PriceChart symbol={selectedSymbol} midPrice={midPrice || 1} />
        </div>
        <div className="order-2 lg:order-0 lg:row-span-2 lg:h-full min-h-0 min-w-0">
          <TradePanel
            symbol={selectedSymbol}
            midPrice={midPrice || 1}
            availableBalance={balance}
            onTradeStaged={() => setRefreshKey((k) => k + 1)}
          />
        </div>
        <div className="order-3 lg:order-0 lg:h-full min-h-0 min-w-0 overflow-hidden border-t border-border">
          <PositionsTable refreshKey={refreshKey} />
        </div>
      </div>
    </div>
  );
}
