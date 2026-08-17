"""
generate_assets.py — WinExhale branding generator.

Draws a modern minimalist shield + sparkle logo in cyan / deep-blue tones on a
transparent background, then exports:

  - app_logo.png   (1024x1024, RGBA)
  - app_icon.ico   (multi-resolution: 16 -> 256 px)

Requirements:  pip install pillow
Usage:         python generate_assets.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024                 # final export size (px)
SS = 2                      # supersampling: draw at SIZE*SS, downscale for smooth edges
CANVAS = SIZE * SS

CYAN_LIGHT = (34, 211, 238, 255)     # #22D3EE
BLUE_DEEP = (23, 37, 84, 255)        # #172554
EDGE = (125, 231, 255, 255)          # #7DE7FF
WHITE = (245, 253, 255, 255)         # #F5FDFF
GLOW = (34, 211, 238, 200)

RESAMPLE = getattr(Image, "Resampling", Image)
HERE = os.path.dirname(os.path.abspath(__file__))


def quad(p0, p1, p2, steps=48):
    """Sample points along a quadratic bezier curve."""
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        pts.append((
            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
        ))
    return pts


def shield_points(cx, cy, w, h, scale=1.0):
    """Outline of a rounded-top shield tapering to a point at the bottom."""
    w, h = w * scale, h * scale
    r = w * 0.09
    top, bot = cy - h / 2, cy + h / 2
    left, right = cx - w / 2, cx + w / 2
    side_y = top + h * 0.55

    pts = [(left + r, top)]
    for i in range(25):                                    # top-left corner arc
        a = math.radians(90 + i * 90 / 24)
        pts.append((left + r + r * math.cos(a), top + r - r * math.sin(a)))
    pts.append((left, side_y))                             # straight left side
    pts += quad((left, side_y), (left, bot - h * 0.10), (cx, bot))
    pts += quad((cx, bot), (right, bot - h * 0.10), (right, side_y))
    pts.append((right, top + r))
    for i in range(25):                                    # top-right corner arc
        a = math.radians(180 - i * 90 / 24)
        pts.append((right - r + r * math.cos(a), top + r - r * math.sin(a)))
    return pts


def star_points(cx, cy, radius, inner, tips=4, rotation=0.0):
    """Four-point 'sparkle' star (concave diamond)."""
    pts = []
    for k in range(tips * 2):
        a = math.radians(rotation + k * 180.0 / tips)
        rad = radius if k % 2 == 0 else radius * inner
        pts.append((cx + rad * math.sin(a), cy - rad * math.cos(a)))
    return pts


def build():
    cx = cy = CANVAS / 2
    w, h = CANVAS * 0.56, CANVAS * 0.62
    pts = shield_points(cx, cy, w, h)
    glow_pts = shield_points(cx, cy, w, h, scale=1.055)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))

    # Soft cyan halo behind the shield
    glow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(glow_pts, fill=GLOW)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=48))
    canvas = Image.alpha_composite(canvas, glow)

    # Vertical cyan -> deep-blue gradient clipped to the shield silhouette
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    grad = Image.new("RGBA", (CANVAS, CANVAS))
    gdraw = ImageDraw.Draw(grad)
    for y in range(CANVAS):
        t = (y / (CANVAS - 1)) ** 1.15
        row = tuple(int(CYAN_LIGHT[i] + (BLUE_DEEP[i] - CYAN_LIGHT[i]) * t) for i in range(3)) + (255,)
        gdraw.line([(0, y), (CANVAS, y)], fill=row)
    body = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    body.paste(grad, (0, 0), mask)
    canvas = Image.alpha_composite(canvas, body)

    # Crisp bright edge around the shield
    edge = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    ImageDraw.Draw(edge).line(pts + [pts[0]], fill=EDGE, width=6 * SS, joint="curve")
    canvas = Image.alpha_composite(canvas, edge)

    # Sparkles with a subtle bloom
    def sparkle(shape, blur):
        layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        ImageDraw.Draw(layer).polygon(shape, fill=WHITE)
        halo = layer.filter(ImageFilter.GaussianBlur(radius=blur))
        return Image.alpha_composite(halo, layer)

    main_star = star_points(cx + w * 0.14, cy - h * 0.14, w * 0.20, 0.34)
    mini_star = star_points(cx - w * 0.24, cy + h * 0.06, w * 0.085, 0.34, rotation=18)
    canvas = Image.alpha_composite(canvas, sparkle(main_star, 5 * SS))
    canvas = Image.alpha_composite(canvas, sparkle(mini_star, 3 * SS))

    img = canvas.resize((SIZE, SIZE), RESAMPLE.LANCZOS)

    png_path = os.path.join(HERE, "app_logo.png")
    ico_path = os.path.join(HERE, "app_icon.ico")
    img.save(png_path)
    img.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                              (64, 64), (128, 128), (256, 256)])
    print(f"[+] wrote {png_path}")
    print(f"[+] wrote {ico_path}")


if __name__ == "__main__":
    build()
