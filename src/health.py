#!/usr/bin/env python3
"""
Health check module for the bot.
Provides a small HTTP server for health checks and webhook handling.
"""

import asyncio
import json
import logging
import os
import sys
from http import HTTPStatus
from typing import Tuple, Dict, Any, Optional

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
MAIN_BOT_PORT = int(os.environ.get("MAIN_BOT_PORT", 8081))
MAIN_BOT_HOST = os.environ.get("MAIN_BOT_HOST", "localhost")

# Create the FastAPI app
app = FastAPI(title="Allkinds Bot Health Check")

class HealthStatus(BaseModel):
    """Health status model."""
    status: str
    details: Dict[str, Any]

async def check_bot_health(host: str, port: int) -> bool:
    """Check if a bot is healthy by making a request to its health endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{host}:{port}/health", timeout=5.0)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False

@app.get("/health", response_model=HealthStatus)
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    # Check each bot's health
    main_status = await check_bot_health(MAIN_BOT_HOST, MAIN_BOT_PORT)
    
    status = "ok" if main_status else "unhealthy"
    
    return {
        "status": status,
        "details": {
            "main_bot": main_status,
        }
    }

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Unified webhook handler that forwards to the appropriate bot."""
    try:
        body = await request.body()
        try:
            update = json.loads(body)
            update_id = update.get("update_id", "unknown")
            logger.info(f"Received update ID: {update_id}")
            
            # Log message text if available
            if "message" in update and "text" in update["message"]:
                logger.info(f"Message text: {update['message']['text']}")
        except Exception as e:
            logger.error(f"Error parsing update: {e}")
        
        # Forward the update to the main bot internally
        async with httpx.AsyncClient() as client:
            # Forward to main bot
            main_url = f"http://{MAIN_BOT_HOST}:{MAIN_BOT_PORT}/webhook"
            logger.info(f"Forwarding to main bot: {main_url}")
            try:
                main_response = await client.post(
                    main_url, 
                    content=body,
                    timeout=5.0
                )
                logger.info(f"Main bot response: {main_response.status_code}")
            except Exception as e:
                logger.error(f"Error forwarding to main bot: {e}")
        
        return Response(status_code=HTTPStatus.OK)
    except Exception as e:
        logger.exception(f"Error in webhook handler: {e}")
        return Response(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": str(exc.detail)},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors."""
    return JSONResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content={"message": str(exc)},
    )

async def wait_for_bots(timeout: int = 60) -> bool:
    """Wait for bots to become healthy."""
    logger.info("Waiting for bots to become healthy...")
    start = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start < timeout:
        main_status = await check_bot_health(MAIN_BOT_HOST, MAIN_BOT_PORT)
        
        if main_status:
            logger.info("All bots are healthy!")
            return True
        
        logger.info(f"Waiting for bots... Main: {main_status}")
        await asyncio.sleep(5)
    
    logger.warning("Timed out waiting for bots to become healthy!")
    return False

@app.on_event("startup")
async def startup_event():
    """Print startup information."""
    logger.info(f"Health check server started")
    logger.info(f"Main bot expected at {MAIN_BOT_HOST}:{MAIN_BOT_PORT}")
    
    # Don't block startup if bots aren't ready
    asyncio.create_task(wait_for_bots())
