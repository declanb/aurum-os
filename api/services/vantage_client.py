"""
Singleton MetaApi connection manager for Vantage MT5 account.

Handles authentication, connection lifecycle, and reconnection.
Provides a shared connection instance for market_data and trade_executor services.
"""

import asyncio
import logging
from typing import Optional
from metaapi_cloud_sdk import MetaApi
from api.core.config import settings

logger = logging.getLogger(__name__)

# Module-level singleton state
_meta_api: Optional[MetaApi] = None
_account = None
_connection = None


async def get_meta_api() -> MetaApi:
    """Get or create the MetaApi SDK instance."""
    global _meta_api
    if _meta_api is None:
        if not settings.META_API_TOKEN:
            raise RuntimeError(
                "META_API_TOKEN is not set. Please add it to your .env file. "
                "Get your token at https://metaapi.cloud"
            )
        _meta_api = MetaApi(settings.META_API_TOKEN)
    return _meta_api


async def get_account():
    """Get the configured MetaApi account (Vantage MT5)."""
    global _account
    if _account is None:
        if not settings.META_API_ACCOUNT_ID:
            raise RuntimeError(
                "META_API_ACCOUNT_ID is not set. Please add it to your .env file. "
                "Connect your Vantage MT5 account at https://metaapi.cloud"
            )
        api = await get_meta_api()
        _account = await api.metatrader_account_api.get_account(
            settings.META_API_ACCOUNT_ID
        )
        # Deploy the account if it hasn't been deployed yet
        if _account.state not in ("DEPLOYED", "DEPLOYING"):
            logger.info("Deploying MetaApi account %s...", _account.id)
            await _account.deploy()
        # Wait for the account to connect to the broker
        if _account.state != "DEPLOYED" or _account.connection_status != "CONNECTED":
            logger.info("Waiting for account %s to connect to broker...", _account.id)
            await _account.wait_connected()
    return _account


async def get_connection():
    """
    Get the RPC connection to the MT5 terminal.
    RPC mode is ideal for request/response patterns (REST API endpoints).
    """
    global _connection
    if _connection is None:
        account = await get_account()
        _connection = account.get_rpc_connection()
        await _connection.connect()
        await _connection.wait_synchronized()
        logger.info("MetaApi RPC connection established for account %s", account.id)
    return _connection


async def get_connection_status() -> dict:
    """Return the current connection status without forcing a new connection."""
    try:
        if not settings.META_API_TOKEN or not settings.META_API_ACCOUNT_ID:
            return {
                "connected": False,
                "status": "NOT_CONFIGURED",
                "message": "MetaApi credentials not set in .env",
            }
        account = await get_account()
        return {
            "connected": account.connection_status == "CONNECTED",
            "status": account.connection_status,
            "state": account.state,
            "broker": getattr(account, "broker", "Vantage"),
            "server": getattr(account, "server", "Unknown"),
        }
    except Exception as e:
        logger.error("Connection status check failed: %s", e)
        return {
            "connected": False,
            "status": "ERROR",
            "message": str(e),
        }


async def disconnect():
    """Gracefully close the MetaApi connection."""
    global _connection, _account, _meta_api
    if _connection:
        try:
            await _connection.close()
        except Exception:
            pass
        _connection = None
    if _account:
        try:
            await _account.undeploy()
        except Exception:
            pass
        _account = None
    _meta_api = None
    logger.info("MetaApi connection closed.")
