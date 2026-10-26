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
    direction: "LONG" | "SHORT" | "EXIT";
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

export async function fetchTradesResult(status?: string): Promise<{ trades: TradeIdea[]; error: string | null }> {
    try {
        const url = status ? `${API_URL}/trades/?status=${encodeURIComponent(status)}` : `${API_URL}/trades/`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) return { trades: [], error: "Could not load trade ideas" };
        const data = await res.json();
        if (!Array.isArray(data)) return { trades: [], error: "Could not load trade ideas" };
        return { trades: data as TradeIdea[], error: null };
    } catch (error) {
        console.error(error);
        return { trades: [], error: "Could not load trade ideas" };
    }
}

export async function fetchTrades(status?: string): Promise<TradeIdea[]> {
    const result = await fetchTradesResult(status);
    return result.trades;
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
): Promise<any | null> {
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
    entry_ticket_id?: number | null;
    exit?: ExitBracketView | null;
};

export type ExitBracketView = {
    id: number;
    entry_ticket_id: number;
    trade_idea_id: number;
    exit_trade_idea_id: number | null;
    exit_trade_status: string | null;
    symbol: string;
    direction: string;
    qty: number;
    entry_price: number;
    initial_stop_price: number;
    stop_price: number;
    target_price: number;
    high_water_price: number;
    trail_armed: boolean;
    status: string;
    exit_reason: string | null;
    last_price: number | null;
    last_trigger: string | null;
    pending_clear: boolean;
};

export type ExitBracketResponse = {
    paper_trading: boolean;
    live_exit: "approval_required" | "paper_auto";
    rule: string;
    count: number;
    brackets: ExitBracketView[];
};

export function exitStatusLabel(status: string): string {
    const labels: Record<string, string> = {
        armed: "Armed",
        exit_proposed: "Exit pending",
        closing: "Closing",
        paper_closed: "Paper closed",
        closed: "Closed",
        cancelled: "Cancelled",
    };
    return labels[status] || status;
}

export async function fetchExitBrackets(): Promise<ExitBracketResponse | null> {
    try {
        const res = await fetch(`${API_URL}/exits`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error("fetchExitBrackets failed:", error);
        return null;
    }
}

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

export type FleetCard = {
    id: string;
    name: string;
    kind: string;
    blurb: string;
    health: "healthy" | "stale" | "idle" | "off";
    paused: boolean;
    symbol: string | null;
    last_action: string;
    last_action_at: string | null;
    last_heartbeat: string | null;
    can_clear: boolean;
    detail: string | null;
};

export type FleetBoard = {
    paused: boolean;
    paper_trading: boolean;
    cron_enabled: boolean;
    cards: FleetCard[];
};

export async function fetchFleet(): Promise<FleetBoard | null> {
    try {
        const res = await fetch(`${API_URL}/agent/fleet`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export async function pauseAgents(): Promise<boolean> {
    const res = await fetch(`${API_URL}/agent/pause`, { method: "POST" });
    return res.ok;
}

export async function resumeAgents(): Promise<boolean> {
    const res = await fetch(`${API_URL}/agent/resume`, { method: "POST" });
    return res.ok;
}

export async function cleanStaleAgents(): Promise<boolean> {
    const res = await fetch(`${API_URL}/agent/clean`, { method: "POST" });
    return res.ok;
}

export async function clearAgent(agentId: string): Promise<boolean> {
    const res = await fetch(`${API_URL}/agent/clear/${encodeURIComponent(agentId)}`, { method: "POST" });
    return res.ok;
}

export type IdeaExplanation = {
    trade_id: number;
    symbol: string;
    direction: string;
    status?: string;
    headline: string;
    why: string;
    thesis: string;
    invalidation: string;
    levels: {
        entry: number | null;
        stop: number | null;
        target: number | null;
        risk_reward: number | null;
    };
    spot_note: string;
    advisory: boolean;
    can_execute: boolean;
};

export type GuruReply = {
    reply: string;
    advisory: boolean;
    can_execute: boolean;
    source: string;
    trade_id?: number;
};

export async function fetchIdeaWhy(tradeId: number): Promise<IdeaExplanation | null> {
    try {
        const res = await fetch(`${API_URL}/advisor/idea/${tradeId}`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error(error);
        return null;
    }
}

export async function askIdea(tradeId: number, question: string): Promise<GuruReply | null> {
    const res = await fetch(`${API_URL}/advisor/idea/${tradeId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
    });
    if (!res.ok) {
        throw new Error("The guru could not answer that.");
    }
    return res.json();
}

export async function askGuru(
    messages: { role: "user" | "assistant"; content: string }[],
    tradeId?: number,
): Promise<GuruReply> {
    const res = await fetch(`${API_URL}/advisor/guru`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages, trade_id: tradeId ?? null }),
    });
    if (!res.ok) {
        throw new Error("The guru could not answer that.");
    }
    return res.json();
}

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

// ── Helm profit notifications (in-app; no broker write) ────────────────────

export type ProfitNotification = {
    id: number;
    kind: "in_profit" | "take_profit" | "exit_filled" | string;
    symbol: string;
    position_key: string;
    pnl_eur: number | null;
    pnl_pct: number | null;
    qty: number | null;
    entry_price: number | null;
    mark_price: number | null;
    title: string;
    body: string;
    read: boolean;
    read_at: string | null;
    created_at: string | null;
};

export type ProfitNotificationList = {
    count: number;
    unread_count: number;
    notifications: ProfitNotification[];
    created?: number;
    source?: string;
};

export async function fetchProfitNotifications(): Promise<ProfitNotificationList | null> {
    try {
        const res = await fetch(`${API_URL}/notifications`);
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error("fetchProfitNotifications failed:", error);
        return null;
    }
}

export async function scanProfitNotifications(): Promise<ProfitNotificationList | null> {
    try {
        const res = await fetch(`${API_URL}/notifications/scan`, { method: "POST" });
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error("scanProfitNotifications failed:", error);
        return null;
    }
}

export async function markProfitNotificationRead(id: number): Promise<ProfitNotificationList | null> {
    try {
        const res = await fetch(`${API_URL}/notifications/${id}/read`, { method: "POST" });
        if (!res.ok) return null;
        return fetchProfitNotifications();
    } catch (error) {
        console.error("markProfitNotificationRead failed:", error);
        return null;
    }
}

export async function markAllProfitNotificationsRead(): Promise<ProfitNotificationList | null> {
    try {
        const res = await fetch(`${API_URL}/notifications/read-all`, { method: "POST" });
        if (!res.ok) return null;
        return res.json();
    } catch (error) {
        console.error("markAllProfitNotificationsRead failed:", error);
        return null;
    }
}
