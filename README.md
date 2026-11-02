# RAMpage - 30lb Combat Robot

RAMpage is a 30-pound combat robot built by Team 22 (Avery, Nick, Chris, Miles, Matthew) for the Bengal Bot competition. The robot uses a pneumatic plow as its primary weapon - a system that demands precise timing, hard activation limits, and fail-safe behavior that must work correctly even under signal loss or electrical noise from combat.

The core engineering challenge is coordinating two independent controllers in real time. A Raspberry Pi 4B handles video streaming to the driver station while a Raspberry Pi Pico W manages weapon control and safety logic. Getting both systems to operate reliably under combat conditions - EMI, vibration, intermittent wireless - required careful design decisions at every layer.

---

## System Architecture

The system is split across two controllers, each responsible for what it does best.

**Raspberry Pi Pico W - Weapon and Safety**

The Pico W runs the weapon control loop. It reads PWM signals from the FlySky FS-iA6B receiver using hardware interrupts, sequences the pneumatic solenoid valves, enforces the activation limit and cooldown, and handles emergency stop logic. The Pico is the right choice here because it has deterministic real-time behavior - there's no Linux scheduler adding jitter to interrupt handlers, and MicroPython's `machine.Pin.irq` fires on every edge with microsecond-resolution timestamps. The weapon system cannot tolerate delayed or missed triggers.

Drive motors connect directly from the RC receiver to the ESCs - the Pico does not sit in that path. This means drive control has zero additional latency and no single point of failure through the microcontroller.

**Raspberry Pi 4B - Video**

The Pi 4B runs the camera and streams compressed frames over UDP to the driver's laptop. It uses Picamera2 (libcamera-based) for low-latency capture and OpenCV for JPEG encoding. The Pi 4B is the right choice here because it has the processing power to run the camera pipeline at 30 FPS while handling socket I/O, and it runs Linux, which is what Picamera2 requires.

The two systems are independent. A crash or hang on the video side does not affect weapon control, and vice versa.

---

## Weapon System

RAMpage uses a pneumatic plow. As built:

- **Two reservoirs:** seamless aluminum, rated 200 psi, charged before a match from an external compressor through a Schrader valve. There is no compressor on the robot (vibration, power and weight).
- **Two inlet valves (GP15):** each reservoir has its own quarter-inch inlet solenoid valve (12 V, 8.5 W). Both open together; in the code they are `piston_solenoid`. They feed one shared supply line.
- **Two cylinders:** the shared line drives two pneumatic cylinders, one above the other, each with its own rod, both pushing the one plow. About 80 lbf per cylinder at 200 psi.
- **One exhaust valve (GP14):** a half-inch outlet solenoid valve (12 V, 16 W) branches off the shared line to atmosphere; in the code it is `main_solenoid`. It is a branch to atmosphere, not a stage between the reservoirs and the cylinders. It sits open when idle so the plow stays pulled in, and it is forced open on any error or emergency stop.

**Firing Sequence**

Each activation follows a fixed valve sequence:

1. Exhaust open, 50 ms (plow home)
2. Exhaust closes
3. 50 ms dwell
4. Both inlets open, 400 ms (plow out, full extension)
5. Inlets close
6. Exhaust reopens (the plow vents and retracts)

**Activation Limits**

The pneumatic system has a finite air supply. The Pico enforces a hard limit of **17 activations** in firmware. The team's air analysis found that only about the first **six** cycles deliver more than 30 lbf before reservoir pressure drops too far (predicted five, measured six); later cycles still fire, with less force. After 17 fires, the weapon is locked out and the LED pattern switches to a rapid double-blink. A 500 ms cooldown is enforced between each activation to prevent valve damage from rapid cycling.

**Safety Logic**

The Pico implements three emergency stop triggers:

- **Kill switch (SwA/CH5):** Flipping the kill switch on puts the system into emergency stop immediately. The ESCs enter failsafe mode, cutting drive power. To recover, the kill switch must be returned to OFF, at which point the Pico resets after a 300 ms debounce.
- **Signal loss:** If either CH5 or CH6 goes more than 1000 ms without a valid PWM pulse, the Pico treats this as a lost transmitter and triggers emergency stop. It recovers automatically once both signals return.
- **Startup interlock:** If the kill switch is ON when the Pico boots, it enters emergency stop immediately and waits for the operator to turn it off before allowing any operation.

In emergency stop, all solenoids are reset to their safe state (exhaust open, inlets closed), and the LED blinks rapidly to indicate the condition.

---

## Video System

The Pi 4B streams camera frames from a Picamera2 camera over UDP to the driver's laptop, which runs the receiver script on Windows.

**Why UDP**

TCP's retransmission and acknowledgment overhead adds latency that compounds at 30 FPS. In a live control environment, a stale frame displayed on time is more useful than a fresh frame delivered 200 ms late. UDP sends each frame independently - a dropped frame is simply skipped, and the display moves on to the next one.

**Adaptive JPEG Compression**

Each frame is JPEG-encoded before transmission. The Pi targets quality 80, but if a frame encodes larger than 65,000 bytes (just under the UDP maximum of 65,507), it automatically steps down through quality levels: 80 → 75 → 70 → 65 → 60 → 55 → 50. If no quality level produces a packet that fits, the frame is skipped. This keeps every transmitted frame within a single UDP packet, avoiding fragmentation.

Camera settings are tuned for the combat environment: sharpness 2.5 (identify other robots), contrast 1.2 (better edge definition), brightness slightly raised, noise reduction at minimum (lower latency at the cost of some grain). A timestamp and FPS counter are burned into each frame, which also lets the driver assess stream latency visually.

**No Signal Detection**

The receiver script on the laptop monitors frame arrival time. If no frame arrives within 3 seconds, the display switches to a black "NO SIGNAL" screen. When frames resume, it reconnects automatically. The stream uses Tailscale for the network link between the robot and the driver station.

---

## Controls

| Input | Channel | Function |
|---|---|---|
| Left stick | CH1/CH2 | Drive (direct to ESCs) |
| Right stick | CH3/CH4 | Drive (direct to ESCs) |
| SwA (top left, 2-pos) | CH5 | Kill switch - ON triggers emergency stop |
| SwD (top right, 2-pos) | CH6 | Weapon trigger - edge-triggered, fires once per press |

The weapon fires on the rising edge of SwD, not while held. Holding the trigger down does not fire repeatedly - the Pico detects the OFF→ON transition and fires once, then waits for the trigger to be released before it can fire again.

---

## Hardware

- Raspberry Pi 4B (video streaming)
- Raspberry Pi Pico W (weapon and safety control)
- FlySky FS-iA6B RC receiver
- Picamera2-compatible Pi camera
- 2× solenoid valves (normally closed): main reservoir valve + piston valve
- Pneumatic reservoir and plow mechanism
- Drive ESCs (connected directly to receiver)

---

## Testing Scripts

**`temp_test.py`** - Reads CPU temperature from `/sys/class/thermal/thermal_zone0/temp` on the Pi 4B every second for 60 seconds and reports max and average. The safe operating limit is 85°C; the script warns at 80°C. This matters because the Pi 4B runs encoding and socket I/O simultaneously inside a robot with limited airflow - thermal throttling would drop the stream frame rate at the worst possible moment.

**`weapon_latency_test.py`** - Runs on the Pico W and measures the time between the weapon trigger rising edge (SwD/CH6) and the physical solenoid response, detected via an interrupt on the main solenoid monitoring pin. Latency values under 200 ms are recorded; the target is under 50 ms. Reports min, max, and average across all activations during a 30-second window. The results from this test informed the final values in `pico_direct.py` - specifically `MAX_WEAPON_ACTIVATIONS = 17` and the solenoid timing constants.

---

## Setup and Deployment

**Pico W (weapon controller)**

Flash MicroPython firmware onto the Pico W, then copy `pico_direct.py` to the device. The script runs automatically on boot.

**Pi 4B (video streaming)**

Install dependencies:
```sh
sudo apt install python3-picamera2
pip install opencv-python numpy
```

SSH into the Pi from the driver's laptop, then start the stream:
```sh
python3 pi4_direct.py --ip <tailscale-laptop-ip>
```

**Driver station (laptop)**

Run the receiver in PowerShell:
```sh
python video_direct.py
```

Optional flags: `--fullscreen`, `--debug`, `--port <n>` (default 5000).

**Testing**

Temperature test (run on Pi 4B):
```sh
python3 temp_test.py
```

Weapon latency test (copy to Pico W and run via REPL or on boot):
```sh
import weapon_latency_test
```
