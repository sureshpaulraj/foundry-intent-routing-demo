"""Render the three editable Excalidraw diagrams as animated GIF previews."""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1] / "diagrams"
FONT_PATH = next(
    (path for path in (
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ) if path.is_file()),
    None,
)
SCALE = 1.5
PADDING = 28


def font(size):
    pixels = max(10, round(size * SCALE))
    return ImageFont.truetype(str(FONT_PATH), pixels) if FONT_PATH else ImageFont.load_default(size=pixels)


def render_text(draw, element, origin):
    x = round((element["x"] + PADDING - origin[0]) * SCALE)
    y = round((element["y"] + PADDING - origin[1]) * SCALE)
    w = round(element["width"] * SCALE)
    h = round(element["height"] * SCALE)
    lines = element["text"].split("\n")
    size = element.get("fontSize", 18)
    if len(lines) == 1 and element.get("textAlign") != "center":
        face = font(size)
        words = lines[0].split()
        wrapped = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and draw.textlength(candidate, font=face) > w:
                wrapped.append(current)
                current = word
            else:
                current = candidate
        lines = wrapped + ([current] if current else [])
    while size > 9:
        face = font(size)
        heights = [draw.textbbox((0, 0), line or " ", font=face)[3] for line in lines]
        widths = [draw.textlength(line, font=face) for line in lines]
        spacing = max(4, round(size * SCALE * 0.25))
        if max(widths, default=0) <= w and sum(heights) + spacing * (len(lines) - 1) <= h:
            break
        size -= 1
    total_height = sum(heights) + spacing * (len(lines) - 1)
    align = element.get("textAlign", "left")
    vertical = element.get("verticalAlign", "top")
    cursor_y = y + (h - total_height) // 2 if vertical == "middle" else y
    for line, line_height, line_width in zip(lines, heights, widths):
        cursor_x = x + (w - line_width) / 2 if align == "center" else x
        draw.text((cursor_x, cursor_y), line, font=face, fill="#000000")
        cursor_y += line_height + spacing


def render_shape(draw, element, origin):
    x = round((element["x"] + PADDING - origin[0]) * SCALE)
    y = round((element["y"] + PADDING - origin[1]) * SCALE)
    w = round(element["width"] * SCALE)
    h = round(element["height"] * SCALE)
    fill = element.get("backgroundColor", "transparent")
    fill = None if fill == "transparent" else fill
    outline = element.get("strokeColor", "#000000")
    line_width = max(2, round(element.get("strokeWidth", 2) * SCALE))
    if element["type"] == "diamond":
        draw.polygon(
            [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)],
            fill=fill, outline=outline, width=line_width,
        )
    else:
        draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=round(12 * SCALE),
            fill=fill, outline=outline, width=line_width,
        )


def render_arrow(draw, element, origin):
    points = [
        (
            round((element["x"] + px + PADDING - origin[0]) * SCALE),
            round((element["y"] + py + PADDING - origin[1]) * SCALE),
        )
        for px, py in element["points"]
    ]
    color = element.get("strokeColor", "#000000")
    draw.line(points, fill=color, width=max(2, round(element.get("strokeWidth", 2) * SCALE)))
    if len(points) < 2:
        return
    start, end = points[-2:]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 12 * SCALE
    wing = 6 * SCALE
    draw.polygon(
        [
            end,
            (end[0] - length * math.cos(angle) + wing * math.sin(angle),
             end[1] - length * math.sin(angle) - wing * math.cos(angle)),
            (end[0] - length * math.cos(angle) - wing * math.sin(angle),
             end[1] - length * math.sin(angle) + wing * math.cos(angle)),
        ],
        fill=color,
    )


def render(diagram, frontier):
    elements = diagram["elements"]
    min_x = min(element["x"] for element in elements)
    min_y = min(element["y"] for element in elements)
    max_x = max(element["x"] + element.get("width", 0) for element in elements)
    max_y = max(element["y"] + element.get("height", 0) for element in elements)
    origin = (min_x, min_y)
    image = Image.new(
        "RGB",
        (round((max_x - min_x + 2 * PADDING) * SCALE),
         round((max_y - min_y + 2 * PADDING) * SCALE)),
        "#ffffff",
    )
    draw = ImageDraw.Draw(image)
    visible = [
        element for element in elements
        if element["id"].endswith("-title")
        or element["x"] + element.get("width", 0) <= frontier
    ]
    for element in visible:
        if element["type"] == "arrow":
            render_arrow(draw, element, origin)
    for element in visible:
        if element["type"] in ("rectangle", "diamond"):
            render_shape(draw, element, origin)
    for element in visible:
        if element["type"] == "text":
            render_text(draw, element, origin)
    return image


def main():
    for name in ("architecture", "data-flow", "components"):
        diagram = json.loads((ROOT / f"{name}.excalidraw").read_text(encoding="utf-8"))
        right = max(element["x"] + element.get("width", 0) for element in diagram["elements"])
        frontiers = [right * fraction for fraction in (0.28, 0.52, 0.76, 1.01)]
        frames = [render(diagram, frontier) for frontier in frontiers]
        output = ROOT / f"{name}.gif"
        frames[0].save(
            output, save_all=True, append_images=frames[1:],
            duration=[700, 700, 700, 4200], loop=0, optimize=True,
        )
        print(f"{output.name}: {frames[-1].width}x{frames[-1].height}")


if __name__ == "__main__":
    main()
