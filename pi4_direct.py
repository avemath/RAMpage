#!/usr/bin/env python3
"""
RAMpage 30lb Combat Robot - Pi 4 Video Streaming Code
Team 22: Avery, Nick, Chris, Miles, Matthew

Video streaming script for Raspberry Pi 4B with camera:
- Streams video from the camera to my pc 
- Handles adaptive JPEG compression to fit frames into UDP packets
- Provides real-time visual feedback with status info overlay

Run video_direct.py script on pc powershell and pi4_direct.py in git bash through ssh
    
MIT License
"""

import argparse
import socket
import time
import cv2
import numpy as np
import sys
import signal
import os

# Import picamera2 (the new libcamera-based module)
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    print("ERROR: Picamera2 module not found. Install with:")
    print("  sudo apt install python3-picamera2")
    PICAMERA2_AVAILABLE = False

# ======= CONFIGURATION =======
# Network settings
DEFAULT_CLIENT_IP = "192.168.1.100"  # Laptop tailscale IP
DEFAULT_PORT = 5000                  # UDP port for video streaming

# Camera settings
RESOLUTION = (800, 600)              # Camera resolution (width, height)
FPS_TARGET = 30                      # Target frames per second
JPEG_QUALITY = 80                    # Initial JPEG compression quality (0-100)

# Max UDP packet size (conservative to avoid fragmentation)
MAX_UDP_SIZE = 65000                 # Slightly below theoretical max of 65507

# ======= GLOBAL VARIABLES =======
# Control flags
running = True                       # Main loop control

# Performance tracking
frame_count = 0                      # Frames since last FPS calculation
frames_sent = 0                      # Total frames successfully sent
frames_skipped = 0                   # Frames skipped due to size constraints
current_fps = 0                      # Current calculated FPS
start_time = 0                       # Start time for overall performance tracking

def parse_arguments():
    """
    Parse command line arguments using argparse

    Source:
    https://docs.python.org/3/library/argparse.html
    """
    parser = argparse.ArgumentParser(description="RAMpage Combat Robot - Pi 4 Video Streaming")
    parser.add_argument("--ip", type=str, default=DEFAULT_CLIENT_IP,
                      help=f"IP address of receiver (default: {DEFAULT_CLIENT_IP})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                      help=f"Port for video streaming (default: {DEFAULT_PORT})")
    parser.add_argument("--debug", action="store_true",
                      help="Enable additional debug output")
    return parser.parse_args()

def signal_handler(sig, frame):
   
     """
    Handle Ctrl+C (SIGINT) and other termination signals gracefully

    Source:
    https://docs.python.org/3/library/signal.html
    """
    global running
    print("\nReceived signal to terminate. Shutting down...")
    running = False

# Register signal handlers for clean shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def init_camera():
    """
    Initialize the camera with Picamera2
    
    Configures the Pi camera with optimized settings for combat robotics:
    - Higher sharpness for better visibility
    - Increased contrast to help identify other robots
    - Minimal noise reduction for lower latency
    - Auto white balance and exposure for varying lighting conditions

    Sources:
    https://www.raspberrypi.com/documentation/computers/camera_software.html
    https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
    https://github.com/raspberrypi/picamera2
    """
    
    if not PICAMERA2_AVAILABLE:
        print("ERROR: Camera initialization failed - picamera2 not available")
        return None
        
    try:
        print("Initializing camera...")
        
        # Create Picamera2 instance
        picam2 = Picamera2()
        
        # Configure for video streaming
        config = picam2.create_video_configuration(
            main={"size": RESOLUTION, "format": "RGB888"},
            controls={"FrameRate": FPS_TARGET}
        )
        picam2.configure(config)
        
        # Values determined through testing
        picam2.set_controls({
            "AwbEnable": True,      # Auto white balance
            "AeEnable": True,       # Auto exposure
            "Sharpness": 2.5,       # Better sharpness
            "Contrast": 1.2,        # Slightly more contrast
            "Brightness": 0.1,      # Slightly brighter
            "NoiseReductionMode": 1 # Minimal noise reduction (clearer image)
        })
        
        # Start the camera
        picam2.start()
        
        # Allow camera time to initialize
        print("Waiting for camera to initialize...")
        time.sleep(2)
        
        # Test capture to ensure camera is working
        test_frame = picam2.capture_array()
        if test_frame is None or test_frame.size == 0:
            print("ERROR: Failed to capture test frame from camera")
            return None
            
        print(f"Camera initialized successfully. Frame size: {test_frame.shape}")
        return picam2
        
    except Exception as e:
        print(f"ERROR initializing camera: {e}")
        return None

def create_socket():
    """
    Create and configure a UDP socket for sending video frames
    
    Uses UDP for lowest latency video streaming, which is critical
    for real-time robot control in combat situations.
    
    Source:
    https://docs.python.org/3/library/socket.html
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock
    except Exception as e:
        print(f"ERROR creating socket: {e}")
        return None

def add_overlay(frame, fps=0):
    """
    Add status overlay to the video frame
    - Current timestamp for latency assessment
    - FPS counter for performance monitoring
    """
    # Add timestamp for testing latency
    timestamp = time.strftime("%H:%M:%S.%f")[:-3]
    cv2.putText(frame, timestamp, (10, 70), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    # Add FPS counter
    if fps > 0:
        fps_text = f"FPS: {fps:.1f}"
        cv2.putText(frame, fps_text, (frame.shape[1] - 120, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    return frame

def stream_video(client_ip, port, debug=False):
    
     """
    Stream video from Raspberry Pi camera to client (pc)
    
    Main video streaming loop that:
    - Captures frames from camera
    - Adds status overlay
    - Compresses each frame using JPEG
    - Sends frame over UDP to video client
    - Includes performance metrics and fallback quality steps
    
    Combines techniques from:
    - OpenCV official examples: https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html
    - Picamera2 documentation: https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
    - OpenCV JPEG encoding: https://docs.opencv.org/4.x/d4/da8/group__imgcodecs.html
    """
    global running, frame_count, current_fps, frames_sent, frames_skipped
    
    # Initialize camera
    picam2 = init_camera()
    if not picam2:
        print("Failed to initialize camera. Exiting.")
        return False
    
    # Create socket
    sock = create_socket()
    if not sock:
        print("Failed to create socket. Exiting.")
        if picam2:
            picam2.close()
        return False
    
    # Performance tracking variables
    start_time = time.time()
    last_report = start_time
    fps_update_time = start_time
    
    # Set up compression quality steps
    # If a frame is too large, try progressively lower quality
    quality_steps = [JPEG_QUALITY, 75, 70, 65, 60, 55, 50]
    
    print(f"Starting video stream to {client_ip}:{port}")
    try:
        while running:
            loop_start = time.time()
            
            # Capture a frame
            frame = picam2.capture_array()
            
            # Convert from RGB to BGR for OpenCV processing
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            # Add overlay with timestamp and FPS
            frame_bgr = add_overlay(frame_bgr, current_fps)
            
            # Try different quality levels until frame fits in UDP packet
            frame_sent = False
            for quality in quality_steps:
                # Compress the frame to JPEG with current quality
                encode_param = [
                    int(cv2.IMWRITE_JPEG_QUALITY), quality,
                    int(cv2.IMWRITE_JPEG_OPTIMIZE), 1
                ]
                success, encoded_frame = cv2.imencode('.jpg', frame_bgr, encode_param)
                
                if not success:
                    continue  # Try next quality level
                
                # Get the packet data and check size
                packet_data = encoded_frame.tobytes()
                packet_size = len(packet_data)
                
                # Check if packet fits in UDP
                if packet_size <= MAX_UDP_SIZE:
                    # Send the frame
                    sock.sendto(packet_data, (client_ip, port))
                    frames_sent += 1
                    frame_count += 1
                    frame_sent = True
                    
                    # If we had to reduce quality, log it
                    if debug and quality < JPEG_QUALITY:
                        print(f"Frame quality reduced to {quality} to fit in UDP (size: {packet_size} bytes)")
                    
                    break  # Successfully sent, exit quality loop
            
            # If we couldn't send frame at any quality
            if not frame_sent:
                frames_skipped += 1
                if debug:
                    print(f"WARNING: Frame skipped - couldn't compress enough")
            
            # Calculate FPS every second
            current_time = time.time()
            fps_elapsed = current_time - fps_update_time
            if fps_elapsed >= 1.0:
                current_fps = frame_count / fps_elapsed
                frame_count = 0
                fps_update_time = current_time
            
            # Print debug info periodically
            if debug and (current_time - last_report) >= 5.0:
                elapsed = current_time - start_time
                total_frames = frames_sent + frames_skipped
                avg_fps = frames_sent / elapsed if elapsed > 0 else 0
                print(f"Streaming stats - Time: {elapsed:.1f}s, Sent: {frames_sent} frames, "
                      f"Skipped: {frames_skipped} frames ({frames_skipped/total_frames*100:.1f}%), "
                      f"FPS: {current_fps:.1f}, Avg FPS: {avg_fps:.1f}")
                last_report = current_time
            
            # Control frame rate
            frame_duration = 1.0 / FPS_TARGET
            processing_time = time.time() - loop_start
            sleep_time = max(0, frame_duration - processing_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except Exception as e:
        print(f"ERROR during streaming: {e}")
        return False
    
    finally:
        # Clean up
        print("Closing camera and socket...")
        try:
            picam2.close()
        except:
            pass
        try:
            sock.close()
        except:
            pass
    
    # Print summary statistics
    elapsed = time.time() - start_time
    fps = frames_sent / elapsed if elapsed > 0 else 0
    print(f"Stream ended - Sent {frames_sent} frames in {elapsed:.1f} seconds ({fps:.1f} FPS)")
    if frames_skipped > 0:
        print(f"Skipped {frames_skipped} oversized frames ({frames_skipped/(frames_sent+frames_skipped)*100:.1f}%)")
    return True

def main():
    """Main function"""
    # Parse command line arguments
    args = parse_arguments()
    
    print("\n===== RAMpage Combat Robot - Pi 4 Video Streaming =====")
    print(f"Streaming to: {args.ip}:{args.port}")
    print(f"Resolution: {RESOLUTION[0]}x{RESOLUTION[1]}, Target FPS: {FPS_TARGET}")
    print("Press Ctrl+C to stop streaming")
    
    # Start streaming
    success = stream_video(args.ip, args.port, args.debug)
    
    if success:
        print("Streaming completed successfully")
        return 0
    else:
        print("Streaming ended with errors")
        return 1

if __name__ == "__main__":
    main()