"use client";

import { useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import { fetchRxAccount } from "@/lib/api";

export function BalancePill() {
  const [balance, setBalance] = useState<number | null>(null);
  const [currency, setCurrency] = useState<string>("EUR");
  const [error, setError] = useState(false);

  useEffect(() => {
    const load = async () => {
      const acc = await fetchRxAccount();
      if (!acc?.balances) {
        setError(true);
        return;
      }
      const top = [...acc.balances]
        .filter((b) => (b.available ?? 0) > 0)
        .sort((a, b) => (b.available ?? 0) - (a.available ?? 0))[0];
      if (top) {
        setBalance(top.available);
        setCurrency(top.currency);
        setError(false);
      } else {
        setBalance(0);
      }
    };
    load();
    const i = setInterval(load, 15_000);
    return () => clearInterval(i);
  }, []);

  return (
    <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted/50 border border-border">
      <Wallet className="w-3.5 h-3.5 text-muted-foreground" />
      <span className="text-xs text-muted-foreground">Revolut X</span>
      <span className="text-xs font-mono font-bold text-foreground">
        {error
          ? "offline"
          : balance === null
          ? "…"
          : `${currency} ${balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
      </span>
    </div>
  );
}
