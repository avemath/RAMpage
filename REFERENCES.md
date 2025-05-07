# Software Resources & References

This file lists all open-source libraries, tools, and documentation used in the RAMpage 30lb Combat Robot project. Each entry includes the license type and its relevance to this project.

---

##  Core Languages and Frameworks

- **MicroPython v1.20** — *MIT License*  
  Used to program the Raspberry Pi Pico W.  
  https://github.com/micropython/micropython

- **Python v3.9** — *PSF License*  
  Used for scripting and video streaming on Raspberry Pi 4B.  
  https://docs.python.org/3/license.html

- **OpenCV v4.5.5** — *Apache 2.0 License*  
  Used for video frame capture, JPEG compression, and real-time overlays.  
  https://github.com/opencv/opencv

- **NumPy v1.23.5** — *BSD License*  
  Used for array conversion and buffer manipulation in video decoding.  
  https://numpy.org/doc/stable/user/index.html

---

##  Networking and Communication

- **Python socket module** — *PSF License*  
  Used for UDP video transmission between Pi and PC.  
  https://docs.python.org/3/library/socket.html

- **AFHDS 2A Protocol** 
  Used to decode PWM signals from FlySky iA6B receiver.  
  https://www.multi-module.org/using-the-module/protocol-details/flysky-afhds2a

---

##  Hardware Interfaces

- **RPi.GPIO v0.7.0** — *MIT License*  
  Used for low-level GPIO control on Raspberry Pi 4B.  
  https://pypi.org/project/RPi.GPIO/

- **PiCamera2 v0.3.9** — *BSD License*  
  Used for accessing the camera module via Picamera2 API.  
  https://github.com/raspberrypi/picamera2/tree/main  
  https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf

- **MicroPython `machine` and `Pin` Modules** — *MIT License*  
  Used for GPIO pin control, interrupts, and PWM input reading on Pico W.  
  https://docs.micropython.org/en/latest/library/machine.html  
  https://docs.micropython.org/en/latest/library/machine.Pin.html#machine.Pin.irq

---

##  Development References

- **Raspberry Pi Pico Python SDK**  
  GPIO, timing, and peripheral access reference for MicroPython.  
  https://datasheets.raspberrypi.com/pico/raspberry-pi-pico-python-sdk.pdf

- **MicroPython Interrupt Handling Rules**  
  Ensures ISR functions are fast, memory-safe, and minimal.  
  https://docs.micropython.org/en/latest/reference/isr_rules.html

- **Python Signal Handling**  
  Used for graceful shutdown via Ctrl+C on Raspberry Pi 4B.  
  https://docs.python.org/3/library/signal.html

---

##  Video Streaming and Compression

- **OpenCV: JPEG Compression Flags**  
  Used for quality adaptation in JPEG frame encoding.  
  https://docs.opencv.org/4.x/d8/d6a/group__imgcodecs__flags.html

- **MJPG-streamer (BSD License)**  
  Referenced for adaptive JPEG compression and UDP packet sizing.  
  https://github.com/jacksonliam/mjpg-streamer

- **PyImageSearch Tutorials**  
  Used for real-time image capture/display techniques.  
  https://pyimagesearch.com/

---

##  Safety and Control Systems

- **RioBotz Combat Tutorial**  
  Industry-standard safety and emergency stop system reference.  
  https://www.riobotz.com/riobotz-combot-tutorial

---

##  Debugging and Testing Tools

- **PuTTY** — *MIT License*  
  Used for SSH access and debugging during deployment.  
  https://www.chiark.greenend.org.uk/~sgtatham/putty/licence.html

- **Thonny IDE v4.0.1** — *MIT License*  
  Used to flash and debug MicroPython code on the Pico W.  
  https://github.com/thonny/thonny/tree/master

- **Wireshark v3.6.2** — *GPL v2*  
  Used to analyze network traffic during UDP streaming tests.  
  https://www.wireshark.org/docs/wsug_html_chunked/

---

##  Code Examples and Patterns

- **MicroPython PWM Reading Example** — *MIT License*  
  Used to build interrupt-based PWM readers on Pico W.  
  https://github.com/micropython/micropython/tree/master/examples/hwapi

- **GPIO Zero Documentation**  
  Used as a general reference for GPIO pin control patterns on Raspberry Pi.  
  https://gpiozero.readthedocs.io/en/stable/

---
