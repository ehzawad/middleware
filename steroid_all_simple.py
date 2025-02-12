import asyncio
import httpx
import sys
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from openai import OpenAI

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
)
logger.addHandler(console_handler)

CONFIDENCE_THRESHOLD = 0.80

@dataclass
class ConversationTurn:
    timestamp: datetime
    user_message: str
    bot_response: str
    confidence: float
    system: str  # either 'rasa' or 'openai'

class ConversationHistory:
    def __init__(self):
        self.clear()
    
    def clear(self):
        """Reset the conversation history"""
        self.turns: List[ConversationTurn] = []
    
    def add_turn(self, user_message: str, bot_response: str, confidence: float, system: str):
        turn = ConversationTurn(
            timestamp=datetime.now(),
            user_message=user_message,
            bot_response=bot_response,
            confidence=confidence,
            system=system
        )
        self.turns.append(turn)
    
    def get_system_conversations(self, system: str) -> List[ConversationTurn]:
        return [turn for turn in self.turns if turn.system == system]
    
    def format_for_summary(self, system: Optional[str] = None) -> str:
        turns = self.turns if system is None else self.get_system_conversations(system)
        if not turns:
            return "No conversation history available."
            
        formatted = []
        for turn in turns:
            formatted.append(f"Time: {turn.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            formatted.append(f"System: {turn.system}")
            formatted.append(f"Confidence: {turn.confidence:.2f}")
            formatted.append(f"User: {turn.user_message}")
            formatted.append(f"Bot: {turn.bot_response}")
            formatted.append("-" * 50)
        return "\n".join(formatted)

class RasaClientError(Exception):
    """Base exception for Rasa client errors."""
    pass

class RasaClient:
    def __init__(
        self,
        server_url: str = "http://localhost",
        server_port: int = 5005,
        sleep_delay: float = 0.0,
        sender_id: str = "default"
    ) -> None:
        self.server_url = f"{server_url}:{server_port}"
        self.sleep_delay = sleep_delay
        self.sender_id = sender_id
        self.active_form: Optional[str] = None
        self.slots: Dict[str, Any] = {}
        self.client: Optional[httpx.AsyncClient] = None
        self.conversation_history = ConversationHistory()
        
        # Initialize OpenAI
        logger.info("Initializing OpenAI client...")
        self.openai_client = OpenAI()
        self.assistant = None


    async def reset_conversation(self) -> None:
        if not self.client:
            raise RasaClientError("Client not initialized")
        
        url = f"{self.server_url}/conversations/{self.sender_id}/tracker/events"
        headers = {"Content-Type": "application/json"}
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


    async def ensure_assistant(self):
        """Create OpenAI assistant if not exists."""
        if not self.assistant:
            logger.info("Creating new OpenAI assistant...")
            self.assistant = self.openai_client.beta.assistants.create(
                name="Fallback Handler",
                model="gpt-4-1106-preview",
                instructions="""You are a helpful assistant that provides concise responses.
                Keep responses friendly but brief, ideally 1-2 sentences."""
            )
            logger.info(f"Assistant created with ID: {self.assistant.id}")
        return self.assistant

    async def get_conversation_summary(self, system: Optional[str] = None) -> str:
        try:
            formatted_conversation = self.conversation_history.format_for_summary(system)
            if "No conversation history" in formatted_conversation:
                return formatted_conversation
            
            summary_prompt = f"""Please provide a concise summary of the following conversation:
            
            {formatted_conversation}
            
            Focus on:
            1. Main topics discussed
            2. Key outcomes or decisions
            3. Any important patterns in the interaction
            """
            
            assistant = await self.ensure_assistant()
            thread = self.openai_client.beta.threads.create()
            
            self.openai_client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=summary_prompt
            )
            
            run = self.openai_client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id
            )
            
            while True:
                run_status = self.openai_client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run_status.status == 'completed':
                    messages = self.openai_client.beta.threads.messages.list(
                        thread_id=thread.id
                    )
                    for msg in messages.data:
                        if msg.role == "assistant":
                            return msg.content[0].text.value
                
                elif run_status.status in ['failed', 'cancelled', 'expired']:
                    return "Failed to generate conversation summary."
                
                await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return "Failed to generate conversation summary due to an error."

    async def get_server_status(self) -> Dict[str, Any]:
        if not self.client:
            raise RasaClientError("Client not initialized")
        # UPDATED: Use '/status' instead of '/health' for Rasa server
        response = await self.client.get(f"{self.server_url}/status")
        response.raise_for_status()
        return response.json()

    async def get_openai_response(self, message: str) -> str:
        """Get response from OpenAI for low confidence queries."""
        try:
            logger.info(f"Getting OpenAI response for: '{message}'")
            assistant = await self.ensure_assistant()
            
            thread = self.openai_client.beta.threads.create()
            self.openai_client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=message
            )
            
            run = self.openai_client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id
            )
            
            start_time = time.time()
            while time.time() - start_time < 10:  # 10 second timeout
                run_status = self.openai_client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                
                if run_status.status == 'completed':
                    messages = self.openai_client.beta.threads.messages.list(
                        thread_id=thread.id
                    )
                    for msg in messages.data:
                        if msg.role == "assistant":
                            response_text = msg.content[0].text.value
                            logger.info(f"OpenAI response: '{response_text}'")
                            return response_text
                    break
                elif run_status.status in ['failed', 'cancelled', 'expired']:
                    logger.error(f"OpenAI run failed with status: {run_status.status}")
                    return "I apologize, but I'm having trouble understanding. Could you rephrase that?"
                
                await asyncio.sleep(0.1)
            
            return "I apologize, but I'm not able to help with that right now."
            
        except Exception as e:
            logger.error(f"OpenAI error: {str(e)}")
            return "I apologize, but I'm having trouble. Please try again."

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

    async def send_message(self, message_text: str) -> List[Dict[str, Any]]:
        """Send message and track in conversation history."""
        logger.info(f"Processing message: '{message_text}'")
        
        if not self.client:
            raise RasaClientError("Client not initialized")

        try:
            # First check intent confidence
            parse_response = await self.client.post(
                f"{self.server_url}/model/parse",
                json={"text": message_text}
            )
            parse_response.raise_for_status()
            parse_data = parse_response.json()
            confidence = parse_data.get("intent", {}).get("confidence", 0.0)
            logger.info(f"Intent confidence: {confidence}")

            # If confidence is low, use OpenAI
            if confidence < CONFIDENCE_THRESHOLD:
                logger.info("Using OpenAI fallback (low confidence)")
                openai_response = await self.get_openai_response(message_text)
                
                # Store in conversation history
                self.conversation_history.add_turn(
                    user_message=message_text,
                    bot_response=openai_response,
                    confidence=confidence,
                    system='openai'
                )
                
                return [{"text": openai_response}]

            # For high confidence, use existing middleware flow
            url = f"{self.server_url}/webhooks/rest/webhook"
            payload = {
                "sender": self.sender_id,
                "message": message_text
            }

            logger.info("Using middleware for Rasa actions (high confidence)")
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            resp_json = response.json()
            
            # Extract bot response text
            bot_response = " ".join([msg.get("text", "") for msg in resp_json if "text" in msg])
            
            # Store in conversation history
            self.conversation_history.add_turn(
                user_message=message_text,
                bot_response=bot_response,
                confidence=confidence,
                system='rasa'
            )

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
            logger.error(f"Error processing message: {str(e)}")
            return [{"text": "Error communicating with the bot"}]

    @staticmethod
    def get_bot_response_text(messages: List[Dict[str, Any]]) -> List[str]:
        if not messages:
            return ["[No response]"]
        return [msg["text"] for msg in messages if "text" in msg] or ["[No text response]"]

    # NEW: Added missing get_tracker method
    async def get_tracker(self) -> Dict[str, Any]:
        """Retrieve the current tracker state from the Rasa server."""
        if not self.client:
            raise RasaClientError("Client not initialized")
        tracker_url = f"{self.server_url}/conversations/{self.sender_id}/tracker"
        response = await self.client.get(tracker_url)
        response.raise_for_status()
        return response.json()

async def interactive_chat(client: RasaClient) -> None:
    # First reset the conversation state
    await client.reset_conversation()
    
    print("Bot: Hello! Available commands:")
    print("- Type your message normally to chat")
    print("- 'summary all' - View complete conversation summary")
    print("- 'summary rasa' - View Rasa conversation summary")
    print("- 'summary openai' - View OpenAI conversation summary")
    print("- 'reset' - Reset conversation")
    print("- 'quit' or 'exit' to end")
    print("-" * 50)

    while True:
        try:
            user_message = input("You: ").strip()
            if not user_message:
                continue

            if user_message.lower() in ("quit", "exit"):
                print("Bot: Goodbye!")
                return
            
            if user_message.lower() == "reset":
                await client.reset_conversation()
                print("Bot: Conversation has been reset.")
                continue

            if user_message.lower().startswith("summary"):
                parts = user_message.lower().split()
                system = parts[1] if len(parts) > 1 and parts[1] in ('rasa', 'openai') else None
                print(f"\n{'='*20} Conversation Summary {'='*20}")
                summary = await client.get_conversation_summary(system)
                print(f"{summary}\n{'='*60}\n")
                continue

            bot_messages = await client.send_message(user_message)
            for msg in bot_messages:
                if "text" in msg:
                    print(f"Bot: {msg['text']}")

        except (KeyboardInterrupt, EOFError):
            print("\nBot: Session terminated.")
            return
        except Exception as e:
            logger.error(f"Chat error: {e}")
            print("Bot: An error occurred. Please try again.")

async def main() -> None:
    client = None
    try:
        client = await RasaClient.create()
        
        try:
            status = await client.get_server_status()
            logger.info("Connected to Rasa server. Status: %s", status.get("status", "unknown"))
        except Exception as e:
            logger.error(f"Server connection failed: {e}")
            print("Error: Ensure Rasa server is running at http://localhost:5005")
            return

        # Start the interactive chat session
        await interactive_chat(client)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print("Critical failure. Check logs for details.")
    finally:
        # Ensure cleanup happens even if there's an error
        if client:
            await client.close()

if __name__ == "__main__":
    asyncio.run(main())
