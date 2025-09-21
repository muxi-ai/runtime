#!/usr/bin/env python3
"""
Simple webhook server for testing async processing.
Logs all received webhooks to a file for test analysis.
"""

import asyncio
import json
import logging
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from aiohttp import web

# Configuration
WEBHOOK_LOG_FILE = "webhook_log.json"
WEBHOOK_PORT = 8765
WEBHOOK_HOST = "0.0.0.0"

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WebhookServer:
    def __init__(self, log_file: str = WEBHOOK_LOG_FILE):
        self.log_file = Path(log_file)
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        """Setup webhook endpoints"""
        self.app.router.add_post("/", self.handle_webhook)
        self.app.router.add_post("/{path:.*}", self.handle_webhook)
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/logs", self.get_logs)

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook requests"""
        try:
            # Get request details
            webhook_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": request.method,
                "path": str(request.path),
                "headers": dict(request.headers),
                "query_params": dict(request.query),
                "content_type": request.content_type,
            }

            # Get body based on content type
            if request.content_type == "application/json":
                try:
                    webhook_data["body"] = await request.json()
                except json.JSONDecodeError:
                    webhook_data["body"] = await request.text()
                    webhook_data["body_type"] = "text"
            else:
                webhook_data["body"] = await request.text()
                webhook_data["body_type"] = "text"

            # Log to file
            self._append_to_log(webhook_data)

            # Log to console
            logger.info(f"Webhook received on {request.path}")
            logger.debug(f"Webhook data: {json.dumps(webhook_data, indent=2)}")

            # Return success response
            return web.json_response(
                {
                    "status": "success",
                    "message": "Webhook received",
                    "timestamp": webhook_data["timestamp"],
                }
            )

        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        return web.json_response(
            {
                "status": "healthy",
                "service": "MUXI Webhook Server",
                "log_file": str(self.log_file),
                "webhook_count": self._get_webhook_count(),
            }
        )

    async def get_logs(self, request: web.Request) -> web.Response:
        """Get webhook logs"""
        try:
            logs = self._read_logs()
            return web.json_response({"status": "success", "count": len(logs), "logs": logs})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    def _append_to_log(self, data: dict):
        """Append webhook data to log file using append-only approach with file locking"""
        try:
            # Ensure directory exists
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

            # Append to file with locking (JSONL format - one JSON object per line)
            with open(self.log_file, "a") as f:
                # Acquire exclusive lock to prevent race conditions
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    # Write as single line JSON (JSONL format)
                    json.dump(data, f, separators=(",", ":"))
                    f.write("\n")
                    f.flush()  # Ensure data is written immediately
                finally:
                    # Release lock
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        except OSError as e:
            logger.error(f"File I/O error writing to log file: {e}")
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization error writing to log file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error writing to log file: {e}")

    def _read_logs(self) -> list:
        """Read logs from file (JSONL format - one JSON object per line)"""
        if not self.log_file.exists():
            return []

        logs = []
        try:
            with open(self.log_file, "r") as f:
                # Acquire shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    for line in f:
                        line = line.strip()
                        if line:  # Skip empty lines
                            try:
                                logs.append(json.loads(line))
                            except json.JSONDecodeError:
                                # Skip malformed lines but continue reading
                                logger.warning(f"Skipping malformed log line: {line}")
                                continue
                finally:
                    # Release lock
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except IOError as e:
            logger.error(f"Error reading log file: {e}")
            return []

        return logs

    def _get_webhook_count(self) -> int:
        """Get total webhook count"""
        return len(self._read_logs())

    def clear_logs(self):
        """Clear webhook logs"""
        if self.log_file.exists():
            self.log_file.unlink()
        logger.info("Webhook logs cleared")


async def main():
    """Run the webhook server"""
    server = WebhookServer()

    # Clear logs on startup (optional)
    # server.clear_logs()

    runner = web.AppRunner(server.app)
    await runner.setup()

    site = web.TCPSite(runner, WEBHOOK_HOST, WEBHOOK_PORT)
    await site.start()

    logger.info(f"Webhook server started on http://{WEBHOOK_HOST}:{WEBHOOK_PORT}")
    logger.info(f"Logging webhooks to: {WEBHOOK_LOG_FILE}")
    logger.info(f"Health check: http://{WEBHOOK_HOST}:{WEBHOOK_PORT}/health")
    logger.info(f"View logs: http://{WEBHOOK_HOST}:{WEBHOOK_PORT}/logs")

    # Keep the server running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down webhook server...")


if __name__ == "__main__":
    asyncio.run(main())
