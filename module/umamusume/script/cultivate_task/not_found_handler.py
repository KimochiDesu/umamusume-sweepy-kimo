import cv2
import random

import bot.base.log as logger
from bot.recog.ocr import ocr_line
from bot.recog.image_matcher import image_match
from module.umamusume.context import UmamusumeContext
from module.umamusume.asset.point import (
    CULTIVATE_RESULT_CONFIRM, GOAL_ACHIEVE_CONFIRM, GOAL_FAIL_CONFIRM,
    NEXT_GOAL_CONFIRM
)

log = logger.get_logger(__name__)

RACE_LIST_ROI = (238, 525, 300, 588)
TITLE_AREA_ROI = (200, 400, 100, 620)
BOND_AREA_ROI = (400, 600, 100, 620)
MIDDLE_AREA_ROI = (800, 1000, 200, 560)


def has_home_coin(ctx):
    try:
        img = ctx.current_screen
        if img is None:
            return False
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        from module.umamusume.asset.template import REF_HOME_COIN
        coin_match = image_match(img_gray, REF_HOME_COIN)
        return coin_match.find_match
    except Exception:
        return False


def script_not_found_ui(ctx: UmamusumeContext):
    if ctx.current_screen is not None:
        log.debug(f"NOT_FOUND_UI - Screen shape: {ctx.current_screen.shape}")

        if has_home_coin(ctx):
            return

        try:
            from module.umamusume.asset.template import REF_NEXT, REF_NEXT2
            img_gray_full = getattr(ctx, 'current_screen_gray', None)
            if img_gray_full is None:
                img_gray_full = cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
            next_match = image_match(img_gray_full, REF_NEXT)
            if next_match.find_match:
                ctx.ctrl.click(next_match.center_point[0], next_match.center_point[1], "REF_NEXT")
                return
            next2_match = image_match(img_gray_full, REF_NEXT2)
            if next2_match.find_match:
                ctx.ctrl.click(next2_match.center_point[0], next2_match.center_point[1], "REF_NEXT2")
                return
        except Exception:
            pass

        try:
            from module.umamusume.asset.template import UI_CULTIVATE_RACE_LIST_2
            img_gray_full = getattr(ctx, 'current_screen_gray', None)
            if img_gray_full is None:
                img_gray_full = cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
            x1, y1, x2, y2 = RACE_LIST_ROI
            h, w = img_gray_full.shape[:2]
            x1c = max(0, min(w, x1)); x2c = max(0, min(w, x2))
            y1c = max(0, min(h, y1)); y2c = max(0, min(h, y2))
            roi = img_gray_full[y1c:y2c, x1c:x2c]
            res = image_match(roi, UI_CULTIVATE_RACE_LIST_2)
            if res.find_match:
                from module.umamusume.script.cultivate_task.race_handlers import script_cultivate_race_list
                script_cultivate_race_list(ctx)
                return
        except Exception as e:
            log.debug(f"Race List ROI check failed: {e}")
                
        try:
            from module.umamusume.asset.template import UI_CULTIVATE_RESULT_1
            
            img = ctx.current_screen
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            result = image_match(img_gray, UI_CULTIVATE_RESULT_1)
            
            if result.find_match:
                log.info("Cultivate Result 1 template matched! Clicking confirm button")
                ctx.ctrl.click_by_point(CULTIVATE_RESULT_CONFIRM)
                return
            else:
                log.debug("Cultivate Result 1 template not found")
                
        except Exception as e:
            log.debug(f"Template matching failed: {str(e)}")
        
        try:
            img = ctx.current_screen
            title_area = img[TITLE_AREA_ROI[0]:TITLE_AREA_ROI[1], TITLE_AREA_ROI[2]:TITLE_AREA_ROI[3]]
            title_text = ocr_line(title_area).lower()
            
            log.debug(f"OCR detected text: '{title_text[:100]}...'")
            
            result_keywords = ['rewards', 'result', 'cultivation', 'complete', 'finish']
            if any(keyword in title_text for keyword in result_keywords):
                log.info(f"Potential cultivation result detected: '{title_text[:50]}...'")
                log.info("Attempting to click cultivation result confirm button")
                ctx.ctrl.click_by_point(CULTIVATE_RESULT_CONFIRM)
                return
                
            by1, by2, bx1, bx2 = BOND_AREA_ROI
            bond_area = img[by1:by2, bx1:bx2]
            bond_text = ocr_line(bond_area).lower()
            log.debug(f"Bond area OCR: '{bond_text[:100]}...'")
            if 'bond level' in bond_text or 'total fans' in bond_text:
                log.info(f"Rewards screen detected via bond/fans text: '{bond_text[:50]}...'")
                log.info("Attempting to click cultivation result confirm button")
                ctx.ctrl.click_by_point(CULTIVATE_RESULT_CONFIRM)
                return
                
        except Exception as e:
            log.debug(f"Cultivation result detection failed: {str(e)}")
    
    try:
        img = ctx.current_screen
        if img is not None:
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            ty1, ty2, tx1, tx2 = TITLE_AREA_ROI
            title_area = img_gray[ty1:ty2, tx1:tx2]
            title_text = ocr_line(title_area).lower()
            
            my1, my2, mx1, mx2 = MIDDLE_AREA_ROI
            middle_area = img_gray[my1:my2, mx1:mx2]
            middle_text = ocr_line(middle_area).lower()
            
            goal_keywords = ['goal', 'complete', 'achieved', 'failed', 'next', 'finish', 'target', 'objective']
            
            combined_text = f"{title_text} {middle_text}"
            
            if any(keyword in combined_text for keyword in goal_keywords):
                log.info(f"Fallback goal screen detected: '{combined_text[:50]}...'")
                
                if any(word in combined_text for word in ['complete', 'achieved']):
                    try:
                        from module.umamusume.asset.template import REF_NEXT
                        img_full = getattr(ctx, 'current_screen_gray', None) or cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
                        next_match = image_match(img_full, REF_NEXT)
                        if next_match.find_match:
                            ctx.ctrl.click(next_match.center_point[0], next_match.center_point[1], "REF_NEXT")
                            return
                    except Exception:
                        pass
                    ctx.ctrl.click_by_point(GOAL_ACHIEVE_CONFIRM)
                    return
                elif any(word in combined_text for word in ['failed']):
                    try:
                        from module.umamusume.asset.template import REF_NEXT
                        img_full = getattr(ctx, 'current_screen_gray', None) or cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
                        next_match = image_match(img_full, REF_NEXT)
                        if next_match.find_match:
                            ctx.ctrl.click(next_match.center_point[0], next_match.center_point[1], "REF_NEXT")
                            return
                    except Exception:
                        pass
                    ctx.ctrl.click_by_point(GOAL_FAIL_CONFIRM)
                    return
                elif any(word in combined_text for word in ['next']):
                    try:
                        from module.umamusume.asset.template import REF_NEXT
                        img_full = getattr(ctx, 'current_screen_gray', None) or cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
                        next_match = image_match(img_full, REF_NEXT)
                        if next_match.find_match:
                            ctx.ctrl.click(next_match.center_point[0], next_match.center_point[1], "REF_NEXT")
                            return
                    except Exception:
                        pass
                    ctx.ctrl.click_by_point(NEXT_GOAL_CONFIRM)
                    return
                else:
                    log.info(f"Generic goal screen - using standard position")
                    ctx.ctrl.click(370, 1110, "Generic goal confirmation")
                    return
            
    except Exception as e:
        log.debug(f"Goal detection fallback failed: {str(e)}")
    try:
        from module.umamusume.asset.template import REF_NEXT
        img = getattr(ctx, 'current_screen_gray', None) or cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
        next_match = image_match(img, REF_NEXT)
        if next_match.find_match:
            center_x = next_match.center_point[0]
            center_y = next_match.center_point[1]
            ctx.ctrl.click(center_x, center_y, "Next button")
            return
    except Exception:
        pass

    try:
        from module.umamusume.asset.template import REF_EDIT_TEAM
        img_gray = getattr(ctx, 'current_screen_gray', None) or cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
        edit_team_match = image_match(img_gray, REF_EDIT_TEAM)
        if edit_team_match.find_match:
            x = random.randint(276, 452)
            y = random.randint(1155, 1196)
            ctx.ctrl.click(x, y, "Default fallback click")
            return
    except Exception:
        pass

    try:
        from module.umamusume.asset.template import REF_TP
        img_gray = getattr(ctx, 'current_screen_gray', None) or cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
        tp_match = image_match(img_gray, REF_TP)
        if tp_match.find_match:
            return
    except Exception:
        pass

    try:
        from module.umamusume.define import ScenarioType
        if (hasattr(ctx, 'cultivate_detail') and hasattr(ctx.cultivate_detail, 'scenario')
                and ctx.cultivate_detail.scenario.scenario_type() == ScenarioType.SCENARIO_TYPE_MANT):
            from module.umamusume.asset.template import REF_MANT_FINAL_END
            img_gray = getattr(ctx, 'current_screen_gray', None) or cv2.cvtColor(ctx.current_screen, cv2.COLOR_BGR2GRAY)
            final_match = image_match(img_gray, REF_MANT_FINAL_END)
            if final_match.find_match:
                ctx.ctrl.click(360, 1110, "MANT final end Next")
                return
    except Exception:
        pass

    log.debug("No specific UI detected - using default fallback click")
    # Click center-bottom area (standard "Next/Continue" button zone)
    x, y = random.randint(300, 420), random.randint(1050, 1150)
    ctx.ctrl.click(x, y, "Default fallback click")
