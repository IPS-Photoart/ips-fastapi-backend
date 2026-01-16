import os
from PIL import Image, ImageDraw, ImageFont
import qrcode


CERT_DIR = "cert_previews"
os.makedirs(CERT_DIR, exist_ok=True)


def vertical_gradient(width, height, top_color, bottom_color):
    base = Image.new("RGB", (width, height), top_color)
    top = Image.new("RGB", (width, height), bottom_color)
    mask = Image.new("L", (width, height))
    for y in range(height):
        mask.putpixel((0, y), int(255 * (y / height)))
    mask = mask.resize((width, height))
    return Image.composite(top, base, mask)


def add_preview_watermark(img, text="PREVIEW – PAYMENT REQUIRED"):
    img = img.convert("RGBA")
    width, height = img.size

    text_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(text_layer)

    try:
        font = ImageFont.truetype("arialbd.ttf", 64)
    except:
        font = ImageFont.load_default()

    for y in range(0, height, 450):
        for x in range(-width, width, 700):
            draw.text((x, y), text, font=font, fill=(150, 150, 150, 70))

    text_layer = text_layer.rotate(-30, expand=1)
    watermark = Image.alpha_composite(
        Image.new("RGBA", img.size, (255, 255, 255, 0)),
        text_layer.crop((0, 0, width, height))
    )

    return Image.alpha_composite(img, watermark).convert("RGB")


def generate_certificate_png(
    cert_code: str,
    user_name: str,
    grade: str,
    percentage: float,
    verify_url: str
):
    WIDTH, HEIGHT = 1650, 1150

    img = vertical_gradient(
        WIDTH,
        HEIGHT,
        (250, 244, 236),
        (232, 220, 205)
    )

    draw = ImageDraw.Draw(img)

    # Banner
    banner = Image.open("banner.jpg")
    banner = banner.resize(
        (WIDTH, int(WIDTH * banner.height / banner.width))
    )
    img.paste(banner, (0, 0))

    y_cursor = banner.height + 40

    # Logo
    logo = Image.open("logo.jpg").resize((180, 180))
    img.paste(logo, (100, y_cursor))

    try:
        title_font = ImageFont.truetype("arialbd.ttf", 48)
        body_font = ImageFont.truetype("arial.ttf", 30)
        small_font = ImageFont.truetype("arial.ttf", 22)
    except:
        title_font = body_font = small_font = ImageFont.load_default()

    draw.text(
        (WIDTH // 2, y_cursor + 20),
        "Indian Photographic Society",
        font=title_font,
        fill=(80, 50, 30),
        anchor="mm",
    )

    draw.text(
        (WIDTH // 2, y_cursor + 80),
        "Professional Photography Certification",
        font=body_font,
        fill=(110, 80, 55),
        anchor="mm",
    )

    body_y = y_cursor + 170

    draw.text((350, body_y), "This is to certify that", font=body_font, fill=(60, 40, 20))
    draw.text((350, body_y + 45), user_name, font=title_font, fill=(40, 25, 15))

    draw.text(
        (350, body_y + 120),
        "has successfully completed the prescribed course and assessment.",
        font=body_font,
        fill=(60, 40, 20),
    )

    draw.text(
        (350, body_y + 190),
        f"Grade: {grade}     Score: {percentage}%",
        font=body_font,
        fill=(60, 40, 20),
    )

    draw.text(
        (350, body_y + 250),
        f"Certificate Code: {cert_code}",
        font=small_font,
        fill=(90, 60, 40),
    )

    qr = qrcode.make(verify_url).resize((220, 220))
    img.paste(qr, (WIDTH - 360, HEIGHT - 360))

    draw.rectangle(
        (20, 20, WIDTH - 20, HEIGHT - 20),
        outline=(160, 120, 90),
        width=4,
    )

    path = os.path.join(CERT_DIR, f"{cert_code}.png")
    img.save(path)
    return path
