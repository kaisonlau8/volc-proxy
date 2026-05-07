"""Volc Proxy — Anthropic-compatible local proxy for Volcano Engine API."""

import json
import logging
import time
from collections import deque

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from contextlib import asynccontextmanager

from config import ARK_API_KEY, ARK_BASE_URL, LOCAL_PORT, MODEL_MAP, THINKING_MODE, THINKING_INFO, EXTRA_MODELS
from converter import (
    anthropic_models_list,
    anthropic_to_openai,
    openai_to_anthropic,
    stream_delta_event,
    stream_end_events,
    stream_start_events,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("volc-proxy")

# ── Dashboard HTML ──────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Volc Proxy Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #0f172a; color: #e2e8f0; min-height: 100vh; }
.header { background: #1e293b; padding: 20px 32px; border-bottom: 1px solid #334155;
          display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 20px; color: #f8fafc; }
.header .tag { background: #22c55e; color: #0f172a; padding: 2px 10px; border-radius: 12px;
               font-size: 12px; font-weight: 600; }
.container { max-width: 1200px; margin: 24px auto; padding: 0 24px; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
.stat-card .label { font-size: 13px; color: #94a3b8; margin-bottom: 8px; }
.stat-card .value { font-size: 28px; color: #f8fafc; font-weight: 700; }
.stat-card .value.green { color: #22c55e; }
.stat-card .value.yellow { color: #eab308; }
.stat-card .value.blue { color: #3b82f6; }
.model-section { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155;
                margin-bottom: 24px; }
.model-section h2 { font-size: 16px; margin-bottom: 16px; color: #f8fafc; }
.model-row { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
.model-row .local { background: #3b82f6; color: #fff; padding: 4px 12px; border-radius: 8px;
                    font-size: 14px; font-weight: 600; }
.model-row .arrow { color: #94a3b8; }
.model-row .real { background: #334155; color: #f8fafc; padding: 4px 12px; border-radius: 8px;
                   font-size: 14px; }
.model-row select { background: #334155; color: #f8fafc; border: 1px solid #475569;
                    padding: 6px 12px; border-radius: 8px; font-size: 14px; min-width: 240px; }
.model-row button { background: #3b82f6; color: #fff; border: none; padding: 6px 16px;
                    border-radius: 8px; font-size: 14px; cursor: pointer; }
.model-row button:hover { background: #2563eb; }
.model-desc { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.model-thinking { font-size: 11px; color: #64748b; }

/* Thinking toggle */
.thinking-section { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155;
                    margin-bottom: 24px; }
.thinking-section h2 { font-size: 16px; margin-bottom: 16px; color: #f8fafc; }
.thinking-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.thinking-btn { background: #334155; color: #94a3b8; border: 1px solid #475569; padding: 6px 16px;
                border-radius: 8px; font-size: 14px; cursor: pointer; }
.thinking-btn:hover { color: #f8fafc; }
.thinking-btn.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.history-section { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
.history-section h2 { font-size: 16px; margin-bottom: 16px; color: #f8fafc;
                     display: flex; justify-content: space-between; }
.history-section .count { color: #94a3b8; font-size: 13px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 12px; color: #94a3b8; padding: 10px 12px;
     border-bottom: 1px solid #334155; }
td { font-size: 13px; padding: 10px 12px; border-bottom: 1px solid #1e293b; }
tr:hover td { background: #0f172a; }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }
.badge.ok { background: #22c55e20; color: #22c55e; }
.badge.err { background: #ef444420; color: #ef4444; }
.badge.stream { background: #3b82f620; color: #3b82f6; }
.badge.sync { background: #eab30820; color: #eab308; }
.empty { text-align: center; color: #64748b; padding: 40px; }
.refresh-btn { background: #334155; color: #94a3b8; border: none; padding: 4px 12px;
               border-radius: 6px; font-size: 12px; cursor: pointer; }
.refresh-btn:hover { color: #f8fafc; }
.auto-tag { color: #22c55e; font-size: 11px; }
tr.clickable { cursor: pointer; }
tr.clickable:hover td { background: #1e293b; }

/* Modal */
.modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                 background: rgba(0,0,0,0.6); z-index: 1000; justify-content: center; align-items: center; }
.modal-overlay.active { display: flex; }
.modal-box { background: #1e293b; border: 1px solid #475569; border-radius: 16px;
             max-width: 800px; width: 90%; max-height: 85vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center;
                padding: 16px 24px; border-bottom: 1px solid #334155; }
.modal-header h3 { font-size: 15px; color: #f8fafc; }
.modal-close { background: none; border: none; color: #94a3b8; font-size: 24px; cursor: pointer;
               line-height: 1; }
.modal-close:hover { color: #f8fafc; }
.modal-body { padding: 24px; }
.modal-section { margin-bottom: 20px; }
.modal-section .section-label { font-size: 12px; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.modal-section .section-content { background: #0f172a; border-radius: 8px; padding: 16px;
                                  font-size: 14px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
                                  border: 1px solid #334155; max-height: 300px; overflow-y: auto; }
.modal-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.modal-meta-item { background: #0f172a; border-radius: 8px; padding: 12px; border: 1px solid #334155; }
.modal-meta-item .meta-label { font-size: 11px; color: #94a3b8; }
.modal-meta-item .meta-value { font-size: 14px; color: #f8fafc; margin-top: 4px; }
</style>
</head>
<body>
<div class="header">
  <h1>Volc Proxy Dashboard</h1>
  <span class="tag">RUNNING</span>
</div>
<div class="container">
  <div class="stats">
    <div class="stat-card"><div class="label">Total Requests</div><div class="value green" id="s-total">0</div></div>
    <div class="stat-card"><div class="label">Errors</div><div class="value yellow" id="s-errors">0</div></div>
    <div class="stat-card"><div class="label">Input Tokens</div><div class="value blue" id="s-in">0</div></div>
    <div class="stat-card"><div class="label">Output Tokens</div><div class="value blue" id="s-out">0</div></div>
  </div>

  <div class="model-section">
    <h2>Model Mapping</h2>
    <div id="model-map"></div>
    <div class="model-row" style="margin-top:16px">
      <span class="local">opus-4.7</span>
      <span class="arrow">&rarr;</span>
      <select id="model-select"></select>
      <button onclick="switchModel()">Switch</button>
    </div>
    <div id="model-desc" class="model-desc"></div>
    <div id="model-thinking" class="model-thinking"></div>
  </div>

  <div class="thinking-section">
    <h2>Thinking Mode</h2>
    <div class="thinking-row">
      <button class="thinking-btn" id="tk-auto" onclick="setThinking('auto')">Auto (follow model default)</button>
      <button class="thinking-btn" id="tk-enabled" onclick="setThinking('enabled')">Enabled (force thinking)</button>
      <button class="thinking-btn" id="tk-disabled" onclick="setThinking('disabled')">Disabled (force non-thinking)</button>
    </div>
    <div id="tk-status" class="model-desc" style="margin-top:8px"></div>
  </div>

  <div class="history-section">
    <h2>Request History <span class="count" id="h-count">0 records</span>
      <button class="refresh-btn" onclick="loadStats()">Refresh <span class="auto-tag">auto 5s</span></button>
    </h2>
    <table>
      <thead><tr>
        <th>Time</th><th>Local</th><th>Real</th><th>Mode</th><th>Status</th>
        <th>In Tokens</th><th>Out Tokens</th><th>Input</th><th>Output</th>
      </tr></thead>
      <tbody id="history-body"></tbody>
    </table>
  </div>
</div>

<!-- Modal -->
<div class="modal-overlay" id="modal-overlay" onclick="closeModal(event)">
  <div class="modal-box">
    <div class="modal-header">
      <h3 id="modal-title">Request Detail</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body">
      <div class="modal-meta" id="modal-meta"></div>
      <div class="modal-section">
        <div class="section-label">Input</div>
        <div class="section-content" id="modal-input"></div>
      </div>
      <div class="modal-section">
        <div class="section-label">Output</div>
        <div class="section-content" id="modal-output"></div>
      </div>
    </div>
  </div>
</div>

<script>
const API = '/_dashboard/api/stats';
const MODEL_API = '/_admin/set_model';
const MODELS_API = '/_admin/models_map';

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
}

async function loadStats() {
  try {
    const r = await fetch(API);
    const d = await r.json();
    document.getElementById('s-total').textContent = d.total_requests;
    document.getElementById('s-errors').textContent = d.total_errors;
    document.getElementById('s-in').textContent = d.total_input_tokens.toLocaleString();
    document.getElementById('s-out').textContent = d.total_output_tokens.toLocaleString();
    document.getElementById('h-count').textContent = d.history.length + ' records';

    updateThinkingUI(d.thinking_mode);
    window._historyData = d.history;
    window._modelsData = d.available_models;
    window._thinkingMode = d.thinking_mode;

    let mapHtml = '';
    for (const [k,v] of Object.entries(d.model_map)) {
      mapHtml += '<div class="model-row"><span class="local">'+k+'</span><span class="arrow">&rarr;</span><span class="real">'+v+'</span></div>';
    }
    document.getElementById('model-map').innerHTML = mapHtml;

    const tbody = document.getElementById('history-body');
    if (d.history.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">No requests yet</td></tr>';
      return;
    }
    const rows = d.history.slice().reverse();
    tbody.innerHTML = rows.map((r, i) => {
      const modeBadge = r.stream
        ? '<span class="badge stream">stream</span>'
        : '<span class="badge sync">sync</span>';
      const statusBadge = r.status === 200
        ? '<span class="badge ok">200</span>'
        : '<span class="badge err">'+r.status+'</span>';
      const idx = d.history.length - 1 - i;
      return '<tr class="clickable" onclick="showDetail('+idx+')"><td>'+fmtTime(r.time)+'</td><td>'+r.local_model+'</td><td>'+r.real_model+'</td>'
        +'<td>'+modeBadge+'</td><td>'+statusBadge+'</td>'
        +'<td>'+r.in_tokens+'</td><td>'+r.out_tokens+'</td>'
        +'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(r.input_preview)+'</td>'
        +'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(r.output_preview)+'</td></tr>';
    }).join('');
  } catch(e) { console.error(e); }
}

function esc(s) { return s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;') : ''; }

function showDetail(idx) {
  const overlay = document.getElementById('modal-overlay');
  const r = window._historyData[idx];
  if (!r) return;
  document.getElementById('modal-title').textContent = fmtTime(r.time) + ' ' + r.real_model;
  document.getElementById('modal-meta').innerHTML =
    '<div class="modal-meta-item"><div class="meta-label">Local Model</div><div class="meta-value">'+esc(r.local_model)+'</div></div>'
    +'<div class="modal-meta-item"><div class="meta-label">Mode</div><div class="meta-value">'+(r.stream?'stream':'sync')+'</div></div>'
    +'<div class="modal-meta-item"><div class="meta-label">Status</div><div class="meta-value">'+r.status+'</div></div>'
    +'<div class="modal-meta-item"><div class="meta-label">In Tokens</div><div class="meta-value">'+r.in_tokens+'</div></div>'
    +'<div class="modal-meta-item"><div class="meta-label">Out Tokens</div><div class="meta-value">'+r.out_tokens+'</div></div>'
    +'<div class="modal-meta-item"><div class="meta-label">Messages</div><div class="meta-value">'+r.msg_count+'</div></div>';
  document.getElementById('modal-input').textContent = r.input || '(empty)';
  document.getElementById('modal-output').textContent = r.output || '(empty)';
  overlay.classList.add('active');
}

function closeModal(e) {
  if (e && e.target !== document.getElementById('modal-overlay')) return;
  document.getElementById('modal-overlay').classList.remove('active');
}

async function loadModels() {
  try {
    const r = await fetch(MODELS_API);
    const d = await r.json();
    const sel = document.getElementById('model-select');
    sel.innerHTML = '';
    const llm = d.available_models;
    sel.innerHTML = '';
    llm.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      const tkLabel = m.default_thinking === true ? 'thinking' : (m.default_thinking === false ? 'non-thinking' : 'unknown');
      opt.textContent = m.name + ' (' + m.id + ') — ' + tkLabel;
      sel.appendChild(opt);
    });
    const current = d.model_map['opus-4.7'] || '';
    sel.value = current;
    updateModelDesc(d.available_models, current);
  } catch(e) { console.error(e); }
}

function updateModelDesc(models, currentId) {
  const m = models.find(m => m.id === currentId);
  if (m) {
    document.getElementById('model-desc').textContent = m.desc;
    document.getElementById('model-thinking').textContent = m.default_thinking === true ? 'Default: thinking' : (m.default_thinking === false ? 'Default: non-thinking' : 'Default: unknown');
  } else {
    document.getElementById('model-desc').textContent = '';
    document.getElementById('model-thinking').textContent = '';
  }
}

function updateThinkingUI(mode) {
  document.getElementById('tk-auto').classList.toggle('active', mode === 'auto');
  document.getElementById('tk-enabled').classList.toggle('active', mode === 'enabled');
  document.getElementById('tk-disabled').classList.toggle('active', mode === 'disabled');
  const labels = {auto: 'Following model default', enabled: 'Thinking forced ON', disabled: 'Thinking forced OFF'};
  document.getElementById('tk-status').textContent = labels[mode] || mode;
}

async function setThinking(mode) {
  await fetch('/_admin/set_thinking', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({mode: mode}),
  });
  loadStats();
}

document.getElementById('model-select').addEventListener('change', function() {
  const models = window._modelsData || [];
  updateModelDesc(models, this.value);
});

async function switchModel() {
  const sel = document.getElementById('model-select');
  const real = sel.value;
  if (!real) return;
  await fetch(MODEL_API, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({local_model: 'opus-4.7', real_model: real}),
  });
  loadStats();
}

loadStats();
loadModels();
setInterval(loadStats, 5000);
</script>
</body>
</html>"""

# ── Request history ─────────────────────────────────────────────────

MAX_HISTORY = 200
request_history: deque = deque(maxlen=MAX_HISTORY)
total_requests = 0
total_errors = 0
total_input_tokens = 0
total_output_tokens = 0
start_time = time.time()


def _add_record(record: dict):
    global total_requests
    total_requests += 1
    request_history.append(record)


def _add_error():
    global total_errors
    total_errors += 1


def _add_tokens(in_t: int, out_t: int):
    global total_input_tokens, total_output_tokens
    total_input_tokens += in_t
    total_output_tokens += out_t


# ── App setup ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()


app = FastAPI(title="Volc Proxy", description="Anthropic-compatible proxy for Volcano Engine", lifespan=lifespan)

client = httpx.AsyncClient(
    base_url=ARK_BASE_URL,
    headers={"Authorization": f"Bearer {ARK_API_KEY}"},
    timeout=httpx.Timeout(300.0, connect=30.0),
)


# ── Health check ────────────────────────────────────────────────────

@app.get("/")
@app.head("/")
async def health():
    return {"status": "ok", "model_map": MODEL_MAP.copy()}


# ── Dashboard ───────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/_dashboard/api/stats")
async def dashboard_stats():
    uptime = int(time.time() - start_time)
    return {
        "uptime": uptime,
        "total_requests": total_requests,
        "total_errors": total_errors,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "model_map": MODEL_MAP.copy(),
        "thinking_mode": THINKING_MODE,
        "history": list(request_history),
    }


# ── Anthropic-compatible endpoints ──────────────────────────────────

@app.get("/v1/models")
async def list_models():
    return anthropic_models_list()


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    body = await request.json()
    total_chars = 0
    for msg in body.get("messages", []):
        c = msg.get("content", "")
        if isinstance(c, str):
            total_chars += len(c)
        elif isinstance(c, list):
            for block in c:
                if block.get("type") == "text":
                    total_chars += len(block.get("text", ""))
    return {"input_tokens": max(1, total_chars // 4)}


@app.post("/v1/messages")
async def create_message(request: Request):
    body = await request.json()
    request_model = body.get("model", "opus-4.7")
    stream = body.get("stream", False)

    real_model = MODEL_MAP.get(request_model, request_model) or request_model
    msg_count = len(body.get("messages", []))
    first_user = ""
    for msg in body.get("messages", []):
        if msg["role"] == "user":
            c = msg["content"]
            if isinstance(c, str):
                first_user = c[:80]
            elif isinstance(c, list):
                texts = [b["text"] for b in c if b.get("type") == "text"]
                first_user = " ".join(texts)[:80]
            break

    logger.info(">> local=%s real=%s msgs=%d stream=%s | %s",
                request_model, real_model, msg_count, stream, first_user)

    openai_body = anthropic_to_openai(body)

    if stream:
        return StreamingResponse(
            _stream_response(openai_body, request_model, real_model, first_user),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # Non-streaming
    resp = await client.post("/v1/chat/completions", json=openai_body)
    ts = time.time()
    if resp.status_code != 200:
        _add_error()
        _add_record({
            "time": ts, "local_model": request_model, "real_model": real_model,
            "stream": False, "msg_count": msg_count,
            "input": first_user, "input_preview": first_user[:60],
            "output": resp.text[:500], "output_preview": resp.text[:60],
            "status": resp.status_code, "in_tokens": 0, "out_tokens": 0,
        })
        logger.error("<< Volcano error %d: %s", resp.status_code, resp.text[:300])
        return _error_response(resp.status_code, resp.text)

    result = openai_to_anthropic(resp.json(), request_model)
    reply_text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            reply_text = block["text"]
    out_tokens = result.get("usage", {}).get("output_tokens", 0)
    in_tokens = result.get("usage", {}).get("input_tokens", 0)
    _add_tokens(in_tokens, out_tokens)
    _add_record({
        "time": ts, "local_model": request_model, "real_model": real_model,
        "stream": False, "msg_count": msg_count,
        "input": first_user, "input_preview": first_user[:60],
        "output": reply_text, "output_preview": reply_text[:60],
        "status": 200, "in_tokens": in_tokens, "out_tokens": out_tokens,
    })
    logger.info("<< 200 out_tokens=%d | %s", out_tokens, reply_text[:80])
    return result


async def _stream_response(openai_body: dict, request_model: str, real_model: str, first_user: str):
    """Stream OpenAI SSE → Anthropic SSE conversion."""
    yield stream_start_events(request_model)

    output_tokens = 0
    full_text = ""
    ts = time.time()

    async with client.stream("POST", "/v1/chat/completions", json=openai_body) as resp:
        if resp.status_code != 200:
            error_text = await resp.aread()
            _add_error()
            _add_record({
                "time": ts, "local_model": request_model, "real_model": real_model,
                "stream": True, "msg_count": 0,
                "input": first_user, "input_preview": first_user[:60],
                "output": f"Error {resp.status_code}: {error_text.decode()[:500]}",
                "output_preview": f"Error {resp.status_code}",
                "status": resp.status_code, "in_tokens": 0, "out_tokens": 0,
            })
            logger.error("<< Volcano stream error %d: %s", resp.status_code, error_text[:300])
            yield stream_delta_event(f"[Error: Volcano API returned {resp.status_code}]")
            yield stream_end_events("end_turn", output_tokens)
            return

        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue

            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            text = delta.get("content", "")
            if text:
                output_tokens += 1
                full_text += text
                yield stream_delta_event(text)

    _add_tokens(0, output_tokens)
    _add_record({
        "time": ts, "local_model": request_model, "real_model": real_model,
        "stream": True, "msg_count": 0,
        "input": first_user, "input_preview": first_user[:60],
        "output": full_text, "output_preview": full_text[:60],
        "status": 200, "in_tokens": 0, "out_tokens": output_tokens,
    })
    logger.info("<< stream done out_tokens=%d | %s", output_tokens, full_text[:80])
    yield stream_end_events("end_turn", output_tokens)


def _error_response(status_code: int, text: str) -> dict:
    return {
        "type": "error",
        "error": {
            "type": "api_error",
            "message": f"Volcano Engine API error ({status_code}): {text[:300]}",
        },
    }


# ── Runtime model switch endpoint ──────────────────────────────────

@app.post("/_admin/set_model")
async def set_model(request: Request):
    body = await request.json()
    local = body.get("local_model", "opus-4.7")
    real = body.get("real_model")
    if not real:
        return {"error": "real_model is required"}
    MODEL_MAP[local] = real
    logger.info("Model mapping updated: %s -> %s", local, real)
    return {"local_model": local, "real_model": real, "current_map": MODEL_MAP.copy()}


@app.post("/_admin/set_thinking")
async def set_thinking(request: Request):
    """Switch thinking mode globally: auto / enabled / disabled."""
    import config
    body = await request.json()
    mode = body.get("mode", "auto")
    if mode not in ("auto", "enabled", "disabled"):
        return {"error": "mode must be auto, enabled, or disabled"}
    config.THINKING_MODE = mode
    global THINKING_MODE
    THINKING_MODE = mode
    logger.info("Thinking mode updated: %s", mode)
    return {"thinking_mode": mode}


@app.get("/_admin/models_map")
async def get_models_map():
    """Fetch available models from Volcano Engine API + extra models, filter to chat-capable ones."""
    resp = await client.get("/v1/models")
    models = []
    seen_ids = set()
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        for m in data:
            status = m.get("status", "")
            if status in ("Shutdown", "Retiring"):
                continue
            domain = m.get("domain", "")
            out_mods = m.get("modalities", {}).get("output_modalities", [])
            if domain not in ("LLM", "VLM", "Router") and "text" not in out_mods:
                continue
            mid = m["id"]
            seen_ids.add(mid)
            models.append({
                "id": mid,
                "name": m.get("name", mid),
                "domain": domain,
                "default_thinking": THINKING_INFO.get(mid),
            })
    # Add extra models not listed by API but actually usable
    for em in EXTRA_MODELS:
        if em["id"] not in seen_ids:
            models.append({
                "id": em["id"],
                "name": em["name"],
                "domain": em.get("domain", "LLM"),
                "default_thinking": THINKING_INFO.get(em["id"]),
            })
    return {"model_map": MODEL_MAP.copy(), "available_models": models}


if __name__ == "__main__":
    logger.info("Starting Volc Proxy on port %d, model map: %s", LOCAL_PORT, MODEL_MAP)
    uvicorn.run(app, host="0.0.0.0", port=LOCAL_PORT, log_level="info")