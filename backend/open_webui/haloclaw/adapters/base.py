import abc
from typing import Optional


class BaseAdapter(abc.ABC):
    """Abstract base class for all messaging platform adapters."""

    def __init__(self, gateway_id: str, platform: str, config: dict):
        self.gateway_id = gateway_id
        self.platform = platform
        self.config = config
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @abc.abstractmethod
    async def start(self) -> None:
        """Start listening for messages. Called once during lifecycle startup."""
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the adapter. Called during lifecycle shutdown."""
        ...

    @abc.abstractmethod
    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        """Send a message to the platform. Returns the platform message ID."""
        ...

    @abc.abstractmethod
    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """Edit an existing message on the platform."""
        ...

    async def send_photo(
        self,
        chat_id: str,
        image_url: str,
        caption: str = "",
    ) -> Optional[str]:
        """Send a photo to the platform. Returns the platform message ID.

        Default no-op; subclasses override for platform-specific photo sending.
        """
        return None
