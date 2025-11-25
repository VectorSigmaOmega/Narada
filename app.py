# app.py - The Flask Server (Single Source of Truth)

import os
import io
import base64
import time
import threading

from flask import Flask, request, jsonify, send_from_directory
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set or .env file not found.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

job_store = {
    "job_pending": False,
    "llm_result": None,
    "image_parts": []
}
job_lock = threading.Lock()

app = Flask(__name__, static_folder='build', static_url_path='/')

def run_gemini_in_background(image_list):
    print(f"Background thread started for Gemini analysis on {len(image_list)} parts.")
    try:
        prompt = """
        Analyze the problem presented across the following series of images and provide a comprehensive solution.
        The images are parts of a single problem, view them in order.
        If it's a DSA coding question, provide the code in C++. Explaination of the code is unimportant.
	If it's a coding question but not DSA related, provide the code in the language set in the IDE.
        If it's a multiple-choice question, provide the answer. Explainatiion is secondary.
        Solve the task presented.
        """
        response = model.generate_content([prompt] + image_list, request_options={'timeout': 300})
        with job_lock:
            job_store["llm_result"] = response.text
    except Exception as e:
        print(f"An error occurred in the Gemini background thread: {e}")
        with job_lock:
            job_store["llm_result"] = f"Error: Could not process the image. {e}"
    finally:
        with job_lock:
            job_store["image_parts"] = []

@app.route('/api/trigger', methods=['POST'])
def trigger_job():
    with job_lock:
        job_store["job_pending"] = True
    return jsonify({"status": "triggered"})

@app.route('/api/check_job', methods=['GET'])
def check_job():
    # This long-polling endpoint for the agent remains the same
    for _ in range(25):
        with job_lock:
            if job_store["job_pending"]:
                job_store["job_pending"] = False
                return jsonify({"command": "take_screenshot"})
        time.sleep(1)
    return jsonify({"command": "no_job"})

@app.route('/api/upload', methods=['POST'])
def upload_screenshot():
    # This endpoint remains the same
    data = request.json
    image_bytes = base64.b64decode(data['image'])
    img = Image.open(io.BytesIO(image_bytes))
    with job_lock:
        job_store["image_parts"].append(img)
    return jsonify({"status": "part_received"})

@app.route('/api/solve', methods=['POST'])
def solve_problem():
    # This endpoint remains the same
    with job_lock:
        if not job_store["image_parts"]:
            return jsonify({"error": "No images"}), 400
        image_list_copy = list(job_store["image_parts"])
        job_store["llm_result"] = None
    thread = threading.Thread(target=run_gemini_in_background, args=(image_list_copy,))
    thread.start()
    return jsonify({"status": "solving_started"})

@app.route('/api/clear', methods=['POST'])
def clear_state():
    # This endpoint remains the same
    with job_lock:
        job_store["image_parts"] = []
        job_store["llm_result"] = None
        job_store["job_pending"] = False
    return jsonify({"status": "cleared"})

# --- REPLACED /api/result WITH THIS NEW ENDPOINT ---
@app.route('/api/status', methods=['GET'])
def get_status():
    """Provides a complete status update for the frontend."""
    with job_lock:
        screenshot_count = len(job_store["image_parts"])
        result = job_store["llm_result"]
        
        # If a result is ready, we "consume" it by clearing it
        if result:
            job_store["llm_result"] = None

        return jsonify({
            "screenshotCount": screenshot_count,
            "llmResult": result # Will be the result string or None
        })

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)