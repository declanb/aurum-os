"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/GlassCard";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchTrades, fetchJournalEntries, fetchVantageAccount, TradeIdea } from "@/lib/api";

export default function Dashboard() {
    const [trades, setTrades] = useState<TradeIdea[]>([]);
    const [journalEntries, setJournalEntries] = useState<any[]>([]);
    const [account, setAccount] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function loadData() {
            try {
                const [tradesData, journalData, accountData] = await Promise.all([
                    fetchTrades(),
                    fetchJournalEntries(),
                    fetchVantageAccount()
                ]);
                setTrades(tradesData);
                setJournalEntries(journalData);
                setAccount(accountData);
            } catch (error) {
                console.error("Dashboard load failed:", error);
            } finally {
                setLoading(false);
            }
        }
        loadData();
    }, []);

    const pendingCount = trades.filter(t => t.status === "Ready for Approval").length;

    return (
        <div className="space-y-8 max-w-7xl mx-auto">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-foreground mb-1">Morning, Declan.</h1>
                    <p className="text-muted-foreground">Here is your daily briefing and market overview.</p>
                </div>
                <div className="text-left md:text-right">
                    <div className="text-2xl font-bold text-primary">XAU/USD</div>
                    <div className="text-sm text-muted-foreground">2045.50 <span className="text-emerald-500">+12.40</span></div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <GlassCard className="p-5 md:col-span-3 min-h-[300px] flex flex-col justify-between">
                    <div>
                        <div className="flex items-center gap-2 mb-4">
                            <Badge variant="outline" className="text-primary border-primary/20 bg-primary/10">AI Briefing</Badge>
                            <span className="text-xs text-muted-foreground">Generated 10 mins ago</span>
                        </div>
                        <p className="text-foreground/80 leading-relaxed max-w-3xl">
                            Market state is currently in a high-timeframe consolidation forming a bullish flag below 2050 resistance.
                            The Asian session swept local lows, leaving an untapped order block around 2028.
                            Agents recommend extreme patience today. Do not force longs unless a clear H1 close above 2055 confirms momentum.
                        </p>
                    </div>
                    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 text-sm text-muted-foreground border-t border-border pt-4 mt-6">
                        <span>Daily Bias: <span className="text-foreground font-medium">Neutral / Bullish</span></span>
                        <span className="hidden sm:inline-block text-border">•</span>
                        <span>Key Support: <span className="text-foreground font-medium">2028.00</span></span>
                        <span className="hidden sm:inline-block text-border">•</span>
                        <span>Key Resistance: <span className="text-foreground font-medium">2055.00</span></span>
                    </div>
                </GlassCard>

                <Card className="flex flex-col">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Pending Action</CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 flex flex-col justify-center">
                        <div className="text-5xl font-bold text-foreground mb-2">
                            {loading ? "..." : pendingCount}
                        </div>
                        <p className="text-sm text-muted-foreground">Trade awaiting your approval</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-lg text-foreground font-semibold">Account Performance</CardTitle>
                        {account && (
                            <Badge variant="outline" className="text-[10px] text-emerald-500 border-emerald-500/20 bg-emerald-500/5">
                                {account.broker || "Vantage"} Live
                            </Badge>
                        )}
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-6 pt-2">
                            <div>
                                <p className="text-xs text-muted-foreground uppercase tracking-widest mb-1">Current Balance</p>
                                <p className="text-2xl font-bold text-foreground">
                                    {account ? `$${account.balance?.toLocaleString()}` : "$0.00"}
                                </p>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground uppercase tracking-widest mb-1">Portfolio Equity</p>
                                <p className="text-2xl font-bold text-primary">
                                    {account ? `$${account.equity?.toLocaleString()}` : "$0.00"}
                                </p>
                            </div>
                        </div>
                        <div className="mt-8 pt-6 border-t border-border/50">
                            <h4 className="text-sm font-medium text-foreground mb-4">Risk Profile Tracker</h4>
                            <div className="space-y-4">
                                <div className="flex flex-col gap-1">
                                    <div className="flex justify-between items-center text-xs">
                                        <span className="text-muted-foreground">Max Risk per Trade</span>
                                        <span className="font-medium text-foreground">1.0%</span>
                                    </div>
                                    <div className="w-full h-1 bg-muted rounded-full overflow-hidden">
                                        <div className="w-1/4 h-full bg-emerald-500 rounded-full"></div>
                                    </div>
                                </div>
                                <div className="flex flex-col gap-1">
                                    <div className="flex justify-between items-center text-xs">
                                        <span className="text-muted-foreground">Daily Drawdown Limit</span>
                                        <span className="font-medium text-foreground">3.0%</span>
                                    </div>
                                    <div className="w-full h-1 bg-muted rounded-full overflow-hidden">
                                        <div className="w-[10%] h-full bg-primary rounded-full"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg text-foreground font-semibold">Psychological Journal</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {journalEntries.length > 0 ? (
                                journalEntries.slice(0, 3).map((entry, i) => (
                                    <div key={entry.id || i} className="flex justify-between items-start pb-4 border-b border-border/50 last:border-0 last:pb-0">
                                        <div>
                                            <h4 className="font-medium text-sm text-foreground/90">{entry.expected_behaviour || "Journal Entry"}</h4>
                                            <p className="text-xs text-muted-foreground mt-1 truncate max-w-sm">
                                                {entry.actual_behaviour || entry.lesson_learned}
                                            </p>
                                        </div>
                                        <Badge variant="outline" className="text-[10px] text-emerald-500 border-emerald-500/20">
                                            {entry.thesis_validity === "Valid" ? "Verified" : "Logged"}
                                        </Badge>
                                    </div>
                                ))
                            ) : (
                                <p className="text-sm text-muted-foreground italic">No recent entries found.</p>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
