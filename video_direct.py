#!/usr/bin/env python3
"""
RAMpage 30lb Combat Robot - Video Client Receiver
Team 22: Avery, Nick, Chris, Miles, Matthew

Video client for receiving and displaying camera feed from the RAMpage robot:
- Receives video stream from Pi via UDP
- Displays stream with status info and performance metrics
- Includes "No Signal" detection and handling

Run video_direct.py script on pc powershell and pi4_direct.py in git bash through ssh

MIT License
"""

import cv2
import socket
import numpy as np
import time
import sys
import argparse

# ======= CONFIG =======
# Default settings - match Pi side
DEFAULT_PORT = 5000               # UDP port
DISPLAY_WIDTH = 800               # Initial window width
DISPLAY_HEIGHT = 600              # Initial window height
WINDOW_NAME = "RAMpage Robot Camera"
MAX_PACKET_SIZE = 65536           # Max UDP packet size
TIMEOUT = 3.0                     # Seconds without video before showing "No Signal"

# ======= GLOBAL VARIABLES =======
running = True                    # Main loop control
frame_count = 0                   # Frames since last FPS calculation
fps = 0                           # Current FPS
connected = False                 # Whether we're receiving video
last_frame_time = 0               # Time of last received frame

def parse_arguments():
     """
    Parse command line arguments using argparse

    Source:
    https://docs.python.org/3/library/argparse.html
    """
    parser = argparse.ArgumentParser(description="RAMpage Combat Robot - Video Client")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port for receiving video (default: {DEFAULT_PORT})")
    parser.add_argument("--fullscreen", action="store_true",
                        help="Start in fullscreen mode")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug mode with extra information")
    return parser.parse_args()

def create_socket(port):
    """
    Create and configure UDP socket for receiving video

    Sets up:
    - Reusable address (SO_REUSEADDR)
    - Large receive buffer for high frame rate
    - Short timeout for responsiveness

    Source:
    - Python socket documentation: https://docs.python.org/3/library/socket.html
    """
    try:
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Set socket options
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2*65536)  # Larger receive buffer
        
        # Set a timeout to detect connection loss
        sock.settimeout(0.5)  # Short timeout for responsiveness
        
        # Bind to all interfaces
        sock.bind(("0.0.0.0", port))
        
        print(f"Socket created and bound to port {port}")
        return sock
    except Exception as e:
        print(f"Failed to create socket: {e}")
        return None

def create_window(fullscreen=False):
   """
    Create OpenCV window for display

    Creates a resizable window w/ optional fullscreen mode.
    Provides low-latency display, which is key for real-time driving.

    Source:
    https://docs.opencv.org/4.x/d7/dfc/group__highgui.html
    """
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, DISPLAY_WIDTH, DISPLAY_HEIGHT)
    
    if fullscreen:
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    print(f"Display window created ({'fullscreen' if fullscreen else 'windowed'} mode)")
    return fullscreen

def create_no_signal_frame():
     """
    Create a frame to display when no video signal is received

    Uses OpenCV drawing + NumPy zeroed frame to generate a black frame with "NO SIGNAL" text.
    
    Sources:
    - OpenCV text overlay: https://docs.opencv.org/4.x/d6/d6e/group__imgproc__draw.html
    - NumPy blank image: https://numpy.org/doc/stable/reference/generated/numpy.zeros.html
    """
    # Create a black background
    frame = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8)
    
    # Add "NO SIGNAL" text
    cv2.putText(frame, "NO SIGNAL", (DISPLAY_WIDTH//2 - 100, DISPLAY_HEIGHT//2),
               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # Add help text
    cv2.putText(frame, "ESC: Exit | F: Toggle fullscreen", 
               (20, DISPLAY_HEIGHT - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    
    # Add RAMpage identifier
    cv2.putText(frame, "RAMpage Combat Robot", 
               (DISPLAY_WIDTH//2 - 120, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    
    return frame

def main():
    """
    Main function for video client

    Main loop:
    - Initializes socket and window
    - Receives frames over UDP
    - Decodes JPEG from bytes
    - Adds overlay and handles no-signal state
    - Tracks FPS

    Sources:
    - Socket how-to: https://docs.python.org/3/howto/sockets.html
    - OpenCV video display: https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html
    """
    
    global running, connected, last_frame_time, frame_count, fps
    
    # Parse command line arguments
    args = parse_arguments()
    
    print(f"\n===== RAMpage Combat Robot - Video Client =====")
    print(f"Receiving on port: {args.port}")
    print(f"Display resolution: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    print("Controls: ESC = Exit | F = Toggle fullscreen")
    
    # Create socket
    sock = create_socket(args.port)
    if not sock:
        print("Socket creation failed. Exiting.")
        return 1
    
    # Create display window
    fullscreen = create_window(args.fullscreen)
    
    # Create empty frame for when no signal is received
    no_signal_frame = create_no_signal_frame()
    current_frame = no_signal_frame.copy()
    
    # Performance tracking
    start_time = time.time()
    last_fps_update = start_time
    last_debug_update = start_time
    packets_received = 0
    
    try:
        print("Waiting for video stream...")
        
        while running:
            try:
                # Try to receive a video frame
                packet, addr = sock.recvfrom(MAX_PACKET_SIZE)
                packets_received += 1
                
                # Update connection status
                if not connected:
                    connected = True
                    print(f"Connected to video source at {addr[0]}:{addr[1]}")
                
                # Reset "no signal" timer
                last_frame_time = time.time()
                
                # Update performance counters
                frame_count += 1
                current_time = time.time()
                if current_time - last_fps_update >= 1.0:
                    fps = frame_count / (current_time - last_fps_update)
                    frame_count = 0
                    last_fps_update = current_time
                    
                    # Show periodic debug info if enabled
                    if args.debug and current_time - last_debug_update >= 5.0:
                        print(f"FPS: {fps:.1f}, Packet size: {len(packet)} bytes")
                        last_debug_update = current_time
                
                # Decode the JPEG image
                try:
                    # Convert packet to numpy array   
                    img_array = np.frombuffer(packet, dtype=np.uint8)
                    
                    # Decode image with high quality settings
                    frame = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)     
                    
                    if frame is not None and frame.size > 0:
                        # Save the current frame 
                        current_frame = frame.copy()
                        
                        # Add connection status
                        status_text = f"Connected - {fps:.1f} FPS"
                        cv2.putText(frame, status_text, (10, DISPLAY_HEIGHT - 40), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        # Add controls reminder
                        cv2.putText(frame, "ESC: Exit | F: Toggle fullscreen", 
                                   (10, DISPLAY_HEIGHT - 20), cv2.FONT_HERSHEY_SIMPLEX, 
                                   0.5, (255, 255, 255), 1)
                        
                        # Display the frame
                        cv2.imshow(WINDOW_NAME, frame)
                    else:
                        raise ValueError("Invalid frame data")
                
                except Exception as e:
                    if args.debug:
                        print(f"Error decoding frame: {e}")
            
            except socket.timeout:
                # Socket timeout - no data received in the timeout period
                # This is normal for a non-blocking receive
                pass
            
            except Exception as e:
                print(f"Error receiving video: {e}")
            
            # Check for video signal loss
            current_time = time.time()
            if connected and (current_time - last_frame_time) > TIMEOUT:
                connected = False
                print("Video signal lost. Waiting for reconnection...")
                cv2.imshow(WINDOW_NAME, no_signal_frame)
            
            # Process keyboard input
            key = cv2.waitKey(1) & 0xFF
            
            # ESC key: exit
            if key == 27:
                print("ESC pressed. Exiting...")
                running = False
                break
            
            # F key: toggle fullscreen
            elif key == ord('f') or key == ord('F'):
                fullscreen = not fullscreen
                if fullscreen:
                    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                print(f"Fullscreen: {fullscreen}")
    
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    
    finally:
        # Cleanup
        print("Cleaning up...")
        try:
            sock.close()
        except:
            pass
            
        try:
            cv2.destroyAllWindows()
        except:
            pass
    
    # Final statistics
    elapsed = time.time() - start_time
    if elapsed > 0:
        print(f"Runtime: {elapsed:.1f} seconds, Avg FPS: {(packets_received / elapsed):.1f}")
    
    print("Video client closed")
    return 0

if __name__ == "__main__":
    sys.exit(main())