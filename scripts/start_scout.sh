#!/usr/bin/env bash
# Launch the Aurum Scout Agent
#
# Usage:
#   ./scripts/start_scout.sh [wyckoff|ict_smc|trend_follower|macro|livermore]
#
# The scout agent:
#   - Polls AI recommendations every 15 minutes
#   - Auto-approves high-confidence setups (confidence ≥80, edge ≥70, R:R ≥1.8)
#   - Logs to /tmp/scout_agent.log
#   - Coordinates with profit_hunter agents (won't double-approve same symbol)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"
source .venv/bin/activate

PLAYBOOK=${1:-trend_follower}
SYMBOLS="BTC-USD,ETH-USD,SOL-USD,ATOM-USD"
POLL_MINUTES=15

echo "🔭 Starting Scout Agent..."
echo "   Playbook:       $PLAYBOOK"
echo "   Symbols:        $SYMBOLS"
echo "   Poll interval:  ${POLL_MINUTES}m"
echo "   Log:            /tmp/scout_agent.log"
echo ""

# Check if AURUM_AUTO_APPROVE is set
if [ "$AURUM_AUTO_APPROVE" != "1" ]; then
    echo "⚠️  WARNING: AURUM_AUTO_APPROVE is not set to 1"
    echo "   The scout will run but won't auto-approve any trades."
    echo "   Set AURUM_AUTO_APPROVE=1 in .env to enable."
    echo ""
fi

# Launch in background
nohup python3 -m api.services.scout_agent \
    --playbook "$PLAYBOOK" \
    --symbols "$SYMBOLS" \
    --poll-minutes "$POLL_MINUTES" \
    > /tmp/scout_agent.log 2>&1 &

SCOUT_PID=$!
echo "✅ Scout agent started (PID: $SCOUT_PID)"
echo ""
echo "Monitor with:"
echo "  tail -f /tmp/scout_agent.log"
echo "  curl -s http://localhost:8000/api/agent/status"
echo "  curl -s http://localhost:8000/api/agent/"
echo ""
echo "Stop with:"
echo "  pkill -f scout_agent"
