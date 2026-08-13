from django.urls import re_path
from apps.core import consumers

websocket_urlpatterns = [
    # Generic queue room — room name determines which group the client joins.
    # Examples:
    #   /ws/queue/opd/            → OPD / triage board
    #   /ws/queue/cashier/        → Cashier workstation queue
    #   /ws/queue/lab/            → Laboratory queue
    #   /ws/queue/invest/         → Investigations queue
    #   /ws/queue/pharmacy/       → Pharmacy dispensing list
    #   /ws/queue/workstation/    → All doctor workstations (broadcast)
    #   /ws/queue/doctor-42/      → Individual doctor workstation (doctor pk=42)
    re_path(r'^ws/queue/(?P<room>[a-zA-Z0-9_-]+)/$', consumers.QueueConsumer.as_asgi()),
]
