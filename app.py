import cv2
import numpy as np
import pytesseract
import re
import os
from flask import Flask, render_template, Response, send_from_directory, request
from flask_socketio import SocketIO
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app)

# Define the camera status variable
camera_active = False

# Load the Haar cascade for Russian plate numbers
plate_cascade = cv2.CascadeClassifier("C://Users/Trimi/Lic/haarcascade_russian_plate_number.xml")

# Define the paths for saving images
output_folder = 'web_output/'
originals_folder = os.path.join(output_folder, 'originals')
blackwhite_folder = os.path.join(output_folder, 'blackwhite')

os.makedirs(output_folder, exist_ok=True)
os.makedirs(originals_folder, exist_ok=True)
os.makedirs(blackwhite_folder, exist_ok=True)

# Connect to the webcam
cap = cv2.VideoCapture(0)  # Use 0 for the first camera (change if you have multiple cameras)

# Create a font for text overlay
font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.6
font_thickness = 2

def process_video():
    while True:
        ret, frame = cap.read()  # Capture a frame from the webcam

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detect plates in the frame
        plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        # Check if a possible license plate is detected
        if len(plates) > 0:
            for (x, y, w, h) in plates:
                # Draw a rectangle around the plate
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

                # Extract the region of interest (ROI) which is the detected license plate
                plate_roi = gray[y:y+h, x:x+w]

                # Apply pytesseract to read the text from the license plate ROI
                img_thresh = cv2.adaptiveThreshold(
                    plate_roi,
                    maxValue=255.0,
                    adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    thresholdType=cv2.THRESH_BINARY_INV,
                    blockSize=19,
                    C=9
                )
                text = pytesseract.image_to_string(img_thresh)

                if text:
                    print("License plate detected:", text)

                    # Get the current date and time for image filenames
                    current_datetime = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

                    # Save the original image
                    original_image_filename = os.path.join(originals_folder, f'original_{current_datetime}.png')
                    cv2.imwrite(original_image_filename, frame)

                    # Save the black and white image
                    bw_image_filename = os.path.join(blackwhite_folder, f'bw_{current_datetime}.png')
                    cv2.imwrite(bw_image_filename, img_thresh)

                    # Display the recognized text on the webcam feed
                    cv2.putText(frame, text, (x, y - 10), font, font_scale, (0, 0, 255), font_thickness)

        # Encode the frame as JPEG
        ret, jpeg_frame = cv2.imencode('.jpg', frame)
        frame_bytes = jpeg_frame.tobytes()

        # Emit the frame to the WebSocket clients
        socketio.emit('video_feed', {'frame': frame_bytes}, namespace='/video')

        yield (b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect', namespace='/video')
def test_connect():
    print("Client Connected")

@socketio.on('disconnect', namespace='/video')
def test_disconnect():
    print("Client Disconnected")

@app.route('/video_feed')
def video_feed():
    return Response(process_video(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/images')
def images():
    refresh = request.args.get('refresh')
    if refresh and refresh.lower() == 'true':
        # Clear the search by resetting the session variable
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
        # Handle invalid folder name here, e.g., return a 404 error.
        return "Invalid folder", 404





@app.route('/search', methods=['POST'])
def search_images():
    datetime_query = request.form['datetime']
    original_images = os.listdir(originals_folder)
    bw_images = os.listdir(blackwhite_folder)


    # Filter images based on the datetime_query
    filtered_originals = [filename for filename in original_images if filename.startswith(f'original_{datetime_query}')]
    filtered_bw = [filename for filename in bw_images if filename.startswith(f'bw_{datetime_query}')]

    return render_template('images.html', original_images=filtered_originals, bw_images=filtered_bw)




if __name__ == '__main__':
    socketio.run(app, debug=True)