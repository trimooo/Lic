# main.py

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
import time
import threading
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure key

# Configuration
UPLOAD_FOLDER = 'web_output/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Directory setup
output_folder = 'web_output/'
originals_folder = os.path.join(output_folder, 'originals')
blackwhite_folder = os.path.join(output_folder, 'blackwhite')

# Create necessary directories
for folder in [output_folder, originals_folder, blackwhite_folder]:
    os.makedirs(folder, exist_ok=True)

# Global variables
camera = None
plate_cascade = cv2.CascadeClassifier("haarcascade_russian_plate_number.xml")
detected_plates = []
current_location = {
    'street': None,
    'city': None,
    'country': None,
    'lat': None,
    'lon': None,
    'last_update': None
}
last_detection = {
    'plate_number': None,
    'timestamp': None,
    'detection_time': None,
    'country': None,
    'street': None,
    'city': None
}

# Country code mappings
COUNTRY_CODES = {
    'AL': 'Albania',
    'KS': 'Kosovo',
    'MK': 'North Macedonia',
    'ME': 'Montenegro',
    'RS': 'Serbia',
    'GR': 'Greece',
    'HR': 'Croatia',
    'IT': 'Italy',
    'AT': 'Austria',
    'DE': 'Germany',
}

# Initialize geolocator
geolocator = Nominatim(user_agent="plate_detector")

def is_cloud_environment():
    """Check if running in cloud environment"""
    return os.environ.get('DEPLOYMENT_ENV') == 'cloud'

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    """Create database connection"""
    conn = sqlite3.connect('license_plates.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with required tables"""
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
    conn.commit()
    conn.close()

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
        time.sleep(60)  # Update every minute

def initialize_camera():
    """Initialize camera if not in cloud environment"""
    if is_cloud_environment():
        return None
        
    try:
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            print("Error: Could not open camera.")
            return None
        print("Camera is opened successfully.")
        return camera
    except Exception as e:
        print(f"Error initializing camera: {e}")
        return None

def process_frame(frame):
    """Process a single frame for license plate detection"""
    if frame is None:
        return None, []
        
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    
    detected = []
    for (x, y, w, h) in plates:
        plate_roi = gray[y:y+h, x:x+w]
        img_thresh = cv2.adaptiveThreshold(
            plate_roi, 255.0, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 19, 9
        )
        text = pytesseract.image_to_string(img_thresh)
        
        if text:
            clean_text = re.sub(r'\W+', '', text).upper()
            if len(clean_text) >= 4:
                detected.append({
                    'plate_number': clean_text,
                    'coordinates': (x, y, w, h),
                    'threshold_image': img_thresh
                })
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(frame, clean_text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    
    return frame, detected

def save_detection(plate_info, original_image=None):
    """Save detection information to database and filesystem"""
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y%m%d%H%M%S")
    
    # Save the threshold image
    bw_filename = f"bw_{timestamp}_{plate_info['plate_number']}.png"
    bw_path = os.path.join(blackwhite_folder, bw_filename)
    cv2.imwrite(bw_path, plate_info['threshold_image'])
    
    # Handle original image
    if original_image is not None:
        original_filename = f"original_{timestamp}_{plate_info['plate_number']}.png"
        original_path = os.path.join(originals_folder, original_filename)
        cv2.imwrite(original_path, original_image)
    else:
        original_filename = None
    
    # Get country code
    country_code = detect_country_code(plate_info['plate_number'])
    
    # Save to database
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO plates 
        (plate_number, country_code, original_image_path, bw_image_path, 
         street, city, country, latitude, longitude) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        plate_info['plate_number'],
        country_code,
        original_filename,
        bw_filename,
        current_location['street'],
        current_location['city'],
        COUNTRY_CODES.get(country_code, 'Unknown'),
        current_location['lat'],
        current_location['lon']
    ))
    conn.commit()
    conn.close()

def generate_frames():
    """Generate video frames with plate detection"""
    global camera, last_detection
    
    while True:
        if is_cloud_environment():
            # Generate placeholder frame for cloud environment
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, 
                       "Camera not available in cloud deployment", 
                       (50, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 
                       0.8, 
                       (255, 255, 255), 
                       2)
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
            continue
            
        if camera is None or not camera.isOpened():
            time.sleep(0.1)
            continue
            
        success, frame = camera.read()
        if not success:
            continue
            
        processed_frame, detections = process_frame(frame)
        
        # Update last detection if plates were found
        if detections:
            plate_info = detections[0]  # Use first detection
            current_time = datetime.now()
            last_detection.update({
                'plate_number': plate_info['plate_number'],
                'timestamp': current_time,
                'detection_time': current_time.strftime("%Y-%m-%d %H:%M:%S"),
                'country': COUNTRY_CODES.get(detect_country_code(plate_info['plate_number']), 'Unknown'),
                'street': current_location['street'],
                'city': current_location['city']
            })
            
            # Save detection
            save_detection(plate_info, processed_frame)
        
        ret, buffer = cv2.imencode('.jpg', processed_frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# Flask Routes
@app.route('/')
def index():
    return render_template('index.html', cloud_mode=is_cloud_environment())

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Read and process the uploaded image
        frame = cv2.imread(filepath)
        processed_frame, detections = process_frame(frame)
        
        if detections:
            # Save detections
            for plate_info in detections:
                save_detection(plate_info, processed_frame)
            
            return jsonify({
                'success': True,
                'plates': [d['plate_number'] for d in detections]
            })
        
        os.remove(filepath)  # Clean up uploaded file
        return jsonify({'error': 'No plates detected'}), 400
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/images')
def images():
    conn = get_db_connection()
    plates = conn.execute('SELECT * FROM plates ORDER BY timestamp DESC').fetchall()
    conn.close()
    return render_template('images.html', plates=plates)

@app.route('/get_camera_status')
def get_camera_status():
    if is_cloud_environment():
        return jsonify({
            'status': 'cloud',
            'is_running': False,
            'message': 'Camera not available in cloud deployment'
        })
    
    return jsonify({
        'status': 'success',
        'is_running': camera is not None and camera.isOpened()
    })

@app.route('/get_stats')
def get_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    
    stats = {
        'total_detections': cur.execute('SELECT COUNT(*) FROM plates').fetchone()[0],
        'unique_plates': cur.execute('SELECT COUNT(DISTINCT plate_number) FROM plates').fetchone()[0],
        'top_plates': [dict(row) for row in cur.execute('''
            SELECT plate_number, COUNT(*) as count 
            FROM plates 
            GROUP BY plate_number 
            ORDER BY count DESC 
            LIMIT 5
        ''').fetchall()],
        'locations': [dict(row) for row in cur.execute('''
            SELECT city, COUNT(*) as count 
            FROM plates 
            GROUP BY city 
            ORDER BY count DESC 
            LIMIT 5
        ''').fetchall()]
    }
    
    conn.close()
    return jsonify(stats)

@app.route('/get_last_detection')
def get_last_detection():
    return jsonify(last_detection)

# Main execution
if __name__ == '__main__':
    init_db()
    
    # Start location tracking thread
    location_thread = threading.Thread(target=update_location)
    location_thread.daemon = True
    location_thread.start()
    
    # Initialize camera if not in cloud environment
    if not is_cloud_environment():
        camera = initialize_camera()
    
    # Start the Flask app
    app.run(debug=True, host='0.0.0.0', port=8000)
