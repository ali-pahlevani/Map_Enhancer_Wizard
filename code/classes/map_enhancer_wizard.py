# Main application class for the Map Enhancer Wizard, handling UI, map processing,
# and filtering. Delegates optimization tasks to the Optimizer class.

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
import yaml
import os
from collections import deque
from classes.tooltip import ToolTip
from classes.optimizer import Optimizer
from utils.clamp import clamp
from utils.safe_float import safe_float
from utils.cv_to_photo import cv_to_photo
from utils.linux_mousewheel_bind import linux_mousewheel_bind
from utils.morphological_kernel import morphological_kernel

# Application title constant
APP_TITLE = "Map Enhancer Wizard (V2)"

class MapEnhancerWizard(tk.Tk):
    def __init__(self):
        # Initialize Tkinter root window
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")  # Default window size
        self.minsize(1000, 700)   # Minimum window size

        # Map state variables
        self.original_map = None          # Original loaded PGM image
        self.filter_input_map = None      # Base image for filtering
        self.processed_map = None         # Latest filtered/optimized map
        self.map_metadata = {}            # YAML metadata
        self.original_folder_name = ""     # Name of loaded folder

        # Canvas interaction state
        self.zoom_factor = 1.0            # Zoom level for canvas
        self.pan_x = 0                    # Horizontal pan offset
        self.pan_y = 0                    # Vertical pan offset
        self.pan_start = None             # Starting point for panning
        self.photo_cache = None           # Cached PhotoImage for canvas
        self.last_draw = {"scale": 1.0, "ox": 0, "oy": 0}  # Canvas drawing parameters

        # UI state variables
        self.preview_mode = tk.StringVar(value="enhanced")  # Preview mode: "original", "enhanced", "side_by_side"
        self.show_grid = tk.BooleanVar(value=False)        # Toggle grid overlay
        self.invert_view = tk.BooleanVar(value=False)      # Toggle inverted display
        self.active_tab = "Filtering"                      # Current notebook tab
        self.show_cp_overlay = False                       # Show control points in Optimization tab

        # Filter parameters
        self.threshold_var = tk.DoubleVar(value=0.5)       # Threshold (0..1 mapped to 0..255)
        self.use_adaptive = tk.BooleanVar(value=False)     # Use adaptive thresholding
        self.blur_var = tk.IntVar(value=0)                # Gaussian blur kernel size
        self.median_var = tk.IntVar(value=0)              # Median filter kernel size
        self.opening_var = tk.IntVar(value=0)             # Opening morphology size
        self.closing_var = tk.IntVar(value=0)             # Closing morphology size
        self.dilation_var = tk.IntVar(value=0)            # Dilation morphology size
        self.erosion_var = tk.IntVar(value=0)             # Erosion morphology size

        # Status bar labels
        self.metrics_label_var = tk.StringVar(value="")    # Displays map metrics
        self.zoom_label_var = tk.StringVar(value="100%")   # Displays current zoom level

        # Undo/redo history
        self.history = deque(maxlen=50)                   # Past filter states
        self.future = deque(maxlen=50)                    # Redo stack

        # Optimizer instance for control point management
        self.optimizer = Optimizer(self)

        # Build UI and bind keyboard shortcuts
        self._build_ui()
        self._bind_keys()

    def _build_ui(self):
        # Configure modern styling with ttk
        style = ttk.Style()
        try:
            style.theme_use("clam")  # Use modern 'clam' theme
        except Exception:
            pass

        # Define color palette
        ACCENT = "#3C82F6"      # Primary button color
        ACCENT_DK = "#2F6BCE"   # Button hover/pressed color
        SURFACE = "#F7F9FC"     # Background color
        CARD = "#FFFFFF"        # Card background
        TEXT = "#1F2937"        # Text color
        MUTED = "#6B7280"       # Muted text color
        BORDER = "#E5E7EB"      # Border color

        # Configure widget styles
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), background=SURFACE, foreground=TEXT)
        style.configure("Small.TLabel", font=("Segoe UI", 9), background=SURFACE, foreground=MUTED)
        style.configure("TFrame", background=SURFACE)
        style.configure("Card.TLabelframe", background=SURFACE, relief="flat")
        style.configure("Card.TLabelframe.Label", background=SURFACE, foreground=TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background=SURFACE, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8), font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", CARD)], expand=[("selected", [1, 1, 1, 0])])
        style.configure("Modern.TButton", font=("Segoe UI", 10, "bold"), padding=(10, 8), background=ACCENT, foreground="#FFFFFF", borderwidth=0)
        style.map("Modern.TButton", background=[("active", ACCENT_DK), ("pressed", ACCENT_DK)])
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT)
        style.configure("TRadiobutton", background=SURFACE, foreground=TEXT)
        style.configure("TScale", background=SURFACE)
        self.configure(bg=SURFACE)

        # Set up main layout with resizable panes
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.paned = tk.PanedWindow(self, orient="horizontal", sashwidth=6, bg=SURFACE, bd=0, sashrelief="flat")
        self.paned.grid(row=0, column=0, sticky="nsew")

        # Left pane: scrollable controls
        left_outer = ttk.Frame(self, style="TFrame")
        self._build_left_scrollable(left_outer)
        self.paned.add(left_outer, minsize=260)  # Minimum width for left pane

        # Right pane: canvas for map display
        right = ttk.Frame(self, padding=(4, 4), style="TFrame")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(right, bg="#FAFAFF", highlightthickness=1, highlightbackground=BORDER)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.paned.add(right)

        # Status bar at bottom
        status = ttk.Frame(self, style="TFrame")
        status.grid(row=1, column=0, sticky="ew")
        status.grid_columnconfigure(1, weight=1)
        border = tk.Frame(status, height=1, bg=BORDER)
        border.grid(row=0, column=0, columnspan=3, sticky="ew")
        ttk.Label(status, text="Zoom:", style="Small.TLabel").grid(row=1, column=0, sticky="w", padx=(8, 4), pady=6)
        ttk.Label(status, textvariable=self.zoom_label_var, style="Small.TLabel").grid(row=1, column=1, sticky="w")
        ttk.Label(status, textvariable=self.metrics_label_var, style="Small.TLabel").grid(row=1, column=2, sticky="e", padx=8)

        # Bind window resize and canvas interactions
        self.bind("<Configure>", self._enforce_split_and_refresh)
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)  # Middle-click to start panning
        self.canvas.bind("<B2-Motion>", self._on_pan_drag)       # Middle-drag to pan
        linux_mousewheel_bind(self.canvas, self._on_wheel)       # Mouse wheel for zooming
        self.canvas.bind("<Shift-Double-Button-1>", lambda e: self.fit_to_window())  # Shift+double-click to fit
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_click)  # Left-click for control points
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)  # Double-click to remove connections

    def _build_left_scrollable(self, parent):
        # Create a scrollable container for left-side controls
        shell = ttk.Frame(parent, padding=(8, 8), style="TFrame")
        shell.pack(fill="both", expand=True)
        self.left_canvas = tk.Canvas(shell, highlightthickness=0, bg="#F7F9FC")
        vscroll = ttk.Scrollbar(shell, orient="vertical", command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=vscroll.set)
        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        # Host frame for controls inside canvas
        self.controls_host = ttk.Frame(self.left_canvas, style="TFrame")
        self.controls_host_id = self.left_canvas.create_window((0, 0), window=self.controls_host, anchor="nw")

        # Sync canvas width with viewport
        def _sync_width(event):
            self.left_canvas.itemconfig(self.controls_host_id, width=event.width)
        self.left_canvas.bind("<Configure>", _sync_width)

        # Update scroll region when content changes
        def _update_scrollregion(_=None):
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))
        self.controls_host.bind("<Configure>", _update_scrollregion)

        # Notebook for tabbed interface
        nb = ttk.Notebook(self.controls_host, style="TNotebook")
        self.nb = nb
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        nb.pack(fill="both", expand=True)

        # Filtering tab
        tab_controls = ttk.Frame(nb, padding=(10, 10), style="TFrame")
        nb.add(tab_controls, text="Filtering")
        self._build_filtering_tab(tab_controls)

        # Optimization tab (delegated to Optimizer)
        tab_opt = ttk.Frame(nb, padding=(10, 10), style="TFrame")
        nb.add(tab_opt, text="Optimization")
        self.optimizer.build_ui(tab_opt)

        # Metadata tab
        tab_meta = ttk.Frame(nb, padding=(10, 10), style="TFrame")
        nb.add(tab_meta, text="Metadata")
        self.meta_text = tk.Text(tab_meta, width=36, height=18, wrap="none")
        self.meta_text.configure(font=("Consolas", 10), bd=0, highlightbackground="#E5E7EB")
        self.meta_text.pack(fill="both", expand=True)

    def _build_filtering_tab(self, parent):
        # File I/O section
        file_frame = ttk.Labelframe(parent, text="Map I/O", padding=10, style="Card.TLabelframe")
        file_frame.pack(fill="x", expand=False)
        ttk.Button(file_frame, text="Select Map Folder", command=self.select_folder, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(file_frame, text="Save Enhanced Map", command=self.save_map, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(file_frame, text="Fit to Window (F)", command=self.fit_to_window, style="Modern.TButton").pack(fill="x", pady=4)

        # Preview options section
        preview_frame = ttk.Labelframe(parent, text="Preview", padding=10, style="Card.TLabelframe")
        preview_frame.pack(fill="x", expand=False, pady=(10, 0))
        for mode, label in [("original", "Original"), ("enhanced", "Enhanced"), ("side_by_side", "Side-by-Side")]:
            ttk.Radiobutton(preview_frame, text=label, value=mode, variable=self.preview_mode, command=self.update_preview).pack(anchor="w")
        ttk.Checkbutton(preview_frame, text="Show Grid", variable=self.show_grid, command=self.update_preview).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(preview_frame, text="Invert View (visual only)", variable=self.invert_view, command=self.update_preview).pack(anchor="w")

        # Filter controls section
        filt = ttk.Labelframe(parent, text="Filters & Morphology", padding=10, style="Card.TLabelframe")
        filt.pack(fill="x", expand=False, pady=(10, 0))

        # Helper function to create sliders with tooltips
        def add_slider(parent, text, var, from_, to_, step=1, cb=None, tooltip=None):
            row = ttk.Frame(parent, style="TFrame")
            row.pack(fill="x", pady=6)
            ttk.Label(row, text=text).pack(side="left")
            val_lbl = ttk.Label(row, textvariable=tk.StringVar(value=str(var.get())), width=6, anchor="e")
            val_lbl.pack(side="right")
            scale = ttk.Scale(row, from_=from_, to=to_, orient="horizontal",
                              command=lambda _=None, v=var, l=val_lbl: self._on_scale_change(v, l, cb),
                              variable=var)
            scale.pack(fill="x", padx=8)
            if tooltip:
                ToolTip(scale, tooltip)
            return scale

        # Add filter sliders
        add_slider(filt, "Threshold (0..1)", self.threshold_var, 0.0, 1.0, 0.01, cb=self.update_preview,
                   tooltip="Binarization cutoff before morphology. Use 'Adaptive' for tricky lighting/noise.")
        ttk.Checkbutton(filt, text="Use Adaptive Threshold (local)", variable=self.use_adaptive, command=self.update_preview).pack(anchor="w", pady=(0, 6))
        add_slider(filt, "Gaussian Blur (px)", self.blur_var, 0, 9, 1, cb=self.update_preview,
                   tooltip="Smooth small variations before thresholding (odd kernel auto-selected).")
        add_slider(filt, "Median Filter (px)", self.median_var, 0, 9, 1, cb=self.update_preview,
                   tooltip="Salt-and-pepper noise removal (odd kernel).")
        add_slider(filt, "Opening (px)", self.opening_var, 0, 15, 1, cb=self.update_preview,
                   tooltip="Remove tiny speckles (erode then dilate).")
        add_slider(filt, "Closing (px)", self.closing_var, 0, 15, 1, cb=self.update_preview,
                   tooltip="Fill tiny gaps/holes (dilate then erode).")
        add_slider(filt, "Dilation (px)", self.dilation_var, 0, 15, 1, cb=self.update_preview,
                   tooltip="Thicken obstacles or close narrow gaps.")
        add_slider(filt, "Erosion (px)", self.erosion_var, 0, 15, 1, cb=self.update_preview,
                   tooltip="Thin obstacles / remove edge artifacts.")

        # Action buttons
        act = ttk.Labelframe(parent, text="Actions", padding=10, style="Card.TLabelframe")
        act.pack(fill="x", expand=False, pady=(10, 0))
        ttk.Button(act, text="Auto-Enhance (A)", command=self.auto_enhance, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(act, text="Reset All Filters (R)", command=self.reset_filters, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(act, text="Undo (Ctrl+Z)", command=self.undo, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(act, text="Redo (Ctrl+Y)", command=self.redo, style="Modern.TButton").pack(fill="x", pady=4)

    def _enforce_split_and_refresh(self, e):
        # Maintain 25%/75% split between left and right panes on window resize
        try:
            total_w = self.winfo_width()
            if total_w <= 1:
                return
            left_w = int(total_w * 0.25)
            if self.paned.sashcoord(0)[0] != left_w:
                self.paned.sash_place(0, left_w, 1)
        except Exception:
            pass
        self.update_preview()

    def _bind_keys(self):
        # Bind keyboard shortcuts for common actions
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
        # Update slider value, clamp it, and refresh label
        if isinstance(var, tk.IntVar):
            var.set(clamp(var.get(), 0, 9999))
        elif isinstance(var, tk.DoubleVar):
            var.set(clamp(var.get(), 0.0, 1.0))
        label_widget.configure(text=str(var.get()))
        self._push_history_snapshot()
        if callback:
            callback()

    def select_folder(self):
        # Load a folder containing .pgm and .yaml files
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
            self.filter_input_map = img.copy()
            self.processed_map = img.copy()
            self.original_folder_name = os.path.basename(folder)
            self.zoom_factor = 1.0
            self.pan_x = 0
            self.pan_y = 0
            self._update_meta_text(pgm_file, yaml_file)
            self._clear_history()
            self._push_history_snapshot()
            self.update_preview()
            self._status(f"Loaded: {self.original_folder_name} ({img.shape[1]}×{img.shape[0]})")
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to load folder:\n{ex}")

    def save_map(self):
        # Save the processed map and updated metadata
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
            if self.optimizer.working_map is not None:
                self.processed_map = self.optimizer.working_map.copy()
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
        # Update metadata display in the Metadata tab
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

    def apply_filters(self):
        # Apply image processing filters based on UI parameters
        base = self.filter_input_map if self.filter_input_map is not None else self.original_map
        if base is None:
            return None
        img = base.copy()
        med = clamp(int(self.median_var.get()), 0, 99)
        if med > 0:
            k = med if med % 2 == 1 else med + 1
            img = cv2.medianBlur(img, k)  # Remove salt-and-pepper noise
        g = clamp(int(self.blur_var.get()), 0, 99)
        if g > 0:
            k = g if g % 2 == 1 else g + 1
            img = cv2.GaussianBlur(img, (k, k), 0)  # Smooth image
        if self.use_adaptive.get():
            block = max(15, (min(img.shape[:2]) // 30) | 1)
            th_img = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, block, 5)
        else:
            thr = clamp(float(self.threshold_var.get()), 0.0, 1.0)
            _, th_img = cv2.threshold(img, int(thr * 255), 255, cv2.THRESH_BINARY)
        out = th_img
        op = clamp(int(self.opening_var.get()), 0, 99)
        if op > 0:
            out = cv2.morphologyEx(out, cv2.MORPH_OPEN, morphological_kernel(op))  # Remove speckles
        cl = clamp(int(self.closing_var.get()), 0, 99)
        if cl > 0:
            out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, morphological_kernel(cl))  # Fill gaps
        dil = clamp(int(self.dilation_var.get()), 0, 99)
        if dil > 0:
            out = cv2.dilate(out, morphological_kernel(dil))  # Thicken obstacles
        ero = clamp(int(self.erosion_var.get()), 0, 99)
        if ero > 0:
            out = cv2.erode(out, morphological_kernel(ero))  # Thin obstacles
        self.processed_map = out
        return out

    def auto_enhance(self):
        # Automatically adjust filter parameters based on image analysis
        if self.filter_input_map is None:
            messagebox.showwarning("No Map", "Load a map first.")
            return
        img = self.filter_input_map
        hist = cv2.calcHist([img], [0], None, [256], [0, 256]).flatten()
        total = img.size
        mean_val = float((hist * np.arange(256)).sum() / max(total, 1))
        lap = cv2.Laplacian(img, cv2.CV_64F)
        lap_var = float(lap.var())  # Measure image noise
        try:
            _ret, _ = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            thr = _ret / 255.0
            use_adapt = False
            if lap_var > 120.0:
                use_adapt = True
                thr = 0.5
        except Exception:
            thr = 0.5
            use_adapt = False
        if lap_var < 30:
            g, med = 0, 0
        elif lap_var < 120:
            g, med = 1, 1
        else:
            g, med = 3, 3
        if use_adapt:
            block = max(15, (min(img.shape[:2]) // 30) | 1)
            bw = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, block, 5)
        else:
            _, bw = cv2.threshold(img, int(thr * 255), 255, cv2.THRESH_BINARY)
        dark_ratio = hist[:64].sum() / total
        bright_ratio = hist[192:].sum() / total
        obstacles_are_black = dark_ratio >= bright_ratio
        bin_obs = (bw == (0 if obstacles_are_black else 255)).astype(np.uint8) * 255
        if bin_obs.max() > 0:
            dist = cv2.distanceTransform(bin_obs, cv2.DIST_L2, 3)
            edge = cv2.Canny(bin_obs, 50, 150)
            dvals = dist[edge > 0]
            mean_thick = float(dvals.mean() * 2.0) if dvals.size else 1.0
        else:
            mean_thick = 1.0
        known_mask = (img != 205) if 205 in np.unique(img) else np.ones_like(img, dtype=bool)
        occ_ratio = float((bin_obs > 0).sum()) / float(known_mask.sum() + 1e-6)
        res_m = safe_float(self.map_metadata.get("resolution", 0.05), 0.05)
        target_wall_m = 0.15
        target_px = clamp(int(round(target_wall_m / max(res_m, 1e-6))), 1, 15)
        dilation = erosion = opening = closing = 0
        if occ_ratio < 0.02 or lap_var > 120:
            opening = clamp(int(round(0.05 / res_m)), 0, 7)
        closing = clamp(int(round(0.04 / res_m)), 0, 7)
        if mean_thick < target_px:
            dilation = clamp(int(round(target_px - mean_thick)), 0, 8)
        elif mean_thick > target_px * 1.8:
            erosion = clamp(int(round(mean_thick - target_px)), 0, 8)
        if opening and erosion:
            erosion = max(0, erosion - 1)
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
        self._status(f"Auto-Enhance | lapVar={lap_var:.1f} meanPix={mean_val:.1f} wall≈{mean_thick:.1f}px target≈{target_px}px occ={occ_ratio*100:.1f}%")

    def fit_to_window(self):
        # Adjust zoom to fit the map in the canvas
        img = self.processed_map if self.processed_map is not None else self.filter_input_map
        if img is None:
            return
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        h, w = img.shape
        scale = min(cw / w, ch / h)
        self.zoom_factor = scale
        self.pan_x = 0
        self.pan_y = 0
        self.update_preview()

    def _center_preview(self):
        # Reset pan to center the map
        self.pan_x = 0
        self.pan_y = 0
        self.update_preview()

    def _on_wheel(self, e):
        # Handle mouse wheel for zooming
        delta = 0
        if hasattr(e, "delta") and e.delta != 0:
            delta = 1 if e.delta > 0 else -1
        elif hasattr(e, "num"):
            delta = 1 if e.num == 4 else -1
        if delta > 0:
            self.zoom_factor *= 1.1
        else:
            self.zoom_factor *= 0.9
            self.zoom_factor = max(self.zoom_factor, 0.05)
        self._update_zoom_label()
        self.update_preview()

    def _update_zoom_label(self):
        # Update zoom level display
        self.zoom_label_var.set(f"{int(self.zoom_factor*100):d}%")

    def _on_pan_start(self, ev):
        # Start panning with middle mouse button
        self.pan_start = (ev.x, ev.y)

    def _on_pan_drag(self, ev):
        # Update pan position during drag
        if not self.pan_start:
            return
        dx = ev.x - self.pan_start[0]
        dy = ev.y - self.pan_start[1]
        self.pan_x += dx
        self.pan_y += dy
        self.pan_start = (ev.x, ev.y)
        self.update_preview()

    def _to_canvas(self, x, y):
        # Convert image coordinates to canvas coordinates
        s = self.last_draw["scale"]
        ox = self.last_draw["ox"]
        oy = self.last_draw["oy"]
        return ox + int(x*s) + int(self.pan_x), oy + int(y*s) + int(self.pan_y)

    def _from_canvas(self, cx, cy):
        # Convert canvas coordinates to image coordinates
        s = self.last_draw["scale"]
        ox = self.last_draw["ox"]
        oy = self.last_draw["oy"]
        if s <= 0: return None
        base = self.processed_map if self.processed_map is not None else self.filter_input_map
        if base is None:
            return None
        x = (cx - ox - self.pan_x) / s
        y = (cy - oy - self.pan_y) / s
        h, w = base.shape
        if x < 0 or y < 0 or x >= w or y >= h: return None
        return (float(x), float(y))

    def _on_canvas_click(self, ev):
        # Delegate single-click events to Optimizer in Optimization tab
        if self.active_tab == "Optimization":
            self.optimizer.on_canvas_click(ev)

    def _on_canvas_double_click(self, ev):
        # Delegate double-click events to Optimizer in Optimization tab
        if self.active_tab == "Optimization":
            self.optimizer.on_canvas_double_click(ev)

    def _compose_preview_image(self, base_override=None):
        # Create preview image based on mode (original, enhanced, side-by-side)
        if self.filter_input_map is None and self.processed_map is None:
            return None
        mode = self.preview_mode.get()
        if mode == "original":
            base = self.original_map if self.original_map is not None else (self.filter_input_map if self.filter_input_map is not None else self.processed_map)
        elif mode == "enhanced":
            base = base_override if base_override is not None else (self.processed_map if self.processed_map is not None else self.filter_input_map)
        else:
            left = self.original_map if self.original_map is not None else (self.filter_input_map if self.filter_input_map is not None else self.processed_map)
            right = base_override if base_override is not None else (self.processed_map if self.processed_map is not None else self.filter_input_map)
            if left is None or right is None:
                return None
            h1, w1 = left.shape
            h2, w2 = right.shape
            h = max(h1, h2)
            canvas = np.full((h, w1 + w2 + 4), 255, np.uint8)
            canvas[:h1, :w1] = left
            canvas[:h2, w1 + 4:w1 + 4 + w2] = right
            base = canvas
        img = base.copy()
        if self.invert_view.get():
            img = 255 - img  # Invert for visual effect
        if self.show_grid.get():
            step = max(10, min(img.shape[0], img.shape[1]) // 40)
            vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            for x in range(0, vis.shape[1], step):
                cv2.line(vis, (x, 0), (x, vis.shape[0]-1), (180, 180, 180), 1, cv2.LINE_AA)
            for y in range(0, vis.shape[0], step):
                cv2.line(vis, (0, y), (vis.shape[1]-1, y), (180, 180, 180), 1, cv2.LINE_AA)
            img = vis
        else:
            if img.ndim != 2:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    def update_preview(self):
        # Update the canvas with the current map and overlays
        if self.active_tab == "Filtering":
            self.apply_filters()
        base_override = self.optimizer.working_map if (self.preview_mode.get()=="enhanced" and self.optimizer.working_map is not None) else None
        try:
            src = base_override if base_override is not None else (self.processed_map if self.processed_map is not None else self.filter_input_map)
            if src is not None:
                occ_black = (src == 0).sum()
                total = src.size
                occ_ratio = occ_black / max(total, 1)
                self.metrics_label_var.set(f"Obstacles≈{occ_ratio*100:.1f}% | size {src.shape[1]}×{src.shape[0]}")
        except Exception:
            pass
        img = self._compose_preview_image(base_override=base_override)
        if img is None:
            return
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
        self.last_draw["scale"] = scale
        self.last_draw["ox"] = (cw - new_w) // 2
        self.last_draw["oy"] = (ch - new_h) // 2
        self.photo_cache = cv_to_photo(disp)
        self.canvas.delete("all")
        x0 = self.last_draw["ox"] + int(self.pan_x)
        y0 = self.last_draw["oy"] + int(self.pan_y)
        self.canvas.create_image(x0, y0, anchor=tk.NW, image=self.photo_cache)
        if self.show_cp_overlay and self.preview_mode.get() == "enhanced" and self.optimizer.points:
            for (i,j) in self.optimizer.pairs:
                xi, yi = self.optimizer.points[i]
                xj, yj = self.optimizer.points[j]
                cxi, cyi = self._to_canvas(xi, yi)
                cxj, cyj = self._to_canvas(xj, yj)
                self.canvas.create_line(cxi, cyi, cxj, cyj, fill="green", width=3)
            for idx, (x, y) in enumerate(self.optimizer.points):
                cx, cy = self._to_canvas(x, y)
                r = max(5, int(1.1 * self.last_draw["scale"]))
                if idx in self.optimizer.anchor_idx:
                    fill_color = "#2563EB"
                else:
                    fill_color = "red"
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill_color, outline="black", width=1)
            if self.optimizer.selected is not None:
                sx, sy = self._to_canvas(*self.optimizer.points[self.optimizer.selected])
                R = self.optimizer.hit_radius
                self.canvas.create_oval(sx-R, sy-R, sx+R, sy+R, outline="#33ff33", width=2, dash=(3,2))

    def _on_tab_changed(self, e):
        # Handle tab switching and state updates
        try:
            tab_text = self.nb.tab(self.nb.select(), "text")
        except Exception:
            tab_text = "Filtering"
        self.active_tab = tab_text
        self.show_cp_overlay = (tab_text == "Optimization")
        if tab_text != "Optimization" and self.optimizer.working_map is not None:
            self.processed_map = self.optimizer.working_map.copy()
            self.filter_input_map = self.processed_map.copy()
            self.optimizer.reset_state()
        self.update_preview()

    def _snapshot(self):
        # Capture current filter parameters for undo/redo
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
        # Restore filter parameters from a snapshot
        self.threshold_var.set(float(s.get("threshold", 0.5)))
        self.use_adaptive.set(bool(s.get("adaptive", False)))
        self.blur_var.set(int(s.get("blur", 0)))
        self.median_var.set(int(s.get("median", 0)))
        self.opening_var.set(int(s.get("opening", 0)))
        self.closing_var.set(int(s.get("closing", 0)))
        self.dilation_var.set(int(s.get("dilation", 0)))
        self.erosion_var.set(int(s.get("erosion", 0)))

    def _clear_history(self):
        # Clear undo/redo stacks
        self.history.clear()
        self.future.clear()

    def _push_history_snapshot(self):
        # Save current filter state for undo
        snap = self._snapshot()
        if not self.history or self.history[-1] != snap:
            self.history.append(snap)
            self.future.clear()

    def undo(self):
        # Revert to previous filter state
        if len(self.history) <= 1:
            return
        cur = self.history.pop()
        self.future.appendleft(cur)
        prev = self.history[-1]
        self._apply_snapshot(prev)
        self.update_preview()

    def redo(self):
        # Restore next filter state
        if not self.future:
            return
        nxt = self.future.popleft()
        self.history.append(nxt)
        self._apply_snapshot(nxt)
        self.update_preview()

    def reset_filters(self):
        # Reset all filter parameters to defaults
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
        # Update window title with status message
        self.title(f"{APP_TITLE} — {msg}")