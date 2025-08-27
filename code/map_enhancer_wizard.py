import tkinter as tk
from tkinter import ttk
from map_enhancer_2d import MapEnhancer2D
from map_enhancer_3d import MapEnhancer3D

class MapEnhancerWizard(tk.Tk):
    """Launcher window that lets the user pick between 2D and 3D modes."""

    def __init__(self):
        super().__init__()
        self.title("Map Enhancer Wizard")
        self.geometry("300x150")
        self.init_ui()

    def init_ui(self):
        ttk.Button(self, text="2D Map Enhancer", command=self.launch_2d).pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        ttk.Button(self, text="3D Map Enhancer", command=self.launch_3d).pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    def launch_2d(self):
        self.destroy()
        app = MapEnhancer2D()
        app.mainloop()

    def launch_3d(self):
        self.destroy()
        app = MapEnhancer3D()
        app.mainloop()

if __name__ == "__main__":
    app = MapEnhancerWizard()
    app.mainloop()
