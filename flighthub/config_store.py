import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PATH = os.path.join(_ROOT, "config", "config.json")
_PATH = os.environ.get("FLIGHTHUB_CONFIG", _DEFAULT_PATH)

DEFAULTS = {
    "setup": {"completed": False, "version": 1},
    "brand": {
        "name": "Flight Hub",
        "footer": "Flight Hub",
        "airline": "Airline",
        "tail_emoji": "",
    },
    "guilds": {"staff": None, "customer": None, "log": None},
    "channels": {},
    "roles": {},
    "colors": {
        "primary": 0x1B3444,
        "private": 0x808080,
        "success": 0x2ECC71,
        "warning": 0xF1C40F,
        "danger": 0xE74C3C,
        "info": 0x3498DB,
    },
    "emojis": {},
    "templates": {},
    "options": {"timezone": "Asia/Tokyo"},
}

CORE_BINDINGS = [
    ("guilds.staff", "STAFF_GUILD_ID"),
    ("guilds.customer", "CUSTOMER_GUILD_ID"),
    ("guilds.log", "LOG_GUILD_ID"),
    ("channels.staff_announce", "STAFF_CHANNEL_ID"),
    ("channels.customer_announce", "CUSTOMER_CHANNEL_ID"),
    ("channels.flight_input", "FLIGHT_INPUT_CHANNEL_ID"),
    ("channels.flight_log", "FLIGHT_LOG_CHANNEL_ID"),
    ("channels.briefing", "BRIEFING_CHANNEL_ID"),
    ("channels.remind_track", "REMIND_TRACK_CHANNEL_ID"),
    ("channels.command", "COMMAND_CHANNEL_ID"),
    ("channels.reflection", "REFLECTION_CHANNEL_ID"),
    ("channels.flight_app", "FLIGHT_APP_CHANNEL_ID"),
    ("channels.eval_track", "EVAL_TRACK_CHANNEL_ID"),
    ("channels.audit_log", "AUDIT_LOG_CHANNEL_ID"),
    ("channels.loa_track", "LOA_TRACK_CHANNEL_ID"),
    ("channels.misc_data", "MISC_DATA_CHANNEL_ID"),
    ("channels.flight_log_history", "FLIGHT_LOG_HISTORY_CHANNEL_ID"),
    ("channels.manual_log", "MANUAL_LOG_CHANNEL_ID"),
    ("channels.test_briefing_category", "TEST_BRIEFING_CATEGORY_ID"),
    ("channels.flight_channel_category", "FLIGHT_CHANNEL_CATEGORY_ID"),
    ("channels.flight_chat_archive", "FLIGHT_CHAT_ARCHIVE_CHANNEL_ID"),
    ("channels.test_json", "TEST_JSON_CHANNEL_ID"),
    ("channels.test_customer_category", "TEST_CUSTOMER_CATEGORY_ID"),
    ("channels.test_staff", "TEST_STAFF_CHANNEL_ID"),
    ("channels.selftest_customer_category", "SELFTEST_CUSTOMER_CATEGORY_ID"),
    ("roles.allowed", "ALLOWED_ROLE_ID"),
    ("roles.notification", "NOTIFICATION_ROLE_ID"),
    ("roles.join_notification", "JOIN_NOTIFICATION_ROLE_ID"),
    ("roles.dm_target", "DM_TARGET_ROLE_ID"),
    ("roles.dm_staff", "DM_STAFF_ROLE_ID"),
    ("roles.dm_exclude", "DM_EXCLUDE_ROLE_ID"),
    ("roles.event_manager", "ROLE_EVENT_MANAGERS"),
    ("roles.ground_ops", "ROLE_GROUND_OPS"),
    ("roles.cabin_crew", "ROLE_CABIN_CREWS"),
    ("roles.flight_ops", "ROLE_FLIGHT_OPS"),
    ("roles.exclude_remind", "EXCLUDE_REMIND_ROLE_ID"),
    ("roles.exclude_remind_2", "EXCLUDE_REMIND_ROLE_ID_2"),
    ("roles.chief", "CHIEF_ROLE_ID"),
    ("roles.flight_verifier", "FLIGHT_VERIFIER_ROLE_ID"),
    ("roles.loa", "LOA_ROLE_ID"),
    ("roles.profile_export", "LOG_COPY_ROLE_ID"),
]


def _deep_merge(base, override):
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load():
    data = {}
    if _PATH and os.path.isfile(_PATH):
        try:
            with open(_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle) or {}
        except (OSError, ValueError):
            data = {}
    return _deep_merge(DEFAULTS, data)


CONFIG = load()


def cfg(path, default=None):
    node = CONFIG
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return default if node is None else node


def set_value(path, value):
    parts = path.split(".")
    node = CONFIG
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value
    return value


def save():
    directory = os.path.dirname(_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as handle:
        json.dump(CONFIG, handle, ensure_ascii=False, indent=2)


def reload():
    global CONFIG
    CONFIG = load()
    return CONFIG


def config_path():
    return _PATH


def is_configured():
    return bool(cfg("setup.completed")) and bool(cfg("guilds.staff"))


def apply_to_core(core_module):
    applied = []
    for path, attr in CORE_BINDINGS:
        value = cfg(path)
        if value is not None:
            setattr(core_module, attr, value)
            applied.append(attr)
    return applied


def summary_lines():
    lines = []
    for group in ("guilds", "channels", "roles"):
        values = CONFIG.get(group, {})
        set_count = sum(1 for v in values.values() if v)
        lines.append(f"**{group}**: {set_count}/{len(values)} configured")
    return lines


UI_SECTIONS = ("brand", "colors", "emojis", "templates")


def export_ui_settings():
    return {section: dict(CONFIG.get(section, {}) or {}) for section in UI_SECTIONS}


def import_ui_settings(data):
    if not isinstance(data, dict):
        return False
    changed = False
    for section in UI_SECTIONS:
        values = data.get(section)
        if isinstance(values, dict) and values:
            CONFIG[section] = _deep_merge(CONFIG.get(section, {}), values)
            changed = True
    return changed


def reset_ui_settings():
    for section in UI_SECTIONS:
        CONFIG[section] = dict(DEFAULTS.get(section, {}) or {})
