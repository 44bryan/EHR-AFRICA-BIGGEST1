"""
Ollama local LLM client for production on-premises deployment.
Drop-in replacement for groq_client — same return schema.
Calls the Ollama REST API at OLLAMA_BASE_URL (default: http://localhost:11434).
"""
import json
import time
import logging
import urllib.request
import urllib.error

from django.conf import settings

logger = logging.getLogger('apps.ai_assistant')


def _get_model(fast: bool = False) -> str:
    """Return the configured Ollama model name."""
    # fast mode uses the same model unless overridden — Ollama handles speed via quantization
    return getattr(settings, 'OLLAMA_MODEL', 'llama3.3:70b')


def _ollama_request(endpoint: str, payload: dict, timeout: int = 120) -> dict:
    """Low-level POST to Ollama REST API. Returns parsed JSON or raises."""
    base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def ollama_chat(messages: list, system: str = '', model: str = None,
                max_tokens: int = 2048, fast: bool = False) -> dict:
    """
    Send a chat completion request to local Ollama.

    Returns dict matching groq_client schema:
        {
            'success': bool,
            'text': str,
            'usage': {'prompt_tokens': int, 'completion_tokens': int},
            'model': str,
            'error': str | None,
        }
    """
    model = model or _get_model(fast=fast)
    payload = {
        'model': model,
        'messages': messages,
        'stream': False,
        'options': {
            'num_predict': max_tokens,
            'temperature': 0.3,
        },
    }
    if system:
        payload['system'] = system

    start = time.time()
    try:
        result = _ollama_request('/api/chat', payload, timeout=180)
        elapsed = int((time.time() - start) * 1000)
        text = result.get('message', {}).get('content', '')
        usage = result.get('usage', {})
        return {
            'success': True,
            'text': text,
            'usage': {
                'prompt_tokens': usage.get('prompt_eval_count', 0),
                'completion_tokens': usage.get('eval_count', 0),
            },
            'model': model,
            'elapsed_ms': elapsed,
            'error': None,
        }
    except urllib.error.URLError as e:
        logger.error('Ollama connection error (%s): %s', model, e)
        return {'success': False, 'text': '', 'usage': {}, 'model': model, 'error': str(e)}
    except Exception as e:
        logger.exception('Ollama unexpected error: %s', e)
        return {'success': False, 'text': '', 'usage': {}, 'model': model, 'error': str(e)}


def ollama_json(messages: list, system: str = '', model: str = None,
                max_tokens: int = 2048) -> dict:
    """
    Like ollama_chat but forces JSON output mode and parses the result.

    Returns dict matching groq_client schema:
        {
            'success': bool,
            'data': dict | None,   # parsed JSON
            'text': str,           # raw text
            'error': str | None,
        }
    """
    model = model or _get_model()
    payload = {
        'model': model,
        'messages': messages,
        'stream': False,
        'format': 'json',
        'options': {
            'num_predict': max_tokens,
            'temperature': 0.1,
        },
    }
    if system:
        payload['system'] = system

    try:
        result = _ollama_request('/api/chat', payload, timeout=180)
        text = result.get('message', {}).get('content', '')
        try:
            data = json.loads(text)
            return {'success': True, 'data': data, 'text': text, 'error': None}
        except json.JSONDecodeError as e:
            logger.warning('Ollama JSON parse error: %s | raw=%s', e, text[:200])
            return {'success': False, 'data': None, 'text': text, 'error': f'JSON parse error: {e}'}
    except Exception as e:
        logger.exception('Ollama JSON request error: %s', e)
        return {'success': False, 'data': None, 'text': '', 'error': str(e)}


def ollama_health_check() -> dict:
    """
    Check if Ollama is reachable and the configured model is available.
    Returns {'online': bool, 'model_available': bool, 'models': list, 'error': str|None}
    """
    base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
    target_model = getattr(settings, 'OLLAMA_MODEL', 'llama3.3:70b')
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        models = [m['name'] for m in data.get('models', [])]
        # Check if target model name is a prefix match (e.g. "llama3.3:70b" in "llama3.3:70b-instruct-q4_K_M")
        model_available = any(target_model in m for m in models)
        return {'online': True, 'model_available': model_available, 'models': models, 'error': None}
    except Exception as e:
        return {'online': False, 'model_available': False, 'models': [], 'error': str(e)}
