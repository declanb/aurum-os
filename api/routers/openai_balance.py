"""
OpenAI account balance & usage endpoint.
Shows remaining credits and current billing period usage.
"""

from fastapi import APIRouter, HTTPException
import httpx
from api.core.config import settings

router = APIRouter(prefix="/openai", tags=["openai"])


@router.get("/balance")
async def get_balance():
    """
    Fetch OpenAI account credit balance and usage.
    
    Returns:
        - total_granted: prepaid credits (if any)
        - total_used: amount used in current billing period
        - total_available: remaining balance
        - currency: USD
    """
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    
    try:
        async with httpx.AsyncClient() as client:
            # OpenAI billing/subscription endpoint
            headers = {
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            
            # Get subscription info (for paid accounts)
            sub_resp = await client.get(
                "https://api.openai.com/v1/dashboard/billing/subscription",
                headers=headers,
                timeout=10.0
            )
            
            if sub_resp.status_code == 200:
                sub_data = sub_resp.json()
                
                # Get usage for current billing period
                usage_resp = await client.get(
                    "https://api.openai.com/v1/dashboard/billing/usage",
                    headers=headers,
                    params={
                        "start_date": sub_data.get("current_period_start", ""),
                        "end_date": sub_data.get("current_period_end", ""),
                    },
                    timeout=10.0
                )
                
                usage_data = usage_resp.json() if usage_resp.status_code == 200 else {}
                
                return {
                    "connected": True,
                    "plan": sub_data.get("plan", {}).get("title", "Unknown"),
                    "total_granted": sub_data.get("hard_limit_usd", 0),
                    "total_used": usage_data.get("total_usage", 0) / 100,  # cents → dollars
                    "total_available": sub_data.get("hard_limit_usd", 0) - (usage_data.get("total_usage", 0) / 100),
                    "currency": "USD",
                    "billing_period_start": sub_data.get("current_period_start"),
                    "billing_period_end": sub_data.get("current_period_end"),
                }
            else:
                # For free-tier or API key without billing access
                return {
                    "connected": True,
                    "plan": "API Key (no billing access)",
                    "total_granted": None,
                    "total_used": None,
                    "total_available": None,
                    "currency": "USD",
                    "message": "API key valid but billing endpoint returned " + str(sub_resp.status_code)
                }
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenAI API timeout")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch OpenAI balance: {str(e)}")
