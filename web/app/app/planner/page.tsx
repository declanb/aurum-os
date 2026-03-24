"use client";

import { useState, useEffect } from "react";
import { GlassCard } from "@/components/GlassCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Save, Bot, Compass, ArrowRight, XCircle, FilePlus, ChevronRight, CheckCircle, AlertTriangle, RefreshCw } from "lucide-react";
import { fetchTrades, createTrade, updateTrade, challengeTrade, TradeIdea } from "@/lib/api";

export default function TradePlanner() {
    const [trades, setTrades] = useState<TradeIdea[]>([]);
    const [activeTrade, setActiveTrade] = useState<Partial<TradeIdea>>({
        symbol: "XAUUSD",
        direction: "LONG",
        status: "Draft"
    });
    const [isSaving, setIsSaving] = useState(false);
    const [isChallenging, setIsChallenging] = useState(false);
    const [guardianResult, setGuardianResult] = useState<any>(null);

    useEffect(() => {
        loadTrades();
    }, []);

    const loadTrades = async () => {
        const data = await fetchTrades();
        setTrades(data);
    };

    const handleSave = async () => {
        setIsSaving(true);
        if (activeTrade.id) {
            await updateTrade(activeTrade.id, activeTrade);
        } else {
            const newTrade = await createTrade(activeTrade);
            if (newTrade) setActiveTrade(newTrade);
        }
        await loadTrades();
        setIsSaving(false);
    };

    const handleChallenge = async () => {
        if (!activeTrade.id) {
            await handleSave();
        }

        if (activeTrade.id) {
            setIsChallenging(true);
            setGuardianResult(null);
            const res = await challengeTrade(activeTrade.id);
            setGuardianResult(res);
            setIsChallenging(false);
            await loadTrades();

            // Re-sync active trade if it passed
            if (res?.passed) {
                const updated = (await fetchTrades()).find(t => t.id === activeTrade.id);
                if (updated) setActiveTrade(updated);
            }
        }
    };

    const startNewTrade = () => {
        setGuardianResult(null);
        setActiveTrade({
            symbol: "XAUUSD",
            direction: "LONG",
            status: "Draft",
            entry_price: 0,
            target_price: 0,
            stop_price: 0,
            thesis: "",
            invalidation_notes: ""
        });
    }

    // Calculate Risk/Reward Naively
    const rr = (activeTrade.entry_price && activeTrade.target_price && activeTrade.stop_price)
        ? (Math.abs(activeTrade.target_price - activeTrade.entry_price) / Math.abs(activeTrade.entry_price - activeTrade.stop_price)).toFixed(2)
        : "0.00";

    return (
        <div className="flex h-[calc(100vh-8rem)] gap-6">

            {/* Left Sidebar: Trade Setup List */}
            <GlassCard className="w-80 flex flex-col shrink-0 overflow-hidden">
                <div className="p-4 border-b border-border flex justify-between items-center bg-muted/50">
                    <h3 className="font-bold text-foreground">Pending Ideas</h3>
                    <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={startNewTrade}>
                        <FilePlus className="w-4 h-4 text-emerald-500" />
                    </Button>
                </div>
                <div className="flex-1 overflow-y-auto w-full p-2 space-y-2">
                    {trades.map(trade => (
                        <button
                            key={trade.id}
                            onClick={() => {
                                setActiveTrade(trade);
                                setGuardianResult(null);
                            }}
                            className={`w-full text-left p-3 rounded-lg border transition-all ${activeTrade.id === trade.id ? 'bg-accent border-primary/50' : 'bg-card border-border hover:bg-accent/50'}`}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2">
                                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${trade.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-red-500/20 text-red-500'}`}>
                                        {trade.direction}
                                    </span>
                                    <span className="text-sm font-semibold text-foreground/90">{trade.symbol}</span>
                                </div>
                                <Badge variant="outline" className="text-[10px] py-0">{trade.status}</Badge>
                            </div>
                            <div className="text-xs text-muted-foreground truncate">{trade.thesis || "No thesis provided."}</div>
                        </button>
                    ))}
                </div>
            </GlassCard>

            {/* Main Workspace */}
            <div className="flex-1 flex flex-col overflow-y-auto">
                <div className="flex justify-between items-end mb-6">
                    <div>
                        <h1 className="text-3xl font-bold text-foreground mb-2">Trade Planner</h1>
                        <p className="text-muted-foreground text-sm">Design structural setups. Invalid parameters will be blocked by the Guardian AI.</p>
                    </div>
                    <Button
                        onClick={handleSave}
                        disabled={isSaving || activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                    >
                        {isSaving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> {activeTrade.id ? "Update Setup" : "Save Draft"}</>}
                    </Button>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 pb-8">

                    {/* Form Column */}
                    <GlassCard className="xl:col-span-2 p-6 flex flex-col gap-8">

                        {/* Metadata Header */}
                        <div className="flex items-center gap-6 pb-6 border-b border-border">
                            <div className="flex-1">
                                <Label className="text-xs text-muted-foreground uppercase tracking-wider mb-2 block">Asset</Label>
                                <div className="text-2xl font-bold text-foreground">{activeTrade.symbol}</div>
                            </div>
                            <div className="flex-1">
                                <Label className="text-xs text-muted-foreground uppercase tracking-wider mb-2 block">Bias</Label>
                                <div className="flex bg-muted rounded-lg p-1 border border-border w-fit">
                                    <button
                                        onClick={() => setActiveTrade({ ...activeTrade, direction: 'LONG' })}
                                        disabled={activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                                        className={`px-6 py-1.5 rounded-md text-sm font-bold transition-all ${activeTrade.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-500' : 'text-muted-foreground hover:text-foreground'}`}
                                    >
                                        LONG
                                    </button>
                                    <button
                                        onClick={() => setActiveTrade({ ...activeTrade, direction: 'SHORT' })}
                                        disabled={activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                                        className={`px-6 py-1.5 rounded-md text-sm font-bold transition-all ${activeTrade.direction === 'SHORT' ? 'bg-red-500/20 text-red-500' : 'text-muted-foreground hover:text-foreground'}`}
                                    >
                                        SHORT
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Price Logic */}
                        <div className="grid grid-cols-3 gap-6">
                            <div>
                                <Label className="text-muted-foreground mb-2 block">Entry Price</Label>
                                <div className="relative">
                                    <Compass className="w-4 h-4 text-muted-foreground/50 absolute left-3 top-1/2 -translate-y-1/2" />
                                    <Input
                                        type="number"
                                        value={activeTrade.entry_price || ""}
                                        disabled={activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setActiveTrade({ ...activeTrade, entry_price: parseFloat(e.target.value) || 0 })}
                                        className="pl-9 font-mono h-11"
                                        placeholder="2045.50"
                                    />
                                </div>
                            </div>
                            <div>
                                <Label className="text-muted-foreground mb-2 block">Stop Loss</Label>
                                <div className="relative">
                                    <XCircle className="w-4 h-4 text-red-500/50 absolute left-3 top-1/2 -translate-y-1/2" />
                                    <Input
                                        type="number"
                                        value={activeTrade.stop_price || ""}
                                        disabled={activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setActiveTrade({ ...activeTrade, stop_price: parseFloat(e.target.value) || 0 })}
                                        className="pl-9 text-red-400 dark:text-red-400 font-mono h-11"
                                    />
                                </div>
                            </div>
                            <div>
                                <Label className="text-muted-foreground mb-2 block">Target</Label>
                                <div className="relative">
                                    <ArrowRight className="w-4 h-4 text-emerald-500/50 absolute left-3 top-1/2 -translate-y-1/2" />
                                    <Input
                                        type="number"
                                        value={activeTrade.target_price || ""}
                                        disabled={activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setActiveTrade({ ...activeTrade, target_price: parseFloat(e.target.value) || 0 })}
                                        className="pl-9 text-emerald-500 font-mono h-11"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Thesis & Context */}
                        <div className="space-y-6 flex-1 flex flex-col">
                            <div className="flex-1 flex flex-col">
                                <Label className="text-muted-foreground mb-2 block">Trade Thesis <span className="text-destructive">*</span></Label>
                                <textarea
                                    value={activeTrade.thesis || ""}
                                    disabled={activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setActiveTrade({ ...activeTrade, thesis: e.target.value })}
                                    className="w-full h-32 bg-muted/50 border border-input rounded-xl p-4 text-foreground/80 focus:ring-1 focus:ring-ring outline-none resize-none"
                                    placeholder="Why are you taking this trade? What is the narrative?"
                                />
                            </div>
                            <div className="flex-1 flex flex-col">
                                <Label className="text-muted-foreground mb-2 block">Invalidation Notes <span className="text-destructive">*</span></Label>
                                <textarea
                                    value={activeTrade.invalidation_notes || ""}
                                    disabled={activeTrade.status === "Approved" || activeTrade.status === "Sent"}
                                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setActiveTrade({ ...activeTrade, invalidation_notes: e.target.value })}
                                    className="w-full h-24 bg-muted/50 border border-input rounded-xl p-4 text-foreground/80 focus:ring-1 focus:ring-ring outline-none resize-none"
                                    placeholder="What specific price action immediately invalidates this idea?"
                                />
                            </div>
                        </div>
                    </GlassCard>

                    {/* AI Side Panel & Risk */}
                    <div className="xl:col-span-1 flex flex-col gap-6">
                        <GlassCard className="p-5 flex flex-col">
                            <div className="pb-4 border-b border-border mb-4 flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                                    <Bot className="w-4 h-4 text-primary" />
                                </div>
                                <div>
                                    <h4 className="font-bold text-foreground text-sm">Risk Guardian</h4>
                                    <p className="text-xs text-muted-foreground">
                                        {activeTrade.id ? "Analyzing setup..." : "Save draft to analyze"}
                                    </p>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4 mb-6">
                                <div className="bg-muted p-3 rounded-lg border border-border">
                                    <div className="text-xs text-muted-foreground mb-1">Projected R:R</div>
                                    <div className="text-xl font-bold text-foreground">{rr}R</div>
                                </div>
                                <div className="bg-muted p-3 rounded-lg border border-border">
                                    <div className="text-xs text-muted-foreground mb-1">Status</div>
                                    <div className="text-sm font-bold text-primary uppercase tracking-tight">{activeTrade.status}</div>
                                </div>
                            </div>

                            {/* Guardian Result Panel */}
                            {isChallenging ? (
                                <div className="flex-1 flex flex-col items-center justify-center py-8 space-y-4">
                                    <RefreshCw className="w-8 h-8 text-primary animate-spin" />
                                    <p className="text-sm text-muted-foreground animate-pulse">Consulting Risk Engine...</p>
                                </div>
                            ) : guardianResult ? (
                                <div className={`flex-1 p-4 rounded-xl border mb-6 ${guardianResult.passed ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
                                    <div className="flex items-center gap-2 mb-2">
                                        {guardianResult.passed ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <AlertTriangle className="w-4 h-4 text-red-500" />}
                                        <span className={`font-bold text-sm ${guardianResult.passed ? 'text-emerald-500' : 'text-red-500'}`}>
                                            {guardianResult.passed ? 'PASSED' : 'FLAGGED'}
                                        </span>
                                        <span className="ml-auto text-xs font-mono">Score: {guardianResult.score}</span>
                                    </div>
                                    <p className="text-xs text-foreground/80 leading-relaxed mb-4">{guardianResult.message}</p>

                                    {!guardianResult.passed && guardianResult.issues && (
                                        <ul className="space-y-2">
                                            {guardianResult.issues.map((issue: string, i: number) => (
                                                <li key={i} className="text-[10px] text-red-400 flex gap-2">
                                                    <span className="shrink-0">•</span>
                                                    <span>{issue}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    )}

                                    {guardianResult.passed && (
                                        <p className="text-[10px] text-emerald-400">
                                            This trade has been moved to <strong>Ready for Approval</strong>. It must be signed in the Approvals tab before execution.
                                        </p>
                                    )}
                                </div>
                            ) : (
                                <div className="space-y-3 mb-6 flex-1">
                                    <div className={`flex items-start gap-3 transition-opacity ${rr !== "0.00" && parseFloat(rr) >= 1.5 ? 'opacity-100' : 'opacity-40'}`}>
                                        <CheckCircle className={`w-4 h-4 mt-0.5 ${rr !== "0.00" && parseFloat(rr) >= 1.5 ? 'text-emerald-500' : 'text-muted-foreground'}`} />
                                        <span className="text-sm text-muted-foreground">Validate Target is &gt; 1.5R</span>
                                    </div>
                                    <div className={`flex items-start gap-3 transition-opacity ${activeTrade.thesis && activeTrade.thesis.length > 20 ? 'opacity-100' : 'opacity-40'}`}>
                                        <CheckCircle className={`w-4 h-4 mt-0.5 ${activeTrade.thesis && activeTrade.thesis.length > 20 ? 'text-emerald-500' : 'text-muted-foreground'}`} />
                                        <span className="text-sm text-muted-foreground">Detailed Narrative Thesis</span>
                                    </div>
                                    <div className={`flex items-start gap-3 transition-opacity ${activeTrade.invalidation_notes ? 'opacity-100' : 'opacity-40'}`}>
                                        <CheckCircle className={`w-4 h-4 mt-0.5 ${activeTrade.invalidation_notes ? 'text-emerald-500' : 'text-muted-foreground'}`} />
                                        <span className="text-sm text-muted-foreground">Define Exact Invalidation</span>
                                    </div>
                                </div>
                            )}

                            <Button
                                onClick={handleChallenge}
                                disabled={isChallenging || (activeTrade.status !== "Draft" && activeTrade.status !== "Needs Work")}
                                className="w-full justify-between px-4 group"
                            >
                                {isChallenging ? "Running..." : "Run Guardian Challenge"}
                                <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                            </Button>
                        </GlassCard>
                    </div>

                </div>
            </div>

        </div>
    );
}

// Helper icons needed from lucide-react (handled in imports)
