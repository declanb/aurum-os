# Helm exit brackets

Revolut X spot cannot attach a stop-loss or take-profit to an order. `trade_executor.execute_trade` accepts `stop_loss` and `take_profit` and does not send them to the broker. Closing a long is a separate market sell of the base asset.

After an approved LONG entry fills, Aurum arms an `ExitBracket` from that fill and the idea's `stop_price` / `target_price`. The bracket is the protective order the exchange does not offer.

## Rule (spot LONG only)

`R` is the fill price minus the original stop. Trailing stays off when `R <= 0`.

The mark is the **bid** (what a market sell can receive).

1. **Hard stop.** Bid at or through the original stop → `hard_stop`.
2. **Take-profit.** Bid at or through `target_price` → `take_profit`. Checked after the stop, so a gap through the stop protects capital first.
3. **Trailing ratchet.** Once the bid high-water reaches the fill plus **1R**, the stop moves to high-water minus **1R**. It steps only when the new stop is at least **0.25R** above the current stop. It never moves down and never under the original stop. A breach of that raised stop is `trailing_stop`.

Shorts and leverage are not armed.

Worked example: fill 100, stop 90, target 130 (`R = 10`).

| Bid | Effective stop | What happens |
| --- | --- | --- |
| 109 | 90 | Still inside 1R. Trail off. |
| 110 | 100 | Trail arms. Stop jumps to fill (1R behind 110). |
| 115 | 105 | Step is 0.5R, so the stop ratchets. |
| 116 | 105 | Step would be 0.1R, under 0.25R. Stop stays. |
| 105 | 105 | `trailing_stop`. |
| 130 (from a fresh bracket) | ratchets, then target | `take_profit` if the bid is still above the stop. |
| 90 (before any rally) | 90 | `hard_stop`. |

## Live vs paper

| Mode | On a trigger |
| --- | --- |
| Live (`PAPER_TRADING` off) | Create an `EXIT` trade idea in **Ready for Approval**. No broker order. A human approves (ApprovalEvent), then Execute sells `bracket.qty` at market. |
| Paper (`PAPER_TRADING=1`) | Same idea, plus an ApprovalEvent written by the monitor, then a simulated sell. |

`/api/cron/hunt` is the monitor. It stays behind `AURUM_AGENTS_ENABLED`. It does not call the broker. The local `profit_hunter` CLI uses the same rule and also refuses live sells.

Rejecting an exit idea cancels that proposal. Helm waits until price trades back to the safe side of the trigger and a 15-minute cooldown has passed before it proposes again.

## Where to look

- `GET /api/exits` — stop, target, trail, and exit-idea status
- Live positions (`GET /api/revolut-x/positions/live`) include an `exit` object per symbol
- Open trades and My Trade show the same status
- Approvals queue shows `EXIT` ideas. Execute on those sells the bracket quantity and ignores a quote-EUR buy amount
