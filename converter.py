"""Anthropic protocol ↔ OpenAI-compatible protocol converter."""

import time
import uuid
from typing import Any

from config import MODEL_MAP, THINKING_MODE


def anthropic_to_openai(body: dict) -> dict:
    """Convert Anthropic /v1/messages request to OpenAI /v1/chat/completions format."""
    model = MODEL_MAP.get(body.get("model", ""), body.get("model", ""))

    messages: list[dict] = []

    # Anthropic has `system` as a top-level field
    if "system" in body:
        system = body["system"]
        if isinstance(system, str):
            messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text_parts = []
            for block in system:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block["text"])
            if text_parts:
                messages.append({"role": "system", "content": "\n".join(text_parts)})

    # Convert messages
    for msg in body.get("messages", []):
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Anthropic content blocks → OpenAI content parts
            parts: list[dict] = []
            for block in content:
                if block.get("type") == "text":
                    parts.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "image":
                    src = block.get("source", {})
                    if src.get("type") == "base64":
                        media_type = src.get("media_type", "image/png")
                        data_url = f"data:{media_type};base64,{src['data']}"
                        parts.append({"type": "image_url", "image_url": {"url": data_url}})
                    elif src.get("type") == "url":
                        parts.append({"type": "image_url", "image_url": {"url": src["url"]}})
            messages.append({"role": role, "content": parts})

    result: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }

    if "max_tokens" in body:
        result["max_tokens"] = body["max_tokens"]
    if "stop_sequences" in body:
        result["stop"] = body["stop_sequences"]
    if "temperature" in body:
        result["temperature"] = body["temperature"]
    if "top_p" in body:
        result["top_p"] = body["top_p"]

    # stream is passed through
    if "stream" in body:
        result["stream"] = body["stream"]

    # Thinking mode
    result["thinking"] = _resolve_thinking(result["model"], body.get("thinking"))

    return result


def openai_to_anthropic(resp: dict, request_model: str) -> dict:
    """Convert OpenAI /v1/chat/completions response to Anthropic /v1/messages format."""
    choice = resp.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content_str = msg.get("content", "")
    stop_reason = _map_stop_reason(choice.get("finish_reason", ""))

    content: list[dict] = []
    if content_str:
        content.append({"type": "text", "text": content_str})

    usage = resp.get("usage", {})
    return {
        "id": resp.get("id", f"msg_{uuid.uuid4().hex[:24]}"),
        "type": "message",
        "role": "assistant",
        "model": request_model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def _map_stop_reason(finish_reason: str) -> str:
    mapping = {
        "stop": "end_turn",
        "length": "max_tokens",
        "end_turn": "end_turn",
        "max_tokens": "max_tokens",
    }
    return mapping.get(finish_reason, "end_turn")


def _resolve_thinking(real_model: str, anthropic_thinking: dict | None) -> dict | None:
    """Resolve thinking config for Volcano Engine API."""
    import config as _cfg

    if anthropic_thinking is not None:
        if anthropic_thinking.get("type") == "enabled":
            return {"type": "enabled"}
        else:
            return {"type": "disabled"}

    mode = _cfg.THINKING_MODE
    if mode == "enabled":
        return {"type": "enabled"}
    elif mode == "disabled":
        return {"type": "disabled"}

    return None


# ── Streaming helpers ──────────────────────────────────────────────

def _make_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {_json_dumps(data)}\n\n"


def _json_dumps(obj: dict) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def stream_start_events(request_model: str, input_tokens: int = 0) -> str:
    """Generate the initial Anthropic streaming events (message_start, content_block_start)."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    events = []

    # message_start
    events.append(_make_event("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": request_model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": 0,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        },
    }))

    # content_block_start — text block index 0
    events.append(_make_event("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    }))

    # ping
    events.append("event: ping\ndata: {}\n\n")

    return "".join(events)


def stream_delta_event(text: str, index: int = 0) -> str:
    """Generate a content_block_delta event for a text chunk."""
    return _make_event("content_block_delta", {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "text_delta", "text": text},
    })


def stream_end_events(stop_reason: str = "end_turn", output_tokens: int = 0) -> str:
    """Generate the final Anthropic streaming events (content_block_stop, message_delta, message_stop)."""
    events = []

    # content_block_stop
    events.append(_make_event("content_block_stop", {
        "type": "content_block_stop",
        "index": 0,
    }))

    # message_delta
    events.append(_make_event("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": output_tokens},
    }))

    # message_stop
    events.append(_make_event("message_stop", {"type": "message_stop"}))

    return "".join(events)


def anthropic_models_list() -> dict:
    """Return Anthropic-style /v1/models response, only showing mapped local model names."""
    models = []
    for local_name in MODEL_MAP:
        models.append({
            "id": local_name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "volc-proxy",
        })
    return {
        "object": "list",
        "data": models,
    }