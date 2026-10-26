"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    fetchProfitNotifications,
    markAllProfitNotificationsRead,
    markProfitNotificationRead,
    scanProfitNotifications,
    type ProfitNotification,
    type ProfitNotificationList,
} from "@/lib/api";

type ProfitNoteState = {
    data: ProfitNotificationList | null;
    ready: boolean;
    offline: boolean;
    open: boolean;
    setOpen: (open: boolean) => void;
    markOne: (id: number) => Promise<void>;
    markAll: () => Promise<void>;
};

const ProfitNoteContext = createContext<ProfitNoteState | null>(null);

function useProfitNotes(): ProfitNoteState {
    const value = useContext(ProfitNoteContext);
    if (!value) {
        throw new Error("Profit notifications render inside the Helm shell");
    }
    return value;
}

export function ProfitNotificationProvider({ children }: { children: React.ReactNode }) {
    const [data, setData] = useState<ProfitNotificationList | null>(null);
    const [ready, setReady] = useState(false);
    const [offline, setOffline] = useState(false);
    const [open, setOpen] = useState(false);
    const request = useRef(0);

    const refresh = useCallback(async () => {
        const token = ++request.current;
        const scanned = await scanProfitNotifications();
        if (token !== request.current) return;
        if (scanned) {
            setData(scanned);
            setOffline(false);
            setReady(true);
            return;
        }
        const listed = await fetchProfitNotifications();
        if (token !== request.current) return;
        setReady(true);
        if (listed) {
            setData(listed);
            setOffline(false);
            return;
        }
        setOffline(true);
    }, []);

    useEffect(() => {
        void refresh();
        const interval = window.setInterval(() => {
            void refresh();
        }, 60_000);
        return () => window.clearInterval(interval);
    }, [refresh]);

    useEffect(() => {
        if (!open) return;
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") setOpen(false);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open]);

    const markOne = useCallback(async (id: number) => {
        const token = ++request.current;
        const listed = await markProfitNotificationRead(id);
        if (token !== request.current || !listed) return;
        setData(listed);
        setReady(true);
        setOffline(false);
    }, []);

    const markAll = useCallback(async () => {
        const token = ++request.current;
        const listed = await markAllProfitNotificationsRead();
        if (token !== request.current || !listed) return;
        setData(listed);
        setReady(true);
        setOffline(false);
    }, []);

    return (
        <ProfitNoteContext.Provider value={{ data, ready, offline, open, setOpen, markOne, markAll }}>
            {children}
        </ProfitNoteContext.Provider>
    );
}

export function ProfitBell() {
    const { data, open, setOpen } = useProfitNotes();
    const unread = data?.unread_count ?? 0;
    const label = unread > 0 ? `Helm profit notifications, ${unread} unread` : "Helm profit notifications";

    return (
        <Button
            type="button"
            variant="ghost"
            size="icon"
            className="relative size-11 md:size-9 shrink-0"
            aria-label={label}
            aria-expanded={open}
            aria-controls="helm-profit-notifications"
            onClick={() => setOpen(!open)}
        >
            <Bell className="h-5 w-5" />
            {unread > 0 && (
                <span className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-emerald-500 px-1 text-[10px] font-bold leading-none text-white">
                    {unread > 9 ? "9+" : unread}
                </span>
            )}
        </Button>
    );
}

export function ProfitBanner() {
    const { data, setOpen } = useProfitNotes();
    const unread = (data?.notifications ?? []).filter((note) => !note.read);
    if (!data || data.unread_count <= 0) return null;
    const latest = unread[0];
    const extra = latest ? Math.max(0, data.unread_count - 1) : 0;

    return (
        <button
            type="button"
            onClick={() => setOpen(true)}
            className="mb-4 flex min-h-14 w-full items-center gap-3 rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-left"
            aria-live="polite"
        >
            <span className="min-w-0 flex-1">
                <span className="block text-base font-semibold text-foreground">
                    {latest ? latest.title : "Helm profit"}
                </span>
                <span className="mt-0.5 block text-sm text-emerald-700 dark:text-emerald-300">
                    {latest ? latest.body : `${data.unread_count} unread`}
                </span>
                {extra > 0 && (
                    <span className="mt-1 block text-xs text-muted-foreground">+{extra} more</span>
                )}
            </span>
            <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-foreground">View</span>
        </button>
    );
}

function kindLabel(kind: string): string {
    if (kind === "in_profit") return "In profit";
    if (kind === "take_profit") return "Target hit";
    if (kind === "exit_filled") return "Profit booked";
    return "Helm";
}

function NoteRow({
    note,
    onRead,
    onNavigate,
}: {
    note: ProfitNotification;
    onRead: (id: number) => void;
    onNavigate: () => void;
}) {
    const href = note.kind === "take_profit" ? "/app/approvals" : "/app/my-trade";
    const action = note.kind === "take_profit" ? "Review exit" : "See position";

    return (
        <article
            className={`rounded-xl border p-4 ${note.read ? "border-border bg-background" : "border-emerald-500/40 bg-emerald-500/5"}`}
        >
            <div className="flex items-start justify-between gap-3">
                <p className="text-base font-semibold text-foreground">{note.title}</p>
                <span className="shrink-0 rounded-full bg-emerald-500/15 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                    {kindLabel(note.kind)}
                </span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-foreground/90">{note.body}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
                <Link
                    href={href}
                    onClick={onNavigate}
                    className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium text-foreground underline underline-offset-4"
                >
                    {action}
                </Link>
                {!note.read && (
                    <Button type="button" variant="outline" className="min-h-11" onClick={() => onRead(note.id)}>
                        Got it
                    </Button>
                )}
            </div>
        </article>
    );
}

export function ProfitSheet() {
    const { data, ready, offline, open, setOpen, markOne, markAll } = useProfitNotes();
    if (!open) return null;
    const notes = data?.notifications ?? [];
    const unread = data?.unread_count ?? 0;

    return (
        <div className="fixed inset-0 z-50 flex items-end md:items-start md:justify-end md:p-4">
            <button
                type="button"
                aria-label="Close profit notifications"
                className="absolute inset-0 bg-black/50"
                onClick={() => setOpen(false)}
            />
            <div
                id="helm-profit-notifications"
                role="dialog"
                aria-modal="true"
                aria-label="Helm profit notifications"
                className="relative flex max-h-[min(85dvh,40rem)] w-full flex-col overflow-hidden rounded-t-2xl border border-border bg-card shadow-xl md:max-w-md md:rounded-2xl"
            >
                <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
                    <div>
                        <h2 className="text-base font-bold text-foreground">Helm</h2>
                        <p className="text-xs text-muted-foreground">Profit on open spot longs</p>
                    </div>
                    <Button type="button" variant="outline" className="min-h-11" onClick={() => setOpen(false)}>
                        Close
                    </Button>
                </div>
                <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
                    {!ready && (
                        <p className="text-sm text-muted-foreground">Checking live spot PnL…</p>
                    )}
                    {ready && offline && notes.length === 0 && (
                        <p className="text-sm leading-relaxed text-muted-foreground">
                            Helm couldn&apos;t reach notifications. Open this again in a moment.
                        </p>
                    )}
                    {ready && !offline && notes.length === 0 && (
                        <p className="text-sm leading-relaxed text-muted-foreground">
                            No profit pings yet. Helm notifies once when a spot long turns green, when a take-profit
                            is ready to approve, and when a profitable exit fills.
                        </p>
                    )}
                    {notes.map((note) => (
                        <NoteRow
                            key={note.id}
                            note={note}
                            onRead={(id) => {
                                void markOne(id);
                            }}
                            onNavigate={() => setOpen(false)}
                        />
                    ))}
                    {unread > 0 && (
                        <Button type="button" variant="secondary" className="min-h-12 w-full" onClick={() => void markAll()}>
                            Mark all read
                        </Button>
                    )}
                </div>
            </div>
        </div>
    );
}
