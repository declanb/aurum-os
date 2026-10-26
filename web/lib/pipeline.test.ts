import assert from "node:assert/strict";
import test from "node:test";

import { pipelineIdeas, RECENT_SENT_LIMIT, type PipelineStatus } from "./pipeline.ts";
import type { TradeIdea } from "./api.ts";

function idea(partial: Pick<TradeIdea, "id" | "status"> & Partial<TradeIdea>): TradeIdea {
  return {
    symbol: "AVAX-EUR",
    direction: "LONG",
    entry_price: 10,
    stop_price: 9,
    target_price: 12,
    thesis: "staged",
    created_at: "2026-10-01T00:00:00.000Z",
    updated_at: "2026-10-01T00:00:00.000Z",
    user_id: "seed_user",
    ...partial,
  };
}

test("lists ready, needs work, approved, and only the newest sent ideas", () => {
  const sent = Array.from({ length: RECENT_SENT_LIMIT + 3 }, (_, index) =>
    idea({
      id: 100 + index,
      status: "Sent",
      symbol: `S${index}`,
      updated_at: `2026-10-${String(index + 1).padStart(2, "0")}T12:00:00.000Z`,
    }),
  );
  const trades = [
    idea({ id: 1, status: "Draft", updated_at: "2026-10-20T00:00:00.000Z" }),
    idea({ id: 2, status: "Closed", updated_at: "2026-10-20T00:00:00.000Z" }),
    idea({ id: 3, status: "Cancelled", updated_at: "2026-10-20T00:00:00.000Z" }),
    idea({ id: 55, status: "Sent", symbol: "AVAX-EUR", updated_at: "2026-10-26T09:00:00.000Z" }),
    idea({ id: 4, status: "Approved", updated_at: "2026-10-25T00:00:00.000Z" }),
    idea({ id: 7, status: "Approved", updated_at: "2026-10-26T08:00:00.000Z" }),
    idea({ id: 5, status: "Ready for Approval", updated_at: "2026-10-24T00:00:00.000Z" }),
    idea({ id: 8, status: "Ready for Approval", updated_at: "2026-10-26T07:00:00.000Z" }),
    idea({ id: 6, status: "Needs Work", updated_at: "2026-10-23T00:00:00.000Z" }),
    ...sent,
  ];

  const listed = pipelineIdeas(trades);
  const statuses = listed.map((trade) => trade.status);

  assert.deepEqual(
    [...new Set(statuses)],
    ["Ready for Approval", "Needs Work", "Approved", "Sent"] satisfies PipelineStatus[],
  );
  assert.equal(listed.filter((trade) => trade.status === "Sent").length, RECENT_SENT_LIMIT);
  assert.equal(listed[0]?.id, 8);
  assert.equal(listed.find((trade) => trade.status === "Needs Work")?.id, 6);
  assert.equal(listed.filter((trade) => trade.status === "Approved").map((trade) => trade.id).join(","), "7,4");
  assert.equal(listed.some((trade) => trade.id === 55), true);
  assert.equal(listed.some((trade) => trade.status === "Draft"), false);
  assert.equal(listed.some((trade) => trade.id === 100), false);
});

test("returns an empty list when nothing is in the pipeline", () => {
  assert.deepEqual(pipelineIdeas([idea({ id: 1, status: "Draft" })]), []);
  assert.deepEqual(pipelineIdeas([]), []);
});
