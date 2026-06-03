"use client";

import { useState, useEffect, useCallback } from "react";
import { Sparkles, TrendingUp, TrendingDown, Target, Shield, Zap, RefreshCw, BookOpen, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  fetchRecommendations,
  fetchPlaybooks,
  fetchEdge,
  createTrade,
  type TradeRecommendation,
  type PlaybookSummary,
  type EdgeFingerprint,
} from "@/lib/api";

interface AiRecommendationsProps {
  onTradeCreated?: () => void;
}

export function AiRecommendations({ onTradeCreated }: AiRecommendationsProps) {
  const [recommendations, setRecommendations] = useState<TradeRecommendation[]>([]);
  const [playbooks, setPlaybooks] = useState<PlaybookSummary[]>([]);
  const [selectedPlaybook, setSelectedPlaybook] = useState<string>("trend_follower");
  const [edge, setEdge] = useState<EdgeFingerprint | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRecommendations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRecommendations(
        "BTC-USD,ETH-USD,SOL-USD",
        3,
        selectedPlaybook,
      );
      setRecommendations(data);
    } catch (err) {
      setError("Failed to load recommendations");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [selectedPlaybook]);

  // Load playbooks + edge once on mount
  useEffect(() => {
    fetchPlaybooks().then(setPlaybooks);
    fetchEdge().then(setEdge);
  }, []);

  // Reload recommendations whenever the playbook changes
  useEffect(() => {
    loadRecommendations();
  }, [loadRecommendations]);

  const handleQuickExecute = async (rec: TradeRecommendation) => {
    if (!rec.direction) return;
    
    try {
      const result = await createTrade({
        symbol: rec.symbol,
        direction: rec.direction,
        entry_price: rec.entry_price,
        stop_price: rec.stop_price,
        target_price: rec.target_price,
        thesis: rec.thesis,
        invalidation_notes: rec.invalidation,
        status: "Draft", // Start as draft for Guardian review
      });

      if (result) {
        alert(`Trade created for ${rec.symbol}! Review in Approvals.`);
        onTradeCreated?.();
      }
    } catch (err) {
      console.error("Failed to create trade:", err);
      alert("Failed to create trade. Check console.");
    }
  };

  return (
    <Card className="p-6 bg-linear-to-br from-card via-card to-primary/5 border-primary/20">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Sparkles className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-foreground">AI Trade Advisor</h3>
            <p className="text-xs text-muted-foreground">
              GPT-4 · trader playbook lens · your personal edge
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={loadRecommendations}
          disabled={loading}
          className="gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Playbook selector */}
      {playbooks.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2">
            <BookOpen className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Trader Lens
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {playbooks.map((pb) => {
              const active = pb.id === selectedPlaybook;
              return (
                <button
                  key={pb.id}
                  onClick={() => setSelectedPlaybook(pb.id)}
                  disabled={loading}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                    active
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-card border-border text-muted-foreground hover:text-foreground hover:border-primary/40"
                  }`}
                  title={`${pb.trader} · ${pb.style}`}
                >
                  {pb.name}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Personal edge banner */}
      {edge && (
        <div className="mb-4 p-3 rounded-lg bg-primary/5 border border-primary/20">
          <div className="flex items-center gap-2 mb-1.5">
            <User className="w-3.5 h-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">
              Your edge from {edge.sample_size} approved trades
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {edge.long_bias_pct}% LONG · typical R:R {edge.avg_risk_reward ?? "–"} · typical risk {edge.avg_risk_pct ?? "–"}%
            {edge.favourite_symbols.length > 0 && (
              <> · favourites: {edge.favourite_symbols.map((s) => s.symbol).join(", ")}</>
            )}
          </p>
        </div>
      )}

      {/* Loading State */}
      {loading && recommendations.length === 0 && (
        <div className="text-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin text-primary mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">Analyzing markets...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="text-center py-8 text-destructive">
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Recommendations List */}
      {!loading && recommendations.length === 0 && !error && (
        <div className="text-center py-12">
          <Sparkles className="w-8 h-8 text-muted-foreground mx-auto mb-3 opacity-50" />
          <p className="text-sm text-muted-foreground">No high-confidence setups right now</p>
          <p className="text-xs text-muted-foreground mt-1">Check back in a few minutes</p>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="space-y-4">
          {recommendations.map((rec, index) => (
            <RecommendationCard
              key={`${rec.symbol}-${index}`}
              recommendation={rec}
              onExecute={() => handleQuickExecute(rec)}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

interface RecommendationCardProps {
  recommendation: TradeRecommendation;
  onExecute: () => void;
}

function RecommendationCard({ recommendation: rec, onExecute }: RecommendationCardProps) {
  const isLong = rec.direction === "LONG";
  const directionColor = isLong ? "text-emerald-500" : "text-red-500";
  const directionBg = isLong ? "bg-emerald-500/10" : "bg-red-500/10";
  const directionBorder = isLong ? "border-emerald-500/30" : "border-red-500/30";
  
  const confidenceColor = 
    rec.confidence_score >= 75 ? "text-emerald-500" :
    rec.confidence_score >= 60 ? "text-yellow-500" : "text-orange-500";

  return (
    <div className={`p-4 rounded-xl border-2 ${directionBorder} ${directionBg} transition-all hover:scale-[1.02]`}>
      {/* Header Row */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {isLong ? (
            <TrendingUp className={`w-6 h-6 ${directionColor}`} />
          ) : (
            <TrendingDown className={`w-6 h-6 ${directionColor}`} />
          )}
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-base font-bold font-mono text-foreground">
                {rec.symbol}
              </span>
              <Badge variant="outline" className={`${directionColor} border-current`}>
                {rec.direction}
              </Badge>
              {rec.playbook_used && (
                <Badge variant="secondary" className="gap-1 text-[10px]" title={rec.playbook_used.trader}>
                  <BookOpen className="w-2.5 h-2.5" />
                  {rec.playbook_used.name}
                </Badge>
              )}
              {typeof rec.edge_match_score === "number" && (
                <Badge
                  variant="secondary"
                  className={`gap-1 text-[10px] ${
                    rec.edge_match_score >= 70
                      ? "bg-emerald-500/10 text-emerald-500"
                      : rec.edge_match_score >= 50
                      ? "bg-yellow-500/10 text-yellow-600"
                      : "bg-orange-500/10 text-orange-500"
                  }`}
                  title="How well this matches your past approved trades"
                >
                  <User className="w-2.5 h-2.5" />
                  Edge {rec.edge_match_score}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">{rec.timeframe} timeframe</p>
          </div>
        </div>

        {/* Confidence Score */}
        <div className="text-right">
          <div className={`text-2xl font-bold ${confidenceColor}`}>
            {rec.confidence_score}%
          </div>
          <p className="text-xs text-muted-foreground">confidence</p>
        </div>
      </div>

      {/* Thesis */}
      <p className="text-sm text-foreground mb-3 leading-relaxed">
        {rec.thesis}
      </p>

      {/* Price Levels */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="bg-card/50 p-2 rounded-lg">
          <div className="flex items-center gap-1 mb-1">
            <Target className="w-3 h-3 text-primary" />
            <span className="text-xs text-muted-foreground">Entry</span>
          </div>
          <span className="text-sm font-bold font-mono text-foreground">
            ${rec.entry_price.toLocaleString()}
          </span>
        </div>

        <div className="bg-card/50 p-2 rounded-lg">
          <div className="flex items-center gap-1 mb-1">
            <Shield className="w-3 h-3 text-red-500" />
            <span className="text-xs text-muted-foreground">Stop</span>
          </div>
          <span className="text-sm font-bold font-mono text-foreground">
            ${rec.stop_price.toLocaleString()}
          </span>
        </div>

        <div className="bg-card/50 p-2 rounded-lg">
          <div className="flex items-center gap-1 mb-1">
            <Target className="w-3 h-3 text-emerald-500" />
            <span className="text-xs text-muted-foreground">Target</span>
          </div>
          <span className="text-sm font-bold font-mono text-foreground">
            ${rec.target_price.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Risk/Reward */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-muted-foreground">Risk:Reward Ratio</span>
        <Badge variant="secondary" className="font-mono">
          1:{rec.risk_reward.toFixed(2)}
        </Badge>
      </div>

      {/* Action Button */}
      <Button 
        onClick={onExecute}
        className="w-full gap-2"
        variant="default"
        size="sm"
      >
        <Zap className="w-4 h-4" />
        Create Trade Idea
      </Button>

      {/* Reasoning (Expandable) */}
      <details className="mt-3">
        <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
          View detailed analysis
        </summary>
        <div className="mt-2 p-3 bg-card/30 rounded-lg border border-border">
          <p className="text-xs text-muted-foreground leading-relaxed mb-2">
            {rec.reasoning}
          </p>
          <div className="pt-2 border-t border-border">
            <span className="text-xs font-semibold text-red-500">Invalidation: </span>
            <span className="text-xs text-muted-foreground">{rec.invalidation}</span>
          </div>
        </div>
      </details>
    </div>
  );
}
