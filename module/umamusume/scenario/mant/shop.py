import time
import random
import cv2

from module.umamusume.asset.template import MANT_SHOP_TEMPLATES
import bot.base.log as logger

log = logger.get_logger(__name__)

SHOP_ROI_X1 = 30
SHOP_ROI_X2 = 140
SHOP_ROI_Y1 = 440
SHOP_ROI_Y2 = 920
MATCH_THRESHOLD = 0.82
POSITION_MERGE_PX = 40
MAX_SCROLL_ATTEMPTS = 20

TRACK_TOP = 479
TRACK_BOT = 938
SB_X = 696

MANT_SHOP_SCAN_START = 14
MANT_SHOP_SCAN_INTERVAL = 6


def is_shop_scan_turn(date):
    return date >= MANT_SHOP_SCAN_START and (date - MANT_SHOP_SCAN_START) % MANT_SHOP_SCAN_INTERVAL == 0


def is_thumb(r, g, b):
    return abs(r - 125) <= 5 and abs(g - 120) <= 5 and abs(b - 142) <= 5


def find_thumb(img_rgb):
    top = bot = None
    for y in range(TRACK_TOP, TRACK_BOT + 1):
        r, g, b = int(img_rgb[y, SB_X, 0]), int(img_rgb[y, SB_X, 1]), int(img_rgb[y, SB_X, 2])
        if is_thumb(r, g, b):
            if top is None:
                top = y
            bot = y
    return (top, bot) if top is not None else None


def at_top(img_rgb):
    thumb = find_thumb(img_rgb)
    if thumb is None:
        return False
    return thumb[0] <= TRACK_TOP + 10


def trigger_scrollbar(ctx):
    y = 475 + random.randint(0, 10)
    ctx.ctrl.swipe(30, y, 30, y, 100, "trigger sb")
    time.sleep(0.15)


def sb_drag(ctx, from_y, to_y):
    ctx.ctrl.swipe(SB_X, from_y, SB_X, to_y, 190, "sb drag")
    time.sleep(0.15)


def scroll_to_top(ctx):
    for _ in range(15):
        trigger_scrollbar(ctx)
        img = ctx.ctrl.get_screen()
        if img is None:
            continue
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if at_top(img_rgb):
            return
        thumb = find_thumb(img_rgb)
        if thumb is None:
            continue
        sb_drag(ctx, (thumb[0] + thumb[1]) // 2, TRACK_TOP)


def scroll_down_step(ctx, thumb_h):
    step = max(10, int(thumb_h * 0.7))
    trigger_scrollbar(ctx)
    img = ctx.ctrl.get_screen()
    if img is None:
        return
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    thumb = find_thumb(img_rgb)
    if thumb:
        cursor = (thumb[0] + thumb[1]) // 2
        target = min(TRACK_BOT - thumb_h // 2, cursor + step)
        sb_drag(ctx, cursor, target)


def content_same(before, after):
    b = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)[SHOP_ROI_Y1:SHOP_ROI_Y2, SHOP_ROI_X1:SHOP_ROI_X2]
    a = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)[SHOP_ROI_Y1:SHOP_ROI_Y2, SHOP_ROI_X1:SHOP_ROI_X2]
    diff = cv2.absdiff(b, a)
    return cv2.mean(diff)[0] < 3


def load_templates():
    loaded = {}
    for name, template in MANT_SHOP_TEMPLATES.items():
        tpl = template.template_image
        if tpl is not None:
            loaded[name] = tpl
    return loaded


def detect_items_in_frame(screen, templates):
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    roi = gray[SHOP_ROI_Y1:SHOP_ROI_Y2, SHOP_ROI_X1:SHOP_ROI_X2]
    raw_hits = []
    for name, tpl in templates.items():
        th, tw = tpl.shape[:2]
        if roi.shape[0] < th or roi.shape[1] < tw:
            continue
        result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= MATCH_THRESHOLD:
            cy = SHOP_ROI_Y1 + max_loc[1] + th // 2
            raw_hits.append((name, max_val, cy))
    raw_hits.sort(key=lambda h: -h[1])
    used_y = []
    deduped = []
    for name, score, cy in raw_hits:
        taken = any(abs(cy - uy) < POSITION_MERGE_PX for uy in used_y)
        if not taken:
            deduped.append((name, score, cy))
            used_y.append(cy)
    return deduped


def scan_mant_shop(ctx):
    templates = load_templates()
    if not templates:
        return []

    ctx.ctrl.click(412, 1125, "MANT shop open")
    time.sleep(1.5)

    scroll_to_top(ctx)

    trigger_scrollbar(ctx)
    img = ctx.ctrl.get_screen()
    if img is None:
        ctx.ctrl.click(5, 5)
        time.sleep(1)
        return []

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    thumb = find_thumb(img_rgb)
    thumb_h = (thumb[1] - thumb[0]) if thumb else 36

    all_items = {}
    prev_frame = None

    for _ in range(MAX_SCROLL_ATTEMPTS):
        frame = ctx.ctrl.get_screen()
        if frame is None:
            continue

        if prev_frame is not None and content_same(prev_frame, frame):
            break

        found = detect_items_in_frame(frame, templates)
        for name, score, cy in found:
            if name not in all_items or score > all_items[name]:
                all_items[name] = score

        prev_frame = frame
        scroll_down_step(ctx, thumb_h)

    items_list = list(all_items.keys())
    log.info("Shop items: %s", items_list)

    ctx.ctrl.click(5, 5)
    time.sleep(1)

    return items_list
