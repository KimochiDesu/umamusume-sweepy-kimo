from module.umamusume.context import UmamusumeContext
from module.umamusume.define import TurnOperationType
from module.umamusume.asset.template import REF_DIALOGUE_SELECTOR, REF_AOHARUHAI_TEAM_NAME
from bot.recog.image_matcher import image_match
from bot.conn.fetch import read_energy
import time

import bot.base.log as logger
log = logger.get_logger(__name__)

# First year New Year event
def scenario_event_1(ctx: UmamusumeContext) -> int:
    energy = read_energy()
    if ctx.cultivate_detail.turn_info.turn_operation == TurnOperationType.TURN_OPERATION_TYPE_REST or \
            (ctx.cultivate_detail.turn_info.turn_operation == TurnOperationType.TURN_OPERATION_TYPE_MEDIC and energy >= 50) or \
            (ctx.cultivate_detail.turn_info.turn_operation == TurnOperationType.TURN_OPERATION_TYPE_TRIP and energy >= 50):
        return 3
    else:
        return 2


# Second year New Year event
def scenario_event_2(ctx: UmamusumeContext) -> int:
    energy = read_energy()
    if ctx.cultivate_detail.turn_info.turn_operation == TurnOperationType.TURN_OPERATION_TYPE_REST or \
            (ctx.cultivate_detail.turn_info.turn_operation == TurnOperationType.TURN_OPERATION_TYPE_MEDIC and energy >= 40) or \
            (ctx.cultivate_detail.turn_info.turn_operation == TurnOperationType.TURN_OPERATION_TYPE_TRIP and energy >= 50):
        return 3
    else:
        return 1

def _find_dialogue_selectors(img):
    all_points = []
    for template in REF_DIALOGUE_SELECTOR:
        img_temp = img.copy()
        for _ in range(20):
            match_result = image_match(img_temp, template)
            if not match_result.find_match:
                break
            all_points.append(match_result)
            m = match_result.matched_area
            img_temp[m[0][1]:m[1][1], m[0][0]:m[1][0]] = 0
    all_points.sort(key=lambda p: p.matched_area[0][1])
    result = [all_points[0]]
    for mr in all_points[1:]:
        if abs(mr.matched_area[0][1] - result[-1].matched_area[0][1]) > 20 or abs(mr.center_point[0] - result[-1].center_point[0]) > 80:
            result.append(mr)
    return result[:5]
    
# Youth Cup team name selection event
def aoharuhai_team_name_event(ctx: UmamusumeContext) -> int:
    img = ctx.ctrl.get_screen(to_gray=True)
    event_selector_list = _find_dialogue_selectors(img)

    try:
        sel = int(getattr(ctx.task.detail.scenario_config.aoharu_config, 'aoharu_team_name_selection', 4))
    except Exception:
        sel = 4
    if sel not in (0, 1, 2, 3, 4):
        sel = 4
    name_map = {
        0: "Taiki Shuttle <HOP CHEERS>",
        1: "Matikanefukukitaru <Sunny Runner>",
        2: "Haru Urara <Carrot Pudding>",
        3: "Rice Shower <Bloom>",
        4: "Default <Carrot>",
    }
    log.info(f"Aoharu team configured: index={sel} name={name_map.get(sel, 'Unknown')}")
    if sel == 4:
        log.info(f"Selecting Aoharu team: {name_map[4]} (choose last option, total options={len(event_selector_list)})")
        try:
            if event_selector_list:
                last = event_selector_list[-1]
                cx, cy = last.center_point
                ctx.ctrl.click(int(cx), int(cy), "Select Default <Carrot> (last option)")
                ctx.cultivate_detail.event_cooldown_until = time.time() + 2.5
                return 0
            else:
                from module.umamusume.script.cultivate_task.parse import parse_cultivate_event
                img_color = ctx.ctrl.get_screen()
                _, selectors = parse_cultivate_event(ctx, img_color)
                if isinstance(selectors, list) and selectors:
                    tx, ty = selectors[-1]
                    ctx.ctrl.click(int(tx), int(ty), "Select Default <Carrot> (last option)")
                    ctx.cultivate_detail.event_cooldown_until = time.time() + 2.5
                    return 0
        except Exception:
            pass
        return len(event_selector_list) if event_selector_list else 4

    h, w = img.shape[:2]
    x1, y1, x2, y2 = 70, 315, 162, 811
    x1 = max(0, min(w, x1)); x2 = max(x1, min(w, x2))
    y1 = max(0, min(h, y1)); y2 = max(y1, min(h, y2))
    roi = img[y1:y2, x1:x2]

    res = image_match(roi, REF_AOHARUHAI_TEAM_NAME[sel])
    if res.find_match:
        gx = x1 + res.center_point[0]
        gy = y1 + res.center_point[1]
        log.info(f"Selecting Aoharu team: {name_map.get(sel, 'Unknown')} at ({gx},{gy}) by ROI match")
        try:
            ctx.ctrl.click(int(gx), int(gy), "Select Aoharu team by name")
            ctx.cultivate_detail.event_cooldown_until = time.time() + 2.5
            return 0
        except Exception:
            pass
        return 0

    log.info("No match for configured Youth Cup team name")
    return 0
