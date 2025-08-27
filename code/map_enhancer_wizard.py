import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
import yaml
import os
import math
import platform
from collections import deque

APP_TITLE = "Map Enhancer Wizard (V2)"

# ----------------------------- Utilities -----------------------------

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default

def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

def cv_to_photo(img):
    """Accepts uint8 grayscale or 3-channel BGR; returns PhotoImage."""
    if img.ndim == 2:
        pil = Image.fromarray(img)
    else:
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    return ImageTk.PhotoImage(pil)

def linux_mousewheel_bind(widget, up_cb, down_cb):
    """Make wheel work across platforms."""
    sys = platform.system()
    if sys == "Windows":
        widget.bind("<MouseWheel>", lambda e: (up_cb() if e.delta > 0 else down_cb()))
    elif sys == "Darwin":
        widget.bind("<MouseWheel>", lambda e: (up_cb() if e.delta > 0 else down_cb()))
    else:
        widget.bind("<Button-4>", lambda e: up_cb())
        widget.bind("<Button-5>", lambda e: down_cb())

def morphological_kernel(size):
    size = clamp(int(size), 1, 99)
    # force odd > 0
    if size % 2 == 0:
        size += 1
    return cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))


# ----------------------------- ToolTip -----------------------------

class ToolTip:
    def __init__(self, widget, text, delay_ms=350):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.after_id = None
        self.delay_ms = delay_ms
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _):
        self._cancel()
        self.after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Arial", 10),
            padx=6,
            pady=4,
        )
        label.pack()

    def _hide(self, _=None):
        self._cancel()
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


# ----------------------------- Main App -----------------------------

class MapEnhancerWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1000, 700)

        # state
        self.original_map = None          # uint8 grayscale
        self.processed_map = None         # uint8 grayscale
        self.map_metadata = {}
        self.original_folder_name = ""
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.pan_start = None
        self.photo_cache = None  # keep a reference
        self.preview_mode = tk.StringVar(value="enhanced")  # "original"|"enhanced"|"side_by_side"
        self.show_grid = tk.BooleanVar(value=False)
        self.invert_view = tk.BooleanVar(value=False)

        # params (tk variables for live UI)
        self.threshold_var = tk.DoubleVar(value=0.5)  # 0..1 mapped to 0..255
        self.use_adaptive = tk.BooleanVar(value=False)
        self.blur_var = tk.IntVar(value=0)            # gaussian sigma size-ish (0=off)
        self.median_var = tk.IntVar(value=0)          # median filter kernel (0=off)
        self.opening_var = tk.IntVar(value=0)         # morph open kernel
        self.closing_var = tk.IntVar(value=0)         # morph close kernel
        self.dilation_var = tk.IntVar(value=0)
        self.erosion_var = tk.IntVar(value=0)

        self.metrics_label_var = tk.StringVar(value="")
        self.zoom_label_var = tk.StringVar(value="100%")

        # undo/redo stacks of parameter snapshots
        self.history = deque(maxlen=50)
        self.future = deque(maxlen=50)

        self._build_ui()
        self._bind_keys()

    # ------------------------- UI -------------------------

    def _build_ui(self):
        # Style
        style = ttk.Style()
        style.configure("TButton", font=("Arial", 11, "bold"))
        style.configure("TLabel", font=("Arial", 11))
        style.configure("Header.TLabel", font=("Arial", 12, "bold"))
        style.configure("Small.TLabel", font=("Arial", 9))

        # Layout
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Left controls (with notebook)
        controls = ttk.Frame(self, padding=(10, 10))
        controls.grid(row=0, column=0, sticky="ns")

        nb = ttk.Notebook(controls)
        nb.pack(fill="both", expand=True)

        # --- Tab: Controls ---
        tab_controls = ttk.Frame(nb, padding=(10, 10))
        nb.add(tab_controls, text="Controls")

        # File actions
        file_frame = ttk.LabelFrame(tab_controls, text="Map I/O", padding=10)
        file_frame.pack(fill="x", expand=False)
        ttk.Button(file_frame, text="Select Map Folder", command=self.select_folder).pack(fill="x", pady=4)
        ttk.Button(file_frame, text="Save Enhanced Map", command=self.save_map).pack(fill="x", pady=4)
        ttk.Button(file_frame, text="Fit to Window (F)", command=self.fit_to_window).pack(fill="x", pady=4)

        # Preview opts
        preview_frame = ttk.LabelFrame(tab_controls, text="Preview", padding=10)
        preview_frame.pack(fill="x", expand=False, pady=(10, 0))
        for mode, label in [("original", "Original"), ("enhanced", "Enhanced"), ("side_by_side", "Side-by-Side")]:
            ttk.Radiobutton(preview_frame, text=label, value=mode, variable=self.preview_mode, command=self.update_preview).pack(anchor="w")
        ttk.Checkbutton(preview_frame, text="Show Grid", variable=self.show_grid, command=self.update_preview).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(preview_frame, text="Invert View (visual only)", variable=self.invert_view, command=self.update_preview).pack(anchor="w")

        # Filters
        filt = ttk.LabelFrame(tab_controls, text="Filters & Morphology", padding=10)
        filt.pack(fill="x", expand=False, pady=(10, 0))

        def add_slider(parent, text, var, from_, to_, step=1, cb=None, tooltip=None):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=text).pack(side="left")
            val_lbl = ttk.Label(row, textvariable=tk.StringVar(value=str(var.get())), width=4, anchor="e")
            val_lbl.pack(side="right")
            scale = ttk.Scale(row, from_=from_, to=to_, orient="horizontal",
                              command=lambda _=None, v=var, l=val_lbl: self._on_scale_change(v, l, cb),
                              variable=var)
            scale.pack(fill="x", padx=8)
            if tooltip:
                ToolTip(scale, tooltip)
            return scale

        self._s_thresh = add_slider(filt, "Threshold (0..1)", self.threshold_var, 0.0, 1.0, 0.01,
                                    cb=self.update_preview, tooltip="Binarization cutoff before morphology. Use 'Adaptive' for tricky lighting/noise.")
        ttk.Checkbutton(filt, text="Use Adaptive Threshold (local)", variable=self.use_adaptive, command=self.update_preview).pack(anchor="w", pady=(0, 6))

        self._s_gauss = add_slider(filt, "Gaussian Blur (px)", self.blur_var, 0, 9, 1,
                                   cb=self.update_preview, tooltip="Smooth small variations before thresholding (odd kernel auto-selected).")
        self._s_median = add_slider(filt, "Median Filter (px)", self.median_var, 0, 9, 1,
                                    cb=self.update_preview, tooltip="Salt-and-pepper noise removal (odd kernel).")

        self._s_open = add_slider(filt, "Opening (px)", self.opening_var, 0, 15, 1,
                                  cb=self.update_preview, tooltip="Remove tiny speckles (erode then dilate).")
        self._s_close = add_slider(filt, "Closing (px)", self.closing_var, 0, 15, 1,
                                   cb=self.update_preview, tooltip="Fill tiny gaps/holes (dilate then erode).")
        self._s_dil = add_slider(filt, "Dilation (px)", self.dilation_var, 0, 15, 1,
                                 cb=self.update_preview, tooltip="Thicken obstacles or close narrow gaps.")
        self._s_ero = add_slider(filt, "Erosion (px)", self.erosion_var, 0, 15, 1,
                                 cb=self.update_preview, tooltip="Thin obstacles / remove edge artifacts.")

        # Actions
        act = ttk.LabelFrame(tab_controls, text="Actions", padding=10)
        act.pack(fill="x", expand=False, pady=(10, 0))
        ttk.Button(act, text="Auto-Enhance (A)", command=self.auto_enhance).pack(fill="x", pady=4)
        ttk.Button(act, text="Reset All Filters (R)", command=self.reset_filters).pack(fill="x", pady=4)
        ttk.Button(act, text="Undo (Ctrl+Z)", command=self.undo).pack(fill="x", pady=4)
        ttk.Button(act, text="Redo (Ctrl+Y)", command=self.redo).pack(fill="x", pady=4)

        # --- Tab: Metadata ---
        tab_meta = ttk.Frame(nb, padding=(10, 10))
        nb.add(tab_meta, text="Metadata")
        self.meta_text = tk.Text(tab_meta, width=36, height=18, wrap="none")
        self.meta_text.configure(font=("Courier New", 10))
        self.meta_text.pack(fill="both", expand=True)

        # Canvas & status
        right = ttk.Frame(self, padding=(4, 4))
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(right, bg="white", highlightthickness=1, highlightbackground="#d0d0d0")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Status bar
        status = ttk.Frame(self, relief=tk.SUNKEN)
        status.grid(row=1, column=0, columnspan=2, sticky="ew")
        status.grid_columnconfigure(1, weight=1)
        ttk.Label(status, text="Zoom:").grid(row=0, column=0, sticky="w", padx=(8, 4))
        ttk.Label(status, textvariable=self.zoom_label_var).grid(row=0, column=1, sticky="w")
        ttk.Label(status, textvariable=self.metrics_label_var).grid(row=0, column=2, sticky="e", padx=8)

        # Bind
        self.bind("<Configure>", lambda e: self.update_preview())
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_drag)
        self.canvas.bind("<Double-Button-1>", lambda e: self.fit_to_window())
        linux_mousewheel_bind(self.canvas, self._zoom_in, self._zoom_out)

    def _bind_keys(self):
        self.bind("f", lambda e: self.fit_to_window())
        self.bind("F", lambda e: self.fit_to_window())
        self.bind("a", lambda e: self.auto_enhance())
        self.bind("A", lambda e: self.auto_enhance())
        self.bind("r", lambda e: self.reset_filters())
        self.bind("R", lambda e: self.reset_filters())
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Escape>", lambda e: self._center_preview())

    def _on_scale_change(self, var, label_widget, callback):
        # Normalize and clamp ints where appropriate
        if isinstance(var, (tk.IntVar,)):
            var.set(clamp(safe_int(var.get()), 0, 99))
        elif isinstance(var, (tk.DoubleVar,)):
            var.set(clamp(safe_float(var.get()), 0.0, 1.0))
        label_widget.configure(text=str(var.get()))
        self._push_history_snapshot()
        if callback:
            callback()

    # ------------------------- Map I/O -------------------------

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing .pgm and .yaml")
        if not folder:
            return
        try:
            pgm_file = next((os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pgm")), None)
            yaml_file = next((os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".yaml")), None)
            if not pgm_file or not yaml_file:
                messagebox.showerror("Error", "Missing .pgm or .yaml in selected folder.")
                return

            with open(yaml_file, "r") as fd:
                meta = yaml.safe_load(fd) or {}
                if not isinstance(meta, dict):
                    meta = {}
                self.map_metadata = meta

            img = cv2.imread(pgm_file, cv2.IMREAD_GRAYSCALE)
            if img is None or img.size == 0:
                messagebox.showerror("Error", "Failed to load PGM image.")
                return

            self.original_map = img
            self.processed_map = img.copy()
            self.original_folder_name = os.path.basename(folder)
            self.zoom_factor = 1.0
            self.pan_x = 0
            self.pan_y = 0
            self._update_meta_text(pgm_file, yaml_file)
            self._clear_history()
            self._push_history_snapshot()  # initial state
            self.update_preview()
            self._status(f"Loaded: {self.original_folder_name} ({img.shape[1]}×{img.shape[0]})")

        except Exception as ex:
            messagebox.showerror("Error", f"Failed to load folder:\n{ex}")

    def save_map(self):
        if self.processed_map is None:
            messagebox.showerror("Error", "No map to save.")
            return
        save_folder = filedialog.askdirectory(title="Pick a folder to save the enhanced map")
        if not save_folder:
            return
        try:
            folder_name = os.path.basename(save_folder) or "enhanced_map"
            pgm_file = os.path.join(save_folder, f"{folder_name}.pgm")
            yaml_file = os.path.join(save_folder, f"{folder_name}.yaml")

            ok = cv2.imwrite(pgm_file, self.processed_map)
            if not ok:
                raise RuntimeError("cv2.imwrite failed")

            meta = dict(self.map_metadata) if isinstance(self.map_metadata, dict) else {}
            meta["image"] = f"{folder_name}.pgm"
            with open(yaml_file, "w") as fd:
                yaml.safe_dump(meta, fd, default_flow_style=False, sort_keys=False)

            self._status(f"Saved to: {save_folder}")
            messagebox.showinfo("Success", f"Map saved:\n{pgm_file}\n{yaml_file}")

        except Exception as ex:
            messagebox.showerror("Error", f"Failed to save:\n{ex}")

    def _update_meta_text(self, pgm_path, yaml_path):
        self.meta_text.delete("1.0", tk.END)
        res = self.map_metadata.get("resolution", "(unknown)")
        origin = self.map_metadata.get("origin", "(unknown)")
        image_name = self.map_metadata.get("image", os.path.basename(pgm_path))
        mode = self.map_metadata.get("mode", "(n/a)")
        negate = self.map_metadata.get("negate", "(n/a)")
        occ_th = self.map_metadata.get("occupied_thresh", "(n/a)")
        free_th = self.map_metadata.get("free_thresh", "(n/a)")
        lines = [
            f"PGM:    {image_name}",
            f"YAML:   {os.path.basename(yaml_path)}",
            "",
            f"resolution: {res}",
            f"origin:     {origin}",
            f"mode:       {mode}",
            f"negate:     {negate}",
            f"occupied_thresh: {occ_th}",
            f"free_thresh:     {free_th}",
        ]
        self.meta_text.insert("1.0", "\n".join(lines))

    # ------------------------- Processing -------------------------

    def apply_filters(self):
        """Build output from original using current parameters."""
        if self.original_map is None:
            return None

        img = self.original_map.copy()

        # Denoise pre-threshold
        med = clamp(int(self.median_var.get()), 0, 99)
        if med > 0:
            k = med if med % 2 == 1 else med + 1
            img = cv2.medianBlur(img, k)

        g = clamp(int(self.blur_var.get()), 0, 99)
        if g > 0:
            k = g if g % 2 == 1 else g + 1
            img = cv2.GaussianBlur(img, (k, k), 0)

        # Threshold
        if self.use_adaptive.get():
            # adaptive mean threshold; block size auto from image size
            block = max(15, (min(img.shape[:2]) // 30) | 1)  # odd
            th_img = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                           cv2.THRESH_BINARY, block, 5)
        else:
            thr = clamp(float(self.threshold_var.get()), 0.0, 1.0)
            _, th_img = cv2.threshold(img, int(thr * 255), 255, cv2.THRESH_BINARY)

        # Morphology sequence
        out = th_img

        op = clamp(int(self.opening_var.get()), 0, 99)
        if op > 0:
            out = cv2.morphologyEx(out, cv2.MORPH_OPEN, morphological_kernel(op))

        cl = clamp(int(self.closing_var.get()), 0, 99)
        if cl > 0:
            out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, morphological_kernel(cl))

        dil = clamp(int(self.dilation_var.get()), 0, 99)
        if dil > 0:
            out = cv2.dilate(out, morphological_kernel(dil))

        ero = clamp(int(self.erosion_var.get()), 0, 99)
        if ero > 0:
            out = cv2.erode(out, morphological_kernel(ero))

        self.processed_map = out
        return out

    # ------------------------- Auto Enhance -------------------------

    def auto_enhance(self):
        """Analyze map + YAML and auto-tune parameters."""
        if self.original_map is None:
            messagebox.showwarning("No Map", "Load a map first.")
            return

        img = self.original_map

        # 1) Estimate basic stats
        hist = cv2.calcHist([img], [0], None, [256], [0, 256]).flatten()
        total = img.size
        mean_val = float((hist * np.arange(256)).sum() / max(total, 1))
        # Laplacian variance as noise indicator
        lap = cv2.Laplacian(img, cv2.CV_64F)
        lap_var = float(lap.var())

        # 2) Choose threshold automatically (Otsu), fallback to mid if fails
        try:
            _ret, otsu = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            thr = _ret / 255.0
            use_adapt = False
            # If histogram is very flat or lap_var high, prefer adaptive
            if lap_var > 120.0:
                use_adapt = True
                thr = 0.5
        except Exception:
            thr = 0.5
            use_adapt = False

        # 3) Rough noise level -> blur/median
        # tuned heuristics (empirical but safe):
        #   low noise: lap_var < 30, med: 30..120, high: > 120
        if lap_var < 30:
            g, med = 0, 0
        elif lap_var < 120:
            g, med = 1, 1
        else:
            g, med = 3, 3

        # 4) Build a quick binary with the chosen threshold to inspect obstacles
        if use_adapt:
            block = max(15, (min(img.shape[:2]) // 30) | 1)
            bw = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                       cv2.THRESH_BINARY, block, 5)
        else:
            _, bw = cv2.threshold(img, int(thr * 255), 255, cv2.THRESH_BINARY)

        # Decide which value represents obstacles: look at ends of histogram
        # Assume obstacles are darker in typical ROS maps; verify by sampling
        dark_ratio = hist[:64].sum() / total
        bright_ratio = hist[192:].sum() / total
        obstacles_are_black = dark_ratio >= bright_ratio

        bin_obs = (bw == (0 if obstacles_are_black else 255)).astype(np.uint8) * 255

        # 5) Estimate wall thickness using distance transform
        if bin_obs.max() > 0:
            dist = cv2.distanceTransform(bin_obs, cv2.DIST_L2, 3)
            # consider only near-surface points (avoid giant filled rooms)
            edge = cv2.Canny(bin_obs, 50, 150)
            dvals = dist[edge > 0]
            mean_thick = float(dvals.mean() * 2.0) if dvals.size else 1.0
        else:
            mean_thick = 1.0

        # 6) Compute occupancy
        known_mask = (img != 205) if 205 in np.unique(img) else np.ones_like(img, dtype=bool)
        occ_ratio = float((bin_obs > 0).sum()) / float(known_mask.sum() + 1e-6)

        # 7) Use YAML resolution for sensible physical goals
        res_m = safe_float(self.map_metadata.get("resolution", 0.05), 0.05)  # default 5 cm
        target_wall_m = 0.15  # target min wall thickness in meters (15 cm typical lidar map)
        target_px = clamp(int(round(target_wall_m / max(res_m, 1e-6))), 1, 15)

        # 8) Decide morphology
        dilation = 0
        erosion = 0
        opening = 0
        closing = 0

        # remove pepper noise
        if occ_ratio < 0.02 or lap_var > 120:
            opening = clamp(int(round(0.05 / res_m)), 0, 7)

        # fill tiny gaps along walls/doors
        closing = clamp(int(round(0.04 / res_m)), 0, 7)

        # bring walls toward target thickness
        if mean_thick < target_px:
            dilation = clamp(int(round(target_px - mean_thick)), 0, 8)
        elif mean_thick > target_px * 1.8:
            erosion = clamp(int(round(mean_thick - target_px)), 0, 8)

        # Soft limits and sanity
        if opening and erosion:
            # opening already erodes; avoid double-eroding too hard
            erosion = max(0, erosion - 1)

        # 9) Push the tuned parameters into the UI and refresh
        self.threshold_var.set(round(thr, 3))
        self.use_adaptive.set(bool(use_adapt))
        self.blur_var.set(int(g))
        self.median_var.set(int(med))
        self.opening_var.set(int(opening))
        self.closing_var.set(int(closing))
        self.dilation_var.set(int(dilation))
        self.erosion_var.set(int(erosion))

        self._push_history_snapshot()
        self.update_preview()

        # 10) Status summary
        self._status(
            f"Auto-Enhance applied | lapVar={lap_var:.1f} meanPix={mean_val:.1f} "
            f"wall≈{mean_thick:.1f}px target≈{target_px}px occ={occ_ratio*100:.1f}%"
        )

    # ------------------------- Preview & Canvas -------------------------

    def fit_to_window(self):
        if self.processed_map is None:
            return
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        h, w = self.processed_map.shape
        scale = min(cw / w, ch / h)
        self.zoom_factor = scale
        self.pan_x = 0
        self.pan_y = 0
        self.update_preview()

    def _center_preview(self):
        self.pan_x = 0
        self.pan_y = 0
        self.update_preview()

    def _zoom_in(self):
        self.zoom_factor *= 1.1
        self._update_zoom_label()
        self.update_preview()

    def _zoom_out(self):
        self.zoom_factor *= 0.9
        self.zoom_factor = max(self.zoom_factor, 0.05)
        self._update_zoom_label()
        self.update_preview()

    def _update_zoom_label(self):
        self.zoom_label_var.set(f"{int(self.zoom_factor*100):d}%")

    def _on_pan_start(self, ev):
        self.pan_start = (ev.x, ev.y)

    def _on_pan_drag(self, ev):
        if not self.pan_start:
            return
        dx = ev.x - self.pan_start[0]
        dy = ev.y - self.pan_start[1]
        self.pan_x += dx
        self.pan_y += dy
        self.pan_start = (ev.x, ev.y)
        self.update_preview()

    def _compose_preview_image(self):
        """Create the preview image based on selected mode and flags."""
        if self.processed_map is None or self.original_map is None:
            return None

        mode = self.preview_mode.get()
        if mode == "original":
            base = self.original_map
        elif mode == "enhanced":
            base = self.processed_map
        else:
            # side by side
            h1, w1 = self.original_map.shape
            h2, w2 = self.processed_map.shape
            h = max(h1, h2)
            canvas = np.full((h, w1 + w2 + 4), 255, np.uint8)
            canvas[:h1, :w1] = self.original_map
            canvas[:h2, w1 + 4:w1 + 4 + w2] = self.processed_map
            base = canvas

        img = base.copy()

        # Visual invert (for display only)
        if self.invert_view.get():
            img = 255 - img

        # Optional grid overlay for scale/inspection
        if self.show_grid.get():
            step = max(20, min(img.shape[0], img.shape[1]) // 20)
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            for x in range(0, img.shape[1], step):
                cv2.line(img, (x, 0), (x, img.shape[0]-1), (180, 180, 180), 1, cv2.LINE_AA)
            for y in range(0, img.shape[0], step):
                cv2.line(img, (0, y), (img.shape[1]-1, y), (180, 180, 180), 1, cv2.LINE_AA)
        else:
            # keep grayscale for sharper view
            if img.ndim != 2:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        return img

    def update_preview(self):
        # Recompute processed map
        self.apply_filters()
        if self.processed_map is None:
            return

        # Update metrics quick glance
        try:
            occ_black = (self.processed_map == 0).sum()
            occ_white = (self.processed_map == 255).sum()
            total = self.processed_map.size
            occ_ratio = occ_black / max(total, 1)
            self.metrics_label_var.set(f"Obstacles≈{occ_ratio*100:.1f}% | size {self.processed_map.shape[1]}×{self.processed_map.shape[0]}")
        except Exception:
            pass

        # Compose preview image
        img = self._compose_preview_image()
        if img is None:
            return

        # Scale to canvas
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        h, w = img.shape[:2]
        scale = min(cw / w, ch / h) * self.zoom_factor
        if scale <= 0:
            return

        new_w = clamp(int(w * scale), 1, 10000)
        new_h = clamp(int(h * scale), 1, 10000)
        interp = cv2.INTER_NEAREST if scale >= 1.0 else cv2.INTER_AREA
        disp = cv2.resize(img, (new_w, new_h), interpolation=interp)

        self.photo_cache = cv_to_photo(disp)
        self.canvas.delete("all")
        x = (cw - new_w) // 2 + int(self.pan_x)
        y = (ch - new_h) // 2 + int(self.pan_y)
        self.canvas.create_image(x, y, anchor=tk.NW, image=self.photo_cache)

    # ------------------------- History -------------------------

    def _snapshot(self):
        return dict(
            threshold=float(self.threshold_var.get()),
            adaptive=bool(self.use_adaptive.get()),
            blur=int(self.blur_var.get()),
            median=int(self.median_var.get()),
            opening=int(self.opening_var.get()),
            closing=int(self.closing_var.get()),
            dilation=int(self.dilation_var.get()),
            erosion=int(self.erosion_var.get()),
        )

    def _apply_snapshot(self, s):
        self.threshold_var.set(float(s.get("threshold", 0.5)))
        self.use_adaptive.set(bool(s.get("adaptive", False)))
        self.blur_var.set(int(s.get("blur", 0)))
        self.median_var.set(int(s.get("median", 0)))
        self.opening_var.set(int(s.get("opening", 0)))
        self.closing_var.set(int(s.get("closing", 0)))
        self.dilation_var.set(int(s.get("dilation", 0)))
        self.erosion_var.set(int(s.get("erosion", 0)))

    def _clear_history(self):
        self.history.clear()
        self.future.clear()

    def _push_history_snapshot(self):
        # push only if changed from last
        snap = self._snapshot()
        if not self.history or self.history[-1] != snap:
            self.history.append(snap)
            self.future.clear()

    def undo(self):
        if len(self.history) <= 1:
            return
        cur = self.history.pop()  # remove current
        self.future.appendleft(cur)
        prev = self.history[-1]
        self._apply_snapshot(prev)
        self.update_preview()

    def redo(self):
        if not self.future:
            return
        nxt = self.future.popleft()
        self.history.append(nxt)
        self._apply_snapshot(nxt)
        self.update_preview()

    # ------------------------- Misc -------------------------

    def reset_filters(self):
        self.threshold_var.set(0.5)
        self.use_adaptive.set(False)
        self.blur_var.set(0)
        self.median_var.set(0)
        self.opening_var.set(0)
        self.closing_var.set(0)
        self.dilation_var.set(0)
        self.erosion_var.set(0)
        self._push_history_snapshot()
        self.update_preview()
        self._status("Filters reset.")

    def _status(self, msg):
        self.title(f"{APP_TITLE} — {msg}")


if __name__ == "__main__":
    app = MapEnhancerWizard()
    app.mainloop()
