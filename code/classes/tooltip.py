import tkinter as tk

class ToolTip:
    def __init__(self, widget, text, delay_ms=350):
        # Initialize tooltip for a widget
        self.widget = widget            # Target widget for tooltip
        self.text = text                # Tooltip text to display
        self.tip_window = None          # Toplevel window for tooltip (None when hidden)
        self.after_id = None            # ID for scheduled tooltip display
        self.delay_ms = delay_ms        # Delay before showing tooltip (ms)

        # Bind widget events for tooltip behavior
        widget.bind("<Enter>", self._schedule)    # Show tooltip on mouse enter
        widget.bind("<Leave>", self._hide)       # Hide tooltip on mouse leave
        widget.bind("<ButtonPress>", self._hide)  # Hide tooltip on click

    def _schedule(self, _):
        # Schedule tooltip display after delay
        self._cancel()  # Cancel any existing schedule
        self.after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        # Cancel scheduled tooltip display
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self):
        # Display tooltip window at widget's position
        if self.tip_window or not self.text:
            return  # Skip if already shown or no text
        # Position tooltip below and slightly right of widget
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)  # Remove window decorations
        tw.wm_geometry(f"+{x}+{y}")   # Set position
        # Create label with styled tooltip text
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",      # Light yellow background
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 10),
            padx=6,
            pady=4,
        )
        label.pack()

    def _hide(self, _=None):
        # Hide and destroy tooltip window
        self._cancel()  # Cancel any scheduled display
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None