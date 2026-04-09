"""Discord webhook notifier for curated career events.

Non-blocking, silent-failing sender. The bot should never break because
Discord is unreachable or rate-limited.
"""
import json
import threading
import time
from urllib import request as _urlreq
from urllib import error as _urlerr

import bot.base.log as logger

log = logger.get_logger(__name__)

_MIN_INTERVAL = 1.2  # seconds between sends (stay under Discord 30/min)
_last_send_ts = 0.0
_send_lock = threading.Lock()


def _get_config():
    try:
        from module.umamusume.persistence import get_discord_config
        return get_discord_config()
    except Exception:
        return {'webhook_url': '', 'user_id': ''}


def _post(webhook_url: str, payload: dict):
    try:
        data = json.dumps(payload).encode('utf-8')
        req = _urlreq.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'umamusume-sweepy'},
            method='POST',
        )
        with _urlreq.urlopen(req, timeout=6) as resp:
            resp.read()
    except _urlerr.HTTPError as e:
        log.debug(f"Discord webhook HTTP {e.code}: {e.reason}")
    except Exception as e:
        log.debug(f"Discord webhook send failed: {e}")


def _send_async(payload: dict):
    cfg = _get_config()
    url = cfg.get('webhook_url') or ''
    if not url:
        return
    global _last_send_ts
    with _send_lock:
        gap = time.time() - _last_send_ts
        if gap < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - gap)
        _last_send_ts = time.time()
    t = threading.Thread(target=_post, args=(url, payload), daemon=True)
    t.start()


def send_message(content: str, mention_user: bool = False):
    """Fire-and-forget send of a plain text message to the configured webhook."""
    if not content:
        return
    cfg = _get_config()
    url = cfg.get('webhook_url') or ''
    if not url:
        return
    if mention_user and cfg.get('user_id'):
        content = f"<@{cfg['user_id']}> {content}"
    # Discord limit is 2000 chars
    if len(content) > 1900:
        content = content[:1900] + "\n…(truncated)"
    _send_async({'content': content, 'allowed_mentions': {'parse': ['users']}})


# ------------------------------ formatting helpers ------------------------------

_MOOD_NAMES = {0: 'Unknown', 1: 'Awful', 2: 'Bad', 3: 'Normal', 4: 'Good', 5: 'Great'}

# 24 turns per year (2 per in-game month). Phase boundaries match
# module.umamusume.constants.game_constants: DEBUT 1-12, JUNIOR 13-24,
# CLASSIC 25-48, SENIOR 49-72, FINALE 73+.
def _phase_name(date: int) -> str:
    try:
        from module.umamusume.constants.game_constants import (
            PRE_DEBUT_END, JUNIOR_YEAR_END, CLASSIC_YEAR_END, SENIOR_YEAR_END,
        )
    except Exception:
        PRE_DEBUT_END, JUNIOR_YEAR_END, CLASSIC_YEAR_END, SENIOR_YEAR_END = 12, 24, 48, 72
    if date is None or date <= 0:
        return 'DEBUT'
    if date <= PRE_DEBUT_END:
        return 'DEBUT'
    if date <= JUNIOR_YEAR_END:
        return 'JUNIOR'
    if date <= CLASSIC_YEAR_END:
        return 'CLASSIC'
    if date <= SENIOR_YEAR_END:
        return 'SENIOR'
    return 'FINALE'


def _half_name(date: int) -> str:
    if date is None or date <= 0:
        return ''
    # Each in-game month has two turns: early / late.
    return 'EARLY' if (date % 2 == 1) else 'LATE'


_MONTH_NAMES = ['Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May','Jun']

def _month_index(date: int) -> int:
    if date is None or date <= 0:
        return 0
    # 2 turns per month, starting at month 1 of the current phase year
    return ((date - 1) % 24) // 2 + 1

def _month_name(date: int) -> str:
    if date is None or date <= 0:
        return ''
    # Career starts Junior Year Early July; 2 turns per month, 12 months per year
    offset = ((date - 1) // 2) % 12
    return _MONTH_NAMES[offset]


def _scenario_name(ctx) -> str:
    try:
        return ctx.cultivate_detail.scenario.scenario_name().upper()
    except Exception:
        try:
            return ctx.cultivate_detail.scenario.scenario_type().name.replace('SCENARIO_TYPE_', '')
        except Exception:
            return 'UNKNOWN'


def _mood_name(ctx) -> str:
    try:
        ti = ctx.cultivate_detail.turn_info
        lvl = getattr(ti, 'cached_mood', None)
        if lvl is None:
            lvl = getattr(ti, 'motivation_level', None)
        if lvl is None:
            return 'Unknown'
        if hasattr(lvl, 'value'):
            lvl = lvl.value
        return _MOOD_NAMES.get(int(lvl), 'Unknown')
    except Exception:
        return 'Unknown'


def _energy_str(ctx) -> str:
    try:
        ti = ctx.cultivate_detail.turn_info
        cur = getattr(ti, 'cached_energy', None)
        if cur is None:
            cur = getattr(ti, 'base_energy', None)
        if cur is None:
            rs = getattr(ti, 'remain_stamina', -1)
            cur = rs if (rs is not None and rs >= 0) else None
        mx = getattr(ctx.cultivate_detail, 'mant_max_energy', 100) or 100
        if cur is None:
            return f"?/{mx}"
        try:
            cur_int = int(round(float(cur)))
        except Exception:
            return f"?/{mx}"
        return f"{cur_int}/{mx}"
    except Exception:
        return "?/?"


def _shop_items_line(ctx) -> str:
    try:
        items = getattr(ctx.cultivate_detail, 'mant_shop_items', []) or []
        coins = getattr(ctx.cultivate_detail, 'mant_coins', 0)
        if not items:
            return f"**SHOP ITEMS** ({coins} coins): (none scanned)"
        names = []
        for it in items[:15]:
            if isinstance(it, dict):
                nm = it.get('name') or it.get('item') or ''
            elif isinstance(it, (tuple, list)):
                nm = it[0] if len(it) > 0 else ''
            else:
                nm = str(it)
            if nm:
                names.append(str(nm))
        more = '' if len(items) <= 15 else f" (+{len(items) - 15} more)"
        return f"**SHOP ITEMS** ({coins} coins): " + ", ".join(names) + more
    except Exception:
        return "**SHOP ITEMS:** (error)"


def _used_items_line(ctx) -> str:
    try:
        used = getattr(ctx.cultivate_detail, '_discord_used_items', []) or []
        if not used:
            return "**USED ITEMS:** (none)"
        return "**USED ITEMS:** " + ", ".join(used)
    except Exception:
        return "**USED ITEMS:** (error)"


def _bought_items_line(ctx) -> str:
    try:
        bought = getattr(ctx.cultivate_detail, '_discord_bought_items', []) or []
        if not bought:
            return "**BOUGHT ITEMS:** (none)"
        return "**BOUGHT ITEMS:** " + ", ".join(bought)
    except Exception:
        return "**BOUGHT ITEMS:** (error)"


def _stats_line(ctx) -> str:
    try:
        attr = getattr(ctx.cultivate_detail.turn_info, 'uma_attribute', None)
        if attr is None:
            return ''
        return (f"SPD {attr.speed} | STAM {attr.stamina} | POW {attr.power} | "
                f"GUTS {attr.will} | WIT {attr.intelligence}")
    except Exception:
        return ''


def _action_line(ctx) -> str:
    """Describe what the bot did this turn: train X / race / rest / recreation / medic."""
    try:
        from module.umamusume.define import TurnOperationType, TrainingType
        op = getattr(ctx.cultivate_detail.turn_info, 'turn_operation', None)
        if op is None:
            return "**ACTION:** ?"
        op_type = getattr(op, 'turn_operation_type', None)
        if op_type == TurnOperationType.TURN_OPERATION_TYPE_TRAINING:
            tt = getattr(op, 'training_type', None)
            name = {
                TrainingType.TRAINING_TYPE_SPEED: 'Speed',
                TrainingType.TRAINING_TYPE_STAMINA: 'Stamina',
                TrainingType.TRAINING_TYPE_POWER: 'Power',
                TrainingType.TRAINING_TYPE_WILL: 'Guts',
                TrainingType.TRAINING_TYPE_INTELLIGENCE: 'Wit',
            }.get(tt, None)
            if name is None:
                try:
                    name = str(tt.name).replace('TRAINING_TYPE_', '').title()
                except Exception:
                    name = '?'
            return f"**ACTION:** Trained {name}"
        if op_type == TurnOperationType.TURN_OPERATION_TYPE_RACE:
            return "**ACTION:** Race"
        if op_type == TurnOperationType.TURN_OPERATION_TYPE_TRIP:
            return "**ACTION:** Recreation/Rest"
        # Fall back to the enum name
        try:
            return f"**ACTION:** {op_type.name.replace('TURN_OPERATION_TYPE_', '').title()}"
        except Exception:
            return "**ACTION:** ?"
    except Exception:
        return "**ACTION:** ?"


def _race_line(ctx) -> str:
    try:
        from module.umamusume.define import TurnOperationType
        ti = ctx.cultivate_detail.turn_info
        op = getattr(ti, 'turn_operation', None)
        if op is None:
            return "**RACE:** No"
        op_type = getattr(op, 'turn_operation_type', None)
        if op_type != TurnOperationType.TURN_OPERATION_TYPE_RACE:
            return "**RACE:** No"
        race_id = getattr(op, 'race_id', 0) or 0
        try:
            from module.umamusume.asset.race_data import RACE_LIST
            info = RACE_LIST.get(int(race_id))
            if info:
                return f"**RACE:** {info[1]} (id {race_id})"
        except Exception:
            pass
        return f"**RACE:** id {race_id}"
    except Exception:
        return "**RACE:** ?"


def notify_turn_summary(ctx):
    """Send the per-turn summary line. Safe to call anywhere — bails if no webhook."""
    try:
        cfg = _get_config()
        if not cfg.get('webhook_url'):
            return
        detail = ctx.cultivate_detail
        date = getattr(detail.turn_info, 'date', -1)
        phase = _phase_name(date)
        half = _half_name(date)
        month = _month_name(date)
        scenario = _scenario_name(ctx)
        mood = _mood_name(ctx)
        energy = _energy_str(ctx)

        header = f"**Turn {date} | {phase} | {half} {month} | Energy {energy} | Mood {mood} | {scenario}**"
        lines = ["**---------------------------------------------**", header]
        stats = _stats_line(ctx)
        if stats:
            lines.append(stats)
        lines.append(_action_line(ctx))
        lines.append(_shop_items_line(ctx))
        lines.append(_bought_items_line(ctx))
        lines.append(_used_items_line(ctx))
        lines.append(_race_line(ctx))
        send_message("\n".join(lines))
    except Exception as e:
        log.debug(f"notify_turn_summary failed: {e}")


def _sparks_line(ctx) -> str:
    """Format sparks as 'Stamina (3) Mile (3) Groundwork (3) ...' from the
    parsed cultivate_result.factor_list (list of [name, level])."""
    try:
        cres = getattr(ctx.task.detail, 'cultivate_result', {}) or {}
        factors = cres.get('factor_list') or []
        if not factors:
            return ''
        parts = []
        for f in factors:
            try:
                name = f[0]
                level = int(f[1])
            except Exception:
                continue
            if not name or level <= 0:
                continue
            parts.append(f"{name} ({level})")
        if not parts:
            return ''
        return "Sparks: " + " ".join(parts)
    except Exception:
        return ''


def _skills_line() -> str:
    """Format the full detected-skill set from this run."""
    try:
        from module.umamusume.context import detected_skills_log
        names = []
        for entry in detected_skills_log.values():
            n = entry.get('name') if isinstance(entry, dict) else None
            if n:
                names.append(str(n))
        if not names:
            return ''
        # De-dup while preserving order
        seen = set()
        unique = []
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            unique.append(n)
        return "Skills: " + ", ".join(unique)
    except Exception:
        return ''


def notify_career_finished(ctx, reason: str = 'COMPLETE'):
    """Final summary for a completed career, pings the configured user."""
    try:
        cfg = _get_config()
        if not cfg.get('webhook_url'):
            return
        detail = ctx.cultivate_detail
        scenario = _scenario_name(ctx)

        fans = getattr(detail, 'final_fans', None)
        if fans is None:
            fans = getattr(detail, 'fan_count', None)

        attr = getattr(getattr(detail, 'turn_info', None), 'uma_attribute', None)
        stats_line = ''
        if attr is not None:
            try:
                stats_line = (
                    f"SPD {attr.speed} | STA {attr.stamina} | PWR {attr.power} | "
                    f"WIL {attr.will} | INT {attr.intelligence}"
                )
            except Exception:
                stats_line = ''

        lines = [f"**Career Finished — {scenario} ({reason})**"]
        if stats_line:
            lines.append(stats_line)
        if fans is not None:
            lines.append(f"Fans: {fans}")
        sparks = _sparks_line(ctx)
        if sparks:
            lines.append(sparks)
        skills = _skills_line()
        if skills:
            lines.append(skills)
        send_message("\n".join(lines), mention_user=True)
    except Exception as e:
        log.debug(f"notify_career_finished failed: {e}")


# ------------------------------ per-turn state helpers ------------------------------

def mark_items_bought(ctx, item_names):
    """Called from shop purchase flow whenever item(s) are bought this turn."""
    try:
        lst = getattr(ctx.cultivate_detail, '_discord_bought_items', None)
        if lst is None:
            lst = []
            ctx.cultivate_detail._discord_bought_items = lst
        if isinstance(item_names, str):
            item_names = [item_names]
        for n in item_names or []:
            if n:
                lst.append(str(n))
    except Exception:
        pass


def mark_item_used(ctx, item_name: str):
    """Called from inventory handlers whenever an item is consumed this turn."""
    try:
        if not item_name:
            return
        lst = getattr(ctx.cultivate_detail, '_discord_used_items', None)
        if lst is None:
            lst = []
            ctx.cultivate_detail._discord_used_items = lst
        lst.append(str(item_name))
    except Exception:
        pass


def mark_race(ctx, race_label: str):
    try:
        ctx.cultivate_detail._discord_raced_this_turn = str(race_label) if race_label else None
    except Exception:
        pass


def reset_turn_tracking(ctx):
    try:
        ctx.cultivate_detail._discord_used_items = []
        ctx.cultivate_detail._discord_bought_items = []
        ctx.cultivate_detail._discord_raced_this_turn = None
    except Exception:
        pass
