#!/usr/bin/env python3
"""
RAMpage 30lb Combat Robot - Pi Temperature Monitoring Test
Team 22: Avery, Nick, Chris, Miles, Matthew

Simple temperature monitoring test:
- Monitors Raspberry Pi CPU temperature
- Verifies temperature stays below safe threshold
- Logs temperature data with timestamps
    
MIT License
"""

import time
import sys
import signal

# ======= CONFIG =======
# Temperature threshold (in Celsius)
PI_MAX_TEMP = 85.0       # Under 85°C for Pi safe operating

# Test duration
TEST_DURATION = 60  # seconds

# ======= GLOBAL VARIABLES =======
running = True
temps_recorded = []

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\nShutting down...")
    running = False

# Register signal handlers for clean shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_cpu_temperature():
    """Get Raspberry Pi CPU temperature from system"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read()) / 1000.0
        return temp
    except Exception as e:
        print(f"ERROR reading CPU temperature: {e}")
        return 0.0

def main():
    """Main function"""
    global running, temps_recorded
    
    print("\n===== RAMpage Combat Robot - Pi Temperature Test =====")
    print(f"Pi temperature limit: {PI_MAX_TEMP}°C")
    print(f"Test duration: {TEST_DURATION} seconds")
    print("Press Ctrl+C to stop test")
    
    # Initialize variables
    start_time = time.time()
    print(f"[{start_time:.3f}] Test started")
    
    try:
        while running:
            current_time = time.time()
            
            # Check if test duration exceeded
            if current_time - start_time >= TEST_DURATION:
                print("\nTest duration reached. Stopping test.")
                break
            
            # Read Pi CPU temperature
            pi_temp = get_cpu_temperature()
            temps_recorded.append(pi_temp)
            
            # Get current timestamp
            timestamp = time.time()
            
            # Display current temperature
            print(f"[{timestamp:.3f}] Raspberry Pi: {pi_temp:.1f}°C")
            
            # Check for temperature warning
            if pi_temp > PI_MAX_TEMP - 5:
                print(f"[{timestamp:.3f}] WARNING: Pi temperature near limit!")
            
            # Sleep for a second before next reading
            time.sleep(1)
    
    except Exception as e:
        print(f"ERROR during test: {e}")
    
    finally:
        # Calculate statistics
        if temps_recorded:
            max_temp = max(temps_recorded)
            avg_temp = sum(temps_recorded) / len(temps_recorded)
            
            print("\n----- TEST RESULTS -----")
            print(f"Samples collected: {len(temps_recorded)}")
            print(f"Maximum temperature: {max_temp:.1f}°C")
            print(f"Average temperature: {avg_temp:.1f}°C")
            
            # Overall test result
            if max_temp <= PI_MAX_TEMP:
                print(f"PASS: Maximum temperature ({max_temp:.1f}°C) is within limit ({PI_MAX_TEMP}°C)")
            else:
                print(f"FAIL: Maximum temperature ({max_temp:.1f}°C) exceeds limit ({PI_MAX_TEMP}°C)")
        
        # Final timestamp
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"[{end_time:.3f}] Test completed (duration: {elapsed:.1f}s)")

if __name__ == "__main__":
    main()