import asyncio
import socket
import logging
import os
import time
from typing import List, Set

import uvicorn
import keyboard
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# --- Configuration ---
HOST = "0.0.0.0"
PORT = 8000

# --- Global State ---
state = {
    "intercept_active": False,
    "buffer": "",
    "hook_id": None,
    "loop": None,
    "last_toggle_time": 0,
    "pressed_modifiers": set()  # Track modifiers manually for the exit combo
}

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- FastAPI App ---
app = FastAPI()

# --- Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        await self.send_update()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_update(self):
        message = {
            "mode": "INTERCEPT" if state["intercept_active"] else "PASSTHROUGH",
            "text": state["buffer"]
        }
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WS: {e}")

manager = ConnectionManager()

# --- Keyboard Logic ---

def process_key_event(event):
    """
    Runs in the background thread when Intercept Mode is ON.
    This hook suppresses ALL keys.
    """
    global state
    
    key = event.name.lower()

    # --- Manual Modifier Tracking ---
    # Since we suppress keys, we must manually track if Ctrl/Alt are held down
    # to detect the Exit Combo (Ctrl + Alt + PageUp).
    if key in ('ctrl', 'right ctrl', 'left ctrl', 'alt', 'right alt', 'left alt'):
        if event.event_type == 'down':
            state["pressed_modifiers"].add(key)
        elif event.event_type == 'up':
            if key in state["pressed_modifiers"]:
                state["pressed_modifiers"].remove(key)
    
    # We only process 'down' events for logic to avoid double triggering
    if event.event_type == 'up':
        return

    # --- EXIT CHECK: Ctrl + Alt + PageUp ---
    if key == 'page up':
        # Check if any Ctrl and any Alt are currently pressed
        is_ctrl_down = any('ctrl' in k for k in state["pressed_modifiers"])
        is_alt_down = any('alt' in k for k in state["pressed_modifiers"])
        
        if is_ctrl_down and is_alt_down:
            # We call toggle using call_later to avoid thread conflict with the hook
            keyboard.call_later(toggle_intercept)
            return

    # --- Buffer Handling ---
    if key == 'space':
        state["buffer"] += " "
    elif key == 'enter':
        state["buffer"] += "\n" 
    elif key == 'backspace':
        state["buffer"] = state["buffer"][:-1]
    elif key == 'tab':
        state["buffer"] += "    "
    elif len(key) == 1:
        state["buffer"] += event.name
    
    # Schedule UI Update
    if state["loop"]:
        asyncio.run_coroutine_threadsafe(manager.send_update(), state["loop"])

def toggle_intercept(event=None):
    """
    Toggles interception mode on/off.
    """
    # Debounce check for high-level listener
    if event and event.event_type == 'up':
        return

    global state
    current_time = time.time()
    
    # Cooldown to prevent rapid bouncing
    if current_time - state["last_toggle_time"] < 0.5:
        return
    
    state["last_toggle_time"] = current_time
    state["intercept_active"] = not state["intercept_active"]

    if state["intercept_active"]:
        logger.info(">>> INTERCEPT MODE ACTIVATED")
        # Clear modifiers before entering to prevent sticky keys
        state["pressed_modifiers"] = set()
        # Hook everything and suppress
        state["hook_id"] = keyboard.hook(process_key_event, suppress=True)
    else:
        logger.info("<<< PASSTHROUGH MODE ACTIVATED")
        # Unhook to restore normal Windows typing
        if state["hook_id"]:
            keyboard.unhook(state["hook_id"])
            state["hook_id"] = None

    if state["loop"]:
        asyncio.run_coroutine_threadsafe(manager.send_update(), state["loop"])

def start_keyboard_listeners():
    # Detect the combo to ENTER Intercept Mode
    # Note: 'add_hotkey' works even in background for the initial trigger
    keyboard.add_hotkey('ctrl+alt+page up', toggle_intercept)
    logger.info("Keyboard listeners active.")

# --- FastAPI Routes ---

@app.get("/")
async def get():
    with open("index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "exit_mode":
                # Remote unlock from phone
                if state["intercept_active"]:
                    keyboard.call_later(toggle_intercept)
            # Removed kill/clear logic as requested
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WS Error: {e}")

# --- Helper ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    state["loop"] = loop

    start_keyboard_listeners()

    local_ip = get_local_ip()
    print(f"[-] Mobile URL: http://{local_ip}:{PORT}")
    print(f"[-] Toggle Mode: Ctrl + Alt + Page Up")

    config = uvicorn.Config(app=app, host=HOST, port=PORT, loop="asyncio")
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())