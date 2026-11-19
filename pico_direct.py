"""
RAMpage 30lb Combat Robot - Main Pico Code
Team 22: Avery, Nick, Chris, Miles, Matthew

Main controller for the Raspberry Pi Pico W:
- Drive pass-through: reads the two drive channels (CH2 = left motor,
  CH3 = right motor) from the FlySky receiver and re-creates the PWM signal
  for the two motor inputs of the 4-in-1 ESC. Because the drive signal now
  goes THROUGH the Pico, the emergency stop can force both motors to neutral.
- Reads weapon trigger and kill switch from the FlySky receiver
- Controls the pneumatic weapon system with an activation counter
- Emergency stop (kill switch, lost receiver signal, startup interlock)

WIRING (changed from the original "direct" version, see README):
    Receiver CH2 -> level shifter -> GP16      Receiver CH5 -> level shifter -> GP18
    Receiver CH3 -> level shifter -> GP17      Receiver CH6 -> level shifter -> GP19
    GP20 -> ESC left motor signal input  (this wire used to come from receiver CH2)
    GP21 -> ESC right motor signal input (this wire used to come from receiver CH3)
    Pico GND, receiver GND and ESC signal GND must all be connected together.
    Full table and diagram: hardware/WIRING.md

THINGS THE CODE CANNOT DO FOR ME (must be set up on the hardware):
1. Transmitter turned off / out of range: the iA6B receiver keeps sending
   pulses when it loses the transmitter, so the Pico cannot see that kind of
   signal loss by itself. In the transmitter failsafe menu, set CH5 to the ON
   (kill) position so a lost transmitter looks like a kill switch flip, and
   set CH2 and CH3 to center (1500), not to low throttle.
2. The Pico is now a single point of failure for driving. If this program
   stops, the watchdog resets the Pico, its pins stop sending pulses, and the
   ESC must stop the motors on "no signal". Bench test this with the wheels off the ground.
3. The exhaust valve is normally closed, so "exhaust open" needs power. If the
   Pico or the 12 V rail dies, the exhaust valve closes.

MIT License
"""

import machine
from machine import Pin, PWM
import utime
import sys

# ======= PIN CONFIG =======
# RC receiver input pins - FlySky iA6B (5 V signals, through the level shifter)
CH2_PIN = 16     # Left motor  (left stick up/down)
CH3_PIN = 17     # Right motor (right stick up/down)
CH5_PIN = 18     # SwA - Kill switch (top left)
CH6_PIN = 19     # SwD - Weapon trigger (top right)

# Drive output pins to the SEQURE 4-in-1 ESC (3.3 V servo-style PWM made by the Pico)
# GP20 and GP21 share one PWM slice, which is fine because both run at 50 Hz.
ESC_LEFT_PIN = 20    # Left motor signal, passes CH2 through
ESC_RIGHT_PIN = 21   # Right motor signal, passes CH3 through

# Solenoid pins - Normally Closed (NC) valves
MAIN_SOLENOID_PIN = 14    # Exhaust valve relay (open when idle)
PISTON_SOLENOID_PIN = 15  # Inlet valves relay (both reservoirs)

# ======= CONSTANTS =======
# RC signal constants - standard RC values (microseconds)
PWM_MIN = 1000      # 1 ms pulse (min)
PWM_MAX = 2000      # 2 ms pulse (max)
PWM_CENTER = 1500   # 1.5 ms pulse (center/neutral position)

# Drive output
ESC_PWM_FREQ = 50          # Hz - standard RC frame rate (one pulse every 20 ms)
DRIVE_NEUTRAL_US = 1500    # Pulse that means "stop" for a reversible ESC.
                           # NOTE: check this matches how the ESCs were calibrated.

# FlySky switch threshold
SWITCH_ON_THRESHOLD = 1700   # Above this value, switch is ON

# System timing (ms)
SIGNAL_TIMEOUT = 1000        # No valid pulse for this long = signal lost
SIGNAL_RECOVERY_TIME = 1000  # Signals must be good this long before auto reset
STARTUP_DELAY = 3000         # Wait at startup (drive held at neutral)
KILL_SWITCH_DEBOUNCE = 300   # Minimum time in emergency stop before reset
LOOP_DELAY = 5               # Main loop period
STATUS_INTERVAL = 3000       # Time between status prints

# Watchdog: resets the Pico if the main loop ever hangs for this long.
# NOTE: once started it cannot be turned off. After I press Stop in Thonny the
# Pico will reboot about 2 s later. Set USE_WATCHDOG = False for bench work.
USE_WATCHDOG = True
WATCHDOG_TIMEOUT = 2000      # ms

# Weapon system constants - values from weapon_latency_test.py testing results
MAX_WEAPON_ACTIVATIONS = 17          # Max weapon activations
WEAPON_COOLDOWN = 500                # ms - wait after a shot finishes
SOLENOID_ACTIVATION_TIME = 400       # ms - how long the inlets stay open
SOLENOID_SEQUENCE_DELAY = 50         # ms - delay between valve steps

# Weapon firing steps (the firing sequence is a small state machine so the
# main loop never stops to wait, and the kill switch works mid-shot)
WEAPON_IDLE = 0      # Exhaust open, inlets closed
WEAPON_HOME = 1      # Exhaust open for 50 ms (plow home)
WEAPON_DWELL = 2     # Exhaust closed, waiting 50 ms
WEAPON_EXTEND = 3    # Inlets open for 400 ms (plow out)

# ======= GLOBAL VARIABLES =======
# System state
emergency_stop = False
emergency_cause = "none"   # "none", "kill_switch", "signal_loss", "startup"
emergency_time = 0         # When the emergency stop started
last_signal_loss = 0       # Last time any channel was missing

# Weapon state
weapon_state = WEAPON_IDLE
weapon_state_start = 0     # When the current firing step started
weapon_activations = 0     # Number of times weapon has been activated
weapon_cooldown_end = 0    # Time when weapon can be activated again
weapon_depleted = False    # Whether we've hit max activations
# Starts True so the trigger has to be seen OFF before the first shot.
# (If SwD is already ON at power-up, nothing fires.)
weapon_trigger_last_state = True

led_state = -1             # Last value written to the LED

# ======= HARDWARE INITIALIZATION =======
print("\n===== RAMpage Combat Robot - Main Pico Code =====")

# Status LED. "LED" works on both the Pico and the Pico W
# (on the Pico W the LED is on the wireless chip, not on GP25).
# https://docs.micropython.org/en/latest/rp2/quickref.html
led = Pin("LED", Pin.OUT)
led.value(0)

# Drive outputs to the ESC - start at neutral before anything else happens
# https://docs.micropython.org/en/latest/library/machine.PWM.html
try:
    esc_left = PWM(Pin(ESC_LEFT_PIN))
    esc_right = PWM(Pin(ESC_RIGHT_PIN))
    esc_left.freq(ESC_PWM_FREQ)
    esc_right.freq(ESC_PWM_FREQ)
    esc_left.duty_ns(DRIVE_NEUTRAL_US * 1000)
    esc_right.duty_ns(DRIVE_NEUTRAL_US * 1000)
    print(f"Drive ESC outputs on GP{ESC_LEFT_PIN} and GP{ESC_RIGHT_PIN} (neutral)")
except Exception as e:
    print(f"Drive output setup failed: {e}")
    sys.exit(1)

# Solenoids
solenoid_active = 0  # Active-low relays
try:
    main_solenoid = Pin(MAIN_SOLENOID_PIN, Pin.OUT)
    piston_solenoid = Pin(PISTON_SOLENOID_PIN, Pin.OUT)

    main_solenoid.value(solenoid_active)          # Exhaust open
    piston_solenoid.value(not solenoid_active)    # Inlets closed

    print(f"Solenoids initialized on pins {MAIN_SOLENOID_PIN} and {PISTON_SOLENOID_PIN}")
except Exception as e:
    print(f"Solenoid initialization failed: {e}")
    sys.exit(1)


# ======= RC RECEIVER INPUT =======
class RCChannel:
    """
    Measures the pulse width of one RC receiver channel using an interrupt.

    Rising edge starts the timer, falling edge calculates the width.
    The handler only stores integers, which keeps it safe to run as an
    interrupt (no memory allocation).

    Sources:
    https://docs.micropython.org/en/latest/library/machine.Pin.html#machine.Pin.irq
    https://docs.micropython.org/en/latest/reference/isr_rules.html#writing-interrupt-handlers
    """

    def __init__(self, pin_number):
        self.pulse_start = 0
        self.pulse_width = 0     # Last valid pulse width in microseconds
        self.last_update = 0     # ticks_ms() of the last valid pulse
        self.seen = False        # True once at least one valid pulse arrived
        self.pin = Pin(pin_number, Pin.IN)
        self.pin.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=self.edge_handler)

    def edge_handler(self, pin):
        now = utime.ticks_us()
        if pin.value():  # Rising edge
            self.pulse_start = now
        else:  # Falling edge
            if self.pulse_start > 0:
                width = utime.ticks_diff(now, self.pulse_start)
                if 900 < width < 2100:  # Valid pulse range
                    self.pulse_width = width
                    self.last_update = utime.ticks_ms()
                    self.seen = True

    def lost(self, now):
        """True if this channel has no valid pulse within SIGNAL_TIMEOUT."""
        if not self.seen:
            return True
        return utime.ticks_diff(now, self.last_update) > SIGNAL_TIMEOUT

    def switch_on(self):
        """True if this channel is a switch in the ON position."""
        return self.pulse_width > SWITCH_ON_THRESHOLD


try:
    ch2 = RCChannel(CH2_PIN)   # Left motor
    ch3 = RCChannel(CH3_PIN)   # Right motor
    ch5 = RCChannel(CH5_PIN)   # Kill switch
    ch6 = RCChannel(CH6_PIN)   # Weapon trigger
    print(f"RC inputs: drive GP{CH2_PIN}/GP{CH3_PIN}, kill GP{CH5_PIN}, weapon GP{CH6_PIN}")
except Exception as e:
    print(f"RC interrupt setup failed: {e}")
    sys.exit(1)


# ======= HELPER FUNCTIONS =======
def any_signal_lost(now):
    """True if any of the four receiver channels has stopped sending pulses."""
    return ch2.lost(now) or ch3.lost(now) or ch5.lost(now) or ch6.lost(now)


def set_drive(left_us, right_us):
    """Send pulse widths (microseconds) to the left and right motor inputs, limited to 1000-2000."""
    left_us = min(max(left_us, PWM_MIN), PWM_MAX)
    right_us = min(max(right_us, PWM_MIN), PWM_MAX)
    esc_left.duty_ns(left_us * 1000)
    esc_right.duty_ns(right_us * 1000)


def drive_neutral():
    """Command both drive motors to stop."""
    esc_left.duty_ns(DRIVE_NEUTRAL_US * 1000)
    esc_right.duty_ns(DRIVE_NEUTRAL_US * 1000)


def solenoids_safe():
    """Put the valves in the safe state: inlets closed, exhaust open."""
    piston_solenoid.value(not solenoid_active)
    main_solenoid.value(solenoid_active)


def set_led(on):
    """Only write to the LED when it changes (the Pico W LED write is slow)."""
    global led_state
    on = 1 if on else 0
    if on != led_state:
        led.value(on)
        led_state = on


# ======= WEAPON =======
def start_weapon(now):
    """
    Start one firing sequence. Returns True if the sequence started.

    The sequence itself is stepped by update_weapon():
    1. Exhaust open, 50 ms (plow home)
    2. Exhaust closes, 50 ms dwell
    3. Inlets open, 400 ms (plow out)
    4. Inlets close, exhaust reopens (plow vents and retracts)
    """
    global weapon_state, weapon_state_start, weapon_activations, weapon_depleted

    if emergency_stop:
        print("Cannot activate weapon - emergency stop active")
        return False
    if weapon_state != WEAPON_IDLE:
        return False  # Already firing
    if weapon_depleted:
        print("Weapon depleted - maximum activations reached")
        return False
    if utime.ticks_diff(now, weapon_cooldown_end) < 0:
        print("Weapon in cooldown - wait before activating again")
        return False

    weapon_activations += 1
    print(f"Activating weapon ({weapon_activations}/{MAX_WEAPON_ACTIVATIONS})")
    if weapon_activations >= MAX_WEAPON_ACTIVATIONS:
        weapon_depleted = True
        print("WARNING: Weapon system depleted")

    # Step 1: exhaust open (plow home)
    main_solenoid.value(solenoid_active)
    weapon_state = WEAPON_HOME
    weapon_state_start = now
    return True


def update_weapon(now):
    """Move the firing sequence to its next step when the step time is up."""
    global weapon_state, weapon_state_start, weapon_cooldown_end

    if weapon_state == WEAPON_IDLE:
        return

    elapsed = utime.ticks_diff(now, weapon_state_start)

    if weapon_state == WEAPON_HOME and elapsed >= SOLENOID_SEQUENCE_DELAY:
        # Step 2: close exhaust, dwell
        main_solenoid.value(not solenoid_active)
        weapon_state = WEAPON_DWELL
        weapon_state_start = now

    elif weapon_state == WEAPON_DWELL and elapsed >= SOLENOID_SEQUENCE_DELAY:
        # Step 3: open inlets to extend the plow
        piston_solenoid.value(solenoid_active)
        weapon_state = WEAPON_EXTEND
        weapon_state_start = now

    elif weapon_state == WEAPON_EXTEND and elapsed >= SOLENOID_ACTIVATION_TIME:
        # Step 4: close inlets, reopen exhaust
        solenoids_safe()
        weapon_state = WEAPON_IDLE
        weapon_cooldown_end = utime.ticks_add(now, WEAPON_COOLDOWN)


def abort_weapon():
    """Stop a firing sequence right away and vent."""
    global weapon_state
    solenoids_safe()
    weapon_state = WEAPON_IDLE


# ======= EMERGENCY STOP =======
def trigger_emergency_stop(cause, now):
    """
    Emergency stop: both drive motors to neutral, inlets closed, exhaust open.

    This is a software stop. The removable link on the battery is still the
    real power cut-off, which follows the RioBotz advice that the main
    power switch must not depend on electronics.
    Source: https://www.riobotz.com/riobotz_combot_tutorial.pdf
    """
    global emergency_stop, emergency_cause, emergency_time

    if emergency_stop:
        return  # Already in emergency stop

    # Make everything safe FIRST, then do the bookkeeping
    drive_neutral()
    abort_weapon()

    emergency_stop = True
    emergency_cause = cause
    emergency_time = now
    print(f"EMERGENCY STOP ACTIVATED: {cause}")


def can_reset_emergency_stop(now, kill_switch_on, signal_lost):
    """
    Returns True if it is safe to leave emergency stop.

    For every cause the kill switch must be OFF and all four channels must
    be sending pulses. After a signal loss the signals also have to stay
    good for SIGNAL_RECOVERY_TIME.
    """
    if kill_switch_on or signal_lost:
        return False
    if utime.ticks_diff(now, emergency_time) < KILL_SWITCH_DEBOUNCE:
        return False
    if emergency_cause == "signal_loss":
        if utime.ticks_diff(now, last_signal_loss) < SIGNAL_RECOVERY_TIME:
            return False
    return True


def reset_emergency_stop():
    """Leave emergency stop."""
    global emergency_stop, emergency_cause
    print(f"Emergency stop reset (was: {emergency_cause}) - system ready")
    emergency_stop = False
    emergency_cause = "none"


def print_status(now):
    """Print current status info to console"""
    print("\n----- STATUS UPDATE -----")
    print(f"Kill switch: {'ON' if ch5.switch_on() else 'OFF'}")
    print(f"Weapon trigger: {'ON' if ch6.switch_on() else 'OFF'}")
    print(f"Emergency stop: {'ACTIVE' if emergency_stop else 'Inactive'}")
    print(f"Emergency cause: {emergency_cause}")
    print(f"Signal status: {'LOST' if any_signal_lost(now) else 'Good'}")
    print(f"Weapon activations: {weapon_activations}/{MAX_WEAPON_ACTIVATIONS}" +
          (" (DEPLETED)" if weapon_depleted else ""))
    print(f"Raw values - Left:{ch2.pulse_width} Right:{ch3.pulse_width} "
          f"Kill:{ch5.pulse_width} Weapon:{ch6.pulse_width}")


# ======= MAIN FUNCTION =======
def main():
    """
    Main loop. Nothing in here waits longer than LOOP_DELAY, so the drive
    pass-through and the kill switch are checked about every 5 ms.
    """
    global weapon_trigger_last_state, last_signal_loss, weapon_cooldown_end

    print("\n===== STARTING CONTROL SYSTEM =====")
    print("Waiting for RC signals to stabilize (drive held at neutral)...")

    # Startup delay. Drive stays at neutral, which also lets the ESC arm.
    startup_start = utime.ticks_ms()
    while utime.ticks_diff(utime.ticks_ms(), startup_start) < STARTUP_DELAY:
        set_led((utime.ticks_ms() % 500) < 250)
        utime.sleep_ms(50)

    now = utime.ticks_ms()
    last_signal_loss = now
    weapon_cooldown_end = now
    last_status_time = now

    # Startup interlock: kill switch ON at boot means start in emergency stop
    if ch5.seen and ch5.switch_on():
        print("Kill switch is ON during startup - must turn OFF to operate")
        trigger_emergency_stop("startup", now)

    print("System initialized")
    print(f"Maximum weapon activations: {MAX_WEAPON_ACTIVATIONS}")
    print("To RESET emergency stop: turn the kill switch OFF")

    # https://docs.micropython.org/en/latest/library/machine.WDT.html
    wdt = machine.WDT(timeout=WATCHDOG_TIMEOUT) if USE_WATCHDOG else None

    try:
        while True:
            now = utime.ticks_ms()
            if wdt:
                wdt.feed()

            if utime.ticks_diff(now, last_status_time) > STATUS_INTERVAL:
                print_status(now)
                last_status_time = now

            # Read RC channels
            kill_switch_on = ch5.switch_on()
            weapon_trigger_on = ch6.switch_on()
            signal_lost = any_signal_lost(now)
            if signal_lost:
                last_signal_loss = now

            # Emergency stop checks
            if not emergency_stop:
                if signal_lost:
                    trigger_emergency_stop("signal_loss", now)
                elif kill_switch_on:
                    trigger_emergency_stop("kill_switch", now)
            elif can_reset_emergency_stop(now, kill_switch_on, signal_lost):
                reset_emergency_stop()

            if emergency_stop:
                # Keep commanding the safe state every loop
                drive_neutral()
                solenoids_safe()
                # Keep tracking the trigger so a switch that was flipped ON
                # during the stop does not fire the weapon when the stop clears
                weapon_trigger_last_state = weapon_trigger_on
                set_led((now % 200) < 100)   # Fast blink = emergency stop
                utime.sleep_ms(LOOP_DELAY)
                continue

            # Drive pass-through: copy the stick pulses to the ESC
            set_drive(ch2.pulse_width, ch3.pulse_width)

            # Weapon: fire once on the OFF -> ON edge of the trigger
            if weapon_trigger_on and not weapon_trigger_last_state:
                start_weapon(now)
            weapon_trigger_last_state = weapon_trigger_on
            update_weapon(now)

            # LED status
            if weapon_state != WEAPON_IDLE:
                set_led(1)                                   # Solid = firing
            elif weapon_depleted:
                phase = now % 1000
                set_led(phase < 100 or 200 < phase < 300)    # Double blink = depleted
            else:
                set_led((now % 2000) < 500)                  # Slow pulse = ready

            utime.sleep_ms(LOOP_DELAY)

    except KeyboardInterrupt:
        print("\nControl system terminated by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.print_exception(e)
    finally:
        # Leave everything safe. If the watchdog is on, the Pico reboots
        # about 2 s after this because nothing feeds it anymore.
        drive_neutral()
        solenoids_safe()
        led.value(0)
        print("System stopped - drive neutral, solenoids safe")


# Run the program
if __name__ == "__main__":
    main()
