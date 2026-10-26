"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { askGuru, fetchIdeaWhy, type IdeaExplanation } from "@/lib/api";

type ChatMsg = { role: "user" | "assistant"; content: string };

const STARTERS = [
    "What is the pitfall if I add to a loser?",
    "How should I size a spot long on this book?",
    "What would make you skip a setup?",
];

function GuruChat() {
    const params = useSearchParams();
    const tradeParam = params.get("trade");
    const tradeId = tradeParam && /^\d+$/.test(tradeParam) ? Number(tradeParam) : undefined;
    const [messages, setMessages] = useState<ChatMsg[]>([]);
    const [draft, setDraft] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [idea, setIdea] = useState<IdeaExplanation | null>(null);

    useEffect(() => {
        let cancelled = false;
        setMessages([]);
        setIdea(null);
        setError(null);
        if (!tradeId) return;
        fetchIdeaWhy(tradeId).then((why) => {
            if (cancelled || !why) {
                if (!cancelled) setError("That idea is not on the book. You can still ask a general question.");
                return;
            }
            setIdea(why);
            setMessages([
                {
                    role: "assistant",
                    content: `${why.headline}\n\n${why.why}\n\n${why.spot_note}\n\nAdvisory only. This chat cannot approve or execute.`,
                },
            ]);
        });
        return () => {
            cancelled = true;
        };
    }, [tradeId]);

    const send = async (text: string) => {
        const trimmed = text.trim();
        if (!trimmed || busy) return;
        const history: ChatMsg[] = [...messages, { role: "user", content: trimmed }];
        setMessages(history);
        setDraft("");
        setBusy(true);
        setError(null);
        try {
            const result = await askGuru(history, tradeId);
            setMessages((current) => [...current, { role: "assistant", content: result.reply }]);
        } catch (err) {
            setError(err instanceof Error ? err.message : "The guru could not answer that.");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="flex min-h-0 flex-1 flex-col gap-4">
            <div>
                <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                    <MessageCircle className="h-7 w-7 text-primary" />
                    Trading Guru
                </h1>
                <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                    Advisory only. Tape, ideas, and risk. This chat cannot approve a TradeIdea or send an order to Revolut X.
                </p>
            </div>

            {idea && (
                <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-foreground">
                    Talking about {idea.symbol} {idea.direction}. {idea.spot_note}
                </p>
            )}

            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto rounded-2xl border border-border bg-card p-3" aria-live="polite">
                {messages.length === 0 && (
                    <div className="space-y-3 py-6 text-sm text-muted-foreground">
                        <p>Ask about a setup, a size, or a mistake you are about to make. The default answer is skeptical.</p>
                        <div className="flex flex-col gap-2">
                            {STARTERS.map((prompt) => (
                                <button
                                    key={prompt}
                                    type="button"
                                    onClick={() => void send(prompt)}
                                    className="min-h-11 rounded-lg border border-border px-3 text-left text-sm text-foreground hover:bg-accent"
                                >
                                    {prompt}
                                </button>
                            ))}
                        </div>
                    </div>
                )}
                {messages.map((message, index) => (
                    <div
                        key={`${message.role}-${index}`}
                        data-testid={message.role === "assistant" ? "guru-reply" : undefined}
                        className={`max-w-[95%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed ${message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted text-foreground"}`}
                    >
                        {message.content}
                    </div>
                ))}
                {busy && <p className="text-sm text-muted-foreground">Thinking…</p>}
            </div>

            {error && <p className="text-sm text-red-500">{error}</p>}

            <form
                className="flex items-end gap-2"
                onSubmit={(event) => {
                    event.preventDefault();
                    void send(draft);
                }}
            >
                <label className="sr-only" htmlFor="guru-draft">Message the Trading Guru</label>
                <textarea
                    id="guru-draft"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    rows={2}
                    maxLength={2000}
                    placeholder="Ask about the tape, an idea, or the risk."
                    className="min-h-11 flex-1 resize-none rounded-xl border border-input bg-card p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                />
                <Button type="submit" disabled={busy || !draft.trim()} className="min-h-11 min-w-16">
                    Send
                </Button>
            </form>
        </div>
    );
}

export default function GuruPage() {
    return (
        <Suspense fallback={<p className="text-sm text-muted-foreground">Loading Trading Guru…</p>}>
            <GuruChat />
        </Suspense>
    );
}
