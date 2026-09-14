"""
WebSocket consumers for live queue updates.

Each queue page connects to /ws/queue/<room>/ and joins the corresponding
Redis channel group.  When a patient is routed (visit status changes), the
view layer calls ws_notify.notify_queue(room) which broadcasts a 'refresh'
event to every connected client in that room — browsers then call their
existing doRefresh() handler for an instant, zero-polling update.

NOTE: Authentication is NOT enforced here because this channel only sends
opaque "refresh" signals — no PHI or sensitive data.  The browser's fetch()
call that follows IS authenticated via normal Django session/cookie auth.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer


class QueueConsumer(AsyncWebsocketConsumer):
    """
    Generic queue room consumer.  One class handles every queue type;
    the room name from the URL determines which Redis group to join.
    """

    def _make_group(self, room: str) -> str:
        """Sanitise the room name into a valid channel group name."""
        return f"ehr_queue_{room.replace('-', '_')}"

    async def connect(self):
        self.room = self.scope['url_route']['kwargs']['room']
        self.group_name = self._make_group(self.room)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # ── Receive message from browser (not used — server-push only) ──────────
    async def receive(self, text_data=None, bytes_data=None):
        pass  # clients don't send messages; they only listen

    # ── Handle group_send from server ────────────────────────────────────────
    async def queue_update(self, event):
        """Forward a queue_update event to the WebSocket client."""
        await self.send(text_data=json.dumps({
            'action': event.get('action', 'refresh'),
            'room':   self.room,
            'data':   event.get('data', {}),
        }))
