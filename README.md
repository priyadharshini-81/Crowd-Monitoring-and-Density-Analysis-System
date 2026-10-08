# Crowd-Monitoring-and-Density-Analysis-System
The Real-time IoT crowd monitoring system using YOLOv8 and OpenCV to detect people, count crowds, analyze density, and trigger alerts during overcrowding. The system integrates ESP32, sensors, GSM, and IoT communication for real-time monitoring and automated alerts. It helps authorities make quick decisions and prevent crowd-related accidents .

## Features

- Real-time crowd detection
- Zone classification (A, B, C, D)
- YOLO-based person detection
- Crowd density analysis
- Real-time overcrowding detection
- SMS alerts using ESP32 + GSM
- LCD display for crowd status

## How It Works

- Python processes webcam/video input using YOLO and OpenCV
- Detected crowd data is analyzed based on predefined density thresholds
- Data is sent to ESP32 through Serial communication
- ESP32 displays the crowd status on LCD
- SMS alerts are triggered through GSM when overcrowding is detected

## Technologies Used

- Python
- OpenCV
- YOLO
- ESP32
- GSM Module
- LCD
- Serial Communication

## Run

```bash
python main_final.py
