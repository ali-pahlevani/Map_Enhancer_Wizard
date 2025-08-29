def safe_float(v, default=0.0):
    # Convert value to float, return default if conversion fails
    try:
        return float(v)
    except Exception:
        return default