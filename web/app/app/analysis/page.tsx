"use client";

import { useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Save, AlertCircle, RefreshCw } from "lucide-react";
import { createNote } from "@/lib/api";

export default function AnalysisWorkspace() {
    const [isSaving, setIsSaving] = useState(false);
    const [formData, setFormData] = useState({
        timeframe: "4H",
        market_state: "Trending Bullish",
        support_levels: "2028.50, 2015.00",
        resistance_levels: "2055.00, 2080.00",
        content: ""
    });

    const handleSave = async () => {
        setIsSaving(true);
        await createNote({
            symbol: "XAUUSD",
            ...formData
        });
        // In a real app we would mutate SWR or refetch here
        setIsSaving(false);
    };

    return (
        <div className="space-y-6 max-w-7xl mx-auto h-[calc(100vh-8rem)] flex flex-col">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-white mb-1">Market Analysis</h1>
                    <p className="text-slate-400">Contextualize price action and validate market state.</p>
                </div>
                <div className="flex gap-3">
                    <Button variant="outline" className="text-slate-300 border-slate-700 hover:bg-slate-800">
                        <RefreshCw className="w-4 h-4 mr-2" /> Refresh Chart
                    </Button>
                    <Button
                        className="bg-amber-500 text-slate-950 font-bold hover:bg-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.2)]"
                        onClick={handleSave}
                        disabled={isSaving}
                    >
                        {isSaving ? "Saving..." : <><Save className="w-4 h-4 mr-2" /> Save Snapshot</>}
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
                {/* Left Column: Chart & State */}
                <div className="col-span-1 lg:col-span-2 flex flex-col gap-6 h-full">
                    {/* Chart Placeholder */}
                    <GlassCard className="flex-1 flex flex-col overflow-hidden min-h-[400px]">
                        <div className="h-12 border-b border-slate-800/50 bg-slate-900/50 px-4 flex items-center justify-between shrink-0">
                            <div className="flex items-center gap-4">
                                <span className="text-white font-bold tracking-wide">XAUUSD</span>
                                <div className="flex gap-2">
                                    {['1H', '4H', 'D', 'W'].map(tf => (
                                        <button
                                            key={tf}
                                            onClick={() => setFormData(p => ({ ...p, timeframe: tf }))}
                                            className={`text-xs px-2 py-1 rounded transition-colors ${formData.timeframe === tf ? 'bg-slate-800 text-amber-500 font-medium' : 'text-slate-500 hover:text-slate-300'}`}
                                        >
                                            {tf}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
                                <span className="text-xs text-slate-400">Live feed connected</span>
                            </div>
                        </div>

                        {/* Fake Chart Area */}
                        <div className="flex-1 relative bg-slate-950/80 p-6 flex flex-col items-center justify-center">

                            {/* Simulated Candle sticks */}
                            <div className="flex items-end justify-center w-full h-full gap-2 opacity-30 pb-10 border-b border-slate-800 pointer-events-none">
                                {[40, 60, 45, 80, 75, 90, 85, 120, 110, 140, 130, 160].map((h, i) => (
                                    <div key={i} className={`w-3 relative ${i % 2 === 0 ? 'bg-emerald-500' : 'bg-red-500'} rounded-sm`} style={{ height: `${h}px` }}>
                                        <div className={`absolute left-1/2 -translate-x-1/2 w-px h-8 -top-8 ${i % 2 === 0 ? 'bg-emerald-500' : 'bg-red-500'}`} />
                                        <div className={`absolute left-1/2 -translate-x-1/2 w-px h-8 -bottom-8 ${i % 2 === 0 ? 'bg-emerald-500' : 'bg-red-500'}`} />
                                    </div>
                                ))}
                            </div>

                            <div className="absolute inset-0 flex flex-col items-center justify-center opacity-40">
                                <AlertCircle className="w-12 h-12 text-slate-600 mb-2" />
                                <p className="text-slate-500 text-sm">TradingView Widget / Advanced Charting Integration Point</p>
                            </div>
                        </div>
                    </GlassCard>

                    {/* Market Facts Row */}
                    <div className="grid grid-cols-3 gap-6 shrink-0 h-32">
                        <Card className="bg-slate-900/50 border-slate-800">
                            <CardHeader className="p-4 pb-2">
                                <CardTitle className="text-xs font-semibold uppercase text-slate-500 tracking-wider">Market State</CardTitle>
                            </CardHeader>
                            <CardContent className="p-4 pt-0">
                                <input
                                    value={formData.market_state}
                                    onChange={(e) => setFormData(p => ({ ...p, market_state: e.target.value }))}
                                    className="bg-transparent border-none text-white font-medium p-0 focus:ring-0 w-full placeholder:text-slate-700"
                                    placeholder="e.g. Range Bound"
                                />
                                <div className="w-full h-1 bg-amber-500/20 rounded-full mt-3">
                                    <div className="h-full bg-amber-500 rounded-full w-2/3 shadow-[0_0_10px_rgba(245,158,11,0.5)]"></div>
                                </div>
                            </CardContent>
                        </Card>
                        <Card className="bg-slate-900/50 border-slate-800">
                            <CardHeader className="p-4 pb-2">
                                <CardTitle className="text-xs font-semibold uppercase text-slate-500 tracking-wider">Key Resistance</CardTitle>
                            </CardHeader>
                            <CardContent className="p-4 pt-0">
                                <input
                                    value={formData.resistance_levels}
                                    onChange={(e) => setFormData(p => ({ ...p, resistance_levels: e.target.value }))}
                                    className="bg-transparent border-none text-red-400 font-mono text-lg font-bold p-0 focus:ring-0 w-full placeholder:text-slate-700"
                                />
                            </CardContent>
                        </Card>
                        <Card className="bg-slate-900/50 border-slate-800">
                            <CardHeader className="p-4 pb-2">
                                <CardTitle className="text-xs font-semibold uppercase text-slate-500 tracking-wider">Key Support</CardTitle>
                            </CardHeader>
                            <CardContent className="p-4 pt-0">
                                <input
                                    value={formData.support_levels}
                                    onChange={(e) => setFormData(p => ({ ...p, support_levels: e.target.value }))}
                                    className="bg-transparent border-none text-emerald-400 font-mono text-lg font-bold p-0 focus:ring-0 w-full placeholder:text-slate-700"
                                />
                            </CardContent>
                        </Card>
                    </div>
                </div>

                {/* Right Column: AI Analysis & Structured Notes */}
                <div className="col-span-1 flex flex-col gap-6 h-full">
                    <GlassCard className="flex-1 flex flex-col overflow-hidden">
                        <div className="p-4 border-b border-slate-800 flex items-center justify-between shrink-0">
                            <h3 className="font-bold text-white flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                                Observer AI
                            </h3>
                            <Badge variant="outline" className="text-slate-400 border-slate-700">Analyst Agent</Badge>
                        </div>
                        <div className="p-4 flex-1 overflow-y-auto font-mono text-sm text-slate-400 space-y-4">
                            <p className="text-emerald-500/80">
                                &gt; Analyzing price structure on 4H...<br />
                                &gt; Strong reaction off 2028.50 detected.<br />
                                &gt; Market forming higher highs.
                            </p>
                            <p className="text-slate-300">
                                Based on context, current structure remains fundamentally bullish. However, proximity to 2055.00 resistance suggests caution for immediate longs.
                            </p>
                            <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
                                <p className="text-amber-500 font-bold mb-1 border-b border-slate-800/50 pb-1">AI Prompt Hook</p>
                                <p className="text-xs">Once connected to AI SDK, this panel will stream analysis from the Market Analyst agent, challenging structural interpretations in real-time.</p>
                            </div>
                        </div>
                    </GlassCard>

                    <GlassCard className="h-2/5 shrink-0 flex flex-col border-amber-500/20 shadow-[0_0_30px_rgba(245,158,11,0.05)]">
                        <div className="p-4 px-5 border-b border-slate-800/50 flex space-between items-center bg-slate-900/50">
                            <h3 className="font-bold text-white text-sm uppercase tracking-widest">My Context Notes</h3>
                        </div>
                        <div className="flex-1 p-0">
                            <textarea
                                value={formData.content}
                                onChange={(e) => setFormData(p => ({ ...p, content: e.target.value }))}
                                placeholder="Enter your interpretation here... (e.g. 'Waiting for London open to confirm direction.')"
                                className="w-full h-full bg-transparent border-none text-slate-300 placeholder:text-slate-600 p-5 font-mono text-sm focus:ring-0 resize-none outline-none"
                            />
                        </div>
                    </GlassCard>
                </div>
            </div>
        </div>
    );
}
