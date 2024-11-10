import cv2
import numpy as np
import pytesseract
import re
import os
import geocoder
from geopy.geocoders import Nominatim
import pycountry
from flask import Flask, render_template, Response, send_from_directory, request, session, jsonify, abort, redirect, url_for
from datetime import datetime
import sqlite3
from collections import Counter, defaultdict
from time import time
import time
import threading
from werkzeug.utils import secure_filename
import atexit
atexit.register(lambda: camera.release() if camera and camera.isOpened() else None)
import logging
import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)
from dataclasses import dataclass
from typing import Optional, Dict, List
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Plate Cascade Setup
plate_cascade = cv2.CascadeClassifier("haarcascade_russian_plate_number.xml")
if plate_cascade.empty():
    print("Error loading cascade file.")

ENABLE_CAMERA = os.getenv("ENABLE_CAMERA", "false").lower() == "true"

if ENABLE_CAMERA:
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Camera is not accessible.")
        camera = None
else:
    print("Camera functionality is disabled in this environment.")
    camera = None

# Directory setup
output_folder = 'web_output/'
originals_folder = os.path.join(output_folder, 'originals')
blackwhite_folder = os.path.join(output_folder, 'blackwhite')

os.makedirs(output_folder, exist_ok=True)
os.makedirs(originals_folder, exist_ok=True)
os.makedirs(blackwhite_folder, exist_ok=True)

camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("Error: Could not open camera.")
else:
    print("Camera is opened successfully.")
    
camera_available = False 

# Global Variables
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("Camera is not accessible. Video streaming features will be disabled.")
    camera = None  # Disable camera functionality

detected_plates = []
last_detection = None
stats = {"total_detections": 100, "successful_detections": 90}
camera_status = "offline" if not camera_available else "online"

# And ensure to release the camera when stopping
def stop_camera():
    global camera
    if camera:
        camera.release()
        camera = None


# Font settings
font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.6
font_thickness = 2

# Plate Detection Class
@dataclass
class PlateDetection:
    plate_number: str
    timestamp: datetime
    country_code: str
    location: Dict[str, str]
    original_image_path: str
    bw_image_path: str

# Camera Manager Class
class CameraManager:
    def __init__(self):
        self.camera = None
        self.lock = threading.Lock()
        
    @contextmanager
    def get_camera(self):
        with self.lock:
            if self.camera is None:
                self.camera = cv2.VideoCapture(0)
                if not self.camera.isOpened():
                    logger.error("Failed to open camera")
                    raise RuntimeError("Camera initialization failed")
            try:
                yield self.camera
            finally:
                if self.camera and self.camera.isOpened():
                    self.camera.release()
                    self.camera = None

camera_manager = CameraManager()

# Country Code Mapping
COUNTRY_CODES = {
    'AL': 'Albania', 'KS': 'Kosovo', 'MK': 'North Macedonia', 'ME': 'Montenegro',
    'RS': 'Serbia', 'GR': 'Greece', 'HR': 'Croatia', 'IT': 'Italy', 'AT': 'Austria', 'DE': 'Germany',
}

# Location Tracking
geolocator = Nominatim(user_agent="plate_detector")
current_location = {
    'street': None,
    'city': None,
    'country': None,
    'lat': None,
    'lon': None,
    'last_update': None
}

# Database initialization
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
            country_code TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            original_image_path TEXT,
            bw_image_path TEXT,
            street TEXT,
            city TEXT,
            country TEXT,
            latitude REAL,
            longitude REAL
        )
    ''')
    conn.close()

# Global variables for tracking
detected_plates = []
plate_tracking = defaultdict(lambda: {'first_seen': None, 'last_seen': None, 'alert_shown': False})
last_detection = {
    'plate_number': None,
    'timestamp': None,
    'detection_time': None,
    'country': None,
    'street': None,
    'city': None
}

def update_location():
    """Background thread to update GPS location"""
    global current_location
    while True:
        try:
            g = geocoder.ip('me')
            if g.ok:
                lat, lon = g.latlng
                location = geolocator.reverse(f"{lat}, {lon}")
                address = location.raw['address']
                current_location.update({
                    'street': address.get('road', 'Unknown Street'),
                    'city': address.get('city', address.get('town', 'Unknown City')),
                    'country': address.get('country', 'Unknown Country'),
                    'lat': lat,
                    'lon': lon,
                    'last_update': datetime.now()
                })
        except Exception as e:
            print(f"Error updating location: {e}")
        time.sleep(1)

def detect_country_code(plate_number):
    """Detect country code from license plate format"""
    patterns = {
        r'^[A-Z]{2}\d{3,5}[A-Z]{2}$': 'AL',  # Albania
        r'^[A-Z]{2}\d{3,4}[A-Z]{2}$': 'RKS',  # Kosovo
        r'^\d{2}-[A-Z]{1,2}-\d{3}$': 'MK',   # North Macedonia
        r'^[A-Z]{2}[A-Z0-9]{4,5}$': 'ME',    # Montenegro
    }
    
    for pattern, country_code in patterns.items():
        if re.match(pattern, plate_number):
            return country_code
    return 'Unknown'

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
    should_alert = duration >= 10 and not plate_tracking[plate_number]['alert_shown']
    
    if should_alert:
        plate_tracking[plate_number]['alert_shown'] = True
        
    return should_alert

def process_video():
    global detected_plates, last_detection
    while True:
        ret, frame = camera.read()
        if not ret:
            continue
            
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
                    country_code = detect_country_code(clean_text)
                    country_name = COUNTRY_CODES.get(country_code, 'Unknown')
                    
                    if last_detection['plate_number'] != clean_text:
                        current_time = datetime.now()
                        
                        # Update last detection info
                        last_detection.update({
                            'plate_number': clean_text,
                            'timestamp': current_time,
                            'detection_time': current_time.strftime("%Y-%m-%d %H:%M:%S"),
                            'country': country_name,
                            'street': current_location['street'],
                            'city': current_location['city']
                        })

                        # Save images
                        current_datetime = current_time.strftime('%Y%m%d%H%M%S')
                        original_image_filename = f'original_{current_datetime}_{clean_text}.png'
                        bw_image_filename = f'bw_{current_datetime}_{clean_text}.png'
                        
                        original_image_path = os.path.join(originals_folder, original_image_filename)
                        bw_image_path = os.path.join(blackwhite_folder, bw_image_filename)
                        
                        cv2.imwrite(original_image_path, frame)
                        cv2.imwrite(bw_image_path, img_thresh)

                        # Save to database
                        conn = get_db_connection()
                        conn.execute('''
                            INSERT INTO plates 
                            (plate_number, country_code, original_image_path, bw_image_path, 
                             street, city, country, latitude, longitude) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (clean_text, country_code, original_image_filename, bw_image_filename,
                              current_location['street'], current_location['city'], country_name,
                              current_location['lat'], current_location['lon']))
                        conn.commit()
                        conn.close()

                    # Display info on frame
                    display_text = f"{clean_text} ({country_name})"
                    location_text = f"{current_location['street']}, {current_location['city']}"
                    cv2.putText(frame, display_text, (x, y - 20), font, font_scale, (0, 0, 255), font_thickness)
                    cv2.putText(frame, location_text, (x, y - 5), font, font_scale * 0.8, (0, 255, 0), font_thickness)

        if not plate_found:
            last_detection['plate_number'] = None
            last_detection['timestamp'] = None
            last_detection['detection_time'] = None
            last_detection['country'] = None
            last_detection['street'] = None
            last_detection['city'] = None

        ret, jpeg_frame = cv2.imencode('.png', frame)
        frame_bytes = jpeg_frame.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/png\r\n\r\n' + frame_bytes + b'\r\n')

# [Previous imports and setup code remains the same until the Flask routes section]

# Flask routes
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
    conn.close()
    return render_template('images.html', plates=detected_plates)

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
        elif search_type == 'location':
            plates = conn.execute(''' 
                SELECT * FROM plates 
                WHERE street LIKE ? OR city LIKE ? OR country LIKE ?
                ORDER BY timestamp DESC
            ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%')).fetchall()
        else:
            plates = []
        
        conn.close()
        
        return render_template('images.html', plates=plates, search_query=search_query, search_type=search_type)
    else:
        return redirect(url_for('images'))

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
                INSERT INTO plates (plate_number, timestamp, original_image_path, bw_image_path, street, city)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (plate_number, timestamp, original_filename, bw_filename, location, current_location['city']))
            conn.commit()
            conn.close()

            return redirect(url_for('images'))
        else:
            return render_template('images.html', error="All fields are required."), 400
    else:
        return render_template('images.html')
    
@app.route('/get_last_detected_plate', methods=['GET'])
def get_last_detected_plate():
    if last_detection['plate_number'] is None:
        return jsonify({
            "plate": None,
            "timestamp": None,
            "detection_time": None,
            "country": None,
            "street": None,
            "city": None
        })
    
    return jsonify({
        "plate": last_detection['plate_number'],
        "detection_time": last_detection['detection_time'],
        "country": last_detection['country'],
        "street": last_detection['street'],
        "city": last_detection['city']
    })




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

@app.route('/uploads/<folder>/<filename>')
def uploaded_file(folder, filename):
    return send_from_directory(os.path.join(app.root_path, 'web_output', folder), filename)

# Add a new detection for demonstration
@app.route('/api/add_detection', methods=['POST'])
def add_detection():
    plate_number = request.json.get('plate_number')
    image_path = request.json.get('image_path', '')
    if plate_number:
        detection = {
            'id': len(detected_plates) + 1,
            'plate_number': plate_number,
            'timestamp': datetime.now().isoformat(),
            'image_path': image_path
        }
        detected_plates.append(detection)
        return jsonify(status="success", plate=detection), 201
    return jsonify(status="error", message="Invalid plate number"), 400

@app.route('/api/detected_plates', methods=['GET'])
def get_detected_plates():
    return jsonify(detected_plates)

@app.route('/get_camera_status', methods=['GET'])
def get_camera_status():
    return jsonify({"camera_status": camera_status})




@app.route('/start_camera', methods=['POST'])
def start_camera():
    global camera
    if camera is None:
        camera = cv2.VideoCapture(1)  # Open the default camera
        if not camera.isOpened():
            return jsonify({'status': 'error', 'message': 'Failed to open camera'})
    return jsonify({'status': 'success'})

@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    global camera
    if camera and camera.isOpened():
        camera.release()  # Stop the camera
        camera = None  # Clear the camera object
    return jsonify({'status': 'success'})

@app.route('/get_stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    
    total_detections = cur.execute('SELECT COUNT(*) FROM plates').fetchone()[0]
    unique_plates = cur.execute('SELECT COUNT(DISTINCT plate_number) FROM plates').fetchone()[0]
    
    top_plates = cur.execute('''
        SELECT plate_number, COUNT(*) as count, MAX(country) as country
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
        SELECT city, COUNT(*) as count
        FROM plates
        GROUP BY city
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
    
    # Conditional camera access based on availability
if camera_available:
    def open_camera():
        try:
            # Placeholder for camera access logic
            pass
        except Exception as e:
            logging.error(f"Camera error: {str(e)}")
else:
    def open_camera():
        logging.warning("Camera is not available in the current environment.")
        return None

class AddressProcessor:
    def __init__(self, address):
        self.address = address  # Store the address as an instance variable

    def process_address(self):
        match = re.search(r'^\d+', self.address, re.UNICODE)
        if match:
            return match.group(0)
        return None
# Error handling for unimplemented routes
@app.errorhandler(404)
def not_found(e):
    return jsonify(error=str(e)), 404

if __name__ == '__main__':
    init_db()
    # Start location tracking in background
    location_thread = threading.Thread(target=update_location)
    location_thread.daemon = True
    location_thread.start()
    
    # Start video processing thread
    video_thread = threading.Thread(target=process_video)
    video_thread.daemon = True
    video_thread.start()
    
    app.run(debug=True)