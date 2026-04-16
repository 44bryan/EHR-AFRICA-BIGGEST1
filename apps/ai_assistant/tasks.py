"""
Celery tasks for AI assistant.

WHY THIS MATTERS:
The Anthropic Claude API call can take 3–10 seconds to respond.
If this runs synchronously in a Django view, the web worker is blocked
for that entire time — it can't serve ANY other request.

With 300 users, even 10 simultaneous AI requests would block 10 workers
completely. By offloading to Celery, the web worker hands off the job
immediately and is free to serve other requests while waiting for Claude.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=5, time_limit=60)
def process_ai_message(self, conversation_id, user_message, user_id):
    """
    Run Claude API call in background, save the response to the AIMessage model.
    The frontend polls for the response rather than waiting on the HTTP request.

    time_limit=60: if Claude takes more than 60s, the task is killed — prevents
    zombie workers piling up under load.
    """
    try:
        from apps.ai_assistant.models import AIConversation, AIMessage
        from apps.ai_assistant.claude_client import get_claude_response

        conversation = AIConversation.objects.get(pk=conversation_id)

        # Save user message
        AIMessage.objects.create(
            conversation=conversation,
            role='user',
            content=user_message,
        )

        # Get Claude response (this is the slow part — runs in background)
        response_text = get_claude_response(conversation, user_message)

        # Save assistant response
        AIMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=response_text,
        )

        return {'status': 'done', 'conversation_id': str(conversation_id)}

    except Exception as exc:
        logger.error(f'process_ai_message failed for conversation {conversation_id}: {exc}')
        raise self.retry(exc=exc)
