#!/usr/bin/env python3
"""Convert a raster site-plan line drawing into a scaled DXF.

The red reference line in the image gives the scale: its real length is
passed on the command line (default 19.5 m). Black linework is skeletonised
to 1-px centre lines, traced into polylines, simplified, and written in
millimetres (1 drawing unit = 1 mm) with the origin at the image's
bottom-left corner.
"""
import argparse
import math

import cv2
import ezdxf
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize

NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def red_mask(rgb):
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    return (r > 140) & (r - g > 70) & (r - b > 70)


def measure_red_line(mask):
    """Return the red stroke's centre-line endpoints (px) and its length."""
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(float)
    c = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    d = vt[0]
    t = (pts - c) @ d
    extent = t.max() - t.min()
    width = len(pts) / extent  # stroke area / extent = mean stroke width
    # Round caps add half a stroke width at each end.
    half = width / 2
    p1 = c + d * (t.min() + half)
    p2 = c + d * (t.max() - half)
    return p1, p2, extent - width


def trace_skeleton(skel):
    """Split a 1-px skeleton into pixel paths between junctions/endpoints."""
    h, w = skel.shape
    padded = np.zeros((h + 2, w + 2), np.uint8)
    padded[1:-1, 1:-1] = skel
    k = np.ones((3, 3), np.uint8)
    deg = cv2.filter2D(padded, -1, k, borderType=cv2.BORDER_CONSTANT) - padded
    deg = deg * padded
    on = padded.astype(bool)
    node = on & (deg != 2)

    visited_edges = set()
    paths = []

    def walk(start, nxt):
        path = [start, nxt]
        prev, cur = start, nxt
        while not node[cur] and cur != start:
            moved = False
            for dy, dx in NEIGHBOURS:
                cand = (cur[0] + dy, cur[1] + dx)
                if cand != prev and on[cand]:
                    key = (min(cur, cand), max(cur, cand))
                    if key in visited_edges:
                        continue
                    visited_edges.add(key)
                    prev, cur = cur, cand
                    path.append(cur)
                    moved = True
                    break
            if not moved:
                break
        return path

    def start_from(p):
        for dy, dx in NEIGHBOURS:
            q = (p[0] + dy, p[1] + dx)
            if on[q]:
                key = (min(p, q), max(p, q))
                if key not in visited_edges:
                    visited_edges.add(key)
                    paths.append(walk(p, q))

    for p in zip(*np.nonzero(node)):
        start_from(p)
    # Remaining pixels belong to closed loops with no junction.
    for p in zip(*np.nonzero(on & ~node)):
        start_from(p)
    # Back to unpadded (x, y) coordinates.
    return [np.array([(c - 1, r - 1) for r, c in path], float) for path in paths]


def path_length(p):
    return float(np.sum(np.hypot(*np.diff(p, axis=0).T))) if len(p) > 1 else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image")
    ap.add_argument("out_dxf")
    ap.add_argument("--red-length-m", type=float, default=19.5)
    ap.add_argument("--upscale", type=int, default=3)
    ap.add_argument("--threshold", type=int, default=205)
    ap.add_argument("--tolerance", type=float, default=0.35,
                    help="simplification tolerance in original pixels")
    ap.add_argument("--min-length", type=float, default=1.5,
                    help="drop isolated strokes shorter than this (original px)")
    ap.add_argument("--geom", help="also write plain-text geometry for geom2dwg")
    args = ap.parse_args()

    rgb = np.array(Image.open(args.image).convert("RGB"))
    H, W = rgb.shape[:2]
    red = red_mask(rgb)
    p1, p2, red_px = measure_red_line(red)
    mm_per_px = args.red_length_m * 1000.0 / red_px
    print(f"image {W}x{H}px, red line {red_px:.1f}px -> {mm_per_px:.2f} mm/px, "
          f"sheet {W * mm_per_px / 1000:.1f} x {H * mm_per_px / 1000:.1f} m")

    # Black linework, with the red stroke painted out.
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    red_d = cv2.dilate(red.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    gray[red_d] = 255
    s = args.upscale
    big = cv2.resize(gray, (W * s, H * s), interpolation=cv2.INTER_CUBIC)
    ink = (big < args.threshold).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    skel = skeletonize(ink.astype(bool)).astype(np.uint8)
    paths = trace_skeleton(skel)

    def to_mm(pts_px):
        return [(x * mm_per_px, (H - y) * mm_per_px) for x, y in pts_px]

    layers = [("LINEWORK", 7), ("RED_LINE", 1), ("ANNOTATION", 3)]
    polylines = []  # (layer, points, closed)
    tol = args.tolerance * s
    for p in paths:
        if path_length(p) < args.min_length * s:
            continue
        closed = len(p) > 3 and np.hypot(*(p[0] - p[-1])) < 1.5
        simp = cv2.approxPolyDP(p.astype(np.float32).reshape(-1, 1, 2), tol, closed)
        simp = simp.reshape(-1, 2) / s
        if len(simp) < 2:
            continue
        polylines.append(("LINEWORK", to_mm(simp), closed and len(simp) > 2))

    # Sheet border matching the source image extent.
    Wm, Hm = W * mm_per_px, H * mm_per_px
    polylines.append(("ANNOTATION", [(0, 0), (Wm, 0), (Wm, Hm), (0, Hm)], True))

    a, b = to_mm([p1, p2])
    length_mm = math.dist(a, b)
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    if ang > 90:
        ang -= 180
    elif ang < -90:
        ang += 180
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    off = 1500  # text sits 1.5 m below/right of the red line
    nx, ny = -math.sin(math.radians(ang)), math.cos(math.radians(ang))
    text = (f"{length_mm / 1000:.1f}m", (mid[0] - nx * off, mid[1] - ny * off), 700.0, ang)

    doc = ezdxf.new("R2000")
    doc.header["$INSUNITS"] = 4  # millimetres
    doc.header["$MEASUREMENT"] = 1
    for name, color in layers:
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for layer, pts, closed in polylines:
        msp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": layer})
    msp.add_line(a, b, dxfattribs={"layer": "RED_LINE"})
    msp.add_text(text[0], height=text[2], rotation=text[3],
                 dxfattribs={"layer": "ANNOTATION"}).set_placement(
        text[1], align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    doc.saveas(args.out_dxf)

    if args.geom:
        # Plain-text geometry for tools/geom2dwg.c (LibreDWG writer).
        with open(args.geom, "w") as f:
            f.write(f"E 0 0 {Wm:.3f} {Hm:.3f}\n")
            for name, color in layers:
                f.write(f"L {name} {color}\n")
            for layer, pts, closed in polylines:
                coords = " ".join(f"{x:.3f} {y:.3f}" for x, y in pts)
                f.write(f"P {layer} {int(closed)} {len(pts)} {coords}\n")
            f.write(f"N RED_LINE {a[0]:.3f} {a[1]:.3f} {b[0]:.3f} {b[1]:.3f}\n")
            f.write(f"T ANNOTATION {text[1][0]:.3f} {text[1][1]:.3f} {text[2]} {text[3]:.6f} {text[0]}\n")

    print(f"{len(polylines) - 1} polylines written to {args.out_dxf}; red line {length_mm:.0f} mm")


if __name__ == "__main__":
    main()
