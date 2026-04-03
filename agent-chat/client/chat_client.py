"""
Agent Chat client for Auxesis CEO and other Python-based agents.

Usage:
    from chat_client import AgentChat

    chat = AgentChat(
        api_url="https://chat.synthinsightlabs.com",
        api_key="...",
        sender="auxesis-ceo",
    )

    # Send a message
    chat.send("SIW sandbox-validation passed. Moving to launch-readiness.")

    # Read new messages since last check
    messages = chat.read()
    for msg in messages:
        print(f"{msg['sender']}: {msg['body']}")
"""

from urllib.error import URLError
from urllib.request import Request, urlopen
import json
from typing import Optional


class AgentChat:
    def __init__(self, api_url: str, api_key: str, sender: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.sender = sender
        self._last_ts: Optional[str] = None

    def send(self, body: str, priority: str = "normal",
             to: Optional[str] = None, reply_to: Optional[int] = None) -> Optional[dict]:
        try:
            msg = {
                "sender": self.sender,
                "body": body,
                "priority": priority,
            }
            if to:
                msg["to"] = to
            if reply_to:
                msg["reply_to"] = reply_to
            payload = json.dumps(msg).encode("utf-8")
            req = Request(
                f"{self.api_url}/send",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                },
                method="POST",
            )
            resp = urlopen(req, timeout=10)
            return json.loads(resp.read())
        except (URLError, OSError, TimeoutError) as e:
            import logging
            logging.getLogger(__name__).warning("Agent Chat send failed: %s", e)
            return None

    def read(self, limit: int = 20) -> list[dict]:
        try:
            params = f"?limit={limit}"
            if self._last_ts:
                params += f"&since={self._last_ts}"
            req = Request(
                f"{self.api_url}/messages{params}",
                headers={"X-API-Key": self.api_key},
            )
            resp = urlopen(req, timeout=10)
            data = json.loads(resp.read())
            messages = data.get("messages", [])
            if messages:
                self._last_ts = messages[-1]["ts"]
            return messages
        except (URLError, OSError, TimeoutError) as e:
            import logging
            logging.getLogger(__name__).warning("Agent Chat read failed: %s", e)
            return []
