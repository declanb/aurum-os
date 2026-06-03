"use client";

interface SymbolHeaderProps {
  symbol: string;
  price: number;
  change24h: number;
  high24h: number;
  low24h: number;
  volume24h: number;
}

export function SymbolHeader({ symbol, price, change24h, high24h, low24h, volume24h }: SymbolHeaderProps) {
  const isUp = change24h >= 0;
  const changeAbs = (price * change24h) / 100;

  return (
    <div className="flex items-center gap-8 px-4 py-3 bg-card border-b border-border overflow-x-auto">
      <div className="flex items-center gap-3 shrink-0">
        <div>
          <h1 className="text-base font-bold text-foreground">{symbol}</h1>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Spot</p>
        </div>
      </div>

      <div className="shrink-0">
        <p className={`text-2xl font-mono font-bold ${isUp ? "text-emerald-500" : "text-red-500"}`}>
          {price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </p>
      </div>

      <Stat label="24h Change" value={`${isUp ? "+" : ""}${changeAbs.toFixed(2)} / ${isUp ? "+" : ""}${change24h.toFixed(2)}%`} positive={isUp} />
      <Stat label="24h High" value={high24h.toFixed(2)} />
      <Stat label="24h Low" value={low24h.toFixed(2)} />
      <Stat label="24h Volume" value={`$${(volume24h / 1_000_000).toFixed(2)}M`} />
    </div>
  );
}

function Stat({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="shrink-0">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">{label}</p>
      <p
        className={`text-sm font-mono font-semibold ${
          positive === undefined ? "text-foreground" : positive ? "text-emerald-500" : "text-red-500"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
