from PIL import Image

# Open your existing PNG or JPG
img = Image.open("ulm_logo.png")

# Save it as an ICO file with standard Windows icon sizes
img.save("ULM_icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])