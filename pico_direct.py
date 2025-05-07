"""
RAMpage 30lb Combat Robot - Main Pico Code
Team 22: Avery, Nick, Chris, Miles, Matthew

Main controller for the Raspberry Pi Pico:
- Direct Flysky RC to ESC connection for motor control
- Reads weapon trigger and kill switch from FlySky receiver
- Controls pneumatic weapon system with activation counter

MIT License
"""

import machine
from machine import Pin
import utime
import sys

# ======= PIN CONFIG =======
# RC receiver pins - FlySky iA6B
CH5_PIN = 18     # SwA - Kill switch (top left)
CH6_PIN = 19     # SwD - Weapon trigger (top right)

# Solenoid pins - Normally Closed (NC) valves
MAIN_SOLENOID_PIN = 14    # Reservoir relay (exhaust) 
PISTON_SOLENOID_PIN = 15  # Pistons relay

# ======= CONSTANTS =======
# RC signal constants - standard RC values
PWM_MIN = 1000      # 1ms pulse (min)
PWM_MAX = 2000      # 2ms pulse (max)
PWM_CENTER = 1500   # 1.5ms pulse (center/neutral position)

# FlySky switch thresholds
SWITCH_ON_THRESHOLD = 1700   # Above this value, switch is ON
SWITCH_OFF_THRESHOLD = 1300  # Below this value, switch is OFF

# System timing
SIGNAL_TIMEOUT = 1000    # ms - time to wait before considering signal lost
STARTUP_DELAY = 3000     # ms - time to wait during startup 
KILL_SWITCH_DEBOUNCE = 300  # ms - debounce time for kill switch changes

# Weapon system constants - updated values from weapon_latency_test.py testing results
MAX_WEAPON_ACTIVATIONS = 17          # Max weapon activations
WEAPON_COOLDOWN = 500                # ms - cooldown between activations
SOLENOID_ACTIVATION_TIME = 400       # ms - how long to keep solenoids open
SOLENOID_SEQUENCE_DELAY = 50         # ms - delay between opening valves

# ======= GLOBAL VARIABLES =======
# RC signal tracking
ch5_pulse_width = 0    # Kill switch
ch6_pulse_width = 0    # Weapon trigger
ch5_last_update = 0    # Last time we received a kill switch signal
ch6_last_update = 0    # Last time we received a weapon trigger signal

# System state
startup_time = 0
emergency_stop = False
emergency_cause = "none"  # Can be "none", "kill_switch", "signal_loss", "startup"
kill_switch_last_change = 0
signal_loss_time = 0

# Weapon state
weapon_activations = 0     # Number of times weapon has been activated
weapon_cooldown_end = 0    # Time when weapon can be activated again
weapon_depleted = False    # Whether we've hit max activations
plow_active = False        # Whether plow is currently active
weapon_trigger_last_state = False  # For edge detection

# ======= HARDWARE INITIALIZATION =======
print("\n===== RAMpage Combat Robot - Main Pico Code =====")

# Set up LED (for status indication)
led = Pin(25, Pin.OUT)
led.value(0)  # Start with LED off

# Initialize solenoids
solenoid_active = 0  # Active-low
try:
    main_solenoid = Pin(MAIN_SOLENOID_PIN, Pin.OUT)
    piston_solenoid = Pin(PISTON_SOLENOID_PIN, Pin.OUT)
    
    main_solenoid.value(solenoid_active)          # Initialize exhaust relay to active state (open)
    piston_solenoid.value(not solenoid_active)    # Initialize pistons relay to inactive state (closed)
    
    print(f"Solenoids initialized on pins {MAIN_SOLENOID_PIN} and {PISTON_SOLENOID_PIN}")
except Exception as e:
    print(f"Solenoid initialization failed: {e}")
    main_solenoid = piston_solenoid = None
    sys.exit(1)

# ======= RC RECEIVER INTERRUPT HANDLERS =======
# Variables for pulse timing
ch5_pulse_start = 0
ch6_pulse_start = 0

def ch5_handler(pin):
     """
    Interrupt handler for CH5 (kill switch)

    Uses edge detection to measure PWM pulse width from RC receiver.
    Rising edge starts the timer, falling edge calculates width.
    Technique inspired by RC decoder implementations for microcontrollers.
    
    Sources:
    https://docs.micropython.org/en/latest/library/machine.Pin.html#machine.Pin.irq
    https://docs.micropython.org/en/latest/reference/isr_rules.html#writing-interrupt-handlers
    """
    global ch5_pulse_start, ch5_pulse_width, ch5_last_update
    now = utime.ticks_us()
    if pin.value():  # Rising edge
        ch5_pulse_start = now
    else:  # Falling edge
        if ch5_pulse_start > 0:
            width = utime.ticks_diff(now, ch5_pulse_start)
            if 900 < width < 2100:  # Valid pulse range
                ch5_pulse_width = width
                ch5_last_update = utime.ticks_ms()

def ch6_handler(pin):
    """
    Interrupt handler for CH6 (weapon trigger)
    
    Uses edge detection to measure PWM pulse width from RC receiver.
    Rising edge starts the timer, falling edge calculates width.
    Used MicroPython IRQ documentation for details on interrupt handling.
    """
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
try:
    # Using Pin.IRQ approach as shown in the MicroPython docs
    # https://docs.micropython.org/en/latest/library/machine.Pin.html#machine.Pin.irq
    ch5_pin = Pin(CH5_PIN, Pin.IN)
    ch6_pin = Pin(CH6_PIN, Pin.IN)
    
    ch5_pin.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=ch5_handler)
    ch6_pin.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=ch6_handler)
    
    print(f"RC receiver interrupts configured for kill switch (GP{CH5_PIN}) and weapon trigger (GP{CH6_PIN})")
except Exception as e:
    print(f"RC interrupt setup failed: {e}")
    sys.exit(1)

# ======= HELPER FUNCTIONS =======
def read_rc_switch(pulse_width, last_update):
    
    """
    Read the state of an RC switch channel.
    Signal bounds based on FlySky testing.

    Returns (switch_on, signal_lost) where:
    - switch_on: True if switch is ON, False if OFF or MIDDLE
    - signal_lost: True if we haven't received a signal recently
    """
    now = utime.ticks_ms()
    
    # Check if we have a recent signal
    if utime.ticks_diff(now, last_update) > SIGNAL_TIMEOUT:
        # During initial startup, don't report signal loss
        if utime.ticks_diff(now, startup_time) < STARTUP_DELAY:
            return False, False  # Default to OFF, no signal loss
        return False, True  # Default to OFF, signal lost
    
    # For switches, using explicit thresholds for better reliability
    if pulse_width > SWITCH_ON_THRESHOLD:
        return True, False  # ON, signal good
    else:
        return False, False  # OFF or MIDDLE, signal good

def activate_weapon():
    """
    This function sequences the solenoid valves for proper firing of the pneumatic plow system:
    1. Open main valve (exhaust - to pull in plow)
    2. Short delay to build pressure
    3. Close main valve
    4. Short dwell time
    5. Open piston valves to actuate the plow
    6. Keep valves open for activation time
    7. Close piston valves
    8. Open main valve to vent
    
    Returns True if activation was successful, False otherwise.
    """
    global weapon_activations, weapon_cooldown_end, weapon_depleted, plow_active
    
    # Don't activate if in emergency stop
    if emergency_stop:
        print("Cannot activate weapon - emergency stop active")
        return False
    
    # Don't activate if in cooldown period
    now = utime.ticks_ms()
    if now < weapon_cooldown_end:
        print("Weapon in cooldown - wait before activating again")
        return False
    
    # Don't activate if weapon is depleted
    if weapon_depleted:
        print("Weapon depleted - maximum activations reached")
        return False
    
    # Check if solenoids are available
    if main_solenoid is None or piston_solenoid is None:
        print("Solenoids not initialized - can't activate weapon")
        return False
    
    try:
        # Increment activation counter
        weapon_activations += 1
        print(f"Activating weapon ({weapon_activations}/{MAX_WEAPON_ACTIVATIONS})")
        
        # Set cooldown end time
        weapon_cooldown_end = utime.ticks_add(now, WEAPON_COOLDOWN)
        
        # Check if we've reached max activations
        if weapon_activations >= MAX_WEAPON_ACTIVATIONS:
            weapon_depleted = True
            print("WARNING: Weapon system depleted")
        
        # Show activation with LED
        plow_active = True
        led.value(1)
        
        # Activate solenoids in sequence
        # 1. Open main valve to allow air flow (exhaust)
        main_solenoid.value(solenoid_active)
        
        # 2. Wait for pressure to build
        utime.sleep_ms(SOLENOID_SEQUENCE_DELAY)
        
        # 3. Close main valve
        main_solenoid.value(not solenoid_active)
        
        # 4. Dweel time
        utime.sleep_ms(SOLENOID_SEQUENCE_DELAY)
        
        # 5. Open piston valves to extend plow
        piston_solenoid.value(solenoid_active)
        
        # 6. Keep valves open for activation time to fully extend
        utime.sleep_ms(SOLENOID_ACTIVATION_TIME)
        
        # 7. Close valves to complete activation
        piston_solenoid.value(not solenoid_active)
        
        # 8. Re-open main valve (exhaust)
        main_solenoid.value(solenoid_active)
        
        # Reset flags
        plow_active = False
        led.value(0)
        
        return True
    except Exception as e:
        print(f"Weapon activation failed: {e}")
        # Make sure pistons solenoid is closed & main solenoid is open in case of error
        try:
            main_solenoid.value(solenoid_active)
            piston_solenoid.value(not solenoid_active)
            plow_active = False
            led.value(0)
        except:
            pass
        return False

def trigger_emergency_stop(cause="unknown"):
    """
    Activate emergency stop by cutting power to the Flysky receiver.

    Removing signal to ESCs causes them to enter failsafe mode.
    This approach is recommended by the RioBotz team and others 
    in combat robotics as a reliable safety mechanism.
    Source: https://www.riobotz.com/riobotz_combot_tutorial.pdf
    """
    global emergency_stop, emergency_cause, kill_switch_last_change
    
    if emergency_stop:
        return  # Already in emergency stop
    
    print(f"EMERGENCY STOP ACTIVATED: {cause}")
    emergency_stop = True
    emergency_cause = cause
    kill_switch_last_change = utime.ticks_ms()
    
    # Reset solenoids
    if main_solenoid:
        main_solenoid.value(solenoid_active)
    if piston_solenoid:
        piston_solenoid.value(not solenoid_active)
    
    # Blink LED rapidly to indicate emergency stop
    for _ in range(10):
        led.value(1)
        utime.sleep_ms(50)
        led.value(0)
        utime.sleep_ms(50)

def check_emergency_stop_reset():
    """
    Check if we can reset from emergency stop.
    Returns True if emergency stop can be reset, False otherwise.
    """
    global emergency_stop, emergency_cause
    
    # Only try to reset if we're in emergency stop
    if not emergency_stop:
        return False
    
    now = utime.ticks_ms()
    
    # Get kill switch state
    kill_switch_on, kill_lost = read_rc_switch(ch5_pulse_width, ch5_last_update)
    
    # Reset logic
    if emergency_cause == "kill_switch":
        # If kill switch caused the emergency, it must be OFF to reset
        if not kill_switch_on and not kill_lost:
            # Debounce edge case
            if utime.ticks_diff(now, kill_switch_last_change) > KILL_SWITCH_DEBOUNCE:
                print("Emergency stop reset (kill switch now OFF)")
                return True
    
    elif emergency_cause == "signal_loss":
        # If signal loss caused the emergency, we just need signals back
        kill_switch_on, kill_lost = read_rc_switch(ch5_pulse_width, ch5_last_update)
        weapon_trigger_on, weapon_lost = read_rc_switch(ch6_pulse_width, ch6_last_update)
        
        signal_lost = kill_lost or weapon_lost
        if not signal_lost:
            # Check signals are stable
            if utime.ticks_diff(now, signal_loss_time) > 1000:
                print("Emergency stop reset (signal restored)")
                return True
    
    else:
        # For other causes, just check kill switch is OFF and signal is good
        if not kill_switch_on and not kill_lost:
            if utime.ticks_diff(now, kill_switch_last_change) > KILL_SWITCH_DEBOUNCE:
                print("Emergency stop reset (generic)")
                return True
    
    return False

def reset_emergency_stop():
    """Reset emergency stop"""
    global emergency_stop, emergency_cause
    
    emergency_stop = False
    emergency_cause = "none"
    
    # Blink LED to confirm reset
    for _ in range(2):
        led.value(1)
        utime.sleep_ms(200)
        led.value(0)
        utime.sleep_ms(200)
    
    print("Emergency stop reset - system ready")

def print_status():
    """Print current status info to console"""
    
    # Get switch states
    kill_switch_on, kill_lost = read_rc_switch(ch5_pulse_width, ch5_last_update)
    weapon_trigger_on, weapon_lost = read_rc_switch(ch6_pulse_width, ch6_last_update)
    
    # Print status info
    print("\n----- STATUS UPDATE -----")
    print(f"Kill switch: {'ON' if kill_switch_on else 'OFF'}")
    print(f"Weapon trigger: {'ON' if weapon_trigger_on else 'OFF'}")
    print(f"Emergency stop: {'ACTIVE' if emergency_stop else 'Inactive'}")
    print(f"Emergency cause: {emergency_cause}")
    print(f"Signal status: {'LOST' if kill_lost or weapon_lost else 'Good'}")
    print(f"Weapon activations: {weapon_activations}/{MAX_WEAPON_ACTIVATIONS}" +
          (" (DEPLETED)" if weapon_depleted else ""))
    print(f"Raw values - Kill:{ch5_pulse_width} Weapon:{ch6_pulse_width}")

# ======= MAIN FUNCTION =======
def main():
    """
    Main function that runs the weapon control system.
    Monitors the FlySky switches and controls the pneumatic weapon.
    """
    global startup_time, emergency_stop, weapon_trigger_last_state
    global kill_switch_last_change, signal_loss_time
    
    # Record startup time
    startup_time = utime.ticks_ms()
    kill_switch_last_change = startup_time
    signal_loss_time = startup_time
    
    print("\n===== STARTING WEAPON CONTROL SYSTEM =====")
    print("Waiting for RC signals to stabilize...")
    
    # Initial LED pattern to show we're starting
    for _ in range(3):
        led.value(1)
        utime.sleep_ms(200)
        led.value(0)
        utime.sleep_ms(200)
    
    # Startup and warmup delay
    wait_start = utime.ticks_ms()
    while utime.ticks_diff(utime.ticks_ms(), wait_start) < STARTUP_DELAY:
        # Blink LED during startup
        led.value((utime.ticks_ms() % 500) < 250)
        
        # Check for kill switch during startup
        kill_switch_on, _ = read_rc_switch(ch5_pulse_width, ch5_last_update)
        if kill_switch_on:
            print("Kill switch is ON during startup - must turn OFF to operate")
            trigger_emergency_stop("startup")
            break
        
        utime.sleep_ms(100)
    
    print("System initialized")
    print(f"Maximum weapon activations: {MAX_WEAPON_ACTIVATIONS}")
    print("To RESET emergency stop: Simply turn the kill switch OFF")
    
    # Status display interval
    status_interval = 3000  # 3s between status prints
    last_status_time = 0
    
    # Main loop
    try:
        while True:
            now = utime.ticks_ms()
            
            # Print status periodically
            if utime.ticks_diff(now, last_status_time) > status_interval:
                print_status()
                last_status_time = now
            
            # Read RC channels
            kill_switch_on, kill_lost = read_rc_switch(ch5_pulse_width, ch5_last_update)
            weapon_trigger_on, weapon_lost = read_rc_switch(ch6_pulse_width, ch6_last_update)
            
            # Check for kill switch activation
            if kill_switch_on and not emergency_stop:
                print("Kill switch activated")
                trigger_emergency_stop("kill_switch")
            
            # Check for signal loss
            if (kill_lost or weapon_lost) and not emergency_stop:
                print("Signal lost - emergency stop")
                signal_loss_time = now
                trigger_emergency_stop("signal_loss")
            
            # Check if we can reset from emergency stop
            if emergency_stop and check_emergency_stop_reset():
                reset_emergency_stop()
            
            # Skip the rest if in emergency stop
            if emergency_stop:
                # Blink LED to indicate emergency state
                led.value(1 if (now % 500) < 250 else 0)
                utime.sleep_ms(10)
                continue
            
            # Weapon activation
            if weapon_trigger_on and not weapon_trigger_last_state and not plow_active and not weapon_depleted:
                activate_weapon()
            
            # Update last weapon trigger state for edge detection
            weapon_trigger_last_state = weapon_trigger_on
            
            # LED status - blink pattern based on system state
            if weapon_depleted:
                # Rapid double blink when depleted
                led.value(1 if (now % 1000) < 100 or (now % 1000) > 200 and (now % 1000) < 300 else 0)
            elif plow_active:
                # Solid when plow is active
                led.value(1)
            else:
                # Slow pulse when idle and ready
                led.value(1 if (now % 2000) < 500 else 0)
            
            # Short delay to prevent tight loop
            utime.sleep_ms(20)
            
    except KeyboardInterrupt:
        print("\nControl system terminated by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import sys
        sys.print_exception(e)
    finally:
        # Clean up
        print("\nShutting down...")
        
        # Reset solenoids
        if main_solenoid:
            main_solenoid.value(solenoid_active)
        if piston_solenoid:
            piston_solenoid.value(not solenoid_active)
            
        led.value(0)
        print("System stopped")

# Run the program
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}")
        import sys
        sys.print_exception(e)
        
        # Emergency cleanup
        try:
            if 'main_solenoid' in globals() and main_solenoid is not None:
                main_solenoid.value(solenoid_active)
            if 'piston_solenoid' in globals() and piston_solenoid is not None:
                piston_solenoid.value(not solenoid_active)
            if 'led' in globals() and led is not None:
                led.value(0)
        except:
            pass