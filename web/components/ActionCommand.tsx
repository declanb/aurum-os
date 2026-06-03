"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Zap, ShieldCheck, TrendingUp, Clock } from "lucide-react";
import Link from "next/link";

interface ActionCommandProps {
  pendingApprovals: number;
  activeTrades: number;
  onQuickTrade: () => void;
}

export function ActionCommand({ pendingApprovals, activeTrades, onQuickTrade }: ActionCommandProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Primary Action - Quick Trade */}
      <button
        onClick={onQuickTrade}
        className="group relative overflow-hidden p-6 rounded-2xl border-2 border-primary bg-linear-to-br from-primary/10 to-primary/5 hover:from-primary/20 hover:to-primary/10 transition-all duration-300 text-left"
      >
        <div className="relative z-10">
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-xl bg-primary/20 flex items-center justify-center group-hover:scale-110 transition-transform">
              <Zap className="w-6 h-6 text-primary" />
            </div>
            <Badge variant="outline" className="border-primary/50 text-primary">Hot</Badge>
          </div>
          <h3 className="text-xl font-bold text-foreground mb-2">Quick Trade</h3>
          <p className="text-sm text-muted-foreground">Launch trade setup in seconds</p>
        </div>
        <div className="absolute inset-0 bg-linear-to-br from-primary/0 to-primary/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      </button>

      {/* Pending Approvals */}
      <Link
        href="/app/approvals"
        className="group relative overflow-hidden p-6 rounded-2xl border-2 border-border bg-card hover:border-primary/50 hover:bg-accent transition-all duration-300 text-left"
      >
        <div className="relative z-10">
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center group-hover:scale-110 transition-transform">
              <ShieldCheck className="w-6 h-6 text-foreground" />
            </div>
            {pendingApprovals > 0 && (
              <Badge variant="destructive" className="animate-pulse">
                {pendingApprovals}
              </Badge>
            )}
          </div>
          <h3 className="text-xl font-bold text-foreground mb-2">Approvals</h3>
          <p className="text-sm text-muted-foreground">
            {pendingApprovals > 0 ? `${pendingApprovals} trade${pendingApprovals > 1 ? "s" : ""} awaiting auth` : "All clear"}
          </p>
        </div>
      </Link>

      {/* Active Positions */}
      <Link
        href="/app/planner"
        className="group relative overflow-hidden p-6 rounded-2xl border-2 border-border bg-card hover:border-emerald-500/50 hover:bg-accent transition-all duration-300 text-left"
      >
        <div className="relative z-10">
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
              <TrendingUp className="w-6 h-6 text-emerald-500" />
            </div>
            <Badge variant="outline" className="border-emerald-500/50 text-emerald-500">
              {activeTrades}
            </Badge>
          </div>
          <h3 className="text-xl font-bold text-foreground mb-2">Active Trades</h3>
          <p className="text-sm text-muted-foreground">Monitor open positions</p>
        </div>
      </Link>

      {/* Market Analysis */}
      <Link
        href="/app/analysis"
        className="group relative overflow-hidden p-6 rounded-2xl border-2 border-border bg-card hover:border-blue-500/50 hover:bg-accent transition-all duration-300 text-left"
      >
        <div className="relative z-10">
          <div className="flex items-start justify-between mb-4">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
              <Clock className="w-6 h-6 text-blue-500" />
            </div>
          </div>
          <h3 className="text-xl font-bold text-foreground mb-2">Market Notes</h3>
          <p className="text-sm text-muted-foreground">Technical & fundamental context</p>
        </div>
      </Link>
    </div>
  );
}
