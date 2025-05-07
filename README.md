**RAMpage**


**Project Overview**

RAMpage is a 30lb combat robot built for the Bengal Bot competition. This repository contains the control software running on the robot's Raspberry Pi 4B and Raspberry Pi Pico W, handling remote operation, weapon control, safety systems, and video streaming.


**System Architecture**

The robot uses a dual-controller approach:
Raspberry Pi 4B: Handles video streaming from the fisheye camera to the operator laptop

Raspberry Pi Pico W: Controls the pneumatic weapon system and safety mechanisms

Communication is managed through:
WiFi/UDP for video streaming (Pi 4B)
Direct PWM signals from a FlySky RC receiver (Pico W)


**Files Overview**

pico_direct.py: Main weapon control code for the Raspberry Pi Pico W
pi4_direct.py: Video streaming code for the Raspberry Pi 4B
video_direct.py: Client-side video receiver code for the operator laptop
temp_test.py: Test script for monitoring Pi CPU temperature
weapon_latency_test.py: Test script for weapon system response times


**Hardware Requirements**

Raspberry Pi 4B with camera interface
Raspberry Pi Pico W
Raspberry Pi Camera (fisheye version recommended)
FlySky RC transmitter (FS-i6X) and receiver (FS-iA6B)
Solenoid valves for pneumatic system


**Software Requirements**

Raspberry Pi OS with Python 3
MicroPython installed on Raspberry Pi Pico W
Required Python packages: OpenCV, NumPy, Picamera2


**Use the FlySky controller to operate the robot:**

Left stick: Left motor control
Right stick: Right motor control
Switch A (top left): Kill switch
Switch D (top right): Weapon trigger


**Weapon System**

The pneumatic weapon system uses:
Two pneumatic cylinders for the pusher mechanism
Solenoid valves for precise control
Activation counter to manage limited air supply
Safety mechanisms including kill switch and signal loss detection


**Video System**

The video streaming system features:
UDP-based transmission for lowest latency
Adaptive JPEG compression to fit frames in UDP packets
Status overlay with timestamp and FPS counter
"No Signal" detection with visual feedback


**Testing and Validation**

temp_test.py: Monitors CPU temperature to ensure the robot doesn't overheat
weapon_latency_test.py: Measures weapon system response time


**License**

This project is licensed under the MIT License. See the LICENSE file for details.
