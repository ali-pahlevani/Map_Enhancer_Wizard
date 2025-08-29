import cv2
from utils.clamp import clamp

def morphological_kernel(size):
    # Create a square structuring element of odd size
    size = clamp(int(size), 1, 99)  # Ensure size is within valid range
    if size % 2 == 0:
        size += 1  # Force odd size for symmetry
    return cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))