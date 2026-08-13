"""
Thin helper for pushing WebSocket notifications from synchronous Django views.

Usage:
    from apps.core.ws_notify import notify_queue
    notify_queue('opd')              # broadcast refresh to OPD queue page
    notify_queue('cashier')          # broadcast refresh to cashier queue page
    notify_queue(f'doctor-{pk}')     # broadcast refresh to a specific doctor
    notify_queue('workstation')      # broadcast to ALL doctor workstations

This NEVER raises — if channels/redis is unavailable the call is silently
swallowed so the HTTP request still completes normally.
"""


def notify_queue(room: str, action: str = 'refresh', data: dict | None = None) -> None:
    """
    Broadcast a queue_update event to every WebSocket client connected to
    the given room.  Safe to call from any synchronous view or signal.
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        layer = get_channel_layer()
        if layer is None:
            return

        group = f"ehr_queue_{room.replace('-', '_')}"
        async_to_sync(layer.group_send)(group, {
            'type': 'queue.update',   # maps to QueueConsumer.queue_update()
            'action': action,
            'data': data or {},
        })
    except Exception:
        pass  # never crash an HTTP request because of a WS notification failure
