import { GlassCard } from "@/components/GlassCard";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function Dashboard() {
    return (
        <div className="space-y-8 max-w-7xl mx-auto">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-white mb-1">Morning, Declan.</h1>
                    <p className="text-slate-400">Here is your daily briefing and market overview.</p>
                </div>
                <div className="text-left md:text-right">
                    <div className="text-2xl font-bold text-amber-500">XAU/USD</div>
                    <div className="text-sm text-slate-400">2045.50 <span className="text-emerald-500">+12.40</span></div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <GlassCard className="p-5 md:col-span-3 min-h-[300px] flex flex-col justify-between">
                    <div>
                        <div className="flex items-center gap-2 mb-4">
                            <Badge variant="outline" className="text-amber-500 border-amber-500/20 bg-amber-500/10">AI Briefing</Badge>
                            <span className="text-xs text-slate-500">Generated 10 mins ago</span>
                        </div>
                        <p className="text-slate-300 leading-relaxed max-w-3xl">
                            Market state is currently in a high-timeframe consolidation forming a bullish flag below 2050 resistance.
                            The Asian session swept local lows, leaving an untapped order block around 2028.
                            Agents recommend extreme patience today. Do not force longs unless a clear H1 close above 2055 confirms momentum.
                        </p>
                    </div>
                    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 text-sm text-slate-400 border-t border-slate-800 pt-4 mt-6">
                        <span>Daily Bias: <span className="text-white font-medium">Neutral / Bullish</span></span>
                        <span className="hidden sm:inline-block text-slate-700">•</span>
                        <span>Key Support: <span className="text-white font-medium">2028.00</span></span>
                        <span className="hidden sm:inline-block text-slate-700">•</span>
                        <span>Key Resistance: <span className="text-white font-medium">2055.00</span></span>
                    </div>
                </GlassCard>

                <Card className="bg-slate-900 border-slate-800 flex flex-col">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wider">Pending Action</CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 flex flex-col justify-center">
                        <div className="text-5xl font-bold text-white mb-2">1</div>
                        <p className="text-sm text-slate-400">Trade awaiting your approval</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card className="bg-slate-900 border-slate-800">
                    <CardHeader>
                        <CardTitle className="text-lg text-white">Recent Journal Entries</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            <div className="flex justify-between items-start pb-4 border-b border-slate-800/50">
                                <div>
                                    <h4 className="font-medium text-slate-200">Choppy London session</h4>
                                    <p className="text-sm text-slate-400 mt-1">Patience was key, avoided forcing a trade.</p>
                                </div>
                                <Badge variant="outline" className="text-emerald-500 border-emerald-500/20">Valid</Badge>
                            </div>
                            <div className="flex justify-between items-start pb-2">
                                <div>
                                    <h4 className="font-medium text-slate-200">Sweep and Reverse</h4>
                                    <p className="text-sm text-slate-400 mt-1">Took the short at 2092 supply perfectly.</p>
                                </div>
                                <Badge variant="outline" className="text-emerald-500 border-emerald-500/20">Valid</Badge>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-slate-900 border-slate-800">
                    <CardHeader>
                        <CardTitle className="text-lg text-white">Risk Profile Tracker</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-5">
                            <div className="flex flex-col gap-1">
                                <div className="flex justify-between items-center text-sm">
                                    <span className="text-slate-400">Max Risk per Trade</span>
                                    <span className="font-medium text-white">1.0%</span>
                                </div>
                                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                    <div className="w-1/4 h-full bg-emerald-500 rounded-full"></div>
                                </div>
                            </div>
                            <div className="flex flex-col gap-1">
                                <div className="flex justify-between items-center text-sm">
                                    <span className="text-slate-400">Daily Drawdown Limit</span>
                                    <span className="font-medium text-white">3.0%</span>
                                </div>
                                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                    <div className="w-[10%] h-full bg-amber-500 rounded-full"></div>
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
