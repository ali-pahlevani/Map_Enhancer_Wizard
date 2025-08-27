import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import sqlite3
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class MapEnhancer3D(tk.Tk):
    """Simple 3D map enhancer that works with SQLite `.db` files.

    Rather than requiring a rigid schema, the loader now scans the database for
    any table containing 3D coordinate columns. It first looks for a table with
    `x`, `y`, `z` and optionally `value` columns. If those are not found, it
    also checks for RTAB-Map style columns such as `pose_x`, `pose_y` and
    `pose_z`. The detected columns are used to build a minimal point cloud which
    can then be filtered by the threshold slider.

    This is an intentionally lightweight visualisation intended as a starting
    point for more advanced 3D enhancements."""

    def __init__(self):
        super().__init__()
        self.title("Map Enhancer Wizard 3D (V1)")
        self.geometry("1200x800")

        self.points = None
        self.filtered_points = None

        self.init_ui()

    def init_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        # Controls frame on the left
        self.controls_frame = ttk.Frame(self, padding=10, relief=tk.RAISED)
        self.controls_frame.grid(row=0, column=0, sticky="nsew")

        self.select_btn = ttk.Button(self.controls_frame, text="Select .db Map", command=self.select_file)
        self.select_btn.pack(fill=tk.X, pady=5)

        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill=tk.X, pady=5)

        self.threshold_var = tk.DoubleVar(value=0.5)
        ttk.Label(self.controls_frame, text="Threshold (0-1)").pack(pady=5)
        self.threshold_slider = ttk.Scale(self.controls_frame, from_=0.0, to=1.0, variable=self.threshold_var, command=self.update_plot)
        self.threshold_slider.pack(fill=tk.X, pady=10)

        # Plot area on the right
        self.figure = Figure()
        self.ax = self.figure.add_subplot(111, projection='3d')
        self.canvas_plot = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas_plot.get_tk_widget().grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        # Status bar
        self.status_frame = ttk.Frame(self, relief=tk.SUNKEN)
        self.status_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status_label = ttk.Label(self.status_frame, text="Select a .db map to begin.")
        self.status_label.pack(side=tk.LEFT, padx=5, pady=2)

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("DB Files", "*.db"), ("All Files", "*.*")])
        if file_path:
            self.load_map(file_path)

    def load_map(self, file_path):
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()

            table, cols = self._detect_point_table(cursor)
            if table is None:
                raise ValueError("No table with x/y/z coordinates found")

            query = f"SELECT {cols[0]}, {cols[1]}, {cols[2]}"
            if cols[3]:
                query += f", {cols[3]}"
            else:
                query += ", 1.0"  # default intensity
            query += f" FROM {table}"

            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read map data: {e}")
            return

        if not rows:
            messagebox.showerror("Error", "No usable map data found in the database.")
            return

        self.points = np.array(rows, dtype=float)
        self.status_label.config(text=f"Map loaded: {file_path}")
        self.update_plot()

    def _detect_point_table(self, cursor):
        """Return a tuple (table_name, (x, y, z, value_col or None))."""

        tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            cols = [row[1].lower() for row in cursor.execute(f"PRAGMA table_info({table})")]
            colset = set(cols)
            if {'x', 'y', 'z', 'value'} <= colset:
                return table, ('x', 'y', 'z', 'value')
            if {'x', 'y', 'z'} <= colset:
                return table, ('x', 'y', 'z', None)
            if {'pose_x', 'pose_y', 'pose_z'} <= colset:
                return table, ('pose_x', 'pose_y', 'pose_z', None)
        return None, None

    def apply_filters(self):
        if self.points is None:
            return
        thresh = self.threshold_var.get()
        mask = self.points[:, 3] <= thresh
        self.filtered_points = self.points[mask]

    def update_plot(self, *args):
        self.apply_filters()
        self.ax.clear()
        if self.filtered_points is not None and len(self.filtered_points) > 0:
            pts = self.filtered_points
            self.ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], c=pts[:, 3], cmap='gray')
        self.canvas_plot.draw()

if __name__ == "__main__":
    app = MapEnhancer3D()
    app.mainloop()
