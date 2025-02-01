import cv2
import numpy as np
import pytesseract
import re
import os
import geocoder
from geopy.geocoders import Nominatim
from flask import Flask, render_template, Response, send_from_directory, request, jsonify, redirect, url_for
from datetime import datetime
import sqlite3
from collections import defaultdict
import time
import threading
from werkzeug.utils import secure_filename
import atexit
import logging
from contextlib import contextmanager
import imutils
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Add near top of app.py
originals_folder = os.path.join('web_output', 'originals')
os.makedirs(originals_folder, exist_ok=True)



# Configuration
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
TESSERACT_CONFIG = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
HAAR_CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_russian_plate_number.xml'

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# Initialize plate cascade
plate_cascade = cv2.CascadeClassifier(HAAR_CASCADE_PATH)
if plate_cascade.empty():
    raise SystemError("Failed to load cascade file. Check path: " + HAAR_CASCADE_PATH)



# CameraHandler Class Fixes
class CameraHandler:
    def __init__(self):
        self.camera = None
        self.lock = threading.Lock()
        self.frame_buffer = None
        self.processing_frame = None
        self.is_running = False
        self.plate_tracking = defaultdict(lambda: {'first_seen': None, 'last_seen': None, 'alert_sent': False})  # Initialize plate_tracking

    def initialize(self, camera_index=0):
        with self.lock:
            if self.camera is None:
                self.camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
                if not self.camera.isOpened():
                    logger.error("Camera initialization failed")
                    return False
                
                # Set explicit camera resolution
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.is_running = True
                logger.info("Camera initialized at 1280x720")
                return True
            return True

    def get_frame(self):
        with self.lock:
            if self.camera and self.camera.isOpened():
                ret, frame = self.camera.read()
                if ret:
                    self.processing_frame = frame
                    return True
                logger.error("Failed to capture frame")
            return False

    def update_frame_buffer(self, frame):
        with self.lock:
            if frame is not None:
                # Convert BGR to RGB and encode
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                _, buffer = cv2.imencode('.jpg', frame_rgb)
                self.frame_buffer = buffer.tobytes()

    def release(self):
        with self.lock:
            if self.camera:
                self.camera.release()
                self.camera = None
            self.is_running = False

# Global instances
camera_handler = CameraHandler()
current_location = {
    'street': 'Unknown', 'city': 'Unknown', 'country': 'Unknown',
    'lat': 0.0, 'lon': 0.0, 'last_update': None
}
last_detection = {
    'plate_number': None, 'timestamp': None, 'detection_time': None,
    'country': None, 'street': None, 'city': None
}

# Database setup
@contextmanager
def get_db_connection():
    conn = sqlite3.connect('license_plates.db')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                country_code TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                original_image_path TEXT,
                street TEXT,
                city TEXT,
                country TEXT
            )
        ''')

# Video Processing Thread Fix
def process_video():
    logger.info("Starting video processing thread")
    time.sleep(2)  # Camera warmup
    
    while camera_handler.is_running:
        if camera_handler.get_frame():
            frame = camera_handler.processing_frame
            if frame is None:
                continue
            
            # Maintain original aspect ratio
            debug_frame = imutils.resize(frame, width=800)
            
            # Add status text to actual camera frame
            cv2.putText(debug_frame, "STATUS: CAMERA ACTIVE", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, (0, 255, 0), 2)
            
            camera_handler.update_frame_buffer(debug_frame)
        
        time.sleep(0.033)

def process_video():
    logger.info("Starting video processing thread")
    time.sleep(2)  # Camera warmup
    
    while camera_handler.is_running:
        if camera_handler.get_frame():
            frame = camera_handler.processing_frame
            if frame is None:
                continue
            
            # Maintain original aspect ratio
            debug_frame = imutils.resize(frame, width=800)
            
            # Add status text to actual camera frame
            cv2.putText(debug_frame, "STATUS: CAMERA ACTIVE", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, (0, 255, 0), 2)
            
            camera_handler.update_frame_buffer(debug_frame)
        
        time.sleep(0.033)

def generate_frames():
    while True:
        if camera_handler.frame_buffer:
            yield (b'--frame\r\n'
                  b'Content-Type: image/jpeg\r\n\r\n' + 
                  camera_handler.frame_buffer + b'\r\n')
        else:
            # Fallback blank frame with status
            blank = np.zeros((600, 800, 3), dtype=np.uint8)
            cv2.putText(blank, "STATUS: NO FEED", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            _, buffer = cv2.imencode('.jpg', blank)
            yield (b'--frame\r\n'
                  b'Content-Type: image/jpeg\r\n\r\n' + 
                  buffer.tobytes() + b'\r\n')
        time.sleep(0.033)

def handle_plate_detection(plate_number, frame, x, y, current_time):
    country_code = detect_country_code(plate_number)
    country_name = COUNTRY_CODES.get(country_code, 'Unknown')
    
    # Update tracking
    with camera_handler.lock:
        if plate_number not in camera_handler.plate_tracking:
            camera_handler.plate_tracking[plate_number] = {
                'first_seen': current_time,
                'last_seen': current_time,
                'alert_sent': False
            }
        else:
            camera_handler.plate_tracking[plate_number]['last_seen'] = current_time

    # Update display and database
    if last_detection.get('plate_number') != plate_number:
        timestamp_str = current_time.strftime("%Y-%m-%d_%H-%M-%S")
        img_path = os.path.join('web_output', f'original_{timestamp_str}_{plate_number}.png')
        
        try:
            cv2.imwrite(img_path, frame)
            with get_db_connection() as conn:
                conn.execute('''
                    INSERT INTO plates 
                    (plate_number, country_code, original_image_path, street, city, country)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (plate_number, country_code, img_path,
                      current_location['street'], current_location['city'], country_name))
                conn.commit()
                
            last_detection.update({
                'plate_number': plate_number,
                'timestamp': current_time,
                'detection_time': timestamp_str,
                'country': country_name,
                'street': current_location['street'],
                'city': current_location['city']
            })
            
        except Exception as e:
            logger.error(f"Detection handling error: {str(e)}")

    # Draw detection info
    cv2.putText(frame, f"{plate_number} ({country_name})", 
               (x, y-25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
    cv2.putText(frame, f"{current_location['street']}, {current_location['city']}",
               (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

def detect_country_code(plate_number):
    patterns = {
        r'^[A-Z]{2}\d{3,5}[A-Z]{2}$': 'AL',
        r'^[A-Z]{2}\d{3,4}[A-Z]{2}$': 'RKS',
        r'^\d{2}-[A-Z]{1,2}-\d{3}$': 'MK',
        r'^[A-Z]{2}[A-Z0-9]{4,5}$': 'ME',
    }
    for pattern, code in patterns.items():
        if re.match(pattern, plate_number):
            return code
    return 'Unknown'

COUNTRY_CODES = {
    'AL': 'Albania', 'RKS': 'Kosovo', 'MK': 'North Macedonia',
    'ME': 'Montenegro', 'RS': 'Serbia', 'GR': 'Greece'
}

# Web routes
@app.route('/')
def index():
    stats = {
        'total_detections': 0,
        'unique_plates': 0,
        'top_plates': [],
        'hour_distribution': []
    }
    
    try:
        with get_db_connection() as conn:
            # Total detections
            stats['total_detections'] = conn.execute('SELECT COUNT(*) FROM plates').fetchone()[0]
            
            # Unique plates
            stats['unique_plates'] = conn.execute('SELECT COUNT(DISTINCT plate_number) FROM plates').fetchone()[0]
            
            # Top 5 plates
            stats['top_plates'] = conn.execute('''
                SELECT plate_number, COUNT(*) as count 
                FROM plates 
                GROUP BY plate_number 
                ORDER BY count DESC 
                LIMIT 5
            ''').fetchall()
            
            # Hour distribution
            stats['hour_distribution'] = conn.execute('''
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM plates
                GROUP BY hour
                ORDER BY hour
            ''').fetchall()
            
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
    
    return render_template('index.html', stats=stats)


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

def generate_frames():
    while camera_handler.is_running:
        try:
            if camera_handler.frame_buffer:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + 
                       camera_handler.frame_buffer + b'\r\n')
            else:
                logger.warning("No frame buffer available")
            time.sleep(0.033)  # ~30 FPS
        except Exception as e:
            logger.error(f"Frame generation error: {str(e)}")
            break
        
@app.route('/uploads/<folder>/<filename>')
def uploaded_file(folder, filename):
    try:
        return send_from_directory(os.path.join(app.root_path, 'web_output', folder), filename)
    except FileNotFoundError:
        abort(404)

# Update the upload_plate route
@app.route('/upload_plate', methods=['GET', 'POST'])
def upload_plate():
    if request.method == 'POST':
        try:
            plate_number = request.form.get('plate_number')
            location = request.form.get('location')
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            
            # Validate required fields
            if not plate_number or not location:
                raise ValueError("All fields are required")
                
            # Handle file uploads
            original_image = request.files.get('original_image')
            if not original_image:
                raise ValueError("Original image is required")
                
            # Save files (fix path handling)
            original_filename = secure_filename(f"original_{timestamp}_{plate_number}.png")
            original_image.save(os.path.join(originals_folder, original_filename))


            # Database operation
            with get_db_connection() as conn:
                conn.execute('''
                    INSERT INTO plates 
                    (plate_number, timestamp, original_image_path, street, city)
                    VALUES (?, ?, ?, ?, ?)
                ''', (plate_number, timestamp, original_filename, 
                      location, current_location.get('city', 'Unknown')))
                conn.commit()

            return redirect(url_for('images'))
            
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            return render_template('images.html', error=str(e))
    
    # GET request - show upload form
    with get_db_connection() as conn:
        plates = conn.execute('SELECT * FROM plates ORDER BY timestamp DESC').fetchall()
    return render_template('images.html', plates=plates)

@app.route('/delete_plate/<int:id>', methods=['POST'])
def delete_plate(id):
    try:
        with get_db_connection() as conn:
            # Fetch the plate record to get the image path
            plate = conn.execute('SELECT * FROM plates WHERE id = ?', (id,)).fetchone()
            if plate:
                # Delete the associated image file
                if plate['original_image_path']:
                    image_path = os.path.join('web_output', 'originals', plate['original_image_path'])
                    if os.path.exists(image_path):
                        os.remove(image_path)
                
                # Delete the database record
                conn.execute('DELETE FROM plates WHERE id = ?', (id,))
                conn.commit()
                return jsonify({'status': 'success'})
            else:
                return jsonify({'status': 'error', 'message': 'Plate not found'}), 404
    except Exception as e:
        logger.error(f"Delete plate error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/images')
def images():
    try:
        with get_db_connection() as conn:
            plates = conn.execute('SELECT * FROM plates ORDER BY timestamp DESC').fetchall()
        return render_template('images.html', plates=plates)
    except Exception as e:
        logger.error(f"Images error: {str(e)}")
        return render_template('images.html', plates=[])

def handle_plate_detection(plate_number, frame, x, y, current_time):
    country_code = detect_country_code(plate_number)
    country_name = COUNTRY_CODES.get(country_code, 'Unknown')
    
    # Update tracking
    with camera_handler.lock:  # Use the lock to ensure thread safety
        if plate_number not in camera_handler.plate_tracking:
            camera_handler.plate_tracking[plate_number] = {
                'first_seen': current_time,
                'last_seen': current_time,
                'alert_sent': False
            }
        else:
            camera_handler.plate_tracking[plate_number]['last_seen'] = current_time

    # Update display and database
    if last_detection.get('plate_number') != plate_number:
        timestamp_str = current_time.strftime("%Y-%m-%d_%H-%M-%S")
        img_path = os.path.join('web_output', f'original_{timestamp_str}_{plate_number}.png')
        
        try:
            cv2.imwrite(img_path, frame)
            with get_db_connection() as conn:
                conn.execute('''
                    INSERT INTO plates 
                    (plate_number, country_code, original_image_path, street, city, country)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (plate_number, country_code, img_path,
                      current_location['street'], current_location['city'], country_name))
                conn.commit()
                
            last_detection.update({
                'plate_number': plate_number,
                'timestamp': current_time,
                'detection_time': timestamp_str,
                'country': country_name,
                'street': current_location['street'],
                'city': current_location['city']
            })
            
        except Exception as e:
            logger.error(f"Detection handling error: {str(e)}")

    # Draw detection info
    cv2.putText(frame, f"{plate_number} ({country_name})", 
               (x, y-25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
    cv2.putText(frame, f"{current_location['street']}, {current_location['city']}",
               (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

@app.route('/check_prolonged_detection')
def check_prolonged_detection():
    try:
        current_time = datetime.now()
        alerts = []
        
        with camera_handler.lock:  # Use the lock to ensure thread safety
            # Remove old entries older than 1 hour
            to_delete = [p for p, data in camera_handler.plate_tracking.items() 
                        if (current_time - data['last_seen']).total_seconds() > 3600]
            
            for plate in to_delete:
                del camera_handler.plate_tracking[plate]
            
            # Check for prolonged presence
            for plate, data in camera_handler.plate_tracking.items():
                if data['alert_sent']:
                    continue
                
                duration = (current_time - data['first_seen']).total_seconds()
                if duration > 300:  # 5 minutes
                    alerts.append({
                        'plate': plate,
                        'first_seen': data['first_seen'].isoformat(),
                        'duration': duration
                    })
                    data['alert_sent'] = True

        return jsonify({
            'alert': bool(alerts),
            'plates': alerts,
            'timestamp': current_time.isoformat()
        })
    
    except Exception as e:
        logger.error(f"Prolonged detection error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/start_camera', methods=['POST'])
def start_camera():
    if camera_handler.initialize(camera_index=0):
        camera_handler.is_running = True
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Camera initialization failed'}), 500

@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    camera_handler.release()
    return jsonify({'status': 'success'})

@atexit.register
def cleanup():
    camera_handler.release()
    
    
# Add this route for statistics
@app.route('/get_stats')
def get_stats():
    try:
        with get_db_connection() as conn:
            stats = {
                "total_detections": conn.execute('SELECT COUNT(*) FROM plates').fetchone()[0],
                "unique_plates": conn.execute('SELECT COUNT(DISTINCT plate_number) FROM plates').fetchone()[0],
                "top_plates": [],
                "hour_distribution": []
            }

            # Get top 5 plates
            top_plates = conn.execute('''
                SELECT plate_number, COUNT(*) as count 
                FROM plates 
                GROUP BY plate_number 
                ORDER BY count DESC 
                LIMIT 5
            ''').fetchall()
            
            stats['top_plates'] = [dict(row) for row in top_plates]

            # Get hour distribution
            hour_dist = conn.execute('''
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM plates
                GROUP BY hour
                ORDER BY hour
            ''').fetchall()
            
            stats['hour_distribution'] = [dict(row) for row in hour_dist]

        return jsonify(stats)
    
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# Fix the search route
@app.route('/search', methods=['GET', 'POST'])
def search_images():
    plates = []
    search_query = request.form.get('search', '')
    search_type = request.form.get('search_type', 'plate')

    try:
        with get_db_connection() as conn:
            if search_type == 'plate':
                plates = conn.execute('''
                    SELECT * FROM plates 
                    WHERE plate_number LIKE ? 
                    ORDER BY timestamp DESC
                ''', (f'%{search_query}%',)).fetchall()
            
            elif search_type == 'time':
                plates = conn.execute('''
                    SELECT * FROM plates 
                    WHERE strftime('%H:%M', timestamp) LIKE ?
                    ORDER BY timestamp DESC
                ''', (f'%{search_query}%',)).fetchall()
            
            elif search_type == 'location':
                plates = conn.execute('''
                    SELECT * FROM plates 
                    WHERE street LIKE ? OR city LIKE ? OR country LIKE ?
                    ORDER BY timestamp DESC
                ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%')).fetchall()

    except Exception as e:
        logger.error(f"Search error: {str(e)}")
    
    return render_template('images.html', 
                         plates=plates,
                         search_query=search_query,
                         search_type=search_type)

if __name__ == '__main__':
    init_db()
    os.makedirs('web_output/originals', exist_ok=True)
    
    # Start background services
    if camera_handler.initialize(camera_index=0):
        video_thread = threading.Thread(target=process_video, daemon=True)
        video_thread.start()
        logger.info("Camera processing started")
    else:
        logger.error("Failed to initialize camera")
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)