"use client";

import { useState } from "react";
import { X, TrendingUp, TrendingDown, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { createTrade } from "@/lib/api";

interface QuickTradePanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function QuickTradePanel({ isOpen, onClose, onSuccess }: QuickTradePanelProps) {
  const [direction, setDirection] = useState<"LONG" | "SHORT">("LONG");
  const [symbol, setSymbol] = useState("BTC-USD");
  const [entry, setEntry] = useState("");
  const [stop, setStop] = useState("");
  const [target, setTarget] = useState("");
  const [thesis, setThesis] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Calculate risk metrics
  const entryNum = parseFloat(entry) || 0;
  const stopNum = parseFloat(stop) || 0;
  const targetNum = parseFloat(target) || 0;

  const risk = Math.abs(entryNum - stopNum);
  const reward = Math.abs(targetNum - entryNum);
  const rrRatio = risk > 0 ? (reward / risk).toFixed(2) : "—";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entry || !stop || !target || !thesis) {
      alert("Please fill in all required fields");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await createTrade({
        symbol,
        direction,
        entry_price: parseFloat(entry),
        stop_price: parseFloat(stop),
        target_price: parseFloat(target),
        thesis,
        status: "Ready for Approval",
      });

      if (result) {
        // Reset form
        setEntry("");
        setStop("");
        setTarget("");
        setThesis("");
        onSuccess?.();
        onClose();
      }
    } catch (error) {
      console.error("Failed to create trade:", error);
      alert("Failed to create trade. Check console.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 animate-in fade-in"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-full md:w-125 bg-card border-l border-border z-50 animate-in slide-in-from-right duration-300 flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-border flex items-center justify-between bg-muted/30">
          <div>
            <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
              <Zap className="w-5 h-5 text-primary" />
              Quick Trade Entry
            </h2>
            <p className="text-xs text-muted-foreground mt-1">Stage a trade for AI scrutiny</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Direction Selector */}
          <div>
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 block">
              Direction
            </Label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setDirection("LONG")}
                className={`p-4 rounded-xl border-2 transition-all ${
                  direction === "LONG"
                    ? "border-emerald-500 bg-emerald-500/10"
                    : "border-border bg-card hover:bg-accent"
                }`}
              >
                <TrendingUp className="w-6 h-6 mx-auto mb-2 text-emerald-500" />
                <span className="block text-sm font-bold text-foreground">LONG</span>
              </button>
              <button
                type="button"
                onClick={() => setDirection("SHORT")}
                className={`p-4 rounded-xl border-2 transition-all ${
                  direction === "SHORT"
                    ? "border-red-500 bg-red-500/10"
                    : "border-border bg-card hover:bg-accent"
                }`}
              >
                <TrendingDown className="w-6 h-6 mx-auto mb-2 text-red-500" />
                <span className="block text-sm font-bold text-foreground">SHORT</span>
              </button>
            </div>
          </div>

          {/* Symbol */}
          <div>
            <Label htmlFor="symbol" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 block">
              Symbol
            </Label>
            <Input
              id="symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="BTC-USD"
              className="h-12 text-base font-mono"
            />
          </div>

          {/* Price Levels */}
          <div className="space-y-4">
            <div>
              <Label htmlFor="entry" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 block">
                Entry Price
              </Label>
              <Input
                id="entry"
                type="number"
                step="0.01"
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
                placeholder="2045.50"
                className="h-12 text-base font-mono"
                required
              />
            </div>

            <div>
              <Label htmlFor="stop" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 block">
                Stop Loss
              </Label>
              <Input
                id="stop"
                type="number"
                step="0.01"
                value={stop}
                onChange={(e) => setStop(e.target.value)}
                placeholder="2040.00"
                className="h-12 text-base font-mono"
                required
              />
            </div>

            <div>
              <Label htmlFor="target" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 block">
                Take Profit
              </Label>
              <Input
                id="target"
                type="number"
                step="0.01"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="2060.00"
                className="h-12 text-base font-mono"
                required
              />
            </div>
          </div>

          {/* Risk/Reward Display */}
          {entry && stop && target && (
            <div className="p-4 rounded-xl bg-muted/50 border border-border">
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Risk</p>
                  <p className="text-base font-bold text-foreground">{risk.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Reward</p>
                  <p className="text-base font-bold text-foreground">{reward.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">R:R</p>
                  <Badge
                    variant="outline"
                    className={`text-sm font-bold ${
                      parseFloat(rrRatio) >= 2
                        ? "border-emerald-500/50 text-emerald-500 bg-emerald-500/10"
                        : "border-amber-500/50 text-amber-500 bg-amber-500/10"
                    }`}
                  >
                    1:{rrRatio}
                  </Badge>
                </div>
              </div>
            </div>
          )}

          {/* Thesis */}
          <div>
            <Label htmlFor="thesis" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 block">
              Trade Thesis
            </Label>
            <textarea
              id="thesis"
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              placeholder="Technical setup, fundamental catalyst, macro context..."
              className="w-full h-32 px-3 py-2 text-sm bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              required
            />
          </div>
        </form>

        {/* Footer Actions */}
        <div className="p-6 border-t border-border bg-muted/30">
          <Button
            type="submit"
            onClick={handleSubmit}
            disabled={isSubmitting || !entry || !stop || !target || !thesis}
            className="w-full h-12 text-base font-bold"
          >
            {isSubmitting ? "Staging Trade..." : "Stage for Approval"}
          </Button>
        </div>
      </div>
    </>
  );
}
