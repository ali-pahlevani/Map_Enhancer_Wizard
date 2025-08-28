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
import random

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

def linux_mousewheel_bind(widget, wheel_cb, up_id="<Button-4>", down_id="<Button-5>"):
    """Bind zoom wheel generically."""
    sys = platform.system()
    if sys in ("Windows", "Darwin"):
        widget.bind("<MouseWheel>", wheel_cb)
    else:
        widget.bind(up_id, wheel_cb)
        widget.bind(down_id, wheel_cb)

def morphological_kernel(size):
    size = clamp(int(size), 1, 99)
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
            font=("Segoe UI", 10),
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
        self.original_map = None          # original loaded PGM
        self.filter_input_map = None      # <- NEW: the current base for Filtering tab
        self.processed_map = None         # latest filtered/optimized result
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
        self.blur_var = tk.IntVar(value=0)            # gaussian kernel (odd, 0=off)
        self.median_var = tk.IntVar(value=0)          # median filter kernel (odd, 0=off)
        self.opening_var = tk.IntVar(value=0)
        self.closing_var = tk.IntVar(value=0)
        self.dilation_var = tk.IntVar(value=0)
        self.erosion_var = tk.IntVar(value=0)

        self.metrics_label_var = tk.StringVar(value="")
        self.zoom_label_var = tk.StringVar(value="100%")

        # undo/redo stacks of parameter snapshots (for Filtering)
        self.history = deque(maxlen=50)
        self.future = deque(maxlen=50)

        # --------- Kernel Control-Points optimizer state ---------
        self.cp_n = tk.IntVar(value=2000)            # number of control points
        self.cp_kernel = tk.IntVar(value=5)         # odd size: 3,5,7,...
        self.cp_sigma = tk.DoubleVar(value=14.0)    # reserved for future
        self.cp_alpha = tk.DoubleVar(value=0.05)    # step size per iter
        self.cp_lc = tk.DoubleVar(value=2.0)        # line (pair) weight
        self.cp_ls = tk.DoubleVar(value=0.08)        # neighbor Laplacian weight
        self.cp_nb_radius = tk.IntVar(value=8)     # neighbor radius (px)
        self.cp_max_iters = tk.IntVar(value=100)
        self.cp_tol = tk.DoubleVar(value=1e-3)      # improvement tolerance

        # ---- Corner-anchors tunables (UI in Optimization tab) ----
        self.ca_angle_min = tk.DoubleVar(value=85.0)   # degrees
        self.ca_angle_max = tk.DoubleVar(value=95.0)   # degrees
        self.ca_quality   = tk.DoubleVar(value=0.05)   # goodFeaturesToTrack qualityLevel
        self.ca_min_bcnt  = tk.IntVar(value=5)         # minimum 2nd-peak count
        self.ca_min_bratio= tk.DoubleVar(value=0.20)   # minimum ratio of 2nd to 1st peak

        # Rebuild anchors automatically when these change (if CPs exist)
        self._ca_after_id = None
        def _rebuild_on_change(*_):
            # Debounce to avoid firing while entry is temporarily empty
            if self._ca_after_id is not None:
                try:
                    self.after_cancel(self._ca_after_id)
                except Exception:
                    pass
            self._ca_after_id = self.after(150, self._rebuild_anchors_if_any)

        for v in [self.ca_angle_min, self.ca_angle_max, self.ca_quality, self.ca_min_bcnt, self.ca_min_bratio]:
            try:
                v.trace_add("write", _rebuild_on_change)
            except Exception:
                pass

        self.cp_points = []      # [(x,y), ...] current (float)
        self.cp_init = []        # initial positions (float)
        self.cp_prev = []        # previous positions (float) for erase step
        self.cp_pairs = []       # list of (i,j) constraints
        self.cp_selected = None  # index of selected point (for pairing)
        self.cp_hit_radius = 14  # selection radius (canvas px)
        self.cp_running = False
        self.cp_last_score = None
        self.cp_neighbors = None # cached neighbor lists
        self.last_draw = {"scale":1.0, "ox":0, "oy":0}

        # ---- Corner anchors (points near sharp angles that we keep fixed) ----
        self.cp_anchor_idx = set()   # set[int] of CP indices that are locked (do not move)

        # kernel payloads
        self.cp_kernels = []     # list of np.uint8 (k x k) with values 0/1 (1=occupied)
        self.cp_base_map = None  # frozen enhanced map at start
        self.cp_base_occ = None  # boolean 0/1 occupancy from base map (1=occupied)
        self.cp_work_occ = None  # evolving occupancy map (0/1)
        self.cp_working_map = None  # evolving grayscale map (0 or 255)

        # optimizer param dirtiness
        self.cp_need_prepare = False      # <- NEW: if params changed

        self._build_ui()
        self._bind_keys()
        self._bind_cp_param_traces()      # <- NEW

    # -------- traces to mark optimizer params as dirty --------

    def _bind_cp_param_traces(self):
        def mark_dirty(*_):
            self.cp_need_prepare = True
        for v in [self.cp_kernel, self.cp_alpha, self.cp_lc, self.cp_ls,
                  self.cp_nb_radius, self.cp_max_iters, self.cp_tol]:
            try:
                v.trace_add("write", mark_dirty)
            except Exception:
                pass

    def _rebuild_anchors_if_any(self):
        if self.cp_points:
            self._assign_anchor_points()
            self.update_preview()

    # ------------------------- UI -------------------------

    def _build_ui(self):
        # ==== Modernize styling ====
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Color palette (soft light with an accent)
        ACCENT = "#3C82F6"   # blue
        ACCENT_DK = "#2F6BCE"
        SURFACE = "#F7F9FC"
        CARD = "#FFFFFF"
        TEXT = "#1F2937"
        MUTED = "#6B7280"
        BORDER = "#E5E7EB"

        # Global widget styles
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

        style.configure("Modern.TButton",
                        font=("Segoe UI", 10, "bold"),
                        padding=(10, 8),
                        background=ACCENT,
                        foreground="#FFFFFF",
                        borderwidth=0)
        style.map("Modern.TButton",
                  background=[("active", ACCENT_DK), ("pressed", ACCENT_DK)])

        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT)
        style.configure("TRadiobutton", background=SURFACE, foreground=TEXT)
        style.configure("TScale", background=SURFACE)

        self.configure(bg=SURFACE)

        # ==== Layout: use a PanedWindow to enforce 25%/75% split ====
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.paned = tk.PanedWindow(self, orient="horizontal", sashwidth=6, bg=SURFACE, bd=0, sashrelief="flat")
        self.paned.grid(row=0, column=0, sticky="nsew")

        # Left pane (scrollable)
        left_outer = ttk.Frame(self, style="TFrame")
        self._build_left_scrollable(left_outer)
        self.paned.add(left_outer, minsize=260)  # sensible minimum

        # Right pane (canvas area)
        right = ttk.Frame(self, padding=(4, 4), style="TFrame")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(right, bg="#FAFAFF", highlightthickness=1, highlightbackground=BORDER)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.paned.add(right)

        # Status bar (spans full width)
        status = ttk.Frame(self, style="TFrame")
        status.grid(row=1, column=0, sticky="ew")
        status.grid_columnconfigure(1, weight=1)
        border = tk.Frame(status, height=1, bg=BORDER)
        border.grid(row=0, column=0, columnspan=3, sticky="ew")
        ttk.Label(status, text="Zoom:", style="Small.TLabel").grid(row=1, column=0, sticky="w", padx=(8, 4), pady=6)
        ttk.Label(status, textvariable=self.zoom_label_var, style="Small.TLabel").grid(row=1, column=1, sticky="w")
        ttk.Label(status, textvariable=self.metrics_label_var, style="Small.TLabel").grid(row=1, column=2, sticky="e", padx=8)

        # Enforce 25%/75% split whenever window size changes
        self.bind("<Configure>", self._enforce_split_and_refresh)

        # Mouse: middle button panning, wheel zoom
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)   # middle press
        self.canvas.bind("<B2-Motion>", self._on_pan_drag)        # middle drag
        linux_mousewheel_bind(self.canvas, self._on_wheel)        # zoom on wheel

        # Fit to window: Shift + double left-click (avoid conflict with node double-click)
        self.canvas.bind("<Shift-Double-Button-1>", lambda e: self.fit_to_window())

        # CP interactions: left click to pair toggle; double-click to remove all connections of a node
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_click)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)

    def _build_left_scrollable(self, parent):
        """Create the left controls inside a scrollable container so they never hide behind the canvas."""
        # Scrollable shell
        shell = ttk.Frame(parent, padding=(8, 8), style="TFrame")
        shell.pack(fill="both", expand=True)

        self.left_canvas = tk.Canvas(shell, highlightthickness=0, bg="#F7F9FC")

        vscroll = ttk.Scrollbar(shell, orient="vertical", command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=vscroll.set)

        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        # Frame inside canvas
        self.controls_host = ttk.Frame(self.left_canvas, style="TFrame")
        self.controls_host_id = self.left_canvas.create_window((0, 0), window=self.controls_host, anchor="nw")

        # Make the interior width follow the viewport width
        def _sync_width(event):
            self.left_canvas.itemconfig(self.controls_host_id, width=event.width)
        self.left_canvas.bind("<Configure>", _sync_width)

        # Update scrollregion when content changes size
        def _update_scrollregion(_=None):
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))
        self.controls_host.bind("<Configure>", _update_scrollregion)

        # Build notebook & controls inside controls_host
        nb = ttk.Notebook(self.controls_host, style="TNotebook")
        self.nb = nb
        self.active_tab = "Filtering"
        self.show_cp_overlay = False
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        nb.pack(fill="both", expand=True)

        # --- Tab: Filtering ---
        tab_controls = ttk.Frame(nb, padding=(10, 10), style="TFrame")
        nb.add(tab_controls, text="Filtering")

        # File actions
        file_frame = ttk.Labelframe(tab_controls, text="Map I/O", padding=10, style="Card.TLabelframe")
        file_frame.pack(fill="x", expand=False)
        ttk.Button(file_frame, text="Select Map Folder", command=self.select_folder, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(file_frame, text="Save Enhanced Map", command=self.save_map, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(file_frame, text="Fit to Window (F)", command=self.fit_to_window, style="Modern.TButton").pack(fill="x", pady=4)

        # Preview opts
        preview_frame = ttk.Labelframe(tab_controls, text="Preview", padding=10, style="Card.TLabelframe")
        preview_frame.pack(fill="x", expand=False, pady=(10, 0))
        for mode, label in [("original", "Original"), ("enhanced", "Enhanced"), ("side_by_side", "Side-by-Side")]:
            ttk.Radiobutton(preview_frame, text=label, value=mode, variable=self.preview_mode, command=self.update_preview).pack(anchor="w")
        ttk.Checkbutton(preview_frame, text="Show Grid", variable=self.show_grid, command=self.update_preview).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(preview_frame, text="Invert View (visual only)", variable=self.invert_view, command=self.update_preview).pack(anchor="w")

        # Filters
        filt = ttk.Labelframe(tab_controls, text="Filters & Morphology", padding=10, style="Card.TLabelframe")
        filt.pack(fill="x", expand=False, pady=(10, 0))

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

        act = ttk.Labelframe(tab_controls, text="Actions", padding=10, style="Card.TLabelframe")
        act.pack(fill="x", expand=False, pady=(10, 0))
        ttk.Button(act, text="Auto-Enhance (A)", command=self.auto_enhance, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(act, text="Reset All Filters (R)", command=self.reset_filters, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(act, text="Undo (Ctrl+Z)", command=self.undo, style="Modern.TButton").pack(fill="x", pady=4)
        ttk.Button(act, text="Redo (Ctrl+Y)", command=self.redo, style="Modern.TButton").pack(fill="x", pady=4)

        # --- Tab: Optimization (Kernel Control Points) ---
        tab_opt = ttk.Frame(nb, padding=(10, 10), style="TFrame")
        nb.add(tab_opt, text="Optimization")

        genf = ttk.Labelframe(tab_opt, text="Control Points", padding=10, style="Card.TLabelframe")
        genf.pack(fill="x", pady=(0,8))
        ttk.Label(genf, text="N points:").grid(row=0, column=0, sticky="w")
        ttk.Entry(genf, width=8, textvariable=self.cp_n).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(genf, text="Generate (occupied only)", command=self._cp_generate, style="Modern.TButton").grid(row=0, column=2, padx=6)
        ttk.Button(genf, text="Clear Pairs", command=self._cp_clear_pairs, style="Modern.TButton").grid(row=0, column=3, padx=6)
        ttk.Label(genf, text="Click two red points to toggle a green constraint line. Double-click a node to remove all its connections.").grid(row=1, column=0, columnspan=4, sticky="w", pady=(6,0))

        el = ttk.Labelframe(tab_opt, text="Kernel & Optimization Parameters", padding=10, style="Card.TLabelframe")
        el.pack(fill="x", pady=(0,8))

        def put(r,c,txt,var,w=8,tip=None):
            ttk.Label(el, text=txt).grid(row=r, column=c*2, sticky="w")
            e = ttk.Entry(el, width=w, textvariable=var); e.grid(row=r, column=c*2+1, sticky="w", padx=4)
            if tip: ToolTip(e, tip)

        put(0,0,"Kernel size (odd):", self.cp_kernel, tip="3, 5, 7, ... Kernel a CP carries.")
        put(0,1,"Step α:", self.cp_alpha, tip="Gradient step size per iteration.")
        put(0,2,"Line weight λc:", self.cp_lc, tip="Weight for user constraints (pull endpoints together).")
        put(1,0,"Elastic weight λs:", self.cp_ls, tip="Neighbor Laplacian weight.")
        put(1,1,"Neighbor radius (px):", self.cp_nb_radius, tip="Neighbors within this radius influence each other.")
        put(1,2,"Max iters:", self.cp_max_iters, tip="Max optimization iterations.")
        put(2,0,"Tol (Δscore):", self.cp_tol, tip="Stop if improvement below this value.")

        # --- Corner Anchor Settings ---
        anchorf = ttk.Labelframe(tab_opt, text="Corner Anchor Settings", padding=10, style="Card.TLabelframe")
        anchorf.pack(fill="x", pady=(0,8))

        # Angle band (min/max)
        row1 = ttk.Frame(anchorf, style="TFrame"); row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="Angle band (°):").pack(side="left")
        e_min = ttk.Entry(row1, width=6, textvariable=self.ca_angle_min); e_min.pack(side="left", padx=(6,4))
        ttk.Label(row1, text="to").pack(side="left")
        e_max = ttk.Entry(row1, width=6, textvariable=self.ca_angle_max); e_max.pack(side="left", padx=(6,0))

        # Corner detector qualityLevel
        row2 = ttk.Frame(anchorf, style="TFrame"); row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="qualityLevel:").pack(side="left")
        e_q = ttk.Entry(row2, width=8, textvariable=self.ca_quality); e_q.pack(side="left", padx=(6,0))
        ttk.Label(row2, text="(0..1; higher = stricter)").pack(side="left", padx=(6,0))

        # Second-peak requirement: min count & min ratio
        row3 = ttk.Frame(anchorf, style="TFrame"); row3.pack(fill="x", pady=4)
        ttk.Label(row3, text="2nd peak ≥").pack(side="left")
        e_cnt = ttk.Entry(row3, width=6, textvariable=self.ca_min_bcnt); e_cnt.pack(side="left", padx=(6,4))
        ttk.Label(row3, text="or ≥").pack(side="left")
        e_ratio = ttk.Entry(row3, width=6, textvariable=self.ca_min_bratio); e_ratio.pack(side="left", padx=(6,4))
        ttk.Label(row3, text="× 1st peak").pack(side="left")

        # Manual rebuild (useful after Generate CPs)
        row4 = ttk.Frame(anchorf, style="TFrame"); row4.pack(fill="x", pady=6)
        ttk.Button(row4, text="Rebuild Anchors Now", command=self._rebuild_anchors_if_any, style="Modern.TButton").pack(side="left")

        runf = ttk.Labelframe(tab_opt, text="Run", padding=10, style="Card.TLabelframe")
        runf.pack(fill="x")
        ttk.Button(runf, text="Start", command=self._cp_start, style="Modern.TButton").grid(row=0, column=0, padx=4, pady=2, sticky="ew")
        ttk.Button(runf, text="Step Once", command=self._cp_step_once, style="Modern.TButton").grid(row=0, column=1, padx=4, pady=2, sticky="ew")
        ttk.Button(runf, text="Stop", command=self._cp_stop, style="Modern.TButton").grid(row=0, column=2, padx=4, pady=2, sticky="ew")
        ttk.Button(runf, text="Apply to Enhanced", command=self._cp_apply, style="Modern.TButton").grid(row=1, column=0, columnspan=2, padx=4, pady=6, sticky="ew")
        ttk.Button(runf, text="Revert Working", command=self._cp_revert, style="Modern.TButton").grid(row=1, column=2, padx=4, pady=6, sticky="ew")

        stat = ttk.Labelframe(tab_opt, text="Status", padding=10, style="Card.TLabelframe")
        stat.pack(fill="x")
        self.lbl_iter = ttk.Label(stat, text="iter: 0"); self.lbl_iter.grid(row=0, column=0, sticky="w")
        self.lbl_score = ttk.Label(stat, text="score: -"); self.lbl_score.grid(row=0, column=1, sticky="w", padx=(12,0))
        ttk.Label(stat, text="Tip: middle-mouse to pan, mouse wheel to zoom. 'F' to fit window.").grid(row=1, column=0, columnspan=3, sticky="w", pady=(6,0))

        # --- Tab: Metadata ---
        tab_meta = ttk.Frame(nb, padding=(10, 10), style="TFrame")
        nb.add(tab_meta, text="Metadata")
        self.meta_text = tk.Text(tab_meta, width=36, height=18, wrap="none")
        self.meta_text.configure(font=("Consolas", 10), bd=0, highlightthickness=1, highlightbackground="#E5E7EB")
        self.meta_text.pack(fill="both", expand=True)

    # Keep the left/right panes exactly 25% / 75% of window width
    def _enforce_split_and_refresh(self, e):
        # Ignore events from child widgets that report tiny widths/heights
        try:
            total_w = self.winfo_width()
            if total_w <= 1:
                return
            left_w = int(total_w * 0.25)
            # Only reposition sash if it has actually moved (prevents jitter)
            if self.paned.sashcoord(0)[0] != left_w:
                # place the sash so that left pane width == 25% of window width
                self.paned.sash_place(0, left_w, 1)
        except Exception:
            pass
        # Update preview on resize as before
        self.update_preview()

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

    def _on_canvas_double_click(self, ev):
        if self.active_tab != "Optimization":
            return
        if not self.cp_points:
            return
        imgxy = self._from_canvas(ev.x, ev.y)
        if imgxy is None:
            return
        best = None; bestd2 = 1e9
        for i,(x,y) in enumerate(self.cp_points):
            cx, cy = self._to_canvas(x,y)
            d2 = (cx-ev.x)**2 + (cy-ev.y)**2
            if d2 < bestd2:
                bestd2 = d2; best = i
        if best is None or bestd2 > (self.cp_hit_radius**2):
            return
        self.cp_pairs = [p for p in self.cp_pairs if (best not in p)]
        if self.cp_selected == best:
            self.cp_selected = None
        self.update_preview()

    def _on_scale_change(self, var, label_widget, callback):
        # Normalize and clamp ints where appropriate
        if isinstance(var, (tk.IntVar,)):
            if var is self.cp_kernel:
                k = clamp(safe_int(var.get()), 3, 99)
                if k % 2 == 0: k += 1
                var.set(k)
            else:
                var.set(clamp(safe_int(var.get()), 0, 9999))
        elif isinstance(var, (tk.DoubleVar,)):
            if var is self.threshold_var:
                var.set(clamp(safe_float(var.get()), 0.0, 1.0))
            else:
                var.set(safe_float(var.get()))
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
            self.filter_input_map = img.copy()     # <- base for filtering
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

            # If there’s a live working optimized map, bake it first
            if self.cp_working_map is not None:
                self.processed_map = self.cp_working_map.copy()

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

    # ------------------------- Processing (Filtering tab) -------------------------

    def apply_filters(self):
        """Build output from filter_input_map using current parameters."""
        base = self.filter_input_map if self.filter_input_map is not None else self.original_map
        if base is None:
            return None

        img = base.copy()

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
        if self.filter_input_map is None:
            messagebox.showwarning("No Map", "Load a map first.")
            return

        img = self.filter_input_map
        hist = cv2.calcHist([img], [0], None, [256], [0, 256]).flatten()
        total = img.size
        mean_val = float((hist * np.arange(256)).sum() / max(total, 1))
        lap = cv2.Laplacian(img, cv2.CV_64F)
        lap_var = float(lap.var())

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
            bw = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                       cv2.THRESH_BINARY, block, 5)
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
        self._status(
            f"Auto-Enhance | lapVar={lap_var:.1f} meanPix={mean_val:.1f} wall≈{mean_thick:.1f}px target≈{target_px}px occ={occ_ratio*100:.1f}%"
        )

    # ------------------------- Preview & Canvas -------------------------

    def fit_to_window(self):
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
        self.pan_x = 0
        self.pan_y = 0
        self.update_preview()

    def _on_wheel(self, e):
        """Zoom on wheel rotation."""
        delta = 0
        if hasattr(e, "delta") and e.delta != 0:
            delta = 1 if e.delta > 0 else -1
        elif hasattr(e, "num"):
            delta = 1 if e.num == 4 else -1
        if delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

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

    def _to_canvas(self, x, y):
        s = self.last_draw["scale"]; ox = self.last_draw["ox"]; oy = self.last_draw["oy"]
        return ox + int(x*s) + int(self.pan_x), oy + int(y*s) + int(self.pan_y)

    def _from_canvas(self, cx, cy):
        s = self.last_draw["scale"]; ox = self.last_draw["ox"]; oy = self.last_draw["oy"]
        if s <= 0: return None
        if self.processed_map is None and self.filter_input_map is None:
            return None
        base = self.processed_map if self.processed_map is not None else self.filter_input_map
        x = (cx - ox - self.pan_x) / s
        y = (cy - oy - self.pan_y) / s
        h, w = base.shape
        if x < 0 or y < 0 or x >= w or y >= h: return None
        return (float(x), float(y))

    def _on_canvas_click(self, ev):
        # Only in Optimization tab and Enhanced view
        if self.active_tab != "Optimization" or self.preview_mode.get() != "enhanced":
            return
        if not self.cp_points:
            return
        imgxy = self._from_canvas(ev.x, ev.y)
        if imgxy is None:
            return

        # find nearest cp within hit radius
        best = None; bestd2 = 1e9
        for i,(x,y) in enumerate(self.cp_points):
            cx, cy = self._to_canvas(x,y)
            d2 = (cx-ev.x)**2 + (cy-ev.y)**2
            if d2 < bestd2:
                bestd2 = d2; best = i
        if best is None or bestd2 > (self.cp_hit_radius**2):
            return

        if self.cp_selected is None:
            self.cp_selected = best
        else:
            i = self.cp_selected
            j = best
            if i != j:
                pair = (min(i,j), max(i,j))
                if pair in self.cp_pairs:
                    # toggle OFF => remove connection
                    self.cp_pairs.remove(pair)
                else:
                    # toggle ON => add connection
                    self.cp_pairs.append(pair)
            self.cp_selected = None
        self.update_preview()

    def _compose_preview_image(self, base_override=None):
        """Create the preview image with overlays."""
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
            img = 255 - img

        # Grid overlay
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
        # Run filtering only on the Filtering tab to avoid clobbering optimization view
        if self.active_tab == "Filtering":
            self.apply_filters()

        # live optimizer view: show working map if exists in enhanced mode
        base_override = self.cp_working_map if (self.preview_mode.get()=="enhanced" and self.cp_working_map is not None) else None

        # Update metrics
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

        # remember mapping
        self.last_draw["scale"] = scale
        self.last_draw["ox"] = (cw - new_w) // 2
        self.last_draw["oy"] = (ch - new_h) // 2

        self.photo_cache = cv_to_photo(disp)
        self.canvas.delete("all")
        x0 = self.last_draw["ox"] + int(self.pan_x)
        y0 = self.last_draw["oy"] + int(self.pan_y)
        self.canvas.create_image(x0, y0, anchor=tk.NW, image=self.photo_cache)

        # overlays: control points & pairs (Optimization tab only)
        if self.show_cp_overlay and self.preview_mode.get() == "enhanced" and self.cp_points:
            for (i,j) in self.cp_pairs:
                xi, yi = self.cp_points[i]; xj, yj = self.cp_points[j]
                cxi, cyi = self._to_canvas(xi, yi)
                cxj, cyj = self._to_canvas(xj, yj)
                self.canvas.create_line(cxi, cyi, cxj, cyj, fill="green", width=3)
            for idx, (x, y) in enumerate(self.cp_points):
                cx, cy = self._to_canvas(x, y)
                r = max(5, int(1.1 * self.last_draw["scale"]))
                # Anchors (corner-locked) in BLUE, movables in RED
                if idx in self.cp_anchor_idx:
                    fill_color = "#2563EB"  # blue
                else:
                    fill_color = "red"
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill=fill_color, outline="black", width=1)
            if self.cp_selected is not None:
                sx, sy = self._to_canvas(*self.cp_points[self.cp_selected])
                R = self.cp_hit_radius
                self.canvas.create_oval(sx-R, sy-R, sx+R, sy+R, outline="#33ff33", width=2, dash=(3,2))

    # ------------------------- History & Tab switching -------------------------

    def _on_tab_changed(self, e):
        try:
            tab_text = e.widget.tab(e.widget.select(), "text")
        except Exception:
            tab_text = "Filtering"
        self.active_tab = tab_text
        self.show_cp_overlay = (tab_text == "Optimization")

        # If we're leaving Optimization and have a working optimized map,
        # bake it so Filtering sees the result and then clear CP state.
        if tab_text != "Optimization" and self.cp_working_map is not None:
            self.processed_map = self.cp_working_map.copy()
            self.filter_input_map = self.processed_map.copy()   # <- important for Filtering chain
            # clear CP state
            self.cp_running = False
            self.cp_points = []
            self.cp_init = []
            self.cp_prev = []
            self.cp_pairs = []
            self.cp_neighbors = None
            self.cp_kernels = []
            self.cp_base_map = None
            self.cp_base_occ = None
            self.cp_work_occ = None
            self.cp_working_map = None
            self.cp_last_score = None
            self.cp_anchor_idx = set()

        self.update_preview()

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
        snap = self._snapshot()
        if not self.history or self.history[-1] != snap:
            self.history.append(snap)
            self.future.clear()

    def undo(self):
        if len(self.history) <= 1:
            return
        cur = self.history.pop()
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

    # =================================================================
    #               CONTROL POINTS + KERNEL-BASED OPTIMIZATION
    # =================================================================

    def _occupied_coords(self):
        """Return Nx2 float array of (x,y) where processed_map is occupied (black=0)."""
        src = self.processed_map if self.processed_map is not None else self.filter_input_map
        if src is None:
            return np.empty((0,2), np.float32)
        mask = (src == 0)
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return np.empty((0,2), np.float32)
        return np.stack([xs, ys], axis=1).astype(np.float32)

    def _cp_generate(self):
        """Generate N control points, roughly evenly (k-means over occupied)."""
        src = self.processed_map if self.processed_map is not None else self.filter_input_map
        if src is None:
            messagebox.showwarning("No Map", "Load or produce a map first.")
            return
        pts = self._occupied_coords()
        if len(pts) == 0:
            messagebox.showwarning("No Occupied Pixels", "Adjust filtering so obstacles are black (0).")
            return
        N = int(self.cp_n.get())
        N = clamp(N, 2, min(2000, len(pts)))
        if len(pts) > 50000:
            idx = np.random.choice(len(pts), 50000, replace=False)
            data = pts[idx]
        else:
            data = pts
        Z = data.astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 1.0)
        ret, labels, centers = cv2.kmeans(Z, N, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        centers = centers.astype(np.float32)
        h, w = src.shape
        centers[:,0] = np.clip(np.round(centers[:,0]), 0, w-1)
        centers[:,1] = np.clip(np.round(centers[:,1]), 0, h-1)
        self.cp_points = [(float(x), float(y)) for (x,y) in centers]
        self.cp_init = [(float(x), float(y)) for (x,y) in centers]
        self.cp_prev = [(float(x), float(y)) for (x,y) in centers]
        self.cp_pairs = []
        self.cp_selected = None
        self.cp_neighbors = None
        self.cp_last_score = None
        self.cp_kernels = []
        self.cp_base_map = None
        self.cp_base_occ = None
        self.cp_work_occ = None
        self.cp_working_map = None
        self.cp_need_prepare = True

        # After generating CPs, mark corner-near points as anchors (fixed)
        self._assign_anchor_points()

        self._status(f"Generated {len(self.cp_points)} control points.")
        self.update_preview()

    def _cp_clear_pairs(self):
        self.cp_pairs = []
        self.cp_selected = None
        self._status("Cleared constraint pairs.")
        self.update_preview()

    def _cp_build_neighbors(self):
        """Brute-force neighbor lists within radius."""
        if not self.cp_points:
            self.cp_neighbors = []
            return
        pts = np.array(self.cp_points, dtype=np.float32)
        R = float(self.cp_nb_radius.get())
        R2 = R*R
        n = len(pts)
        neigh = [[] for _ in range(n)]
        for i in range(n):
            dx = pts[:,0] - pts[i,0]
            dy = pts[:,1] - pts[i,1]
            d2 = dx*dx + dy*dy
            idxs = np.where((d2 > 0.0) & (d2 <= R2))[0]
            neigh[i] = idxs.tolist()
        self.cp_neighbors = neigh

    def _cp_score(self, P):
        """Sum of squared distances for all constraint lines."""
        if not self.cp_pairs:
            return 0.0
        pts = np.array(P, dtype=np.float32)
        s = 0.0
        for (i,j) in self.cp_pairs:
            d = pts[j] - pts[i]
            s += float(d[0]*d[0] + d[1]*d[1])
        return s

    def _cp_forces(self, P):
        """Forces from constraints and elastic neighbors."""
        n = len(P)
        F = np.zeros((n,2), np.float32)
        pts = np.array(P, dtype=np.float32)
        lc = float(self.cp_lc.get())
        ls = float(self.cp_ls.get())

        # constraint lines: pull endpoints together
        for (i,j) in self.cp_pairs:
            d = pts[j] - pts[i]
            F[i] += lc * d
            F[j] += lc * (-d)

        # elastic Laplacian with neighbors
        if self.cp_neighbors is None:
            self._cp_build_neighbors()
        for i, neigh in enumerate(self.cp_neighbors or []):
            if not neigh: continue
            diff = pts[neigh] - pts[i]        # sum_j (pj - pi)
            F[i] += ls * diff.sum(axis=0)

        return F

    # -------- Kernel extraction & application --------

    def _extract_kernel_at(self, occ01, cx, cy, k):
        """Return kxk uint8 kernel (values 0 or 1) centered at (cx,cy). OOB => 0."""
        r = k // 2
        karr = np.zeros((k,k), dtype=np.uint8)
        h, w = occ01.shape
        x0 = int(round(cx)) - r
        y0 = int(round(cy)) - r
        xs0 = max(0, x0); ys0 = max(0, y0)
        xs1 = min(w, x0 + k); ys1 = min(h, y0 + k)
        if xs0 < xs1 and ys0 < ys1:
            kx0 = xs0 - x0; ky0 = ys0 - y0
            kx1 = kx0 + (xs1 - xs0); ky1 = ky0 + (ys1 - ys0)
            karr[ky0:ky1, kx0:kx1] = occ01[ys0:ys1, xs0:xs1]
        return karr

    def _compose_from_kernels(self, prev_occ, prev_positions, new_positions, kernels):
        """
        Move each kernel from prev_positions -> new_positions.
        - First erase previous kernel footprints (set to free=0).
        - Then write kernel at new positions (last-wins for overlaps).
        """
        out = prev_occ.copy()
        h, w = out.shape
        k = kernels[0].shape[0] if kernels else 0
        r = k // 2

        # 1) erase previous footprints
        for (px,py), K in zip(prev_positions, kernels):
            cx = int(round(px)); cy = int(round(py))
            x0 = cx - r; y0 = cy - r
            xs0 = max(0, x0); ys0 = max(0, y0)
            xs1 = min(w, x0 + k); ys1 = min(h, y0 + k)
            if xs0 < xs1 and ys0 < ys1:
                out[ys0:ys1, xs0:xs1] = 0  # free where this kernel used to be

        # 2) place at new positions
        for (nx,ny), K in zip(new_positions, kernels):
            cx = int(round(nx)); cy = int(round(ny))
            x0 = cx - r; y0 = cy - r
            xs0 = max(0, x0); ys0 = max(0, y0)
            xs1 = min(w, x0 + k); ys1 = min(h, y0 + k)
            if xs0 < xs1 and ys0 < ys1:
                kx0 = xs0 - x0; ky0 = ys0 - y0
                kx1 = kx0 + (xs1 - xs0); ky1 = ky0 + (ys1 - ys0)
                out[ys0:ys1, xs0:xs1] = K[ky0:ky1, kx0:kx1]

        return out

    def _refresh_working_map_from_occ(self):
        """Convert 0/1 occupancy to grayscale map 0/255."""
        if self.cp_work_occ is None:
            return None
        self.cp_working_map = np.where(self.cp_work_occ > 0, 0, 255).astype(np.uint8)
        return self.cp_working_map

    # -------- helper: estimate wall thickness for drawing --------

    def _estimate_wall_thickness_px(self, bin_img_0_255):
        try:
            obs = (bin_img_0_255 == 0).astype(np.uint8) * 255
            if obs.max() == 0:
                return 3
            dist = cv2.distanceTransform(obs, cv2.DIST_L2, 3)
            edge = cv2.Canny(obs, 50, 150)
            dvals = dist[edge > 0]
            if dvals.size == 0:
                return 3
            mean_thick = float(dvals.mean() * 2.0)
            return clamp(int(round(mean_thick)), 1, 12)
        except Exception:
            return 3

    # -------- Corner detection & anchor assignment --------

    def _estimate_cp_spacing(self):
        """Estimate a typical nearest-neighbor spacing among control points (in pixels)."""
        if not self.cp_points or len(self.cp_points) < 2:
            return 8.0
        pts = np.array(self.cp_points, dtype=np.float32)
        # Sample to keep O(n^2) manageable
        if len(pts) > 400:
            idx = np.random.choice(len(pts), 400, replace=False)
            pts = pts[idx]
        dmins = []
        for i in range(len(pts)):
            dx = pts[:, 0] - pts[i, 0]
            dy = pts[:, 1] - pts[i, 1]
            d2 = dx * dx + dy * dy
            d2[i] = 1e12  # ignore self
            dmins.append(float(np.sqrt(d2.min())))
        dmins.sort()
        k = max(5, int(0.2 * len(dmins)))  # be robust to outliers
        return max(4.0, float(np.mean(dmins[:k])))

    def _get_ca_vals(self):
        """
        Safely read Corner Anchor UI values with sensible defaults and clamping.
        Returns: (amin, amax, quality, min_bcnt, min_bratio)
        """
        try:
            amin = safe_float(self.ca_angle_min.get() or 85.0, 85.0)
        except Exception:
            amin = 85.0
        try:
            amax = safe_float(self.ca_angle_max.get() or 95.0, 95.0)
        except Exception:
            amax = 95.0
        try:
            quality = safe_float(self.ca_quality.get() or 0.05, 0.05)
        except Exception:
            quality = 0.05
        try:
            min_bcnt = safe_int(self.ca_min_bcnt.get() or 5, 5)
        except Exception:
            min_bcnt = 5
        try:
            min_bratio = safe_float(self.ca_min_bratio.get() or 0.20, 0.20)
        except Exception:
            min_bratio = 0.20

        # Clamp & sanitize
        quality   = clamp(quality, 0.0, 1.0)
        min_bcnt  = clamp(min_bcnt, 0, 1_000_000)
        min_bratio= clamp(min_bratio, 0.0, 1.0)
        amin      = clamp(amin, 0.0, 180.0)
        amax      = clamp(amax, 0.0, 180.0)
        if amin > amax:
            amin, amax = amax, amin
        return amin, amax, quality, min_bcnt, min_bratio

    def _compute_edges_and_orientation(self, base_gray_0_255):
        """
        Precompute edge map and per-pixel gradient orientation (0..180 degrees).
        We use the obstacle mask for crisp edges.
        """
        obs = (base_gray_0_255 == 0).astype(np.uint8) * 255
        edges = cv2.Canny(obs, 80, 160, apertureSize=3, L2gradient=True)

        # Gradient orientation modulo 180° (direction sign ignored)
        gx = cv2.Sobel(obs, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(obs, cv2.CV_32F, 0, 1, ksize=3)
        ang = cv2.phase(gx, gy, angleInDegrees=True)   # 0..360
        theta = (ang % 180.0).astype(np.float32)       # 0..180
        return edges, theta

    def _has_right_angle_at(self, x, y, edges, theta, win_px):
        """
        Check if the local neighborhood around (x,y) contains two dominant edge
        orientations whose difference is between 80° and 100°.
        """
        h, w = edges.shape
        hw = int(max(5, min(60, win_px)) // 2)  # half-window
        cx = int(round(x)); cy = int(round(y))
        x0 = max(0, cx - hw); x1 = min(w, cx + hw + 1)
        y0 = max(0, cy - hw); y1 = min(h, cy + hw + 1)

        patch_edges = edges[y0:y1, x0:x1]
        if patch_edges.size == 0:
            return False

        mask = (patch_edges > 0)
        if mask.sum() < 20:
            return False

        patch_theta = theta[y0:y1, x0:x1][mask]  # 1D angles array
        # Histogram in 5° bins across 0..180
        bins = np.linspace(0.0, 180.0, 37)  # 36 bins, width=5°
        hist, _ = np.histogram(patch_theta, bins=bins)

        # Two dominant peaks?
        if hist.sum() < 25:
            return False
        top2_idx = hist.argsort()[-2:][::-1]
        a_idx, b_idx = int(top2_idx[0]), int(top2_idx[1])
        a_cnt, b_cnt = int(hist[a_idx]), int(hist[b_idx])

        # Require the second peak to be meaningful (user tunables)
        _amin, _amax, _q, min_bcnt, min_bratio = self._get_ca_vals()
        if b_cnt < max(min_bcnt, min_bratio * a_cnt):
            return False

        # Bin centers (degrees)
        bin_w = 180.0 / 36.0  # 5 degrees
        a_deg = (a_idx + 0.5) * bin_w
        b_deg = (b_idx + 0.5) * bin_w
        diff = abs(a_deg - b_deg)
        if diff > 90.0:
            diff = 180.0 - diff  # acute equivalent

        # Use UI-controlled band (safe)
        amin, amax, _, _, _ = self._get_ca_vals()
        return (amin <= diff <= amax)

    def _detect_corners(self, src_gray_0_255):
        """
        Detect strong corners on the *edges* of the obstacle mask.
        Using edges reduces flooding the map with “corners”.
        Returns a list of (x, y) float coordinates in image space.
        """
        try:
            obs = (src_gray_0_255 == 0).astype(np.uint8) * 255
            # Edge map for sparser, more localized interest points
            edges = cv2.Canny(obs, 80, 160, apertureSize=3, L2gradient=True)

            corners = cv2.goodFeaturesToTrack(
                image=edges,
                maxCorners=800,                            # keep bounded
                qualityLevel=self._get_ca_vals()[2],       # quality from safe getter
                minDistance=6,                             # spread them out a bit
                blockSize=5,
                useHarrisDetector=True,
                k=0.04
            )
            if corners is None:
                return []
            return [(float(c[0][0]), float(c[0][1])) for c in corners]
        except Exception:
            return []

    def _assign_anchor_points(self):
        """
        Mark control points close to detected corners as anchors (fixed) **only if**
        the local neighborhood shows two dominant edge directions forming 80°..100°.
        Uses adaptive radius (from CP spacing) and caps anchor ratio.
        """
        self.cp_anchor_idx = set()

        if not self.cp_points:
            return

        base = self.processed_map if self.processed_map is not None else self.filter_input_map
        if base is None:
            return

        # 1) Sparse corner proposals (on edges)
        corners = self._detect_corners(base)
        if not corners:
            self._status("Anchors assigned: 0 (no corners)")
            return

        # 2) Precompute edges + orientation once
        edges, theta = self._compute_edges_and_orientation(base)

        # 3) Adaptive radius from CP spacing, and a window size for angle test
        spacing = self._estimate_cp_spacing() if hasattr(self, "_estimate_cp_spacing") else 8.0
        radius = int(max(4, min(12, 0.45 * spacing)))     # for corner proximity
        r2 = float(radius * radius)

        # Window for the local angle check (odd-ish, scaled with spacing)
        win_px = int(max(11, min(41, 1.2 * spacing)))

        pts = np.array(self.cp_points, dtype=np.float32)
        candidates = []

        # Gather CP indices that are near ANY detected corner
        for i, (x, y) in enumerate(pts):
            for (cx, cy) in corners:
                dx = cx - x
                dy = cy - y
                if (dx * dx + dy * dy) <= r2:
                    candidates.append(i)
                    break

        if not candidates:
            self._status("Anchors assigned: 0 (no CPs near corners)")
            return

        # 4) Enforce the right-angle rule (80..100 deg)
        confirmed = []
        for i in candidates:
            x, y = pts[i]
            if self._has_right_angle_at(x, y, edges, theta, win_px):
                confirmed.append(i)

        if not confirmed:
            self._status("Anchors assigned: 0 (no right-angle corners)")
            return

        # 5) Cap anchors to avoid over-anchoring
        max_ratio = 0.18  # at most 18% of CPs
        cap = max(8, int(max_ratio * len(self.cp_points)))
        cap = min(cap, 250)

        # Deduplicate while preserving order
        seen = set()
        uniq = [c for c in confirmed if (c not in seen and not seen.add(c))]

        if len(uniq) > cap:
            # uniform down-sample to keep coverage
            step = len(uniq) / float(cap)
            picked = []
            acc = 0.0
            for _ in range(cap):
                idx = int(acc)
                picked.append(uniq[idx])
                acc += step
            self.cp_anchor_idx = set(picked)
        else:
            self.cp_anchor_idx = set(uniq)

        self._status(
            f"Anchors assigned: {len(self.cp_anchor_idx)} of {len(self.cp_points)} "
            f"(radius={radius}, win={win_px}, right-angle only)"
        )

    # -------- Lifecycle: prepare / iterate / start/stop/apply --------

    def _cp_prepare(self):
        base = self.processed_map if self.processed_map is not None else self.filter_input_map
        if base is None:
            messagebox.showwarning("No Map", "Load or produce a map first.")
            return False
        if not self.cp_points:
            messagebox.showwarning("No Control Points", "Generate control points first.")
            return False

        # freeze base map + occupancy
        self.cp_base_map = base.copy()
        self.cp_base_occ = (self.cp_base_map == 0).astype(np.uint8)  # 1=occupied, 0=free

        # initial working occupancy is the base
        self.cp_work_occ = self.cp_base_occ.copy()
        self._refresh_working_map_from_occ()

        # lock initial positions & previous positions
        self.cp_init = [(float(x), float(y)) for (x,y) in self.cp_points]
        self.cp_prev = [(float(x), float(y)) for (x,y) in self.cp_points]

        # build kernels at initial positions
        k = int(self.cp_kernel.get())
        if k % 2 == 0: k += 1
        k = clamp(k, 3, 99)
        self.cp_kernel.set(k)
        self.cp_kernels = [self._extract_kernel_at(self.cp_base_occ, x, y, k) for (x,y) in self.cp_points]

        # neighbors from current radius
        self.cp_neighbors = None
        self._cp_build_neighbors()

        self.cp_last_score = self._cp_score(self.cp_points)
        self.lbl_score.config(text=f"score: {self.cp_last_score:.3f}")
        self.lbl_iter.config(text="iter: 0")
        self.cp_need_prepare = False
        return True

    def _cp_iterate_once(self):
        """One gradient step on control points; then move kernels accordingly."""
        P = np.array(self.cp_points, np.float32)
        F = self._cp_forces(P)
        alpha = float(self.cp_alpha.get())
        P_new = P + alpha * F

        # keep inside image bounds
        base = self.processed_map if self.processed_map is not None else self.filter_input_map
        h, w = base.shape
        P_new[:,0] = np.clip(P_new[:,0], 0, w-1)
        P_new[:,1] = np.clip(P_new[:,1], 0, h-1)

        # ---- LOCK ANCHORS: keep corner-near control points fixed ----
        if self.cp_anchor_idx:
            anchor_idx = np.fromiter(self.cp_anchor_idx, dtype=np.int64)
            # Safety: clamp to bounds 0..len-1
            anchor_idx = anchor_idx[(anchor_idx >= 0) & (anchor_idx < P_new.shape[0])]
            if anchor_idx.size > 0:
                P_new[anchor_idx] = P[anchor_idx]

        # evaluate score
        new_score = self._cp_score(P_new)
        improved = (self.cp_last_score is None) or (new_score < self.cp_last_score - float(self.cp_tol.get()))

        # Update map by actually MOVING kernels (erase old footprint -> write new)
        if improved:
            new_positions = [(float(x), float(y)) for (x,y) in P_new]
            self.cp_work_occ = self._compose_from_kernels(self.cp_work_occ, self.cp_prev, new_positions, self.cp_kernels)
            self.cp_prev = new_positions
            self.cp_points = new_positions
            self.cp_last_score = new_score
            self._refresh_working_map_from_occ()
        return improved, new_score

    def _cp_step_once(self):
        if not self.cp_points:
            messagebox.showwarning("No Control Points", "Generate control points first.")
            return
        if self.cp_last_score is None or self.cp_need_prepare:
            if not self._cp_prepare():
                return
        improved, score = self._cp_iterate_once()
        self.update_preview()
        self.lbl_score.config(text=f"score: {score:.3f}")
        t = self.lbl_iter.cget("text")
        k = int(t.split(":")[-1]) if ":" in t else 0
        self.lbl_iter.config(text=f"iter: {k+1}")

    def _cp_loop_tick(self, it_left):
        if not self.cp_running:
            return
        if it_left <= 0:
            self._cp_stop()
            return
        improved, score = self._cp_iterate_once()
        self.update_preview()
        self.lbl_score.config(text=f"score: {score:.3f}")
        t = self.lbl_iter.cget("text")
        k = int(t.split(":")[-1]) if ":" in t else 0
        self.lbl_iter.config(text=f"iter: {k+1}")
        if not improved:
            self._cp_stop()
            return
        self.after(1, lambda: self._cp_loop_tick(it_left-1))

    def _cp_start(self):
        if self.cp_last_score is None or self.cp_need_prepare:
            if not self._cp_prepare():
                return
        self.cp_running = True
        self._status("Kernel optimizer running…")
        maxit = int(self.cp_max_iters.get())
        self._cp_loop_tick(maxit)

    def _cp_stop(self):
        if self.cp_running:
            self.cp_running = False
            self._status("Optimization stopped / converged")

    def _cp_apply(self):
        """Bake working map to processed_map (kernel-based result)."""
        if self.cp_working_map is None:
            messagebox.showinfo("Kernel Optimizer", "Nothing to apply yet.")
            return

        # Bake the kernel-optimized map
        self.processed_map = self.cp_working_map.copy()
        self.filter_input_map = self.processed_map.copy()

        # Clear optimization state
        self.cp_running = False
        self.cp_points = []
        self.cp_init = []
        self.cp_prev = []
        self.cp_pairs = []
        self.cp_neighbors = None
        self.cp_kernels = []
        self.cp_base_map = None
        self.cp_base_occ = None
        self.cp_work_occ = None
        self.cp_working_map = None
        self.cp_last_score = None
        self.cp_need_prepare = False
        self.cp_anchor_idx = set()

        self._push_history_snapshot()
        self.update_preview()
        messagebox.showinfo("Kernel Optimizer", "Applied kernel-optimized map to Enhanced and set as Filtering base.")

    def _cp_revert(self):
        """Revert working map to base; reset CP positions to init."""
        if self.cp_base_map is None:
            return
        self.cp_work_occ = self.cp_base_occ.copy()
        self._refresh_working_map_from_occ()
        self.cp_points = [(x,y) for (x,y) in self.cp_init]
        self.cp_prev = [(x,y) for (x,y) in self.cp_init]
        self.cp_last_score = None
        self.lbl_iter.config(text="iter: 0")
        self.lbl_score.config(text="score: -")
        self.update_preview()
        self._status("Working copy reverted.")

if __name__ == "__main__":
    app = MapEnhancerWizard()
    app.mainloop()
