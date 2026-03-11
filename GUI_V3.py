import cv2
import tkinter as tk
from tkinter import Label, Button, filedialog
from PIL import Image, ImageTk
import numpy as np
import mido
import time

midi_out = mido.open_output('loopMIDI Port 1')

TARGET_WIDTH = 1280
TARGET_HEIGHT = 720


class VideoPlayer:
    def __init__(self, root):

        self.root = root
        self.root.title("OpenCV MOV Player - Circular MIDI Sampler")

        self.cap = None
        self.playing = False

        self.current_frame = None

        self.root.geometry(f"{TARGET_WIDTH}x{TARGET_HEIGHT + 100}")
        self.root.resizable(False, False)

        # --- Circle parameters ---
        self.circle_x = TARGET_WIDTH // 2
        self.circle_y = TARGET_HEIGHT // 2
        self.radius = 50
        self.min_radius = 10
        self.max_radius = 300

        # --- MIDI smoothing ---
        self.smooth_val = 0
        self.alpha = 0.5
        self.last_note = None
        self.last_sent_time = 0
        self.midi_interval = 0.05

        # --- Multi-CC smoothing ---
        self.smooth_r = 0.0
        self.smooth_g = 0.0
        self.smooth_b = 0.0
        self.smooth_radius = 0.0

        self.last_cc_values = {
            18: -1,
            19: -1,
            20: -1,
            21: -1
        }

        self.last_cc_time = 0
        self.cc_interval = 0.02  # 50Hz max
        self.cc_threshold = 1  # ignore tiny changes

        # --- CC smoothing ---
        self.smooth_r = 0.0
        self.last_cc18 = -1
        self.last_sent = 0
        self.change_threshold = 1

        # --- Scale settings ---
        self.scale_lock = True  # default ON
        self.c_major = [0, 2, 4, 5, 7, 9, 11]

        # --- UI ---
        self.label = Label(root)
        self.label.pack()

        self.label.bind("<Button-1>", self.move_circle)
        self.label.bind("<MouseWheel>", self.resize_circle)

        self.pixel_info = Label(root, text="Brightness: -", font=("Arial", 14))
        self.pixel_info.pack(pady=5)

        Button(root, text="Open MOV File", command=self.open_file).pack(side="left", padx=5)
        Button(root, text="Play", command=self.play_video).pack(side="left", padx=5)
        Button(root, text="Pause", command=self.pause_video).pack(side="left", padx=5)
        Button(root, text="Exit", command=self.close).pack(side="left", padx=5)
        Button(root, text="Toggle C Major Lock", command=self.toggle_scale).pack(side="left", padx=5)

        Button(root, text="Macro 1 Run", command=lambda: self.play_run(18)).pack(side="left", padx=5)
        Button(root, text="Macro 2 Run", command=lambda: self.play_run(19)).pack(side="left", padx=5)
        Button(root, text="Macro 3 Run", command=lambda: self.play_run(20)).pack(side="left", padx=5)
        Button(root, text="Macro 4 Run", command=lambda: self.play_run(21)).pack(side="left", padx=5)

        self.update_frame()

    def send_cc(self, cc_number, normalized_value, smooth_attr):

        # Smooth value (0.0–1.0)
        current = getattr(self, smooth_attr)
        smoothed = self.alpha * normalized_value + (1 - self.alpha) * current
        setattr(self, smooth_attr, smoothed)

        cc_value = int(smoothed * 127)

        # Rate limit
        now = time.time()
        if now - self.last_cc_time < self.cc_interval:
            return

        # Ignore tiny change
        if abs(cc_value - self.last_cc_values[cc_number]) < self.cc_threshold:
            return

        midi_out.send(
            mido.Message(
                'control_change',
                channel=0,
                control=cc_number,
                value=cc_value
            )
        )

        self.last_cc_values[cc_number] = cc_value
        self.last_cc_time = now


    # ------------------ MIDI ------------------
    def toggle_scale(self):
        self.scale_lock = not self.scale_lock
        print("C Major Lock:", "ON" if self.scale_lock else "OFF")

    def quantize_to_c_major(self, note):

        octave = note // 12
        note_in_octave = note % 12

        closest = min(self.c_major, key=lambda x: abs(x - note_in_octave))

        return octave * 12 + closest

    def send_midi(self, brightness):

       #self.smooth_val = self.alpha * brightness + (1 - self.alpha) * self.smooth_val
        self.smooth_val = brightness

        note = int(self.smooth_val / 255 * 48) + 36

        if self.scale_lock:
         note = self.quantize_to_c_major(note)

        now = time.time()
        if now - self.last_sent_time < self.midi_interval:
            return

        self.last_sent_time = now

        if note != self.last_note:

            if self.last_note is not None:
                midi_out.send(mido.Message('note_off', note=self.last_note))

            midi_out.send(mido.Message('note_on', note=note, velocity=100))

            self.last_note = note

    def play_run(self, cc_number):

        # Normalized ascending values (0.0 → 1.0)
        steps = [0.0, 0.25, 0.5, 0.75, 1.0]

        for norm in steps:
            cc_value = int(norm * 127)

            midi_out.send(
                mido.Message(
                    'control_change',
                    channel=0,
                    control=cc_number,
                    value=cc_value
                )
            )

            self.root.update()
            time.sleep(0.08)

    # ------------------ Video ------------------

    def open_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("MOV files", "*.mov"), ("All files", "*.*")]
        )
        if file_path:
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(file_path)
            self.playing = True

    def play_video(self):
        self.playing = True

    def pause_video(self):
        self.playing = False

    def fit_to_window(self, frame):
        h, w = frame.shape[:2]
        scale = min(TARGET_WIDTH / w, TARGET_HEIGHT / h)

        new_w = int(w * scale)
        new_h = int(h * scale)

        resized = cv2.resize(frame, (new_w, new_h))

        canvas = np.zeros((TARGET_HEIGHT, TARGET_WIDTH, 3), dtype=np.uint8)

        x_offset = (TARGET_WIDTH - new_w) // 2
        y_offset = (TARGET_HEIGHT - new_h) // 2

        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized

        return canvas

    # ------------------ Mouse Controls ------------------

    def move_circle(self, event):
        self.circle_x = event.x
        self.circle_y = event.y

    def resize_circle(self, event):
        if event.delta > 0:
            self.radius += 5
        else:
            self.radius -= 5

        self.radius = max(self.min_radius, min(self.radius, self.max_radius))

    # ------------------ Sampling ------------------

    def compute_circle_average(self):

        if self.current_frame is None:
            return

        mask = np.zeros(self.current_frame.shape[:2], dtype=np.uint8)

        cv2.circle(mask, (self.circle_x, self.circle_y), self.radius, 255, -1)

        region = cv2.bitwise_and(self.current_frame, self.current_frame, mask=mask)

        pixels = region[mask == 255]

        if len(pixels) == 0:
            return

        avg_color = pixels.mean(axis=0)
        r, g, b = avg_color.astype(int)

        brightness = (r + g + b) / 3
        self.pixel_info.config(text=f"RGB: {r}, {g}, {b}")

        # Normalize RGB 0–255 → 0–1
        r_norm = r / 255.0
        g_norm = g / 255.0
        b_norm = b / 255.0

        # Normalize radius
        radius_norm = (self.radius - self.min_radius) / (self.max_radius - self.min_radius)

        # Send CCs
        self.send_cc(18, r_norm, "smooth_r")  # Macro 1
        self.send_cc(19, g_norm, "smooth_g")  # Macro 2
        self.send_cc(20, b_norm, "smooth_b")  # Macro 3
        self.send_cc(21, radius_norm, "smooth_radius")  # Macro 4

        # Keep your note output
        self.send_midi(brightness)

    # ------------------ Update Loop ------------------

    def update_frame(self):

        if self.cap and self.playing:

            ret, frame = self.cap.read()

            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return

            frame = self.fit_to_window(frame)

            # draw circle
            cv2.circle(frame,
                       (self.circle_x, self.circle_y),
                       self.radius,
                       (0, 255, 0),
                       2)

            self.current_frame = frame.copy()

            self.compute_circle_average()

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)

            self.label.imgtk = imgtk
            self.label.configure(image=imgtk)

        self.root.after(30, self.update_frame)

    def close(self):

        if self.cap:
            self.cap.release()

        if self.last_note is not None:
            midi_out.send(mido.Message('note_off', note=self.last_note))

        self.root.destroy()


root = tk.Tk()
player = VideoPlayer(root)
root.mainloop()
