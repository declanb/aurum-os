# AI Trade Recommendations - Quick Start Guide

## Overview

Aurum OS now includes AI-powered trade recommendations that analyze market trends and suggest actionable trade setups with entry, stop-loss, and take-profit levels.

## Features

- **GPT-4 Market Analysis**: Real-time analysis of price action, technical indicators, and trend alignment
- **Risk Management**: All recommendations include R:R ratio ≥ 1.5
- **One-Click Execution**: Convert recommendations directly to trade ideas for Guardian review
- **Confidence Scoring**: Each recommendation includes a 0-100 confidence score
- **Detailed Reasoning**: Expandable analysis explaining the trade setup and invalidation criteria

## Setup

### 1. Configure OpenAI API Key

Add your OpenAI API key to the `.env` file in the project root:

```bash
OPENAI_API_KEY="sk-proj-..."
```

If you don't have an API key yet:
1. Visit https://platform.openai.com/api-keys
2. Create a new secret key
3. Add it to your `.env` file

**Note:** Without an API key, the system will display mock recommendations for demo purposes.

### 2. Install Dependencies

The `openai` package should already be installed. If not:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start the Services

Terminal 1 (API):
```bash
source .venv/bin/activate
uvicorn api.index:app --reload --port 8000
```

Terminal 2 (Web):
```bash
cd web
npm run dev
```

## Usage

### Viewing Recommendations

1. Navigate to **Trade Planner** page (`/app/planner`)
2. The AI Recommendations panel appears at the top
3. Click **Refresh** to generate new recommendations based on current market data

### Creating a Trade from a Recommendation

1. Review the recommended trade setup
2. Click **"Create Trade Idea"** button
3. The trade is automatically created in **Draft** status
4. It appears in your "Pending Ideas" list for Guardian review

### Recommendation Details

Each recommendation includes:

- **Symbol** (e.g., BTC-USD, ETH-USD, SOL-USD)
- **Direction** (LONG or SHORT)
- **Confidence Score** (50-100, higher = stronger setup)
- **Entry Price** - Suggested entry point
- **Stop Price** - Risk management level
- **Target Price** - Take-profit target
- **Timeframe** - Analysis timeframe (1h, 4h, 1d)
- **Thesis** - Brief summary of the setup
- **Risk:Reward Ratio** - Expected R:R
- **Detailed Analysis** - Expandable section with full reasoning and invalidation criteria

## How It Works

1. **Data Collection**: Fetches live market data from Revolut X including:
   - Current bid/ask prices
   - OHLCV candles (1H and 4H timeframes)
   - Recent price action

2. **Technical Analysis**: Calculates indicators:
   - Simple Moving Averages (SMA 20 & 50)
   - Momentum (20-period change)
   - Support/Resistance levels
   - Volatility

3. **AI Analysis**: GPT-4 evaluates:
   - Trend alignment across timeframes
   - Support/resistance tests
   - Momentum and volatility patterns
   - Clear entry/exit levels with R:R ≥ 1.5

4. **Filtering**: Only high-confidence setups (≥50% confidence) are shown

## API Endpoint

The recommendations are available via REST API:

```bash
GET /api/recommendations/?symbols=BTC-USD,ETH-USD&max_results=3
```

**Query Parameters:**
- `symbols` (optional) - Comma-separated list of symbols to analyze
- `max_results` (optional, default=3) - Maximum number of recommendations (1-10)

**Response:**
```json
[
  {
    "symbol": "BTC-USD",
    "direction": "LONG",
    "confidence_score": 75,
    "entry_price": 68500,
    "stop_price": 67200,
    "target_price": 71000,
    "timeframe": "4h",
    "thesis": "Bullish engulfing on 4H with momentum shift",
    "reasoning": "Price bounced off key support...",
    "invalidation": "Close below $67,000 invalidates setup",
    "risk_reward": 1.92,
    "generated_at": "2024-01-15T10:30:00"
  }
]
```

## Guardian Integration

**Important:** All AI recommendations still require Guardian approval before execution.

1. Recommendation → Draft Trade Idea
2. Click **"Challenge with Guardian"** to validate
3. Guardian checks:
   - Risk/Reward ratio (must be ≥1.5)
   - Thesis quality (≥20 characters)
   - Invalidation notes present
4. If passed → Ready for Approval
5. Manual approval → Trade can be executed

This ensures human oversight and prevents blind algorithmic trading.

## Customization

### Analyzing Different Symbols

Edit the default symbols in `api/routers/recommendations.py`:

```python
@router.get("/")
async def get_recommendations(
    symbols: Optional[str] = Query(None),  # Pass custom symbols here
    ...
):
    if symbols is None:
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD"]  # Default symbols
```

### Adjusting Confidence Threshold

In `api/services/ai_advisor.py`, modify the confidence filter:

```python
# Only return recommendations with confidence ≥ 50
if not result.get("direction") or result.get("confidence_score", 0) < 50:
    return None
```

### Changing Analysis Timeframes

In `api/services/ai_advisor.py`, adjust candle timeframes:

```python
candles_1h = await market_data.get_candles(symbol, timeframe="1h", count=100)
candles_4h = await market_data.get_candles(symbol, timeframe="4h", count=50)
# Available: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
```

## Troubleshooting

### No Recommendations Showing

1. **Check API logs** for errors:
   ```bash
   # In the terminal running uvicorn
   # Look for "Failed to generate recommendation" or OpenAI errors
   ```

2. **Verify OpenAI API Key**:
   ```python
   # In Python console:
   from api.core.config import settings
   print(bool(settings.OPENAI_API_KEY))  # Should print True
   ```

3. **Check Revolut X connection**:
   ```bash
   curl http://localhost:8000/api/revolut-x/account
   ```

### "Failed to fetch recommendations" Error

- Check that the API server is running on port 8000
- Verify the frontend API URL in `web/lib/api.ts` matches your setup
- Check browser console for detailed error messages

### Recommendations Are Always the Same

- This means OpenAI API is not configured and mock data is being used
- Add your OpenAI API key to `.env` and restart the API server

## Cost Considerations

Each recommendation request:
- Makes 1 GPT-4 API call per symbol analyzed
- Average token usage: ~1,000-2,000 tokens per call
- Approximate cost: $0.01-0.03 per request (at GPT-4 pricing)

To minimize costs:
- Use the Refresh button sparingly (not auto-refresh)
- Start with 2-3 symbols instead of analyzing many pairs
- Consider using GPT-3.5-turbo for cheaper analysis (edit model in `ai_advisor.py`)

## Next Steps

1. Review the recommendations in the Trade Planner
2. Create trades from promising setups
3. Challenge with Guardian to validate risk parameters
4. Approve and execute through Revolut X

Remember: AI recommendations are advisory only. Always apply your own analysis and risk management before executing trades.
