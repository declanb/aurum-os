"use client";

import { useState, useEffect } from "react";
import { GlassCard } from "@/components/GlassCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Save, Bot, Compass, ArrowRight, XCircle, FilePlus, ChevronRight } from "lucide-react";
import { fetchTrades, createTrade, updateTrade, TradeIdea } from "@/lib/api";

export default function TradePlanner() {
    const [trades, setTrades] = useState<TradeIdea[]>([]);
    const [activeTrade, setActiveTrade] = useState<Partial<TradeIdea>>({
        symbol: "XAUUSD",
        direction: "LONG",
        status: "Draft"
    });
    const [isSaving, setIsSaving] = useState(false);

    useEffect(() => {
        loadTrades();
    }, []);

    const loadTrades = async () => {
        const data = await fetchTrades();
        setTrades(data);
        if (data.length > 0 && !activeTrade.id) {
            // Optional: Auto-select latest draft
        }
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

    const startNewTrade = () => {
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
                <div className="p-4 border-b border-slate-800/50 flex justify-between items-center bg-slate-900/50">
                    <h3 className="font-bold text-white">Pending Ideas</h3>
                    <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={startNewTrade}>
                        <FilePlus className="w-4 h-4 text-emerald-500" />
                    </Button>
                </div>
                <div className="flex-1 overflow-y-auto w-full p-2 space-y-2">
                    {trades.map(trade => (
                        <button
                            key={trade.id}
                            onClick={() => setActiveTrade(trade)}
                            className={`w-full text-left p-3 rounded-lg border transition-all ${activeTrade.id === trade.id ? 'bg-slate-800 border-amber-500/50' : 'bg-slate-900/40 border-slate-800/50 hover:bg-slate-800/50'}`}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2">
                                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${trade.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-red-500/20 text-red-500'}`}>
                                        {trade.direction}
                                    </span>
                                    <span className="text-sm font-semibold text-slate-200">{trade.symbol}</span>
                                </div>
                                <Badge variant="outline" className="text-[10px] py-0 border-slate-700 text-slate-400">{trade.status}</Badge>
                            </div>
                            <div className="text-xs text-slate-500 truncate">{trade.thesis || "No thesis provided."}</div>
                        </button>
                    ))}
                </div>
            </GlassCard>

            {/* Main Workspace */}
            <div className="flex-1 flex flex-col overflow-y-auto">
                <div className="flex justify-between items-end mb-6">
                    <div>
                        <h1 className="text-3xl font-bold text-white mb-2">Trade Planner</h1>
                        <p className="text-slate-400 text-sm">Design structural setups. Invalid parameters will be blocked by the Guardian AI.</p>
                    </div>
                    <Button
                        className="bg-amber-500 text-slate-950 hover:bg-amber-400 font-bold shadow-[0_0_15px_rgba(245,158,11,0.2)]"
                        onClick={handleSave}
                        disabled={isSaving}
                    >
                        {isSaving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> Save Draft</>}
                    </Button>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

                    {/* Form Column */}
                    <GlassCard className="xl:col-span-2 p-6 flex flex-col gap-8">

                        {/* Metadata Header */}
                        <div className="flex items-center gap-6 pb-6 border-b border-slate-800/50">
                            <div className="flex-1">
                                <Label className="text-xs text-slate-500 uppercase tracking-wider mb-2 block">Asset</Label>
                                <div className="text-2xl font-bold text-white">{activeTrade.symbol}</div>
                            </div>
                            <div className="flex-1">
                                <Label className="text-xs text-slate-500 uppercase tracking-wider mb-2 block">Bias</Label>
                                <div className="flex bg-slate-900 rounded-lg p-1 border border-slate-800 w-fit">
                                    <button
                                        onClick={() => setActiveTrade({ ...activeTrade, direction: 'LONG' })}
                                        className={`px-6 py-1.5 rounded-md text-sm font-bold transition-all ${activeTrade.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-500' : 'text-slate-500 hover:text-white'}`}
                                    >
                                        LONG
                                    </button>
                                    <button
                                        onClick={() => setActiveTrade({ ...activeTrade, direction: 'SHORT' })}
                                        className={`px-6 py-1.5 rounded-md text-sm font-bold transition-all ${activeTrade.direction === 'SHORT' ? 'bg-red-500/20 text-red-500' : 'text-slate-500 hover:text-white'}`}
                                    >
                                        SHORT
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Price Logic */}
                        <div className="grid grid-cols-3 gap-6">
                            <div>
                                <Label className="text-slate-400 mb-2 block">Entry Price</Label>
                                <div className="relative">
                                    <Compass className="w-4 h-4 text-slate-600 absolute left-3 top-1/2 -translate-y-1/2" />
                                    <Input
                                        type="number"
                                        value={activeTrade.entry_price || ""}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setActiveTrade({ ...activeTrade, entry_price: parseFloat(e.target.value) || 0 })}
                                        className="pl-9 bg-slate-900/50 border-slate-700 text-white font-mono h-11"
                                        placeholder="2045.50"
                                    />
                                </div>
                            </div>
                            <div>
                                <Label className="text-slate-400 mb-2 block">Stop Loss</Label>
                                <div className="relative">
                                    <XCircle className="w-4 h-4 text-red-500/50 absolute left-3 top-1/2 -translate-y-1/2" />
                                    <Input
                                        type="number"
                                        value={activeTrade.stop_price || ""}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setActiveTrade({ ...activeTrade, stop_price: parseFloat(e.target.value) || 0 })}
                                        className="pl-9 bg-slate-900/50 border-slate-700 text-red-400 font-mono h-11"
                                    />
                                </div>
                            </div>
                            <div>
                                <Label className="text-slate-400 mb-2 block">Target</Label>
                                <div className="relative">
                                    <ArrowRight className="w-4 h-4 text-emerald-500/50 absolute left-3 top-1/2 -translate-y-1/2" />
                                    <Input
                                        type="number"
                                        value={activeTrade.target_price || ""}
                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setActiveTrade({ ...activeTrade, target_price: parseFloat(e.target.value) || 0 })}
                                        className="pl-9 bg-slate-900/50 border-slate-700 text-emerald-400 font-mono h-11"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Thesis & Context */}
                        <div className="space-y-6 flex-1 flex flex-col">
                            <div className="flex-1 flex flex-col">
                                <Label className="text-slate-400 mb-2 block">Trade Thesis <span className="text-red-500">*</span></Label>
                                <textarea
                                    value={activeTrade.thesis || ""}
                                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setActiveTrade({ ...activeTrade, thesis: e.target.value })}
                                    className="w-full h-32 bg-slate-900/50 border border-slate-700 rounded-xl p-4 text-slate-300 focus:ring-1 focus:ring-amber-500 outline-none resize-none"
                                    placeholder="Why are you taking this trade? What is the narrative?"
                                />
                            </div>
                            <div className="flex-1 flex flex-col">
                                <Label className="text-slate-400 mb-2 block">Invalidation Notes <span className="text-red-500">*</span></Label>
                                <textarea
                                    value={activeTrade.invalidation_notes || ""}
                                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setActiveTrade({ ...activeTrade, invalidation_notes: e.target.value })}
                                    className="w-full h-24 bg-slate-900/50 border border-slate-700 rounded-xl p-4 text-slate-300 focus:ring-1 focus:ring-amber-500 outline-none resize-none"
                                    placeholder="What specific price action immediately invalidates this idea?"
                                />
                            </div>
                        </div>
                    </GlassCard>

                    {/* AI Side Panel & Risk */}
                    <div className="xl:col-span-1 flex flex-col gap-6">
                        <GlassCard className="p-5 flex flex-col border-amber-500/20 bg-slate-950">
                            <div className="pb-4 border-b border-slate-800 mb-4 flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
                                    <Bot className="w-4 h-4 text-amber-500" />
                                </div>
                                <div>
                                    <h4 className="font-bold text-white text-sm">Risk Guardian</h4>
                                    <p className="text-xs text-slate-500">Awaiting parameter input</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4 mb-6">
                                <div className="bg-slate-900/50 p-3 rounded-lg border border-slate-800">
                                    <div className="text-xs text-slate-500 mb-1">Projected R:R</div>
                                    <div className="text-xl font-bold text-white">{rr}R</div>
                                </div>
                                <div className="bg-slate-900/50 p-3 rounded-lg border border-slate-800">
                                    <div className="text-xs text-slate-500 mb-1">Risk Amount</div>
                                    <div className="text-xl font-bold text-white">---</div>
                                </div>
                            </div>

                            <div className="space-y-3 mb-6 flex-1">
                                {/* Dynamic checklist */}
                                <div className="flex items-start gap-3 opacity-50">
                                    <div className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center shrink-0 mt-0.5" />
                                    <span className="text-sm text-slate-400">Validate Target is &gt; 1.5R</span>
                                </div>
                                <div className="flex items-start gap-3 opacity-50">
                                    <div className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center shrink-0 mt-0.5" />
                                    <span className="text-sm text-slate-400">Check macro news calendar</span>
                                </div>
                                <div className="flex items-start gap-3 opacity-50">
                                    <div className="w-5 h-5 rounded-full border border-slate-600 flex items-center justify-center shrink-0 mt-0.5" />
                                    <span className="text-sm text-slate-400">Identify exact invalidation</span>
                                </div>
                            </div>

                            <Button
                                className="w-full bg-slate-800 hover:bg-slate-700 text-white justify-between px-4 group"
                                disabled={activeTrade.status !== "Draft" && activeTrade.status !== "Needs Work"}
                            >
                                Run Guardian Challenge
                                <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-white transition-colors" />
                            </Button>
                        </GlassCard>
                    </div>

                </div>
            </div>

        </div>
    );
}
