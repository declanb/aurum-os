// Create an API service for frontend data fetching
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

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

export async function challengeTrade(id: number): Promise<any | null> {
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

export async function fetchApprovalEvents(tradeId: number): Promise<any[]> {
    try {
        const res = await fetch(`${API_URL}/approvals/events/${tradeId}`);
        if (!res.ok) throw new Error("Failed to fetch approval events");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function fetchTradeVersions(tradeId: number): Promise<any[]> {
    try {
        const res = await fetch(`${API_URL}/journal/versions/${tradeId}`);
        if (!res.ok) throw new Error("Failed to fetch versions");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function fetchJournalEntries(): Promise<any[]> {
    try {
        const res = await fetch(`${API_URL}/journal/`);
        if (!res.ok) throw new Error("Failed to fetch journal entries");
        return res.json();
    } catch (error) {
        console.error(error);
        return [];
    }
}

export async function createJournalEntry(data: any): Promise<any | null> {
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

export async function executeTrade(tradeId: number, volume: number = 0.0001): Promise<any | null> {
    try {
        const res = await fetch(`${API_URL}/revolut-x/execute/${tradeId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ volume, use_market: true }),
        });
        if (!res.ok) throw new Error("Failed to execute trade on Revolut X");
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}
