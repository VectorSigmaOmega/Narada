# local_agent.py - The Silent Screenshot Agent

import requests
import mss
import base64
import time
import os
from datetime import datetime

# --- Configuration ---
SERVER_URL = "http://127.0.0.1:5001" 
SCREENSHOTS_DIR = "screenshots" # The folder to save screenshots in

def take_and_upload_screenshot():
    """Takes a screenshot, saves a copy, encodes it, and sends it to the server."""
    try:
        # --- NEW: Ensure the screenshots directory exists ---
        if not os.path.exists(SCREENSHOTS_DIR):
            os.makedirs(SCREENSHOTS_DIR)

        with mss.mss() as sct:
            sct_img = sct.grab(sct.monitors[1])
            
            # --- NEW: Create a unique filename with a timestamp ---
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = os.path.join(SCREENSHOTS_DIR, f"capture_{timestamp}.png")

            # --- NEW: Save the screenshot to the file ---
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=filename)
            print(f"Screenshot saved to {filename}")

            # Convert to PNG bytes in memory for sending
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            b64_string = base64.b64encode(img_bytes).decode('utf-8')
            
            print("Uploading to server...")
            payload = {'image': b64_string}
            response = requests.post(f"{SERVER_URL}/api/upload", json=payload)
            response.raise_for_status()
            
            print("Upload successful.")

    except Exception as e:
        print(f"An error occurred during screenshot or upload: {e}")


def main_loop():
    """The main loop for polling the server."""
    while True:
        try:
            print("Polling server for a job...")
            response = requests.get(f"{SERVER_URL}/api/check_job", timeout=30)

            if response.status_code == 200:
                data = response.json()
                if data.get("command") == "take_screenshot":
                    print("Job received!")
                    take_and_upload_screenshot()
            else:
                print(f"Server returned status: {response.status_code}. Retrying in 5s.")
                time.sleep(5)

        except requests.exceptions.RequestException as e:
            print(f"Could not connect to server: {e}. Retrying in 5s.")
            time.sleep(5)

if __name__ == "__main__":
    print("Starting local agent...")
    main_loop()