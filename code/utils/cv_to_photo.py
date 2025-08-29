import cv2
from PIL import Image, ImageTk

def cv_to_photo(img):
    # Convert OpenCV image (grayscale or BGR) to PhotoImage
    if img.ndim == 2:
        pil = Image.fromarray(img)  # Grayscale image
    else:
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))  # Convert BGR to RGB
    return ImageTk.PhotoImage(pil)  # Return Tkinter-compatible image