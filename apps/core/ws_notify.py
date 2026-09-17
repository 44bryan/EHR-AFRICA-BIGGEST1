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

    Also broadcasts to the 'tracker' room so the Patient Tracker Board
    receives instant updates whenever any queue changes.

    Runs in a daemon thread with a 2-second timeout so a slow/unavailable
    Redis never blocks the calling HTTP request.
    """
    import threading

    def _send():
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            layer = get_channel_layer()
            if layer is None:
                return
            group = f"ehr_queue_{room.replace('-', '_')}"
            async_to_sync(layer.group_send)(group, {
                'type': 'queue.update',
                'action': action,
                'data': data or {},
            })
            # Also notify the Patient Tracker board (if not already)
            if room != 'tracker':
                tracker_group = 'ehr_queue_tracker'
                async_to_sync(layer.group_send)(tracker_group, {
                    'type': 'queue.update',
                    'action': 'refresh',
                    'data': {},
                })
        except Exception:
            pass

    t = threading.Thread(target=_send, daemon=True)
    t.start()
    t.join(timeout=2.0)  # Never block the view for more than 2 seconds
