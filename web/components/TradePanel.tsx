"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { createTrade } from "@/lib/api";

interface TradePanelProps {
  symbol: string;
  midPrice: number;
  availableBalance: number;
  onTradeStaged?: () => void;
}

type OrderType = "market" | "limit" | "stop-limit";
type Side = "buy" | "sell";

export function TradePanel({ symbol, midPrice, availableBalance, onTradeStaged }: TradePanelProps) {
  const [side, setSide] = useState<Side>("buy");
  const [orderType, setOrderType] = useState<OrderType>("limit");
  const [price, setPrice] = useState(midPrice.toFixed(2));
  const [amount, setAmount] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [sizePercent, setSizePercent] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const priceNum = parseFloat(price) || midPrice;
  const amountNum = parseFloat(amount) || 0;
  const total = priceNum * amountNum;

  const handlePercent = (pct: number) => {
    setSizePercent(pct);
    const targetTotal = (availableBalance * pct) / 100;
    const newAmount = priceNum > 0 ? targetTotal / priceNum : 0;
    setAmount(newAmount.toFixed(4));
  };

  const handleSubmit = async () => {
    if (!amount || amountNum <= 0) {
      alert("Enter an amount");
      return;
    }
    if (!stopLoss || !takeProfit) {
      alert("Stop loss and take profit are required for AI scrutiny");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await createTrade({
        symbol: symbol.replace("/", ""),
        direction: side === "buy" ? "LONG" : "SHORT",
        entry_price: priceNum,
        stop_price: parseFloat(stopLoss),
        target_price: parseFloat(takeProfit),
        thesis: `${orderType.toUpperCase()} ${side.toUpperCase()} ${amount} ${symbol} @ ${priceNum}`,
        status: "Ready for Approval",
      });

      if (result) {
        setAmount("");
        setStopLoss("");
        setTakeProfit("");
        setSizePercent(0);
        onTradeStaged?.();
      }
    } catch (error) {
      console.error(error);
      alert("Failed to stage trade");
    } finally {
      setIsSubmitting(false);
    }
  };

  const sideColor = side === "buy" ? "emerald" : "red";

  return (
    <div className="flex flex-col h-full bg-card border-l border-border">
      {/* Buy/Sell Tabs */}
      <div className="grid grid-cols-2 border-b border-border">
        <button
          onClick={() => setSide("buy")}
          className={`py-3 text-sm font-bold transition-colors ${
            side === "buy"
              ? "bg-emerald-500/10 text-emerald-500 border-b-2 border-emerald-500"
              : "text-muted-foreground hover:bg-accent border-b-2 border-transparent"
          }`}
        >
          BUY / LONG
        </button>
        <button
          onClick={() => setSide("sell")}
          className={`py-3 text-sm font-bold transition-colors ${
            side === "sell"
              ? "bg-red-500/10 text-red-500 border-b-2 border-red-500"
              : "text-muted-foreground hover:bg-accent border-b-2 border-transparent"
          }`}
        >
          SELL / SHORT
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Order Type */}
        <div className="flex gap-1 p-1 bg-muted/50 rounded-md">
          {(["market", "limit", "stop-limit"] as OrderType[]).map((type) => (
            <button
              key={type}
              onClick={() => setOrderType(type)}
              className={`flex-1 py-1.5 text-xs font-semibold uppercase rounded transition-colors ${
                orderType === type
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {type}
            </button>
          ))}
        </div>

        {/* Available */}
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">Available</span>
          <span className="font-mono text-foreground">${availableBalance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        </div>

        {/* Price (limit only) */}
        {orderType !== "market" && (
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">
              Price (USD)
            </label>
            <div className="relative">
              <input
                type="number"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="w-full h-11 px-3 pr-12 text-sm font-mono bg-muted/30 border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-ring text-foreground"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground font-semibold">USD</span>
            </div>
          </div>
        )}

        {/* Amount */}
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">
            Amount
          </label>
          <div className="relative">
            <input
              type="number"
              value={amount}
              onChange={(e) => {
                setAmount(e.target.value);
                setSizePercent(0);
              }}
              placeholder="0.00"
              className="w-full h-11 px-3 pr-16 text-sm font-mono bg-muted/30 border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-ring text-foreground"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground font-semibold">
              {symbol.split("/")[0]}
            </span>
          </div>
        </div>

        {/* Size Slider */}
        <div className="grid grid-cols-4 gap-1">
          {[25, 50, 75, 100].map((pct) => (
            <button
              key={pct}
              onClick={() => handlePercent(pct)}
              className={`py-1.5 text-xs font-mono rounded border transition-colors ${
                sizePercent === pct
                  ? `border-${sideColor}-500 bg-${sideColor}-500/10 text-${sideColor}-500`
                  : "border-border bg-muted/30 text-muted-foreground hover:bg-accent"
              }`}
            >
              {pct}%
            </button>
          ))}
        </div>

        {/* SL / TP */}
        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-red-500 block mb-1.5">
              Stop Loss
            </label>
            <input
              type="number"
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value)}
              placeholder={(midPrice * (side === "buy" ? 0.99 : 1.01)).toFixed(2)}
              className="w-full h-10 px-3 text-sm font-mono bg-muted/30 border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-red-500/50 text-foreground"
            />
          </div>
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-emerald-500 block mb-1.5">
              Take Profit
            </label>
            <input
              type="number"
              value={takeProfit}
              onChange={(e) => setTakeProfit(e.target.value)}
              placeholder={(midPrice * (side === "buy" ? 1.02 : 0.98)).toFixed(2)}
              className="w-full h-10 px-3 text-sm font-mono bg-muted/30 border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-emerald-500/50 text-foreground"
            />
          </div>
        </div>

        {/* Total */}
        <div className="flex justify-between items-center py-2 px-3 bg-muted/30 rounded-md">
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Total</span>
          <span className="text-sm font-mono font-bold text-foreground">
            ${total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>

        {/* R:R indicator */}
        {stopLoss && takeProfit && amount && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Risk / Reward</span>
            {(() => {
              const risk = Math.abs(priceNum - parseFloat(stopLoss));
              const reward = Math.abs(parseFloat(takeProfit) - priceNum);
              const rr = risk > 0 ? (reward / risk).toFixed(2) : "—";
              const rrNum = parseFloat(rr);
              return (
                <Badge
                  variant="outline"
                  className={
                    rrNum >= 2
                      ? "border-emerald-500/50 text-emerald-500"
                      : "border-amber-500/50 text-amber-500"
                  }
                >
                  1 : {rr}
                </Badge>
              );
            })()}
          </div>
        )}
      </div>

      {/* Submit */}
      <div className="p-4 border-t border-border bg-muted/20">
        <Button
          onClick={handleSubmit}
          disabled={isSubmitting || !amount}
          className={`w-full h-12 text-sm font-bold uppercase tracking-wider ${
            side === "buy"
              ? "bg-emerald-500 hover:bg-emerald-600 text-white"
              : "bg-red-500 hover:bg-red-600 text-white"
          }`}
        >
          {isSubmitting ? "Staging..." : `${side === "buy" ? "Buy" : "Sell"} ${symbol.split("/")[0]}`}
        </Button>
        <p className="text-[10px] text-center text-muted-foreground mt-2">
          Routes to AI scrutiny → human approval → broker
        </p>
      </div>
    </div>
  );
}
