import cv2
import numpy as np
import pytesseract
import re
import os
from flask import Flask, render_template, Response, send_from_directory, request, session, jsonify, abort, redirect, url_for
from datetime import datetime
import sqlite3
from collections import Counter
from time import time
from collections import defaultdict
from werkzeug.utils import secure_filename
import threading

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Camera and image processing setup
camera_active = False
plate_cascade = cv2.CascadeClassifier("C:/Users/Trimi/haarcascade_russian_plate_number.xml")

if plate_cascade.empty():
    print("Error loading cascade file.")

output_folder = 'web_output/'
originals_folder = os.path.join(output_folder, 'originals')
blackwhite_folder = os.path.join(output_folder, 'blackwhite')

os.makedirs(output_folder, exist_ok=True)
os.makedirs(originals_folder, exist_ok=True)
os.makedirs(blackwhite_folder, exist_ok=True)

cap = cv2.VideoCapture(1)

font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.6
font_thickness = 2

def get_db_connection():
    conn = sqlite3.connect('license_plates.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS plates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            original_image_path TEXT,
            bw_image_path TEXT,
            location TEXT
        )
    ''')
    conn.close()

init_db()

# Global variable to store detected plates
detected_plates = []


# Add this after the detected_plates declaration
plate_tracking = defaultdict(lambda: {'first_seen': None, 'last_seen': None, 'alert_shown': False})

def check_plate_duration(plate_number, current_time):
    """Check if a plate has been present for more than 5 minutes"""
    if plate_number not in plate_tracking:
        plate_tracking[plate_number] = {
            'first_seen': current_time,
            'last_seen': current_time,
            'alert_shown': False
        }
    else:
        plate_tracking[plate_number]['last_seen'] = current_time
        
    duration = current_time - plate_tracking[plate_number]['first_seen']
    should_alert = duration >= 30 and not plate_tracking[plate_number]['alert_shown']  # 300 seconds = 5 minutes
    
    if should_alert:
        plate_tracking[plate_number]['alert_shown'] = True
        
    return should_alert


last_detection = {
    'plate_number': None,
    'timestamp': None,
    'detection_time': None
}

def process_video():
    global detected_plates, last_detection
    while True:
        ret, frame = cap.read()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        plate_found = False
        
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
                if len(clean_text) >= 4:
                    plate_found = True
                    
                    # Only update timestamp if it's a new plate or first detection
                    if last_detection['plate_number'] != clean_text:
                        current_time = datetime.now()
                        last_detection['plate_number'] = clean_text
                        last_detection['timestamp'] = current_time
                        last_detection['detection_time'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Save the image files
                        current_datetime = current_time.strftime('%Y%m%d%H%M%S')
                        original_image_filename = f'original_{current_datetime}_{clean_text}.png'
                        bw_image_filename = f'bw_{current_datetime}_{clean_text}.png'
                        
                        original_image_path = os.path.join(originals_folder, original_image_filename)
                        bw_image_path = os.path.join(blackwhite_folder, bw_image_filename)
                        
                        cv2.imwrite(original_image_path, frame)
                        cv2.imwrite(bw_image_path, img_thresh)

                        # Add to database
                        conn = get_db_connection()
                        conn.execute('''
                            INSERT INTO plates 
                            (plate_number, original_image_path, bw_image_path, location) 
                            VALUES (?, ?, ?, ?)
                        ''', (clean_text, original_image_filename, bw_image_filename, "Unknown Location"))
                        conn.commit()
                        conn.close()

                    cv2.putText(frame, clean_text, (x, y - 10), font, font_scale, (0, 0, 255), font_thickness)

        if not plate_found:
            # Reset detection if no plate is found
            last_detection['plate_number'] = None
            last_detection['timestamp'] = None
            last_detection['detection_time'] = None

        ret, jpeg_frame = cv2.imencode('.png', frame)
        frame_bytes = jpeg_frame.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/png\r\n\r\n' + frame_bytes + b'\r\n')

# Start video processing in a separate thread
video_thread = threading.Thread(target=process_video)
video_thread.daemon = True  # Daemonize thread
video_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(process_video(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/images')
def images():
    conn = get_db_connection()
    detected_plates = conn.execute('SELECT * FROM plates ORDER BY timestamp DESC').fetchall()
    conn.close()  # Close the connection after fetching plates

    # Debugging output to verify data
    print(detected_plates)

    return render_template('images.html', plates=detected_plates)


# Add this new route to check for prolonged detections
@app.route('/check_prolonged_detection')
def check_prolonged_detection():
    if not detected_plates:
        return jsonify({'alert': False, 'plate': None})
    
    latest_plate = detected_plates[-1]
    if latest_plate.get('duration_alert', False):
        return jsonify({
            'alert': True,
            'plate': latest_plate['plate_number'],
            'timestamp': latest_plate['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return jsonify({'alert': False, 'plate': None})


@app.route('/delete_plate/<int:plate_id>', methods=['POST'])
def delete_plate(plate_id):
    conn = get_db_connection()
    
    # Get the plate record to retrieve image paths
    plate = conn.execute('SELECT * FROM plates WHERE id = ?', (plate_id,)).fetchone()
    
    if plate:
        # Delete images from the filesystem
        original_image_path = os.path.join(originals_folder, plate['original_image_path'])
        bw_image_path = os.path.join(blackwhite_folder, plate['bw_image_path'])
        
        if os.path.exists(original_image_path):
            os.remove(original_image_path)
        if os.path.exists(bw_image_path):
            os.remove(bw_image_path)

        # Delete the record from the database
        conn.execute('DELETE FROM plates WHERE id = ?', (plate_id,))
        conn.commit()
    
    conn.close()
    
    return redirect(url_for('images'))

@app.route('/search', methods=['GET', 'POST'])
def search_images():
    if request.method == 'POST':
        search_query = request.form.get('search', '')
        search_type = request.form.get('search_type', 'plate')
        
        conn = get_db_connection()
        
        if search_type == 'plate':
            plates = conn.execute(''' 
                SELECT * FROM plates 
                WHERE plate_number LIKE ? 
                ORDER BY timestamp DESC
            ''', (f'%{search_query}%',)).fetchall()
        elif search_type == 'time':
            plates = conn.execute(''' 
                SELECT * FROM plates 
                WHERE timestamp LIKE ? OR strftime('%H:%M', timestamp) LIKE ?
                ORDER BY timestamp DESC
            ''', (f'%{search_query}%', f'%{search_query}%',)).fetchall()
        else:
            plates = []
        
        conn.close()
        
        return render_template('images.html', plates=plates, search_query=search_query, search_type=search_type)
    else:
        return redirect(url_for('images'))


@app.route('/upload_plate', methods=['GET', 'POST'])
def upload_plate():
    if request.method == 'POST':
        plate_number = request.form.get('plate_number')
        location = request.form.get('location')
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        bw_image = request.files.get('bw_image')
        original_image = request.files.get('original_image')
        
        if bw_image and original_image and plate_number and location:
            bw_filename = secure_filename(f"bw_{timestamp}_{plate_number}.png")
            original_filename = secure_filename(f"original_{timestamp}_{plate_number}.png")
            
            bw_image.save(os.path.join(blackwhite_folder, bw_filename))
            original_image.save(os.path.join(originals_folder, original_filename))
            
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO plates (plate_number, timestamp, original_image_path, bw_image_path, location)
                VALUES (?, ?, ?, ?, ?)
            ''', (plate_number, timestamp, original_filename, bw_filename, location))
            conn.commit()
            conn.close()

            return redirect(url_for('images'))
        else:
            return render_template('images.html', error="All fields are required."), 400
    else:
        return render_template('images.html')
    
@app.route('/uploads/<folder>/<filename>')
def uploaded_file(folder, filename):
    # Serve the uploaded file based on the folder and filename
    return send_from_directory(os.path.join(app.root_path, 'web_output', folder), filename)

@app.route('/get_last_detected_plate', methods=['GET'])
def get_last_detected_plate():
    if last_detection['plate_number'] is None:
        return jsonify({
            "plate": None,
            "timestamp": None,
            "detection_time": None
        })
    
    return jsonify({
        "plate": last_detection['plate_number'],
        "detection_time": last_detection['detection_time']
    })



@app.route('/get_stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    
    total_detections = cur.execute('SELECT COUNT(*) FROM plates').fetchone()[0]
    unique_plates = cur.execute('SELECT COUNT(DISTINCT plate_number) FROM plates').fetchone()[0]
    
    top_plates = cur.execute('''
        SELECT plate_number, COUNT(*) as count, location
        FROM plates 
        GROUP BY plate_number 
        ORDER BY count DESC 
        LIMIT 5
    ''').fetchall()
    
    hour_distribution = cur.execute('''
        SELECT strftime('%H', timestamp) as hour, COUNT(*) as count 
        FROM plates 
        GROUP BY hour 
        ORDER BY hour
    ''').fetchall()
    
    locations = cur.execute('''
        SELECT location, COUNT(*) as count
        FROM plates
        GROUP BY location
        ORDER BY count DESC
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        "total_detections": total_detections,
        "unique_plates": unique_plates,
        "top_plates": [dict(p) for p in top_plates],
        "hour_distribution": [dict(h) for h in hour_distribution],
        "top_locations": [dict(l) for l in locations]
    })

if __name__ == '__main__':
   app.run(debug=True)