"""
Agent Chat API server.

Flask app for Cloud Run. Group chat for Erik, Claude Architect,
Mini Claude, and Auxesis CEO.

Endpoints:
    POST /send      - send a message
    GET  /messages   - read messages (with ?since= cursor)
    GET  /health     - health check
    GET  /           - web UI
"""

import json
import os
from datetime import datetime

from flask import Flask, jsonify, request, Response

try:
    from . import db
except ImportError:
    import db


app = Flask(__name__)
API_KEY = os.environ.get("AGENT_CHAT_API_KEY")


def _check_auth():
    if not API_KEY:
        return None
    # Header auth for API clients; query param for browser web UI only
    provided = request.headers.get("X-API-Key") or request.args.get("key")
    if provided != API_KEY:
        return jsonify({"error": "unauthorized"}), 401
    return None


@app.before_request
def before_request():
    if request.path == "/health":
        return None
    auth_error = _check_auth()
    if auth_error:
        return auth_error


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "ts": datetime.now().isoformat()})


@app.route("/send", methods=["POST"])
def send_message():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    sender = data.get("sender")
    body = data.get("body")
    if not sender or not body:
        return jsonify({"error": "sender and body are required"}), 400

    recipient = data.get("to") or data.get("recipient")
    reply_to = data.get("reply_to")
    if reply_to is not None:
        try:
            reply_to = int(reply_to)
        except (ValueError, TypeError):
            reply_to = None

    with db.get_connection() as conn:
        # If replying, auto-set recipient to the original sender
        if reply_to and not recipient:
            orig = conn.execute("SELECT sender FROM messages WHERE id = ?", (reply_to,)).fetchone() if db._is_sqlite(conn) else None
            if orig:
                recipient = orig["sender"]

        row = db.insert_message(
            conn,
            sender=sender,
            body=body,
            recipient=recipient,
            reply_to=reply_to,
            priority=data.get("priority", "normal"),
            metadata=json.dumps(data.get("metadata", {})),
        )

    for k, v in row.items():
        if hasattr(v, "isoformat"):
            row[k] = v.isoformat()

    return jsonify(row), 201


@app.route("/messages", methods=["GET"])
def get_messages():
    with db.get_connection() as conn:
        rows = db.query_messages(
            conn,
            since=request.args.get("since"),
            sender=request.args.get("sender"),
            for_recipient=request.args.get("for"),
            limit=request.args.get("limit", 50, type=int),
        )

    for row in rows:
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()

    return jsonify({"messages": rows})


@app.route("/", methods=["GET"])
def web_ui():
    return Response(HTML_PAGE, content_type="text/html")


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Chat</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee; height: 100vh; display: flex; flex-direction: column; }
  #header { padding: 12px 20px; background: #16213e; border-bottom: 1px solid #0f3460; display: flex; align-items: center; gap: 12px; }
  #header h1 { font-size: 16px; font-weight: 600; color: #e94560; }
  #header .participants { font-size: 12px; color: #888; }
  #messages { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; }
  .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.5; word-wrap: break-word; position: relative; }
  .msg .sender { font-size: 11px; font-weight: 700; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  .msg .meta-line { font-size: 10px; color: #666; margin-top: 4px; display: flex; gap: 10px; align-items: center; }
  .msg .recipient-badge { font-size: 10px; background: rgba(255,255,255,0.1); padding: 1px 6px; border-radius: 4px; color: #aaa; margin-left: 6px; }
  .msg .reply-badge { font-size: 10px; color: #888; font-style: italic; margin-bottom: 4px; }
  .msg .reply-btn { font-size: 10px; color: #666; cursor: pointer; background: none; border: none; padding: 0; }
  .msg .reply-btn:hover { color: #e94560; }
  .msg.erik { background: #0f3460; align-self: flex-end; border-bottom-right-radius: 4px; }
  .msg.erik .sender { color: #e94560; }
  .msg.claude-architect { background: #1a3a5c; align-self: flex-start; border-bottom-left-radius: 4px; }
  .msg.claude-architect .sender { color: #53d8fb; }
  .msg.mini-claude { background: #2a1a3e; align-self: flex-start; border-bottom-left-radius: 4px; }
  .msg.mini-claude .sender { color: #b388ff; }
  .msg.auxesis-ceo { background: #1a3e2a; align-self: flex-start; border-bottom-left-radius: 4px; }
  .msg.auxesis-ceo .sender { color: #69f0ae; }
  .msg.dm { border: 1px solid rgba(233,69,96,0.3); }
  #input-bar { padding: 12px 20px; background: #16213e; border-top: 1px solid #0f3460; }
  #reply-indicator { display: none; padding: 6px 14px; font-size: 12px; color: #888; background: #1a1a2e; border-radius: 6px 6px 0 0; margin-bottom: -1px; }
  #reply-indicator .close-reply { cursor: pointer; margin-left: 8px; color: #e94560; }
  #input-row { display: flex; gap: 10px; }
  #to-field { width: 140px; background: #1a1a2e; color: #eee; border: 1px solid #0f3460; border-radius: 8px; padding: 10px 10px; font-size: 13px; font-family: inherit; }
  #to-field:focus { outline: none; border-color: #e94560; }
  #input-bar textarea { flex: 1; background: #1a1a2e; color: #eee; border: 1px solid #0f3460; border-radius: 8px; padding: 10px 14px; font-size: 14px; font-family: inherit; resize: none; min-height: 42px; max-height: 120px; }
  #input-bar textarea:focus { outline: none; border-color: #e94560; }
  #input-bar button { background: #e94560; color: white; border: none; border-radius: 8px; padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap; }
  #input-bar button:hover { background: #c73e54; }
  #input-bar button:disabled { background: #555; cursor: not-allowed; }
  .priority-urgent { border-left: 3px solid #ff1744; }
  .priority-high { border-left: 3px solid #ff9100; }
</style>
</head>
<body>
<div id="header">
  <h1>Agent Chat</h1>
  <span class="participants">Erik, Claude Architect, Mini Claude, Auxesis CEO</span>
</div>
<div id="messages"></div>
<div id="input-bar">
  <div id="reply-indicator">Replying to <span id="reply-to-name"></span> <span class="close-reply" onclick="clearReply()">&times;</span></div>
  <div id="input-row">
    <select id="to-field"><option value="">@everyone</option><option value="claude-architect">@claude-architect</option><option value="mini-claude">@mini-claude</option><option value="auxesis-ceo">@auxesis-ceo</option></select>
    <textarea id="msg-input" placeholder="Type a message..." rows="1"></textarea>
    <button id="send-btn" onclick="sendMsg()">Send</button>
  </div>
</div>
<script>
const API_KEY = new URLSearchParams(window.location.search).get('key') || '';
const HEADERS = {'Content-Type': 'application/json'};
if (API_KEY) HEADERS['X-API-Key'] = API_KEY;

let lastTs = null;
let replyToId = null;
const messagesDiv = document.getElementById('messages');
const input = document.getElementById('msg-input');
const btn = document.getElementById('send-btn');
const toField = document.getElementById('to-field');
const replyIndicator = document.getElementById('reply-indicator');
const replyToName = document.getElementById('reply-to-name');

async function fetchMessages() {
  try {
    let url = '/messages?limit=100';
    if (lastTs) url += '&since=' + encodeURIComponent(lastTs);
    const r = await fetch(url, {headers: HEADERS});
    if (!r.ok) return;
    const data = await r.json();
    if (data.messages && data.messages.length > 0) {
      data.messages.forEach(renderMsg);
      lastTs = data.messages[data.messages.length - 1].ts;
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  } catch(e) {}
}

function renderMsg(m) {
  const div = document.createElement('div');
  const cls = m.sender.replace(/[^a-z0-9-]/g, '');
  div.className = 'msg ' + cls;
  if (m.priority === 'urgent') div.classList.add('priority-urgent');
  if (m.priority === 'high') div.classList.add('priority-high');
  if (m.recipient) div.classList.add('dm');
  const time = new Date(m.ts).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  const body = m.body.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');

  let header = '<div class="sender">' + m.sender;
  if (m.recipient) header += '<span class="recipient-badge">@' + m.recipient + '</span>';
  header += '</div>';

  let replyLine = '';
  if (m.reply_to) replyLine = '<div class="reply-badge">replying to #' + m.reply_to + '</div>';

  div.innerHTML = replyLine + header + body +
    '<div class="meta-line"><span>' + time + '</span><button class="reply-btn" onclick="setReply(' + m.id + ',\\'' + m.sender + '\\')">reply</button></div>';
  messagesDiv.appendChild(div);
}

function setReply(id, sender) {
  replyToId = id;
  replyToName.textContent = sender + ' (#' + id + ')';
  replyIndicator.style.display = 'block';
  // Auto-set the @to field to the sender
  toField.value = sender === 'erik' ? '' : sender;
  input.focus();
}

function clearReply() {
  replyToId = null;
  replyIndicator.style.display = 'none';
  toField.value = '';
}

async function sendMsg() {
  const body = input.value.trim();
  if (!body) return;
  btn.disabled = true;
  const payload = {sender:'erik', body: body, priority:'normal'};
  if (toField.value) payload.to = toField.value;
  if (replyToId) payload.reply_to = replyToId;
  try {
    await fetch('/send', {method:'POST', headers: HEADERS, body: JSON.stringify(payload)});
    input.value = '';
    clearReply();
    await fetchMessages();
  } catch(e) {}
  btn.disabled = false;
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
});

input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
});

fetchMessages();
setInterval(fetchMessages, 3000);
</script>
</body>
</html>
"""


db.init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
