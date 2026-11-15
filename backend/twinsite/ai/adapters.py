"""Wire adapters: real HTTP calls, stdlib only. Credentials travel in headers only
(never URLs), and nothing raised from here contains a header, URL query or body."""
import base64
import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

USER_AGENT = 'TwinSite/1.0 (planetary-analog research; server-side)'


class ProviderError(Exception):
    """kind: rate_limited | auth | payment_required | not_found | bad_request | server | timeout | network | empty | policy"""

    def __init__(self, kind, message, status=None, retry_after=None):
        super().__init__(f'{kind}: {message}'[:300])
        self.kind, self.status, self.retry_after = kind, status, retry_after


@dataclass
class Completion:
    text: str
    model: str
    http_status: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    rate_headers: dict = field(default_factory=dict)


def _classify(status):
    return {400: 'bad_request', 401: 'auth', 403: 'auth', 402: 'payment_required', 404: 'not_found',
            408: 'timeout', 413: 'bad_request', 422: 'bad_request', 429: 'rate_limited'}.get(
        status, 'server' if status and status >= 500 else 'bad_request')


def _retry_after(headers):
    for key in ('retry-after', 'x-ratelimit-reset-requests', 'x-ratelimit-reset'):
        value = headers.get(key)
        if value:
            try:
                return float(str(value).rstrip('s'))
            except ValueError:
                return None
    return None


def post_json(url, headers, body, timeout):
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST',
                                 headers={**headers, 'Content-Type': 'application/json', 'User-Agent': USER_AGENT})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(4_000_000)
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, json.loads(raw.decode('utf-8')), hdrs, int((time.monotonic() - started) * 1000)
    except urllib.error.HTTPError as error:
        hdrs = {k.lower(): v for k, v in (error.headers or {}).items()}
        detail = ''
        try:
            payload = json.loads(error.read(20_000).decode('utf-8', 'replace'))
            err = payload.get('error') if isinstance(payload, dict) else None
            detail = (err.get('message') if isinstance(err, dict) else str(err or payload))[:160]
        except Exception:  # noqa: BLE001 - body is diagnostic only
            pass
        raise ProviderError(_classify(error.code), f'HTTP {error.code} {detail}', error.code, _retry_after(hdrs)) from None
    except (socket.timeout, TimeoutError):
        raise ProviderError('timeout', f'no response within {timeout}s') from None
    except urllib.error.URLError as error:
        raise ProviderError('network', type(error.reason).__name__) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProviderError('server', 'non-JSON response') from None
    except (ConnectionError, http.client.HTTPException, OSError) as error:
        raise ProviderError('network', type(error).__name__) from None


def get_json(url, headers, timeout=20):
    req = urllib.request.Request(url, headers={**headers, 'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read(8_000_000).decode('utf-8'))
    except urllib.error.HTTPError as error:
        raise ProviderError(_classify(error.code), f'HTTP {error.code}', error.code) from None
    except (socket.timeout, TimeoutError):
        raise ProviderError('timeout', 'no response') from None
    except urllib.error.URLError as error:
        raise ProviderError('network', type(error.reason).__name__) from None
    except (ConnectionError, http.client.HTTPException, OSError, ValueError) as error:
        raise ProviderError('network', type(error).__name__) from None


def _rate(hdrs):
    return {k: v for k, v in hdrs.items() if 'ratelimit' in k or k == 'retry-after'}


def openai_chat(endpoint, key, model, system, user, images=(), max_tokens=900, json_mode=True, timeout=60,
                reasoning_effort=None):
    content = user if not images else [{'type': 'text', 'text': user}] + [
        {'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (mime, base64.b64encode(data).decode())}}
        for mime, data in images]
    body = {'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}],
            'max_tokens': max_tokens, 'temperature': 0.2}
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    if reasoning_effort:
        body['reasoning_effort'] = reasoning_effort
    status, data, hdrs, ms = post_json(endpoint, {'Authorization': 'Bearer ' + key}, body, timeout)
    if isinstance(data, dict) and data.get('success') is False:
        raise ProviderError('server', 'provider reported success=false', status)
    try:
        message = data['choices'][0]['message']
        text = message.get('content') or ''
        if isinstance(text, list):
            text = ''.join(part.get('text', '') for part in text if isinstance(part, dict))
    except (KeyError, IndexError, TypeError):
        raise ProviderError('server', 'unexpected response shape', status) from None
    if not text.strip():
        raise ProviderError('empty', 'empty completion (reasoning may have consumed the output budget)', status)
    usage = data.get('usage') or {}
    return Completion(text, data.get('model') or model, status, usage.get('prompt_tokens'),
                      usage.get('completion_tokens'), ms, _rate(hdrs))


def google_generate(endpoint, key, model, system, user, images=(), max_tokens=900, json_mode=True, timeout=60,
                    reasoning_effort=None):
    parts = [{'text': user}] + [{'inline_data': {'mime_type': mime, 'data': base64.b64encode(data).decode()}}
                                for mime, data in images]
    config = {'maxOutputTokens': max_tokens, 'temperature': 0.2}
    if json_mode:
        config['responseMimeType'] = 'application/json'
    if 'gemini-3' in model:
        config['thinkingConfig'] = {'thinkingLevel': 'low'}
    body = {'systemInstruction': {'parts': [{'text': system}]}, 'contents': [{'role': 'user', 'parts': parts}],
            'generationConfig': config}
    status, data, hdrs, ms = post_json(endpoint.format(model=model), {'x-goog-api-key': key}, body, timeout)
    try:
        candidate = data['candidates'][0]
        text = ''.join(p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought'))
    except (KeyError, IndexError, TypeError):
        reason = (data.get('promptFeedback') or {}).get('blockReason') if isinstance(data, dict) else None
        raise ProviderError('policy' if reason else 'empty', f'no candidate text ({reason or "no content"})', status) from None
    if not text.strip():
        raise ProviderError('empty', 'empty completion', status)
    usage = data.get('usageMetadata') or {}
    return Completion(text, model, status, usage.get('promptTokenCount'), usage.get('candidatesTokenCount'), ms, _rate(hdrs))


def elevenlabs_tts(endpoint, key, model, text, voice='21m00Tcm4TlvDq8EAccM', timeout=60):
    """Speech synthesis. Registered for completeness; no TwinSite feature invokes it by default."""
    data = json.dumps({'text': text[:2500], 'model_id': model}).encode()
    req = urllib.request.Request(endpoint.format(voice=voice), data=data, method='POST',
                                 headers={'xi-api-key': key, 'Content-Type': 'application/json', 'Accept': 'audio/mpeg',
                                          'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(20_000_000)
    except urllib.error.HTTPError as error:
        raise ProviderError(_classify(error.code), f'HTTP {error.code}', error.code) from None


WIRES = {'openai_chat': openai_chat, 'google_generate': google_generate}
