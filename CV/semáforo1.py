import numpy as np
from ultralytics import YOLO
import cv2
import cvzone
import time
from collections import deque
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
import os

# Firebase initialization
def initialize_firebase():
    """Initialize Firebase - update paths and URL for your local setup"""
    try:
        # Update this path to your local service account key file
        firebase_key_path = "firebaseKey.json"  # Put this in your project directory
        
        if not os.path.exists(firebase_key_path):
            print("Warning: Firebase key not found. Firebase logging disabled.")
            return False
            
        cred = credentials.Certificate(firebase_key_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://projetedb-2224f-default-rtdb.firebaseio.com/'  # Replace with your Firebase URL
        })
        print("Firebase initialized successfully")
        return True
    except Exception as e:
        print(f"Firebase initialization failed: {e}")
        return False

# Initialize Firebase
firebase_enabled = initialize_firebase()

# Create session ID for this detection run
session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")

# Video source - update these paths for your local setup
VIDEO_PATH = "cars.mp4"  # Put your video file in the project directory
MASK_PATH = "mask-950x480.png"  # Optional mask file
GRAPHICS_PATH = "graphics.png"  # Optional graphics overlay

# Check if video file exists
if not os.path.exists(VIDEO_PATH):
    print(f"Error: Video file '{VIDEO_PATH}' not found!")
    print("Please place your video file in the same directory as this script")
    exit()

cap = cv2.VideoCapture(VIDEO_PATH)

# Check if video opened successfully
if not cap.isOpened():
    print("Error: Could not open video file")
    exit()

# Frame skip configuration
FRAME_SKIP = 2
frame_count = 0

# Firebase logging configuration
FIREBASE_UPDATE_INTERVAL = 5  # Send data every 5 seconds
last_firebase_update = 0

# Load YOLO model - it will download automatically if not present
print("Loading YOLO model...")
model = YOLO("yolov8l.pt")  # Will download if not present
print("YOLO model loaded successfully")

# Only vehicle classes we care about
VEHICLE_CLASSES = {"car": 2, "motorbike": 3, "bus": 5, "truck": 7}

# Load images (optional - will skip if not found)
mask = None
imgGraphics = None

if os.path.exists(MASK_PATH):
    mask = cv2.imread(MASK_PATH)
    print("Mask loaded successfully")
else:
    print(f"Warning: Mask file '{MASK_PATH}' not found - continuing without mask")

if os.path.exists(GRAPHICS_PATH):
    imgGraphics = cv2.imread(GRAPHICS_PATH, cv2.IMREAD_UNCHANGED)
    print("Graphics overlay loaded successfully")
else:
    print(f"Warning: Graphics file '{GRAPHICS_PATH}' not found - continuing without graphics overlay")

# Counting line - you may need to adjust these coordinates based on your video
limits = [400, 297, 673, 297]
totalCount = []

# Rolling average (30 seconds)
WINDOW_SIZE = 30
detection_history = deque()

def euclidean_distance(a, b):
    return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

def update_rolling_average(current_count):
    current_time = time.time()
    detection_history.append((current_time, current_count))

    # Remove old entries
    while detection_history and (current_time - detection_history[0][0]) > WINDOW_SIZE:
        detection_history.popleft()

    return sum(count for _, count in detection_history) / len(detection_history) if detection_history else 0.0

def send_to_firebase(total_crossed, current_cars, avg_cars):
    """Send detection data to Firebase"""
    if not firebase_enabled:
        return
        
    try:
        ref = db.reference(f'/car_detection/{session_id}')
        data = {
            'timestamp': int(time.time()),
            'datetime': datetime.now().isoformat(),
            'total_count': total_crossed,
            'current_cars': current_cars,
            'rolling_average': round(avg_cars, 2)
        }
        # Push data (creates unique key) or set with timestamp
        ref.child(str(int(time.time()))).set(data)
        print(f"Data sent to Firebase: {data}")
    except Exception as e:
        print(f"Firebase error: {e}")

# Tracking variables
tracked_objects = {}
next_id = 0
MAX_DISTANCE = 50

print("Starting video processing...")
print("Press 'q' to quit")

# Get video properties for display
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Video: {fps:.1f} FPS, {total_frames} frames")

start_time = time.time()
processed_frames = 0

while True:
    success, img = cap.read()
    if not success:
        print("End of video reached")
        break

    frame_count += 1
    if frame_count % FRAME_SKIP != 0:
        continue
    
    processed_frames += 1

    # Apply mask if available
    if mask is not None:
        mask_resized = cv2.resize(mask, (img.shape[1], img.shape[0]))
        if len(mask_resized.shape) == 3:
            imgRegion = cv2.bitwise_and(img, mask_resized)
        else:
            mask_resized = cv2.cvtColor(mask_resized, cv2.COLOR_GRAY2BGR)
            imgRegion = cv2.bitwise_and(img, mask_resized)
    else:
        imgRegion = img.copy()

    # Overlay graphics if available
    if imgGraphics is not None:
        img = cvzone.overlayPNG(img, imgGraphics, (0, 0))

    # Run detection
    results = model(imgRegion, stream=True)
    current_detections = []

    for r in results:
        boxes = r.boxes
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls = int(box.cls[0])

            # Filter for vehicles with good confidence
            if cls in VEHICLE_CLASSES.values() and conf > 0.3:
                w, h = x2 - x1, y2 - y1
                cx, cy = x1 + w // 2, y1 + h // 2
                current_detections.append((cx, cy, x1, y1, w, h, conf))

    # Update rolling average
    avg_cars = update_rolling_average(len(current_detections))

    # Update tracking
    new_tracked_objects = {}
    used_ids = set()

    for cx, cy, x1, y1, w, h, conf in current_detections:
        best_id = None
        min_dist = MAX_DISTANCE

        # Find closest existing object
        for obj_id, (prev_cx, prev_cy) in tracked_objects.items():
            if obj_id not in used_ids:
                dist = euclidean_distance((cx, cy), (prev_cx, prev_cy))
                if dist < min_dist:
                    best_id = obj_id
                    min_dist = dist

        # Assign new ID if no match found
        if best_id is None:
            best_id = next_id
            next_id += 1

        new_tracked_objects[best_id] = (cx, cy)
        used_ids.add(best_id)

        # Draw detection with confidence
        cvzone.cornerRect(img, (x1, y1, w, h), l=9, rt=2, colorR=(255, 0, 255))
        cvzone.putTextRect(img, f'{conf:.2f}', (max(0, x1), max(35, y1)),
                          scale=2, thickness=3, offset=10)

        # Check line crossing for counting
        if limits[0] < cx < limits[2] and limits[1] - 15 < cy < limits[1] + 15:
            if best_id not in totalCount:
                totalCount.append(best_id)
                cv2.line(img, (limits[0], limits[1]), (limits[2], limits[3]), (0, 255, 0), 5)

    tracked_objects = new_tracked_objects

    # Draw counting line and display counts
    cv2.line(img, (limits[0], limits[1]), (limits[2], limits[3]), (0, 0, 255), 5)
    cv2.putText(img, str(len(totalCount)), (255, 100), cv2.FONT_HERSHEY_PLAIN, 5, (50, 50, 255), 8)
    cv2.putText(img, f'Current: {len(current_detections)}', (50, 150), cv2.FONT_HERSHEY_PLAIN, 3, (0, 255, 0), 3)
    cv2.putText(img, f'Avg (30s): {avg_cars:.1f}', (50, 200), cv2.FONT_HERSHEY_PLAIN, 3, (255, 255, 0), 3)

    # Display FPS information
    if processed_frames > 0:
        elapsed_time = time.time() - start_time
        processing_fps = processed_frames / elapsed_time
        cv2.putText(img, f'FPS: {processing_fps:.1f}', (50, 50), cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 2)

    # Send data to Firebase every FIREBASE_UPDATE_INTERVAL seconds
    current_time = time.time()
    if current_time - last_firebase_update >= FIREBASE_UPDATE_INTERVAL:
        send_to_firebase(len(totalCount), len(current_detections), avg_cars)
        last_firebase_update = current_time

    # Display the frame - replaced cv2_imshow with cv2.imshow for local use
    cv2.imshow('Car Detection', img)
    
    # Check for 'q' key press to quit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Quitting...")
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()

# Final Firebase update
if firebase_enabled:
    send_to_firebase(len(totalCount), len(current_detections), avg_cars)

print(f"\nProcessing complete!")
print(f"Total cars counted: {len(totalCount)}")
print(f"Frames processed: {processed_frames}")
if processed_frames > 0:
    elapsed_time = time.time() - start_time
    print(f"Average processing FPS: {processed_frames/elapsed_time:.1f}")
