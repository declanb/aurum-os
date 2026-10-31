"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    ackMetaApiLeverage,
    closeMetaApiPaper,
    executeMetaApiIdea,
    fetchMetaApiIdeas,
    fetchMetaApiLedger,
    fetchMetaApiStatus,
    markMetaApiPaper,
    runMetaApiScout,
    type MetaApiIdeaView,
    type MetaApiLedger,
    type MetaApiStatus,
} from "@/lib/api";

function usd(v: number | null | undefined): string {
    if (v == null || Number.isNaN(v)) return "—";
    const sign = v > 0 ? "+" : "";
    return `${sign}$${v.toFixed(2)}`;
}

export default function CommoditiesPage() {
    const [status, setStatus] = useState<MetaApiStatus | null>(null);
    const [ideas, setIdeas] = useState<MetaApiIdeaView[]>([]);
    const [ledger, setLedger] = useState<MetaApiLedger | null>(null);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<string | null>(null);

    const load = useCallback(async () => {
        const [s, i, l] = await Promise.all([fetchMetaApiStatus(), fetchMetaApiIdeas(), fetchMetaApiLedger()]);
        setStatus(s);
        setIdeas(i ?? []);
        setLedger(l);
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const act = async (fn: () => Promise<unknown>, done: string) => {
        setBusy(true);
        setMessage(null);
        try {
            await fn();
            setMessage(done);
        } catch (e) {
            setMessage(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
            load();
        }
    };

    return (
        <div className="space-y-6 p-4 md:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-semibold">Commodities</h1>
                    <p className="text-sm text-muted-foreground">
                        Helm gold, silver and oil via MetaApi (MT4/MT5).
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant={status?.mode === "live" ? "destructive" : "secondary"}>
                        {status?.mode === "live" ? "LIVE" : "Paper"}
                    </Badge>
                    <Badge variant="outline">{status?.configured ? "MetaApi connected" : "MetaApi not configured"}</Badge>
                    <Button size="sm" variant="outline" onClick={load} disabled={busy}>
                        <RefreshCw className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {status && (
                <div className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm">
                    <strong>Leveraged CFDs, not spot.</strong> {status.warning} Max {status.max_lots} lots, margin level
                    must stay ≥ {status.min_margin_level_pct}%.
                </div>
            )}

            {message && <p className="text-sm">{message}</p>}

            <section className="space-y-2">
                <div className="flex items-center justify-between">
                    <h2 className="font-semibold">Ideas</h2>
                    <Button size="sm" disabled={busy} onClick={() => act(runMetaApiScout, "Scout ran.")}>
                        Run commodities scout
                    </Button>
                </div>
                {ideas.length === 0 && <p className="text-sm text-muted-foreground">No commodity ideas yet.</p>}
                {ideas.map((idea) => (
                    <div key={idea.trade_idea_id} className="rounded-lg border p-3 text-sm space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                            <strong>
                                #{idea.trade_idea_id} {idea.symbol} {idea.direction}
                            </strong>
                            <Badge variant="outline">{idea.status}</Badge>
                            <span>
                                {idea.lots} lots · entry {idea.entry_price} · SL {idea.stop_price} · TP {idea.target_price}
                            </span>
                        </div>
                        <p className="text-muted-foreground">{idea.thesis}</p>
                        {idea.guardian.issues.length > 0 && (
                            <p className="text-red-500">Guardian: {idea.guardian.issues.join("; ")}</p>
                        )}
                        <div className="flex flex-wrap items-center gap-3">
                            <label className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    checked={idea.leveraged_ok}
                                    disabled={busy}
                                    onChange={(e) =>
                                        act(() => ackMetaApiLeverage(idea.trade_idea_id, e.target.checked), "Saved.")
                                    }
                                />
                                I understand this is a leveraged CFD
                            </label>
                            {idea.status === "Ready for Approval" && (
                                <Link className="underline" href="/app/approvals">
                                    Approve in Approvals
                                </Link>
                            )}
                            {idea.status === "Approved" && (
                                <Button
                                    size="sm"
                                    disabled={busy || (status?.mode === "live" && !idea.leveraged_ok)}
                                    onClick={() => act(() => executeMetaApiIdea(idea.trade_idea_id), "Executed.")}
                                >
                                    Execute ({status?.mode === "live" ? "live" : "paper"})
                                </Button>
                            )}
                        </div>
                    </div>
                ))}
            </section>

            <section className="space-y-2">
                <div className="flex items-center justify-between">
                    <h2 className="font-semibold">
                        Paper ledger · open {usd(ledger?.unrealized_pnl)} · realised {usd(ledger?.realized_pnl)}
                    </h2>
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => act(markMetaApiPaper, "Marked.")}>
                        Mark to market
                    </Button>
                </div>
                {[...(ledger?.open ?? []), ...(ledger?.closed ?? [])].map((p) => (
                    <div key={p.id} className="flex flex-wrap items-center gap-3 rounded border p-2 text-sm">
                        <strong>
                            {p.symbol} {p.direction} {p.lots}
                        </strong>
                        <span>entry {p.entry_price}</span>
                        <span>mark {p.last_mark ?? "—"}</span>
                        <span>spread {usd(-p.spread_cost)}</span>
                        <span>swap {usd(-p.swap_estimate)}</span>
                        <span>P&amp;L {usd(p.exit_reason ? p.realized_pnl : p.unrealized_pnl)}</span>
                        {p.exit_reason ? (
                            <Badge variant="outline">closed: {p.exit_reason}</Badge>
                        ) : (
                            <Button
                                size="sm"
                                variant="outline"
                                disabled={busy}
                                onClick={() => act(() => closeMetaApiPaper(p.id), "Closed.")}
                            >
                                Close
                            </Button>
                        )}
                    </div>
                ))}
            </section>
        </div>
    );
}
