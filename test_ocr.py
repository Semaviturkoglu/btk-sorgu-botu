from pytesseract import image_to_string
from PIL import Image

print(image_to_string(Image.open("captcha.png")).strip())
