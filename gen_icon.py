"""
Stained glass icon — vitralis v12 (high contrast, taskbar-first).

Design principle: background is near-black so only the V reads at 32px.
Left arm = bright sapphire blue, right arm = bright amber gold.
3 cells per arm max — large enough to see the lead lines as texture,
not noise.
"""

import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

SIZE = 512
random.seed(7)
rng  = np.random.default_rng(7)

# V fills ~80% of icon width, tip at very bottom
V_TIP = (256, 500)
LO = (30,  0);  LI = (210, 0)
RI = (302, 0);  RO = (482, 0)

def lerp(a, b, t):
    return (a[0]*(1-t)+b[0]*t, a[1]*(1-t)+b[1]*t)

left_mask  = np.zeros((SIZE, SIZE), bool)
right_mask = np.zeros((SIZE, SIZE), bool)
gap_mask   = np.zeros((SIZE, SIZE), bool)

for y in range(SIZE):
    t  = min(y / V_TIP[1], 1.0)
    lo = lerp(LO, V_TIP, t)[0]
    li = lerp(LI, V_TIP, t)[0]
    ri = lerp(RI, V_TIP, t)[0]
    ro = lerp(RO, V_TIP, t)[0]
    for x in range(SIZE):
        if y <= V_TIP[1]:
            if lo <= x <= li:   left_mask[y, x]  = True
            elif ri <= x <= ro: right_mask[y, x] = True
            elif li < x < ri:   gap_mask[y, x]   = True

bg_mask = ~(left_mask | right_mask | gap_mask)

def poisson(n, mask, min_d, tries=60000):
    pts = []
    ys, xs = np.where(mask)
    if len(ys) == 0: return pts
    for _ in range(tries):
        if len(pts) >= n: break
        idx = rng.integers(0, len(ys))
        p   = (float(xs[idx]), float(ys[idx]))
        if any(math.hypot(p[0]-q[0], p[1]-q[1]) < min_d for q in pts):
            continue
        pts.append(p)
    return pts

s_left  = poisson(6, left_mask,  min_d=80)
s_right = poisson(6, right_mask, min_d=80)
s_gap   = poisson(1, gap_mask,   min_d=200)
s_bg    = poisson(10, bg_mask,   min_d=80)

all_seeds = s_left + s_right + s_gap + s_bg
zones     = ([0]*len(s_left) + [1]*len(s_right) +
             [2]*len(s_gap)  + [3]*len(s_bg))

real_pts = np.array(all_seeds, dtype=np.float32)
zone_masks_list  = [left_mask, right_mask, gap_mask, bg_mask]
zone_seed_groups = {z: [] for z in range(4)}
zone_seed_idxs   = {z: [] for z in range(4)}
for i, z in enumerate(zones):
    zone_seed_groups[z].append(real_pts[i])
    zone_seed_idxs[z].append(i)

cell_map = np.full((SIZE, SIZE), -1, dtype=np.int32)
cc = 0
for z in range(4):
    zmask = zone_masks_list[z]
    if not np.any(zmask) or not zone_seed_groups[z]: continue
    zs     = np.array(zone_seed_groups[z], dtype=np.float32)
    yy, xx = np.where(zmask)
    dx = xx[:, None].astype(np.float32) - zs[:, 0]
    dy = yy[:, None].astype(np.float32) - zs[:, 1]
    nn = np.argmin(dx*dx + dy*dy, axis=1)
    for li, si in enumerate(zone_seed_idxs[z]):
        cell_map[yy[nn == li], xx[nn == li]] = cc + li
    cc += len(zone_seed_groups[z])

n_cells = int(cell_map.max()) + 1

def hsv_to_rgb(h, s, v):
    h = h % 360; c = v*s; x = c*(1 - abs(h/60 % 2 - 1)); m = v - c
    if   h <  60: r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return ((r+m)*255, (g+m)*255, (b+m)*255)

def jit(v, a): return v + random.uniform(-a, a)

cell_props = {}
cc = 0
for z in range(4):
    for li, si in enumerate(zone_seed_idxs[z]):
        cid = cc + li
        ang = random.uniform(0, math.pi)
        if z == 0:   # left — bright sapphire, hue varies per pane
            h  = jit(213, 22); s = jit(0.88, 0.06)
            vc = jit(0.94, 0.05); ve = jit(0.55, 0.08)
        elif z == 1: # right — bright amber, hue varies per pane
            h  = jit(38, 16);  s = jit(0.92, 0.05)
            vc = jit(0.95, 0.04); ve = jit(0.58, 0.08)
        elif z == 2: # gap — near-black blue-grey
            h  = 210; s = 0.20
            vc = 0.12; ve = 0.06
        else:        # background — dark jewel tones, visible but not competing
            h  = jit(270, 40); s = jit(0.70, 0.12)
            vc = jit(0.28, 0.06); ve = jit(0.12, 0.04)
        cell_props[cid] = (h, s, vc, ve, ang)
    cc += len(zone_seed_idxs[z])

result_f = np.zeros((SIZE, SIZE, 3), np.float32)
for cid in range(n_cells):
    if cid not in cell_props: continue
    h, s, vc, ve, ang = cell_props[cid]
    mask = cell_map == cid
    if not np.any(mask): continue
    yy, xx = np.where(mask)
    cx = xx.mean(); cy = yy.mean()
    dx = (xx - cx).astype(np.float32)
    dy = (yy - cy).astype(np.float32)
    proj  = dx * math.cos(ang) + dy * math.sin(ang)
    pmax  = max(abs(proj).max(), 1.0)
    t     = np.abs(proj / pmax)
    perp  = -dx * math.sin(ang) + dy * math.cos(ang)
    stria = np.sin(perp * 0.09) * 0.04
    v_pix = np.clip(vc * (1 - t**1.2) + ve * t**1.2 + stria, 0.0, 1.0)
    for i in range(len(yy)):
        r, g, b = hsv_to_rgb(h, s, float(v_pix[i]))
        result_f[yy[i], xx[i]] = [r/255, g/255, b/255]

bnd = ((cell_map != np.roll(cell_map, -1, 0)) |
       (cell_map != np.roll(cell_map,  1, 0)) |
       (cell_map != np.roll(cell_map, -1, 1)) |
       (cell_map != np.roll(cell_map,  1, 1)))
lead_dil  = Image.fromarray(bnd.astype(np.uint8)*255).filter(ImageFilter.MaxFilter(11))
lead_mask = np.array(lead_dil) > 128
result    = (np.clip(result_f, 0, 1) * 255).astype(np.uint8)
result[lead_mask] = [10, 9, 8]

img = Image.fromarray(result).convert('RGBA')
img = ImageEnhance.Color(img).enhance(1.25)
img = ImageEnhance.Contrast(img).enhance(1.10)

RAD = 80
mi  = Image.new('L', (SIZE, SIZE), 0)
ImageDraw.Draw(mi).rounded_rectangle([0, 0, SIZE-1, SIZE-1], radius=RAD, fill=255)
mi  = mi.filter(ImageFilter.GaussianBlur(0.5))
bg  = Image.new('RGB', (SIZE, SIZE), (5, 6, 8))
out = Image.composite(img.convert('RGB'), bg, mi)

frame = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
fd    = ImageDraw.Draw(frame)
fd.rounded_rectangle([0, 0, SIZE-1, SIZE-1], radius=RAD,
                     outline=(4, 4, 6, 255), width=14)
out = Image.alpha_composite(out.convert('RGBA'), frame).convert('RGB')

out.save('media/icon.png')
print("Done.")
