#!/usr/bin/env python3
"""
Health check endpoint for Railway deployment.
Also provides webhook forwarding to ensure bots receive commands.
"""

import os
import logging
import sys
import json
from http import HTTPStatus

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    import httpx
    
    # Create FastAPI app
    app = FastAPI(title="Allkinds Service")

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
        
    @app.post("/webhook")
    async def webhook_handler(request: Request):
        """Unified webhook handler that forwards to the appropriate bot."""
        try:
            body = await request.body()
            update = json.loads(body)
            logger.info(f"Received update: {update.get('update_id')}")
            
            # Forward the update to both bots internally
            async with httpx.AsyncClient() as client:
                # Forward to main bot (assuming it's running on port 8081)
                try:
                    main_response = await client.post(
                        "http://localhost:8081/webhook", 
                        content=body,
                        timeout=5.0
                    )
                    logger.info(f"Main bot response: {main_response.status_code}")
                except Exception as e:
                    logger.error(f"Error forwarding to main bot: {e}")
                
                # Forward to communicator bot (assuming it's running on port 8082)
                try:
                    comm_response = await client.post(
                        "http://localhost:8082/webhook", 
                        content=body,
                        timeout=5.0
                    )
                    logger.info(f"Communicator bot response: {comm_response.status_code}")
                except Exception as e:
                    logger.error(f"Error forwarding to communicator bot: {e}")
            
            return Response(status_code=HTTPStatus.OK)
        except Exception as e:
            logger.exception(f"Error in webhook handler: {e}")
            return Response(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

    if __name__ == "__main__":
        try:
            import uvicorn
            port = int(os.environ.get("PORT", 8080))
            logger.info(f"Starting Allkinds service on port {port}")
            uvicorn.run(app, host="0.0.0.0", port=port)
        except ImportError:
            logger.error("Uvicorn not installed. Falling back to simple HTTP server.")
            from http.server import HTTPServer, BaseHTTPRequestHandler
            
            class SimpleHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok","service":"allkinds"}')
                
                def do_POST(self):
                    if self.path == '/webhook':
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"ok":true}')
                        logger.info("Webhook request received but can't be processed in simple mode")
            
            port = int(os.environ.get("PORT", 8080))
            httpd = HTTPServer(('0.0.0.0', port), SimpleHandler)
            logger.info(f"Starting simple HTTP server on port {port}")
            httpd.serve_forever()
except ImportError:
    # Fallback to simple HTTP server if FastAPI is not available
    logger.warning("FastAPI not installed. Using simple HTTP server instead.")
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok","service":"allkinds"}')
        
        def do_POST(self):
            if self.path == '/webhook':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                logger.info("Webhook request received but can't be processed in simple mode")
    
    if __name__ == "__main__":
        port = int(os.environ.get("PORT", 8080))
        httpd = HTTPServer(('0.0.0.0', port), SimpleHandler)
        logger.info(f"Starting simple HTTP server on port {port}")
        httpd.serve_forever()
