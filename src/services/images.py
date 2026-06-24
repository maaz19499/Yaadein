import io
from PIL import Image
import imagehash


def resize_image_width(image_bytes: bytes, target_width: int) -> bytes:
    """
    Resizes an image to the target width while preserving the aspect ratio.
    Saves the resized image as WebP.
    """
    img: Image.Image = Image.open(io.BytesIO(image_bytes))

    # Preserve orientation metadata if present (using PIL's ExifOps equivalent or transpose)
    try:
        # Standard way to auto-rotate based on EXIF
        from PIL import ImageOps

        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    width, height = img.size

    # If image is already smaller, we can just save it or limit to original width
    if width <= target_width:
        new_width = width
        new_height = height
    else:
        aspect_ratio = height / width
        new_width = target_width
        new_height = int(target_width * aspect_ratio)

    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    # Save as WebP with a high quality compression (e.g. quality=85)
    resized_img.save(output, format="WEBP", quality=85)
    return output.getvalue()


def generate_phash(image_bytes: bytes) -> str:
    """
    Generates a 64-bit DCT perceptual hash from loaded image bytes.
    Returns the hash as a 64-character binary bitstring (consisting of '0' and '1').
    """
    img: Image.Image = Image.open(io.BytesIO(image_bytes))
    try:
        from PIL import ImageOps

        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    hash_obj = imagehash.phash(img)
    flat_hash = hash_obj.hash.flatten()
    return "".join("1" if val else "0" for val in flat_hash)
