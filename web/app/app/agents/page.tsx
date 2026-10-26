"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, Pause, Play, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    cleanStaleAgents,
    clearAgent,
    fetchFleet,
    pauseAgents,
    resumeAgents,
    type FleetBoard,
    type FleetCard,
} from "@/lib/api";

const HEALTH_LABEL: Record<FleetCard["health"], string> = {
    healthy: "Healthy",
    stale: "Stale",
    idle: "Idle",
    off: "Off",
};

const HEALTH_CLASS: Record<FleetCard["health"], string> = {
    healthy: "border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
    stale: "border-amber-500/40 bg-amber-500/15 text-amber-800 dark:text-amber-300",
    idle: "border-border bg-muted text-muted-foreground",
    off: "border-border bg-muted text-muted-foreground",
};

function ago(iso: string | null): string {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "";
    const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 48) return `${hours}h ago`;
    return new Date(iso).toLocaleString();
}

export default function AgentsPage() {
    const [board, setBoard] = useState<FleetBoard | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        let cancelled = false;
        let timer = 0;
        const load = async () => {
            const next = await fetchFleet();
            if (cancelled) return;
            if (next) {
                setBoard(next);
                setError(null);
            } else {
                setError("Could not reach the agent fleet.");
            }
            setLoading(false);
        };
        const tick = () => {
            if (!cancelled && document.visibilityState === "visible") void load();
            timer = window.setTimeout(tick, 5000);
        };
        void load();
        timer = window.setTimeout(tick, 5000);
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, []);

    const reload = async () => {
        const next = await fetchFleet();
        if (next) {
            setBoard(next);
            setError(null);
        }
    };

    const run = async (action: () => Promise<boolean>) => {
        setBusy(true);
        try {
            const ok = await action();
            if (!ok) setError("That fleet control did not go through.");
            await reload();
        } finally {
            setBusy(false);
        }
    };

    const cards = board?.cards ?? [];
    const counts = {
        healthy: cards.filter((card) => card.health === "healthy").length,
        stale: cards.filter((card) => card.health === "stale").length,
        idle: cards.filter((card) => card.health === "idle" || card.health === "off").length,
    };

    if (loading && !board) {
        return <p className="text-sm text-muted-foreground">Loading the Helm fleet…</p>;
    }

    return (
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                    <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                        <Bot className="h-7 w-7 text-primary" />
                        Agents
                    </h1>
                    <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                        Live cards for the Helm fleet. They stage ideas and watch exits. None of them send a Revolut X order from this screen.
                    </p>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:flex">
                    <Button
                        type="button"
                        variant="outline"
                        className="min-h-11"
                        disabled={busy}
                        onClick={() => void run(cleanStaleAgents)}
                    >
                        <RefreshCw className="h-4 w-4" />
                        Clean stale
                    </Button>
                    {board?.paused ? (
                        <Button type="button" className="min-h-11 bg-emerald-600 text-white hover:bg-emerald-500" disabled={busy} onClick={() => void run(resumeAgents)}>
                            <Play className="h-4 w-4" />
                            Run
                        </Button>
                    ) : (
                        <Button type="button" variant="destructive" className="min-h-11" disabled={busy} onClick={() => void run(pauseAgents)}>
                            <Pause className="h-4 w-4" />
                            Pause
                        </Button>
                    )}
                </div>
            </div>

            {board?.paused && (
                <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
                    Fleet paused. Scout and the exit watcher skip their next pass. Open orders are unchanged.
                </p>
            )}
            {board && !board.cron_enabled && (
                <p className="rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                    Scheduled scout and exit checks are switched off. A local process can still show as healthy.
                </p>
            )}
            {error && <p className="text-sm text-red-500">{error}</p>}

            <div className="grid grid-cols-3 gap-3">
                <Stat label="Healthy" value={counts.healthy} />
                <Stat label="Stale" value={counts.stale} />
                <Stat label="Idle" value={counts.idle} />
            </div>

            <div className="grid gap-3 sm:grid-cols-2" aria-live="polite">
                {cards.map((card) => (
                    <Card key={card.id} data-testid="fleet-card" className="border-border">
                        <CardHeader className="pb-2">
                            <div className="flex items-start justify-between gap-3">
                                <CardTitle className="text-base font-semibold leading-snug">{card.name}</CardTitle>
                                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${HEALTH_CLASS[card.health]}`}>
                                        {HEALTH_LABEL[card.health]}
                                    </span>
                                    {card.paused && (
                                        <Badge variant="outline" className="text-[10px]">Skips next</Badge>
                                    )}
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm">
                            <p className="text-muted-foreground">{card.blurb}</p>
                            {card.symbol && (
                                <span className="inline-flex rounded-md border border-border px-2 py-0.5 font-mono text-xs">{card.symbol}</span>
                            )}
                            {card.detail && <p className="font-mono text-xs text-foreground/80">{card.detail}</p>}
                            <div>
                                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Last action</p>
                                <p className="mt-1 text-foreground">{card.last_action}</p>
                                {card.last_action_at && (
                                    <p className="mt-1 text-xs text-muted-foreground">{ago(card.last_action_at)}</p>
                                )}
                            </div>
                            {card.last_heartbeat && (
                                <p className="text-xs text-muted-foreground">Heartbeat {ago(card.last_heartbeat)}</p>
                            )}
                            {card.can_clear && (
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="min-h-11 w-full"
                                    disabled={busy}
                                    onClick={() => void run(() => clearAgent(card.id))}
                                >
                                    Clear status
                                </Button>
                            )}
                        </CardContent>
                    </Card>
                ))}
            </div>

            <p className="text-sm text-muted-foreground">
                Want a second opinion before you approve?{" "}
                <Link href="/app/guru" className="underline underline-offset-2">Ask the Trading Guru</Link>.
            </p>
        </div>
    );
}

function Stat({ label, value }: { label: string; value: number }) {
    return (
        <div className="rounded-xl border border-border bg-card px-3 py-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
        </div>
    );
}
