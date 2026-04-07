import time
import cv2
import threading
import re

import bot.base.log as logger
from bot.recog.ocr import ocr_line
from bot.recog.image_matcher import image_match
from module.umamusume.context import UmamusumeContext, log_detected_skill
from module.umamusume.asset.template import (
    Template, UMAMUSUME_REF_TEMPLATE_PATH, REF_HINT_LEVELS_TEXT,
    UI_CULTIVATE_EVENT_UMAMUSUME,
    UI_CULTIVATE_EVENT_SUPPORT_CARD,
    UI_CULTIVATE_EVENT_SCENARIO,
)
from module.umamusume.script.cultivate_task.event.manifest import get_event_choice
from module.umamusume.script.cultivate_task.parse import parse_cultivate_event, get_canonical_skill_name

log = logger.get_logger(__name__)

EVENT_TEMPLATES = [
    UI_CULTIVATE_EVENT_UMAMUSUME,
    UI_CULTIVATE_EVENT_SUPPORT_CARD,
    UI_CULTIVATE_EVENT_SCENARIO,
]


def is_still_on_event(ctrl):
    img = ctrl.get_screen()
    if img is None:
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    for tpl in EVENT_TEMPLATES:
        if image_match(gray, tpl).find_match:
            return True
    return False





def parse_hint_skill(text):
    if not text:
        return None
    m = re.search(r'for\s+(.+?)\.', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    idx = text.lower().find('for ')
    if idx >= 0:
        name = text[idx + 4:].strip().rstrip('.')
        if name:
            return name
    return None


def detect_hint_on_screen(img, event_name):
    try:
        tpl = REF_HINT_LEVELS_TEXT.template_image
        if tpl is None:
            return
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        roi = gray[935:min(h, 1132), 205:min(w, 339)]
        if roi.shape[0] < tpl.shape[0] or roi.shape[1] < tpl.shape[1]:
            return
        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= 0.80:
            match_y = 935 + max_loc[1]
            oy1 = max(0, match_y - 5)
            oy2 = min(img.shape[0], match_y + 30)
            ocr_region = img[oy1:oy2, 60:min(img.shape[1], 660)]
            text = ocr_line(ocr_region, lang='en') or ''
            skill = parse_hint_skill(text)
            if skill:
                canonical = get_canonical_skill_name(skill)
                resolved = canonical if canonical else skill
                log.info("Hint: %s", resolved)
                log_detected_skill(resolved, "event")
    except Exception:
        pass


def detect_hint_after_event(ctrl, event_name):
    try:
        time.sleep(1.5)
        tpl = REF_HINT_LEVELS_TEXT.template_image
        if tpl is None:
            return
        for _ in range(4):
            img = ctrl.get_screen()
            if img is None or getattr(img, 'size', 0) == 0:
                time.sleep(0.4)
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            roi = gray[935:min(h, 1132), 205:min(w, 339)]
            if roi.shape[0] < tpl.shape[0] or roi.shape[1] < tpl.shape[1]:
                time.sleep(0.4)
                continue
            res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= 0.80:
                match_y = 935 + max_loc[1]
                oy1 = max(0, match_y - 5)
                oy2 = min(img.shape[0], match_y + 30)
                ocr_region = img[oy1:oy2, 60:min(img.shape[1], 660)]
                text = ocr_line(ocr_region, lang='en') or ''
                skill = parse_hint_skill(text)
                if skill:
                    canonical = get_canonical_skill_name(skill)
                    resolved = canonical if canonical else skill
                    log.info("Hint: %s", resolved)
                    log_detected_skill(resolved, "event")
                return
            time.sleep(0.5)
    except Exception:
        pass


def script_cultivate_event(ctx: UmamusumeContext):
    try:
        cd = getattr(ctx.cultivate_detail, 'event_cooldown_until', 0)
        if isinstance(cd, (int, float)) and time.time() < cd:
            return
    except Exception:
        pass

    ctx.cultivate_detail.event_cooldown_until = time.time() + 1.5

    log.info("Event handler called")
    ctx.cultivate_detail.mant_cleat_used = False
    
    img = ctx.ctrl.get_screen()
    if img is None or getattr(img, 'size', 0) == 0:
        for _ in range(3):
            time.sleep(0.2)
            img = ctx.ctrl.get_screen()
            if img is not None and getattr(img, 'size', 0) > 0:
                break
    if img is None or getattr(img, 'size', 0) == 0:
        log.warning("Failed to get screen")
        return
    h, w = img.shape[:2]
    y1, y2, x1, x2 = 237, 283, 111, 480
    y1 = max(0, min(h, y1)); y2 = max(y1, min(h, y2))
    x1 = max(0, min(w, x1)); x2 = max(x1, min(w, x2))
    event_name_img = img[y1:y2, x1:x2]
    
    event_name = ocr_line(event_name_img, lang="en")
    
    if not event_name or not event_name.strip():
        h, w = event_name_img.shape[:2]
        event_name_img_upscaled = cv2.resize(event_name_img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        event_name = ocr_line(event_name_img_upscaled, lang="en")
    if isinstance(event_name, str) and len(event_name.strip()) <= 1:
        return
    try:
        from bot.recog.ocr import find_similar_text
        event_blacklist = [
            "", " ",
            "Team Support",
        ]
        if not isinstance(event_name, str) or not event_name.strip():
            return
        if find_similar_text(event_name, event_blacklist, 0.9):
            log.info(f"{event_name} blacklisted. Skipping")
            return
    except Exception:
        pass
    force_choice_index = None
    try:
        if isinstance(event_name, str) and 'team at last' in event_name.lower():
            from module.umamusume.script.cultivate_task.event.scenario_event import aoharuhai_team_name_event
            res = aoharuhai_team_name_event(ctx)
            if isinstance(res, int) and res > 0:
                force_choice_index = int(res)
            else:
                return
    except Exception:
        pass
    
    try:
        _, selectors = parse_cultivate_event(ctx, img)
    except Exception:
        selectors = []

    if not isinstance(selectors, list):
        selectors = []
    if len(selectors) == 0 or len(selectors) > 5:
        try:
            time.sleep(0.25)
            img_retry = ctx.ctrl.get_screen()
            _, selectors2 = parse_cultivate_event(ctx, img_retry)
            if isinstance(selectors2, list) and len(selectors2) > 0:
                selectors = selectors2
                log.info(len(selectors))
        except Exception:
            pass
    
    try:
        if isinstance(event_name, str) and event_name.strip().lower() == "tutorial":
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if isinstance(selectors, list) and len(selectors) in (2, 5):
                    break
                time.sleep(0.3)
                try:
                    img_wait = ctx.ctrl.get_screen()
                    if img_wait is not None and getattr(img_wait, 'size', 0) > 0:
                        _, selectors = parse_cultivate_event(ctx, img_wait)
                except Exception:
                    continue

            if isinstance(selectors, list) and len(selectors) == 5:
                target_pt = selectors[4]
                ctx.ctrl.click(int(target_pt[0]), int(target_pt[1]), "tutorial choice 5")
                time.sleep(1.0)
                img_confirm = ctx.ctrl.get_screen()
                if img_confirm is not None and getattr(img_confirm, 'size', 0) > 0:
                    _, confirm_selectors = parse_cultivate_event(ctx, img_confirm)
                    if isinstance(confirm_selectors, list) and len(confirm_selectors) >= 1:
                        confirm_pt = confirm_selectors[0]
                        ctx.ctrl.click(int(confirm_pt[0]), int(confirm_pt[1]), "tutorial Yes")
                ctx.cultivate_detail.event_cooldown_until = time.time() + 2.5
                return
            elif isinstance(selectors, list) and len(selectors) == 2:
                target_pt = selectors[1]
                ctx.ctrl.click(int(target_pt[0]), int(target_pt[1]), "tutorial choice 2")
                ctx.cultivate_detail.event_cooldown_until = time.time() + 2.5
                return
    except Exception:
        pass
    
    threading.Thread(target=detect_hint_on_screen, args=(img, event_name), daemon=True).start()

    if force_choice_index is not None:
        choice_index = force_choice_index
        choice_source = "hardcoded"
        expected_count = 0
    else:
        choice_index, choice_source, expected_count = get_event_choice(ctx, event_name)

    if not isinstance(choice_index, int) or choice_index <= 0:
        return
    if choice_index > 5:
        choice_index = 2

    if choice_source == "database" and expected_count >= 2:
        min_required = min(2, expected_count)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if isinstance(selectors, list) and len(selectors) >= expected_count:
                break
            time.sleep(0.3)
            try:
                img_wait = ctx.ctrl.get_screen()
                if img_wait is not None and getattr(img_wait, 'size', 0) > 0:
                    _, selectors_wait = parse_cultivate_event(ctx, img_wait)
                    if isinstance(selectors_wait, list) and len(selectors_wait) >= min_required:
                        selectors = selectors_wait
                        if len(selectors) >= expected_count:
                            break
            except Exception:
                continue
        log.info(f"expected={expected_count}, got {len(selectors) if isinstance(selectors, list) else 0}")

    if isinstance(selectors, list) and len(selectors) > 0:
        idx = int(choice_index)
        if idx < 1:
            idx = 1
        if idx > len(selectors):
            idx = len(selectors)
        target_pt = selectors[idx - 1]
        log.info(f"Clicking option {idx}/{len(selectors)} (source={choice_source})")
        ctx.ctrl.click(int(target_pt[0]), int(target_pt[1]), f"Event option-{choice_index}")
        threading.Thread(target=detect_hint_after_event, args=(ctx.ctrl, event_name), daemon=True).start()
        ctx.cultivate_detail.event_cooldown_until = time.time() + 2.5
        return
    try:
        tpl = Template(f"dialogue{choice_index}", UMAMUSUME_REF_TEMPLATE_PATH)
    except:
        tpl = None
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x1, y1, x2, y2 = 24, 316, 696, 936
    h, w = img_gray.shape[:2]
    x1 = max(0, min(w, x1)); x2 = max(x1, min(w, x2)); y1 = max(0, min(h, y1)); y2 = max(y1, min(h, y2))
    roi_gray = img_gray[y1:y2, x1:x2]
    clicked = False
    if tpl is not None:
        try:
            for _ in range(2):
                res = image_match(roi_gray, tpl)
                if res.find_match:
                    ctx.ctrl.click(res.center_point[0] + x1, res.center_point[1] + y1, f"Event option-{choice_index}")
                    threading.Thread(target=detect_hint_after_event, args=(ctx.ctrl, event_name), daemon=True).start()
                    clicked = True
                    ctx.cultivate_detail.event_cooldown_until = time.time() + 5
                    return
                time.sleep(0.56)
                img = ctx.ctrl.get_screen()
                img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                h, w = img_gray.shape[:2]
                x1 = max(0, min(w, x1)); x2 = max(x1, min(w, x2)); y1 = max(0, min(h, y1)); y2 = max(y1, min(h, y2))
                roi_gray = img_gray[y1:y2, x1:x2]
        except:
            pass
    if not clicked:
        if is_still_on_event(ctx.ctrl):
            log.info(f"no selectors found for '{event_name}', retrying parse")
            time.sleep(0.5)
            img_retry = ctx.ctrl.get_screen()
            if img_retry is not None:
                _, retry_selectors = parse_cultivate_event(ctx, img_retry)
                if isinstance(retry_selectors, list) and len(retry_selectors) > 0:
                    fallback_idx = min(int(choice_index), len(retry_selectors)) - 1
                    if fallback_idx < 0:
                        fallback_idx = 0
                    ctx.ctrl.click(int(retry_selectors[fallback_idx][0]), int(retry_selectors[fallback_idx][1]), f"Event fallback option-{fallback_idx + 1}")
            ctx.cultivate_detail.event_cooldown_until = time.time() + 3.0
        return
