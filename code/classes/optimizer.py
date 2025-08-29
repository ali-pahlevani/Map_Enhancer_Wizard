# Handles control point optimization and corner anchor detection for the Map Enhancer Wizard.
# Manages optimization parameters, UI for the Optimization tab, and canvas interactions.

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
from utils.clamp import clamp
from utils.safe_int import safe_int
from utils.safe_float import safe_float
from classes.tooltip import ToolTip

class Optimizer:
    def __init__(self, app):
        # Initialize with reference to main application
        self.app = app

        # Optimization parameters
        self.n = tk.IntVar(value=2000)                 # Number of control points
        self.kernel = tk.IntVar(value=5)               # Kernel size for control points
        self.sigma = tk.DoubleVar(value=14.0)          # Unused (legacy parameter)
        self.alpha = tk.DoubleVar(value=0.05)          # Step size for gradient updates
        self.lc = tk.DoubleVar(value=2.0)              # Line constraint weight
        self.ls = tk.DoubleVar(value=0.08)             # Laplacian smoothing weight
        self.nb_radius = tk.IntVar(value=8)            # Neighbor radius for smoothing
        self.max_iters = tk.IntVar(value=100)          # Maximum optimization iterations
        self.tol = tk.DoubleVar(value=1e-3)            # Convergence tolerance

        # Corner anchor detection parameters
        self.ca_angle_min = tk.DoubleVar(value=85.0)   # Minimum angle for corner detection (°)
        self.ca_angle_max = tk.DoubleVar(value=95.0)   # Maximum angle for corner detection (°)
        self.ca_quality = tk.DoubleVar(value=0.05)     # Quality level for corner detection
        self.ca_min_bcnt = tk.IntVar(value=5)          # Minimum secondary peak count
        self.ca_min_bratio = tk.DoubleVar(value=0.20)  # Minimum secondary peak ratio

        # State for anchor rebuilding
        self._ca_after_id = None                       # After ID for debounced anchor rebuild
        def _rebuild_on_change(*_):
            # Debounce anchor rebuilding on parameter change
            if self._ca_after_id is not None:
                try:
                    self.app.after_cancel(self._ca_after_id)
                except Exception:
                    pass
            self._ca_after_id = self.app.after(150, self._rebuild_anchors_if_any)
        for v in [self.ca_angle_min, self.ca_angle_max, self.ca_quality, self.ca_min_bcnt, self.ca_min_bratio]:
            v.trace_add("write", _rebuild_on_change)

        # Control point and optimization state
        self.points = []                               # Current control points [(x,y), ...]
        self.init = []                                 # Initial control points
        self.prev = []                                 # Previous control points
        self.pairs = []                                # User-defined constraint pairs [(i,j), ...]
        self.selected = None                           # Currently selected control point index
        self.hit_radius = 14                           # Click radius for selecting points
        self.running = False                           # Optimization running state
        self.last_score = None                         # Last computed score
        self.neighbors = None                          # Neighbor indices for each point
        self.kernels = []                              # Kernels for each control point
        self.base_map = None                           # Base map for optimization
        self.base_occ = None                           # Base occupancy (binary)
        self.work_occ = None                           # Working occupancy map
        self.working_map = None                        # Current optimized map
        self.need_prepare = False                      # Flag for re-preparation
        self.anchor_idx = set()                        # Indices of anchor points

        # Bind traces for optimization parameters
        self.bind_param_traces()

    def bind_param_traces(self):
        # Mark optimization as needing preparation when parameters change
        def mark_dirty(*_):
            self.need_prepare = True
        for v in [self.kernel, self.alpha, self.lc, self.ls, self.nb_radius, self.max_iters, self.tol]:
            v.trace_add("write", mark_dirty)

    def _rebuild_anchors_if_any(self):
        # Rebuild anchor points if control points exist
        if self.points:
            self.assign_anchor_points()
            self.app.update_preview()

    def build_ui(self, parent):
        # Build UI for Optimization tab
        genf = ttk.Labelframe(parent, text="Control Points", padding=10, style="Card.TLabelframe")
        genf.pack(fill="x", pady=(0,8))
        ttk.Label(genf, text="N points:").grid(row=0, column=0, sticky="w")
        ttk.Entry(genf, width=8, textvariable=self.n).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(genf, text="Generate (occupied only)", command=self.generate, style="Modern.TButton").grid(row=0, column=2, padx=6)
        ttk.Button(genf, text="Clear Pairs", command=self.clear_pairs, style="Modern.TButton").grid(row=0, column=3, padx=6)
        ttk.Label(genf, text="Click two red points to toggle a green constraint line. Double-click a node to remove all its connections.").grid(row=1, column=0, columnspan=4, sticky="w", pady=(6,0))

        # Optimization parameters section
        el = ttk.Labelframe(parent, text="Kernel & Optimization Parameters", padding=10, style="Card.TLabelframe")
        el.pack(fill="x", pady=(0,8))
        def put(r,c,txt,var,w=8,tip=None):
            # Helper to create labeled entry with tooltip
            ttk.Label(el, text=txt).grid(row=r, column=c*2, sticky="w")
            e = ttk.Entry(el, width=w, textvariable=var); e.grid(row=r, column=c*2+1, sticky="w", padx=4)
            if tip: ToolTip(e, tip)
        put(0,0,"Kernel size (odd):", self.kernel, tip="3, 5, 7, ... Kernel a CP carries.")
        put(0,1,"Step α:", self.alpha, tip="Gradient step size per iteration.")
        put(0,2,"Line weight λc:", self.lc, tip="Weight for user constraints (pull endpoints together).")
        put(1,0,"Elastic weight λs:", self.ls, tip="Neighbor Laplacian weight.")
        put(1,1,"Neighbor radius (px):", self.nb_radius, tip="Neighbors within this radius influence each other.")
        put(1,2,"Max iters:", self.max_iters, tip="Max optimization iterations.")
        put(2,0,"Tol (Δscore):", self.tol, tip="Stop if improvement below this value.")

        # Corner anchor settings
        anchorf = ttk.Labelframe(parent, text="Corner Anchor Settings", padding=10, style="Card.TLabelframe")
        anchorf.pack(fill="x", pady=(0,8))
        row1 = ttk.Frame(anchorf, style="TFrame"); row1.pack(fill="x", pady=4)
        ttk.Label(row1, text="Angle band (°):").pack(side="left")
        ttk.Entry(row1, width=6, textvariable=self.ca_angle_min).pack(side="left", padx=(6,4))
        ttk.Label(row1, text="to").pack(side="left")
        ttk.Entry(row1, width=6, textvariable=self.ca_angle_max).pack(side="left", padx=(6,0))
        row2 = ttk.Frame(anchorf, style="TFrame"); row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="qualityLevel:").pack(side="left")
        ttk.Entry(row2, width=8, textvariable=self.ca_quality).pack(side="left", padx=(6,0))
        ttk.Label(row2, text="(0..1; higher = stricter)").pack(side="left", padx=(6,0))
        row3 = ttk.Frame(anchorf, style="TFrame"); row3.pack(fill="x", pady=4)
        ttk.Label(row3, text="2nd peak ≥").pack(side="left")
        ttk.Entry(row3, width=6, textvariable=self.ca_min_bcnt).pack(side="left", padx=(6,4))
        ttk.Label(row3, text="or ≥").pack(side="left")
        ttk.Entry(row3, width=6, textvariable=self.ca_min_bratio).pack(side="left", padx=(6,4))
        ttk.Label(row3, text="× 1st peak").pack(side="left")
        row4 = ttk.Frame(anchorf, style="TFrame"); row4.pack(fill="x", pady=6)
        ttk.Button(row4, text="Rebuild Anchors Now", command=self._rebuild_anchors_if_any, style="Modern.TButton").pack(side="left")

        # Run controls
        runf = ttk.Labelframe(parent, text="Run", padding=10, style="Card.TLabelframe")
        runf.pack(fill="x")
        ttk.Button(runf, text="Start", command=self.start, style="Modern.TButton").grid(row=0, column=0, padx=4, pady=2, sticky="ew")
        ttk.Button(runf, text="Step Once", command=self.step_once, style="Modern.TButton").grid(row=0, column=1, padx=4, pady=2, sticky="ew")
        ttk.Button(runf, text="Stop", command=self.stop, style="Modern.TButton").grid(row=0, column=2, padx=4, pady=2, sticky="ew")
        ttk.Button(runf, text="Apply to Enhanced", command=self.apply, style="Modern.TButton").grid(row=1, column=0, columnspan=2, padx=4, pady=6, sticky="ew")
        ttk.Button(runf, text="Revert Working", command=self.revert, style="Modern.TButton").grid(row=1, column=2, padx=4, pady=6, sticky="ew")

        # Status display
        stat = ttk.Labelframe(parent, text="Status", padding=10, style="Card.TLabelframe")
        stat.pack(fill="x")
        self.lbl_iter = ttk.Label(stat, text="iter: 0"); self.lbl_iter.grid(row=0, column=0, sticky="w")
        self.lbl_score = ttk.Label(stat, text="score: -"); self.lbl_score.grid(row=0, column=1, sticky="w", padx=(12,0))
        ttk.Label(stat, text="Tip: middle-mouse to pan, mouse wheel to zoom. 'F' to fit window.").grid(row=1, column=0, columnspan=3, sticky="w", pady=(6,0))

    def generate(self):
        # Generate control points on occupied pixels using k-means
        src = self.app.processed_map if self.app.processed_map is not None else self.app.filter_input_map
        if src is None:
            messagebox.showwarning("No Map", "Load or produce a map first.")
            return
        pts = self.occupied_coords()
        if len(pts) == 0:
            messagebox.showwarning("No Occupied Pixels", "Adjust filtering so obstacles are black (0).")
            return
        N = int(self.n.get())
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
        self.points = [(float(x), float(y)) for (x,y) in centers]
        self.init = [(float(x), float(y)) for (x,y) in centers]
        self.prev = [(float(x), float(y)) for (x,y) in centers]
        self.pairs = []
        self.selected = None
        self.neighbors = None
        self.last_score = None
        self.kernels = []
        self.base_map = None
        self.base_occ = None
        self.work_occ = None
        self.working_map = None
        self.need_prepare = True
        self.assign_anchor_points()
        self.app._status(f"Generated {len(self.points)} control points.")
        self.app.update_preview()

    def occupied_coords(self):
        # Get coordinates of occupied (black) pixels
        src = self.app.processed_map if self.app.processed_map is not None else self.app.filter_input_map
        if src is None:
            return np.empty((0,2), np.float32)
        mask = (src == 0)
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return np.empty((0,2), np.float32)
        return np.stack([xs, ys], axis=1).astype(np.float32)

    def clear_pairs(self):
        # Clear all user-defined constraint pairs
        self.pairs = []
        self.selected = None
        self.app._status("Cleared constraint pairs.")
        self.app.update_preview()

    def build_neighbors(self):
        # Build neighbor lists for each control point based on radius
        if not self.points:
            self.neighbors = []
            return
        pts = np.array(self.points, dtype=np.float32)
        R = float(self.nb_radius.get())
        R2 = R*R
        n = len(pts)
        neigh = [[] for _ in range(n)]
        for i in range(n):
            dx = pts[:,0] - pts[i,0]
            dy = pts[:,1] - pts[i,1]
            d2 = dx*dx + dy*dy
            idxs = np.where((d2 > 0.0) & (d2 <= R2))[0]
            neigh[i] = idxs.tolist()
        self.neighbors = neigh

    def score(self, P):
        # Compute optimization score based on constraint pairs
        if not self.pairs:
            return 0.0
        pts = np.array(P, dtype=np.float32)
        s = 0.0
        for (i,j) in self.pairs:
            d = pts[j] - pts[i]
            s += float(d[0]*d[0] + d[1]*d[1])
        return s

    def forces(self, P):
        # Compute forces for control point movement
        n = len(P)
        F = np.zeros((n,2), np.float32)
        pts = np.array(P, dtype=np.float32)
        lc = float(self.lc.get())
        ls = float(self.ls.get())
        for (i,j) in self.pairs:
            d = pts[j] - pts[i]
            F[i] += lc * d  # Pull paired points together
            F[j] += lc * (-d)
        if self.neighbors is None:
            self.build_neighbors()
        for i, neigh in enumerate(self.neighbors or []):
            if not neigh: continue
            diff = pts[neigh] - pts[i]
            F[i] += ls * diff.sum(axis=0)  # Laplacian smoothing
        return F

    def extract_kernel_at(self, occ01, cx, cy, k):
        # Extract kernel around a control point
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

    def compose_from_kernels(self, prev_occ, prev_positions, new_positions, kernels):
        # Reconstruct occupancy map by moving kernels to new positions
        out = prev_occ.copy()
        h, w = out.shape
        k = kernels[0].shape[0] if kernels else 0
        r = k // 2
        for (px,py), K in zip(prev_positions, kernels):
            cx = int(round(px)); cy = int(round(py))
            x0 = cx - r; y0 = cy - r
            xs0 = max(0, x0); ys0 = max(0, y0)
            xs1 = min(w, x0 + k); ys1 = min(h, y0 + k)
            if xs0 < xs1 and ys0 < ys1:
                out[ys0:ys1, xs0:xs1] = 0  # Clear previous kernel
        for (nx,ny), K in zip(new_positions, kernels):
            cx = int(round(nx)); cy = int(round(ny))
            x0 = cx - r; y0 = cy - r
            xs0 = max(0, x0); ys0 = max(0, y0)
            xs1 = min(w, x0 + k); ys1 = min(h, y0 + k)
            if xs0 < xs1 and ys0 < ys1:
                kx0 = xs0 - x0; ky0 = ys0 - y0
                kx1 = kx0 + (xs1 - xs0); ky1 = ky0 + (ys1 - ys0)
                out[ys0:ys1, xs0:xs1] = K[ky0:ky1, kx0:kx1]  # Place new kernel
        return out

    def refresh_working_map_from_occ(self):
        # Convert binary occupancy to grayscale map
        if self.work_occ is None:
            return None
        self.working_map = np.where(self.work_occ > 0, 0, 255).astype(np.uint8)
        return self.working_map

    def estimate_cp_spacing(self):
        # Estimate average spacing between control points
        if not self.points or len(self.points) < 2:
            return 8.0
        pts = np.array(self.points, dtype=np.float32)
        if len(pts) > 400:
            idx = np.random.choice(len(pts), 400, replace=False)
            pts = pts[idx]
        dmins = []
        for i in range(len(pts)):
            dx = pts[:, 0] - pts[i, 0]
            dy = pts[:, 1] - pts[i, 1]
            d2 = dx * dx + dy * dy
            d2[i] = 1e12
            dmins.append(float(np.sqrt(d2.min())))
        dmins.sort()
        k = max(5, int(0.2 * len(dmins)))
        return max(4.0, float(np.mean(dmins[:k])))

    def get_ca_vals(self):
        # Get and validate corner anchor parameters
        amin = safe_float(self.ca_angle_min.get(), 85.0)
        amax = safe_float(self.ca_angle_max.get(), 95.0)
        quality = safe_float(self.ca_quality.get(), 0.05)
        min_bcnt = safe_int(self.ca_min_bcnt.get(), 5)
        min_bratio = safe_float(self.ca_min_bratio.get(), 0.20)
        quality = clamp(quality, 0.0, 1.0)
        min_bcnt = clamp(min_bcnt, 0, 1_000_000)
        min_bratio = clamp(min_bratio, 0.0, 1.0)
        amin = clamp(amin, 0.0, 180.0)
        amax = clamp(amax, 0.0, 180.0)
        if amin > amax:
            amin, amax = amax, amin
        return amin, amax, quality, min_bcnt, min_bratio

    def compute_edges_and_orientation(self, base_gray_0_255):
        # Compute edges and orientation angles for corner detection
        obs = (base_gray_0_255 == 0).astype(np.uint8) * 255
        edges = cv2.Canny(obs, 80, 160, apertureSize=3, L2gradient=True)
        gx = cv2.Sobel(obs, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(obs, cv2.CV_32F, 0, 1, ksize=3)
        ang = cv2.phase(gx, gy, angleInDegrees=True)
        theta = (ang % 180.0).astype(np.float32)
        return edges, theta

    def has_right_angle_at(self, x, y, edges, theta, win_px):
        # Check if a point has a right-angle corner
        h, w = edges.shape
        hw = int(max(5, min(60, win_px)) // 2)
        cx = int(round(x)); cy = int(round(y))
        x0 = max(0, cx - hw); x1 = min(w, cx + hw + 1)
        y0 = max(0, cy - hw); y1 = min(h, cy + hw + 1)
        patch_edges = edges[y0:y1, x0:x1]
        if patch_edges.size == 0:
            return False
        mask = (patch_edges > 0)
        if mask.sum() < 20:
            return False
        patch_theta = theta[y0:y1, x0:x1][mask]
        bins = np.linspace(0.0, 180.0, 37)
        hist, _ = np.histogram(patch_theta, bins=bins)
        if hist.sum() < 25:
            return False
        top2_idx = hist.argsort()[-2:][::-1]
        a_idx, b_idx = int(top2_idx[0]), int(top2_idx[1])
        a_cnt, b_cnt = int(hist[a_idx]), int(hist[b_idx])
        amin, amax, _, min_bcnt, min_bratio = self.get_ca_vals()
        if b_cnt < max(min_bcnt, min_bratio * a_cnt):
            return False
        bin_w = 180.0 / 36.0
        a_deg = (a_idx + 0.5) * bin_w
        b_deg = (b_idx + 0.5) * bin_w
        diff = abs(a_deg - b_deg)
        if diff > 90.0:
            diff = 180.0 - diff
        return (amin <= diff <= amax)

    def detect_corners(self, src_gray_0_255):
        # Detect corners using OpenCV's goodFeaturesToTrack
        try:
            obs = (src_gray_0_255 == 0).astype(np.uint8) * 255
            edges = cv2.Canny(obs, 80, 160, apertureSize=3, L2gradient=True)
            corners = cv2.goodFeaturesToTrack(
                image=edges,
                maxCorners=800,
                qualityLevel=self.get_ca_vals()[2],
                minDistance=6,
                blockSize=5,
                useHarrisDetector=True,
                k=0.04
            )
            if corners is None:
                return []
            return [(float(c[0][0]), float(c[0][1])) for c in corners]
        except Exception:
            return []

    def assign_anchor_points(self):
        # Assign control points near detected corners as anchors
        self.anchor_idx = set()
        if not self.points:
            return
        base = self.app.processed_map if self.app.processed_map is not None else self.app.filter_input_map
        if base is None:
            return
        corners = self.detect_corners(base)
        if not corners:
            self.app._status("Anchors assigned: 0 (no corners)")
            return
        edges, theta = self.compute_edges_and_orientation(base)
        spacing = self.estimate_cp_spacing()
        radius = int(max(4, min(12, 0.45 * spacing)))
        r2 = float(radius * radius)
        win_px = int(max(11, min(41, 1.2 * spacing)))
        pts = np.array(self.points, dtype=np.float32)
        candidates = []
        for i, (x, y) in enumerate(pts):
            for (cx, cy) in corners:
                dx = cx - x
                dy = cy - y
                if (dx * dx + dy * dy) <= r2:
                    candidates.append(i)
                    break
        if not candidates:
            self.app._status("Anchors assigned: 0 (no CPs near corners)")
            return
        confirmed = []
        for i in candidates:
            x, y = pts[i]
            if self.has_right_angle_at(x, y, edges, theta, win_px):
                confirmed.append(i)
        if not confirmed:
            self.app._status("Anchors assigned: 0 (no right-angle corners)")
            return
        max_ratio = 0.18
        cap = max(8, int(max_ratio * len(self.points)))
        cap = min(cap, 250)
        seen = set()
        uniq = [c for c in confirmed if c not in seen and not seen.add(c)]
        if len(uniq) > cap:
            step = len(uniq) / float(cap)
            picked = []
            acc = 0.0
            for _ in range(cap):
                idx = int(acc)
                picked.append(uniq[idx])
                acc += step
            self.anchor_idx = set(picked)
        else:
            self.anchor_idx = set(uniq)
        self.app._status(f"Anchors assigned: {len(self.anchor_idx)} of {len(self.points)} (radius={radius}, win={win_px}, right-angle only)")

    def prepare(self):
        # Prepare optimization by initializing maps and kernels
        base = self.app.processed_map if self.app.processed_map is not None else self.app.filter_input_map
        if base is None:
            messagebox.showwarning("No Map", "Load or produce a map first.")
            return False
        if not self.points:
            messagebox.showwarning("No Control Points", "Generate control points first.")
            return False
        self.base_map = base.copy()
        self.base_occ = (self.base_map == 0).astype(np.uint8)
        self.work_occ = self.base_occ.copy()
        self.refresh_working_map_from_occ()
        self.init = [(float(x), float(y)) for (x,y) in self.points]
        self.prev = [(float(x), float(y)) for (x,y) in self.points]
        k = int(self.kernel.get())
        if k % 2 == 0: k += 1
        k = clamp(k, 3, 99)
        self.kernel.set(k)
        self.kernels = [self.extract_kernel_at(self.base_occ, x, y, k) for (x,y) in self.points]
        self.neighbors = None
        self.build_neighbors()
        self.last_score = self.score(self.points)
        self.lbl_score.config(text=f"score: {self.last_score:.3f}")
        self.lbl_iter.config(text="iter: 0")
        self.need_prepare = False
        return True

    def iterate_once(self):
        # Perform one optimization iteration
        P = np.array(self.points, np.float32)
        F = self.forces(P)
        alpha = float(self.alpha.get())
        P_new = P + alpha * F
        base = self.app.processed_map if self.app.processed_map is not None else self.app.filter_input_map
        h, w = base.shape
        P_new[:,0] = np.clip(P_new[:,0], 0, w-1)
        P_new[:,1] = np.clip(P_new[:,1], 0, h-1)
        if self.anchor_idx:
            anchor_idx = np.array(list(self.anchor_idx), dtype=np.int64)
            anchor_idx = anchor_idx[(anchor_idx >= 0) & (anchor_idx < len(P_new))]
            if len(anchor_idx) > 0:
                P_new[anchor_idx] = P[anchor_idx]  # Keep anchors fixed
        new_score = self.score(P_new)
        improved = (self.last_score is None) or (new_score < self.last_score - float(self.tol.get()))
        if improved:
            new_positions = [(float(x), float(y)) for (x,y) in P_new]
            self.work_occ = self.compose_from_kernels(self.work_occ, self.prev, new_positions, self.kernels)
            self.prev = new_positions
            self.points = new_positions
            self.last_score = new_score
            self.refresh_working_map_from_occ()
        return improved, new_score

    def step_once(self):
        # Perform a single optimization step
        if not self.points:
            messagebox.showwarning("No Control Points", "Generate control points first.")
            return
        if self.last_score is None or self.need_prepare:
            if not self.prepare():
                return
        improved, score = self.iterate_once()
        self.app.update_preview()
        self.lbl_score.config(text=f"score: {score:.3f}")
        t = self.lbl_iter.cget("text")
        k = int(t.split(":")[-1]) if ":" in t else 0
        self.lbl_iter.config(text=f"iter: {k+1}")

    def loop_tick(self, it_left):
        # Run optimization loop with remaining iterations
        if not self.running:
            return
        if it_left <= 0:
            self.stop()
            return
        improved, score = self.iterate_once()
        self.app.update_preview()
        self.lbl_score.config(text=f"score: {score:.3f}")
        t = self.lbl_iter.cget("text")
        k = int(t.split(":")[-1]) if ":" in t else 0
        self.lbl_iter.config(text=f"iter: {k+1}")
        if not improved:
            self.stop()
            return
        self.app.after(1, lambda: self.loop_tick(it_left-1))

    def start(self):
        # Start continuous optimization
        if self.last_score is None or self.need_prepare:
            if not self.prepare():
                return
        self.running = True
        self.app._status("Kernel optimizer running…")
        maxit = int(self.max_iters.get())
        self.loop_tick(maxit)

    def stop(self):
        # Stop optimization
        if self.running:
            self.running = False
            self.app._status("Optimization stopped / converged")

    def apply(self):
        # Apply optimized map to main application
        if self.working_map is None:
            messagebox.showinfo("Kernel Optimizer", "Nothing to apply yet.")
            return
        self.app.processed_map = self.working_map.copy()
        self.app.filter_input_map = self.app.processed_map.copy()
        self.reset_state()
        self.app._push_history_snapshot()
        self.app.update_preview()
        messagebox.showinfo("Kernel Optimizer", "Applied kernel-optimized map to Enhanced and set as Filtering base.")

    def revert(self):
        # Revert to initial state
        if self.base_map is None:
            return
        self.work_occ = self.base_occ.copy()
        self.refresh_working_map_from_occ()
        self.points = [(x,y) for (x,y) in self.init]
        self.prev = [(x,y) for (x,y) in self.init]
        self.last_score = None
        self.lbl_iter.config(text="iter: 0")
        self.lbl_score.config(text="score: -")
        self.app.update_preview()
        self.app._status("Working copy reverted.")

    def reset_state(self):
        # Reset all optimization state
        self.running = False
        self.points = []
        self.init = []
        self.prev = []
        self.pairs = []
        self.neighbors = None
        self.kernels = []
        self.base_map = None
        self.base_occ = None
        self.work_occ = None
        self.working_map = None
        self.last_score = None
        self.need_prepare = False
        self.anchor_idx = set()
        self.selected = None

    def on_canvas_click(self, ev):
        # Handle single-click to select or pair control points
        if self.app.preview_mode.get() != "enhanced":
            return
        if not self.points:
            return
        imgxy = self.app._from_canvas(ev.x, ev.y)
        if imgxy is None:
            return
        best = None; bestd2 = 1e9
        for i,(x,y) in enumerate(self.points):
            cx, cy = self.app._to_canvas(x,y)
            d2 = (cx-ev.x)**2 + (cy-ev.y)**2
            if d2 < bestd2:
                bestd2 = d2; best = i
        if best is None or bestd2 > (self.hit_radius**2):
            return
        if self.selected is None:
            self.selected = best
        else:
            i = self.selected
            j = best
            if i != j:
                pair = (min(i,j), max(i,j))
                if pair in self.pairs:
                    self.pairs.remove(pair)
                else:
                    self.pairs.append(pair)
            self.selected = None
        self.app.update_preview()

    def on_canvas_double_click(self, ev):
        # Handle double-click to remove all connections for a control point
        if not self.points:
            return
        imgxy = self.app._from_canvas(ev.x, ev.y)
        if imgxy is None:
            return
        best = None; bestd2 = 1e9
        for i,(x,y) in enumerate(self.points):
            cx, cy = self.app._to_canvas(x,y)
            d2 = (cx-ev.x)**2 + (cy-ev.y)**2
            if d2 < bestd2:
                bestd2 = d2; best = i
        if best is None or bestd2 > (self.hit_radius**2):
            return
        self.pairs = [p for p in self.pairs if (best not in p)]
        if self.selected == best:
            self.selected = None
        self.app.update_preview()