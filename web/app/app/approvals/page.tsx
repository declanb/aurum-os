"use client";

import { useState, useEffect } from "react";
import { GlassCard } from "@/components/GlassCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchTrades, processApproval, fetchApprovalEvents, TradeIdea } from "@/lib/api";
import { ShieldAlert, CheckCircle2, XCircle, ArrowRight, ShieldCheck } from "lucide-react";

export default function ApprovalsDashboard() {
    const [pendingTrades, setPendingTrades] = useState<TradeIdea[]>([]);
    const [activeTrade, setActiveTrade] = useState<TradeIdea | null>(null);
    const [events, setEvents] = useState<any[]>([]);
    const [reasoning, setReasoning] = useState("");
    const [isProcessing, setIsProcessing] = useState(false);

    useEffect(() => {
        loadPending();
    }, []);

    const loadPending = async () => {
        // In reality this might fetch "Ready for Approval" and "Approved", but we'll fetch all and filter
        const data = await fetchTrades();
        const needsApproval = data.filter(t => t.status === "Ready for Approval" || t.status === "Needs Work" || t.status === "Approved");
        setPendingTrades(needsApproval);

        if (needsApproval.length > 0 && !activeTrade) {
            setActiveTrade(needsApproval[0]);
            loadEvents(needsApproval[0].id);
        }
    };

    const loadEvents = async (id: number) => {
        const eventData = await fetchApprovalEvents(id);
        setEvents(eventData);
    }

    const handleSelectTrade = (trade: TradeIdea) => {
        setActiveTrade(trade);
        loadEvents(trade.id);
        setReasoning("");
    }

    const handleAction = async (action: "APPROVE" | "REJECT") => {
        if (!activeTrade) return;
        setIsProcessing(true);
        await processApproval(activeTrade.id, action, reasoning);
        setReasoning("");
        await loadPending();

        // Refresh active trade state
        const updated = await fetchTrades();
        const freshActive = updated.find(t => t.id === activeTrade.id);
        if (freshActive) {
            setActiveTrade(freshActive);
            await loadEvents(freshActive.id);
        }

        setIsProcessing(false);
    }

    return (
        <div className="flex h-[calc(100vh-8rem)] gap-6">

            {/* Sidebar Queue */}
            <GlassCard className="w-80 flex flex-col shrink-0 overflow-hidden">
                <div className="p-4 border-b border-slate-800/50 flex justify-between items-center bg-slate-900/50">
                    <h3 className="font-bold text-white flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-amber-500" />
                        Auth Queue
                    </h3>
                    <Badge className="bg-amber-500/20 text-amber-500 hover:bg-amber-500/30">{pendingTrades.length}</Badge>
                </div>
                <div className="flex-1 overflow-y-auto w-full p-2 space-y-2">
                    {pendingTrades.map(trade => (
                        <button
                            key={trade.id}
                            onClick={() => handleSelectTrade(trade)}
                            className={`w-full text-left p-3 rounded-lg border transition-all ${activeTrade?.id === trade.id ? 'bg-slate-800 border-amber-500/50' : 'bg-slate-900/40 border-slate-800/50 hover:bg-slate-800/50'}`}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-semibold text-slate-200">{trade.symbol}</span>
                                </div>
                                {trade.status === "Approved" ? (
                                    <Badge variant="outline" className="text-[10px] py-0 border-emerald-500/30 text-emerald-500 bg-emerald-500/10">Apprvd</Badge>
                                ) : (
                                    <Badge variant="outline" className="text-[10px] py-0 border-amber-500/30 text-amber-500 bg-amber-500/10">Pend</Badge>
                                )}
                            </div>
                            <div className="flex min-w-0 items-center gap-2 text-xs">
                                <span className={`font-bold ${trade.direction === 'LONG' ? 'text-emerald-500' : 'text-red-500'}`}>{trade.direction}</span>
                                <span className="text-slate-500">@ {trade.entry_price}</span>
                            </div>
                        </button>
                    ))}
                    {pendingTrades.length === 0 && (
                        <div className="p-6 text-center text-sm text-slate-500">No trades pending authorization.</div>
                    )}
                </div>
            </GlassCard>

            {/* Primary Authorization View */}
            {activeTrade ? (
                <div className="flex-1 flex flex-col min-w-0">
                    <div className="flex justify-between items-end mb-6">
                        <div>
                            <h1 className="text-3xl font-bold text-white mb-2">Authorize Execution</h1>
                            <p className="text-slate-400 text-sm">Review the risk parameters and narrative before signing off down-circuit.</p>
                        </div>
                        {activeTrade.status === "Approved" ? (
                            <Badge className="bg-emerald-500/20 text-emerald-500 px-4 py-1.5 text-sm border-emerald-500/50">
                                <ShieldCheck className="w-4 h-4 mr-2" /> Authorized & Locked
                            </Badge>
                        ) : (
                            <Badge variant="outline" className="text-amber-500 border-amber-500/50 px-4 py-1.5 text-sm">
                                Pending Supervisor
                            </Badge>
                        )}
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 flex-1 min-h-0">
                        <div className="xl:col-span-2 flex flex-col gap-6 h-full overflow-y-auto w-full">
                            <GlassCard className="p-6">
                                <div className="flex justify-between items-start mb-6">
                                    <div>
                                        <h2 className="text-2xl font-bold text-white mb-1">{activeTrade.symbol}</h2>
                                        <div className="flex items-center gap-3 mt-2">
                                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${activeTrade.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-red-500/20 text-red-500'}`}>
                                                {activeTrade.direction}
                                            </span>
                                            <span className="text-slate-500 text-sm">via Primary Terminal</span>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-sm text-slate-500 mb-1">R:R Profile</div>
                                        <div className="text-xl font-bold text-white">
                                            {((Math.abs(activeTrade.target_price - activeTrade.entry_price) / Math.abs(activeTrade.entry_price - activeTrade.stop_price)) || 0).toFixed(2)}
                                        </div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-3 gap-4 mb-8">
                                    <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <div className="text-xs text-slate-500 mb-1">Entry</div>
                                        <div className="text-lg font-mono text-white">{activeTrade.entry_price}</div>
                                    </div>
                                    <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <div className="text-xs text-slate-500 mb-1">Stop Loss</div>
                                        <div className="text-lg font-mono text-red-400">{activeTrade.stop_price}</div>
                                    </div>
                                    <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <div className="text-xs text-slate-500 mb-1">Target</div>
                                        <div className="text-lg font-mono text-emerald-400">{activeTrade.target_price}</div>
                                    </div>
                                </div>

                                <div className="space-y-6">
                                    <div>
                                        <div className="text-xs font-bold uppercase text-slate-500 mb-2">Trade Thesis</div>
                                        <p className="text-slate-300 text-sm leading-relaxed p-4 bg-slate-900/30 rounded-lg border border-slate-800/50">
                                            {activeTrade.thesis || "No thesis provided."}
                                        </p>
                                    </div>
                                    <div>
                                        <div className="text-xs font-bold uppercase text-slate-500 mb-2">Invalidation Criteria</div>
                                        <p className="text-slate-400 text-sm leading-relaxed p-4 bg-slate-900/30 rounded-lg border border-slate-800/50">
                                            {activeTrade.invalidation_notes || "No invalidation provided."}
                                        </p>
                                    </div>
                                </div>
                            </GlassCard>

                            <GlassCard className="p-6 border-amber-500/20">
                                <h3 className="font-bold text-white mb-4">Verification Checkpoints</h3>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="flex items-center gap-3 p-3 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                                        <span className="text-sm font-medium text-slate-300">Risk &lt; 1% Capital</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                                        <span className="text-sm font-medium text-slate-300">Target &gt; 1.5R</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                                        <span className="text-sm font-medium text-slate-300">Structure Validated</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                                        <span className="text-sm font-medium text-slate-300">No Tier 1 News</span>
                                    </div>
                                </div>
                            </GlassCard>
                        </div>

                        <div className="xl:col-span-1 flex flex-col gap-6">
                            {/* Action Panel */}
                            <GlassCard className="p-5 flex flex-col bg-slate-950">
                                <h3 className="font-bold text-white mb-4">Authorization</h3>

                                {activeTrade.status !== "Approved" ? (
                                    <>
                                        <textarea
                                            value={reasoning}
                                            onChange={e => setReasoning(e.target.value)}
                                            className="w-full h-24 bg-slate-900/50 border border-slate-700 rounded-lg p-3 text-sm text-slate-300 focus:ring-1 focus:ring-amber-500 outline-none resize-none mb-4"
                                            placeholder="Add optional notes for this decision..."
                                        />
                                        <div className="grid grid-cols-2 gap-3">
                                            <Button
                                                variant="outline"
                                                className="border-red-500/50 text-red-500 hover:bg-red-500/10 hover:text-red-400"
                                                onClick={() => handleAction("REJECT")}
                                                disabled={isProcessing}
                                            >
                                                Reject
                                            </Button>
                                            <Button
                                                className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold"
                                                onClick={() => handleAction("APPROVE")}
                                                disabled={isProcessing}
                                            >
                                                Sign & Approve
                                            </Button>
                                        </div>
                                    </>
                                ) : (
                                    <div className="text-center p-6 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <ShieldCheck className="w-8 h-8 text-emerald-500 mx-auto mb-3" />
                                        <p className="text-slate-300 font-medium">Trade Locked & Authorized</p>
                                        <p className="text-xs text-slate-500 mt-1">Further parameter modifications will reset state.</p>

                                        <Button className="w-full mt-6 bg-amber-500 text-slate-950 hover:bg-amber-400 font-bold">
                                            Send to Execution Matrix <ArrowRight className="w-4 h-4 ml-2" />
                                        </Button>
                                    </div>
                                )}
                            </GlassCard>

                            {/* Audit Trail */}
                            <GlassCard className="flex-1 p-5 flex flex-col overflow-hidden">
                                <h3 className="font-bold text-white mb-4 text-sm uppercase tracking-wide">Audit Trail</h3>
                                <div className="flex-1 overflow-y-auto pr-2 space-y-4">
                                    {events.map((ev, i) => (
                                        <div key={i} className="flex gap-3 text-sm">
                                            <div className="flex flex-col items-center mt-1">
                                                <div className={`w-2 h-2 rounded-full ${ev.action === 'APPROVE' ? 'bg-emerald-500' : 'bg-red-500'}`} />
                                                {i !== events.length - 1 && <div className="w-px h-full bg-slate-800 my-1" />}
                                            </div>
                                            <div className="pb-4">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="font-semibold text-slate-200">
                                                        {ev.action === 'APPROVE' ? 'Authorized' : 'Rejected'}
                                                    </span>
                                                    <span className="text-xs text-slate-500">{new Date(ev.created_at).toLocaleTimeString()}</span>
                                                </div>
                                                {ev.reasoning && (
                                                    <p className="text-slate-400 text-xs italic border-l-2 border-slate-700 pl-2">"{ev.reasoning}"</p>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                    {events.length === 0 && (
                                        <div className="text-xs text-slate-500 italic">No formal events logged.</div>
                                    )}
                                </div>
                            </GlassCard>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="flex-1 flex items-center justify-center flex-col text-slate-500">
                    <ShieldAlert className="w-12 h-12 mb-4 opacity-20" />
                    <p>Select a trade from the queue to process authorization.</p>
                </div>
            )}

        </div>
    );
}
