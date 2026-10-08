import cv2
from ultralytics import YOLO
import serial
import time

# -------- ZONE STATE --------
zone_state = {
    "A": "LOW",
    "B": "LOW",
    "C": "LOW",
    "D": "LOW"
}

zone_history = {
    "A": 0,
    "B": 0,
    "C": 0,
    "D": 0
}

VIDEO_PATH = "your_video.mp4"
model = YOLO("yolov8n.pt")

choice = input("Enter 1 for Webcam, 2 for Video: ").strip()

if choice == "1":
    webcamera = cv2.VideoCapture(0)
else:
    webcamera = cv2.VideoCapture(VIDEO_PATH)

THRESHOLD = 4
HIGH_CONFIRM = 2 # frames before confirming HIGH

try:
    ard = serial.Serial(port='COM5', baudrate=115200, timeout=0.1)
    time.sleep(2)  # Let ESP32 finish boot/reset
    print("Serial connected.")
except Exception as e:
    print(f"Serial error: {e}")
    exit()

last_sent = ""
last_sent_time = 0
SEND_INTERVAL = 0.5
high_counter = 0

# -------- DENSITY HELPERS --------

def get_stable_density(zone, value):
    prev = zone_state[zone]

    if value > 0.30:
        zone_state[zone] = "HIGH"
    elif value > 0.18:
        if prev == "HIGH" and value > 0.25:
            zone_state[zone] = "HIGH"
        else:
            zone_state[zone] = "MEDIUM"
    else:
        if prev == "MEDIUM" and value > 0.15:
            zone_state[zone] = "MEDIUM"
        else:
            zone_state[zone] = "LOW"

    return zone_state[zone]

def smooth_int(old, new):
    return int(0.7 * old + 0.3 * new)

def smooth_float(old, new):
    return new if old == 0 else (0.7 * old + 0.3 * new)

def get_density_from_pixels(zone):
    if zone is None or zone.size == 0:
        return 0
    gray = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 60, 255, cv2.THRESH_BINARY_INV)
    if thresh is None:
        return 0
    return cv2.countNonZero(thresh) / (zone.shape[0] * zone.shape[1])

def get_color(label):
    if label == "HIGH":
        return (0, 0, 150)
    elif label == "MEDIUM":
        return (0, 150, 150)
    else:
        return (0, 150, 0)

# -------- MAIN LOOP --------
send_data = "NORMAL\n"  # safe default

while True:
    success, frame = webcamera.read()

    if not success:
        if choice == "2":
            webcamera.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        else:
            break

    if frame is None:
        continue

    results = model.predict(frame, classes=[0], conf=0.5, verbose=False)
    annotated_frame = frame.copy()
    h, w, _ = frame.shape

    zone_labels = {"A": "LOW", "B": "LOW", "C": "LOW", "D": "LOW"}
    high_zones = []

    # -------- WEBCAM: YOLO ZONE COUNTING --------
    if choice == "1":
        zone_counts = {"A": 0, "B": 0, "C": 0, "D": 0}

        if results[0].boxes is not None:
            for box in results[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                if cx < w // 2 and cy < h // 2:
                    zone_counts["A"] += 1
                elif cx >= w // 2 and cy < h // 2:
                    zone_counts["B"] += 1
                elif cx < w // 2 and cy >= h // 2:
                    zone_counts["C"] += 1
                else:
                    zone_counts["D"] += 1

        for z in zone_counts:
            zone_history[z] = smooth_int(zone_history[z], zone_counts[z])

        # FIX: Use count/THRESHOLD ratio to drive density per zone
        for z in zone_history:
            ratio = zone_history[z] / max(THRESHOLD, 1)
            zone_labels[z] = get_stable_density(z, ratio * 0.35)  # scale to density range

        high_zones = [z for z in zone_labels if zone_labels[z] == "HIGH"]

    # -------- VIDEO: PIXEL DENSITY --------
    else:
        zone_pixels = {
            "A": get_density_from_pixels(frame[0:h//2,   0:w//2]),
            "B": get_density_from_pixels(frame[0:h//2,   w//2:w]),
            "C": get_density_from_pixels(frame[h//2:h,   0:w//2]),
            "D": get_density_from_pixels(frame[h//2:h,   w//2:w]),
        }

        print("Density Values:", zone_pixels)

        for z in zone_pixels:
            zone_history[z] = smooth_float(zone_history[z], zone_pixels[z])

        zone_labels = {z: get_stable_density(z, zone_history[z]) for z in zone_history}
        high_zones = [z for z in zone_labels if zone_labels[z] == "HIGH"]

    # -------- UNIFIED HIGH COUNTER (BOTH MODES) --------
    if high_zones:
        high_counter += 1
    else:
        high_counter = 0

    # -------- BUILD SERIAL MESSAGE --------
    # FIX: No frame ID appended — clean format only
    if high_counter >= HIGH_CONFIRM and high_zones:
        send_data = f"HIGH:{','.join(sorted(high_zones))}\n"
    else:
        send_data = "NORMAL\n"

    # -------- SEND WITH RATE LIMITING --------
    current_time = time.time()
    if send_data != last_sent and (current_time - last_sent_time > SEND_INTERVAL):
        try:
            ard.write(send_data.encode())
            print("Sent to Arduino:", send_data.strip())
        except Exception as e:
            print(f"Serial write error: {e}")
        last_sent = send_data
        last_sent_time = current_time

    # -------- DRAW UI --------
    cv2.line(annotated_frame, (w//2, 0), (w//2, h), (0, 0, 0), 3)
    cv2.line(annotated_frame, (0, h//2), (w, h//2), (0, 0, 0), 3)

    labels_pos = {
        "A": (20, 40),
        "B": (w//2 + 20, 40),
        "C": (20, h//2 + 40),
        "D": (w//2 + 20, h//2 + 40),
    }
    for zone, pos in labels_pos.items():
        lbl = zone_labels.get(zone, "LOW")
        cv2.putText(annotated_frame, f"{zone}: {lbl}", pos,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, get_color(lbl), 3)

    person_count = len(results[0].boxes) if results[0].boxes is not None else 0
    cv2.putText(annotated_frame, f"Persons: {person_count}", (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    if person_count >= THRESHOLD:
        cv2.putText(annotated_frame, "ALERT: Threshold Exceeded!",
                    (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

    cv2.imshow("Crowd Detection", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

webcamera.release()
cv2.destroyAllWindows()
ard.close()
print("Last sent:", send_data.strip())
