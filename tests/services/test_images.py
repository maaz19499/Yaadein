import io
from PIL import Image, ImageDraw
from src.services.images import generate_phash


def create_color_image_bytes(color: str, size: tuple[int, int]) -> bytes:
    img = Image.new("RGB", size, color=color)
    output = io.BytesIO()
    img.save(output, format="JPEG")
    return output.getvalue()


def create_pattern_image_bytes(shape: str) -> bytes:
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)
    if shape == "circle":
        draw.ellipse([200, 150, 600, 450], fill="black")
    elif shape == "line":
        draw.line([0, 0, 800, 600], fill="black", width=20)
    output = io.BytesIO()
    img.save(output, format="JPEG")
    return output.getvalue()


def test_generate_phash_similarity() -> None:
    # Generate bytes for visually identical but differently sized images
    img1_bytes = create_color_image_bytes("red", (800, 600))
    img2_bytes = create_color_image_bytes("red", (400, 300))

    phash1 = generate_phash(img1_bytes)
    phash2 = generate_phash(img2_bytes)

    # They should be identical or extremely close
    distance = sum(c1 != c2 for c1, c2 in zip(phash1, phash2))
    assert distance <= 2


def test_generate_phash_difference() -> None:
    # Generate bytes for visually distinct images (different patterns/shapes)
    img1_bytes = create_pattern_image_bytes("circle")
    img2_bytes = create_pattern_image_bytes("line")

    phash1 = generate_phash(img1_bytes)
    phash2 = generate_phash(img2_bytes)

    # They should be significantly different
    distance = sum(c1 != c2 for c1, c2 in zip(phash1, phash2))
    assert distance > 10
