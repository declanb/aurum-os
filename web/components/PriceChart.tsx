"use client";

import { useEffect, useState } from "react";
import { fetchCandles, type RxCandle } from "@/lib/api";

interface PriceChartProps {
  symbol: string; // display format e.g. "BTC/USD"
  midPrice: number;
}

const TIMEFRAMES = [
  { label: "1m", value: "1m" },
  { label: "5m", value: "5m" },
  { label: "15m", value: "15m" },
  { label: "1H", value: "1h" },
  { label: "4H", value: "4h" },
  { label: "1D", value: "1d" },
];

export function PriceChart({ symbol, midPrice }: PriceChartProps) {
  const [candles, setCandles] = useState<RxCandle[]>([]);
  const [timeframe, setTimeframe] = useState("1h");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const apiSymbol = symbol.replace("/", "-");
    const load = async () => {
      setLoading(true);
      const data = await fetchCandles(apiSymbol, timeframe, 80);
      if (cancelled) return;
      setCandles(data);
      setLoading(false);
    };
    load();
    const interval = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [symbol, timeframe]);

  if (loading && candles.length === 0) {
    return <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">Loading {symbol} chart…</div>;
  }
  if (candles.length === 0) {
    return <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">No data for {symbol}</div>;
  }

  const allPrices = candles.flatMap((c) => [c.high, c.low]);
  const min = Math.min(...allPrices);
  const max = Math.max(...allPrices);
  const range = max - min || 1;
  const padding = range * 0.1;
  const chartMin = min - padding;
  const chartMax = max + padding;
  const chartRange = chartMax - chartMin;

  const width = 800;
  const height = 360;
  const candleWidth = width / candles.length;

  const yFor = (price: number) => height - ((price - chartMin) / chartRange) * height;
  const decimals = midPrice < 1 ? 5 : midPrice < 100 ? 3 : 2;

  return (
    <div className="flex flex-col h-full bg-card">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
        <div className="flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value)}
              className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
                timeframe === tf.value ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50"
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
        <div className="text-[10px] text-emerald-500 uppercase tracking-wider font-semibold">● Revolut X Live</div>
      </div>

      <div className="flex-1 relative overflow-hidden">
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="w-full h-full">
          {[0.2, 0.4, 0.6, 0.8].map((p) => (
            <line
              key={p}
              x1={0}
              x2={width}
              y1={height * p}
              y2={height * p}
              stroke="currentColor"
              className="text-border"
              strokeDasharray="2 4"
              strokeWidth={0.5}
            />
          ))}

          {candles.map((c, i) => {
            const x = i * candleWidth + candleWidth / 2;
            const isUp = c.close >= c.open;
            const color = isUp ? "rgb(16 185 129)" : "rgb(239 68 68)";
            return (
              <g key={i}>
                <line x1={x} x2={x} y1={yFor(c.high)} y2={yFor(c.low)} stroke={color} strokeWidth={1} />
                <rect
                  x={x - candleWidth * 0.35}
                  y={yFor(Math.max(c.open, c.close))}
                  width={candleWidth * 0.7}
                  height={Math.max(1, Math.abs(yFor(c.open) - yFor(c.close)))}
                  fill={color}
                />
              </g>
            );
          })}

          <line
            x1={0}
            x2={width}
            y1={yFor(candles[candles.length - 1].close)}
            y2={yFor(candles[candles.length - 1].close)}
            stroke="currentColor"
            className="text-primary"
            strokeDasharray="3 3"
            strokeWidth={0.8}
          />
        </svg>

        <div className="absolute right-2 top-0 h-full flex flex-col justify-between py-1 pointer-events-none">
          {[chartMax, (chartMax + chartMin) / 2, chartMin].map((p, i) => (
            <span key={i} className="text-[10px] font-mono text-muted-foreground bg-card/80 px-1 rounded">
              {p.toFixed(decimals)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
