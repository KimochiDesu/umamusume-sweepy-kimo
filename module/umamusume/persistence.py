import json
import os
import threading
import time

import bot.base.log as logger

log = logger.get_logger(__name__)

PERSISTENCE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'career_data.json')
PERSISTENCE_FILE = os.path.normpath(PERSISTENCE_FILE)

PERSIST_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'persist.json')
PERSIST_FILE = os.path.normpath(PERSIST_FILE)

MAX_DATAPOINTS = 888

career_cleared_flag = False
career_data_lock = threading.Lock()


def rebuild_percentile_history(score_history):
    percentiles = []
    for i in range(1, len(score_history)):
        current = score_history[i]
        prev = score_history[:i]
        below_count = sum(1 for s in prev if s < current)
        percentile = below_count / len(prev) * 100
        percentiles.append(percentile)
    return percentiles


def save_career_data(ctx):
    global career_cleared_flag
    try:
        with career_data_lock:
            if career_cleared_flag:
                career_cleared_flag = False
                ctx.cultivate_detail.score_history = []
                ctx.cultivate_detail.percentile_history = []
                log.info("Career data cleared from memory")
                return
            score_history = getattr(ctx.cultivate_detail, 'score_history', [])
            if not score_history:
                return
            scores = score_history[-MAX_DATAPOINTS:]
            stat_only_history = getattr(ctx.cultivate_detail, 'stat_only_history', [])
            stat_only = stat_only_history[-MAX_DATAPOINTS:]
            data = {
                'score_history': scores,
                'stat_only_history': stat_only,
            }
            with open(PERSISTENCE_FILE, 'w') as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
    except Exception as e:
        log.info(f"Failed to save career data: {e}")


def load_career_data(ctx):
    try:
        if not os.path.exists(PERSISTENCE_FILE):
            return False
        with open(PERSISTENCE_FILE, 'r') as f:
            data = json.load(f)
        score_history = data.get('score_history', [])
        stat_only_history = data.get('stat_only_history', [])
        if not score_history:
            return False
        scores = score_history[-MAX_DATAPOINTS:]
        stat_only = stat_only_history[-MAX_DATAPOINTS:]
        ctx.cultivate_detail.score_history = scores
        ctx.cultivate_detail.stat_only_history = stat_only
        ctx.cultivate_detail.percentile_history = rebuild_percentile_history(scores)
        log.info(f"Restored career data: {len(scores)} datapoints")
        return True
    except Exception as e:
        log.info(f"Failed to load career data: {e}")
        return False


def clear_career_data():
    global career_cleared_flag
    try:
        with career_data_lock:
            with open(PERSISTENCE_FILE, 'w') as f:
                json.dump({'score_history': [], 'stat_only_history': []}, f)
                f.flush()
                os.fsync(f.fileno())
            career_cleared_flag = True
        log.info("Career data cleared")
        return True
    except Exception as e:
        log.info(f"Failed to clear career data: {e}")
        return False


def load_persist():
    try:
        if not os.path.exists(PERSIST_FILE):
            return {}
        with open(PERSIST_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_persist(data):
    try:
        with open(PERSIST_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def mark_buff_used(item_name):
    data = load_persist()
    used = set(data.get('used_buffs', []))
    used.add(item_name)
    data['used_buffs'] = list(used)
    save_persist(data)


def is_buff_used(item_name):
    data = load_persist()
    return item_name in data.get('used_buffs', [])


def get_used_buffs():
    data = load_persist()
    return set(data.get('used_buffs', []))


def clear_used_buffs():
    data = load_persist()
    data['used_buffs'] = []
    save_persist(data)


def get_ignore_cat_food():
    data = load_persist()
    return data.get('ignore_cat_food', False)


def set_ignore_cat_food(flag=True):
    data = load_persist()
    data['ignore_cat_food'] = flag
    save_persist(data)


def clear_ignore_cat_food():
    data = load_persist()
    data.pop('ignore_cat_food', None)
    save_persist(data)


def get_ignore_grilled_carrots():
    data = load_persist()
    return data.get('ignore_grilled_carrots', False)


def set_ignore_grilled_carrots(flag=True):
    data = load_persist()
    data['ignore_grilled_carrots'] = flag
    save_persist(data)


def clear_ignore_grilled_carrots():
    data = load_persist()
    data.pop('ignore_grilled_carrots', None)
    save_persist(data)


def get_discord_config():
    data = load_persist()
    return {
        'webhook_url': data.get('discord_webhook_url', ''),
        'user_id': data.get('discord_user_id', ''),
    }


def set_discord_config(webhook_url: str = '', user_id: str = ''):
    data = load_persist()
    data['discord_webhook_url'] = webhook_url or ''
    data['discord_user_id'] = user_id or ''
    save_persist(data)


def save_megaphone_state(tier, turns):
    data = load_persist()
    data['megaphone_tier'] = tier
    data['megaphone_turns'] = turns
    save_persist(data)


def load_megaphone_state():
    data = load_persist()
    tier = data.get('megaphone_tier', 0)
    turns = data.get('megaphone_turns', 0)
    return tier, turns


def clear_megaphone_state():
    data = load_persist()
    data.pop('megaphone_tier', None)
    data.pop('megaphone_turns', None)
    save_persist(data)


CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'training_checkpoint.json')
CHECKPOINT_FILE = os.path.normpath(CHECKPOINT_FILE)

checkpoint_lock = threading.Lock()


def _serialize_enum(obj):
    """Convert enum to its value"""
    if hasattr(obj, 'value'):
        return obj.value
    return obj


def _serialize_object(obj, max_depth=10, current_depth=0):
    """Recursively serialize an object to dict"""
    if current_depth > max_depth:
        return None

    if obj is None or isinstance(obj, (int, float, str, bool)):
        return obj

    if isinstance(obj, (list, tuple)):
        return [_serialize_object(item, max_depth, current_depth + 1) for item in obj]

    if isinstance(obj, dict):
        return {k: _serialize_object(v, max_depth, current_depth + 1) for k, v in obj.items()}

    if hasattr(obj, 'value'):
        return obj.value

    if hasattr(obj, '__dict__'):
        result = {}
        for k, v in obj.__dict__.items():
            if not k.startswith('_') and k not in ['scenario']:
                result[k] = _serialize_object(v, max_depth, current_depth + 1)
        return result

    return str(obj)


def save_checkpoint(ctx):
    """Save training checkpoint for crash recovery"""
    try:
        with checkpoint_lock:
            detail = ctx.cultivate_detail

            scenario_type = None
            if hasattr(detail, 'scenario') and detail.scenario:
                scenario_type = _serialize_enum(detail.scenario.scenario_type())

            task_detail = ctx.task.detail if hasattr(ctx, 'task') and hasattr(ctx.task, 'detail') else None

            # Capture the full raw attachment_data from the running task so resume
            # preserves every field (item_tiers, mant_config, and anything else).
            full_attachment = None
            try:
                from bot.engine.scheduler import scheduler
                from bot.base.purge import serialize_umamusume_task
                for _t in scheduler.get_task_list() or []:
                    if getattr(_t, 'app_name', None) != 'umamusume':
                        continue
                    if getattr(_t, 'detail', None) is task_detail:
                        raw = getattr(_t, 'attachment_data', None)
                        if isinstance(raw, dict) and raw:
                            full_attachment = raw
                        else:
                            full_attachment = serialize_umamusume_task(_t)
                        break
                if full_attachment is None and task_detail is not None:
                    # Fallback: serialize from the first umamusume task we find.
                    for _t in scheduler.get_task_list() or []:
                        if getattr(_t, 'app_name', None) == 'umamusume':
                            full_attachment = serialize_umamusume_task(_t)
                            break
            except Exception as _e:
                log.info(f"Checkpoint full_attachment capture failed: {_e}")

            checkpoint_data = {
                'in_progress': True,
                'scenario_type': scenario_type,
                'full_attachment_data': full_attachment,
                'task_config': {
                    'expect_attribute': detail.expect_attribute,
                    'follow_support_card_name': detail.follow_support_card_name,
                    'follow_support_card_level': detail.follow_support_card_level,
                    'extra_race_list': detail.extra_race_list,
                    'learn_skill_list': detail.learn_skill_list,
                    'learn_skill_blacklist': detail.learn_skill_blacklist,
                    'tactic_list': detail.tactic_list,
                    'tactic_actions': detail.tactic_actions,
                    'clock_use_limit': detail.clock_use_limit,
                    'learn_skill_threshold': getattr(detail, 'learn_skill_threshold', 180),
                    'learn_skill_only_user_provided': getattr(detail, 'learn_skill_only_user_provided', False),
                    'allow_recover_tp': detail.allow_recover_tp,
                    'extra_weight': detail.extra_weight,
                    'manual_purchase_at_end': getattr(task_detail, 'manual_purchase_at_end', False) if task_detail else False,
                    'override_insufficient_fans_forced_races': getattr(task_detail, 'override_insufficient_fans_forced_races', False) if task_detail else False,
                    'use_last_parents': getattr(detail, 'use_last_parents', False),
                    'rest_threshold': getattr(detail, 'rest_threshold', 48),
                    'motivation_threshold_year1': getattr(detail, 'motivation_threshold_year1', 3),
                    'motivation_threshold_year2': getattr(detail, 'motivation_threshold_year2', 4),
                    'motivation_threshold_year3': getattr(detail, 'motivation_threshold_year3', 4),
                    'skip_training_on_race_day': getattr(detail, 'skip_training_on_race_day', False),
                    'prioritize_recreation': getattr(detail, 'prioritize_recreation', False),
                    'pal_name': getattr(detail, 'pal_name', ''),
                    'pal_thresholds': getattr(detail, 'pal_thresholds', []),
                    'spirit_explosion': getattr(detail, 'spirit_explosion', [0.16, 0.16, 0.16, 0.06, 0.11]),
                },
                'state': {
                    'turn_info': _serialize_object(detail.turn_info),
                    'turn_info_history': _serialize_object(detail.turn_info_history),
                    'learn_skill_done': detail.learn_skill_done,
                    'learn_skill_selected': detail.learn_skill_selected,
                    'debut_race_win': detail.debut_race_win,
                    'clock_used': detail.clock_used,
                    'parse_factor_done': detail.parse_factor_done,
                    'manual_purchase_completed': getattr(detail, 'manual_purchase_completed', False),
                    'final_skill_sweep_active': getattr(detail, 'final_skill_sweep_active', False),
                    'user_provided_priority': getattr(detail, 'user_provided_priority', False),
                    'use_last_parents': getattr(detail, 'use_last_parents', False),
                    'pal_event_stage': getattr(detail, 'pal_event_stage', 0),
                    'pal_name': getattr(detail, 'pal_name', ''),
                    'mant_shop_items': getattr(detail, 'mant_shop_items', []),
                    'mant_shop_scanned_this_turn': getattr(detail, 'mant_shop_scanned_this_turn', False),
                    'mant_shop_last_chunk': getattr(detail, 'mant_shop_last_chunk', -1),
                    'mant_afflictions': getattr(detail, 'mant_afflictions', []),
                    'mant_coins': getattr(detail, 'mant_coins', 0),
                    'mant_inventory_scanned': getattr(detail, 'mant_inventory_scanned', False),
                    'mant_owned_items': getattr(detail, 'mant_owned_items', []),
                    'mant_max_energy': getattr(detail, 'mant_max_energy', 100),
                    'team_sirius_enabled': getattr(detail, 'team_sirius_enabled', False),
                    'team_sirius_percentile': getattr(detail, 'team_sirius_percentile', 26),
                    'team_sirius_available_dates': getattr(detail, 'team_sirius_available_dates', []),
                    'team_sirius_last_date': getattr(detail, 'team_sirius_last_date', -1),
                },
                'timestamp': time.time()
            }

            with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            log.info("Training checkpoint saved")
            return True
    except Exception as e:
        log.info(f"Failed to save checkpoint: {e}")
        return False


def load_checkpoint():
    """Load training checkpoint if exists"""
    try:
        if not os.path.exists(CHECKPOINT_FILE):
            return None

        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data.get('in_progress', False):
            return None

        log.info("Found training checkpoint")
        return data
    except Exception as e:
        log.info(f"Failed to load checkpoint: {e}")
        return None


def clear_checkpoint():
    """Clear checkpoint (training completed or abandoned)"""
    try:
        with checkpoint_lock:
            if os.path.exists(CHECKPOINT_FILE):
                with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'in_progress': False}, f)
                    f.flush()
                    os.fsync(f.fileno())
            log.info("Checkpoint cleared")
            return True
    except Exception as e:
        log.info(f"Failed to clear checkpoint: {e}")
        return False


def restore_checkpoint_to_context(ctx, checkpoint_data):
    """Restore checkpoint data to context"""
    try:
        from module.umamusume.types import TurnInfo, TrainingInfo, UmaAttribute, TurnOperation, SupportCardInfo
        from module.umamusume.define import (
            MotivationLevel, TurnOperationType, TrainingType,
            SupportCardType, SupportCardFavorLevel
        )

        detail = ctx.cultivate_detail
        state = checkpoint_data.get('state', {})

        def restore_turn_info(data):
            if not data:
                return TurnInfo()
            ti = TurnInfo()
            ti.date = data.get('date', -1)
            ti.parse_train_info_finish = data.get('parse_train_info_finish', False)
            ti.parse_main_menu_finish = data.get('parse_main_menu_finish', False)
            ti.remain_stamina = data.get('remain_stamina', -1)
            ti.motivation_level = MotivationLevel(data.get('motivation_level', 0))
            ti.medic_room_available = data.get('medic_room_available', False)
            ti.race_available = data.get('race_available', False)
            ti.turn_info_logged = data.get('turn_info_logged', False)
            ti.turn_learn_skill_done = data.get('turn_learn_skill_done', False)
            ti.aoharu_race_index = data.get('aoharu_race_index', 0)

            uma_attr_data = data.get('uma_attribute', {})
            ti.uma_attribute = UmaAttribute()
            ti.uma_attribute.speed = uma_attr_data.get('speed', 0)
            ti.uma_attribute.stamina = uma_attr_data.get('stamina', 0)
            ti.uma_attribute.power = uma_attr_data.get('power', 0)
            ti.uma_attribute.will = uma_attr_data.get('will', 0)
            ti.uma_attribute.intelligence = uma_attr_data.get('intelligence', 0)
            ti.uma_attribute.skill_point = uma_attr_data.get('skill_point', 0)

            training_list = []
            for train_data in data.get('training_info_list', []):
                train_info = TrainingInfo()
                train_info.speed_incr = train_data.get('speed_incr', 0)
                train_info.stamina_incr = train_data.get('stamina_incr', 0)
                train_info.power_incr = train_data.get('power_incr', 0)
                train_info.will_incr = train_data.get('will_incr', 0)
                train_info.intelligence_incr = train_data.get('intelligence_incr', 0)
                train_info.skill_point_incr = train_data.get('skill_point_incr', 0)
                train_info.failure_rate = train_data.get('failure_rate', -1)
                train_info.relevant_count = train_data.get('relevant_count', 0)
                training_list.append(train_info)
            ti.training_info_list = training_list

            turn_op_data = data.get('turn_operation')
            if turn_op_data:
                turn_op = TurnOperation()
                turn_op.turn_operation_type = TurnOperationType(turn_op_data.get('turn_operation_type', 0))
                turn_op.turn_operation_type_replace = TurnOperationType(turn_op_data.get('turn_operation_type_replace', 0))
                turn_op.training_type = TrainingType(turn_op_data.get('training_type', 0))
                turn_op.race_id = turn_op_data.get('race_id', 0)
                ti.turn_operation = turn_op

            return ti

        detail.turn_info = restore_turn_info(state.get('turn_info'))

        history = []
        for ti_data in state.get('turn_info_history', []):
            history.append(restore_turn_info(ti_data))
        detail.turn_info_history = history

        detail.learn_skill_done = state.get('learn_skill_done', False)
        detail.learn_skill_selected = state.get('learn_skill_selected', False)
        detail.debut_race_win = state.get('debut_race_win', False)
        detail.clock_used = state.get('clock_used', 0)
        detail.parse_factor_done = state.get('parse_factor_done', False)
        detail.manual_purchase_completed = state.get('manual_purchase_completed', False)
        detail.final_skill_sweep_active = state.get('final_skill_sweep_active', False)
        detail.user_provided_priority = state.get('user_provided_priority', False)
        detail.use_last_parents = state.get('use_last_parents', False)
        detail.pal_event_stage = state.get('pal_event_stage', 0)
        detail.pal_name = state.get('pal_name', '')
        detail.mant_shop_items = state.get('mant_shop_items', [])
        detail.mant_shop_scanned_this_turn = state.get('mant_shop_scanned_this_turn', False)
        detail.mant_shop_last_chunk = state.get('mant_shop_last_chunk', -1)
        detail.mant_afflictions = state.get('mant_afflictions', [])
        detail.mant_coins = state.get('mant_coins', 0)
        detail.mant_inventory_scanned = state.get('mant_inventory_scanned', False)
        detail.mant_owned_items = state.get('mant_owned_items', [])
        detail.mant_max_energy = state.get('mant_max_energy', 100)
        detail.team_sirius_enabled = state.get('team_sirius_enabled', False)
        detail.team_sirius_percentile = state.get('team_sirius_percentile', 26)
        detail.team_sirius_available_dates = state.get('team_sirius_available_dates', [])
        detail.team_sirius_last_date = state.get('team_sirius_last_date', -1)

        log.info(f"Restored checkpoint state: Turn {detail.turn_info.date}")
        return True
    except Exception as e:
        log.info(f"Failed to restore checkpoint: {e}")
        return False
