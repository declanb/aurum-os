"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

interface PriceData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
}

export function TradingTicker() {
  const [prices, setPrices] = useState<PriceData[]>([
    { symbol: "XAU/USD", price: 2045.50, change: 12.40, changePercent: 0.61 },
    { symbol: "BTC/USD", price: 67845.20, change: -234.50, changePercent: -0.34 },
    { symbol: "EUR/USD", price: 1.0875, change: 0.0023, changePercent: 0.21 },
  ]);

  // Simulate price updates every 3 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setPrices((prev) =>
        prev.map((p) => {
          const volatility = Math.random() * 0.002 - 0.001; // -0.1% to +0.1%
          const newPrice = p.price * (1 + volatility);
          const newChange = newPrice - (p.price - p.change);
          const newChangePercent = (newChange / (newPrice - newChange)) * 100;

          return {
            ...p,
            price: parseFloat(newPrice.toFixed(2)),
            change: parseFloat(newChange.toFixed(2)),
            changePercent: parseFloat(newChangePercent.toFixed(2)),
          };
        })
      );
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-6 overflow-x-auto pb-2 scrollbar-hide">
      {prices.map((item) => (
        <div
          key={item.symbol}
          className="flex items-center gap-4 px-4 py-2 rounded-lg bg-muted/50 border border-border min-w-fit"
        >
          <div>
            <p className="text-xs text-muted-foreground font-medium">{item.symbol}</p>
            <p className="text-lg font-bold font-mono text-foreground">{item.price.toLocaleString()}</p>
          </div>
          <div className="flex items-center gap-1">
            {item.change >= 0 ? (
              <>
                <TrendingUp className="w-4 h-4 text-emerald-500" />
                <div className="text-right">
                  <p className="text-sm font-bold text-emerald-500">+{item.change.toFixed(2)}</p>
                  <p className="text-xs text-emerald-500">+{item.changePercent.toFixed(2)}%</p>
                </div>
              </>
            ) : (
              <>
                <TrendingDown className="w-4 h-4 text-red-500" />
                <div className="text-right">
                  <p className="text-sm font-bold text-red-500">{item.change.toFixed(2)}</p>
                  <p className="text-xs text-red-500">{item.changePercent.toFixed(2)}%</p>
                </div>
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
