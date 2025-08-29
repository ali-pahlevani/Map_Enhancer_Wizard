def safe_int(v, default=0):
    # Convert value to integer, return default if conversion fails
    try:
        return int(v)
    except Exception:
        return default