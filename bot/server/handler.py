import os
import time
import json
import re
from typing import Dict, Any
import subprocess

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware

from bot.base.log import task_log_handler
from bot.engine import ctrl as bot_ctrl
from starlette.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Union
from bot.base.task import TaskExecuteMode


class AddTaskRequest(BaseModel):
    app_name: str
    task_execute_mode: int
    task_type: int
    task_desc: str
    attachment_data: Any = None
    cron_job_config: Optional[Any] = None

    class Config:
        extra = "allow"


class DeleteTaskRequest(BaseModel):
    task_id: str


class UpdateTaskRequest(BaseModel):
    task_id: Union[str, int]
    attachment_data: Any


class ResetTaskRequest(BaseModel):
    task_id: str


class SafeJSONResponse(JSONResponse):
    _surrogate_re = re.compile(r"[\ud800-\udfff]")

    @classmethod
    def _sanitize(cls, obj):
        if isinstance(obj, str):
            return cls._surrogate_re.sub("\ufffd", obj)
        if isinstance(obj, list):
            return [cls._sanitize(x) for x in obj]
        if isinstance(obj, dict):
            return {k: cls._sanitize(v) for k, v in obj.items()}
        return obj

    def render(self, content) -> bytes:
        safe_content = self._sanitize(content)
        return json.dumps(
            safe_content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


server = FastAPI(default_response_class=SafeJSONResponse)

server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for manual skill notifications
manual_skill_notification_state = {
    "show": False,
    "message": "",
    "timestamp": 0,
    "confirmed": False,
    "cancelled": False
}

@server.post("/api/manual-skill-notification")
def manual_skill_notification(notification_data: Dict[str, Any]):
    """Receive manual skill purchase notification from bot"""
    global manual_skill_notification_state
    manual_skill_notification_state.update({
        "show": True,
        "message": notification_data.get("message", ""),
        "timestamp": notification_data.get("timestamp", time.time()),
        "confirmed": False,
        "cancelled": False
    })
    return {"status": "success"}

@server.get("/api/manual-skill-notification-status")
def get_manual_skill_notification_status():
    """Get current notification status for frontend polling"""
    global manual_skill_notification_state
    return manual_skill_notification_state

@server.post("/api/manual-skill-notification-confirm")
def confirm_manual_skill_notification():
    """Confirm manual skill purchase completion"""
    global manual_skill_notification_state
    manual_skill_notification_state.update({
        "show": False,
        "confirmed": True,
        "cancelled": False
    })
    return {"status": "confirmed"}

@server.post("/api/manual-skill-notification-cancel")
def cancel_manual_skill_notification():
    """Cancel manual skill purchase"""
    global manual_skill_notification_state
    manual_skill_notification_state.update({
        "show": False,
        "confirmed": False,
        "cancelled": True
    })
    return {"status": "cancelled"}


@server.post("/task")
def add_task(req: Dict[str, Any] = Body(...)):
    bot_ctrl.add_task(
        req.get("app_name"),
        int(req.get("task_execute_mode", 1)),
        int(req.get("task_type", 0)),
        req.get("task_desc", ""),
        req.get("cron_job_config"),
        req.get("attachment_data") or {},
    )


@server.delete("/task")
def delete_task(req: DeleteTaskRequest = Body(...)):
    bot_ctrl.delete_task(req.task_id)


@server.put("/task")
def update_task(req: Dict[str, Any] = Body(...)):
    from fastapi import HTTPException
    from bot.engine.scheduler import scheduler

    task_id = req.get("task_id")
    attachment_data = req.get("attachment_data")

    # Bundled frontend may PUT the full task payload (like POST) instead of
    # {task_id, attachment_data}. In that case, find the running task by app_name
    # + task_type and update its attachment_data in place.
    if attachment_data is None and "app_name" in req:
        attachment_data = {k: v for k, v in req.items()
                           if k not in ("app_name", "task_execute_mode", "task_type",
                                        "task_desc", "cron_job_config", "task_id")}
        # If a dedicated attachment_data key wasn't present, the rest of the body IS it.
        if not attachment_data:
            attachment_data = req

    if task_id is None:
        app_name = req.get("app_name")
        task_type = req.get("task_type")
        for t in scheduler.get_task_list():
            if getattr(t, "app_name", None) == app_name and \
               getattr(getattr(t, "task_type", None), "value", None) == task_type:
                task_id = t.task_id
                break

    if task_id is None:
        raise HTTPException(status_code=404, detail="Task not found (no task_id)")

    success = bot_ctrl.update_task(str(task_id), attachment_data or {})
    if success:
        return {"status": "updated"}
    else:
        raise HTTPException(status_code=404, detail="Task not found")


@server.get("/task")
def get_task():
    return bot_ctrl.get_task_list()


class RuntimeThresholds(BaseModel):
    repetitive_threshold: Optional[int] = None
    watchdog_threshold: Optional[int] = None


@server.get("/api/runtime-state")
def get_runtime_state():
    try:
        from bot.base.runtime_state import get_state
        return get_state()
    except Exception:
        return {
            "repetitive_count": 0,
            "repetitive_other_clicks": 0,
            "repetitive_threshold": 11,
            "watchdog_unchanged": 0,
            "watchdog_threshold": 3,
        }


@server.post("/api/runtime-thresholds")
def set_runtime_thresholds(req: RuntimeThresholds):
    try:
        from bot.base.runtime_state import set_thresholds, save_persisted
        set_thresholds(req.repetitive_threshold, req.watchdog_threshold)
        save_persisted()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@server.get("/api/discord-config")
def get_discord_config_endpoint():
    try:
        from module.umamusume.persistence import get_discord_config
        return get_discord_config()
    except Exception as e:
        return {"webhook_url": "", "user_id": "", "error": str(e)}


@server.post("/api/discord-config")
def set_discord_config_endpoint(req: Dict[str, Any] = Body(...)):
    try:
        from module.umamusume.persistence import set_discord_config
        webhook_url = (req.get("webhook_url") or "").strip()
        user_id = (req.get("user_id") or "").strip()
        set_discord_config(webhook_url=webhook_url, user_id=user_id)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@server.post("/api/discord-test")
def test_discord_webhook():
    try:
        from module.umamusume import discord_notify
        discord_notify.send_message("Umamusume Sweepy: webhook connected ✅")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@server.get("/api/update-status")
def get_update_status():
    try:
        repo_root = None
        base = os.path.abspath(os.path.dirname(__file__))
        for _ in range(8):
            if os.path.isdir(os.path.join(base, '.git')):
                repo_root = base
                break
            parent = os.path.dirname(base)
            if parent == base:
                break
            base = parent
        if repo_root is None:
            tl = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=os.getcwd(), timeout=5)
            if tl.returncode == 0 and os.path.isdir(tl.stdout.strip()):
                repo_root = tl.stdout.strip()
            else:
                return {"has_update": False, "error": "git repo not found from server path"}
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, cwd=repo_root, timeout=5)
        if branch.returncode != 0:
            return {"has_update": False, "error": branch.stderr.strip()}
        branch_name = branch.stdout.strip()
        upstream = subprocess.run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], capture_output=True, text=True, cwd=repo_root, timeout=5)
        if upstream.returncode == 0:
            upstream_ref = upstream.stdout.strip()
            remote_name = upstream_ref.split('/')[0]
            subprocess.run(["git", "fetch", "--quiet", remote_name], capture_output=True, text=True, cwd=repo_root, timeout=10)
            revspec = f"HEAD...{upstream_ref}"
        else:
            remote_name = "origin"
            subprocess.run(["git", "fetch", "--quiet", remote_name], capture_output=True, text=True, cwd=repo_root, timeout=10)
            revspec = f"HEAD...{remote_name}/{branch_name}"
        cmp = subprocess.run(["git", "rev-list", "--left-right", "--count", revspec], capture_output=True, text=True, cwd=repo_root, timeout=5)
        if cmp.returncode != 0:
            return {"has_update": False, "error": cmp.stderr.strip(), "branch": branch_name}
        parts = cmp.stdout.strip().split()
        ahead = int(parts[0]) if len(parts) > 0 else 0
        behind = int(parts[1]) if len(parts) > 1 else 0
        head_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root, timeout=5)
        remote_sha = subprocess.run(["git", "rev-parse", revspec.split('...')[1]], capture_output=True, text=True, cwd=repo_root, timeout=5)
        preset_redo = False
        if behind > 0:
            log_cmd = subprocess.run(["git", "log", "--oneline", f"HEAD..{revspec.split('...')[1]}"], capture_output=True, text=True, cwd=repo_root, timeout=10)
            if log_cmd.returncode == 0 and "(TR)" in log_cmd.stdout:
                preset_redo = True
        return {
            "has_update": bool(behind > 0),
            "preset_redo": preset_redo,
            "branch": branch_name,
            "upstream": revspec.split('...')[1],
            "ahead": ahead,
            "behind": behind,
            "head": head_sha.stdout.strip() if head_sha.returncode == 0 else "",
            "remote": remote_sha.stdout.strip() if remote_sha.returncode == 0 else ""
        }
    except Exception as e:
        return {"has_update": False, "error": str(e)}

@server.get("/log/{task_id}")
def get_task_log(task_id):
    return task_log_handler.get_task_log(task_id)


@server.post("/action/bot/reset-task")
def reset_task(req: ResetTaskRequest):
    bot_ctrl.reset_task(req.task_id)


@server.post("/action/bot/start")
def start_bot():
    bot_ctrl.start()


@server.post("/action/bot/stop")
def stop_bot():
    bot_ctrl.stop()


@server.get("/action/bot/status")
def get_bot_status():
    from bot.engine.scheduler import scheduler
    if scheduler.active:
        running_tasks = [t for t in scheduler.task_list 
                        if t.task_status.value == 2] 
        if running_tasks:
            return {"status": "running"}
        return {"status": "active"}
    return {"status": "idle"}


@server.get("/api/detected-skills")
def get_detected_skills():
    from module.umamusume.context import detected_skills_log
    return list(detected_skills_log.values())


@server.get("/api/detected-portraits")
def get_detected_portraits():
    from module.umamusume.context import detected_portraits_log
    return list(detected_portraits_log.values())


@server.get("/api/detected-items")
def get_detected_items():
    from module.umamusume.context import detected_items_log
    return list(detected_items_log.values())


@server.get("/api/detected-shop-items")
def get_detected_shop_items():
    from module.umamusume.context import detected_shop_items_log
    return list(detected_shop_items_log.values())


@server.post("/api/clear-career-data")
def clear_career_data_endpoint():
    from module.umamusume.persistence import clear_career_data
    cleared = clear_career_data()
    return {"cleared": cleared}


@server.get("/api/pal-defaults")
def get_pal_defaults():
    from module.umamusume.user_data import read_pal_defaults
    return read_pal_defaults()


@server.get("/api/training-characters")
def get_training_characters():
    icons_dir = os.path.join("resource", "umamusume", "trainingIcons")
    if not os.path.isdir(icons_dir):
        return []
    names = []
    for f in sorted(os.listdir(icons_dir)):
        if f.lower().endswith(".png"):
            names.append(f[:-4])
    return names


@server.get("/training-icon/{name:path}")
async def get_training_icon(name: str):
    file_path = os.path.join("resource", "umamusume", "trainingIcons", name + ".png")
    if os.path.isfile(file_path):
        return FileResponse(file_path, media_type="image/png")
    return JSONResponse(status_code=404, content={"error": "not found"})



@server.get("/race-icon/{race_id}")
async def get_race_icon(race_id: str):
    file_path = os.path.join("resource", "umamusume", "race", race_id + ".png")
    if os.path.isfile(file_path):
        return FileResponse(file_path, media_type="image/png")
    return JSONResponse(status_code=404, content={"error": "not found"})


@server.get("/")
async def get_index():
    return FileResponse('public/index.html', headers={
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    })


@server.get("/{whatever:path}")
async def get_static_files_or_404(whatever):
    # try open file for path
    file_path = os.path.join("public", whatever)
    # 设置防缓存头
    no_cache_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    if os.path.isfile(file_path):
        if file_path.endswith((".js", ".mjs")):
            return FileResponse(file_path, media_type="application/javascript", headers=no_cache_headers)
        else:
            return FileResponse(file_path, headers=no_cache_headers)
    return FileResponse('public/index.html', headers=no_cache_headers)
