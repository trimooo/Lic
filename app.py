import cv2
import numpy as np
import pytesseract
import re
import os
from flask import Flask, render_template, Response, send_from_directory, request, session,  jsonify, abort
from datetime import datetime
import sqlite3
from collections import Counter

app = Flask(__name__)

# Define the camera status variable
camera_active = False

# Load the Haar cascade for Russian plate numbers
plate_cascade = cv2.CascadeClassifier("C:/Users/Trimi/haarcascade_russian_plate_number.xml")

if plate_cascade.empty():
    print("Error loading cascade file.")


# Define the paths for saving images
output_folder = 'web_output/'
originals_folder = os.path.join(output_folder, 'originals')
blackwhite_folder = os.path.join(output_folder, 'blackwhite')

os.makedirs(output_folder, exist_ok=True)
os.makedirs(originals_folder, exist_ok=True)
os.makedirs(blackwhite_folder, exist_ok=True)

# Connect to the webcam
cap = cv2.VideoCapture(1)  # Use 0 for the first camera (change if you have multiple cameras)

# Create a font for text overlay
font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.6
font_thickness = 2


# Shtoni një lidhje me bazën e të dhënave SQLite
def get_db_connection():
    conn = sqlite3.connect('license_plates.db')
    conn.row_factory = sqlite3.Row
    return conn

# Krijoni tabelën nëse nuk ekziston
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS plates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.close()

init_db()

def process_video():
    while True:
        ret, frame = cap.read()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        for (x, y, w, h) in plates:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            plate_roi = gray[y:y+h, x:x+w]
            img_thresh = cv2.adaptiveThreshold(
                plate_roi, 255.0, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 19, 9
            )
            text = pytesseract.image_to_string(img_thresh)

            if text:
                clean_text = re.sub(r'\W+', '', text).upper()
                if len(clean_text) >= 4:  # Supozojmë që një targë e vlefshme ka të paktën 4 karaktere
                    print("License plate detected:", clean_text)
                    
                    # Ruaj në bazën e të dhënave
                    conn = get_db_connection()
                    conn.execute('INSERT INTO plates (plate_number) VALUES (?)', (clean_text,))
                    conn.commit()
                    conn.close()

                    current_datetime = datetime.now().strftime('%Y%m%d%H%M%S')
                    original_image_filename = os.path.join(originals_folder, f'original_{current_datetime}_{clean_text}.png')
                    cv2.imwrite(original_image_filename, frame)
                    bw_image_filename = os.path.join(blackwhite_folder, f'bw_{current_datetime}_{clean_text}.png')
                    cv2.imwrite(bw_image_filename, img_thresh)
                    cv2.putText(frame, clean_text, (x, y - 10), font, font_scale, (0, 0, 255), font_thickness)

        ret, jpeg_frame = cv2.imencode('.jpg', frame)
        frame_bytes = jpeg_frame.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(process_video(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/images')
def images():
    refresh = request.args.get('refresh')
    if refresh and refresh.lower() == 'true':
        session.pop('search_datetime', None)

    original_images = os.listdir(originals_folder)
    bw_images = os.listdir(blackwhite_folder)
    return render_template('images.html', original_images=original_images, bw_images=bw_images)

@app.route('/images/<folder>/<filename>')
def uploaded_file(folder, filename):
    if folder == 'originals':
        return send_from_directory(originals_folder, filename)
    elif folder == 'blackwhite':
        return send_from_directory(blackwhite_folder, filename)
    else:
        return "Invalid folder", 404

@app.route('/start_camera', methods=['GET'])
def start_camera():
    global camera_active
    if not camera_active:
        camera_active = True
        return jsonify({"status": "success", "message": "Camera started"}), 200
    else:
        return jsonify({"status": "error", "message": "Camera is already active"}), 400

@app.route('/stop_camera', methods=['GET'])
def stop_camera():
    global camera_active
    if camera_active:
        camera_active = False
        return jsonify({"status": "success", "message": "Camera stopped"}), 200
    else:
        return jsonify({"status": "error", "message": "Camera is not active"}), 400

@app.route('/search', methods=['GET', 'POST'])
def search_images():
    if request.method == 'POST':
        search_query = request.form.get('search', '')
        if not search_query:
            return render_template('search_results.html', results=[], error="Ju lutem vendosni një term kërkimi.")
        
        conn = get_db_connection()
        results = conn.execute('''
            SELECT plate_number, timestamp 
            FROM plates 
            WHERE plate_number LIKE ? 
            ORDER BY timestamp DESC
        ''', (f'%{search_query}%',)).fetchall()
        conn.close()
        
        return render_template('search_results.html', results=results, search_query=search_query)
    else:
        # Nëse është kërkesë GET, thjesht shfaq formën e kërkimit
        return render_template('search_form.html')

@app.errorhandler(400)
def bad_request(e):
    return render_template('error.html', error=str(e)), 400

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error="Faqja nuk u gjet."), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error="Ndodhi një gabim i brendshëm në server."), 500
@app.route('/get_stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    
    total_detections = cur.execute('SELECT COUNT(*) FROM plates').fetchone()[0]
    unique_plates = cur.execute('SELECT COUNT(DISTINCT plate_number) FROM plates').fetchone()[0]
    
    # Top 5 targat më të shpeshta
    top_plates = cur.execute('''
        SELECT plate_number, COUNT(*) as count 
        FROM plates 
        GROUP BY plate_number 
        ORDER BY count DESC 
        LIMIT 5
    ''').fetchall()
    
    # Shpeshtësia e detektimeve sipas orës së ditës
    hour_distribution = cur.execute('''
        SELECT strftime('%H', timestamp) as hour, COUNT(*) as count 
        FROM plates 
        GROUP BY hour 
        ORDER BY hour
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        "total_detections": total_detections,
        "unique_plates": unique_plates,
        "top_plates": [dict(p) for p in top_plates],
        "hour_distribution": [dict(h) for h in hour_distribution]
    })



if __name__ == '__main__':
   app.run(debug=True)
