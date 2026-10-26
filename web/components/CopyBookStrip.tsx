"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchCopyStatus, type CopyBookStatus } from "@/lib/api";

function pnl(value: number): string {
    const sign = value > 0 ? "+" : "";
    return `${sign}€${value.toFixed(2)}`;
}

export function CopyBookStrip() {
    const [book, setBook] = useState<CopyBookStatus | null>(null);

    useEffect(() => {
        let cancelled = false;
        let timer = 0;
        const load = async () => {
            const next = await fetchCopyStatus();
            if (!cancelled && next) setBook(next);
        };
        const tick = () => {
            if (!cancelled && document.visibilityState === "visible") void load();
            timer = window.setTimeout(tick, 15000);
        };
        void load();
        timer = window.setTimeout(tick, 15000);
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, []);

    const session = book?.session;
    const pnlClass =
        session && session.session_pnl_eur < 0 ? "text-red-500" : "text-emerald-600 dark:text-emerald-400";

    return (
        <div className="rounded-xl border border-border bg-card px-4 py-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">Paper copy book</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                    Virtual EUR book. Revolut X has no copy API, and this path does not place a live order.
                    {session ? (
                        <>
                            {" "}
                            Session #{session.id}{" "}
                            <span className={pnlClass}>{pnl(session.session_pnl_eur)}</span>
                            {" "}
                            · {session.open_count} open · {session.closed_count} closed
                        </>
                    ) : (
                        " No session running."
                    )}
                </p>
            </div>
            <Link
                href="/app/copy"
                className="inline-flex min-h-11 items-center justify-center rounded-lg border border-border px-3 text-sm font-medium text-foreground hover:bg-accent"
            >
                Open copy book
            </Link>
        </div>
    );
}
