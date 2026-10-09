# ResQnet System

ResQnet is a comprehensive disaster response and thermal intelligence platform consisting of multiple specialized modules working together to provide critical information during emergencies (e.g., earthquakes, natural disasters).

## System Architecture

### 1. AI Route Engine (`route_engine/`)
Responsible for calculating the shortest and safest route for responders and survivors. It dynamically paths around hazards like fires or floods.

### 2. BLE Localization Backend (`ble_localization/`)
The backend localization service. It requires at least two mobile phones running the ResQnet Mesh app to be connected to it in order to accurately triangulate and track positions.

### 3. Frontend Dashboard (`dashboard_next/`)
A Next.js-based interactive dashboard where all detection events and statuses are visible in real-time. It acts as the command center to visualize hazards and routes.

### 4. ResQnet Mesh (`mesh_app/`)
The Flutter mobile application. It acts as a node in the Bluetooth Low Energy (BLE) mesh network, streaming live location data and connecting to the localization backend.

### 5. Thermal Image Analysis (`thermal/`)
A dedicated suite for advanced thermal detection, consisting of two main components:
- **`ai_segmented_heatmap.py`**: Real-time object detection and segmentation using thermal heatmaps.
- **`main.py`**: A detailed, interactive desktop application to measure and analyze heat signatures in depth (crucial during earthquakes and similar disasters, e.g., Nepal).

### 6. Thermal Drone Server (`route_engine/thermal_server.py`)
A fast API backend server dedicated to receiving and processing live drone feeds, providing:
- Raw Sensor input
- Adaptive Threshold Masking
- Locked Thermal Detections
