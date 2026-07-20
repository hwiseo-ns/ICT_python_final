"""
card_tools.py — helper functions for the "Design Your Own Name Card" mini project.
Python Bootcamp Day 4 (Functions).

You do NOT need to understand everything inside this file today.
What matters is that you can CALL these functions with the right arguments —
exactly like you call math.sqrt() without reading its source code.

Requires the Pillow library:   pip install pillow
All images must be inside the  assets/  folder next to this file.

QUICK REFERENCE
---------------
  create_card(width, height, color)          -> new blank card
  add_image(card, filename, x, y, ...)       -> paste an asset image
  tile_image(card, filename, y, ...)         -> repeat an image as a band
  add_text(card, text, x, y, ...)            -> draw text (KR/EN/UZ/RU ok)
  add_rectangle / add_circle / add_line      -> basic shapes
  add_border(card, ...)                      -> frame around the card
  list_assets()                              -> print every usable image
  save_card(card, filename)                  -> write the PNG file
  show_card(card)                            -> open it in an image viewer
"""

import os
from PIL import Image, ImageColor, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Fonts that support English / Cyrillic / Korean, tried in order.
_FONT_CANDIDATES = [
    "malgun.ttf", "malgunbd.ttf",                            # Windows
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",   # Linux
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",   # Colab (after apt)
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "arialbd.ttf", "arial.ttf",
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",            # macOS
]

# Where a downloaded fallback font is cached (next to this file).
_FONT_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_FALLBACK_FONT_URL = ("https://raw.githubusercontent.com/google/fonts/"
                      "main/ofl/nanumgothic/NanumGothic-Bold.ttf")
_FALLBACK_FONT_PATH = os.path.join(_FONT_CACHE_DIR, "NanumGothic-Bold.ttf")

# Pillow renamed its resampling constants in newer versions; support both.
_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
_BICUBIC = getattr(getattr(Image, "Resampling", Image), "BICUBIC")


# ---------------------------------------------------------------------------
# Internal helpers  (you can ignore these)
# ---------------------------------------------------------------------------

def _renders_hangul(path):
    """True if the font file really draws Korean (not empty, not tofu boxes).

    Trick: a font that lacks Hangul draws the SAME placeholder box for every
    Korean character — so if '한' and '글' come out identical, it's fake.
    """
    try:
        font = ImageFont.truetype(path, 24)
    except OSError:
        return False

    def bitmap(ch):
        img = Image.new("L", (40, 40), 0)
        ImageDraw.Draw(img).text((2, 2), ch, font=font, fill=255)
        return img.tobytes()

    a, b = bitmap("한"), bitmap("글")
    return a != b and any(a)


def _download_fallback_font():
    """Download NanumGothic once (≈2 MB) so Korean works anywhere, e.g. Colab."""
    if os.path.exists(_FALLBACK_FONT_PATH):
        return _FALLBACK_FONT_PATH
    try:
        import urllib.request
        os.makedirs(_FONT_CACHE_DIR, exist_ok=True)
        print("card_tools: downloading a Korean font (NanumGothic, one time)...")
        urllib.request.urlretrieve(_FALLBACK_FONT_URL, _FALLBACK_FONT_PATH)
        return _FALLBACK_FONT_PATH
    except Exception:
        return None


_FONT_PATH = None          # resolved once, then reused


def _resolve_font_path():
    """Pick the best available font: Korean-capable > any usable > download."""
    global _FONT_PATH
    if _FONT_PATH is not None:
        return _FONT_PATH
    usable = []
    for path in _FONT_CANDIDATES + [_FALLBACK_FONT_PATH]:
        try:
            ImageFont.truetype(path, 12)
        except OSError:
            continue
        if _renders_hangul(path):
            _FONT_PATH = path
            return path
        usable.append(path)
    # nothing on this machine draws Korean -> fetch one (Colab case)
    downloaded = _download_fallback_font()
    if downloaded and _renders_hangul(downloaded):
        _FONT_PATH = downloaded
        return downloaded
    if usable:
        print("card_tools: WARNING — no Korean-capable font found; "
              "한글 may appear as boxes. Try use_font(<path to a .ttf>).")
        _FONT_PATH = usable[0]
        return _FONT_PATH
    _FONT_PATH = ""        # sentinel: use Pillow's built-in default
    return _FONT_PATH


_FONT_CACHE = {}           # size -> loaded font object


def _load_font(size):
    """Load the resolved font at a given size (cached for speed)."""
    if size not in _FONT_CACHE:
        path = _resolve_font_path()
        try:
            _FONT_CACHE[size] = (ImageFont.truetype(path, size) if path
                                 else ImageFont.load_default())
        except OSError:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def use_font(path):
    """Manually choose a .ttf/.ttc font file for ALL text on your cards.

    Example (e.g. in Colab after uploading your own font):
        card_tools.use_font("/content/MyFont.ttf")
    """
    ImageFont.truetype(path, 12)          # fail fast if the file is bad
    global _FONT_PATH
    _FONT_PATH = path
    _FONT_CACHE.clear()
    print(f"card_tools: now using font {path}")


def _rgba(color, opacity):
    """Turn any color ("red", "#C92C3A", (r, g, b)) + opacity into an RGBA tuple."""
    if isinstance(color, str):
        color = ImageColor.getrgb(color)
    return color[:3] + (int(255 * opacity),)


def _fade(img, opacity):
    """Multiply an image's alpha channel by `opacity` (no-op when opacity >= 1)."""
    if opacity < 1.0:
        alpha = img.getchannel("A").point(lambda a: int(a * opacity))
        img.putalpha(alpha)
    return img


def _stamp(card, draw_fn):
    """Draw onto a fresh transparent layer the size of the card, then composite.

    Drawing on a separate layer keeps semi-transparent colors blending
    correctly instead of overwriting what is already on the card.
    """
    layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    card.alpha_composite(layer)
    return card


def _open_asset(filename):
    """Open an image from assets/ with a friendly error if it doesn't exist."""
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f'"{filename}" is not in the assets folder. '
            f"Run  python card_tools.py  to see every available file name."
        )
    return Image.open(path).convert("RGBA")


# ---------------------------------------------------------------------------
# Creating a card
# ---------------------------------------------------------------------------

def create_card(width=1000, height=600, color="white"):
    """Create and return a new blank card.

    Example:
        card = create_card(1000, 600, color="#F5EEDF")
    """
    return Image.new("RGBA", (width, height), color)


# ---------------------------------------------------------------------------
# Placing images
# ---------------------------------------------------------------------------

def add_image(card, filename, x=0, y=0, width=None, height=None, scale=None,
              rotation=0, opacity=1.0, flip=False, anchor="topleft"):
    """Paste an image from the assets folder onto the card.

    Parameters
    ----------
    card      : the card returned by create_card()
    filename  : name of a file inside assets/, e.g. "taegeuk.png"
    x, y      : position on the card, in pixels
    anchor    : what (x, y) means — "topleft" (default) or "center"
    width     : resize to this width (height auto-scales if not given)
    height    : resize to this height
    scale     : alternative to width/height — e.g. scale=0.5 for half size
    rotation  : degrees counter-clockwise, e.g. 15 or -30
    opacity   : 0.0 (invisible) to 1.0 (fully visible)
    flip      : True to mirror the image left<->right

    Examples:
        add_image(card, "taegeuk.png", x=700, y=60, width=220,
                  rotation=15, opacity=0.9)
        add_image(card, "moon.png", x=500, y=300, scale=0.8, anchor="center")
    """
    img = _open_asset(filename)

    # 1) resize
    if scale is not None:
        width = int(img.size[0] * scale)
        height = int(img.size[1] * scale)
    if width is not None or height is not None:
        w0, h0 = img.size
        if width is not None and height is None:
            height = int(h0 * width / w0)
        elif height is not None and width is None:
            width = int(w0 * height / h0)
        img = img.resize((int(width), int(height)), _LANCZOS)

    # 2) mirror / rotate / fade
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if rotation:
        img = img.rotate(rotation, expand=True, resample=_BICUBIC)
    img = _fade(img, opacity)

    # 3) place
    if anchor == "center":
        x = x - img.size[0] // 2
        y = y - img.size[1] // 2
    card.alpha_composite(img, (int(x), int(y)))
    return card


def tile_image(card, filename, y=0, tile_width=100, spacing=0, rotation=0,
               opacity=1.0):
    """Repeat one image left-to-right across the whole card — instant pattern band!

    Parameters
    ----------
    y          : vertical position of the band (top edge of each tile)
    tile_width : width of each repeated copy
    spacing    : extra pixels between copies (0 = touching)
    rotation, opacity : same as add_image

    Example:
        tile_image(card, "plum.png", y=20, tile_width=90, spacing=30, opacity=0.35)
    """
    step = tile_width + spacing
    for x in range(0, card.size[0], step):
        add_image(card, filename, x=x, y=y, width=tile_width,
                  rotation=rotation, opacity=opacity)
    return card


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def add_text(card, text, x=0, y=0, size=40, color="black", align="left",
             rotation=0, opacity=1.0, outline_color=None, outline_width=2,
             letter_spacing=0):
    """Draw text on the card.

    Parameters
    ----------
    text           : the string to draw (English, O'zbek, Русский, 한국어 all work)
    x, y           : position of the text's top-left (or top-center if align="center")
    size           : font size in pixels
    color          : e.g. "black", "white", "#C92C3A"
    align          : "left" or "center" — "center" centers the text on x
    rotation       : degrees counter-clockwise (great for stamps and labels)
    opacity        : 0.0 to 1.0 (e.g. faint watermark text)
    outline_color  : draw an outline around each letter, e.g. "white"
    outline_width  : thickness of that outline in pixels
    letter_spacing : extra pixels between letters (0 = normal)

    Examples:
        add_text(card, "Aziz Karimov", x=80, y=250, size=64, color="#221E1C")
        add_text(card, "HELLO", x=500, y=60, size=48, color="white",
                 align="center", rotation=10, outline_color="#C92C3A")
    """
    font = _load_font(size)
    pad = 2 * outline_width + 4          # breathing room for the outline
    scratch = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    # 1) measure the text
    if letter_spacing > 0:
        text_w = sum(int(scratch.textlength(ch, font=font)) + letter_spacing
                     for ch in text) - letter_spacing
    else:
        bbox = scratch.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
    text_h = size * 2                    # generous room for ascenders/descenders

    # 2) draw it on its own transparent layer
    layer = Image.new("RGBA", (text_w + 2 * pad, text_h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    stroke = (dict(stroke_width=outline_width, stroke_fill=outline_color)
              if outline_color else {})
    if letter_spacing > 0:
        cx = pad
        for ch in text:
            d.text((cx, pad), ch, font=font, fill=color, **stroke)
            cx += int(scratch.textlength(ch, font=font)) + letter_spacing
    else:
        d.text((pad, pad), text, font=font, fill=color, **stroke)

    # 3) fade / rotate / place
    layer = _fade(layer, opacity)
    if rotation:
        layer = layer.rotate(rotation, expand=True, resample=_BICUBIC)
    px = x - layer.size[0] // 2 if align == "center" else x - pad
    py = y - pad
    card.alpha_composite(layer, (int(px), int(py)))
    return card


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def add_rectangle(card, x, y, width, height, color, opacity=1.0,
                  corner_radius=0, outline_color=None, outline_width=3,
                  rotation=0):
    """Draw a filled rectangle (color band, text backdrop, frame...).

    Parameters
    ----------
    corner_radius : rounded corners, in pixels (0 = sharp corners)
    outline_color : optional border color
    outline_width : border thickness
    rotation      : degrees counter-clockwise

    Example:
        add_rectangle(card, 0, 470, 1000, 130, color="#265094", opacity=0.85)
        add_rectangle(card, 60, 210, 500, 170, color="white", opacity=0.6,
                      corner_radius=20, outline_color="#C92C3A")
    """
    fill = _rgba(color, opacity)
    outline = (dict(outline=outline_color, width=outline_width)
               if outline_color else {})
    layer = Image.new("RGBA", (int(width) + 2, int(height) + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if corner_radius > 0:
        d.rounded_rectangle([0, 0, width, height], radius=corner_radius,
                            fill=fill, **outline)
    else:
        d.rectangle([0, 0, width, height], fill=fill, **outline)
    if rotation:
        layer = layer.rotate(rotation, expand=True, resample=_BICUBIC)
    card.alpha_composite(layer, (int(x), int(y)))
    return card


def add_circle(card, x, y, radius, color, opacity=1.0,
               outline_color=None, outline_width=3):
    """Draw a filled circle centered at (x, y).

    Note: `opacity` fades only the fill — the outline stays solid, which is
    handy for drawing rings (opacity=0.0 + an outline_color).

    Example:
        add_circle(card, 850, 120, 90, color="#F3C342", opacity=0.9)
    """
    fill = _rgba(color, opacity)
    outline = (dict(outline=outline_color, width=outline_width)
               if outline_color else {})

    def draw(d):
        d.ellipse([x - radius, y - radius, x + radius, y + radius],
                  fill=fill, **outline)

    return _stamp(card, draw)


def add_line(card, x1, y1, x2, y2, color="black", thickness=4, opacity=1.0):
    """Draw a straight line from (x1, y1) to (x2, y2).

    Example:
        add_line(card, 70, 320, 560, 320, color="#C92C3A", thickness=5)
    """
    fill = _rgba(color, opacity)
    return _stamp(card, lambda d: d.line([x1, y1, x2, y2],
                                         fill=fill, width=thickness))


def add_border(card, color="#221E1C", thickness=8, margin=20, opacity=1.0):
    """Draw a rectangular frame around the whole card.

    Parameters
    ----------
    thickness : line width of the frame
    margin    : distance from the card edge

    Example:
        add_border(card, color="#C92C3A", thickness=6, margin=24)
    """
    fill = _rgba(color, opacity)
    w, h = card.size
    return _stamp(card, lambda d: d.rectangle(
        [margin, margin, w - margin, h - margin],
        outline=fill, width=thickness))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def list_assets():
    """Print every image file available in the assets folder."""
    names = sorted(os.listdir(ASSETS_DIR))
    count = 0
    for name in names:
        try:
            with Image.open(os.path.join(ASSETS_DIR, name)) as img:
                print(f"{name:32s} {img.size[0]} x {img.size[1]} px")
                count += 1
        except OSError:
            continue                      # skip anything that isn't an image
    print(f"-- {count} images (see ASSETS_GUIDE.txt for themes & recipes) --")


def save_card(card, filename="my_card.png"):
    """Save the finished card as a PNG file and print a confirmation."""
    card.convert("RGB").save(filename)
    print(f"Saved: {filename}")


def show_card(card):
    """Open the card in your computer's image viewer."""
    card.show()


if __name__ == "__main__":
    # Running this file directly shows the available assets — a Day 4 idea in action!
    print("Available design assets:")
    list_assets()