import base64
import io

from PIL import Image


MAX_IMAGE_SIZE = (700, 700)
JPEG_QUALITY = 82


def prepare_image_data(uploaded_file):
    """Resize/compress an uploaded image and return a JPEG data URI."""
    if uploaded_file is None:
        return None

    image = Image.open(uploaded_file)
    image = image.convert("RGB")
    image.thumbnail(MAX_IMAGE_SIZE)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def image_markup(image_data, alt="Product", css_class="product-image"):
    if image_data:
        safe_alt = str(alt).replace('"', "&quot;")
        return f'<img class="{css_class}" src="{image_data}" alt="{safe_alt}">'

    return (
        f'<div class="{css_class} no-product-image">'
        '<span>🛍️</span><small>No image</small></div>'
    )
