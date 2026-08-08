import base64
import io

from PIL import Image

MAX_IMAGE_SIZE = (700, 700)
JPEG_QUALITY = 82


def prepare_image_data(uploaded_file):
    """Resize/compress an uploaded image and return a JPEG data URI."""
    if uploaded_file is None:
        return None

    image = Image.open(uploaded_file).convert("RGB")
    image.thumbnail(MAX_IMAGE_SIZE)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _placeholder_svg():
    return """
    <svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect x="10" y="11" width="44" height="42" rx="8" fill="none" stroke="currentColor" stroke-width="3"/>
      <circle cx="25" cy="27" r="5" fill="currentColor" opacity="0.55"/>
      <path d="M15 47l12-12 8 8 5-5 9 9" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """.strip()


def image_markup(image_data, alt="Product", css_class="product-image", variant="detail"):
    """Return a consistent image or a professional neutral placeholder."""
    safe_alt = str(alt).replace('"', "&quot;")

    if image_data:
        return f'<img class="{css_class}" src="{image_data}" alt="{safe_alt}">'

    label = '<span class="placeholder-label">No photo</span>' if variant == "detail" else ""
    return (
        f'<div class="{css_class} product-placeholder product-placeholder-{variant}" aria-label="{safe_alt}">'
        f'<div class="placeholder-icon">{_placeholder_svg()}</div>{label}'
        '</div>'
    )
