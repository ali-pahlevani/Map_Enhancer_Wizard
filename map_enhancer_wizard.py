import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
import yaml
import os

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event):
        if self.tip_window or not self.text:
            return
        x, y = self.widget.winfo_rootx() + 25, self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("Arial", 12))
        label.pack()

    def hide_tip(self, event):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class MapEnhancerWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Map Enhancer Wizard (V1)")
        self.geometry("1200x800")
        self.original_map = None
        self.processed_map = None
        self.map_metadata = None
        self.original_folder_name = ""
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.init_ui()

    def init_ui(self):
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 12, "bold"), foreground="red")
        self.style.configure("TLabel", font=("Arial", 14, "bold"))

        # Main frame with grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        # Left: Controls frame
        self.controls_frame = ttk.Frame(self, padding=10, relief=tk.RAISED)
        self.controls_frame.grid(row=0, column=0, sticky="nsew")

        # Right: Map preview canvas
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=1, highlightbackground="gray")
        self.canvas.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        # Bottom: Status bar
        self.status_frame = ttk.Frame(self, relief=tk.SUNKEN)
        self.status_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status_label = ttk.Label(self.status_frame, text="Select a map folder to begin.")
        self.status_label.pack(side=tk.LEFT, padx=5, pady=2)
        self.progress = ttk.Progressbar(self.status_frame, mode="indeterminate", length=100)
        self.progress.pack(side=tk.RIGHT, padx=5, pady=2)

        # Controls frame content
        #ttk.Label(self.controls_frame, text="Map Enhancer Controls", font=("Arial", 20, "bold")).pack(pady=(0, 10))

        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)
        self.select_btn = ttk.Button(self.controls_frame, text="Select Map Folder", command=self.select_folder)
        self.select_btn.pack(fill=tk.X, pady=5)
        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)

        # Filter sliders
        self.threshold_var = tk.DoubleVar(value=0.5)
        self.threshold_slider = ttk.Scale(self.controls_frame, from_=0.0, to=1.0, variable=self.threshold_var, command=self.update_preview)
        ttk.Label(self.controls_frame, text="Threshold (0-1)").pack(pady=5)
        self.threshold_slider.pack(fill=tk.X, pady=10)
        ToolTip(self.threshold_slider, "Binarize the map: lower values increase occupied areas.")
        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)

        self.blur_var = tk.IntVar(value=0)
        self.blur_slider = ttk.Scale(self.controls_frame, from_=0, to=5, variable=self.blur_var, command=self.update_preview)
        ttk.Label(self.controls_frame, text="Blur Kernel Size").pack(pady=5)
        self.blur_slider.pack(fill=tk.X, pady=10)
        ToolTip(self.blur_slider, "Smooth noise with Gaussian blur.")
        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)

        self.dilation_var = tk.IntVar(value=0)
        self.dilation_slider = ttk.Scale(self.controls_frame, from_=0, to=10, variable=self.dilation_var, command=self.update_preview)
        ttk.Label(self.controls_frame, text="Dilation Kernel Size").pack(pady=5)
        self.dilation_slider.pack(fill=tk.X, pady=10)
        ToolTip(self.dilation_slider, "Thicken obstacles for safer navigation.")
        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)

        self.erosion_var = tk.IntVar(value=0)
        self.erosion_slider = ttk.Scale(self.controls_frame, from_=0, to=10, variable=self.erosion_var, command=self.update_preview)
        ttk.Label(self.controls_frame, text="Erosion Kernel Size").pack(pady=5)
        self.erosion_slider.pack(fill=tk.X, pady=10)
        ToolTip(self.erosion_slider, "Thin obstacles to refine the map.")
        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)

        self.opening_var = tk.IntVar(value=0)
        self.opening_slider = ttk.Scale(self.controls_frame, from_=0, to=5, variable=self.opening_var, command=self.update_preview)
        ttk.Label(self.controls_frame, text="Opening Kernel Size").pack(pady=5)
        self.opening_slider.pack(fill=tk.X, pady=10)
        ToolTip(self.opening_slider, "Remove small objects/noise.")
        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)

        # Buttons
        self.save_btn = ttk.Button(self.controls_frame, text="Save Enhanced Map", command=self.save_map)
        self.save_btn.pack(fill=tk.X, pady=10)
        self.reset_btn = ttk.Button(self.controls_frame, text="Reset All Filters", command=self.reset_filters)
        self.reset_btn.pack(fill=tk.X, pady=10)

        # Bind events
        self.bind("<Configure>", self.on_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_pan_start)
        self.canvas.bind("<B1-Motion>", self.on_pan_move)
        self.canvas.bind("<MouseWheel>", self.on_zoom)

    def select_folder(self):
        self.progress.start()
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.load_map(folder_path)
        self.progress.stop()

    def load_map(self, folder_path):
        pgm_file = next((os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(".pgm")), None)
        yaml_file = next((os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(".yaml")), None)
        if not pgm_file or not yaml_file:
            messagebox.showerror("Error", "Missing PGM or YAML file.")
            return

        with open(yaml_file, 'r') as f:
            self.map_metadata = yaml.safe_load(f)
        self.original_map = cv2.imread(pgm_file, cv2.IMREAD_GRAYSCALE)
        if self.original_map is None:
            messagebox.showerror("Error", "Failed to load map.")
            return

        self.original_folder_name = os.path.basename(folder_path)
        self.status_label.config(text=f"Map loaded: {self.original_folder_name}")
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update_preview()

    def apply_filters(self):
        if self.original_map is None:
            return
        map_copy = self.original_map.copy()

        # Blur
        if (blur := self.blur_var.get()) > 0:
            ksize = 2 * blur + 1
            map_copy = cv2.GaussianBlur(map_copy, (ksize, ksize), 0)

        # Threshold
        thresh = self.threshold_var.get() * 255
        map_copy = np.where(map_copy <= thresh, 0, 255).astype(np.uint8)

        # Opening
        if (opening := self.opening_var.get()) > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (opening, opening))
            map_copy = cv2.morphologyEx(map_copy, cv2.MORPH_OPEN, kernel)

        # Dilation
        if (dilation := self.dilation_var.get()) > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (dilation, dilation))
            map_copy = cv2.dilate(map_copy, kernel)

        # Erosion
        if (erosion := self.erosion_var.get()) > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (erosion, erosion))
            map_copy = cv2.erode(map_copy, kernel)

        self.processed_map = map_copy

    def update_preview(self, *args):
        self.apply_filters()
        if self.processed_map is not None:
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            map_height, map_width = self.processed_map.shape
            scale = min(canvas_width / map_width, canvas_height / map_height) * self.zoom_factor
            preview_width = int(map_width * scale)
            preview_height = int(map_height * scale)
            preview = cv2.resize(self.processed_map, (preview_width, preview_height), interpolation=cv2.INTER_NEAREST)
            self.photo = ImageTk.PhotoImage(Image.fromarray(preview))
            self.canvas.delete("all")
            x = (canvas_width - preview_width) / 2 + self.pan_x
            y = (canvas_height - preview_height) / 2 + self.pan_y
            self.canvas.create_image(x, y, anchor=tk.NW, image=self.photo)

    def on_resize(self, event):
        self.update_preview()

    def on_pan_start(self, event):
        self.pan_start_x = event.x
        self.pan_start_y = event.y

    def on_pan_move(self, event):
        delta_x = event.x - self.pan_start_x
        delta_y = event.y - self.pan_start_y
        self.pan_x += delta_x
        self.pan_y += delta_y
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.update_preview()

    def on_zoom(self, event):
        scale = 1.1 if event.delta > 0 else 0.9
        self.zoom_factor *= scale
        self.update_preview()

    def save_map(self):
        if self.processed_map is None:
            messagebox.showerror("Error", "No map to save.")
            return
        self.progress.start()
        save_folder = filedialog.askdirectory()
        if save_folder:
            folder_name = os.path.basename(save_folder)
            pgm_file = os.path.join(save_folder, f"{folder_name}.pgm")
            yaml_file = os.path.join(save_folder, f"{folder_name}.yaml")
            cv2.imwrite(pgm_file, self.processed_map)
            self.map_metadata['image'] = f"{folder_name}.pgm"
            with open(yaml_file, 'w') as f:
                yaml.dump(self.map_metadata, f, default_flow_style=None, sort_keys=False)
            self.status_label.config(text=f"Map saved to {save_folder}")
            messagebox.showinfo("Success", "Map saved successfully.")
        self.progress.stop()

    def reset_filters(self):
        self.threshold_var.set(0.5)
        self.blur_var.set(0)
        self.dilation_var.set(0)
        self.erosion_var.set(0)
        self.opening_var.set(0)
        self.update_preview()

if __name__ == "__main__":
    app = MapEnhancerWizard()
    app.mainloop()