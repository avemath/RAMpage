"""
RAMpage 30lb Combat Robot - Drive Output Identification Test
Team 22: Avery, Nick, Chris, Miles, Matthew

Finds out which wheel each Pico drive output controls, and which way it
spins, so I can set SWAP_LEFT_RIGHT / INVERT_LEFT / INVERT_RIGHT in
pico_direct.py.

How to run:
1. WHEELS OFF THE GROUND. Reservoirs empty. Battery link in.
2. Transmitter on, kill switch (SwA) OFF.
3. Open this file in Thonny and run it. It asks me to press Enter before
   each spin, so nothing moves until I say so.
4. Write down which wheel spun and which way for each step, then answer
   the questions printed at the end.

Safety:
- Spins at a low speed (SPIN_OFFSET_US above neutral) for SPIN_TIME_MS.
- Flipping the kill switch ON, or losing the CH5 signal, stops the spin
  right away and ends the test.
- Both outputs go back to neutral when the test ends or crashes.

Wiring is the same as pico_direct.py (see hardware/WIRING.md):
GP18 = CH5 kill switch input, GP20 / GP21 = drive outputs to the ESC.

MIT License
"""

from machine import Pin, PWM
import utime

# ======= PIN CONFIG (must match pico_direct.py) =======
CH5_PIN = 18          # Kill switch input
ESC_LEFT_PIN = 20     # Output the code CALLS "left"
ESC_RIGHT_PIN = 21    # Output the code CALLS "right"

# ======= TEST SETTINGS =======
ESC_PWM_FREQ = 50         # Hz
NEUTRAL_US = 1500         # ESC is bidirectional, 1500 us = stop
SPIN_OFFSET_US = 100      # 1600 us = slow forward. Raise a little if a wheel won't turn.
SPIN_TIME_MS = 2000       # How long each spin lasts
ARM_TIME_MS = 3000        # Neutral at start so the ESC arms
SWITCH_ON_THRESHOLD = 1700
SIGNAL_TIMEOUT_MS = 1000

# ======= KILL SWITCH INPUT =======
# Same pulse-width measurement as pico_direct.py
# https://docs.micropython.org/en/latest/library/machine.Pin.html#machine.Pin.irq
ch5_start = 0
ch5_width = 0
ch5_last = 0


def ch5_handler(pin):
    global ch5_start, ch5_width, ch5_last
    now = utime.ticks_us()
    if pin.value():
        ch5_start = now
    elif ch5_start > 0:
        width = utime.ticks_diff(now, ch5_start)
        if 900 < width < 2100:
            ch5_width = width
            ch5_last = utime.ticks_ms()


ch5 = Pin(CH5_PIN, Pin.IN)
ch5.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=ch5_handler)


def kill_or_lost():
    """True if the kill switch is ON or CH5 has stopped sending pulses."""
    if ch5_last == 0:
        return True
    if utime.ticks_diff(utime.ticks_ms(), ch5_last) > SIGNAL_TIMEOUT_MS:
        return True
    return ch5_width > SWITCH_ON_THRESHOLD


# ======= DRIVE OUTPUTS =======
# https://docs.micropython.org/en/latest/library/machine.PWM.html
outputs = {
    "GP{} (code calls this LEFT)".format(ESC_LEFT_PIN): PWM(Pin(ESC_LEFT_PIN)),
    "GP{} (code calls this RIGHT)".format(ESC_RIGHT_PIN): PWM(Pin(ESC_RIGHT_PIN)),
}


def all_neutral():
    for pwm in outputs.values():
        pwm.duty_ns(NEUTRAL_US * 1000)


for pwm in outputs.values():
    pwm.freq(ESC_PWM_FREQ)
all_neutral()


def spin(pwm):
    """Spin one output slowly forward. Returns False if stopped by the kill switch."""
    pwm.duty_ns((NEUTRAL_US + SPIN_OFFSET_US) * 1000)
    start = utime.ticks_ms()
    try:
        while utime.ticks_diff(utime.ticks_ms(), start) < SPIN_TIME_MS:
            if kill_or_lost():
                return False
            utime.sleep_ms(10)
        return True
    finally:
        pwm.duty_ns(NEUTRAL_US * 1000)


def main():
    print("\n===== RAMpage Drive Output Identification Test =====")
    print("WHEELS MUST BE OFF THE GROUND.")
    print("Holding neutral for {} s so the ESC arms...".format(ARM_TIME_MS // 1000))
    utime.sleep_ms(ARM_TIME_MS)

    if kill_or_lost():
        print("Kill switch is ON or no receiver signal. Turn the transmitter on,")
        print("kill switch OFF, then run again.")
        return

    for name, pwm in outputs.items():
        input("\nPress Enter to spin {} slowly FORWARD for {} s...".format(
            name, SPIN_TIME_MS // 1000))
        print("Spinning {} ... watch which wheel moves and which way.".format(name))
        if not spin(pwm):
            print("STOPPED: kill switch ON or signal lost. Test ended.")
            return
        print("Done. Write down: which wheel (left/right) and direction (fwd/back).")

    print("\n===== Set these in pico_direct.py =====")
    print("SWAP_LEFT_RIGHT = True  if the 'LEFT' output spun the RIGHT wheel")
    print("INVERT_LEFT     = True  if the LEFT wheel spun BACKWARD")
    print("INVERT_RIGHT    = True  if the RIGHT wheel spun BACKWARD")
    print("Then copy which ESC pads (M1-M4) those wires are on into hardware/WIRING.md.")


try:
    main()
finally:
    all_neutral()
    print("Outputs at neutral. Test over.")
