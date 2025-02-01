# middleware.py (Updated)
import uvicorn
import logging
import sys
import httpx
from fastapi import FastAPI, Request, HTTPException

logger = logging.getLogger("middleware_logger")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

file_handler = logging.FileHandler("middleware.log", mode="a")
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

REAL_ACTION_SERVER = "http://localhost:6060"
app = FastAPI()

@app.post("/webhook")
async def action_webhook(request: Request):
    try:
        incoming_data = await request.json()
        logger.info("Incoming request: %s", incoming_data)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{REAL_ACTION_SERVER}/webhook",
                json=incoming_data,
                timeout=10.0
            )
            response.raise_for_status()
            response_data = response.json()
            logger.info("Action response: %s", response_data)
            return response_data
    except httpx.RequestError as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(500, "Failed to reach action server")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(500, "Internal server error")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5055)