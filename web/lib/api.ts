// Create an API service for frontend data fetching
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export type GuardianChallengeResult = {
    passed: boolean;
    score: number;
    message: string;
    issues: string[];
};

export type ApprovalEvent = {
    id: number;
    trade_idea_id: number;
    version_id: number;
    user_id: string;
    snapshot_hash: string;
    timestamp: string;
};

export type TradeVersion = {
    id: number;
    trade_idea_id: number;
    version_number: number;
    symbol: string;
    direction: string;
    entry_price: number;
    stop_price: number;
    target_price: number;
    thesis: string;
    invalidation_notes?: string | null;
    created_at: string;
};

export type JournalEntry = {
    id: number;
    user_id: string;
    trade_idea_id: number | null;
    expected_behaviour: string | null;
    actual_behaviour: string | null;
    thesis_validity: string | null;
    should_have_skipped: boolean;
    lesson_learned: string | null;
    created_at: string;
};

export type JournalEntryInput = {
    trade_idea_id: number;
    content: string;
    mistakes_made?: string;
    lessons_learned?: string;
    execution_rating?: number;
};

export type JournalEntryResult = { status: string; id: number };

export type ExecuteTradeResult = {
    ticket_status?: string;
    trade_status?: string;
    execution?: { message?: string } | null;
    message?: string;
};

type MarketNote = {
    id: number;
    symbol: string;
    timeframe: string;
    content: string;
    market_state?: string;
    support_levels?: string;
    resistance_levels?: string;
    created_at: string;
    user_id: string;
};

export async function fetchNotes(): Promise<MarketNote[]> {
    try {
        const res = await fetch(`${API_URL}/notes/`);
        if (!res.ok) throw new Error("Failed to fetch notes");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function createNote(data: Partial<MarketNote>): Promise<MarketNote | null> {
    try {
        const res = await fetch(`${API_URL}/notes/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error("Failed to create note");
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export type TradeIdea = {
    id: number;
    symbol: string;
    direction: "LONG" | "SHORT";
    entry_price: number;
    stop_price: number;
    target_price: number;
    invalidation_notes?: string;
    thesis: string;
    status: "Draft" | "Needs Work" | "Ready for Approval" | "Approved" | "Sent" | "Closed" | "Cancelled";
    created_at: string;
    updated_at: string;
    user_id: string;
};

export async function fetchTrades(status?: string): Promise<TradeIdea[]> {
    try {
        const url = status ? `${API_URL}/trades/?status=${status}` : `${API_URL}/trades/`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch trades");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function createTrade(data: Partial<TradeIdea>): Promise<TradeIdea | null> {
    try {
        const res = await fetch(`${API_URL}/trades/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error("Failed to create trade");
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export async function updateTrade(id: number, data: Partial<TradeIdea>): Promise<TradeIdea | null> {
    try {
        const res = await fetch(`${API_URL}/trades/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error("Failed to update trade");
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export type TradeRecommendation = {
    symbol: string;
    direction: "LONG" | "SHORT" | null;
    confidence_score: number;
    entry_price: number;
    stop_price: number;
    target_price: number;
    timeframe: string;
    thesis: string;
    reasoning: string;
    invalidation: string;
    risk_reward: number;
    generated_at: string;
    playbook_used?: { id: string; name: string; trader: string } | null;
    edge_match_score?: number | null;
};

export type PlaybookSummary = {
    id: string;
    name: string;
    trader: string;
    style: string;
};

export type EdgeFingerprint = {
    sample_size: number;
    long_bias_pct: number;
    short_bias_pct: number;
    favourite_symbols: { symbol: string; count: number }[];
    avg_risk_reward: number | null;
    avg_risk_pct: number | null;
    avg_reward_pct: number | null;
};

export async function fetchPlaybooks(): Promise<PlaybookSummary[]> {
    try {
        const res = await fetch(`${API_URL}/recommendations/playbooks`);
        if (!res.ok) throw new Error("Failed to fetch playbooks");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function fetchEdge(userId?: string): Promise<EdgeFingerprint | null> {
    try {
        const params = new URLSearchParams();
        if (userId) params.append("user_id", userId);
        const res = await fetch(`${API_URL}/recommendations/edge?${params}`);
        if (!res.ok) throw new Error("Failed to fetch edge");
        const data = await res.json();
        return data.edge ?? null;
    } catch (error) {
        console.error(error);
        return null;
    }
}

export async function fetchRecommendations(
    symbols?: string,
    maxResults: number = 3,
    playbook?: string,
    userId?: string,
): Promise<TradeRecommendation[]> {
    try {
        const params = new URLSearchParams();
        if (symbols) params.append("symbols", symbols);
        params.append("max_results", maxResults.toString());
        if (playbook) params.append("playbook", playbook);
        if (userId) params.append("user_id", userId);

        const url = `${API_URL}/recommendations/?${params}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch recommendations");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function challengeTrade(id: number): Promise<GuardianChallengeResult | null> {
    try {
        const res = await fetch(`${API_URL}/trades/${id}/challenge`, {
            method: "POST",
        });
        if (!res.ok) throw new Error("Failed to challenge trade");
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export async function processApproval(tradeId: number, action: "APPROVE" | "REJECT", reasoning?: string): Promise<{ status: string, new_state: string } | null> {
    try {
        const res = await fetch(`${API_URL}/approvals/${tradeId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, reasoning }),
        });
        if (!res.ok) throw new Error("Failed to process approval");
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export async function fetchApprovalEvents(tradeId: number): Promise<ApprovalEvent[]> {
    try {
        const res = await fetch(`${API_URL}/approvals/events/${tradeId}`);
        if (!res.ok) throw new Error("Failed to fetch approval events");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function fetchTradeVersions(tradeId: number): Promise<TradeVersion[]> {
    try {
        const res = await fetch(`${API_URL}/journal/versions/${tradeId}`);
        if (!res.ok) throw new Error("Failed to fetch versions");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function fetchJournalEntries(): Promise<JournalEntry[]> {
    try {
        const res = await fetch(`${API_URL}/journal/`);
        if (!res.ok) throw new Error("Failed to fetch journal entries");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function createJournalEntry(data: JournalEntryInput): Promise<JournalEntryResult | null> {
    try {
        const res = await fetch(`${API_URL}/journal/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error("Failed to create journal entry");
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

// --- Revolut X live market data ---

export type RxTicker = {
    symbol: string;
    bid: number;
    ask: number;
    last: number;
    mid: number;
};

export async function fetchTickers(symbols: string[]): Promise<RxTicker[]> {
    try {
        const res = await fetch(`${API_URL}/revolut-x/tickers?symbols=${symbols.join(",")}`);
        if (!res.ok) return [];
        const data = await res.json();
        return data.tickers || [];
    } catch (error) {
        console.error(error);
        return [];
    }
}

export type RxOrderBook = {
    symbol: string;
    bids: { price: number; size: number }[];
    asks: { price: number; size: number }[];
};

export async function fetchOrderBook(symbol: string, limit = 20): Promise<RxOrderBook | null> {
    try {
        const res = await fetch(`${API_URL}/revolut-x/orderbook/${symbol}?limit=${limit}`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export type RxCandle = {
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    tick_volume: number;
};

export async function fetchCandles(symbol: string, timeframe = "1h", count = 100): Promise<RxCandle[]> {
    try {
        const res = await fetch(`${API_URL}/revolut-x/candles/${symbol}?timeframe=${timeframe}&count=${count}`);
        if (!res.ok) return [];
        const data = await res.json();
        return data.candles || [];
    } catch (error) {
        console.error(error);
        return [];
    }
}

export type RxAccount = {
    broker: string;
    platform: string;
    balances: { currency: string; available: number; reserved: number; balance: number }[];
};

export async function fetchRxAccount(): Promise<RxAccount | null> {
    try {
        const res = await fetch(`${API_URL}/revolut-x/account`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

// Back-compat alias
export const fetchRevolutXAccount = fetchRxAccount;

export async function fetchRxStatus(): Promise<{ connected: boolean; broker: string; status: string } | null> {
    try {
        const res = await fetch(`${API_URL}/revolut-x/status`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export const fetchRevolutXStatus = fetchRxStatus;

export type OpenAIBalance = {
    connected: boolean;
    plan: string;
    total_granted: number | null;
    total_used: number | null;
    total_available: number | null;
    currency: string;
    message?: string;
};

export async function fetchOpenAIBalance(): Promise<OpenAIBalance | null> {
    try {
        const res = await fetch(`${API_URL}/openai/balance`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export async function executeTrade(
    tradeId: number,
    opts: { volume?: number; quoteEur?: number } = {},
): Promise<ExecuteTradeResult> {
    try {
        const body: Record<string, unknown> = { use_market: true };
        if (opts.quoteEur !== undefined) {
            body.quote_eur = opts.quoteEur;
        } else {
            body.volume = opts.volume ?? 0.0001;
        }
        const res = await fetch(`${API_URL}/revolut-x/execute/${tradeId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            // Surface the actual backend error instead of a generic message
            let errMsg = `HTTP ${res.status}`;
            try {
                const errBody = await res.json();
                errMsg = errBody.detail || errBody.message || JSON.stringify(errBody);
            } catch {
                errMsg = await res.text().catch(() => errMsg);
            }
            throw new Error(errMsg);
        }
        return res.json();
    } catch (error) {
        console.error("executeTrade failed:", error);
        // Re-throw so caller can surface to user
        throw error;
    }
}

// ── Live positions (broker balances ⨝ DB fills ⨝ tickers) ──────────────────

export type LivePosition = {
    symbol: string;
    asset: string;
    qty: number;
    available: number;
    staked: number;
    reserved: number;
    tradeable: boolean;
    is_staked: boolean;
    bid: number;
    ask: number;
    entry_price: number | null;
    cost_eur: number | null;
    fees_eur: number;
    current_value_eur: number;
    pnl_eur: number | null;
    pnl_pct: number | null;
    has_db_record: boolean;
    broker_order_id: string | null;
};

export type LivePositionsResponse = {
    cash_eur: number;
    positions_value_eur: number;
    total_account_eur: number;
    invested_eur: number;
    total_pnl_eur: number;
    positions: LivePosition[];
    count: number;
    unmatched_count: number;
};

export async function fetchLivePositions(): Promise<LivePositionsResponse | null> {
    try {
        const res = await fetch(`${API_URL}/revolut-x/positions/live`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error("fetchLivePositions failed:", error);
        return null;
    }
}
