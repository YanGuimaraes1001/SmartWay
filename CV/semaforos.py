import numpy as np
from ultralytics import YOLO
import cv2
import time
from collections import deque
from datetime import datetime
import psycopg2
import os
import firebase_admin
from firebase_admin import credentials, db
from threading import Thread, Lock
import paho.mqtt.client as mqtt
import json
import re

# ==================== CONFIGURATION ====================

USE_FIREBASE = False

# MQTT Configuration
MQTT_CONFIG = {
    'broker': '192.168.0.9',  # Change to your MQTT broker address
    'port': 1883,
    'topic': '3105/confirmacao',
    'client_id': 'traffic_lane_detector'
}

# Standard resolution for all videos and masks
STANDARD_WIDTH = 640
STANDARD_HEIGHT = 480

# Lane configurations - easily add or remove lanes
# Map lane_id to traffic light letter (A, B, C, D)
LANES_CONFIG = [
    {
        'lane_id': 'lane_1',
        'traffic_letter': 'A',  # Maps to letter A in MQTT message
        'video_path': 'carioca.mp4',
        'mask_path': 'carioca2.png',
        'limits': [200, 297, 650, 297],
        'window_position': (0, 0)
    },
    {
        'lane_id': 'lane_2',
        'traffic_letter': 'B',
        'video_path': 'iei1.mp4',
        'mask_path': 'iei2.png',
        'limits': [100, 297, 350, 297],
        'window_position': (650, 0)
    },
    {
        'lane_id': 'lane_3',
        'traffic_letter': 'C',
        'video_path': 'joseph.mp4',
        'mask_path': 'joseph2.png',
        'limits': [100, 297, 650, 297],
        'window_position': (0, 450)
    },
    {
        'lane_id': 'lane_4',
        'traffic_letter': 'D',
        'video_path': 'julioiei1.mp4',
        'mask_path': 'julioiei2.png',
        'limits': [100, 240, 350, 240],
        'window_position': (650, 450)
    }
]

DB_CONFIG = {
    'host': 'localhost',
    'database': 'car_detection',
    'user': 'projete',
    'password': '12345678',
    'port': 5432
}

FIREBASE_CONFIG = {
    'key_path': 'chaveFirebase.json',
    'database_url': 'https://projetedb-2224f-default-rtdb.firebaseio.com/'
}

# Detection parameters
VEHICLE_CLASSES = {2, 3, 5, 7}  # car, motorcycle, bus, truck
FRAME_SKIP = 1
DATABASE_UPDATE_INTERVAL = 3
WINDOW_SIZE = 20
MAX_DISTANCE = 60
CONF_THRESHOLD = 0.25

# ==================== TRAFFIC LIGHT CONTROLLER ====================

class TrafficLightController:
    def __init__(self):
        self.traffic_states = {}  # {letter: {'status': 'RED'/'GREEN', 'duration': time}}
        self.lock = Lock()
        self.mqtt_client = None
        self.connected = False
        
    def initialize_mqtt(self):
        try:
            self.mqtt_client = mqtt.Client(client_id=MQTT_CONFIG['client_id'])
            self.mqtt_client.on_connect = self.on_connect
            self.mqtt_client.on_message = self.on_message
            self.mqtt_client.on_disconnect = self.on_disconnect
            
            print(f"Connecting to MQTT broker at {MQTT_CONFIG['broker']}:{MQTT_CONFIG['port']}...")
            self.mqtt_client.connect(MQTT_CONFIG['broker'], MQTT_CONFIG['port'], 60)
            self.mqtt_client.loop_start()
            
            # Wait a bit for connection
            time.sleep(2)
            return True
        except Exception as e:
            print(f"❌ MQTT connection failed: {e}")
            print("⚠️  Continuing without MQTT (all lanes will run)")
            return False
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ Connected to MQTT broker")
            client.subscribe(MQTT_CONFIG['topic'])
            print(f"📡 Subscribed to topic: {MQTT_CONFIG['topic']}")
            self.connected = True
        else:
            print(f"❌ Failed to connect to MQTT, return code {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        print(f"⚠️  Disconnected from MQTT broker (code: {rc})")
        self.connected = False
    
    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8').strip()
            print(f"\n📨 MQTT Message received: {payload}")
            self.parse_traffic_status(payload)
        except Exception as e:
            print(f"❌ Error processing MQTT message: {e}")
    
    def parse_traffic_status(self, message):
        """
        Parse traffic light status from individual messages:
        Each message contains status for ONE lane:
        - '{"A": 10.00}' = Lane A green for 10 seconds
        - 'B' or '"B"' = Lane B red
        """
        with self.lock:
            if not self.traffic_states:
                # Set all lanes to RED initially
                for config in LANES_CONFIG:
                    letter = config['traffic_letter']
                    self.traffic_states[letter] = {'status': 'RED', 'duration': 0}
            
            message = message.strip()
            
            # Check if it's a JSON object (green light with duration)
            if message.startswith('{'):
                try:
                    data = json.loads(message)
                    for letter, duration in data.items():
                        letter = letter.strip().upper()
                        self.traffic_states[letter] = {'status': 'GREEN', 'duration': float(duration)}
                        print(f"🟢 Lane {letter}: GREEN for {duration}s")
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse JSON: {e}")
            # It's a simple letter (red light)
            else:
                # Remove quotes if present
                letter = message.strip('"\'').strip().upper()
                if letter.isalpha() and len(letter) == 1:
                    self.traffic_states[letter] = {'status': 'RED', 'duration': 0}
                    print(f"🔴 Lane {letter}: RED")
            
            # Show current state of all lanes
            status_summary = ", ".join([f"{k}:{v['status'][0]}" for k, v in sorted(self.traffic_states.items())])
            print(f"📊 Current state: [{status_summary}]\n")
    
    def is_green(self, traffic_letter):
        """Check if a lane's traffic light is green"""
        with self.lock:
            if not self.traffic_states:
                # If no MQTT data yet, keep lanes stopped (waiting for traffic control)
                return False
            
            state = self.traffic_states.get(traffic_letter, {'status': 'RED'})
            return state.get('status') == 'GREEN'
    
    def get_status(self, traffic_letter):
        """Get current status and duration for a lane"""
        with self.lock:
            return self.traffic_states.get(traffic_letter, {'status': 'UNKNOWN', 'duration': 0})
    
    def cleanup(self):
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            print("🔌 MQTT client disconnected")

# Global traffic controller
traffic_controller = TrafficLightController()

# ==================== DATABASE FUNCTIONS ====================

database_enabled = False
db_lock = Lock()

def initialize_database():
    global database_enabled
    if USE_FIREBASE:
        database_enabled = initialize_firebase()
    else:
        database_enabled = initialize_postgresql()
    return database_enabled

def initialize_postgresql():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        print("✅ Connected to PostgreSQL successfully")
        return True
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False

def initialize_firebase():
    try:
        firebase_key_path = FIREBASE_CONFIG['key_path']
        if not os.path.exists(firebase_key_path):
            print("❌ Firebase key not found. Logging disabled.")
            return False
        cred = credentials.Certificate(firebase_key_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': FIREBASE_CONFIG['database_url']
        })
        print("✅ Firebase initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        return False

def send_to_database(lane_id, total, current_cars, avg):
    if not database_enabled:
        return
    with db_lock:
        if USE_FIREBASE:
            send_to_firebase(lane_id, total, current_cars, avg)
        else:
            send_to_postgresql(lane_id, total, current_cars, avg)

def send_to_postgresql(lane_id, total, current_cars, avg):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO veiculos (lane_id, current_cars, rolling_average, total_count, timestamp) 
        VALUES (%s, %s, %s, %s, NOW())
        RETURNING id, timestamp"""
        avg = min(max(avg, 0.0), 999.99)
        cursor.execute(insert_query, (lane_id, current_cars, avg, total))
        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        if result:
            print(f"✓ [PostgreSQL] [{lane_id}] Written: ID={result[0]}, Time={result[1]}")
        return True
    except Exception as e:
        print(f"❌ [PostgreSQL] [{lane_id}] Error: {e}")
        return False

def ensure_database_schema():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        required_columns = {
            'id': "integer NOT NULL DEFAULT nextval('veiculos_id_seq'::regclass)",
            'timestamp': 'timestamp DEFAULT CURRENT_TIMESTAMP',
            'current_cars': 'integer NOT NULL',
            'rolling_average': 'numeric(5,2) NOT NULL',
            'total_count': 'integer NOT NULL',
            'lane_id': 'character varying(20)',
        }
        
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'veiculos'
        """)
        
        existing_columns = {row[0]: row for row in cursor.fetchall()}
        
        for col, col_def in required_columns.items():
            if col not in existing_columns:
                print(f"Adding column {col} to veiculos table...")
                cursor.execute(f"ALTER TABLE veiculos ADD COLUMN {col} {col_def}")
                conn.commit()
                print(f"✓ Column {col} added")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error ensuring schema: {e}")
        return False

def send_to_firebase(lane_id, total_crossed, current_cars, avg_cars):
    try:
        if not hasattr(send_to_firebase, 'session_ids'):
            send_to_firebase.session_ids = {}
        if lane_id not in send_to_firebase.session_ids:
            send_to_firebase.session_ids[lane_id] = f"session_{int(time.time())}"
        
        ref = db.reference(f'/car_detection/{lane_id}/{send_to_firebase.session_ids[lane_id]}')
        data = {
            'timestamp': int(time.time()),
            'datetime': datetime.now().isoformat(),
            'lane_id': lane_id,
            'total_count': total_crossed,
            'current_cars': current_cars,
            'rolling_average': round(avg_cars, 2)
        }
        ref.child(str(int(time.time()))).set(data)
    except Exception as e:
        print(f"❌ [Firebase] [{lane_id}] Error: {e}")

# ==================== LANE DETECTOR CLASS ====================

class LaneDetector:
    def __init__(self, config, model, traffic_controller):
        self.lane_id = config['lane_id']
        self.traffic_letter = config['traffic_letter']
        self.video_path = config['video_path']
        self.mask_path = config['mask_path']
        self.limits = config['limits']
        self.window_position = config['window_position']
        self.window_name = f'Lane {self.traffic_letter}: {self.lane_id}'
        
        self.model = model
        self.traffic_controller = traffic_controller
        self.cap = None
        self.mask = None
        self.running = False
        self.paused = False
        
        # Tracking variables
        self.tracked_objects = {}
        self.next_id = 0
        self.total_count = []
        self.detection_history = deque()
        
        # Performance tracking
        self.frame_count = 0
        self.processed_frames = 0
        self.start_time = time.time()
        self.last_database_update = 0
        
        # Store last frame for display when paused
        self.last_frame = None
        
    def initialize(self):
        if not os.path.exists(self.video_path):
            print(f"❌ [{self.lane_id}] Video '{self.video_path}' not found!")
            return False
        
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            print(f"❌ [{self.lane_id}] Could not open video")
            return False
        
        if os.path.exists(self.mask_path):
            self.mask = cv2.imread(self.mask_path)
            self.mask = cv2.resize(self.mask, (STANDARD_WIDTH, STANDARD_HEIGHT))
            print(f"✅ [{self.lane_id}] Mask loaded and resized to {STANDARD_WIDTH}x{STANDARD_HEIGHT}")
        else:
            print(f"⚠️  [{self.lane_id}] No mask found - continuing without mask")
        
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, STANDARD_WIDTH, STANDARD_HEIGHT)
        cv2.moveWindow(self.window_name, *self.window_position)
        
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"✅ [{self.lane_id}] (Lane {self.traffic_letter}) Initialized: {fps:.1f} FPS, {total_frames} frames")
        
        self.running = True
        return True
    
    def euclidean_distance(self, a, b):
        return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
    
    def update_rolling_average(self, current_count):
        current_time = time.time()
        self.detection_history.append((current_time, current_count))
        cutoff_time = current_time - WINDOW_SIZE
        while self.detection_history and self.detection_history[0][0] < cutoff_time:
            self.detection_history.popleft()
        return sum(count for _, count in self.detection_history) / len(self.detection_history) if self.detection_history else 0.0
    
    def process_frame(self):
        # Check traffic light status
        is_green = self.traffic_controller.is_green(self.traffic_letter)
        traffic_status = self.traffic_controller.get_status(self.traffic_letter)
        
        # If red light, pause video and display last frame with status
        if not is_green:
            if self.last_frame is not None:
                display_frame = self.last_frame.copy()
            else:
                # No frame yet - read one frame to initialize
                success, frame = self.cap.read()
                if success:
                    frame = cv2.resize(frame, (STANDARD_WIDTH, STANDARD_HEIGHT))
                    display_frame = frame.copy()
                    self.last_frame = frame.copy()
                    # Move back one frame so we can resume from here
                    current_pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, current_pos - 1))
                else:
                    # Create blank frame if video can't be read
                    display_frame = np.zeros((STANDARD_HEIGHT, STANDARD_WIDTH, 3), dtype=np.uint8)
            
            # Add RED overlay
            overlay = display_frame.copy()
            cv2.rectangle(overlay, (0, 0), (display_frame.shape[1], display_frame.shape[0]), 
                         (0, 0, 255), -1)
            cv2.addWeighted(overlay, 0.2, display_frame, 0.8, 0, display_frame)
            
            # Determine message
            if traffic_status['status'] == 'UNKNOWN':
                status_msg = '⏳ WAITING FOR TRAFFIC CONTROL'
            else:
                status_msg = '🔴 RED LIGHT - STOPPED'
            
            # Add status text
            text_size = cv2.getTextSize(status_msg, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 3)[0]
            text_x = (display_frame.shape[1] - text_size[0]) // 2
            text_y = display_frame.shape[0] // 2
            cv2.putText(display_frame, status_msg, (text_x, text_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
            cv2.putText(display_frame, f'Lane {self.traffic_letter}', (50, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            
            # Show stats even when paused
            cv2.putText(display_frame, f'Total: {len(self.total_count)}', (50, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
            
            cv2.imshow(self.window_name, display_frame)
            self.paused = True
            return True
        
        # Transitioning from RED to GREEN - mark as no longer paused
        if self.paused:
            print(f"🟢 [{self.lane_id}] Traffic light turned GREEN - resuming video")
            self.paused = False
        
        # GREEN LIGHT - Process video normally
        success, img = self.cap.read()
        if not success:
            print(f"[{self.lane_id}] Video ended - restarting...")
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.frame_count = 0
            return True
        
        img = cv2.resize(img, (STANDARD_WIDTH, STANDARD_HEIGHT))
        
        self.frame_count += 1
        if self.frame_count % FRAME_SKIP != 0:
            self.last_frame = img.copy()
            return True
        
        self.processed_frames += 1
        
        # Apply mask if available
        if self.mask is not None:
            imgRegion = cv2.bitwise_and(img, self.mask)
        else:
            imgRegion = img.copy()
        
        # Run detection
        results = self.model(imgRegion, stream=False, verbose=False)
        current_detections = []
        
        if results and len(results) > 0:
            r = results[0]
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    
                    if cls in VEHICLE_CLASSES and conf > CONF_THRESHOLD:
                        w, h = x2 - x1, y2 - y1
                        cx, cy = x1 + w // 2, y1 + h // 2
                        current_detections.append((cx, cy, x1, y1, w, h, conf))
        
        # Update rolling average
        avg_cars = self.update_rolling_average(len(current_detections))
        
        # Object tracking
        new_tracked_objects = {}
        used_ids = set()
        
        for cx, cy, x1, y1, w, h, conf in current_detections:
            best_id = None
            min_dist = MAX_DISTANCE
            
            for obj_id, (prev_cx, prev_cy) in self.tracked_objects.items():
                if obj_id not in used_ids:
                    dist = self.euclidean_distance((cx, cy), (prev_cx, prev_cy))
                    if dist < min_dist:
                        best_id = obj_id
                        min_dist = dist
            
            if best_id is None:
                best_id = self.next_id
                self.next_id += 1
            
            new_tracked_objects[best_id] = (cx, cy)
            used_ids.add(best_id)
            
            # Draw detection
            x2, y2 = x1 + w, y1 + h
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 2)
            cv2.putText(img, f'{conf:.2f}', (x1, max(35, y1)), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Line crossing detection
            if self.limits[0] < cx < self.limits[2] and self.limits[1] - 15 < cy < self.limits[1] + 15:
                if best_id not in self.total_count:
                    self.total_count.append(best_id)
                    cv2.line(img, (self.limits[0], self.limits[1]), 
                            (self.limits[2], self.limits[3]), (0, 255, 0), 5)
        
        self.tracked_objects = new_tracked_objects
        
        # Draw counting line
        cv2.line(img, (self.limits[0], self.limits[1]), 
                (self.limits[2], self.limits[3]), (0, 0, 255), 3)
        
        # Display information with traffic light status
        status_color = (0, 255, 0) if traffic_status['status'] == 'GREEN' else (0, 0, 255)
        status_text = f"🟢 GREEN" if traffic_status['status'] == 'GREEN' else "🔴 RED"
        
        cv2.putText(img, f'Lane {self.traffic_letter} - {status_text}', (50, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        cv2.putText(img, f'Total: {len(self.total_count)}', (50, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(img, f'Current: {len(current_detections)}', (50, 85), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(img, f'Avg: {avg_cars:.1f}', (50, 110), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        if self.processed_frames > 0:
            elapsed = time.time() - self.start_time
            fps = self.processed_frames / elapsed
            cv2.putText(img, f'FPS: {fps:.1f}', (50, 135), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Add green duration if available
        if traffic_status['status'] == 'GREEN' and traffic_status['duration'] > 0:
            cv2.putText(img, f"Duration: {traffic_status['duration']:.1f}s", (50, 160), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Database update (only when green)
        current_time = time.time()
        if current_time - self.last_database_update >= DATABASE_UPDATE_INTERVAL:
            send_to_database(self.lane_id, len(self.total_count), len(current_detections), avg_cars)
            self.last_database_update = current_time
        
        # Store frame and display
        self.last_frame = img.copy()
        cv2.imshow(self.window_name, img)
        
        return True
    
    def cleanup(self):
        if self.cap:
            self.cap.release()
        cv2.destroyWindow(self.window_name)
        print(f"[{self.lane_id}] Cleanup complete. Total cars: {len(self.total_count)}, Frames: {self.processed_frames}")

# ==================== MAIN PROGRAM ====================

def main():
    print("=" * 60)
    print("MULTI-LANE CAR DETECTION WITH TRAFFIC LIGHT CONTROL")
    print("=" * 60)
    print(f"Database: {'Firebase' if USE_FIREBASE else 'PostgreSQL'}")
    print(f"Lanes: {len(LANES_CONFIG)}")
    print(f"MQTT Topic: {MQTT_CONFIG['topic']}")
    print(f"Standard Resolution: {STANDARD_WIDTH}x{STANDARD_HEIGHT}")
    print("=" * 60)
    
    # Initialize MQTT traffic controller
    print("\n🚦 Initializing traffic light controller...")
    traffic_controller.initialize_mqtt()
    
    # Initialize database
    initialize_database()
    
    if database_enabled:
        ensure_database_schema()
    
    # Load YOLO model once
    print("\nLoading YOLO model...")
    model = YOLO("yolov8n.pt")
    print("✅ YOLO model loaded\n")
    
    # Initialize all lanes
    lanes = []
    for config in LANES_CONFIG:
        lane = LaneDetector(config, model, traffic_controller)
        if lane.initialize():
            lanes.append(lane)
        else:
            print(f"❌ Failed to initialize {config['lane_id']}")
    
    if not lanes:
        print("❌ No lanes initialized. Exiting.")
        return
    
    print(f"\n✅ {len(lanes)} lane(s) running")
    print("🚦 Waiting for MQTT traffic light commands...")
    print("Press 'q' or ESC in any window to exit\n")
    
    # Main processing loop
    try:
        while True:
            all_ok = True
            for lane in lanes:
                if not lane.process_frame():
                    all_ok = False
            
            if not all_ok:
                break
            
            # Check for quit command
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                print("\nExiting...")
                break
            
            # Check if any window was closed
            window_closed = False
            for lane in lanes:
                if cv2.getWindowProperty(lane.window_name, cv2.WND_PROP_VISIBLE) < 1:
                    window_closed = True
                    break
            if window_closed:
                print("\nWindow closed by user")
                break
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print("\nCleaning up...")
        for lane in lanes:
            lane.cleanup()
        traffic_controller.cleanup()
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        print("\n✅ All systems stopped successfully")

if __name__ == "__main__":
    main()
