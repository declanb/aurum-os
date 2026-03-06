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
