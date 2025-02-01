import asyncio
import httpx
import sys
import logging
import time
from typing import Dict, Any, Optional, List

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
)
logger.addHandler(console_handler)

class RasaClientError(Exception):
    """Base exception for Rasa client errors."""
    pass

class RasaClient:
    def __init__(
        self,
        server_url: str = "http://localhost",
        server_port: int = 5005,
        sleep_delay: float = 0.0,
        sender_id: str = "default"  # Changed to 'default' since we know it works
    ) -> None:
        self.server_url = f"{server_url}:{server_port}"
        self.sleep_delay = sleep_delay
        self.sender_id = sender_id
        self.active_form: Optional[str] = None
        self.slots: Dict[str, Any] = {}
        self.client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def create(
        cls,
        server_url: str = "http://localhost",
        server_port: int = 5005,
        sleep_delay: float = 0.0,
        sender_id: str = "default"
    ) -> "RasaClient":
        instance = cls(server_url, server_port, sleep_delay, sender_id)
        instance.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return instance

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    async def get_server_status(self) -> Dict[str, Any]:
        if not self.client:
            raise RasaClientError("Client not initialized")
        response = await self.client.get(f"{self.server_url}/status")
        response.raise_for_status()
        return response.json()

    async def get_tracker(self) -> Dict[str, Any]:
        if not self.client:
            raise RasaClientError("Client not initialized")
        response = await self.client.get(
            f"{self.server_url}/conversations/{self.sender_id}/tracker"
        )
        response.raise_for_status()
        return response.json()

    async def reset_conversation(self) -> None:
        """
        Reset conversation using PUT method which we know works from our tests.
        """
        if not self.client:
            raise RasaClientError("Client not initialized")

        url = f"{self.server_url}/conversations/{self.sender_id}/tracker/events"
        headers = {"Content-Type": "application/json"}

        # Using the events sequence that worked in our curl tests
        events = [
            {"event": "session_started"},
            {
                "event": "action",
                "name": "action_listen",
                "policy": None,
                "confidence": None
            }
        ]

        try:
            response = await self.client.put(url, json=events, headers=headers)
            response.raise_for_status()
            logger.info("Successfully reset conversation")
        except Exception as e:
            logger.error(f"Failed to reset conversation: {e}")
            # Continue anyway since we know the webhook endpoint works

    async def send_message(self, message_text: str) -> List[Dict[str, Any]]:
        """
        Send a message using the webhook endpoint which we know works reliably.
        """
        if not self.client:
            raise RasaClientError("Client not initialized")

        url = f"{self.server_url}/webhooks/rest/webhook"
        payload = {
            "sender": self.sender_id,
            "message": message_text
        }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            resp_json = response.json()

            # Update tracker state
            try:
                tracker_data = await self.get_tracker()
                self.active_form = tracker_data.get("active_loop", {}).get("name")
                self.slots = tracker_data.get("slots", {})
            except Exception as e:
                logger.error(f"Tracker update failed: {e}")
                self.active_form = None
                self.slots = {}

            if self.active_form and self.sleep_delay > 0:
                await asyncio.sleep(self.sleep_delay)

            return resp_json if resp_json else [{"text": "No response from bot"}]
        except Exception as e:
            logger.error(f"Message send failed: {e}")
            return [{"text": "Error communicating with the bot"}]

    @staticmethod
    def get_bot_response_text(messages: List[Dict[str, Any]]) -> List[str]:
        if not messages:
            return ["[No response]"]
        return [msg["text"] for msg in messages if "text" in msg] or ["[No text response]"]

async def interactive_chat(client: RasaClient) -> None:
    print("Bot: Hello! Type a message or 'quit'/'exit' to end.")
    while True:
        try:
            user_message = input("You: ").strip()
            if not user_message:
                continue
            if user_message.lower() in ("quit", "exit"):
                print("Bot: Goodbye!")
                return

            bot_messages = await client.send_message(user_message)
            for text in client.get_bot_response_text(bot_messages):
                print(f"Bot: {text}")

        except (KeyboardInterrupt, EOFError):
            print("\nBot: Session terminated.")
            return
        except Exception as e:
            logger.error(f"Chat error: {e}")
            print("Bot: An error occurred. Please try again.")

async def main() -> None:
    try:
        client = await RasaClient.create()
        
        # Verify server is up
        try:
            status = await client.get_server_status()
            logger.info(f"Connected to Rasa server. Status: {status}")
        except Exception as e:
            logger.error(f"Server connection failed: {e}")
            print("Error: Ensure Rasa server is running at http://localhost:5005")
            return

        # Try to reset but continue even if it fails
        try:
            await client.reset_conversation()
        except Exception as e:
            logger.warning(f"Reset failed but continuing: {e}")

        # Start chat
        await interactive_chat(client)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print("Critical failure. Check logs for details.")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
