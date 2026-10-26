"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    fetchCopyStatus,
    startCopySession,
    stopCopySession,
    tickCopySession,
    type CopyBookStatus,
    type CopyPositionView,
} from "@/lib/api";

function money(value: number | null | undefined): string {
    if (value == null || Number.isNaN(value)) return "—";
    return `€${value.toFixed(2)}`;
}

function pnl(value: number | null | undefined): string {
    if (value == null || Number.isNaN(value)) return "—";
    const sign = value > 0 ? "+" : "";
    return `${sign}€${value.toFixed(2)}`;
}

function px(value: number | null | undefined): string {
    if (value == null || Number.isNaN(value)) return "—";
    if (value >= 100) return value.toFixed(2);
    if (value >= 1) return value.toFixed(4);
    return value.toFixed(6);
}

function when(iso: string | null | undefined): string {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString();
}

function PnlText({ value }: { value: number | null | undefined }) {
    const negative = value != null && value < 0;
    return <span className={negative ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"}>{pnl(value)}</span>;
}

function PositionTable({ rows, mode }: { rows: CopyPositionView[]; mode: "open" | "closed" }) {
    if (rows.length === 0) {
        return (
            <p className="text-sm text-muted-foreground px-1">
                {mode === "open" ? "No open paper positions." : "No closed paper trades yet."}
            </p>
        );
    }
    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Qty</TableHead>
                    <TableHead>Entry</TableHead>
                    <TableHead>{mode === "open" ? "Mark" : "Exit"}</TableHead>
                    <TableHead>Stop</TableHead>
                    <TableHead>Target</TableHead>
                    <TableHead>P&L</TableHead>
                    <TableHead>Signal</TableHead>
                </TableRow>
            </TableHeader>
            <TableBody>
                {rows.map((row) => {
                    const result = mode === "open" ? row.unrealized_pnl_eur : row.realized_pnl_eur;
                    return (
                        <TableRow key={row.id}>
                            <TableCell>
                                <div className="font-medium text-foreground">{row.symbol}</div>
                                <div className="text-xs text-muted-foreground">{when(mode === "open" ? row.opened_at : row.closed_at)}</div>
                            </TableCell>
                            <TableCell className="font-mono text-xs">{row.qty.toPrecision(6)}</TableCell>
                            <TableCell className="font-mono text-xs">{px(row.entry_price)}</TableCell>
                            <TableCell className="font-mono text-xs">{px(mode === "open" ? row.mark : row.exit_price)}</TableCell>
                            <TableCell className="font-mono text-xs">{px(row.stop_price)}</TableCell>
                            <TableCell className="font-mono text-xs">{px(row.target_price)}</TableCell>
                            <TableCell>
                                <PnlText value={result} />
                                {mode === "closed" && row.exit_reason ? (
                                    <div className="text-xs text-muted-foreground">{row.exit_reason}</div>
                                ) : null}
                            </TableCell>
                            <TableCell className="max-w-[16rem]">
                                <Badge variant="outline">{row.signal_source === "trade_idea" ? "Trade idea" : "Gainer"}</Badge>
                                <p className="mt-1 text-xs text-muted-foreground line-clamp-2" title={row.signal_reason}>
                                    {row.signal_reason}
                                </p>
                            </TableCell>
                        </TableRow>
                    );
                })}
            </TableBody>
        </Table>
    );
}

export default function CopyBookPage() {
    const [book, setBook] = useState<CopyBookStatus | null>(null);
    const [bankroll, setBankroll] = useState("200");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        const next = await fetchCopyStatus();
        if (next) {
            setBook(next);
            setError(null);
        } else {
            setError("Could not load the paper copy book.");
        }
        setLoading(false);
    }, []);

    useEffect(() => {
        let cancelled = false;
        let timer = 0;
        const refresh = async () => {
            const next = await fetchCopyStatus();
            if (cancelled) return;
            if (next) {
                setBook(next);
                setError(null);
            } else {
                setError("Could not load the paper copy book.");
            }
            setLoading(false);
        };
        const tick = () => {
            if (!cancelled && document.visibilityState === "visible") void refresh();
            timer = window.setTimeout(tick, 15000);
        };
        void refresh();
        timer = window.setTimeout(tick, 15000);
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, []);

    const run = async (action: () => Promise<{ status: CopyBookStatus | null; error: string | null }>) => {
        setBusy(true);
        const result = await action();
        setBusy(false);
        if (result.status) {
            setBook(result.status);
            setError(null);
            return;
        }
        setError(result.error);
        await load();
    };

    const session = book?.session;
    const running = Boolean(book?.active && session?.status === "running");

    return (
        <div className="space-y-5 max-w-5xl min-w-0">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">Copy book</h1>
                        <Badge variant="outline">Paper only</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                        Helm simulates a copy of scout ideas and EUR gainers on a virtual book.
                        Revolut X has no copy API. Starting, ticking, and stopping this session never places a live order.
                    </p>
                </div>
                <Button variant="outline" className="min-h-11 w-full sm:w-auto" onClick={() => void load()} disabled={busy}>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Refresh
                </Button>
            </div>

            {error ? (
                <p role="alert" className="text-sm text-red-500">
                    {error}
                </p>
            ) : null}

            <section className="rounded-xl border border-border bg-card p-4 space-y-4">
                {loading && !session ? <p className="text-sm text-muted-foreground">Loading paper book…</p> : null}
                {session ? (
                    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <Stat label="Status" value={running ? "Running" : session.status} />
                        <Stat label="Bankroll" value={money(session.starting_bankroll_eur)} />
                        <Stat label="Cash" value={money(session.cash_eur)} />
                        <Stat label="Equity" value={money(session.equity_eur)} />
                        <Stat label="Session P&L" value={pnl(session.session_pnl_eur)} tone={session.session_pnl_eur} />
                        <Stat label="Realised" value={pnl(session.realized_pnl_eur)} tone={session.realized_pnl_eur} />
                        <Stat label="Unrealised" value={pnl(session.unrealized_pnl_eur)} tone={session.unrealized_pnl_eur} />
                        <Stat label="Open" value={String(session.open_count)} />
                        <Stat label="Closed" value={String(session.closed_count)} />
                    </dl>
                ) : null}

                <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                    <label className="text-sm text-foreground flex flex-col gap-1 sm:w-40">
                        Virtual bankroll (€)
                        <input
                            type="number"
                            min={1}
                            step={1}
                            value={bankroll}
                            onChange={(event) => setBankroll(event.target.value)}
                            disabled={running || busy}
                            className="min-h-11 rounded-lg border border-border bg-background px-3 text-sm"
                        />
                    </label>
                    <Button
                        className="min-h-11"
                        disabled={running || busy}
                        onClick={() => {
                            const amount = Number(bankroll);
                            if (!Number.isFinite(amount) || amount <= 0) {
                                setError("Enter a bankroll above zero.");
                                return;
                            }
                            void run(() => startCopySession(amount));
                        }}
                    >
                        Start dry-run
                    </Button>
                    <Button
                        variant="outline"
                        className="min-h-11"
                        disabled={!running || busy}
                        onClick={() => void run(() => tickCopySession())}
                    >
                        Tick paper book
                    </Button>
                    <Button
                        variant="outline"
                        className="min-h-11"
                        disabled={!running || busy}
                        onClick={() => void run(() => stopCopySession())}
                    >
                        Stop and flatten
                    </Button>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                    Default bankroll is €200 via HELM_COPY_BANKROLL_EUR. An overnight watcher can poll
                    POST /api/copy/tick and GET /api/copy/status. See docs/helm-copy-book.md.
                </p>
            </section>

            <section className="space-y-2">
                <h2 className="text-lg font-semibold text-foreground">Open paper positions</h2>
                <PositionTable rows={book?.open_positions ?? []} mode="open" />
            </section>
            <section className="space-y-2">
                <h2 className="text-lg font-semibold text-foreground">Closed paper trades</h2>
                <PositionTable rows={book?.closed_trades ?? []} mode="closed" />
            </section>
        </div>
    );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: number }) {
    const toneClass =
        tone == null ? "text-foreground" : tone < 0 ? "text-red-500" : "text-emerald-600 dark:text-emerald-400";
    return (
        <div>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className={`text-sm font-semibold ${toneClass}`}>{value}</dd>
        </div>
    );
}
