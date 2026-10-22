import copy
import json
import os
import re

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


COLOR_KEYS = ("primary", "private", "success", "warning", "danger", "info")

COLOR_LABELS = {
    "primary": "Primary (main embeds, dark blue)",
    "private": "Private flight",
    "success": "Success",
    "warning": "Warning",
    "danger": "Danger",
    "info": "Info",
}

DEFAULT_EMOJI_STRINGS = {
    "check": "\u2705",
    "x": "\u274c",
    "noti": "\U0001f514",
    "info": "\u2139\ufe0f",
    "search": "\U0001f50d",
    "baggage": "\U0001f9f3",
    "tail": "\u2708\ufe0f",
    "link": "\U0001f517",
    "brand": "\u2708\ufe0f",
}

DEFAULT_SIGNUP_TYPE_ICONS = {
    "flight": "\u2708\ufe0f",
    "custom": "\U0001f6e0\ufe0f",
    "test": "\U0001f9ea",
    "recurring": "\U0001f501",
    "private": "\U0001f512",
    "gamenight": "\U0001f3ae",
}

DEFAULT_FLIGHT_APPROVED = "\u2705"

EMOJI_LABELS = {
    "check": "Check mark",
    "x": "Cross mark",
    "noti": "Notification bell",
    "info": "Info",
    "search": "Search",
    "baggage": "Baggage",
    "tail": "Tail (announcement)",
    "link": "Link",
    "brand": "Brand",
    "flight_approved": "Flight approved (custom emoji)",
}

SIGNUP_TYPE_LABELS = {
    "flight": "Recruitment: regular flight",
    "custom": "Recruitment: custom flight",
    "test": "Recruitment: test flight",
    "recurring": "Recruitment: recurring flight",
    "private": "Recruitment: private flight",
    "gamenight": "Recruitment: game night",
}

EMOJI_CORE_ATTRS = {
    "check": "EMOJI_CHECK_STR",
    "x": "EMOJI_X_STR",
    "noti": "EMOJI_NOTI_STR",
    "info": "EMOJI_INFO_STR",
    "search": "EMOJI_SEARCH_STR",
    "baggage": "EMOJI_BAGGAGE_STR",
    "tail": "EMOJI_TAIL_STR",
    "link": "EMOJI_LINK_STR",
    "brand": "EMOJI_BRAND_STR",
}

COLOR_CORE_ATTRS = {
    "primary": "EMBED_COLOR",
    "private": "PRIVATE_FLIGHT_COLOR",
}

_CUSTOM_EMOJI_RE = re.compile(r"^<(a?):([^<>:\s]{1,32}):(\d{17,20})>$")


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
    return _deep_merge(copy.deepcopy(DEFAULTS), data)


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



def parse_hex_color(text):
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw[:2].lower() == "0x":
        raw = raw[2:]
    raw = raw.lstrip("#")
    if len(raw) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in raw):
        return None
    return int(raw, 16)


def format_hex_color(value):
    try:
        return "#%06X" % (int(value) & 0xFFFFFF)
    except (TypeError, ValueError):
        return "#------"


def parse_emoji_value(text, as_id=False):
    raw = str(text or "").strip()
    if not raw:
        return None, None
    match = _CUSTOM_EMOJI_RE.match(raw)
    if match:
        return (int(match.group(3)), None) if as_id else (raw, None)
    if as_id:
        if raw.isdigit():
            return int(raw), None
        return None, "Paste a custom emoji (`<:name:id>`) or its numeric id."
    if len(raw) > 64:
        return None, "That value is too long (64 characters max)."
    if any(ord(ch) < 0x80 for ch in raw):
        return None, "Paste an emoji (Unicode or `<:name:id>`), not plain text."
    return raw, None


def current_emoji(key):
    if key == "flight_approved":
        emoji_id = cfg("emojis.flight_approved")
        return f"<:ch:{emoji_id}>" if emoji_id else DEFAULT_FLIGHT_APPROVED
    return cfg(f"emojis.{key}") or DEFAULT_EMOJI_STRINGS.get(key, "")


def current_signup_icon(key):
    icons = dict(DEFAULT_SIGNUP_TYPE_ICONS)
    for name, value in (cfg("emojis.signup_type") or {}).items():
        if value and name in icons:
            icons[name] = value
    return icons.get(key, "")


def reset_emoji(key):
    if key == "flight_approved":
        return set_value("emojis.flight_approved", None)
    if key in DEFAULT_SIGNUP_TYPE_ICONS:
        return set_value(f"emojis.signup_type.{key}", None)
    return set_value(f"emojis.{key}", None)


def reset_all_emojis():
    set_value("emojis", {})


def reset_colors():
    set_value("colors", dict(DEFAULTS["colors"]))


def apply_ui_to_core(core_module):
    applied = []
    if core_module is None:
        return applied

    for key, attr in COLOR_CORE_ATTRS.items():
        value = cfg(f"colors.{key}")
        if value is None:
            value = DEFAULTS["colors"][key]
        try:
            setattr(core_module, attr, int(value))
            applied.append(attr)
        except (TypeError, ValueError):
            pass

    emoji_id = cfg("emojis.flight_approved")
    if emoji_id is not None and not str(emoji_id).isdigit():
        emoji_id = None
    elif emoji_id is not None:
        emoji_id = int(emoji_id)
    core_module.FLIGHT_APPROVED_EMOJI_ID = emoji_id
    core_module.FLIGHT_APPROVED_EMOJI = f"<:ch:{emoji_id}>" if emoji_id else DEFAULT_FLIGHT_APPROVED
    applied.append("FLIGHT_APPROVED_EMOJI")

    for key, attr in EMOJI_CORE_ATTRS.items():
        setattr(core_module, attr, str(cfg(f"emojis.{key}") or DEFAULT_EMOJI_STRINGS[key]))
        applied.append(attr)

    icons = dict(DEFAULT_SIGNUP_TYPE_ICONS)
    for key, value in (cfg("emojis.signup_type") or {}).items():
        if value and key in icons:
            try:
                parsed, _err = parse_emoji_value(value)
            except Exception:
                parsed = None
            icons[key] = parsed or icons[key]
    core_module.SIGNUP_TYPE_ICON = icons
    applied.append("SIGNUP_TYPE_ICON")
    return applied


def summary_lines():
    lines = []
    for group in ("guilds", "channels", "roles"):
        values = CONFIG.get(group, {})
        set_count = sum(1 for v in values.values() if v)
        lines.append(f"**{group}**: {set_count}/{len(values)} configured")
    return lines
