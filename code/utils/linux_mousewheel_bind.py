import platform

def linux_mousewheel_bind(widget, wheel_cb, up_id="<Button-4>", down_id="<Button-5>"):
    # Bind mouse wheel events, handling platform-specific differences
    sys = platform.system()
    if sys in ("Windows", "Darwin"):
        widget.bind("<MouseWheel>", wheel_cb)  # Standard wheel event for Windows/Mac
    else:
        widget.bind(up_id, wheel_cb)  # Linux scroll up event
        widget.bind(down_id, wheel_cb)  # Linux scroll down event