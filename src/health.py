#!/usr/bin/env python3
"""
Health check endpoint for Railway deployment.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import logging

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Allkinds Health Check")

@app.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    return {
        "status": "ok",
        "service": "allkinds",
        "environment": os.environ.get("RAILWAY_ENVIRONMENT", "unknown")
    }

@app.get("/")
async def root():
    """Root endpoint redirects to health check."""
    return await health_check()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
