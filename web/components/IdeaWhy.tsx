"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { askIdea, fetchIdeaWhy, type IdeaExplanation, type TradeIdea } from "@/lib/api";

const PROMPTS = [
    "What invalidates this?",
    "Is the reward/risk enough?",
    "What pitfall does this resemble?",
];

function fallbackWhy(trade: TradeIdea): IdeaExplanation {
    const risk = Math.abs(trade.entry_price - trade.stop_price);
    const reward = Math.abs(trade.target_price - trade.entry_price);
    const rr = risk > 0 ? Math.round((reward / risk) * 100) / 100 : null;
    const invalidation = trade.invalidation_notes || "";
    const thesis = trade.thesis || "";
    return {
        trade_id: trade.id,
        symbol: trade.symbol,
        direction: trade.direction,
        status: trade.status,
        headline: `Why ${trade.symbol} ${trade.direction}`,
        why: `${trade.symbol} ${trade.direction}. Thesis: ${thesis || "none recorded."} Invalidation: ${invalidation || "not set. Guardian would reject this."}`,
        thesis,
        invalidation,
        levels: {
            entry: trade.entry_price,
            stop: trade.stop_price,
            target: trade.target_price,
            risk_reward: rr,
        },
        spot_note: trade.direction === "EXIT"
            ? "This closes a spot long. Asking here does not sell."
            : "Spot only. Asking here does not approve or execute.",
        advisory: true,
        can_execute: false,
    };
}

export function IdeaWhy({ trade }: { trade: TradeIdea }) {
    const [why, setWhy] = useState<IdeaExplanation>(() => fallbackWhy(trade));
    const [question, setQuestion] = useState("");
    const [thread, setThread] = useState<{ question: string; reply: string }[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setThread([]);
        setQuestion("");
        setError(null);
    }, [trade.id]);

    useEffect(() => {
        let cancelled = false;
        setWhy(fallbackWhy(trade));
        fetchIdeaWhy(trade.id).then((remote) => {
            if (!cancelled && remote) setWhy(remote);
        });
        return () => {
            cancelled = true;
        };
    }, [trade]);

    const ask = async (text: string) => {
        const trimmed = text.trim();
        if (!trimmed || busy) return;
        setBusy(true);
        setError(null);
        try {
            const result = await askIdea(trade.id, trimmed);
            setThread((current) => [
                ...current,
                { question: trimmed, reply: result?.reply || "No reply." },
            ]);
            setQuestion("");
        } catch (err) {
            setError(err instanceof Error ? err.message : "The guru could not answer that.");
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className="space-y-4" data-testid="why-this-idea" aria-label="Why this idea">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Why this idea</h3>
                    <p className="mt-1 text-base font-semibold text-foreground">{why.headline}</p>
                </div>
                <span className="shrink-0 rounded-full border border-border px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    Advisory
                </span>
            </div>
            <p className="text-sm leading-relaxed text-foreground/90">{why.why}</p>
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <div className="rounded-lg border border-border bg-muted/40 p-3">
                    <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Reward/risk</dt>
                    <dd className="mt-1 font-mono text-foreground">{why.levels.risk_reward ?? "—"}</dd>
                </div>
                <div className="rounded-lg border border-border bg-muted/40 p-3 sm:col-span-3">
                    <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Invalidation</dt>
                    <dd className="mt-1 text-foreground/90">{why.invalidation || "Not set."}</dd>
                </div>
            </dl>
            {why.thesis && (
                <p className="text-sm leading-relaxed text-muted-foreground">{why.thesis}</p>
            )}
            <p className="text-xs leading-relaxed text-muted-foreground">{why.spot_note}</p>

            <div className="space-y-3 border-t border-border pt-4">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <MessageCircle className="h-4 w-4 text-primary" />
                    Ask the Trading Guru
                </div>
                <div className="flex gap-2 overflow-x-auto pb-1">
                    {PROMPTS.map((prompt) => (
                        <button
                            key={prompt}
                            type="button"
                            onClick={() => ask(prompt)}
                            disabled={busy}
                            className="shrink-0 rounded-full border border-border bg-muted/40 px-3 py-2 text-xs text-foreground hover:bg-accent disabled:opacity-50"
                        >
                            {prompt}
                        </button>
                    ))}
                </div>
                <form
                    className="flex flex-col gap-2 sm:flex-row sm:items-end"
                    onSubmit={(event) => {
                        event.preventDefault();
                        void ask(question);
                    }}
                >
                    <label className="sr-only" htmlFor={`why-q-${trade.id}`}>Question about this idea</label>
                    <textarea
                        id={`why-q-${trade.id}`}
                        value={question}
                        onChange={(event) => setQuestion(event.target.value)}
                        rows={2}
                        maxLength={2000}
                        placeholder="Ask about the level, the invalidation, or the pitfall."
                        className="min-h-11 w-full flex-1 resize-none rounded-lg border border-input bg-muted/50 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                    />
                    <Button type="submit" disabled={busy || !question.trim()} className="min-h-11 sm:min-w-24">
                        {busy ? "Asking…" : "Ask"}
                    </Button>
                </form>
                <p className="text-[11px] text-muted-foreground">
                    This question does not approve or execute.{" "}
                    <Link href={`/app/guru?trade=${trade.id}`} className="underline underline-offset-2">
                        Open the full guru chat
                    </Link>
                    .
                </p>
                {error && <p className="text-sm text-red-500">{error}</p>}
                <div className="space-y-3" aria-live="polite">
                    {thread.map((turn) => (
                        <div key={turn.question} className="space-y-2" data-testid="why-reply">
                            <p className="text-sm font-medium text-foreground">{turn.question}</p>
                            <p className="whitespace-pre-wrap rounded-lg border border-border bg-muted/40 p-3 text-sm leading-relaxed text-foreground/90">
                                {turn.reply}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
