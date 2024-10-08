import cv2
import numpy as np
import pytesseract
import re
import os
from flask import Flask, render_template, Response, send_from_directory, request, session, jsonify, abort, redirect, url_for
from datetime import datetime
import sqlite3
from collections import Counter
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

def process_video():
    global detected_plates  # Use global variable to access it in other routes
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
                if len(clean_text) >= 4:
                    print("License plate detected:", clean_text)
                    
                    current_datetime = datetime.now().strftime('%Y%m%d%H%M%S')
                    original_image_filename = f'original_{current_datetime}_{clean_text}.png'
                    bw_image_filename = f'bw_{current_datetime}_{clean_text}.png'
                    
                    original_image_path = os.path.join(originals_folder, original_image_filename)
                    bw_image_path = os.path.join(blackwhite_folder, bw_image_filename)
                    
                    cv2.imwrite(original_image_path, frame)
                    cv2.imwrite(bw_image_path, img_thresh)

                    # Store detected plate in global variable
                    detected_plates.append({
                        'plate_number': clean_text,
                        'timestamp': datetime.now(),
                        'original_image_path': original_image_filename,
                        'bw_image_path': bw_image_filename,
                        'location': "Unknown Location"
                    })

                    conn = get_db_connection()
                    conn.execute('INSERT INTO plates (plate_number, original_image_path, bw_image_path, location) VALUES (?, ?, ?, ?)',
                                 (clean_text, original_image_filename, bw_image_filename, "Unknown Location"))
                    conn.commit()
                    conn.close()

                    cv2.putText(frame, clean_text, (x, y - 10), font, font_scale, (0, 0, 255), font_thickness)

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
    conn = get_db_connection()
    
    # Query to get the last detected plate and its timestamp
    last_plate = conn.execute('''
        SELECT plate_number, timestamp 
        FROM plates 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''').fetchone()
    
    conn.close()
    
    if last_plate:
        response = {
            "plate": last_plate['plate_number'],  # The plate detected
            "timestamp": last_plate['timestamp']   # The static time when it was detected
        }
    else:
        response = {
            "plate": None,
            "timestamp": None
        }
    
    return jsonify(response)



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