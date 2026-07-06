!pkill -9 -f cloudflared
!pkill -9 -f uvicorn

# 2. Install FastAPI, Uvicorn, and Websockets
!pip install -q fastapi uvicorn websockets

# 3. Download Cloudflare tunnel binary to expose the environment
!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
!chmod +x cloudflared

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import subprocess
import time
import re
import threading

app = FastAPI()

app.add_middleware(
CORSMiddleware,
allow_origins=["*"],
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],
)

canvas_socket = None
pending_requests = {}
req_id = 0

@app.get("/")
async def root():
return {"status": "Google Colab Serverless Bridge Active"}

@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
global canvas_socket
await websocket.accept()
canvas_socket = websocket
print("🚀 Browser extension connected via WebSocket!")
try:
while True:
data = await websocket.receive_text()
try:
msg = json.loads(data)
msg_id = msg.get("id")
body = msg.get("body")
if msg_id in pending_requests:
pending_requests[msg_id].set_result(body)
except Exception:
pass
except WebSocketDisconnect:
print("🔌 Browser extension disconnected.")
if canvas_socket == websocket:
canvas_socket = None

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
global canvas_socket, req_id
if not canvas_socket:
return Response(content=json.dumps({"error": "Canvas app offline"}), status_code=503, media_type="application/json")

body = await request.json()
req_id += 1
current_id = req_id

loop = asyncio.get_event_loop()
future = loop.create_future()
pending_requests[current_id] = future

print(f"📥 Received prompt. Forwarding to Browser Tunnel (ID: {current_id})...")
await canvas_socket.send_text(json.dumps({"id": current_id, "body": body}))

try:
response_body = await asyncio.wait_for(future, timeout=30.0)
return response_body
except asyncio.TimeoutError:
return Response(content=json.dumps({"error": "Request timed out"}), status_code=504, media_type="application/json")
finally:
if current_id in pending_requests:
del pending_requests[current_id]

# Start Cloudflared tunnel in the background to get public URL
print("\n🔥 Starting secure cloud tunnel...")
tunnel_process = subprocess.Popen(
["./cloudflared", "tunnel", "--url", "http://localhost:8000"],
stdout=subprocess.PIPE,
stderr=subprocess.STDOUT,
text=True
)

# Parse output to find the trycloudflare URL
tunnel_url = None
time.sleep(3) # Wait for tunnel initialization
for _ in range(30):
line = tunnel_process.stdout.readline()
match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
if match:
tunnel_url = match.group(0)
break
time.sleep(0.2)

if tunnel_url:
print("=" * 60)
print("🎉 PORT FORWARDING COMPLETED!")
print(f"Your Public Bridge URL: {tunnel_url.replace('https://', '')}")
print("Paste the URL above directly into Step 3 of your Canvas interface.")
print("=" * 60)
else:
print("❌ Failed to resolve Cloudflare tunnel link automatically. Check cell output logs.")

# Run FastAPI server in a background thread to prevent blocking Colab's Jupyter event loop
print("🚀 Starting FastAPI Server in isolated thread...")
config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
server = uvicorn.Server(config=config)

server_thread = threading.Thread(target=server.run, daemon=True)
server_thread.start()

# Keep cell alive and print success
while not server.started:
time.sleep(0.1)

print("⚡ Isolated background server is online! Safe to keep working.")
