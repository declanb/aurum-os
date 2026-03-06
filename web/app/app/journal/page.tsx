"use client";

import { useState, useEffect } from "react";
import { GlassCard } from "@/components/GlassCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchTrades, fetchJournalEntries, fetchTradeVersions, TradeIdea } from "@/lib/api";
import { BookOpen, Calendar, ChevronRight, Activity, TrendingUp, TrendingDown, AlignLeft } from "lucide-react";

export default function JournalDashboard() {
    const [completedTrades, setCompletedTrades] = useState<TradeIdea[]>([]);
    const [activeTrade, setActiveTrade] = useState<TradeIdea | null>(null);
    const [versions, setVersions] = useState<any[]>([]);
    const [journalEntries, setJournalEntries] = useState<any[]>([]);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        // Fetch trades that are completed (Closed, Cancelled, Sent)
        const trades = await fetchTrades();
        const completed = trades.filter(t => ["Sent", "Closed", "Cancelled"].includes(t.status));
        setCompletedTrades(completed);

        if (completed.length > 0) {
            handleSelectTrade(completed[0]);
        }
    };

    const handleSelectTrade = async (trade: TradeIdea) => {
        setActiveTrade(trade);
        const vData = await fetchTradeVersions(trade.id);
        setVersions(vData);
    }

    return (
        <div className="flex h-[calc(100vh-8rem)] gap-6">

            {/* Sidebar: Archive */}
            <GlassCard className="w-80 flex flex-col shrink-0 overflow-hidden">
                <div className="p-4 border-b border-slate-800/50 flex justify-between items-center bg-slate-900/50">
                    <h3 className="font-bold text-white flex items-center gap-2">
                        <BookOpen className="w-4 h-4 text-emerald-500" />
                        Trade Archive
                    </h3>
                </div>
                <div className="flex-1 overflow-y-auto w-full p-2 space-y-2">
                    {completedTrades.map(trade => (
                        <button
                            key={trade.id}
                            onClick={() => handleSelectTrade(trade)}
                            className={`w-full text-left p-3 rounded-lg border transition-all ${activeTrade?.id === trade.id ? 'bg-slate-800 border-emerald-500/50' : 'bg-slate-900/40 border-slate-800/50 hover:bg-slate-800/50'}`}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-semibold text-slate-200">{trade.symbol}</span>
                                </div>
                                <Badge variant="outline" className={`text-[10px] py-0 ${trade.status === 'Closed' ? 'border-amber-500/30 text-amber-500 bg-amber-500/10' : 'border-slate-700 text-slate-400'}`}>
                                    {trade.status}
                                </Badge>
                            </div>
                            <div className="flex min-w-0 items-center justify-between text-xs text-slate-500">
                                <span className="flex items-center gap-1">
                                    {trade.direction === 'LONG' ? <TrendingUp className="w-3 h-3 text-emerald-500" /> : <TrendingDown className="w-3 h-3 text-red-500" />}
                                    {trade.direction}
                                </span>
                                <span>{new Date(trade.created_at).toLocaleDateString()}</span>
                            </div>
                        </button>
                    ))}
                    {completedTrades.length === 0 && (
                        <div className="p-6 text-center text-sm text-slate-500">Archive is currently empty.</div>
                    )}
                </div>
            </GlassCard>

            {/* Main Area: Post-Mortem & Timeline */}
            {activeTrade ? (
                <div className="flex-1 flex flex-col xl:flex-row gap-6 min-w-0 overflow-hidden">

                    {/* Read-Only Trade Summary vs Reality */}
                    <div className="flex-1 flex flex-col gap-6 overflow-y-auto pr-2">
                        <div className="flex justify-between items-end">
                            <div>
                                <h1 className="text-3xl font-bold text-white mb-2">Execution Review</h1>
                                <p className="text-slate-400 text-sm">Post-mortem analysis for {activeTrade.symbol}.</p>
                            </div>
                            <Button className="bg-slate-800 hover:bg-slate-700 text-white">
                                <AlignLeft className="w-4 h-4 mr-2" /> Add Journal Note
                            </Button>
                        </div>

                        <GlassCard className="p-6">
                            <div className="flex justify-between items-start mb-6 border-b border-slate-800/50 pb-6">
                                <div>
                                    <div className="flex items-center gap-3 mb-2">
                                        <h2 className="text-2xl font-bold text-white">{activeTrade.symbol}</h2>
                                        <Badge className={`${activeTrade.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-red-500/20 text-red-500'}`}>
                                            {activeTrade.direction}
                                        </Badge>
                                    </div>
                                    <p className="text-slate-400 text-sm flex items-center gap-2">
                                        <Calendar className="w-4 h-4" /> Initiated {new Date(activeTrade.created_at).toLocaleString()}
                                    </p>
                                </div>
                            </div>

                            <div className="grid grid-cols-3 gap-4 mb-6">
                                <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                                    <div className="text-xs text-slate-500 mb-1 tracking-wider uppercase">Planned Entry</div>
                                    <div className="text-xl font-mono text-white">{activeTrade.entry_price}</div>
                                </div>
                                <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                                    <div className="text-xs text-slate-500 mb-1 tracking-wider uppercase">Stop Loss</div>
                                    <div className="text-xl font-mono text-white">{activeTrade.stop_price}</div>
                                </div>
                                <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                                    <div className="text-xs text-slate-500 mb-1 tracking-wider uppercase">Planned Target</div>
                                    <div className="text-xl font-mono text-white">{activeTrade.target_price}</div>
                                </div>
                            </div>

                            <div className="space-y-6">
                                <div>
                                    <div className="text-xs font-bold uppercase text-slate-500 mb-2">Original Thesis</div>
                                    <p className="text-slate-300 text-sm leading-relaxed p-4 bg-slate-900/30 rounded-lg border border-slate-800/50 text-wrap">
                                        {activeTrade.thesis || "No thesis provided."}
                                    </p>
                                </div>
                            </div>
                        </GlassCard>

                        {/* Simulated Analytics Card */}
                        <GlassCard className="p-6">
                            <h3 className="font-bold text-white mb-4">Execution Reality</h3>
                            <div className="flex items-center justify-center p-8 bg-slate-900/50 rounded-xl border border-dashed border-slate-800 text-slate-500 text-sm text-center">
                                <div>
                                    <Activity className="w-8 h-8 text-slate-600 mx-auto mb-3" />
                                    <p>Broker / Exchange integration required to visualize actual fill data, slippage, and PnL curve.</p>
                                </div>
                            </div>
                        </GlassCard>
                    </div>

                    {/* Right Sidebar: Timeline & Versions */}
                    <div className="w-96 flex flex-col gap-6 shrink-0">
                        <GlassCard className="flex-1 p-5 flex flex-col">
                            <h3 className="font-bold text-white mb-4 text-sm uppercase tracking-wide flex items-center gap-2">
                                <Activity className="w-4 h-4 text-amber-500" /> Version Timeline
                            </h3>
                            <div className="flex-1 overflow-y-auto pr-2 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-800 before:to-transparent">

                                {versions.map((ver, i) => (
                                    <div key={i} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active mb-8">
                                        {/* Icon */}
                                        <div className="flex items-center justify-center w-6 h-6 rounded-full border border-slate-700 bg-slate-900 text-slate-400 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
                                            <div className="w-2 h-2 bg-slate-500 rounded-full" />
                                        </div>
                                        {/* Card */}
                                        <div className="w-[calc(100%-3rem)] md:w-[calc(50%-1.5rem)] p-3 rounded border border-slate-800 bg-slate-900/80 shadow">
                                            <div className="flex items-center justify-between mb-1">
                                                <div className="font-bold text-slate-200 text-xs text-amber-500">v{ver.version_number} Draft</div>
                                            </div>
                                            <div className="text-[10px] text-slate-500 flex flex-col gap-0.5">
                                                <span>Entry: {ver.entry_price}</span>
                                                <span>Stop: {ver.stop_price}</span>
                                                <span>Target: {ver.target_price}</span>
                                            </div>
                                        </div>
                                    </div>
                                ))}

                                {versions.length === 0 && <div className="text-slate-500 text-xs italic text-center w-full">No versions recorded.</div>}

                            </div>
                        </GlassCard>
                    </div>

                </div>
            ) : (
                <div className="flex-1 flex items-center justify-center flex-col text-slate-500">
                    <BookOpen className="w-12 h-12 mb-4 opacity-20" />
                    <p>Select a trade artifact from the archive to review execution quality.</p>
                </div>
            )}

        </div>
    );
}
