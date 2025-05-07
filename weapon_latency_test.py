"""
RAMpage 30lb Combat Robot - Weapon Response Time Test
Team 22: Avery, Nick, Chris, Miles, Matthew

Simple test to measure weapon system response time:
- Monitors FlySky weapon trigger (CH6)
- Measures time between trigger activation and solenoid response

MIT License
"""

import machine
from machine import Pin
import utime
import sys

# ======= PIN CONFIG =======
# RC receiver pin for weapon trigger
CH6_PIN = 19     # SwD - Weapon trigger

# Solenoid pins (match pico_direct.py)
MAIN_SOLENOID_PIN = 14    # Main valve (reservoir)
PISTON_SOLENOID_PIN = 15  # Piston valve

# ======= CONSTANTS =======
# FlySky switch thresholds
SWITCH_ON_THRESHOLD = 1700   # Above this value, switch is ON
SWITCH_OFF_THRESHOLD = 1300  # Below this value, switch is OFF

# Test parameters
TEST_DURATION = 30000      # Test duration in ms (30 seconds)
TARGET_LATENCY = 50        # Target response time in ms

# ======= GLOBAL VARIABLES =======
# RC signal tracking
ch6_pulse_width = 0      # Current pulse width
ch6_last_update = 0      # Last time we received a signal update

# Test metrics
trigger_count = 0        # Number of triggers detected
trigger_active = False   # Current trigger state
last_trigger_time = 0    # Time of last trigger
latency_values = []      # All measured latency values

# ======= HARDWARE SETUP =======
print("\n===== RAMpage Combat Robot - Weapon Response Time Test =====")

# Set up LED for status indication
led = Pin(25, Pin.OUT)
led.value(0)  # Start with LED off

# Set up solenoid monitoring
main_solenoid_monitor = Pin(MAIN_SOLENOID_PIN, Pin.IN)
print(f"Solenoid monitoring configured on pin GP{MAIN_SOLENOID_PIN}")

# ======= RC RECEIVER HANDLER =======
ch6_pulse_start = 0

def ch6_handler(pin):
    """Interrupt handler for weapon trigger"""
    global ch6_pulse_start, ch6_pulse_width, ch6_last_update
    now = utime.ticks_us()
    if pin.value():  # Rising edge
        ch6_pulse_start = now
    else:  # Falling edge
        if ch6_pulse_start > 0:
            width = utime.ticks_diff(now, ch6_pulse_start)
            if 900 < width < 2100:  # Valid pulse range
                ch6_pulse_width = width
                ch6_last_update = utime.ticks_ms()

# Set up the interrupt handlers
ch6_pin = Pin(CH6_PIN, Pin.IN)
ch6_pin.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=ch6_handler)
print(f"RC receiver interrupt configured for weapon trigger (GP{CH6_PIN})")

# Set up solenoid monitoring interrupt
def solenoid_handler(pin):
    """Interrupt handler for solenoid activation"""
    global last_trigger_time, latency_values
    
    # Only record rising edge (solenoid activation)
    if pin.value() and last_trigger_time > 0:
        now = utime.ticks_ms()
        latency = utime.ticks_diff(now, last_trigger_time)
        
        # Only record reasonable response times (<200ms)
        if latency < 200:
            latency_values.append(latency)
            print(f"Measured latency: {latency} ms")
            last_trigger_time = 0  # Reset to avoid double-counting
            
            # Flash LED to confirm measurement
            led.value(1)
            utime.sleep_ms(50)
            led.value(0)

# Register solenoid monitoring interrupt
main_solenoid_monitor.irq(trigger=machine.Pin.IRQ_RISING, handler=solenoid_handler)

# ======= MAIN FUNCTION =======
def main():
    """Main test function"""
    global trigger_count, trigger_active, last_trigger_time
    
    # Print test information
    print(f"Test starting - duration: {TEST_DURATION/1000} seconds")
    print(f"Target latency: < {TARGET_LATENCY} ms")
    print("Activate weapon trigger (Switch D) multiple times during test")
    
    # Blink LED to show test is starting
    for _ in range(3):
        led.value(1)
        utime.sleep_ms(200)
        led.value(0)
        utime.sleep_ms(200)
    
    # Record test start time
    start_time = utime.ticks_ms()
    last_status_time = start_time
    
    try:
        # Main test loop
        while utime.ticks_diff(utime.ticks_ms(), start_time) < TEST_DURATION:
            # Check trigger state
            new_trigger_state = ch6_pulse_width > SWITCH_ON_THRESHOLD
            
            # Detect rising edge (OFF to ON transition)
            if new_trigger_state and not trigger_active:
                trigger_count += 1
                last_trigger_time = utime.ticks_ms()
                print(f"Trigger {trigger_count} activated")
            
            # Update trigger state
            trigger_active = new_trigger_state
            
            # Print status every 5 seconds
            now = utime.ticks_ms()
            if utime.ticks_diff(now, last_status_time) > 5000:
                elapsed = utime.ticks_diff(now, start_time)
                print("\n----- STATUS UPDATE -----")
                print(f"Test running for {elapsed/1000:.1f} seconds")
                print(f"Triggers detected: {trigger_count}")
                print(f"Measurements: {len(latency_values)}")
                
                if latency_values:
                    avg = sum(latency_values) / len(latency_values)
                    print(f"Current avg latency: {avg:.1f} ms")
                
                last_status_time = now
            
            # Brief delay to prevent tight loop
            utime.sleep_ms(20)
        
        # Test complete - print results
        print("\n===== TEST COMPLETE =====")
        
        if latency_values:
            avg = sum(latency_values) / len(latency_values)
            min_val = min(latency_values)
            max_val = max(latency_values)
            
            print(f"Triggers detected: {trigger_count}")
            print(f"Measurements recorded: {len(latency_values)}")
            print(f"Min latency: {min_val} ms")
            print(f"Max latency: {max_val} ms")
            print(f"Avg latency: {avg:.1f} ms")
            
            if avg <= TARGET_LATENCY:
                print(f"PASS: Average latency below target of {TARGET_LATENCY} ms")
            else:
                print(f"FAIL: Average latency exceeds target of {TARGET_LATENCY} ms")
        else:
            print("No measurements collected")
    
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import sys
        sys.print_exception(e)
    finally:
        led.value(0)
        print("\nTest ended")

# Run the test
if __name__ == "__main__":
    main()