import sys
import threading
import subprocess
import os
import yaml
import time
import random
import datetime

import torch

import cv2
import bot.base.log as logger
import bot.base.gpu_utils as gpu_utils

try:
    cores = str(os.cpu_count() or 1)
    os.environ.setdefault("MKL_NUM_THREADS", cores)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", cores)
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", cores)
    cv2.setUseOptimized(True)
    cv2.setNumThreads(int(cores))
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:
        pass
    try:
        os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    except Exception:
        pass
except Exception:
    pass

from bot.base.task import TaskStatus
import bot.conn.u2_ctrl as u2_ctrl
from bot.base.manifest import register_app
from bot.engine.scheduler import scheduler
from module.umamusume.manifest import UmamusumeManifest
from uvicorn import run

log = logger.get_logger(__name__)
_gpu_available = gpu_utils.detect_gpu_capabilities()
_opencv_gpu = gpu_utils.configure_opencv_gpu()

start_time = 0
end_time = 24
KEEPALIVE_ACTIVE = True
DAILY_WAIT_OFFSET = random.randint(16, 188)
DAILY_OFFSET_DAY = datetime.date.today()

def _get_adb_path():
    return os.path.join("deps", "adb", "adb.exe")

def _run_adb(args, timeout=15):
    adb_path = _get_adb_path()
    return subprocess.run([adb_path] + args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)

def restart_adb_server():
    try:
        _run_adb(["kill-server"], timeout=10)
        time.sleep(1)
    except Exception:
        pass
    try:
        result = _run_adb(["start-server"], timeout=15)
        time.sleep(2)
        return result.returncode == 0
    except Exception:
        return False

def check_adb_server_status():
    try:
        result = _run_adb(["version"], timeout=5)
        return result.returncode == 0
    except Exception:
        return False

def get_adb_devices():
    try:
        result = _run_adb(["devices"], timeout=10)
        if result.returncode != 0:
            return []
        devices = []
        lines = result.stdout.strip().split('\n')[1:]
        for line in lines:
            if line.strip() and '\t' in line:
                device_id, status = line.split('\t')
                if status == 'device' or status == 'offline':
                    devices.append(device_id)
        return devices
    except Exception:
        return []

def select_device():
    devices = get_adb_devices()
    if not devices:
        return None
    if len(devices) == 1:
        return devices[0]
    while True:
        try:
            choice = input(f"\nSelect device (1-{len(devices)}): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= len(devices):
                return devices[choice_num - 1]
        except (ValueError, KeyboardInterrupt):
            return None

def update_config(device_name):
    try:
        with open("config.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        config['bot']['auto']['adb']['device_name'] = device_name
        with open("config.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        return True
    except Exception:
        return False

def uninstall_uiautomator(device_id):
    packages = [
        "com.github.uiautomator",
        "com.github.uiautomator.test",
        "com.github.uiautomator.agent",
        "com.github.uiautomator.server"
    ]
    for pkg in packages:
        try:
            _run_adb(["-s", device_id, "uninstall", pkg], timeout=10)
        except Exception:
            pass

def connect_to_device(device_id, max_retries=3):
    print(f"Connecting to {device_id}...")
    
    for attempt in range(1, max_retries + 1):
        if not check_adb_server_status() and attempt > 1:
            restart_adb_server()
        
        if ":" in device_id:
            try:
                result = _run_adb(["connect", device_id], timeout=10)
                if "connected" not in result.stdout.lower() and "already connected" not in result.stdout.lower():
                    if attempt < max_retries:
                        restart_adb_server()
                        continue
            except subprocess.TimeoutExpired:
                if attempt < max_retries:
                    restart_adb_server()
                    continue
            except Exception:
                pass
        
        devices = get_adb_devices()
        if device_id not in devices:
            if attempt < max_retries:
                restart_adb_server()
                time.sleep(2)
                continue
            return False
        
        try:
            result = _run_adb(["-s", device_id, "shell", "echo", "test"], timeout=15)
            if result.returncode == 0 and "test" in result.stdout:
                print(f"Connected to {device_id}")
                return True
        except Exception:
            pass
        
        if attempt < max_retries:
            if attempt >= 1:
                restart_adb_server()
            if ":" in device_id and attempt >= 2:
                try:
                    _run_adb(["disconnect", device_id], timeout=5)
                    time.sleep(1)
                except Exception:
                    pass
            time.sleep(attempt * 2)
    
    print(f"Failed to connect to {device_id}")
    return False

def run_health_checks(device_id):
    try:
        _run_adb(["-s", device_id, "exec-out", "screencap", "-p"], timeout=15)
        _run_adb(["-s", device_id, "shell", "input", "keyevent", "0"], timeout=10)
        return True
    except Exception:
        return True

def normalize_start_end():
    global start_time, end_time
    try:
        start_time = max(0.0, min(24.0, float(start_time)))
        end_time = max(0.0, min(24.0, float(end_time)))
    except Exception:
        start_time, end_time = 0.0, 24.0

def is_in_allowed_window(now: datetime.datetime) -> bool:
    s, e = start_time, end_time
    h = now.hour + (now.minute / 60.0) + (now.second / 3600.0)
    if s == e:
        return True
    if s < e:
        return s <= h < e
    else:
        return h >= s or h < e

def next_window_start(now: datetime.datetime) -> datetime.datetime:
    s, e = start_time, end_time
    today = now.date()
    if s == e:
        return now

    sh = int(s)
    sm = int(round((s - sh) * 60))
    if sm == 60:
        sh += 1
        sm = 0
    if sh >= 24:
        sh = 0
        sm = 0

    start_today = datetime.datetime.combine(today, datetime.time(hour=sh, minute=sm))

    if s < e:
        if now < start_today:
            return start_today
        else:
            return start_today + datetime.timedelta(days=1)
    else:
        if now < start_today:
            return start_today
        else:
            return start_today + datetime.timedelta(days=1)

def refresh_daily_offset():
    global DAILY_WAIT_OFFSET, DAILY_OFFSET_DAY
    today = datetime.date.today()
    if today != DAILY_OFFSET_DAY:
        DAILY_WAIT_OFFSET = random.randint(16, 188)
        DAILY_OFFSET_DAY = today

def time_window_enforcer(device_id: str):
    global KEEPALIVE_ACTIVE
    paused = False
    paused_task_ids = set()
    
    while True:
        refresh_daily_offset()
        now = datetime.datetime.now()
        
        if is_in_allowed_window(now):
            if paused:
                time.sleep(random.randint(16, 188))
                u2_ctrl.INPUT_BLOCKED = False
                KEEPALIVE_ACTIVE = True
                for tid in list(paused_task_ids):
                    if not str(tid).startswith("CRONJOB_"):
                        try:
                            scheduler.reset_task(tid)
                        except Exception:
                            pass
                scheduler.start()
                paused = False
                paused_task_ids.clear()
        else:
            if not paused:
                time.sleep(random.randint(16, 188))
                try:
                    running = [t.task_id for t in scheduler.get_task_list() 
                              if t.task_status == TaskStatus.TASK_STATUS_RUNNING]
                except Exception:
                    running = []
                paused_task_ids = set(running)
                scheduler.stop()
                try:
                    from bot.base.purge import save_scheduler_tasks, save_scheduler_state
                    save_scheduler_tasks()
                    save_scheduler_state()
                except Exception:
                    pass
                u2_ctrl.INPUT_BLOCKED = True
                KEEPALIVE_ACTIVE = False
                try:
                    _run_adb(["-s", device_id, "shell", "am", "force-stop", 
                             "com.cygames.umamusume"], timeout=5)
                except Exception:
                    pass
                paused = True
            
            next_start = next_window_start(now)
            total_sec = int((next_start - now).total_seconds()) + int(DAILY_WAIT_OFFSET)
            if total_sec < 0:
                total_sec = 0
            print(f"Time until next run: {total_sec}s")
        
        time.sleep(60)

if __name__ == '__main__':
    try:
        from bot.base.purge import acquire_instance_lock
        acquire_instance_lock()
    except Exception:
        pass

    selected_device = None
    if os.environ.get("UAT_AUTORESTART", "0") == "1":
        try:
            with open("config.yaml", 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            selected_device = cfg['bot']['auto']['adb']['device_name']
            if not selected_device:
                selected_device = select_device()
        except Exception:
            selected_device = select_device()
    else:
        selected_device = select_device()
    
    if selected_device is None:
        print("No device selected")
        sys.exit(1)
    
    if not connect_to_device(selected_device, max_retries=3):
        print("Connection failed")
        sys.exit(1)
    
    uninstall_uiautomator(selected_device)
    
    if not run_health_checks(selected_device):
        print("Health checks failed")
        sys.exit(1)
    
    if not update_config(selected_device):
        print("Config update failed")
        sys.exit(1)
    
    normalize_start_end()
    
    enforcer_thread = threading.Thread(target=time_window_enforcer, 
                                       args=(selected_device,), daemon=True)
    enforcer_thread.start()
    
    from bake_templates import bake, BAKED_PATH
    if not BAKED_PATH.exists():
        print("Baking character templates...")
        bake()

    from module.umamusume.script.cultivate_task.event.manifest import warmup_event_index
    warmup_event_index()
    
    from bot.recog.image_matcher import preload_templates, init_executor
    preload_templates('resource')
    init_executor()
    
    register_app(UmamusumeManifest)
    
    restored = False
    was_active = None
    try:
        from bot.base.purge import load_saved_tasks, load_scheduler_state
        restored = load_saved_tasks()
        was_active = load_scheduler_state()
    except Exception:
        pass

    checkpoint_found = False
    try:
        from module.umamusume.persistence import load_checkpoint
        checkpoint_data = load_checkpoint()
        if checkpoint_data:
            checkpoint_found = True
            print("=" * 60)
            print("CHECKPOINT DETECTED - Resuming interrupted training")
            print("=" * 60)

            if not restored:
                print("No saved task found, creating task from checkpoint...")
                try:
                    import bot.engine.ctrl as ctrl
                    from bot.base.task import TaskExecuteMode
                    from module.umamusume.task import UmamusumeTaskType

                    task_config = checkpoint_data.get('task_config', {})
                    scenario_type = checkpoint_data.get('scenario_type', 1)

                    # Prefer the raw attachment captured at checkpoint time — it
                    # preserves mant_config/item_tiers and every other user field.
                    full_attachment = checkpoint_data.get('full_attachment_data')
                    if isinstance(full_attachment, dict) and full_attachment:
                        attachment_data = dict(full_attachment)
                        if 'scenario' not in attachment_data:
                            attachment_data['scenario'] = scenario_type
                    else:
                        attachment_data = {
                        'scenario': scenario_type,
                        'expect_attribute': task_config.get('expect_attribute'),
                        'follow_support_card_name': task_config.get('follow_support_card_name', ''),
                        'follow_support_card_level': task_config.get('follow_support_card_level', 0),
                        'extra_race_list': task_config.get('extra_race_list', []),
                        'learn_skill_list': task_config.get('learn_skill_list', []),
                        'learn_skill_blacklist': task_config.get('learn_skill_blacklist', []),
                        'tactic_list': task_config.get('tactic_list', []),
                        'tactic_actions': task_config.get('tactic_actions', []),
                        'clock_use_limit': task_config.get('clock_use_limit', 0),
                        'learn_skill_threshold': task_config.get('learn_skill_threshold', 180),
                        'learn_skill_only_user_provided': task_config.get('learn_skill_only_user_provided', False),
                        'allow_recover_tp': task_config.get('allow_recover_tp', False),
                        'extra_weight': task_config.get('extra_weight', []),
                        'manual_purchase_at_end': task_config.get('manual_purchase_at_end', False),
                        'override_insufficient_fans_forced_races': task_config.get('override_insufficient_fans_forced_races', False),
                        'use_last_parents': task_config.get('use_last_parents', False),
                        'rest_threshold': task_config.get('rest_threshold', 48),
                        'motivation_threshold_year1': task_config.get('motivation_threshold_year1', 3),
                        'motivation_threshold_year2': task_config.get('motivation_threshold_year2', 4),
                        'motivation_threshold_year3': task_config.get('motivation_threshold_year3', 4),
                        'skip_training_on_race_day': task_config.get('skip_training_on_race_day', False),
                        'prioritize_recreation': task_config.get('prioritize_recreation', False),
                        'pal_name': task_config.get('pal_name', ''),
                        'pal_thresholds': task_config.get('pal_thresholds', []),
                        'spirit_explosion': task_config.get('spirit_explosion', [0.16, 0.16, 0.16, 0.06, 0.11]),
                    }

                    ctrl.add_task(
                        'umamusume',
                        TaskExecuteMode.TASK_EXECUTE_MODE_ONE_TIME,
                        UmamusumeTaskType.UMAMUSUME_TASK_TYPE_CULTIVATE.value,
                        'Resumed Training',
                        None,
                        attachment_data
                    )
                    restored = True
                    print("Task created from checkpoint")
                except Exception as e:
                    print(f"Failed to create task from checkpoint: {e}")
    except Exception as e:
        print(f"Checkpoint check failed: {e}")

    scheduler_thread = threading.Thread(target=scheduler.init, args=())
    scheduler_thread.start()

    try:
        if checkpoint_found or was_active is True or (was_active is None and restored):
            scheduler.start()
    except Exception:
        pass
    
    print("UAT running on http://127.0.0.1:8071")

    def _ensure_port_free(host, port, timeout=30):
        import socket
        deadline = time.time() + timeout
        while time.time() < deadline:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((host, port))
                s.close()
                return True
            except OSError:
                s.close()
                # Try to kill whoever is holding the port (Windows).
                try:
                    import subprocess
                    out = subprocess.check_output(
                        ["netstat", "-ano", "-p", "TCP"], text=True, stderr=subprocess.DEVNULL
                    )
                    for line in out.splitlines():
                        if f":{port} " in line and "LISTENING" in line:
                            parts = line.split()
                            pid = parts[-1]
                            if pid.isdigit() and int(pid) != os.getpid():
                                subprocess.run(["taskkill", "/F", "/PID", pid],
                                               stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
                                print(f"Killed stale process {pid} holding port {port}")
                except Exception:
                    pass
                time.sleep(1)
        return False

    if os.environ.get("UAT_AUTORESTART", "0") == "1":
        for attempt in range(10):
            _ensure_port_free("127.0.0.1", 8071)
            try:
                run("bot.server.handler:server", host="127.0.0.1", port=8071, log_level="error")
                break
            except OSError as e:
                if "10048" in str(e) and attempt < 9:
                    time.sleep(1)
                else:
                    raise
    else:
        threading.Thread(target=lambda: (time.sleep(1), __import__('webbrowser').open("http://127.0.0.1:8071")), daemon=True).start()
        try:
            run("bot.server.handler:server", host="127.0.0.1", port=8071, log_level="error")
        finally:
            if ":" in selected_device:
                try:
                    _run_adb(["disconnect", selected_device], timeout=5)
                except Exception:
                    pass