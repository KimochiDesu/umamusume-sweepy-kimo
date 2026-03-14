import time
import cv2
import numpy as np

from module.umamusume.asset.template import REF_BLUE_LINE
from bot.recog.ocr import ocr_line
import bot.base.log as logger

log = logger.get_logger(__name__)

AFFLICTION_ROI_X1 = 22
AFFLICTION_ROI_Y1 = 671
AFFLICTION_ROI_X2 = 695
AFFLICTION_ROI_Y2 = 1102

BLUE_LINE_THRESHOLD = 0.75


def find_blue_lines(gray_roi, blue_tpl):
    th, tw = blue_tpl.shape[:2]
    if gray_roi.shape[0] < th or gray_roi.shape[1] < tw:
        return []
    result = cv2.matchTemplate(gray_roi, blue_tpl, cv2.TM_CCOEFF_NORMED)
    locations = []
    while True:
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < BLUE_LINE_THRESHOLD:
            break
        y = max_loc[1]
        locations.append(y)
        y_start = max(0, y - th)
        y_end = min(result.shape[0], y + th)
        result[y_start:y_end, :] = 0
    locations.sort()
    return locations


def detect_afflictions(ctx):
    ctx.ctrl.click(643, 773, "full stats")
    time.sleep(1.0)

    screen = ctx.ctrl.get_screen()
    if screen is None:
        ctx.ctrl.click(374, 1184, "exit stats")
        time.sleep(0.5)
        return []

    blue_tpl = REF_BLUE_LINE.template_image
    if blue_tpl is None:
        ctx.ctrl.click(374, 1184, "exit stats")
        time.sleep(0.5)
        return []

    roi = screen[AFFLICTION_ROI_Y1:AFFLICTION_ROI_Y2, AFFLICTION_ROI_X1:AFFLICTION_ROI_X2]
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    lines = find_blue_lines(gray_roi, blue_tpl)

    afflictions = []
    for line_y in lines:
        text_y_end = line_y
        text_y_start = max(0, line_y - 35)
        if text_y_end <= text_y_start:
            continue
        text_strip = gray_roi[text_y_start:text_y_end, :]
        text = ocr_line(text_strip, lang="en")
        if text and text.strip():
            afflictions.append(text.strip())

    log.info("Afflictions: %s", afflictions)

    ctx.ctrl.click(374, 1184, "exit stats")
    time.sleep(0.5)

    return afflictions
