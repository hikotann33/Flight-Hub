import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
import datetime
from zoneinfo import ZoneInfo
import json
import io
import base64
import re
import traceback
import functools
import aiohttp
try:
    import edge_tts
except Exception:
    edge_tts = None
try:
    from deep_translator import MyMemoryTranslator
except Exception:
    MyMemoryTranslator = None
import asyncio
import copy
import random
import uuid
import sys
import os
from urllib.parse import urlencode
import matplotlib
matplotlib.use("Agg")  
import matplotlib.pyplot as plt

__version__ = "2.0.0"
DISPLAY_VERSION = "v2"








def _setup_matplotlib_fonts():
    try:
        from matplotlib import font_manager
        available = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:
        return
    preferred = [
        "Hiragino Sans", "Hiragino Kaku Gothic ProN", "YuGothic",
        "Yu Gothic", "Meiryo", "MS Gothic",
        "Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic",
        "TakaoGothic", "VL Gothic", "Source Han Sans JP",
        "DejaVu Sans",
    ]
    chosen = next((n for n in preferred if n in available), None)
    if not chosen:
        return
    matplotlib.rcParams["font.family"] = "sans-serif"
    current = list(matplotlib.rcParams.get("font.sans-serif") or [])
    matplotlib.rcParams["font.sans-serif"] = [chosen] + [f for f in current if f != chosen]
    matplotlib.rcParams["axes.unicode_minus"] = False


_setup_matplotlib_fonts()


def _apply_chart_style():
    if "seaborn-v0_8-whitegrid" in plt.style.available:
        plt.style.use("seaborn-v0_8-whitegrid")
    _setup_matplotlib_fonts()








def _load_dotenv():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(here, ".env"),
        os.path.join(os.path.dirname(here), ".env"),
    ]

    def _clean_value(value):
        value = value.strip()
        if value[:1] in ("'", '"'):
            quote = value[0]
            end = value.find(quote, 1)
            return value[1:end] if end != -1 else value[1:]
        for marker in (" #", "\t#"):
            idx = value.find(marker)
            if idx != -1:
                value = value[:idx]
        return value.rstrip()

    path = next((p for p in candidates if os.path.isfile(p)), None)
    if not path:
        return
    try:
        with open(path, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = _clean_value(value)
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError as e:
        print(f".env read error ({path}): {e}")


_load_dotenv()

from .config_store import cfg
from . import templates


def default_airline() -> str:
    return cfg("brand.airline", "Airline") or "Airline"





TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')


STAFF_GUILD_ID = cfg("guilds.staff")
STAFF_CHANNEL_ID = cfg("channels.staff_announce")

CUSTOMER_GUILD_ID = cfg("guilds.customer")
CUSTOMER_CHANNEL_ID = cfg("channels.customer_announce")




FLIGHT_INPUT_CHANNEL_ID = cfg("channels.flight_input")
FLIGHT_LOG_CHANNEL_ID = cfg("channels.flight_log")
BRIEFING_CHANNEL_ID = cfg("channels.briefing")
REMIND_TRACK_CHANNEL_ID = cfg("channels.remind_track")


COMMAND_CHANNEL_ID = cfg("channels.command")
REFLECTION_CHANNEL_ID = cfg("channels.reflection")
dm_message_cache = {}


NOTIFICATION_ROLE_ID = cfg("roles.notification")
JOIN_NOTIFICATION_ROLE_ID = cfg("roles.join_notification")


DM_TARGET_ROLE_ID = cfg("roles.dm_target")
DM_STAFF_ROLE_ID = cfg("roles.dm_staff")
DM_EXCLUDE_ROLE_ID = cfg("roles.dm_exclude")


ROLE_EVENT_MANAGERS = cfg("roles.event_manager")
ROLE_GROUND_OPS = cfg("roles.ground_ops")
ROLE_CABIN_CREWS = cfg("roles.cabin_crew")
ROLE_FLIGHT_OPS = cfg("roles.flight_ops")

EXCLUDE_REMIND_ROLE_ID = cfg("roles.exclude_remind")
EXCLUDE_REMIND_ROLE_ID_2 = cfg("roles.exclude_remind_2")
EXCLUDE_REMIND_ROLE_IDS = (EXCLUDE_REMIND_ROLE_ID, EXCLUDE_REMIND_ROLE_ID_2)
LOG_GUILD_ID = cfg("guilds.log")
TEST_CUSTOMER_CATEGORY_ID = cfg("channels.test_customer_category")
TEST_STAFF_CHANNEL_ID = cfg("channels.test_staff")
SELFTEST_CUSTOMER_CATEGORY_ID = cfg("channels.selftest_customer_category")
FLIGHT_APPROVED_EMOJI_ID = cfg("emojis.flight_approved")
FLIGHT_APPROVED_EMOJI = f"<:ch:{FLIGHT_APPROVED_EMOJI_ID}>" if FLIGHT_APPROVED_EMOJI_ID else "\u2705"
EMBED_COLOR = cfg("colors.primary", 0x1B3444)
PRIVATE_FLIGHT_COLOR = cfg("colors.private", 0x808080)













SIGNUP_TYPE_ICON = cfg("emojis.signup_type", {
    "flight":    "\u2708\ufe0f",
    "custom":    "\U0001f6e0\ufe0f",
    "test":      "\U0001f9ea",
    "recurring": "\U0001f501",
    "private":   "\U0001f512",
    "gamenight": "\U0001f3ae",
})


def signup_icon(flight: dict) -> str:
    flight = flight or {}
    if flight.get("is_gamenight"):
        key = "gamenight"
    elif flight.get("is_custom"):
        key = "custom"
    elif flight.get("is_test"):
        key = "test"
    elif flight.get("is_private"):
        key = "private"
    else:
        key = "flight"
    return SIGNUP_TYPE_ICON.get(key, "")


def signup_embed_title(flight: dict, name: str) -> str:
    icon = signup_icon(flight)
    return f"{icon} {name}".strip()


def signup_footer(flight_code, host_display) -> str:
    return f"Flight Code: {flight_code} | Created by {host_display}"


def minimum_staff_text() -> str:
    return "Captain - 1\nFirst Officer - 1\nCabin Crew - 2\nGround Crew - 1"




def _component_text(value, limit=4000):
    text = str(value or "")

    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]", "", text)
    return text if len(text) <= limit else text[: limit - 18].rstrip() + "… [truncated]"


def build_v2_card(title, sections=(), *, color=None, footer=None, content=None):
    view = discord.ui.LayoutView(timeout=180)
    children = []


    TOTAL_TEXT_BUDGET = 3900
    content_text = _component_text(content) if content else ""
    title_text = f"# {_component_text(title, 250)}" if title else ""
    footer_text = f"-# {_component_text(footer, 500)}" if footer else ""
    remaining = max(TOTAL_TEXT_BUDGET - len(content_text) - len(title_text) - len(footer_text), 0)
    if content_text:
        children.append(discord.ui.TextDisplay(content_text))
    if title_text:
        children.append(discord.ui.TextDisplay(title_text))


    for index, (heading, body) in enumerate(list(sections)[:30]):
        if index and index % 5 == 0:
            children.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
        if heading and body:
            value = f"**{_component_text(heading, 250)}**\n{_component_text(body, 3650)}"
        elif heading:
            value = f"**{_component_text(heading, 250)}**"
        else:
            value = _component_text(body)
        if value and len(value) > remaining:
            value = (value[:remaining - 1] + "…") if remaining > 1 else ""
        remaining -= len(value)
        if value:
            children.append(discord.ui.TextDisplay(value))
    if footer_text:
        children.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
        children.append(discord.ui.TextDisplay(footer_text))
    if not children:
        children.append(discord.ui.TextDisplay("No details available."))
    accent = getattr(color, "value", color if color is not None else EMBED_COLOR)
    view.add_item(discord.ui.Container(*children, accent_color=accent))
    return view


def embed_to_v2_layout(embed, *, content=None):
    if embed is None:
        return build_v2_card("Notice", [(None, content or "No details available.")])
    sections = []
    if getattr(embed, "author", None) and getattr(embed.author, "name", None):
        sections.append((None, f"*{embed.author.name}*"))
    if getattr(embed, "description", None):
        sections.append((None, embed.description))
    for field in getattr(embed, "fields", []):
        sections.append((field.name or None, field.value or "—"))
    if getattr(embed, "timestamp", None):
        try:
            sections.append(("Updated", f"<t:{int(embed.timestamp.timestamp())}:F>"))
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass
    footer = getattr(getattr(embed, "footer", None), "text", None)
    title = getattr(embed, "title", None) or "Information"
    color = getattr(embed, "color", None) or EMBED_COLOR
    view = build_v2_card(title, sections, color=color, footer=footer, content=content)
    media_items = []
    thumbnail_url = getattr(getattr(embed, "thumbnail", None), "url", None)
    image_url = getattr(getattr(embed, "image", None), "url", None)
    for url in (thumbnail_url, image_url):
        if url:
            media_items.append(discord.MediaGalleryItem(url))
    if media_items:
        view.children[0].add_item(discord.ui.MediaGallery(*media_items))
    return view


FLIGHT_APP_CHANNEL_ID = cfg("channels.flight_app")
CHIEF_ROLE_ID = cfg("roles.chief")
FLIGHT_VERIFIER_ROLE_ID = cfg("roles.flight_verifier")
ADMIN_ROLE_ID = CHIEF_ROLE_ID



REMOTE_ASSIGN_ROLE_IDS = (ROLE_EVENT_MANAGERS, CHIEF_ROLE_ID)
















HIDE_EVENT_MANAGER_COMMANDS = False
EVENT_MANAGER_COMMAND_PERMISSION = "manage_events"

def event_manager_only(func):
    func.__em_cmd__ = True

    @functools.wraps(func)
    async def _guarded(interaction, *args, **kwargs):
        if getattr(interaction, "guild_id", None) != STAFF_GUILD_ID:
            try:
                return await interaction.response.send_message(
                    ephemeral=True, view=build_v2_card('Notice',
                        [(None, 'This command is only available on the staff server.')]))
            except Exception:
                return None
        if not is_event_manager_or_chief(interaction.user):
            try:
                return await interaction.response.send_message(
                    ephemeral=True, view=build_v2_card('Notice',
                        [(None, 'No permission.')]))
            except Exception:
                return None
        return await func(interaction, *args, **kwargs)

    wrapper = _guarded
    if HIDE_EVENT_MANAGER_COMMANDS:
        wrapper = app_commands.default_permissions(**{EVENT_MANAGER_COMMAND_PERMISSION: True})(wrapper)
    wrapper.__em_cmd__ = True
    return wrapper

def is_chief(member) -> bool:
    return any(getattr(r, "id", None) == CHIEF_ROLE_ID for r in (getattr(member, "roles", None) or []))

def can_remote_assign(member) -> bool:
    return any(getattr(r, "id", None) in REMOTE_ASSIGN_ROLE_IDS for r in (getattr(member, "roles", None) or []))

def is_event_manager(member) -> bool:
    return any(getattr(r, "id", None) == ROLE_EVENT_MANAGERS for r in (getattr(member, "roles", None) or []))

def is_event_manager_or_chief(member) -> bool:
    return is_event_manager(member) or is_chief(member)










PERM_EVERYONE = "everyone"
PERM_EVENT_MANAGER = "event_manager"
PERM_VERIFIER = "verifier"
PERM_CHIEF = "chief"
PERM_DISCORD_ADMIN = "discord_admin"


PERMISSION_ORDER = (
    PERM_EVERYONE, PERM_VERIFIER, PERM_EVENT_MANAGER,
    PERM_CHIEF, PERM_DISCORD_ADMIN,
)

PERMISSION_LABELS = {
    PERM_EVERYONE: {"ja": "All Staff", "en": "All staff"},
    PERM_VERIFIER: {"ja": "Flight Verifier", "en": "Flight Verifier"},
    PERM_EVENT_MANAGER: {"ja": "Event Manager", "en": "Event Manager"},
    PERM_CHIEF: {"ja": "Chief", "en": "Chief"},
    PERM_DISCORD_ADMIN: {"ja": "Discord Admin", "en": "Discord Admin"},
}


COMMAND_PERMISSIONS = {

    "/up": PERM_CHIEF,
    "/restart": PERM_CHIEF,
    "/clear_logs": PERM_CHIEF,
    "/setup_em_permissions": PERM_CHIEF,
    "/manage_templates": PERM_CHIEF,
    "/restore_from_message": PERM_CHIEF,
    "/backupflight": PERM_CHIEF,
    "/flight_app_backup": PERM_CHIEF,
    "/editflightlog": PERM_CHIEF,
    "/manual_log": PERM_CHIEF,
    "/update": PERM_CHIEF,
    "/aps": PERM_CHIEF,
    "/undo": PERM_CHIEF,
    "/inactive_staff": PERM_CHIEF,
    "/sync_console": PERM_CHIEF,
    "/send_evaluation": PERM_CHIEF,
    "/remind": PERM_CHIEF,
    "/remind_status": PERM_CHIEF,
    "/flight_stats_graph": PERM_CHIEF,
    "/healthcheck": PERM_CHIEF,
    "/flight_dashboard": PERM_CHIEF,
    "/staff_analytics": PERM_CHIEF,
    "/restore": PERM_CHIEF,
    "/loa list": PERM_CHIEF,
    "/loa cancel": PERM_CHIEF,
    "/loa restore_legacy": PERM_CHIEF,

    "/selftest": PERM_DISCORD_ADMIN,
    "/test_admin": PERM_DISCORD_ADMIN,
    "/test_evaluate": PERM_DISCORD_ADMIN,
    "/test_progress": PERM_DISCORD_ADMIN,

    "/create_flight": PERM_EVENT_MANAGER,
    "/create_flighttest": PERM_EVENT_MANAGER,
    "/create_custom_flight": PERM_EVENT_MANAGER,
    "/create_private_flight": PERM_EVENT_MANAGER,
    "/create_private_flight_template": PERM_EVENT_MANAGER,
    "/recurring_flight": PERM_EVENT_MANAGER,
    "/recurring_flighttest": PERM_EVENT_MANAGER,
    "/duplicate_flight": PERM_EVENT_MANAGER,
    "/dispatch_app": PERM_EVENT_MANAGER,
    "/publish_schedule": PERM_EVENT_MANAGER,
    "/cancel": PERM_EVENT_MANAGER,
    "/delay": PERM_EVENT_MANAGER,
    "/host_change": PERM_EVENT_MANAGER,
    "/close_signup": PERM_EVENT_MANAGER,
    "/update_ui": PERM_EVENT_MANAGER,
    "/event_thread": PERM_EVENT_MANAGER,
    "/briefing": PERM_EVENT_MANAGER,
    "/edit_briefing": PERM_EVENT_MANAGER,
    "/checklist": PERM_EVENT_MANAGER,
    "/find_staff": PERM_EVENT_MANAGER,
    "/request_staff": PERM_EVENT_MANAGER,
    "/flight_log": PERM_EVENT_MANAGER,
    "/flight_backup": PERM_EVENT_MANAGER,
    "/staff_gamenight": PERM_EVENT_MANAGER,
    "/edit_gamenight": PERM_EVENT_MANAGER,

    "/manual_assign": PERM_EVENT_MANAGER,
}


def user_permission_levels(member) -> set:
    levels = {PERM_EVERYONE}
    roles = [getattr(r, "id", None) for r in (getattr(member, "roles", None) or [])]
    if FLIGHT_VERIFIER_ROLE_ID in roles:
        levels.add(PERM_VERIFIER)
    if is_event_manager(member):
        levels.add(PERM_EVENT_MANAGER)
    if is_chief(member):
        levels.add(PERM_CHIEF)
    perms = getattr(member, "guild_permissions", None)
    if perms is not None and getattr(perms, "administrator", False):
        levels.add(PERM_DISCORD_ADMIN)
    return levels


def required_permission(command: str) -> str:
    cmd = (command or "").strip()
    if cmd in COMMAND_PERMISSIONS:
        return COMMAND_PERMISSIONS[cmd]
    base = cmd.split()[0] if cmd else ""
    if base in COMMAND_PERMISSIONS:
        return COMMAND_PERMISSIONS[base]
    return PERM_EVERYONE


def can_run_command(levels: set, command: str) -> bool:
    need = required_permission(command)
    if need == PERM_EVERYONE:
        return True
    if need == PERM_CHIEF:
        return PERM_CHIEF in levels
    if need == PERM_DISCORD_ADMIN:
        return PERM_DISCORD_ADMIN in levels
    if need in (PERM_EVENT_MANAGER, PERM_VERIFIER):
        return need in levels or PERM_CHIEF in levels
    return True


def highest_permission(levels: set) -> str:
    for level in reversed(PERMISSION_ORDER):
        if level in levels:
            return level
    return PERM_EVERYONE

























EVAL_TRACK_CHANNEL_ID = cfg("channels.eval_track")




AUDIT_LOG_CHANNEL_ID = cfg("channels.audit_log")
APP_EXPIRY_HOURS = 48
APP_EXPIRY_ACTION = "remind"

FLIGHT_DB = {}
FLIGHT_AUTOCOMPLETE_CACHE = []
FLIGHT_LOG_CACHE = []



EMOJI_CHECK_STR = cfg("emojis.check", "\u2705")
EMOJI_X_STR = cfg("emojis.x", "\u274c")
EMOJI_NOTI_STR = cfg("emojis.noti", "\U0001f514")
EMOJI_INFO_STR = cfg("emojis.info", "\u2139\ufe0f")
EMOJI_SEARCH_STR = cfg("emojis.search", "\U0001f50d")
EMOJI_BAGGAGE_STR = cfg("emojis.baggage", "\U0001f9f3")
EMOJI_TAIL_STR = cfg("emojis.tail", "\u2708\ufe0f")
EMOJI_LINK_STR = cfg("emojis.link", "\U0001f517")
EMOJI_BRAND_STR = cfg("emojis.brand", "\u2708\ufe0f")

JST = ZoneInfo(cfg("options.timezone", "Asia/Tokyo"))














MENTION_SPACING_HOURS = 24
LAST_CUSTOMER_MENTION_TS = 0.0

def mention_cooldown_active(now_ts=None):
    if now_ts is None:
        now_ts = datetime.datetime.now().timestamp()
    return (now_ts - LAST_CUSTOMER_MENTION_TS) < MENTION_SPACING_HOURS * 3600

def sync_last_mention_from_cache():
    global LAST_CUSTOMER_MENTION_TS
    for f in FLIGHT_LOG_CACHE:
        ts = f.get("mention_sent_ts", 0) or 0
        if ts > LAST_CUSTOMER_MENTION_TS:
            LAST_CUSTOMER_MENTION_TS = ts

def _mention_exempt(flight: dict) -> bool:
    return bool(flight.get("is_test") or flight.get("is_private") or flight.get("is_gamenight"))

def apply_mention_policy(flight: dict, content: str) -> str:
    mention = flight.get("mention_str", f"<@&{NOTIFICATION_ROLE_ID}>")
    if _mention_exempt(flight):
        return content
    if not mention or mention not in content:
        return content
    if mention_cooldown_active():
        flight["no_mention"] = True
        return content.replace(f"{mention}\n", "", 1)
    flight["no_mention"] = False
    return content

def commit_mention(flight: dict, posted_content: str):
    global LAST_CUSTOMER_MENTION_TS
    if _mention_exempt(flight):
        return
    mention = flight.get("mention_str", f"<@&{NOTIFICATION_ROLE_ID}>")
    if not mention or mention not in (posted_content or ""):
        return
    now_ts = datetime.datetime.now().timestamp()
    flight["mention_sent_ts"] = now_ts
    flight["no_mention"] = False
    LAST_CUSTOMER_MENTION_TS = now_ts
    try:
        client.loop.create_task(save_misc_data())
    except Exception as e:
        print(f"Could not persist mention clock: {e}")

_ANNOUNCE_MARKERS = ("Flight code:", "Operation name:")

async def refresh_mention_clock_from_history(limit=100):
    global LAST_CUSTOMER_MENTION_TS
    try:
        ch = client.get_channel(CUSTOMER_CHANNEL_ID) or await client.fetch_channel(CUSTOMER_CHANNEL_ID)
        toks = _mention_tokens()
        async for m in ch.history(limit=limit):
            if m.author != client.user or not m.content:
                continue
            if not any(mk in m.content for mk in _ANNOUNCE_MARKERS):
                continue
            if any(t in m.content for t in toks):
                ts = m.created_at.timestamp()
                if ts > LAST_CUSTOMER_MENTION_TS:
                    LAST_CUSTOMER_MENTION_TS = ts
                    try:
                        client.loop.create_task(save_misc_data())
                    except Exception:
                        pass
                return True
        return True
    except Exception as e:
        print(f"Could not read customer channel history for the mention clock: {e}")
        return False

_MENTION_LOCK = None

async def post_customer_announcement(channel, flight: dict, content: str):
    global _MENTION_LOCK
    if _MENTION_LOCK is None:
        _MENTION_LOCK = asyncio.Lock()
    async with _MENTION_LOCK:

        if not _mention_exempt(flight) and not mention_cooldown_active():
            await refresh_mention_clock_from_history()
        final = apply_mention_policy(flight, content)
        sent = await channel.send(content=final, suppress_embeds=True)
        commit_mention(flight, final)
        return sent

def get_customer_mention_line(flight: dict) -> str:
    if flight.get("no_mention"):
        return ""
    m = flight.get("mention_str", f"<@&{NOTIFICATION_ROLE_ID}>")
    return f"{m}\n" if m else ""
global_json_lock = None
global_db_dirty = False




LOA_ROLE_ID = cfg("roles.loa")
LOA_TRACK_CHANNEL_ID = cfg("channels.loa_track")
LOA_CACHE = {}
LOA_RETURN_HISTORY = {}


MISC_DATA_CHANNEL_ID = cfg("channels.misc_data")
STAFF_NOTES_CACHE = {}
ANNOUNCE_TEMPLATES_CACHE = {}
SWAP_BOARD_CACHE = []
POLL_CACHE = {}
NEWS_CACHE = []
UNDO_STACK = []





remind_tracking_cache = {"month": 0, "users": []}

async def load_remind_tracking():
    global remind_tracking_cache
    found, data = await read_latest_json_backup(REMIND_TRACK_CHANNEL_ID, limit=100)
    if found and isinstance(data, dict):
        remind_tracking_cache = data
        print(f"Remind Cache Loaded: {len(remind_tracking_cache.get('users', []))} users.")
    elif found:
        raise LoadError("remind_tracking backup has an unexpected format")
    else:
        remind_tracking_cache = {"month": 0, "users": []}

async def save_remind_tracking():

    await save_json_to_channel(REMIND_TRACK_CHANNEL_ID, remind_tracking_cache, "remind_tracking.json")

POSITIONS_DATA = [
    ("Co-host", "Requires Event Managers role", ROLE_EVENT_MANAGERS),
    ("Receptionist", "Requires Cabin Crews role", ROLE_CABIN_CREWS),
    ("Airport Guide", "Requires Cabin Crews role", ROLE_CABIN_CREWS),
    ("Lounge Agent", "Requires Cabin Crews role", ROLE_CABIN_CREWS),
    ("Captain", "Requires Flight Operations role", ROLE_FLIGHT_OPS),
    ("First Officer", "Requires Flight Operations role", ROLE_FLIGHT_OPS),
    ("First Class", "Requires Cabin Crews role", ROLE_CABIN_CREWS),
    ("Business Class", "Requires Cabin Crews role", ROLE_CABIN_CREWS),
    ("Premium Economy", "Requires Cabin Crews role", ROLE_CABIN_CREWS),
    ("Economy Class", "Requires Cabin Crews role", ROLE_CABIN_CREWS),
    ("GC Supervisor(MR)", "Requires Ground Operations role", ROLE_GROUND_OPS),
    ("Ground Crew", "Requires Ground Operations role", ROLE_GROUND_OPS)
]


STAFF_GUILD = discord.Object(id=STAFF_GUILD_ID) if STAFF_GUILD_ID else None
CUSTOMER_GUILD = discord.Object(id=CUSTOMER_GUILD_ID) if CUSTOMER_GUILD_ID else None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True
client = commands.Bot(command_prefix="!", intents=intents)

FLIGHT_LOG_HISTORY_CHANNEL_ID = cfg("channels.flight_log_history")
MANUAL_LOG_CHANNEL_ID = cfg("channels.manual_log")
LOG_MANAGER_ROLE_ID = CHIEF_ROLE_ID


VOICE_CLIENTS = {}
VOICE_TARGET_VC = {}
VOICE_TARGET_TEXT = {}
TTS_QUEUE = {}
TTS_TASKS = {}
TTS_ENABLED = {}
TTS_PENDING = set()
TTS_QUEUE_MAX = 5
VOICE_EMPTY_GRACE = 5.0


def _get_tts_queue(guild_id: int) -> "asyncio.Queue":
    q = TTS_QUEUE.get(guild_id)
    if q is None:
        q = asyncio.Queue(maxsize=TTS_QUEUE_MAX)
        TTS_QUEUE[guild_id] = q
    return q


def _clear_voice_state(guild_id: int):
    TTS_ENABLED[guild_id] = False
    VOICE_CLIENTS.pop(guild_id, None)
    VOICE_TARGET_VC.pop(guild_id, None)
    VOICE_TARGET_TEXT.pop(guild_id, None)
    task = TTS_TASKS.pop(guild_id, None)
    if task is not None and not task.done():
        try:
            task.cancel()
        except Exception:
            pass
    TTS_QUEUE.pop(guild_id, None)


_VOICE_DEP_WARNED = False


def voice_libraries_available() -> bool:
    try:
        return bool(getattr(discord.voice_client, "has_nacl", False))
    except Exception:
        return False


def warn_voice_libraries_once():
    global _VOICE_DEP_WARNED
    if _VOICE_DEP_WARNED:
        return
    _VOICE_DEP_WARNED = True
    print("[TTS] The PyNaCl audio library could not be loaded, so voice channel connections and read-aloud are disabled.")
    print("      Current Python: {}".format(sys.executable))
    print("      Run the following on this Python, then restart the bot:")
    print("          ./venv/bin/pip install -r requirements.txt")
    print("      (On a Raspberry Pi, if it fails, try:  sudo apt install -y libsodium-dev)")


async def maybe_auto_leave_voice(guild, before=None, after=None):
    try:
        vc = guild.voice_client
        if vc is None or vc.channel is None:
            return
        ch = vc.channel
        related = False
        for c in (getattr(before, "channel", None), getattr(after, "channel", None)):
            if c is not None and getattr(c, "id", None) == ch.id:
                related = True
                break
        if not related:
            return

        if any(not m.bot for m in ch.members):
            return

        await asyncio.sleep(VOICE_EMPTY_GRACE)
        vc = guild.voice_client
        if vc is None or vc.channel is None:
            return
        if any(not m.bot for m in vc.channel.members):
            return
        print(f"[TTS] Leaving the voice channel because no human is left (guild={guild.id}, channel={vc.channel})")
        try:
            await vc.disconnect(force=True)
        except TypeError:
            await vc.disconnect()
        except Exception as e:
            print(f"[TTS] disconnect error: {e}")
        _clear_voice_state(guild.id)
    except Exception as e:
        print(f"[TTS] auto-leave error: {e}")


def _ffmpeg_executable() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (
        "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg", "/usr/local/ffmpeg/bin/ffmpeg",
    ):
        if os.path.exists(cand):
            return cand
    return "ffmpeg"


async def _tts_synthesize(text: str, lang: str, path: str) -> bool:
    edge_voice = "ja-JP-NanamiNeural" if lang == "ja" else "en-US-JennyNeural"
    if edge_tts is not None:
        try:
            await asyncio.wait_for(edge_tts.Communicate(text, edge_voice).save(path), timeout=10)
            if os.path.getsize(path) > 0:
                return True
        except Exception as e:
            print(f"edge-tts failed, trying gTTS: {e}")
    try:
        from gtts import gTTS

        def _gtts():
            gTTS(text, lang=lang).save(path)

        await asyncio.wait_for(asyncio.to_thread(_gtts), timeout=15)
        return os.path.getsize(path) > 0
    except Exception as e:
        print(f"gTTS failed: {e}")
        return False


async def _tts_speak_text(guild_id: int, text: str, lang: str = "ja"):
    vc = VOICE_CLIENTS.get(guild_id)
    if not vc or not vc.is_connected():

        try:
            g = client.get_guild(guild_id)
            vc = g.voice_client if g else None
            if vc:
                VOICE_CLIENTS[guild_id] = vc
        except Exception:
            vc = None
    if not vc or not vc.is_connected():
        return
    if not text or not text.strip():
        return
    path = None
    try:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        if not await _tts_synthesize(text, lang, path):
            print(f"[TTS] synth failed for: {text[:40]}")
            return
        print(f"[TTS] playing ({lang}, {os.path.getsize(path)} bytes): {text[:40]}")

        def _after(err):
            if err:
                print(f"[TTS] ffmpeg error: {err}")

        while vc.is_playing():
            await asyncio.sleep(0.2)
            if not vc.is_connected():
                return
        vc.play(discord.FFmpegPCMAudio(path, executable=_ffmpeg_executable()), after=_after)

        await asyncio.sleep(0.2)
        waited = 0.0
        while True:
            try:
                if not vc.is_playing():
                    break
            except Exception:
                break
            await asyncio.sleep(0.2)
            waited += 0.2
            if waited >= 120 or not vc.is_connected():
                break
    except Exception as e:
        print(f"TTS play error: {e}")
    finally:
        if path:


            try:
                os.remove(path)
            except Exception:
                pass


async def _tts_queue_worker(guild_id: int):
    queue = _get_tts_queue(guild_id)
    while True:
        try:
            item = await queue.get()
            if item is None:
                break
            text = item.get("text", "")
            lang = item.get("lang", "ja")
            await _tts_speak_text(guild_id, text, lang)
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.2)
        finally:
            try:
                queue.task_done()
            except Exception:
                pass

async def _translate_text(text: str, source: str, target: str) -> str:
    if not text or not text.strip():
        return ""

    def _do(src: str) -> str:
        try:
            if MyMemoryTranslator is None:
                return ""
            t = MyMemoryTranslator(source=source, target=target)
            return t.translate(src)
        except Exception:
            return ""

    try:
        res = await asyncio.wait_for(asyncio.to_thread(_do, text), timeout=8)
        if isinstance(res, str) and res.strip():
            return res.strip()
    except Exception:
        pass
    return text


async def _translate_ja_to_en(text: str) -> str:
    return await _translate_text(text, "japanese", "english")


async def _translate_en_to_ja(text: str) -> str:
    return await _translate_text(text, "english", "japanese")


def _contains_japanese(text: str) -> bool:
    return any(
        ("\u3040" <= ch <= "\u30ff") or ("\u4e00" <= ch <= "\u9fff")
        for ch in text
    )


async def _tts_enqueue_bilingual(guild_id: int, text: str):
    if not text or not text.strip():
        return
    if not TTS_ENABLED.get(guild_id):
        print(f"[TTS] skip: TTS disabled (guild={guild_id})")
        return
    queue = _get_tts_queue(guild_id)

    def _enqueue(item: dict):

        try:
            while queue.full():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except Exception:
                    break
            queue.put_nowait(item)
        except Exception:
            pass


    if _contains_japanese(text):
        print(f"[TTS] queue ja: {text[:40]}")
        _enqueue({"text": text, "lang": "ja"})
        en = await _translate_ja_to_en(text)
        if en and en != text:
            print(f"[TTS] queue en: {en[:40]}")
            _enqueue({"text": en, "lang": "en"})
    else:
        print(f"[TTS] queue en: {text[:40]}")
        _enqueue({"text": text, "lang": "en"})
        ja = await _translate_en_to_ja(text)
        if ja and ja != text:
            print(f"[TTS] queue ja: {ja[:40]}")
            _enqueue({"text": ja, "lang": "ja"})












FLIGHT_MIN_GAP_DAYS = 7



NON_CUSTOMER_LOG_TYPES = ("private", "game night", "gamenight", "test")


def is_customer_flight(f: dict) -> bool:
    if not f:
        return True
    if f.get("is_test") or f.get("is_private") or f.get("is_gamenight"):
        return False
    return not str(f.get("flight_code", "")).upper().startswith("[TEST]")

def _get_jst_date(ts: float) -> datetime.date:
    return datetime.datetime.fromtimestamp(ts, tz=JST).date()

def check_date_based_spacing(new_ts: int, current_flight_code: str = None, min_days: int = FLIGHT_MIN_GAP_DAYS) -> tuple[bool, str]:
    if new_ts <= 0:
        return True, ""
    new_date = _get_jst_date(new_ts)
    for f in FLIGHT_LOG_CACHE:
        if f.get("messages_deleted") or not is_customer_flight(f):
            continue
        if current_flight_code and f.get("flight_code") == current_flight_code:
            continue

        existing_ts = f.get("start_timestamp", 0)
        if existing_ts <= 0:
            continue

        existing_date = _get_jst_date(existing_ts)
        diff_days = abs((new_date - existing_date).days)
        if diff_days < min_days:
            existing_code = f.get("flight_code", "another flight")
            return False, (
                f"This date is too close to flight `{existing_code}` (gap: {diff_days} day(s)).\n"
                f"Flights can only be held once a week: at least {min_days} calendar days apart.\n"
                f"A flight can be hosted once per week. Leave at least {min_days} calendar days between flights."
            )
    return True, ""

async def check_date_based_spacing_vs_log(new_ts: int, min_days: int = FLIGHT_MIN_GAP_DAYS) -> tuple[bool, str]:
    if new_ts <= 0:
        return True, ""
    log_channel = client.get_channel(FLIGHT_LOG_HISTORY_CHANNEL_ID)
    if not log_channel:
        return True, ""
    new_date = _get_jst_date(new_ts)
    try:
        async_iter = log_channel.history(limit=25)
    except Exception:
        return True, ""
    counted = 0
    try:
        async for msg in async_iter:
            parsed = parse_log_message(msg)
            if not parsed:
                continue
            ftype = str(parsed.get("flight_type") or "").strip().lower()
            code = str(parsed.get("flight_code") or "")
            if ftype in NON_CUSTOMER_LOG_TYPES or code.upper().startswith("[TEST]"):
                continue
            cached = next((f for f in FLIGHT_LOG_CACHE if f.get("flight_code") == code), None)
            if cached is not None and not is_customer_flight(cached):
                continue
            counted += 1
            existing_date = _get_jst_date(parsed["timestamp"])
            diff_days = abs((new_date - existing_date).days)
            if diff_days < min_days:
                return False, (
                    f"This date is too close to the recently flown flight `{parsed['flight_code']}` (gap: {diff_days} day(s)).\n"
                    f"Flights can only be held once a week: at least {min_days} calendar days apart.\n"
                    f"A flight can be hosted once per week. Leave at least {min_days} calendar days between flights."
                )
            if counted >= 5:
                break
    except Exception:
        pass
    return True, ""

async def check_host_duplicate(bot_client, host_id: int, ignore_flight_code: str = None) -> str | None:
    now_ts = datetime.datetime.now().timestamp()
    ignore_fc = ignore_flight_code.lower() if ignore_flight_code else None


    for f in FLIGHT_LOG_CACHE:
        if f.get("end_timestamp", 0) > now_ts and not f.get("messages_deleted", False) and not f.get("is_test", False):
            if ignore_fc and f.get("flight_code", "").lower() == ignore_fc:
                continue
            if f.get("host_id") == host_id:
                return f.get("flight_code")


    app_channel = bot_client.get_channel(FLIGHT_APP_CHANNEL_ID)
    if app_channel:
        try:
            async for msg in app_channel.history(limit=50):
                if msg.author.bot and msg.embeds:
                    embed = msg.embeds[0]
                    if embed.title and ("Pending" in embed.title or "Approved" in embed.title):
                        desc = embed.description or ""
                        host_match = re.search(r'\*\*Host:\*\*\s*<@!?(\d+)>', desc)
                        if host_match and int(host_match.group(1)) == host_id:
                            fc_match = re.search(r'\*\*Flight Code:\*\*\s*(.+)', desc)
                            found_fc = fc_match.group(1).strip() if fc_match else "Unknown"
                            if ignore_fc and found_fc.lower() == ignore_fc:
                                continue



                            if "Approved" in embed.title:
                                app_data_check = extract_app_data(embed)
                                dep_ts = parse_date_time_to_ts(
                                    app_data_check.get("date", ""),
                                    app_data_check.get("time", ""),
                                    app_data_check.get("offset_hrs", 9)
                                )
                                if dep_ts > 0 and dep_ts <= now_ts:
                                    continue
                            return found_fc
        except Exception:
            pass
    return None




async def load_loa_tracking():
    global LOA_CACHE, LOA_RETURN_HISTORY
    found, data = await read_latest_json_backup(LOA_TRACK_CHANNEL_ID, filename="loa_data.json", limit=100)
    if found and not isinstance(data, dict):
        raise LoadError("loa_data backup has an unexpected format (expected a dict)")
    if found:
        LOA_CACHE = data
        print(f"LOA Cache Loaded: {len(LOA_CACHE)} users.")
    else:
        LOA_CACHE = {}

    found2, data2 = await read_latest_json_backup(LOA_TRACK_CHANNEL_ID, filename="loa_return_history.json", limit=100)
    if found2 and not isinstance(data2, dict):
        raise LoadError("loa_return_history backup has an unexpected format (expected a dict)")
    if found2:
        LOA_RETURN_HISTORY = data2
        print(f"LOA Return History Loaded: {len(LOA_RETURN_HISTORY)} users.")
    else:
        LOA_RETURN_HISTORY = {}

async def save_loa_tracking():
    await save_json_to_channel(LOA_TRACK_CHANNEL_ID, LOA_CACHE, "loa_data.json")

async def save_loa_return_history():
    await save_json_to_channel(LOA_TRACK_CHANNEL_ID, LOA_RETURN_HISTORY, "loa_return_history.json")

async def record_loa_return(user_id: int):
    LOA_RETURN_HISTORY[str(user_id)] = int(datetime.datetime.now(JST).timestamp())
    await save_loa_return_history()

def is_exempt_from_flight_reminder(member: discord.Member, jst_now: datetime.datetime) -> bool:

    if member.joined_at:
        joined_jst = member.joined_at.astimezone(JST)
        if joined_jst.year == jst_now.year and joined_jst.month == jst_now.month:
            return True


    return_ts = LOA_RETURN_HISTORY.get(str(member.id))
    if return_ts:
        return_dt = datetime.datetime.fromtimestamp(return_ts, tz=JST)
        if return_dt.year == jst_now.year and return_dt.month == jst_now.month:
            return True

    return False





async def load_misc_data():
    global STAFF_NOTES_CACHE, ANNOUNCE_TEMPLATES_CACHE, SWAP_BOARD_CACHE, POLL_CACHE, NEWS_CACHE, LAST_CUSTOMER_MENTION_TS
    found, data = await read_latest_json_backup(MISC_DATA_CHANNEL_ID, filename="misc_data.json", limit=100)
    if not found:
        STAFF_NOTES_CACHE, ANNOUNCE_TEMPLATES_CACHE, SWAP_BOARD_CACHE = {}, {}, []
        POLL_CACHE, NEWS_CACHE = {}, []
        return
    if not isinstance(data, dict):
        raise LoadError("misc_data backup has an unexpected format (expected a dict)")
    STAFF_NOTES_CACHE = data.get("staff_notes", {})
    ANNOUNCE_TEMPLATES_CACHE = data.get("announce_templates", {})
    SWAP_BOARD_CACHE = data.get("swap_board", [])
    POLL_CACHE = data.get("polls") if isinstance(data.get("polls"), dict) else {}
    NEWS_CACHE = data.get("news") if isinstance(data.get("news"), list) else []
    LAST_CUSTOMER_MENTION_TS = max(LAST_CUSTOMER_MENTION_TS, float(data.get("last_customer_mention_ts", 0) or 0))
    print(f"Misc Data Loaded: notes={len(STAFF_NOTES_CACHE)}, templates={len(ANNOUNCE_TEMPLATES_CACHE)}, swaps={len(SWAP_BOARD_CACHE)}")

async def save_misc_data():
    payload = {"last_customer_mention_ts": LAST_CUSTOMER_MENTION_TS}
    if STAFF_NOTES_CACHE:
        payload["staff_notes"] = STAFF_NOTES_CACHE
    if ANNOUNCE_TEMPLATES_CACHE:
        payload["announce_templates"] = ANNOUNCE_TEMPLATES_CACHE
    if SWAP_BOARD_CACHE:
        payload["swap_board"] = SWAP_BOARD_CACHE
    if POLL_CACHE:
        payload["polls"] = POLL_CACHE
    if NEWS_CACHE:
        payload["news"] = NEWS_CACHE
    return await save_json_to_channel(MISC_DATA_CHANNEL_ID, payload, "misc_data.json")

async def cleanup_obsolete_saved_data() -> dict:
    global STAFF_NOTES_CACHE, ANNOUNCE_TEMPLATES_CACHE, SWAP_BOARD_CACHE
    result = {"removed": {}, "backup": None, "skipped": None}
    if MISC_DATA_CHANNEL_ID in LOAD_UNSAFE_CHANNELS:
        result["skipped"] = "misc data was not loaded"
        return result
    counts = {
        "staff_notes": len(STAFF_NOTES_CACHE or {}),
        "announce_templates": len(ANNOUNCE_TEMPLATES_CACHE or {}),
        "swap_board": len(SWAP_BOARD_CACHE or []),
    }
    if any(counts.values()):
        result["backup"] = json.dumps({
            "staff_notes": STAFF_NOTES_CACHE, "announce_templates": ANNOUNCE_TEMPLATES_CACHE, "swap_board": SWAP_BOARD_CACHE,
        }, ensure_ascii=False, indent=2).encode("utf-8")
    STAFF_NOTES_CACHE, ANNOUNCE_TEMPLATES_CACHE, SWAP_BOARD_CACHE = {}, {}, []
    result["removed"] = counts
    return result

def _trunc_desc(s: str, limit: int = 100) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def sanitize_command_descriptions() -> list:
    fixed = []

    def _fix_param(prefix, param):
        try:
            pd = getattr(param, "description", None)
            if isinstance(pd, str) and len(pd) > 100:
                param.description = _trunc_desc(pd)
                fixed.append(f"{prefix} (option)")
        except Exception:
            pass

    def _fix_command(prefix, cmd):
        try:
            d = getattr(cmd, "description", None)
            if isinstance(d, str) and len(d) > 100:
                cmd.description = _trunc_desc(d)
                fixed.append(f"{prefix} (description)")
        except Exception:
            pass
        for pname, param in (getattr(cmd, "_params", {}) or {}).items():
            _fix_param(f"{prefix} {pname}", param)
        for sub in (getattr(cmd, "commands", None) or []):
            _fix_command(f"{prefix} {getattr(sub, 'name', '?')}", sub)

    for cmd in client.tree.get_commands():
        _fix_command(cmd.name, cmd)

    if fixed:
        print(f"[Command sanitize] Truncated long descriptions on {len(fixed)} command(s): {', '.join(fixed)}")
    return fixed


def check_command_visibility_roles(guild=None) -> list:
    warns = []
    if not HIDE_EVENT_MANAGER_COMMANDS:
        warns.append("Event-manager commands are visible to everyone but can only be run by Event Managers on the staff server.")
        return warns
    guild = guild or client.get_guild(STAFF_GUILD_ID)
    if guild is None:
        return warns
    perm = EVENT_MANAGER_COMMAND_PERMISSION
    for rid, label in ((ROLE_EVENT_MANAGERS, "Event Managers"), (CHIEF_ROLE_ID, "Chief")):
        role = guild.get_role(rid)
        if role is None:
            warns.append(f"{label} role not found.")
        elif not getattr(role.permissions, perm, False) and not role.permissions.administrator:
            warns.append(f"`{role.name}` lacks the '{perm}' permission, so event-manager commands are not shown. Please enable 'Manage Events' in the role settings.")
    return warns


async def setup_event_manager_command_permissions(guild=None) -> list:
    warnings = []
    guild = guild or client.get_guild(STAFF_GUILD_ID)
    if guild is None:
        return ["Staff server not found, so resetting command permissions was skipped."]
    try:
        app_id = (await client.application_info()).id
    except Exception as e:
        return [f"Failed to reset command permissions (could not get the application ID): {e}"]
    try:
        commands = client.tree.get_commands()
    except Exception as e:
        return [f"Failed to reset command permissions (could not fetch the command list): {e}"]

    cleared = []
    failed = []
    seen = set()
    for cmd in commands:
        if not getattr(getattr(cmd, "callback", None), "__em_cmd__", False):
            continue
        if cmd.name in seen:
            continue
        seen.add(cmd.name)
        guild_cmd = client.tree.get_command(cmd.name, guild=STAFF_GUILD) or cmd
        cmd_id = getattr(guild_cmd, "id", None)
        if not cmd_id:
            failed.append(f"{cmd.name}: could not get the command ID (re-run after syncing)")
            continue
        try:

            await client.http.edit_application_command_permissions(app_id, STAFF_GUILD_ID, cmd_id, {"permissions": []})
            cleared.append(cmd.name)
        except Exception as e:
            failed.append(f"{cmd.name}: {e}")

    if cleared:
        print(f"[Command visibility] Cleared Integrations role overrides -> visible to everyone: "
              f"{', '.join(sorted(cleared))}")
    elif not HIDE_EVENT_MANAGER_COMMANDS:
        print("[Command visibility] Event-manager commands are visible to everyone (no role overrides to clear).")
    if failed:
        warnings.append("Could not reset permissions for the old-version commands: " + "; ".join(failed))
        warnings.append("Open \"Server Settings > Integrations > this Bot > Commands\" manually,"
                        "and reset the role permissions for each command.")
    return warnings

async def notify_loa_role_failure(user_id: int, member, error, phase: str, role_ids=None):
    try:
        channel = client.get_channel(LOA_TRACK_CHANNEL_ID) or await client.fetch_channel(LOA_TRACK_CHANNEL_ID)
        user_label = member.mention if member else f"<@{user_id}>"
        phase_label = "LOA activation" if phase == "start" else "LOA restoration"
        sections = [
            ("User", f"{user_label} (`{user_id}`)"),
            ("Operation", phase_label),
            ("Error", f"`{str(error)[:300]}`"),
            ("Required action", "Automatic retry is disabled for this failure. Review the member's roles and restore them manually if needed. Ensure the bot's role is above all affected roles."),
        ]
        if role_ids:
            sections.append(("Affected roles", " ".join(f"<@&{role_id}>" for role_id in role_ids)[:1024]))
        await channel.send(
            view=build_v2_card("LOA Role Update Failed", sections, color=0xB23B3B,
                               content=f"<@&{ADMIN_ROLE_ID}>"),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
    except Exception as exc:
        print(f"LOA failure notice could not be sent: {exc}")

async def _persist_loa_failure(user_id: int, stage: str):
    try:
        if not await save_loa_tracking():
            print(f"[LOA] Could not persist {stage} failure for user {user_id}; record remains in memory.")
    except Exception as exc:
        print(f"[LOA] Could not persist {stage} failure for user {user_id}: {exc}")


async def activate_loa(user_id: int, guild: discord.Guild):
    global global_db_dirty
    loa_data = LOA_CACHE.get(str(user_id))
    if not isinstance(loa_data, dict):
        print(f"LOA Activation aborted: no valid record for user {user_id}")
        return False

    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except Exception as e:
            print(f"Could not fetch member {user_id} for LOA activation: {e}")
            loa_data["status"] = "activation_failed"
            loa_data["role_change_error"] = f"member_fetch_failed: {str(e)[:160]}"
            await _persist_loa_failure(user_id, "activation")
            await notify_loa_role_failure(user_id, None, e, "start", loa_data.get("original_role_ids", []))
            return False

    loa_role = guild.get_role(LOA_ROLE_ID)
    if loa_role is None:
        err = f"LOA role {LOA_ROLE_ID} was not found in guild {guild.id}"
        print(err)
        loa_data["status"] = "activation_failed"
        loa_data["role_change_error"] = err[:200]
        await _persist_loa_failure(user_id, "activation")
        await notify_loa_role_failure(user_id, member, err, "start", [])
        return False


    roles_to_remove = [r for r in member.roles if r.id != guild.default_role.id and r.id != LOA_ROLE_ID and not r.managed and not r.is_premium_subscriber()]



    if not loa_data.get("original_role_ids"):
        loa_data["original_role_ids"] = [r.id for r in roles_to_remove]
        loa_data["original_nick"] = member.nick
    loa_data["activation_started_at"] = int(datetime.datetime.now(JST).timestamp())

    try:
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="LOA System: Leave Start")
        if loa_role not in member.roles:
            await member.add_roles(loa_role, reason="LOA System: Leave Start")

        end_ts = loa_data.get("end_timestamp")
        if end_ts:
            end_dt = datetime.datetime.fromtimestamp(float(end_ts), tz=JST)
            new_nick = f"LOA ~{end_dt.strftime('%y/%m/%d')}"
            if len(new_nick) <= 32:
                await member.edit(nick=new_nick, reason="LOA System: Leave Start")

        loa_data["status"] = "active"
        loa_data.pop("role_change_error", None)


        for flight in FLIGHT_LOG_CACHE:
            modified = False
            for list_key in ("accepted_users", "declined_users"):
                values = flight.get(list_key, [])
                if isinstance(values, list) and user_id in values:
                    values.remove(user_id)
                    modified = True
            if modified:
                global_db_dirty = True
                try:
                    s_ch = client.get_channel(flight.get("staff_channel_id"))
                    if s_ch:
                        msg = await s_ch.fetch_message(flight["staff_message_id"])
                        await update_staff_embed_ui(msg, flight, guild)
                except Exception as e:
                    print(f"LOA flight UI update failed for {user_id}: {e}")
        return True
    except Exception as e:

        loa_data["role_change_error"] = str(e)[:200]
        loa_data["status"] = "activation_failed"
        print(f"LOA Activation Error for {user_id}: {e}")
        await _persist_loa_failure(user_id, "activation")
        await notify_loa_role_failure(user_id, member, e, "start", [r.id for r in roles_to_remove])
        return False

async def approved_my_flight_app_autocomplete(interaction: discord.Interaction, current: str):
    choices = []
    app_channel = interaction.client.get_channel(FLIGHT_APP_CHANNEL_ID)
    now = datetime.datetime.now().timestamp()
    
    if app_channel:
        try:
            async for msg in app_channel.history(limit=50):
                if msg.author.bot and msg.embeds:
                    embed = msg.embeds[0]
                    title = embed.title or ""

                    if "Approved" in title:
                        desc = embed.description or ""

                        ho_m = re.search(r'\*\*Host:\*\*\s*<@!?(\d+)>', desc)
                        if ho_m and int(ho_m.group(1)) == interaction.user.id:
                            fc_m = re.search(r'\*\*Flight Code:\*\*\s*(.+)', desc)
                            or_m = re.search(r'\*\*Origin:\*\*\s*(.+)', desc)
                            if fc_m and or_m:
                                fc = fc_m.group(1).strip()
                                origin = or_m.group(1).strip()
                                


                                is_already_active = any(f["flight_code"].lower() == fc.lower() and f.get("end_timestamp", 0) > now for f in FLIGHT_LOG_CACHE)
                                
                                if not is_already_active and current.lower() in fc.lower():
                                    choices.append(app_commands.Choice(name=f"{fc} | {origin} (Approved)", value=str(msg.id)))
        except Exception as e:
            print(f"Autocomplete error: {e}")
            
    if not choices:
        choices.append(app_commands.Choice(name="No approved applications available", value="none"))
        
    return choices[:25]

async def deactivate_loa(user_id: int, guild: discord.Guild):
    member = guild.get_member(user_id)
    loa_data = LOA_CACHE.get(str(user_id))
    if not isinstance(loa_data, dict):
        return False
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception as e:
            loa_data["status"] = "restore_failed"
            loa_data["role_restore_error"] = f"member_fetch_failed: {str(e)[:160]}"
            print(f"LOA Deactivation could not fetch member {user_id}: {e}")
            await _persist_loa_failure(user_id, "restoration")
            await notify_loa_role_failure(user_id, None, e, "end", loa_data.get("original_role_ids", []))
            return False

    try:
        role_ids = loa_data.get("original_role_ids", [])
        if not isinstance(role_ids, list):
            raise ValueError("original_role_ids is not a list")
        roles_to_add = [guild.get_role(rid) for rid in role_ids if guild.get_role(rid)]
        missing_roles = [rid for rid in role_ids if guild.get_role(rid) is None]
        loa_role = guild.get_role(LOA_ROLE_ID)

        if loa_role and loa_role in member.roles:
            await member.remove_roles(loa_role, reason="LOA System: Leave End")
        if roles_to_add:
            await member.add_roles(*roles_to_add, reason="LOA System: Leave End")


        original_nick = loa_data.get("original_nick")
        if member.nick and member.nick.startswith("LOA ~"):
            await member.edit(nick=original_nick, reason="LOA System: Leave End")

        if missing_roles:

            loa_data["missing_role_ids"] = missing_roles
            loa_data["status"] = "restore_partial"
            loa_data["role_restore_error"] = f"Missing original role IDs: {missing_roles}"
            print(f"LOA restore for {user_id} was partial; missing roles {missing_roles}")
            await notify_loa_role_failure(user_id, member, loa_data["role_restore_error"], "end", missing_roles)
            await save_loa_tracking()
            return False

        loa_data["status"] = "restored"
        loa_data.pop("role_restore_error", None)
        del LOA_CACHE[str(user_id)]
        if not await save_loa_tracking():

            LOA_CACHE[str(user_id)] = loa_data
            loa_data["status"] = "restore_persistence_failed"
            loa_data["role_restore_error"] = "Discord backup save failed after role restoration"
            print(f"LOA restore persistence failed for {user_id}; record retained in memory")
            return False
        return True
    except Exception as e:
        loa_data["role_restore_error"] = str(e)[:200]
        loa_data["status"] = "restore_failed"
        print(f"LOA Deactivation Error for {user_id}: {e}")
        await _persist_loa_failure(user_id, "restoration")
        await notify_loa_role_failure(user_id, member, e, "end", loa_data.get("original_role_ids", []))
        return False






def get_embed_color(hex_str):
    if not hex_str:
        return EMBED_COLOR
    try:
        clean_str = hex_str.replace("#", "").strip()[:6]
        color_int = int(clean_str, 16)
        return min(color_int, 16777215)
    except:
        return EMBED_COLOR

def disable_view_items(view):
    def _walk(items):
        for item in items:
            if hasattr(item, "disabled"):
                item.disabled = True
            children = getattr(item, "children", None)
            if children:
                _walk(children)
    _walk(view.children)


def create_info_embed(title, description, color=None):
    return discord.Embed(title=title, description=description, color=EMBED_COLOR if color is None else color)


def build_google_calendar_url(flight: dict, start_ts=None, end_ts=None) -> str:
    try:
        start = int(start_ts if start_ts is not None else (flight.get("start_timestamp") or 0))
        end = int(end_ts if end_ts is not None else (flight.get("end_timestamp") or 0))
        if start <= 0:
            start = int(flight.get("start_timestamp") or 0)
        if start <= 0:
            return ""
        if end <= start:
            end = start + 3600
        fmt = lambda ts: datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        code = str(flight.get("flight_code", "Flight")).strip()
        origin = flight.get("origin") or ""
        destination = flight.get("destination") or ""
        title = f"{code} {origin}→{destination}".strip()
        details = ["Flight Hub"]
        if flight.get("event_url"):
            details.append(f"Discord event: {flight['event_url']}")
        params = {"action": "TEMPLATE", "text": title, "dates": f"{fmt(start)}/{fmt(end)}",
                  "details": "\n".join(details)}
        if origin:
            params["location"] = origin
        return "https://calendar.google.com/calendar/render?" + urlencode(params)
    except Exception:
        return ""


def google_calendar_suffix(flight: dict, start_ts=None) -> str:
    brief = start_ts if start_ts is not None else flight.get("staff_timestamp")
    url = build_google_calendar_url(flight, start_ts=brief, end_ts=flight.get("end_timestamp"))
    return f" [+]({url})" if url else ""


def generate_schedule_embed(active_flights, is_staff=False):
    active_flights.sort(key=lambda x: x["start_timestamp"])

    if not active_flights:
        embed = discord.Embed(
            title=f"{EMOJI_BRAND_STR} Flight Schedule",
            description="No upcoming flights scheduled.",
            color=EMBED_COLOR
        )
        embed.set_footer(text="Flight Hub")
        return embed

    grouped_flights = {}
    for f in active_flights:
        dt = datetime.datetime.fromtimestamp(f["start_timestamp"], tz=JST)
        date_key = dt.strftime("%Y-%m-%d")
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        tomorrow_str = (datetime.datetime.now(JST) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        start_ts_temp = int(f["start_timestamp"])
        if date_key == today_str:
            header_label = f"Today — <t:{start_ts_temp}:D>"
        elif date_key == tomorrow_str:
            header_label = f"Tomorrow — <t:{start_ts_temp}:D>"
        else:
            header_label = f"<t:{start_ts_temp}:D>"
        if header_label not in grouped_flights:
            grouped_flights[header_label] = []
        grouped_flights[header_label].append(f)

    description = ""
    for header, flights in grouped_flights.items():
        description += f"**{header}**\n"
        for f in flights:
            flight_code = f["flight_code"]

            display_flight_code = flight_code

            origin = f.get("origin", "???")
            destination = f.get("destination", "???")
            start_ts = int(f["start_timestamp"])
            end_ts = int(f["end_timestamp"])
            aircraft = f.get("equipment", "Unknown")
            event_url = f.get("event_url", "")
            airline = f.get("airline") or default_airline()
            staff_msg_id = f.get("staff_message_id")

            if not is_staff:
                if event_url:
                    fc_display = f"**[{display_flight_code}]({event_url})**"
                else:
                    fc_display = f"**{display_flight_code}**"
                
                description += f"{fc_display} `{airline}`\n"
                description += f"  {origin} ➝ {destination}\n"
                
                description += f"  <t:{start_ts}:t> – <t:{end_ts}:t>\n"
                description += f"  {aircraft}\n"
            else:
                description += f"{EMOJI_BAGGAGE_STR} **{display_flight_code}** `{airline}`\n"
                description += f"  {origin} ➝ {destination}\n"
                
                description += f"  <t:{start_ts}:t> – <t:{end_ts}:t>\n"
                description += f"  {aircraft}\n"
                if staff_msg_id:
                    staff_link = f"https://discord.com/channels/{STAFF_GUILD_ID}/{STAFF_CHANNEL_ID}/{staff_msg_id}"
                    description += f"  [⇒ Details]({staff_link})\n"
            description += "\n"

    description = description.strip()


    if len(description) > 4000:
        description = description[:4000].rstrip() + "\n… (truncated)"

    embed = discord.Embed(
        title=f"{EMOJI_BRAND_STR} Flight Schedule",
        description=description,
        color=EMBED_COLOR
    )
    embed.set_footer(text="Flight Hub")
    return embed









_ROLE_TO_DEPARTMENT = {}
for _dept, _roles in {
    "Flight Crew": ["captain", "first officer", "co-pilot", "copilot", "pilot", "fo",
                    "\u6a5f\u9577", "\u526f\u64cd\u7e26\u58eb"],
    "Cabin Crew": ["first class", "business class", "premium economy", "premium economy class", "economy class", "economy",

                   "receptionist", "reception", "airport guide", "gate agent", "lounge agent",
                   "\u53d7\u4ed8\u62c5\u5f53", "\u7a7a\u6e2f\u6848\u5185", "\u642d\u4e57\u53e3\u62c5\u5f53", "\u642d\u4e57\u53e3", "\u30e9\u30a6\u30f3\u30b8\u4fc2"],
    "Ground Crew": ["mr", "crew", "ground crew", "gc supervisor", "gc"],
}.items():
    for _r in _roles:
        _ROLE_TO_DEPARTMENT[_r] = _dept

def role_to_department(pos):
    if not pos:
        return pos
    key = re.sub(r"\s*[\(\uff08].*?[\)\uff09]", "", str(pos)).strip().lower()
    return _ROLE_TO_DEPARTMENT.get(key, pos)

PROFILE_EXPORT_USE_DEPARTMENT = True


def parse_log_message(msg):

    content = msg.content
    if msg.embeds:
        for e in msg.embeds:
            content += f"\n{e.title}\n{e.description}\n"
            for f in e.fields:
                content += f"\n{f.name}\n{f.value}\n"

    if not any(keyword in content for keyword in ["Flight-log", "Manual-log", "Flight Backup"]):
        return None
    
    flight_code = "Unknown"
    flight_type = None
    host_id = None
    participants = {}
    

    clean_content = re.sub(r'<a?:[^:]+:(\d+)>', '', content)
    

    all_users = re.findall(r'<@!?(\d+)>', clean_content)
    all_raw_ids = re.findall(r'\b(\d{17,19})\b', clean_content)
    for u in all_users + all_raw_ids:
        participants[int(u)] = "Participant"
        
    lines = clean_content.split('\n')
    for line in lines:
        if line.startswith(" | "):
            flight_code = line.replace(" | ", "").strip()
        elif re.search(r"\|\s*.+?\s*(?:Flight-log|Manual-log|Flight Backup)", line):

            _m = re.search(r"\|\s*(.+?)\s*(?:Flight-log|Manual-log|Flight Backup)", line)
            if _m:
                flight_code = _m.group(1).replace("*", "").strip()
        elif "Flight Code:" in line:
            flight_code = line.split("Flight Code:")[1].strip().replace("*", "")
        elif line.replace("> ", "").strip().lower().startswith("flight type:"):
            flight_type = line.split(":", 1)[1].strip().replace("*", "")
            continue
            
        if ":" in line:
            parts = line.replace("> ", "").split(":", 1)
            if len(parts) == 2:
                pos = parts[0].strip()
                users = re.findall(r'<@!?(\d+)>', parts[1])
                users += re.findall(r'\b(\d{17,19})\b', parts[1])
                for u in users:
                    participants[int(u)] = pos
                if "Host" in pos and users:
                    host_id = int(users[0])
                    
    return {
        "timestamp": msg.created_at.timestamp(),
        "flight_code": flight_code.replace("*", ""),
        "flight_type": flight_type,
        "host_id": host_id,
        "participants": participants
    }


async def auto_publish_schedule():
    try:
        now_ts = datetime.datetime.now().timestamp()
        

        active_flights_staff = [f for f in FLIGHT_LOG_CACHE if f["end_timestamp"] > now_ts and not f.get("is_test")]

        active_flights_customer = [f for f in active_flights_staff if not f.get("pending_customer_msg") and not f.get("is_gamenight") and not f.get("is_private")]



        c_ch = client.get_channel(CUSTOMER_CHANNEL_ID)


        if c_ch is None:
            try:
                c_ch = await client.fetch_channel(CUSTOMER_CHANNEL_ID)
            except Exception as e:
                print(f"Failed to fetch the customer channel: {e}")


        if c_ch:

            existing_msg_c = None

            async for msg in c_ch.history(limit=50):
                if msg.author == client.user and msg.embeds and "Flight Schedule" in str(msg.embeds[0].title):
                    if existing_msg_c is None:
                        existing_msg_c = msg
                    else:

                        try:
                            await msg.delete()
                        except Exception as e:

                            print(f"Failed to delete the schedule message: {e}")


            if len(active_flights_customer) >= 2:
                new_embed_c = generate_schedule_embed(active_flights_customer, is_staff=False)
                

                last_msg_c = None
                async for msg in c_ch.history(limit=1):
                    last_msg_c = msg


                if existing_msg_c and last_msg_c and existing_msg_c.id == last_msg_c.id:
                    try:
                        await existing_msg_c.edit(embed=new_embed_c)
                    except:
                        pass
                else:

                    if existing_msg_c:
                        try:
                            await existing_msg_c.delete()
                        except:
                            pass
                    try:
                        await c_ch.send(embed=new_embed_c)
                    except:
                        pass
            else:

                if existing_msg_c:
                    try:
                        await existing_msg_c.delete()
                    except:
                        pass


        s_ch = client.get_channel(STAFF_CHANNEL_ID)
        if s_ch:
            existing_msg_s = None
            async for msg in s_ch.history(limit=50):
                if msg.author == client.user and msg.embeds and "Flight Schedule" in str(msg.embeds[0].title):
                    if existing_msg_s is None:
                        existing_msg_s = msg
                    else:
                        try:
                            await msg.delete()
                        except Exception as e:

                            print(f"Failed to delete the schedule message: {e}")


            if len(active_flights_staff) >= 2:
                new_embed_s = generate_schedule_embed(active_flights_staff, is_staff=True)
                

                last_msg_s = None
                async for msg in s_ch.history(limit=1):
                    last_msg_s = msg

                if existing_msg_s and last_msg_s and existing_msg_s.id == last_msg_s.id:
                    try:
                        await existing_msg_s.edit(embed=new_embed_s)
                    except:
                        pass
                else:
                    if existing_msg_s:
                        try:
                            await existing_msg_s.delete()
                        except:
                            pass
                    try:
                        await s_ch.send(embed=new_embed_s)
                    except:
                        pass
            else:
                if existing_msg_s:
                    try:
                        await existing_msg_s.delete()
                    except:
                        pass

    except Exception as e:
        print(f"Schedule Auto Publish Error: {e}")

async def init_log_cache():
    global FLIGHT_LOG_CACHE, global_db_dirty


    found, data = await read_latest_json_backup(FLIGHT_LOG_CHANNEL_ID, limit=100,
                                                exclude_prefixes=("flight_log_pre_restore_",))
    if not found:
        print("DB Cache: no existing backup found. Starting fresh.")
        FLIGHT_LOG_CACHE = []
        return
    if not isinstance(data, list):
        raise LoadError("flight_log backup has an unexpected format (expected a list)")


    if FLIGHT_LOG_CHANNEL_ID in LOAD_UNSAFE_CHANNELS and FLIGHT_LOG_CACHE:
        known = {f.get("flight_code") for f in data if isinstance(f, dict)}
        for f in FLIGHT_LOG_CACHE:
            if f.get("flight_code") not in known:
                data.append(f)
                global_db_dirty = True

    FLIGHT_LOG_CACHE = data

    changed = sum(1 for f in FLIGHT_LOG_CACHE if migrate_flight_record(f))
    if changed:
        global_db_dirty = True
    print(f"DB Cache Loaded: {len(FLIGHT_LOG_CACHE)} active flights ({changed} converted to V14 format).")

async def _save_json_to_channel_unlocked(channel_id, data, filename):
    if channel_id in LOAD_UNSAFE_CHANNELS:
        _warn_save_blocked(channel_id, filename)
        return False

    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception as e:
            print(f"[JSON SAVE] Channel fetch failed for {filename} ({channel_id}): {e}")
            return False

    try:
        json_bytes = json.dumps(data, indent=4, ensure_ascii=False).encode("utf-8")
        content = f"Log Updated: <t:{int(datetime.datetime.now().timestamp())}:R>"


        existing_messages = []
        async for message in channel.history(limit=100):
            if (message.author == client.user
                    and any(a.filename == filename for a in message.attachments)):
                existing_messages.append(message)
        existing_messages.sort(key=lambda m: m.created_at, reverse=True)
        target = existing_messages[0] if existing_messages else None

        if target is not None:


            replacement = discord.File(io.BytesIO(json_bytes), filename=filename)
            try:
                await target.edit(
                    content=content,
                    attachments=[replacement],
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                saved_message = target
            except Exception as edit_error:
                print(f"[JSON SAVE] Overwrite failed for {filename} ({channel_id}); no duplicate was posted: {edit_error}")
                traceback.print_exc()
                return False
        else:
            try:
                file = discord.File(io.BytesIO(json_bytes), filename=filename)
                saved_message = await channel.send(
                    content=content, file=file,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except Exception as e:
                print(f"[JSON SAVE] Upload failed for {filename} ({channel_id}): {e}")
                traceback.print_exc()
                return False


        cleanup_errors = []
        for message in existing_messages:
            if message.id == saved_message.id:
                continue
            try:
                await message.delete()
            except Exception as e:
                cleanup_errors.append(f"message {message.id}: {e}")
        if cleanup_errors:
            print(f"[JSON SAVE] {filename} was saved, but duplicate cleanup was incomplete: "
                  + " | ".join(cleanup_errors[:5]))
        return True

    except Exception as e:
        print(f"[JSON SAVE] Unexpected save error for {filename} ({channel_id}): {e}")
        traceback.print_exc()
        return False



_JSON_SAVE_LOCKS = {}

async def save_json_to_channel(channel_id, data, filename):
    key = (int(channel_id), str(filename))
    lock = _JSON_SAVE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _JSON_SAVE_LOCKS[key] = lock
    async with lock:
        return await _save_json_to_channel_unlocked(channel_id, data, filename)








class LoadError(Exception):
    pass

SCHEMA_VERSION = 14
LOAD_UNSAFE_CHANNELS = set()
LOAD_STATUS = {}
LOAD_STATE = {"initialized": False, "retry_running": False}
LOAD_RETRY_DELAYS = (2, 5, 10)
_SAVE_BLOCK_WARNED = {}

def _warn_save_blocked(channel_id, filename):
    now = datetime.datetime.now().timestamp()
    if now - _SAVE_BLOCK_WARNED.get(channel_id, 0) > 60:
        _SAVE_BLOCK_WARNED[channel_id] = now
        print(f"Save blocked: '{filename}' (channel {channel_id}) was not loaded successfully yet. "
              f"Existing backup is protected; the bot keeps retrying the load.")

async def _get_channel_strict(channel_id):
    ch = client.get_channel(channel_id)
    if ch:
        return ch
    try:
        return await client.fetch_channel(channel_id)
    except Exception as e:
        raise LoadError(f"Channel {channel_id} is unreachable: {e}")

async def read_latest_json_backup(channel_id, filename=None, limit=100, exclude_prefixes=()):
    ch = await _get_channel_strict(channel_id)
    candidates = 0
    last_err = None
    try:
        async for message in ch.history(limit=limit):
            if message.author != client.user or not message.attachments:
                continue
            att = message.attachments[0]
            if filename and att.filename != filename:
                continue
            if exclude_prefixes and att.filename.startswith(tuple(exclude_prefixes)):
                continue
            candidates += 1
            try:
                raw = await att.read()
                return True, json.loads(raw.decode("utf-8"))
            except Exception as e:
                last_err = e
                print(f"Backup '{att.filename}' in channel {channel_id} is unreadable ({e}). Trying an older one...")
    except Exception as e:
        raise LoadError(f"Could not read history of channel {channel_id}: {e}")
    if candidates:
        raise LoadError(f"{candidates} backup(s) found in channel {channel_id} but none was readable: {last_err}")
    return False, None

def migrate_flight_record(f) -> bool:
    if not isinstance(f, dict):
        return False
    changed = False

    def setdef(key, value):
        nonlocal changed
        if key not in f:
            f[key] = value
            changed = True

    now_ts = datetime.datetime.now().timestamp()


    if "origin" not in f:
        f["origin"] = "Game Night"
        f["destination"] = "Event"
        f["equipment"] = "Game"
        f["classes"] = "Staff Only"
        changed = True


    setdef("is_private", False)
    setdef("no_mention", False)


    start = f.get("start_timestamp") or 0
    if start:
        setdef("end_timestamp", start + 3600)
        setdef("staff_timestamp", start)
    staff = f.get("staff_timestamp") or 0
    if staff:
        setdef("notify_20min_timestamp", staff - 1200)
        setdef("notified_20min", now_ts >= staff)
        setdef("staff_start_notified", now_ts >= staff)




    if (f.get("is_gamenight") and f.get("notified_20min") and not f.get("briefing_thread_id")
            and not f.get("flight_channels_created") and not f.get("messages_deleted")
            and (f.get("start_timestamp") or 0) > now_ts and f.get("notify_20min_attempts", 0) < 3):
        f["notified_20min"] = False
        f["notify_20min_timestamp"] = (f.get("staff_timestamp") or f.get("start_timestamp") or 0) - 1200
        changed = True



    _end = f.get("end_timestamp") or 0
    setdef("flight_log_missing_notified", bool(_end and _end + 600 <= now_ts))
    setdef("messages_deleted_by_cancel", False)

    setdef("accepted_users", [])
    setdef("declined_users", [])
    setdef("pending_customer_msg", False)
    setdef("customer_msg_timestamp", 0)
    setdef("messages_deleted", False)
    setdef("briefing_sent", False)
    setdef("flight_log_sent", False)
    if not f.get("is_test"):
        setdef("staff_guild_id", STAFF_GUILD_ID)
        setdef("staff_channel_id", STAFF_CHANNEL_ID)
        setdef("customer_guild_id", CUSTOMER_GUILD_ID)
        setdef("customer_channel_id", CUSTOMER_CHANNEL_ID)

    if f.get("schema_version") != SCHEMA_VERSION:
        f["schema_version"] = SCHEMA_VERSION
        changed = True
    return changed

def _mention_tokens():
    toks = {f"<@&{NOTIFICATION_ROLE_ID}>"}
    for f in FLIGHT_LOG_CACHE:
        m = f.get("mention_str")
        if m:
            toks.add(m)
    return toks

def predict_pending_announcements():
    limit = MENTION_SPACING_HOURS * 3600
    now_ts = datetime.datetime.now().timestamp()
    clock = LAST_CUSTOMER_MENTION_TS
    pend = [f for f in FLIGHT_LOG_CACHE if f.get("pending_customer_msg") and not f.get("messages_deleted")]
    pend.sort(key=lambda f: (max(f.get("customer_msg_timestamp", 0) or 0, now_ts), f.get("start_timestamp", 0)))
    out = []
    for f in pend:
        t = max(f.get("customer_msg_timestamp", 0) or 0, now_ts)
        content = f.get("customer_msg_content", "") or ""
        has_mention = any(tok in content for tok in _mention_tokens())
        will = False
        if has_mention and (t - clock) >= limit:
            will = True
            clock = t
        out.append({"code": f.get("flight_code", "?"), "ts": int(t), "mention": will})
    return out

async def v14_upgrade_data():
    global global_db_dirty, LAST_CUSTOMER_MENTION_TS
    report = {"total": len(FLIGHT_LOG_CACHE), "migrated": 0, "threads": 0, "mention_restored": 0,
              "last_mention": 0, "warnings": []}
    now_ts = datetime.datetime.now().timestamp()


    _changed = set()
    for f in FLIGHT_LOG_CACHE:
        if migrate_flight_record(f):
            _changed.add(id(f))
    report["migrated"] = len(_changed)


    report["routes"] = 0
    if FLIGHT_DB:
        for f in FLIGHT_LOG_CACHE:
            try:
                if f.get("route_changed_at") and not f.get("route_code"):
                    rc = resolve_template_code(f)
                    if rc:
                        f["route_code"] = rc
                        report["routes"] += 1
                        _changed.add(id(f))
            except Exception:
                traceback.print_exc()
    report["migrated"] = len(_changed)
    if report["migrated"]:
        global_db_dirty = True


    for f in FLIGHT_LOG_CACHE:
        try:
            if (f.get("notified_20min") and not f.get("briefing_thread_id")
                    and not f.get("is_gamenight") and f.get("staff_message_id")
                    and now_ts < (f.get("staff_timestamp") or 0)):
                ch = client.get_channel(f.get("staff_channel_id"))
                if ch:
                    msg = await ch.fetch_message(f["staff_message_id"])
                    th = getattr(msg, "thread", None)
                    if th:
                        f["briefing_thread_id"] = th.id
                        report["threads"] += 1
                        global_db_dirty = True
        except Exception:
            pass


    for f in FLIGHT_LOG_CACHE:
        try:
            if (f.get("customer_message_id") and not f.get("mention_backfilled")
                    and not (f.get("is_private") or f.get("is_test") or f.get("is_gamenight"))):
                ch = client.get_channel(f.get("customer_channel_id", CUSTOMER_CHANNEL_ID))
                if not ch:
                    continue
                msg = await ch.fetch_message(f["customer_message_id"])
                mention = f.get("mention_str", f"<@&{NOTIFICATION_ROLE_ID}>")
                if mention and mention in (msg.content or ""):
                    f["mention_sent_ts"] = msg.created_at.timestamp()
                    f["no_mention"] = False
                    report["mention_restored"] += 1
                else:
                    f["no_mention"] = True
                f["mention_backfilled"] = True
                global_db_dirty = True
        except Exception:
            pass


    if not await refresh_mention_clock_from_history():
        report["warnings"].append("Customer channel history could not be read (mention clock may be incomplete).")
    latest = LAST_CUSTOMER_MENTION_TS

    best = max([LAST_CUSTOMER_MENTION_TS, latest] + [f.get("mention_sent_ts", 0) or 0 for f in FLIGHT_LOG_CACHE])
    if best > LAST_CUSTOMER_MENTION_TS:
        LAST_CUSTOMER_MENTION_TS = best
        try:
            await save_misc_data()
        except Exception as e:
            report["warnings"].append(f"Could not save mention clock: {e}")
    report["last_mention"] = LAST_CUSTOMER_MENTION_TS


    for f in FLIGHT_LOG_CACHE:
        if f.get("pending_customer_msg") and not f.get("customer_msg_content"):
            report["warnings"].append(f"{f.get('flight_code')}: scheduled announcement body is empty")
    return report

def verify_loaded_data():
    warns = []
    seen = set()
    for f in FLIGHT_LOG_CACHE:
        code = f.get("flight_code", "?")
        if code in seen:
            warns.append(f"{code}: duplicated flight code")
        seen.add(code)
        for k in ("start_timestamp", "end_timestamp", "host_id"):
            if not f.get(k):
                warns.append(f"{code}: missing `{k}`")
        if f.get("schema_version") != SCHEMA_VERSION:
            warns.append(f"{code}: not converted to V14 yet")
        if f.get("route_changed_at") and not f.get("route_code") and FLIGHT_DB:
            warns.append(f"{code}: route changed but route_code could not be determined")
        if not f.get("staff_message_id") and not f.get("queued_for_limit"):
            warns.append(f"{code}: no staff message ID")
        if (not f.get("is_test") and not f.get("is_gamenight") and not f.get("is_private")
                and not f.get("queued_for_limit") and not f.get("messages_deleted")
                and not f.get("customer_message_id") and not f.get("pending_customer_msg")):
            warns.append(f"{code}: customer announcement is neither posted nor scheduled")
    if not isinstance(remind_tracking_cache, dict) or "users" not in remind_tracking_cache:
        warns.append("Remind tracking data has an unexpected format")
    for ev in EVALUATION_CACHE:
        if not isinstance(ev, dict) or "send_timestamp" not in ev or "target_id" not in ev:
            warns.append("Evaluation queue has an entry without send_timestamp/target_id")
            break
    if not FLIGHT_DB:
        warns.append("Flight templates (FLIGHT_DB) is empty")
    return warns[:15]

def _loader_specs():
    return [
        ("Flight log (DB)", init_log_cache, FLIGHT_LOG_CHANNEL_ID),
        ("Flight templates", (lambda: update_db_cache(strict=True)), None),
        ("Remind tracking", load_remind_tracking, REMIND_TRACK_CHANNEL_ID),
        ("LOA data", load_loa_tracking, LOA_TRACK_CHANNEL_ID),
        ("Misc data", load_misc_data, MISC_DATA_CHANNEL_ID),
        ("Evaluations", load_eval_tracking, EVAL_TRACK_CHANNEL_ID),
    ]

async def _run_loader(name, fn, channel_id=None):
    last_err = None
    attempts = len(LOAD_RETRY_DELAYS) + 1
    for attempt in range(1, attempts + 1):
        try:
            await fn()
            LOAD_STATUS[name] = {"ok": True, "detail": "OK", "attempts": attempt}
            if channel_id:
                LOAD_UNSAFE_CHANNELS.discard(channel_id)
            return True
        except Exception as e:
            last_err = e
            print(f"[{name}] load attempt {attempt}/{attempts} failed: {e}")
            if attempt < attempts:
                await asyncio.sleep(LOAD_RETRY_DELAYS[attempt - 1])
    LOAD_STATUS[name] = {"ok": False, "detail": str(last_err)[:200], "attempts": attempts}
    if channel_id:
        LOAD_UNSAFE_CHANNELS.add(channel_id)
    return False

async def load_all_data(only_failed=False):
    specs = _loader_specs()
    if only_failed:
        specs = [sp for sp in specs if not LOAD_STATUS.get(sp[0], {}).get("ok")]
    if specs:
        await asyncio.gather(*[_run_loader(*sp) for sp in specs])
    return LOAD_STATUS

def load_problems():
    return {k: v for k, v in LOAD_STATUS.items() if not v.get("ok")}

async def report_load_problems(title="Data load problem"):
    bad = load_problems()
    if not bad:
        return
    text = title + "\n" + "\n".join(f"• **{k}** — {v['detail']}" for k, v in bad.items())
    text += "\nSaving is paused for these to protect the stored data, and retrying automatically."
    print(text)
    try:
        ch = client.get_channel(AUDIT_LOG_CHANNEL_ID) or await client.fetch_channel(AUDIT_LOG_CHANNEL_ID)
        await ch.send(text[:1900], allowed_mentions=discord.AllowedMentions.none())
    except Exception as e:
        print(f"Load problem report could not be sent: {e}")

async def retry_failed_loads_forever():
    if LOAD_STATE["retry_running"]:
        return
    LOAD_STATE["retry_running"] = True
    try:
        while load_problems():
            await asyncio.sleep(60)
            before = list(load_problems().keys())
            await load_all_data(only_failed=True)
            recovered = [k for k in before if LOAD_STATUS.get(k, {}).get("ok")]
            if recovered:
                print(f"Recovered after retry: {', '.join(recovered)}")
                if "Flight log (DB)" in recovered:
                    try:
                        await v14_upgrade_data()
                    except Exception:
                        traceback.print_exc()
                try:
                    ch = client.get_channel(AUDIT_LOG_CHANNEL_ID) or await client.fetch_channel(AUDIT_LOG_CHANNEL_ID)
                    await ch.send("Data load recovered: " + ", ".join(recovered), allowed_mentions=discord.AllowedMentions.none())
                except Exception:
                    pass
    finally:
        LOAD_STATE["retry_running"] = False

def data_ready(*channel_ids):
    if not LOAD_STATE["initialized"]:
        return False
    return not any(cid in LOAD_UNSAFE_CHANNELS for cid in channel_ids)

async def wait_for_data(*channel_ids, timeout=900):
    waited = 0
    while not data_ready(*channel_ids) and waited < timeout:
        await asyncio.sleep(10)
        waited += 10
    return data_ready(*channel_ids)

def db_write_blocked_message():
    if FLIGHT_LOG_CHANNEL_ID in LOAD_UNSAFE_CHANNELS:
        return ("Flight data failed to load, so creation is temporarily disabled to protect the stored data. It is retrying automatically. Please try again in about a minute.\n"
                "Flight data could not be loaded yet, so creating flights is temporarily disabled to protect saved data. "
                "The bot is retrying automatically — please try again in a minute.")
    return None





async def log_audit(actor: discord.abc.User, action: str, detail: str = "", target: discord.abc.User = None, color: int = None):
    return






async def delete_flight_calendar_event(flight: dict) -> bool:
    url = (flight.get("event_url") or "").strip()
    if not url:
        return True
    parts = [x for x in url.split("?")[0].rstrip("/").split("/") if x]
    try:
        eid = int(parts[-1])
    except Exception:
        return False
    guild_ids = []
    try:
        guild_ids.append(int(parts[-2]))
    except Exception:
        pass
    staff_first = bool(flight.get("is_gamenight") or flight.get("is_test"))
    for gid in ([STAFF_GUILD_ID, CUSTOMER_GUILD_ID] if staff_first else [CUSTOMER_GUILD_ID, STAFF_GUILD_ID]):
        if gid not in guild_ids:
            guild_ids.append(gid)
    for gid in guild_ids:
        guild = client.get_guild(gid)
        if guild is None:
            continue
        try:
            event = await guild.fetch_scheduled_event(eid)
        except discord.NotFound:
            continue
        except Exception as e:
            print(f"Event fetch error ({flight.get('flight_code')}, guild {gid}): {e}")
            continue
        try:
            await event.delete()
            return True
        except discord.NotFound:
            return True
        except Exception as e:
            print(f"Event delete error ({flight.get('flight_code')}, guild {gid}): {e}")
            return False
    return True


async def delete_flight_staff_message(flight: dict):
    ch_id, msg_id = flight.get("staff_channel_id"), flight.get("staff_message_id")
    if not ch_id or not msg_id:
        return
    try:
        ch = client.get_channel(ch_id) or await client.fetch_channel(ch_id)
        msg = await ch.fetch_message(msg_id)
        await msg.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"Staff message delete error ({flight.get('flight_code')}): {e}")
    if flight.get("briefing_thread_id"):
        try:
            th = client.get_channel(flight["briefing_thread_id"]) or await client.fetch_channel(flight["briefing_thread_id"])
            await th.delete()
        except Exception:
            pass


def _resilient_task(func):
    @functools.wraps(func)
    async def _wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception:
            print(f"[task] unhandled exception in {func.__name__} (loop continues next cycle):")
            traceback.print_exc()
    return _wrapper


@tasks.loop(seconds=5)
@_resilient_task
async def quick_save_task():
    if _AUTO_TEST_PAUSE:
        return
    global global_db_dirty
    if global_db_dirty:
        async with global_json_lock:

            success = await save_json_to_channel(FLIGHT_LOG_CHANNEL_ID, FLIGHT_LOG_CACHE, "flight_log.json")
            if success:
                global_db_dirty = False

async def fetch_template_image_url(channel_id, message_id):
    if not channel_id or not message_id:
        return None
    for attempt in (1, 2):
        try:
            ch = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
            msg = await ch.fetch_message(message_id)
            if not msg.attachments:
                print(f"[image] template message has no attachment ({channel_id}/{message_id})")
                return None
            return msg.attachments[0].url
        except discord.NotFound:
            print(f"[image] template message not found ({channel_id}/{message_id})")
            return None
        except Exception as e:
            print(f"[image] template fetch error try {attempt} ({channel_id}/{message_id}): {e}")
            if attempt == 1:
                await asyncio.sleep(1)
    return None


async def fetch_fresh_image_info(channel_id, message_id):
    url = await fetch_template_image_url(channel_id, message_id)
    if not url:
        return None, None
    for attempt in (1, 2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return url, await resp.read()
                    print(f"[image] download status {resp.status} ({channel_id}/{message_id})")
        except Exception as e:
            print(f"[image] download error try {attempt} ({channel_id}/{message_id}): {e}")
        if attempt == 1:
            await asyncio.sleep(1)
    return None, None


async def fetch_image_for_update(channel_id, message_id):
    url, data = await fetch_fresh_image_info(channel_id, message_id)
    if not url:
        url = await fetch_template_image_url(channel_id, message_id)
    return url, data


_IMAGE_MAGIC_EXT = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


def guess_image_extension(data) -> str:
    if not data:
        return "png"
    for magic, ext in _IMAGE_MAGIC_EXT:
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def embed_image_as_attachment(embed, image_bytes, image_url, prefix="image"):
    if image_bytes:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(prefix)).strip("_") or "image"
        fname = f"{safe}.{guess_image_extension(image_bytes)}"
        embed.set_image(url=f"attachment://{fname}")
        return discord.File(io.BytesIO(image_bytes), filename=fname)
    if image_url:
        embed.set_image(url=image_url)
    return None

def parse_timezone_offset(tz_str):
    if not tz_str:
        return 9
    m = re.search(r'([+-])\s*(\d{1,2})(?::?(\d{2}))?', str(tz_str))
    if not m:
        return 9
    sign = -1 if m.group(1) == '-' else 1
    hours = int(m.group(2))
    minutes = int(m.group(3)) if m.group(3) else 0
    return sign * (hours + minutes / 60.0)

def calculate_jst_time(date_str, time_str, tz_offset_hours):
    full_str = f"{date_str} {time_str}".strip().upper()
    full_str = re.sub(r'\s+', ' ', full_str)
    formats = ['%Y-%m-%d %H:%M', '%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p',
               '%Y/%m/%d %H:%M', '%Y/%m/%d %I:%M %p', '%Y/%m/%d %I:%M%p']
    dt_naive = None
    for fmt in formats:
        try:
            dt_naive = datetime.datetime.strptime(full_str, fmt)
            break
        except ValueError:
            continue
    if not dt_naive:
        return None
    try:
        input_tz = datetime.timezone(datetime.timedelta(hours=tz_offset_hours))
        return dt_naive.replace(tzinfo=input_tz).astimezone(JST)
    except:
        return None

async def get_target_user(client_instance, target_str):
    user_id = None
    mention_match = re.match(r'<@!?(\d+)>', target_str)
    if mention_match:
        user_id = int(mention_match.group(1))
    elif target_str.isdigit():
        user_id = int(target_str)

    if user_id:
        user = client_instance.get_user(user_id)
        if not user:
            try:
                user = await client_instance.fetch_user(user_id)
            except discord.NotFound:
                return None
        return user

    user = discord.utils.get(client_instance.get_all_members(), name=target_str)
    if not user:
        user = discord.utils.get(client_instance.get_all_members(), display_name=target_str)
    if not user:
        user = discord.utils.get(client_instance.get_all_members(), global_name=target_str)

    return user

async def update_db_cache(strict=False):
    global FLIGHT_DB, FLIGHT_AUTOCOMPLETE_CACHE
    channel = client.get_channel(FLIGHT_INPUT_CHANNEL_ID)
    if not channel and strict:
        channel = await _get_channel_strict(FLIGHT_INPUT_CHANNEL_ID)
    if not channel:
        return
    temp_db = {}
    try:
        messages = [msg async for msg in channel.history(limit=500)]

        messages.sort(key=lambda m: (m.edited_at or m.created_at))

        for message in messages:
            if not message.content:
                continue
            lines = [l.strip().replace('>', '').replace('*', '').strip() for l in message.content.split('\n') if l.strip()]
            data = {}
            key_map = {"Origin": "origin", "Destination": "destination",
                       "Aircraft": "equipment", "Class": "classes",
                       "Airport": "roblox_link", "Airline": "airline",
                       "Color": "color"}
            
            flight_code = None

            for line in lines:
                if "Flight Information" in line:
                    continue

                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip()
                    val = val.strip()
                    if key in key_map:
                        data[key_map[key]] = val
                elif ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip()
                    val = val.strip()
                    if key in key_map:
                        data[key_map[key]] = val
                else:

                    if not flight_code and re.match(r'^[A-Za-z]{2,3}\d+$', line):
                        flight_code = line

            if flight_code and "equipment" in data:
                equipment_name = data["equipment"]

                if flight_code not in temp_db:
                    temp_db[flight_code] = {"origin": data.get("origin", "Unknown"),
                                            "destination": data.get("destination", "Unknown"), "variants": {}}

                if "origin" in data:
                    temp_db[flight_code]["origin"] = data["origin"]
                if "destination" in data:
                    temp_db[flight_code]["destination"] = data["destination"]

                if message.attachments:
                    temp_db[flight_code]["variants"][equipment_name] = {
                        "classes": data.get("classes", "Unknown"), "roblox_link": data.get("roblox_link", ""),
                        "airline": data.get("airline") or default_airline(), "color": data.get("color", "1B3444").replace("#", ""),
                        "source_channel_id": channel.id, "source_message_id": message.id,

                        "origin": data.get("origin"), "destination": data.get("destination"),
                    }



        for _code, _info in temp_db.items():
            _cur = ((_info.get("origin") or "").strip().lower(), (_info.get("destination") or "").strip().lower())
            for _eq in list(_info["variants"].keys()):
                _v = _info["variants"][_eq]
                _vo = (_v.get("origin") or "").strip().lower()
                _vd = (_v.get("destination") or "").strip().lower()

                _stale = bool(_vo) and _vo != _cur[0]
                if _vd and _vd != _cur[1]:
                    _stale = True
                if _stale and len(_info["variants"]) > 1:
                    print(f"[template] {_code}: '{_eq}' was registered for {_v.get('origin')}->{_v.get('destination')} "
                          f"but the latest route is {_info.get('origin')}->{_info.get('destination')}: skipped (stale)")
                    del _info["variants"][_eq]

        autocomplete_list = []
        for code, info in temp_db.items():
            equip_str = ", ".join(list(info["variants"].keys()))
            label = f"{code} | {info['origin']} ➝ {info['destination']}"
                
            autocomplete_list.append({
                "label": label[:100],
                "value": code[:100],
                "search": f"{code} {info['origin']} {info['destination']} {equip_str}".lower()
            })

        FLIGHT_DB = temp_db
        FLIGHT_AUTOCOMPLETE_CACHE = sorted(autocomplete_list, key=lambda x: x['value'])
        global _TEMPLATE_LAST_LOAD
        _TEMPLATE_LAST_LOAD = datetime.datetime.now().timestamp()
    except Exception as e:
        traceback.print_exc()
        if strict:
            raise LoadError(f"Flight template channel could not be parsed: {e}")

async def update_staff_embed_ui(message, flight_data, guild, embed=None, strict=False, image_file=None,
                                view=None, clear_attachments=False):
    if not message:
        return

    if embed is None:
        if not message.embeds:
            return
        embed = message.embeds[0]

    acc_ids = flight_data.get("accepted_users", [])
    dec_ids = flight_data.get("declined_users", [])


    _staff_guild = client.get_guild(flight_data.get("staff_guild_id") or STAFF_GUILD_ID)
    _name_guilds = [g for g in (_staff_guild, guild) if g is not None]


    async def get_safe_name(uid):
        for g in _name_guilds:
            member = g.get_member(uid)
            if member:
                return member.display_name

        for g in _name_guilds:
            try:
                member = await g.fetch_member(uid)
                return member.display_name
            except Exception:
                continue
        return f"User_{uid}"


    acc_names = [await get_safe_name(uid) for uid in acc_ids]
    dec_names = [await get_safe_name(uid) for uid in dec_ids]

    nl = "\n"
    acc_text = f">>> {nl.join(acc_names)}" if acc_names else "-"
    dec_text = f">>> {nl.join(dec_names)}" if dec_names else "-"


    host_id = flight_data.get("host_id")
    host_display = None
    if isinstance(host_id, int):
        try:
            host_display = await get_server_display_name(host_id, flight_data.get("staff_guild_id") or STAFF_GUILD_ID)
        except Exception as e:
            print(f"Host display name error: {e}")

    for i, field in enumerate(embed.fields):
        if "Accepted" in field.name or "check" in field.name:
            embed.set_field_at(i, name=f"{EMOJI_CHECK_STR} Accepted ({len(acc_names)})", value=acc_text, inline=True)
        elif "Declined" in field.name or "X_" in field.name:
            embed.set_field_at(i, name=f"{EMOJI_X_STR} Declined ({len(dec_names)})", value=dec_text, inline=True)
        elif field.name == "Host" and host_display:
            if field.value != host_display:
                embed.set_field_at(i, name="Host", value=host_display, inline=field.inline)

    if host_display and embed.footer and embed.footer.text:
        _new_footer = re.sub(r"(\| Created by ).*$", lambda m: m.group(1) + host_display, embed.footer.text)
        if _new_footer != embed.footer.text:
            embed.set_footer(text=_new_footer, icon_url=embed.footer.icon_url)

    try:
        edit_kwargs = {"embed": embed}
        if image_file is not None:

            edit_kwargs["attachments"] = [image_file]
        elif clear_attachments:

            edit_kwargs["attachments"] = []
        if view is not None:
            edit_kwargs["view"] = view
        await message.edit(**edit_kwargs)
    except Exception:
        if strict:
            raise





class ReflectionModal(Modal):
    def __init__(self, user_locale):
        is_ja = str(user_locale) == 'ja'
        title_text = 'Submit Reflection' if is_ja else 'Submit Reflection'
        super().__init__(title=title_text)

        self.feedback = TextInput(
            label='Reflection Comments' if is_ja else 'Reflection Comments',
            style=discord.TextStyle.paragraph,
            placeholder='Please enter your reflection here...' if is_ja else 'Please enter your reflection here...',
            required=True,
            max_length=2000
        )
        self.add_item(self.feedback)

    async def on_submit(self, interaction: discord.Interaction):
        is_ja = str(interaction.locale) == 'ja'
        channel = client.get_channel(REFLECTION_CHANNEL_ID)

        if channel:
            embed = discord.Embed(
                title=f"{EMOJI_NOTI_STR} Reflection Received: {interaction.user.display_name}",
                description=self.feedback.value,
                color=discord.Color.green()
            )
            embed.set_footer(text=f"User ID: {interaction.user.id}")
            await channel.send(embed=embed)

            success_msg = 'Your reflection has been submitted successfully. Thank you.' if is_ja else 'Your reflection has been submitted successfully. Thank you.'
            await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, success_msg)]))
        else:
            err_msg = EMOJI_X_STR + ' Error: Destination channel not found.' if is_ja else 'Error: Destination channel not found.'
            await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, err_msg)]))


class ReflectionView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Submit Reflection', style=discord.ButtonStyle.primary, custom_id='reflection_button')
    async def open_form_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ReflectionModal(user_locale=interaction.locale))


def staff_time_passed(flight: dict) -> bool:
    if flight.get("is_gamenight"):
        return False
    ts = flight.get("staff_timestamp")
    return bool(ts) and datetime.datetime.now().timestamp() >= ts

STAFF_TIME_PASSED_MSG = (
    "The staff participation time has passed, so you can no longer accept or decline. If you need a change, please contact the host.\n"
    "The staff join time has passed, so joining or declining is no longer possible. Please contact the host if you need a change."
)

class CancelReasonModal(discord.ui.Modal, title="Cancellation Reason"):
    reason = discord.ui.TextInput(label="Reason for cancellation", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, flight_code, user_id, action_type):
        super().__init__()
        self.flight_code = flight_code
        self.user_id = user_id
        self.action_type = action_type

    async def on_submit(self, interaction: discord.Interaction):
        global global_db_dirty
        await interaction.response.defer(ephemeral=True)
        try:
            async with global_json_lock:
                target_idx = next((i for i, f in enumerate(FLIGHT_LOG_CACHE) if f["flight_code"] == self.flight_code), -1)
                if target_idx == -1:
                    return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_X_STR + ' Error: Flight not found.')]))
                flight = FLIGHT_LOG_CACHE[target_idx]

                if staff_time_passed(flight):
                    return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, STAFF_TIME_PASSED_MSG)]))

                if self.user_id in flight.get("accepted_users", []):
                    flight["accepted_users"].remove(self.user_id)
                if self.user_id not in flight.get("declined_users", []):
                    flight.setdefault("declined_users", []).append(self.user_id)

                global_db_dirty = True

            if s_ch := client.get_channel(flight["staff_channel_id"]):
                msg = await s_ch.fetch_message(flight["staff_message_id"])
                await update_staff_embed_ui(msg, flight, interaction.guild)

            if host := client.get_user(flight["host_id"]):
                user = interaction.guild.get_member(self.user_id)
                u_name = user.display_name if user else f"User ID: {self.user_id}"
                dm_embed = discord.Embed(title="Staff Cancellation Notice",
                                         description=f"**{u_name}** (<@{self.user_id}>) has cancelled their participation.\n**Flight:** {flight['flight_code']}",
                                         color=discord.Color.orange())
                dm_embed.add_field(name="Reason", value=self.reason.value, inline=False)
                try:
                    await host.send(embed=dm_embed)
                except:
                    pass
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, f'{EMOJI_NOTI_STR} Cancellation processed. Host notified.')]))
        except Exception as e:
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, f'{EMOJI_X_STR} Error: {e}')]))


class DeleteReasonModal(discord.ui.Modal, title="Reason for Deletion"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, placeholder="Due to an equipment issue...", required=True)

    def __init__(self, flight_code, flight_data):
        super().__init__()
        self.flight_code = flight_code
        self.flight = flight_data

    async def on_submit(self, interaction: discord.Interaction):
        global global_db_dirty
        await interaction.response.defer(ephemeral=True)
        
        airline = self.flight.get("airline") or default_airline()
        destination = self.flight.get('destination', 'Unknown')


        embed = discord.Embed(
            title=f"{airline} | {self.flight_code} - CANCELED",
            description=(
                f"We sincerely apologize. Flight **{self.flight_code}** to {destination} has been **cancelled** for the following reason.\n"
                f"We deeply apologize to inform you that flight **{self.flight_code}** to *{destination}* has been **canceled**.\n\n"
                f"**Reason:**\n{self.reason.value}\n\n"
                f"We apologize for any inconvenience this may cause and appreciate your understanding.\n"
                f"We sincerely apologize for the major inconvenience to our customers."
            ),
            color=discord.Color.red()
        )
        embed.set_author(name="Travel Update")


        if self.flight.get("event_url"):
            try:
                event_id = int(self.flight["event_url"].split("/")[-1])
                target_guild_id = STAFF_GUILD_ID if (self.flight.get("is_gamenight") or self.flight.get("is_private")) else CUSTOMER_GUILD_ID
                target_guild = client.get_guild(target_guild_id)
                if target_guild:
                    event = await target_guild.fetch_scheduled_event(event_id)
                    await event.delete()
            except: pass


        cancel_msg = None
        if not self.flight.get("is_private"):
            cancel_msg = await client.get_channel(CUSTOMER_CHANNEL_ID).send(embed=embed)


        try:
            if s_ch := client.get_channel(self.flight["staff_channel_id"]):
                await (await s_ch.fetch_message(self.flight["staff_message_id"])).delete()
        except: pass

        try:
            if self.flight.get("customer_message_id") and (c_ch := client.get_channel(self.flight["customer_channel_id"])):
                await (await c_ch.fetch_message(self.flight["customer_message_id"])).delete()
        except: pass

        if self.flight.get("is_custom"):
            try:
                if src_ch := client.get_channel(self.flight["source_channel_id"]):
                    await (await src_ch.fetch_message(self.flight["source_message_id"])).delete()
            except: pass


        async with global_json_lock:
            target_idx = next((i for i, f in enumerate(FLIGHT_LOG_CACHE) if f["flight_code"] == self.flight_code), -1)
            if target_idx != -1:
                if cancel_msg:
                    FLIGHT_LOG_CACHE[target_idx]["cancel_message_id"] = cancel_msg.id
                FLIGHT_LOG_CACHE[target_idx]["end_timestamp"] = int(datetime.datetime.now().timestamp()) - 1
                FLIGHT_LOG_CACHE[target_idx]["messages_deleted"] = True
                FLIGHT_LOG_CACHE[target_idx]["messages_deleted_by_cancel"] = True
                global_db_dirty = True
        try:
            await delete_flight_channels(FLIGHT_LOG_CACHE[target_idx] if target_idx != -1 else self.flight)
        except Exception as e:
            print(f"cancel channel delete error: {e}")


        await auto_publish_schedule()
        await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'Cancellation announced and data removed.')]))

def build_edit_flight_embed(flight, flight_code, image_url=None):
    title = flight.get("event_title") or f"{flight_code} {flight.get('origin','?')}→{flight.get('destination','?')}"
    route_val = f"{flight.get('origin','Unknown')} ➝ {flight.get('destination','Unknown')}"

    embed = discord.Embed(title="What would you like to change?", color=get_embed_color(flight.get('color')))

    embed.add_field(name="1 · Title", value=f"```{title}```", inline=False)
    embed.add_field(name="2 · Route", value=f"```{route_val}```", inline=False)
    embed.add_field(name="3 · Aircraft Equipment", value=f"```{flight.get('equipment', 'Unknown')}```", inline=False)
    embed.add_field(name="4 · Aircraft Operator", value=f"```{flight.get('airline') or default_airline()}```", inline=False)

    staff_ts = int(flight.get('staff_timestamp', 0))
    start_ts = int(flight.get('start_timestamp', 0))
    embed.add_field(name="5 · Staff Briefing Time", value=f"<t:{staff_ts}:F>\n```{datetime.datetime.fromtimestamp(staff_ts, tz=JST).strftime('%Y-%m-%d %H:%M')}```", inline=True)
    embed.add_field(name="6 · Departure Time", value=f"<t:{start_ts}:F>\n```{datetime.datetime.fromtimestamp(start_ts, tz=JST).strftime('%Y-%m-%d %H:%M')}```", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="7 · Image", value="```Auto-generated from the flight template.```", inline=False)

    if event_url := flight.get("event_url"):
        embed.add_field(name="Calendar Event", value=f"[Open in Discord]({event_url})\n```{event_url}```", inline=False)

    embed.set_footer(text="Route / Equipment: choosing a template also changes the flight code, airports, class and image. Title / Operator / Image can't be edited directly.")


    if image_url:
        embed.set_image(url=image_url)

    return embed


class EditFieldSelect(discord.ui.Select):
    def __init__(self, flight, flight_code, is_urgent=False):
        self.flight = flight
        self.flight_code = flight_code
        self.is_urgent = is_urgent

        options = [
            discord.SelectOption(label="1 · Title", value="title"),
            discord.SelectOption(label="2 · Route", value="route"),
            discord.SelectOption(label="3 · Aircraft Equipment", value="equipment"),
            discord.SelectOption(label="4 · Aircraft Operator", value="operator"),
            discord.SelectOption(label="5 · Staff Briefing Time", value="staff_time"),
            discord.SelectOption(label="6 · Departure Time", value="departure_time"),
            discord.SelectOption(label="7 · Image", value="image"),
        ]

        super().__init__(placeholder="Select what to edit...", min_values=1, max_values=1, options=options, custom_id="edit_field_select")

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]


        if choice in ("route", "equipment"):
            await interaction.response.defer(ephemeral=True)
            try:
                await ensure_templates_fresh()
                used = await get_used_origins(interaction.client, ignore_flight_code=self.flight_code)
                routes = list_routes_for_edit(self.flight, used)
                if not routes:
                    return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'No registered routes are available.')]))

                pre = find_current_route_code(self.flight) if choice == "equipment" else None
                view = EditRouteChangeView(self.flight, self.flight_code, routes, is_urgent=self.is_urgent,
                                       origin_message=interaction.message, preselect_code=pre, guild=interaction.guild,
                                       origin_interaction=interaction)
                return await interaction.followup.send(embed=view.make_embed(), view=view, ephemeral=True)
            except Exception as e:
                traceback.print_exc()
                return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, f'{EMOJI_X_STR} Error: {e}')]))


        if choice in ("title", "operator", "image"):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, "This item is auto-generated from the flight template and can't be edited here.")]))


        if choice in ("staff_time", "departure_time"):
            return await interaction.response.send_modal(
                EditFlightModal(self.flight, self.flight_code, is_urgent=self.is_urgent, origin_message=interaction.message)
            )


class EditFlightOptionsView(discord.ui.View):
    def __init__(self, flight, flight_code, is_urgent=False):
        super().__init__(timeout=300)
        self.flight = flight
        self.flight_code = flight_code
        self.is_urgent = is_urgent
        self.add_item(EditFieldSelect(flight, flight_code, is_urgent=is_urgent))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, row=1)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Closed.", embed=None, view=None)








def resolve_template_code(flight: dict):
    rc = flight.get("route_code")
    if rc and rc in FLIGHT_DB:
        return rc
    code = (flight.get("flight_code") or "").strip()
    if code.startswith("[TEST] "):
        code = code[7:]
    if flight.get("route_changed_at"):

        eq = (flight.get("equipment") or "").lower()
        for c, info in FLIGHT_DB.items():
            if info.get("origin") != flight.get("origin"):
                continue
            if info.get("destination") != flight.get("destination"):
                continue
            if any(k.lower() == eq for k in info.get("variants", {})):
                return c
    if code in FLIGHT_DB:
        return code
    return None


def compose_flight_code(flight: dict, route_code: str) -> str:
    if flight.get("is_test"):
        return f"[TEST] {route_code}"
    return route_code




def _custom_source_ids(exclude_code=None) -> set:
    return {f.get("source_message_id") for f in FLIGHT_LOG_CACHE
            if f.get("is_custom") and not f.get("messages_deleted")
            and f.get("flight_code") != exclude_code and f.get("source_message_id")}


def find_current_route_code(flight: dict):
    rc = resolve_template_code(flight)
    if rc:
        return rc
    for c, info in FLIGHT_DB.items():
        if (info.get("origin") == flight.get("origin")
                and info.get("destination") == flight.get("destination")):
            return c
    return None


def list_routes_for_edit(flight: dict, used_origins: set) -> list:
    cur_origin = (flight.get("origin") or "").lower()
    skip_src = _custom_source_ids(flight.get("flight_code"))
    items = []
    for code, info in sorted(FLIGHT_DB.items()):
        if not info.get("variants"):
            continue
        if all(v.get("source_message_id") in skip_src for v in info["variants"].values()):
            continue
        origin = info.get("origin", "Unknown")
        if origin.lower() in used_origins and origin.lower() != cur_origin:
            continue
        label = f"{code} | {origin} ➝ {info.get('destination', 'Unknown')}"
        items.append((code, label[:100]))
    return items


def build_flight_event_name(flight: dict) -> str:
    code = flight["flight_code"]
    name = flight.get("event_title") or f"{code} {flight.get('origin', '')}→{flight.get('destination', '')}"
    return f"[Private Flight] {name}" if flight.get("is_private") else name


def host_display_sync(host_id) -> str:
    if not host_id:
        return "N/A"
    try:
        user = client.get_user(int(host_id))
    except Exception:
        user = None
    if user is not None:
        return getattr(user, "display_name", None) or getattr(user, "name", None) or f"<@{host_id}>"
    return f"<@{host_id}>"


def template_context(flight: dict, *, reason_text: str = "", updated: bool = False) -> dict:
    flight = flight or {}
    airline = flight.get("airline") or default_airline()
    ts_start = int(flight.get("start_timestamp") or 0)
    ts_end = int(flight.get("end_timestamp") or 0)
    staff_ts = int(flight.get("staff_timestamp") or 0)
    host_id = flight.get("host_id")
    host_mention = f"<@{host_id}>" if host_id else "N/A"
    origin = flight.get("origin", "")
    destination = flight.get("destination", "")
    return {
        "Flight Code": flight.get("flight_code", ""),
        "Operation Name": flight.get("flight_code", ""),
        "Airline": airline,
        "Operator": airline,
        "Origin": origin,
        "Server": origin,
        "Destination": destination,
        "Route": f"{origin} \u279d {destination}",
        "Equipment": flight.get("equipment", ""),
        "Vehicle": flight.get("equipment", ""),
        "Classes": flight.get("classes") or "Unknown",
        "Date": f"<t:{ts_start}:D>" if ts_start else "",
        "Check-in Time": f"<t:{ts_start}:t>" if ts_start else "",
        "Start Time": f"<t:{ts_start}:t>" if ts_start else "",
        "Server Lock": f"<t:{ts_start + 1200}:t>" if ts_start else "",
        "Time": f"<t:{ts_start}:F> - <t:{ts_end}:t> (<t:{ts_start}:R>)" if ts_start else "",
        "Staff Briefing Time": f"<t:{staff_ts}:F>" if staff_ts else "",
        "Staff Join Time": f"<t:{staff_ts}:t>" if staff_ts else "",
        "Host": host_display_sync(host_id),
        "Host Mention": host_mention,
        "Minimum Staff": minimum_staff_text(),
        "Event Link": f"{EMOJI_LINK_STR} **[Discord Event Link]({flight.get('event_url', '')})**",
        "Mention": get_customer_mention_line(flight),
        "Updated": " (UPDATED)" if updated else "",
        "Reason": f"{reason_text}\n\n" if reason_text else "",
        "Emoji": EMOJI_TAIL_STR,
        "Color": flight.get("color", ""),
    }


def render_staff_description(flight: dict, key: str = "staff_description") -> str:
    return templates.render(templates.get_template(key), template_context(flight))


def render_customer_post(flight: dict, *, key: str = None, reason_text: str = "", updated: bool = False) -> str:
    if key is None:
        key = "customer_post"
    return templates.render(templates.get_template(key),
                            template_context(flight, reason_text=reason_text, updated=updated))


def render_calendar_description(flight: dict) -> str:
    return templates.render(templates.get_template("calendar_description"), template_context(flight))


def build_flight_event_description(flight: dict) -> str:
    return render_calendar_description(flight)


def build_customer_announcement(flight: dict, updated: bool = False, reason_text: str = "") -> str:
    return render_customer_post(flight, reason_text=reason_text, updated=updated)


async def get_flight_calendar_event(flight: dict):
    url = (flight.get("event_url") or "").strip()
    if not url:
        return None
    parts = [x for x in url.split("?")[0].rstrip("/").split("/") if x]
    try:
        eid = int(parts[-1])
    except Exception:
        return None
    gids = []
    try:
        gids.append(int(parts[-2]))
    except Exception:
        pass
    for gid in ([STAFF_GUILD_ID, CUSTOMER_GUILD_ID] if (flight.get("is_private") or flight.get("is_test") or flight.get("is_gamenight")) else [CUSTOMER_GUILD_ID, STAFF_GUILD_ID]):
        if gid not in gids:
            gids.append(gid)
    for gid in gids:
        guild = client.get_guild(gid)
        if guild is None:
            continue
        try:
            return await guild.fetch_scheduled_event(eid)
        except Exception:
            continue
    return None


async def find_customer_message(flight: dict, code: str = None):
    try:
        c_ch = client.get_channel(flight.get("customer_channel_id") or CUSTOMER_CHANNEL_ID) \
            or await client.fetch_channel(flight.get("customer_channel_id") or CUSTOMER_CHANNEL_ID)
        code = code or flight.get("flight_code", "")
        markers = (f"Flight code: {code}", f"Operation name: {code}")
        url = (flight.get("event_url") or "").strip()
        async for m in c_ch.history(limit=200):
            if m.author != client.user or not m.content:
                continue
            if not any(mk in m.content for mk in markers):
                continue
            if url and url not in m.content:
                continue
            return m
    except Exception as e:
        print(f"find_customer_message error ({flight.get('flight_code')}): {e}")
    return None


async def perform_route_change(flight_code: str, route_code: str, equipment: str, reason: str = None, guild=None):
    global global_db_dirty
    warnings = []
    route = FLIGHT_DB.get(route_code)
    variant = (route or {}).get("variants", {}).get(equipment)
    if not route or not variant:
        return False, "The selected route or equipment is not registered.", warnings

    used = await get_used_origins(client, ignore_flight_code=flight_code)

    old_custom_src = None
    async with global_json_lock:
        flight = next((f for f in FLIGHT_LOG_CACHE if f.get("flight_code") == flight_code), None)
        if not flight:
            return False, "Flight not found.", warnings
        if variant.get("source_message_id") in _custom_source_ids(flight_code):
            return False, "The selected route is a temporary template of another custom flight.", warnings
        if flight.get("messages_deleted") or flight.get("end_timestamp", 0) <= datetime.datetime.now().timestamp():
            return False, "This flight has already ended.", warnings
        new_origin = route.get("origin", "Unknown")
        if new_origin.lower() in used and new_origin.lower() != (flight.get("origin") or "").lower():
            return False, f"Origin '{new_origin}' is already in use by another flight/application.", warnings

        old_code = flight.get("flight_code")
        new_code = compose_flight_code(flight, route_code)
        if new_code != old_code and any(f is not flight and f.get("flight_code") == new_code
                                        and not f.get("messages_deleted") for f in FLIGHT_LOG_CACHE):
            return False, f"The flight code `{new_code}` is already in use by another active flight.", warnings

        old = {"origin": flight.get("origin"), "destination": flight.get("destination"),
               "equipment": flight.get("equipment"), "code": old_code}
        flight["flight_code"] = new_code
        flight["origin"] = new_origin
        flight["destination"] = route.get("destination", "Unknown")
        flight["equipment"] = equipment
        flight["classes"] = variant.get("classes", "Unknown")
        flight["roblox_link"] = variant.get("roblox_link", "")
        flight["airline"] = variant.get("airline") or default_airline()
        flight["color"] = variant.get("color", "1B3444")


        if flight.get("is_custom") and flight.get("source_message_id") != variant.get("source_message_id"):
            old_custom_src = (flight.get("source_channel_id"), flight.get("source_message_id"))
            flight["is_custom"] = False
        flight["source_channel_id"] = variant.get("source_channel_id")
        flight["source_message_id"] = variant.get("source_message_id")

        flight["route_code"] = route_code
        flight["route_changed_at"] = int(datetime.datetime.now().timestamp())
        global_db_dirty = True

    image_url, image_bytes = await fetch_image_for_update(flight.get("source_channel_id"), flight.get("source_message_id"))
    if not image_url:
        warnings.append("Could not fetch the new route image. The recruitment message / calendar image remains unchanged. Please re-sync with /update_ui.")
    elif not image_bytes:
        warnings.append("The image download failed, so the calendar event image remains unchanged. Please re-sync with /update_ui.")
    event_name = build_flight_event_name(flight)
    reason_text = f"**Reason for Update**\n{reason}" if reason else ""


    try:
        event = await get_flight_calendar_event(flight)
        if event is not None:
            kwargs = dict(name=event_name[:100], description=build_flight_event_description(flight), location=flight["origin"][:100])
            if image_bytes:
                kwargs["image"] = image_bytes
            await event.edit(**kwargs)
        elif flight.get("event_url"):
            warnings.append("The calendar event was not found and could not be updated.")
    except Exception as e:
        print(f"Route change: event update error ({flight_code}): {e}")
        warnings.append("Could not update the calendar event. Please check manually.")


    try:
        s_ch = client.get_channel(flight.get("staff_channel_id"))
        if s_ch and flight.get("staff_message_id"):
            msg = await s_ch.fetch_message(flight["staff_message_id"])
            embed = msg.embeds[0]
            embed.title = signup_embed_title(flight, event_name)
            embed.color = PRIVATE_FLIGHT_COLOR if flight.get("is_private") else get_embed_color(flight.get("color"))
            for i, f in enumerate(embed.fields):
                if f.name == "Route":
                    embed.set_field_at(i, name=f.name, value=f"{flight['origin']} ➝ {flight.get('destination', '')}", inline=False)
                elif f.name == "Aircraft Equipment":
                    embed.set_field_at(i, name=f.name, value=flight["equipment"], inline=False)
                elif f.name == "Aircraft Operator":
                    embed.set_field_at(i, name=f.name, value=flight.get("airline") or default_airline(), inline=False)

            route_image_file = None
            if image_bytes:
                route_image_file = embed_image_as_attachment(embed, image_bytes, image_url,
                                                             prefix=f"staff_{new_code}")


            _ft = (embed.footer.text if embed.footer else "") or ""
            _m = re.match(r"Flight Code: (.+?) \|(.*)", _ft)
            if _m:
                _tail_rc = _m.group(2)
            else:
                _hn = await get_server_display_name(flight.get("host_id"), flight.get("staff_guild_id") or STAFF_GUILD_ID,
                                                    fallback=str(flight.get("host_id")))
                _tail_rc = f" Created by {_hn}"
            embed.set_footer(text=f"Flight Code: {new_code} |{_tail_rc}")
            await update_staff_embed_ui(msg, flight, guild, embed=embed, strict=True, image_file=route_image_file)
    except Exception as e:
        print(f"Route change: staff message error ({flight_code}): {e}")
        warnings.append("Could not update the staff recruitment message.")




    repaired_id = False
    if not flight.get("is_private"):
        flight["customer_msg_content"] = build_customer_announcement(flight)
        if flight.get("customer_message_id"):
            edited, last_err = False, None
            for attempt in (1, 2):
                try:
                    c_ch = client.get_channel(flight.get("customer_channel_id") or CUSTOMER_CHANNEL_ID)
                    c_msg = None
                    try:
                        if c_ch:
                            c_msg = await c_ch.fetch_message(flight["customer_message_id"])
                    except Exception:
                        c_msg = await find_customer_message(flight, code=old_code)
                        if c_msg:
                            flight["customer_message_id"] = c_msg.id
                            repaired_id = True
                    if c_msg is None:
                        raise RuntimeError("customer announcement message not found")
                    await c_msg.edit(content=build_customer_announcement(flight, updated=True, reason_text=reason_text), suppress=True)
                    edited = True
                    break
                except Exception as e:
                    last_err = e
                    if attempt == 1:
                        await asyncio.sleep(1)
            if not edited:
                traceback.print_exception(type(last_err), last_err, last_err.__traceback__)
                print(f"Route change: customer message error ({flight_code}): {last_err}")
                warnings.append(f"Could not update the customer announcement. Please check manually. ({type(last_err).__name__}: {str(last_err)[:100]})")
            elif repaired_id:
                warnings.append(f"{EMOJI_INFO_STR} The customer announcement message ID was incorrect, so it was repaired automatically.")


    if flight.get("briefing_thread_id"):
        try:
            th = client.get_channel(flight["briefing_thread_id"]) or await client.fetch_channel(flight["briefing_thread_id"])
            await th.edit(name=f"{flight['flight_code']} {flight['origin']}→{flight.get('destination', '')}"[:100])
            notice = discord.Embed(title="Route / equipment changed", color=get_embed_color(flight.get("color")))
            notice.add_field(name="Before", value=f"{old['code']}\n{old['origin']} ➝ {old['destination']}\n{old['equipment']}", inline=False)
            notice.add_field(name="After", value=f"{flight['flight_code']}\n{flight['origin']} ➝ {flight.get('destination', '')}\n{flight['equipment']}", inline=False)
            if reason:
                notice.add_field(name="Reason", value=reason[:1000], inline=False)
            await th.send(embed=notice)
        except Exception as e:
            print(f"Route change: thread update error ({flight_code}): {e}")

    if flight.get("briefing_sent"):
        warnings.append("The briefing sheet has already been posted. Use /edit_briefing to update the route and equipment.")


    if new_code != old_code:

        if flight.get("flight_channels"):
            try:
                _vn, _cn = _flight_channel_names(new_code)
                _fc = flight["flight_channels"]
                for _cid, _nm in ((_fc.get("vc"), _vn), (_fc.get("chat"), _cn)):
                    if _cid:
                        _ch = client.get_channel(_cid) or await client.fetch_channel(_cid)
                        if _ch.name != _nm:
                            await _ch.edit(name=_nm)
            except Exception as e:
                print(f"Route change: channel rename error ({old_code}): {e}")
                warnings.append("Could not rename the dedicated VC / listen-only chat.")

        if flight.get("master_event_id"):
            try:
                _gid = STAFF_GUILD_ID if flight.get("is_test") else CUSTOMER_GUILD_ID
                _core = new_code.replace("[TEST] ", "")
                _title = f"{_core} {flight['origin']}→{flight.get('destination', '')}"
                await update_discord_recurring_event(_gid, flight["master_event_id"], _title,
                                                     build_flight_event_description(flight), flight["origin"], image_bytes)
            except Exception as e:
                print(f"Route change: recurring event update error ({old_code}): {e}")
                warnings.append("Could not update the recurring event name.")


    if old_custom_src and old_custom_src[0] and old_custom_src[1]:
        try:
            _och = client.get_channel(old_custom_src[0]) or await client.fetch_channel(old_custom_src[0])
            await (await _och.fetch_message(old_custom_src[1])).delete()
        except Exception as e:
            print(f"Route change: old custom image cleanup error ({flight_code}): {e}")


    try:
        async with global_json_lock:
            saved = await _save_flight_log_now()
        if not saved:
            warnings.append("Failed to save the data (JSON) immediately; it will be retried by autosave.")
    except Exception as e:
        print(f"Route change: immediate save error ({flight_code}): {e}")
        warnings.append("Failed to save the data (JSON) immediately; it will be retried by autosave.")


    try:
        await auto_publish_schedule()
    except Exception as e:
        print(f"Route change: schedule publish error ({flight_code}): {e}")
        warnings.append("Failed to update the schedule. Please update it with /update_ui etc.")
    return True, "OK", warnings


class EditRouteChangeReasonModal(discord.ui.Modal, title="Reason for Route Change"):
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        self.reason = discord.ui.TextInput(label="Reason for Edit", style=discord.TextStyle.paragraph,
                                           placeholder="Due to an equipment issue...", required=True, max_length=500)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await self.parent_view.apply(interaction, reason=self.reason.value.strip())


class EditRouteChangeView(discord.ui.View):
    PAGE = 25

    def __init__(self, flight, flight_code, routes, is_urgent=False, origin_message=None, preselect_code=None, guild=None, origin_interaction=None):
        super().__init__(timeout=300)
        self.origin_interaction = origin_interaction
        self.flight = flight
        self.flight_code = flight_code
        self.routes = routes
        self.is_urgent = is_urgent
        self.origin_message = origin_message
        self.guild = guild
        self.route_code = preselect_code if preselect_code in dict(routes) else None
        self.equip = None
        self.page = 0
        self.applied = False
        if self.route_code:
            self.page = [c for c, _ in routes].index(self.route_code) // self.PAGE
        self._build()

    def _max_page(self):
        return max(0, (len(self.routes) - 1) // self.PAGE)

    def _build(self):
        self.clear_items()
        chunk = self.routes[self.page * self.PAGE:(self.page + 1) * self.PAGE]
        route_sel = discord.ui.Select(
            placeholder=f"1. Select a route ({self.page + 1}/{self._max_page() + 1})", row=0,
            options=[discord.SelectOption(label=label, value=code, default=(code == self.route_code)) for code, label in chunk])
        route_sel.callback = self.on_route
        self.add_item(route_sel)

        _skip_src = _custom_source_ids(self.flight_code)
        variants = [k for k, v in FLIGHT_DB.get(self.route_code, {}).get("variants", {}).items()
                    if v.get("source_message_id") not in _skip_src][:25] if self.route_code else []
        if variants:
            eq_sel = discord.ui.Select(
                placeholder="2. Select aircraft equipment", row=1,
                options=[discord.SelectOption(label=v[:100], value=v, default=(v == self.equip)) for v in variants])
        else:
            eq_sel = discord.ui.Select(placeholder="2. Select a route first", row=1, disabled=True,
                                       options=[discord.SelectOption(label="-", value="_")])
        eq_sel.callback = self.on_equip
        self.add_item(eq_sel)

        prev_b = discord.ui.Button(label="Prev", style=discord.ButtonStyle.secondary, row=2, disabled=self.page <= 0)
        prev_b.callback = self.on_prev
        next_b = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, row=2, disabled=self.page >= self._max_page())
        next_b.callback = self.on_next
        ok_b = discord.ui.Button(label="Confirm change", style=discord.ButtonStyle.success, row=2,
                                 disabled=not (self.route_code and self.equip))
        ok_b.callback = self.on_confirm
        cancel_b = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, row=2)
        cancel_b.callback = self.on_cancel
        for b in (prev_b, next_b, ok_b, cancel_b):
            self.add_item(b)

    def make_embed(self) -> discord.Embed:
        f = self.flight
        cur_route = f"{f.get('origin', '?')} ➝ {f.get('destination', '?')}"
        e = discord.Embed(title="Change route / equipment", color=get_embed_color(f.get("color")),
                          description="Select a registered **route** and its **equipment**, then press Confirm.\n"
                                      "Both a route and equipment must be selected.\n"
                                      "**Flight code / route / aircraft / class / airport** are all replaced with the template. Times are kept.\n"
                                      "The flight code, origin, destination, equipment, class, and airport will change to match the template (times stay the same).")
        e.add_field(name="Current", value=f"```{f.get('flight_code', '?')}\n{cur_route}\n{f.get('equipment', '?')}```", inline=False)
        if self.route_code:
            info = FLIGHT_DB.get(self.route_code, {})
            new_route = f"{info.get('origin', '?')} ➝ {info.get('destination', '?')}"
            e.add_field(name="New", value=f"```{compose_flight_code(f, self.route_code)}\n{new_route}\n{self.equip or '(select equipment)'}```", inline=False)
        if self.is_urgent:
            e.set_footer(text="Departure is within 3 hours: a reason is required and will be announced to customers.")
        return e

    async def on_route(self, interaction: discord.Interaction):
        self.route_code = interaction.data["values"][0]
        self.equip = None
        self._build()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def on_equip(self, interaction: discord.Interaction):
        self.equip = interaction.data["values"][0]
        self._build()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def on_prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._build()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def on_next(self, interaction: discord.Interaction):
        self.page = min(self._max_page(), self.page + 1)
        self._build()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def on_cancel(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

    async def on_confirm(self, interaction: discord.Interaction):
        if not (self.route_code and self.equip):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Select both a route and equipment.')]))
        if self.is_urgent:
            return await interaction.response.send_modal(EditRouteChangeReasonModal(self))
        await self.apply(interaction, reason=None)

    async def apply(self, interaction: discord.Interaction, reason=None):
        if self.applied:
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Already applied.')]))
        self.applied = True
        self.stop()

        await interaction.response.edit_message(content="Applying the change...", embed=None, view=None)
        try:
            ok, msg, warnings = await perform_route_change(self.flight_code, self.route_code, self.equip, reason=reason,
                                                           guild=self.guild or interaction.guild)
        except Exception as e:
            traceback.print_exc()
            ok, msg, warnings = False, f"Route change failed: {e}", []
        if ok:
            text = EMOJI_CHECK_STR + " Route and equipment updated."
            if warnings:
                text += "\n" + "\n".join(f"- {w}" for w in warnings)
        else:
            text = f"{EMOJI_X_STR} {msg}"
        try:
            await interaction.edit_original_response(content=text, embed=None, view=None)
        except Exception:
            try:
                await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, text)]))
            except Exception:
                pass
        if ok:


            try:
                fl = next((f for f in FLIGHT_LOG_CACHE
                           if self.flight.get("staff_message_id") and f.get("staff_message_id") == self.flight.get("staff_message_id")), None) or self.flight
                new_code = fl.get("flight_code", self.flight_code)
                image_url = await fetch_template_image_url(fl.get("source_channel_id"), fl.get("source_message_id"))
                new_embed = build_edit_flight_embed(fl, new_code, image_url=image_url)
                new_view = EditFlightOptionsView(fl, new_code, is_urgent=self.is_urgent)
                if self.origin_interaction:
                    await self.origin_interaction.edit_original_response(embed=new_embed, view=new_view)
                elif self.origin_message:
                    await self.origin_message.edit(embed=new_embed, view=new_view)
            except Exception as e:
                print(f"Route change: edit menu refresh error: {e}")


class EditFlightModal(discord.ui.Modal, title="Edit Flight Details"):
    def __init__(self, current_data, flight_code, is_urgent=False, origin_message=None):
        super().__init__()
        self.current_data = current_data
        self.flight_code = flight_code
        self.is_urgent = is_urgent
        self.origin_message = origin_message
        
        tz_offset = parse_timezone_offset(current_data.get("host_timezone_str", "GMT+9"))
        input_tz = datetime.timezone(datetime.timedelta(hours=tz_offset))
        
        staff_ts = current_data.get('staff_timestamp', 0)
        pass_ts = current_data.get('start_timestamp', 0)
        
        staff_time_def = datetime.datetime.fromtimestamp(staff_ts, tz=input_tz).strftime("%Y-%m-%d %H:%M") if staff_ts else ""
        pass_time_def = datetime.datetime.fromtimestamp(pass_ts, tz=input_tz).strftime("%H:%M") if pass_ts else ""

        self.staff_time = discord.ui.TextInput(label="New Staff Meeting", placeholder="YYYY-MM-DD HH:MM", required=True, default=staff_time_def)
        self.pass_time = discord.ui.TextInput(label="New Pax Start", placeholder="HH:MM", required=True, default=pass_time_def)
        
        self.add_item(self.staff_time)
        self.add_item(self.pass_time)


        if self.is_urgent:
            self.reason = discord.ui.TextInput(label="Reason for Edit", style=discord.TextStyle.paragraph, placeholder="Due to an equipment issue...", required=True)
            self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        global global_db_dirty
        await interaction.response.defer(ephemeral=True)
        try:
            tz_str = self.current_data.get("host_timezone_str", "GMT+9")
            tz_offset = parse_timezone_offset(tz_str)
            staff_dt = calculate_jst_time(self.staff_time.value, "", tz_offset)
            date_part = self.staff_time.value.strip().split()[0]
            pass_dt = calculate_jst_time(date_part, self.pass_time.value, tz_offset)
            
            if not staff_dt or not pass_dt:
                raise ValueError("Date format error.")
            if pass_dt < staff_dt:
                pass_dt += datetime.timedelta(days=1)
            end_dt = pass_dt + datetime.timedelta(hours=1)
            lock_dt = pass_dt + datetime.timedelta(minutes=20)



            async with global_json_lock:
                target_idx = next((i for i, f in enumerate(FLIGHT_LOG_CACHE) if f["flight_code"] == self.flight_code), -1)
                if target_idx == -1:
                    return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_X_STR + ' Error: Flight not found.')]))
                flight = FLIGHT_LOG_CACHE[target_idx]

                flight["staff_timestamp"] = int(staff_dt.timestamp())
                flight["start_timestamp"] = int(pass_dt.timestamp())
                flight["end_timestamp"] = int(end_dt.timestamp())
                flight["notify_20min_timestamp"] = (staff_dt - datetime.timedelta(minutes=20)).timestamp()
                flight["notified_20min"] = False
                flight["staff_start_notified"] = False
                
                global_db_dirty = True


            if self.origin_message:
                try:
                    image_url, _ = await fetch_fresh_image_info(flight.get("source_channel_id"), flight.get("source_message_id"))
                    await self.origin_message.edit(embed=build_edit_flight_embed(flight, self.flight_code, image_url=image_url))
                except Exception:
                    pass


            airline = flight.get("airline") or default_airline()
            mention_line = get_customer_mention_line(flight)
            origin = flight.get("origin", "Unknown")
            dest = flight.get("destination", "Unknown")
            equipment = flight.get("equipment", "Unknown")
            classes = flight.get("classes", "Unknown")


            if flight.get("event_url"):
                try:
                    event = await get_flight_calendar_event(flight)
                    if event is not None:
                        await event.edit(start_time=pass_dt, end_time=end_dt)
                    else:
                        print(f"Time edit: calendar event not found ({self.flight_code})")
                except Exception as e:
                    print(f"Time edit: calendar update error ({self.flight_code}): {e}")

            if s_channel := client.get_channel(flight["staff_channel_id"]):
                try:
                    msg = await s_channel.fetch_message(flight["staff_message_id"])
                    embed = msg.embeds[0]
                    ts_start = int(pass_dt.timestamp())
                    ts_end = int(end_dt.timestamp())
                    new_time_str = f"<t:{ts_start}:F> - <t:{ts_end}:t> (<t:{ts_start}:R>)"
                    for i, f in enumerate(embed.fields):
                        if f.name == "Action":
                            embed.set_field_at(i, name="Action", value=f"React to join the flight.\n**Staff Briefing Time:** <t:{int(staff_dt.timestamp())}:F>" + google_calendar_suffix(flight), inline=False)
                        elif f.name == "Time":
                            embed.set_field_at(i, name="Time", value=new_time_str, inline=False)
                    await update_staff_embed_ui(msg, flight, interaction.guild, embed=embed)
                except: pass


            if c_channel := client.get_channel(CUSTOMER_CHANNEL_ID):
                if flight.get("customer_message_id"):
                    try:
                        c_msg = await c_channel.fetch_message(flight["customer_message_id"])
                        reason_text = f"\n\n**Reason for Update**\n{self.reason.value}" if self.is_urgent and hasattr(self, 'reason') else ""
                        
                        new_content = (
                            f"{EMOJI_TAIL_STR} **Flight Information** (UPDATED)\n"
                            f"Flight code: {flight['flight_code']}\n"
                            f"Airline: {airline}\n"
                            f"Departure Airport: {origin}\n"
                            f"Arrival Airport: {dest}\n"
                            f"Date: <t:{int(pass_dt.timestamp())}:D>\n"
                            f"Check-in Time: <t:{int(pass_dt.timestamp())}:t>\n"
                            f"Server Lock: <t:{int(lock_dt.timestamp())}:t>\n"
                            f"Equipment: {equipment}\n"
                            f"Class: {classes}\n"
                            f"{reason_text}\n\n"
                            f"{mention_line}"
                            f"{EMOJI_LINK_STR} **[Discord Event Link]({flight['event_url']})**"
                        )
                        await c_msg.edit(content=new_content, suppress=True)
                    except: pass

            await auto_publish_schedule()
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_CHECK_STR + ' Updated successfully!')]))
        except Exception as e:
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, f'{EMOJI_X_STR} Edit failed: {e}')]))

class ShiftPrefSelect(discord.ui.Select):
    def __init__(self, placeholder, options):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

class ShiftRequestView(discord.ui.View):
    def __init__(self, flight, user_id, departments):
        super().__init__(timeout=300)
        self.flight = flight
        self.user_id = user_id
        
        options = [discord.SelectOption(label=dep) for dep in departments]
        self.first_choice = ShiftPrefSelect("1st Choice", options)
        
        second_options = options.copy()
        second_options.append(discord.SelectOption(label="Any", value="Any"))
        second_options.append(discord.SelectOption(label="None", value="None"))
        self.second_choice = ShiftPrefSelect("2nd Choice", second_options)
        
        self.add_item(self.first_choice)
        self.add_item(self.second_choice)
        
        btn_submit = discord.ui.Button(label="Submit Preference", style=discord.ButtonStyle.success)
        btn_submit.callback = self.submit_callback
        self.add_item(btn_submit)
        
        btn_skip = discord.ui.Button(label="Join without Preference", style=discord.ButtonStyle.secondary)
        btn_skip.callback = self.skip_callback
        self.add_item(btn_skip)

    async def finalize_join(self, interaction, pref_data=None):
        global global_db_dirty
        async with global_json_lock:
            target_idx = next((i for i, f in enumerate(FLIGHT_LOG_CACHE) if f["flight_code"] == self.flight['flight_code']), -1)
            if target_idx == -1:
                await interaction.followup.send(view=embed_to_v2_layout(create_info_embed('Error', 'Flight not found.', discord.Color.red()), content=None), ephemeral=True)
                return False
            
            flight = FLIGHT_LOG_CACHE[target_idx]

            if staff_time_passed(flight):
                return False
            
            if pref_data:
                flight.setdefault("shift_requests", {})
                flight["shift_requests"][str(self.user_id)] = pref_data
            
            flight.setdefault("accepted_users", [])
            flight.setdefault("declined_users", [])
            
            _is_new_join = self.user_id not in flight["accepted_users"]
            if self.user_id not in flight["accepted_users"]:
                flight["accepted_users"].append(self.user_id)
            if self.user_id in flight["declined_users"]:
                flight["declined_users"].remove(self.user_id)
                
            global_db_dirty = True

        if _is_new_join:
            client.loop.create_task(notify_host_of_join(flight, interaction.user, "accepted"))
            
        if s_ch := client.get_channel(flight["staff_channel_id"]):
            try:
                msg = await s_ch.fetch_message(flight["staff_message_id"])
                await update_staff_embed_ui(msg, flight, interaction.guild)
            except:
                pass
        self.clear_items()
        return True

    async def submit_callback(self, interaction: discord.Interaction):
        if not self.first_choice.values or not self.second_choice.values:
            return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Error', 'Please select both 1st and 2nd choices.', discord.Color.red()), content=None), ephemeral=True)

        await interaction.response.defer()
        pref_data = {
            "first": self.first_choice.values[0],
            "second": self.second_choice.values[0]
        }
        if not await self.finalize_join(interaction, pref_data):
            return await interaction.edit_original_response(content=STAFF_TIME_PASSED_MSG, view=None)
        await interaction.edit_original_response(
            content=f"{EMOJI_CHECK_STR} Shift request submitted.\n1st Choice: **{pref_data['first']}**\n2nd Choice: **{pref_data['second']}**", 
            view=None
        )

    async def skip_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await self.finalize_join(interaction, None):
            return await interaction.edit_original_response(content=STAFF_TIME_PASSED_MSG, view=None)
        await interaction.edit_original_response(
            content=EMOJI_CHECK_STR + " Joined without preference.", 
            view=None
        )


async def set_member_attendance(flight: dict, uid: int, status: str):
    global global_db_dirty
    async with global_json_lock:
        flight.setdefault("accepted_users", [])
        flight.setdefault("declined_users", [])
        if status == "accept":
            if uid not in flight["accepted_users"]:
                flight["accepted_users"].append(uid)
            if uid in flight["declined_users"]:
                flight["declined_users"].remove(uid)
        else:
            if uid not in flight["declined_users"]:
                flight["declined_users"].append(uid)
            if uid in flight["accepted_users"]:
                flight["accepted_users"].remove(uid)
        global_db_dirty = True


class FlightSignupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def get_flight_code(self, interaction):
        embed = interaction.message.embeds[0]
        if embed.footer and embed.footer.text:

            match = re.search(r"Flight Code: (.+?) \|", embed.footer.text)
            if match:
                return match.group(1).strip()
        return None

    async def handle_action(self, interaction: discord.Interaction, action: str, staff_message=None):
        global global_db_dirty
        staff_message = staff_message or interaction.message
        flight_code = await self.get_flight_code(interaction)
        if not flight_code:
            return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Error', 'Error reading flight.', discord.Color.red()), content=None), ephemeral=True)
        user_id = interaction.user.id
        now_ts = int(datetime.datetime.now().timestamp())

        target_idx = next((i for i, f in enumerate(FLIGHT_LOG_CACHE) if f["flight_code"] == flight_code), -1)
        if target_idx == -1:
            return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Error', 'Error: Flight not found.', discord.Color.red()), content=None), ephemeral=True)
        flight = FLIGHT_LOG_CACHE[target_idx]


        if flight.get("is_locked"):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Recruitment for this flight is already closed.')]))

        if staff_time_passed(flight):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, STAFF_TIME_PASSED_MSG)]))



        if user_id == flight.get("host_id"):
            if action == "decline" or (action == "accept" and user_id in flight.get("accepted_users", [])):
                return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Error', '**The host cannot remove their accepted status or decline.**', discord.Color.red()), content=None), ephemeral=True)

        staff_ts = flight.get("staff_timestamp", 0)
        is_late = (staff_ts - now_ts) <= 3600
        needs_modal = False

        if action == "accept" and user_id in flight.get("accepted_users", []) and is_late:
            needs_modal = True
        if action == "decline" and user_id in flight.get("accepted_users", []) and is_late:
            needs_modal = True

        if needs_modal:
            try:
                return await interaction.response.send_modal(CancelReasonModal(flight_code, user_id, action))
            except discord.NotFound:
                return 


        if action == "accept" and user_id not in flight.get("accepted_users", []):
            user_roles = [r.id for r in interaction.user.roles]
            departments = []
            
            if ROLE_FLIGHT_OPS in user_roles: departments.append("Flight Ops")
            if ROLE_CABIN_CREWS in user_roles: departments.append("Cabin Crew")
            if ROLE_GROUND_OPS in user_roles: departments.append("Ground Ops")
            

            if len(departments) > 1:
                view = ShiftRequestView(flight, user_id, departments)
                msg_content = (
                    "You belong to multiple departments. Select a 1st and 2nd choice department, or choose 'Join without preference'.\n"
                    "**You belong to multiple departments. Please select your 1st and 2nd choices, or click 'Join without Preference'.**"
                )
                return await interaction.response.send_message(msg_content, view=view, ephemeral=True)

            elif len(departments) == 1:
                flight.setdefault("shift_requests", {})
                flight["shift_requests"][str(user_id)] = {"first": departments[0], "second": "None"}

        try:
            await interaction.response.defer()
        except discord.NotFound:
            pass 

        join_status = None
        async with global_json_lock:


            flight = next((f for f in FLIGHT_LOG_CACHE if f.get("flight_code") == flight_code), None)
            if flight is None:
                return
            accepted = flight.setdefault("accepted_users", [])
            declined = flight.setdefault("declined_users", [])
            
            if action == "accept":
                if user_id in accepted:
                    accepted.remove(user_id)
                else:
                    accepted.append(user_id)
                    if user_id in declined: declined.remove(user_id)
                    join_status = "accepted"
                        
            elif action == "decline":
                if user_id in accepted:
                    accepted.remove(user_id)
                if user_id not in declined:
                    declined.append(user_id)
                    
            global_db_dirty = True

        if join_status:
            client.loop.create_task(notify_host_of_join(flight, interaction.user, join_status))

        await update_staff_embed_ui(staff_message, flight, interaction.guild)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(EMOJI_CHECK_STR),
                       custom_id="flight_btn_accept", row=0)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "accept")

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji.from_str(EMOJI_X_STR),
                       custom_id="flight_btn_decline", row=0)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "decline")

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.primary, custom_id="flight_btn_edit", row=0)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        flight_code = await self.get_flight_code(interaction)
        flight = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
        
        if not flight:
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_X_STR + ' Error: Flight not found.')]))
        
        if interaction.user.id != flight['host_id']:
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_X_STR + ' Error: Only the host who created this can edit it.')]))
        
        if flight.get("is_gamenight"):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, '**About editing a Game Night**\nPlease use the dedicated command **`/edit_gamenight`**!')]))
        

        now_ts = datetime.datetime.now().timestamp()
        is_urgent = (flight["start_timestamp"] - now_ts) <= 10800

        image_url, _ = await fetch_fresh_image_info(flight.get("source_channel_id"), flight.get("source_message_id"))
        await interaction.response.send_message(
            embed=build_edit_flight_embed(flight, flight_code, image_url=image_url),
            view=EditFlightOptionsView(flight, flight_code, is_urgent=is_urgent),
            ephemeral=True
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, custom_id="flight_btn_delete", row=0)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        global global_db_dirty
        flight_code = await self.get_flight_code(interaction)
        
        flight = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
        if not flight:
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_X_STR + ' Error: Data not found.')]))
        
        if interaction.user.id != flight['host_id']:
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_X_STR + ' Error: Only the host who created this can delete it.')]))


        now_ts = datetime.datetime.now().timestamp()
        is_urgent = (flight["start_timestamp"] - now_ts) <= 10800
        

        if is_urgent and not flight.get("is_test") and not flight.get("is_gamenight") and not flight.get("is_private"):
            await interaction.response.send_modal(DeleteReasonModal(flight_code, flight))
            return


        await interaction.response.defer(ephemeral=True)
        try:

            event_ok = await delete_flight_calendar_event(flight)


            if flight.get("is_test"):
                if flight.get("customer_channel_id"):
                    try:
                        test_ch = await client.fetch_channel(flight["customer_channel_id"])
                        if test_ch: await test_ch.delete()
                    except: pass
            elif flight.get("customer_message_id"):
                try:
                    c_ch = client.get_channel(CUSTOMER_CHANNEL_ID)
                    if c_ch is None:
                        try:
                            c_ch = await client.fetch_channel(CUSTOMER_CHANNEL_ID)
                        except Exception as e:
                            print(f"Failed to fetch the customer channel: {e}")
                    if c_ch:
                        await (await c_ch.fetch_message(flight["customer_message_id"])).delete()
                except: pass

            if flight.get("is_custom"):
                try:
                    src_ch = client.get_channel(flight["source_channel_id"])
                    if src_ch:
                        await (await src_ch.fetch_message(flight["source_message_id"])).delete()
                except: pass


            try:
                await interaction.message.delete()
            except: pass
            await delete_flight_staff_message(flight)


            saved = True
            async with global_json_lock:
                try:
                    await delete_flight_channels(flight)
                except Exception as e:
                    print(f"Flight channel cleanup on cancel error: {e}")
                FLIGHT_LOG_CACHE[:] = [f for f in FLIGHT_LOG_CACHE
                                       if f.get("flight_code") != flight_code
                                       and not (flight.get("staff_message_id") and f.get("staff_message_id") == flight.get("staff_message_id"))]
                global_db_dirty = True
                saved = await _save_flight_log_now()


            await auto_publish_schedule()

            warn = []
            if not event_ok:
                warn.append("Could not delete the calendar event. Please delete it manually.")
            if not saved:
                warn.append("Saving flight_log.json failed; the bot will retry automatically.")
            msg = EMOJI_CHECK_STR + " Deletion complete."
            if warn:
                msg = EMOJI_X_STR + " " + "\n".join(warn)
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, msg)]))
        except Exception as e:
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, f'{EMOJI_X_STR} Delete failed: {e}')]))



class PersistentCustomerView(discord.ui.View):
    def __init__(self, link_url: str = None, roblox_url: str = None):
        super().__init__(timeout=None)
        if link_url:
            self.add_item(discord.ui.Button(label="Join Event", style=discord.ButtonStyle.link, url=link_url))

    @discord.ui.button(label="Book Flight", style=discord.ButtonStyle.success,
                       custom_id="persistent_btn_book")
    async def book_flight(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            embed = interaction.message.embeds[0]
            fc_match = re.search(r"Flight (.+)", embed.title)
            if not fc_match:
                return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Error', EMOJI_X_STR + ' Cannot read info.', discord.Color.red()), content=None), ephemeral=True)
            flight_code = fc_match.group(1).strip()
            target = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
            if target:
                await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Check-in', f"Please join via the link:\n\n{target['event_url']}"), content=None), ephemeral=True)
            else:
                await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Error', EMOJI_X_STR + ' Data not found.', discord.Color.red()), content=None), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Error', f'{EMOJI_X_STR} {e}', discord.Color.red()), content=None), ephemeral=True)


class FlightListSelect(discord.ui.Select):
    def __init__(self, flights):
        options = []
        for f in flights[:25]:

            origin_str = f.get('origin', 'Game Night')
            dest_str = f.get('destination', 'Event')
            options.append(discord.SelectOption(
                label=f"{f['flight_code']} | {origin_str} ➝ {dest_str}",
                value=f['flight_code']))
        super().__init__(placeholder="① Select Flight", min_values=1, max_values=1, options=options,
                         custom_id="flight_list_select")

    async def callback(self, interaction: discord.Interaction):
        flight_code = self.values[0]
        flight = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
        if not flight:
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_X_STR + ' Error: Flight not found.')]))

        embed_color = get_embed_color(flight.get('color'))
        embed = discord.Embed(title=f"Flight {flight['flight_code']}", description="Welcome aboard.",
                              color=embed_color)
        embed.add_field(name="Route", value=f"{flight['origin']} ➝ {flight['destination']}", inline=False)
        start_ts = int(flight['start_timestamp'])
        embed.add_field(name="Departure Time", value=f"<t:{start_ts}:F>\n(<t:{start_ts}:R>)", inline=False)
        embed.add_field(name="Aircraft", value=flight.get('equipment', 'Unknown'), inline=True)
        embed.add_field(name="Classes", value=flight.get('classes', 'Unknown'), inline=True)

        image_url, _ = await fetch_fresh_image_info(flight.get("source_channel_id"), flight.get("source_message_id"))
        if image_url:
            embed.set_image(url=image_url)

        view = discord.ui.View(timeout=None)
        now = datetime.datetime.now().timestamp()
        active_flights = [f for f in FLIGHT_LOG_CACHE if f["end_timestamp"] > now]
        active_flights.sort(key=lambda x: x["start_timestamp"])
        view.add_item(FlightListSelect(active_flights))

        if flight.get('event_url'):
            view.add_item(discord.ui.Button(label="Join Event", style=discord.ButtonStyle.link, url=flight['event_url']))
        view.add_item(discord.ui.Button(label="Book Flight", style=discord.ButtonStyle.success,
                                        custom_id=f"dummy_book_{flight['flight_code']}", disabled=True))

        await interaction.response.edit_message(embed=embed, view=view)


class FlightListView(discord.ui.View):
    def __init__(self, flights):
        super().__init__(timeout=None)
        self.add_item(FlightListSelect(flights))





POSITION_TO_DEPT = {
    "Receptionist": "Cabin Crew", "Airport Guide": "Cabin Crew",
    "Lounge Agent": "Cabin Crew", "First Class": "Cabin Crew",
    "Business Class": "Cabin Crew", "Premium Economy": "Cabin Crew", "Economy Class": "Cabin Crew",
    "Captain": "Flight Ops", "First Officer": "Flight Ops",
    "GC Supervisor(MR)": "Ground Ops", "Ground Crew": "Ground Ops",
}

def describe_shift_pref(flight: dict, uid: int, pos_dept):
    pref = (flight.get("shift_requests") or {}).get(str(uid)) or {}
    first = (pref.get("first") or "").strip()
    second = (pref.get("second") or "").strip()
    if not first and not second:
        return 2, "", "No preference"
    desc = f"1st: {first or '-'} / 2nd: {second or '-'}"
    if pos_dept and first == pos_dept:
        return 0, "[1st] ", desc
    if pos_dept and (second == pos_dept or second == "Any"):
        return 1, "[2nd] ", desc
    return 2, "", desc

class AssignUserSelect(discord.ui.Select):
    def __init__(self, options):
        max_val = min(25, len(options)) if len(options) > 0 else 1
        super().__init__(placeholder="② Select Staff", min_values=1, max_values=max_val, options=options,
                         custom_id="user_select")

    async def callback(self, interaction: discord.Interaction):
        if "NONE" in self.values:
            return await interaction.response.defer()


        view = self.view

        if "NA" in self.values:
            view.assignments[view.current_position] = "N/A"
        else:
            view.assignments[view.current_position] = [int(v) for v in self.values]

        view.current_position = None
        view.refresh_ui()
        await interaction.response.edit_message(embed=view.generate_embed(), view=view)


class PositionSelect(discord.ui.Select):
    def __init__(self, parent_view):
        options = []
        for pos, desc, req_role in POSITIONS_DATA:
            val = parent_view.assignments.get(pos)
            if val == "DISABLED":
                continue
            is_selected = (parent_view.current_position == pos)

            if not parent_view.is_edit:
                if val == "UNASSIGNED" or is_selected:
                    options.append(discord.SelectOption(label=pos, description=desc, default=is_selected))
            else:
                options.append(discord.SelectOption(label=pos, description=desc, default=is_selected))

        if not options:
            options.append(discord.SelectOption(label="All positions assigned!", value="NONE"))
        super().__init__(placeholder="① Select Position", min_values=1, max_values=1, options=options,
                         custom_id="pos_select")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "NONE":
            return await interaction.response.defer()
            

        view = self.view
        view.current_position = self.values[0]
        req_role_id = next(r for p, d, r in POSITIONS_DATA if p == view.current_position)

        eligible_options = [discord.SelectOption(label="Set as N/A", value="NA")]
        pos_dept = POSITION_TO_DEPT.get(view.current_position)
        ranked = []
        for uid in view.flight.get("accepted_users", []):
            member = interaction.guild.get_member(uid)
            if member:
                if isinstance(req_role_id, tuple):
                    has_role = any(r.id in req_role_id for r in member.roles)
                else:
                    has_role = any(r.id == req_role_id for r in member.roles)
                if has_role:
                    rank, label, desc = describe_shift_pref(view.flight, uid, pos_dept)
                    ranked.append((rank, member.display_name.lower(), discord.SelectOption(
                        label=(label + member.display_name)[:100], value=str(member.id), description=desc)))
        ranked.sort(key=lambda x: (x[0], x[1]))
        eligible_options.extend(o for _, _, o in ranked)

        if len(eligible_options) == 1:
            eligible_options.append(discord.SelectOption(label="No eligible staff", value="NONE"))

        view.clear_items()
        view.add_item(PositionSelect(view))

        view.user_select = AssignUserSelect(eligible_options[:25])
        view.add_item(view.user_select)

        btn_confirm = discord.ui.Button(label="Review & Confirm", style=discord.ButtonStyle.primary, row=2)
        btn_confirm.callback = view.go_to_confirm
        view.add_item(btn_confirm)

        await interaction.response.edit_message(embed=view.generate_embed(), view=view)



















CABIN_CLASS_ORDER = ["First Class", "Business Class", "Premium Economy", "Economy Class"]


def parse_available_classes(classes_str) -> list:
    text = str(classes_str or "").lower()
    has_first = "first" in text
    has_business = "business" in text
    has_premium = "premium" in text

    rest = text.replace("premium economy", " ")
    has_economy = "economy" in rest
    if not (has_first or has_business or has_premium or has_economy):
        return list(CABIN_CLASS_ORDER)
    out = []
    if has_first: out.append("First Class")
    if has_business: out.append("Business Class")
    if has_premium: out.append("Premium Economy")
    out.append("Economy Class")
    return out


def cabin_class_unavailable(flight: dict, pos: str) -> bool:
    return pos in CABIN_CLASS_ORDER and pos not in parse_available_classes((flight or {}).get("classes"))


class BriefingSetupView(discord.ui.View):

    def __init__(self, flight, state, lang, guild, assignments=None, is_edit=False):
        super().__init__(timeout=900)
        self.flight = flight
        self.state = state
        self.lang = lang
        self.guild = guild
        self.is_edit = is_edit
        self.current_position = None

        self._autofill_pending = not assignments and not is_edit
        self.show_recruit = False
        self.available_classes = parse_available_classes(self.flight.get("classes"))

        if assignments:
            self.assignments = assignments
        else:
            self.assignments = {p[0]: "UNASSIGNED" for p in POSITIONS_DATA}
            self.assignments["Host"] = [flight["host_id"]]
            self.assignments["Gate Agent"] = [flight["host_id"]]
            if state["lounge"] != "Available":
                self.assignments["Lounge Agent"] = "DISABLED"



        for cls_name in CABIN_CLASS_ORDER:
            if cls_name not in self.available_classes and self.assignments.get(cls_name) in ("UNASSIGNED", "N/A", None):
                self.assignments[cls_name] = "DISABLED"

        self.refresh_ui()


    def _assigned_uids(self) -> set:
        ids = set()
        for v in self.assignments.values():
            if isinstance(v, int):
                ids.add(v)
            elif isinstance(v, list):
                ids.update(x for x in v if isinstance(x, int))
        return ids

    def _put(self, pos, uid) -> bool:
        cur = self.assignments.get(pos)
        if cur == "UNASSIGNED":
            self.assignments[pos] = [uid]
            return True
        if isinstance(cur, list) and uid not in cur:
            cur.append(uid)
            return True
        return False


    FLIGHT_CREW_POS = ("Captain", "First Officer")
    GROUND_CREW_POS = ("GC Supervisor(MR)", "Ground Crew")

    def _members_of(self, pos) -> list:
        v = self.assignments.get(pos)
        return [x for x in v if isinstance(x, int)] if isinstance(v, list) else []

    def _remove_uid(self, pos, uid) -> bool:
        v = self.assignments.get(pos)
        if isinstance(v, list) and uid in v:
            rest = [x for x in v if x != uid]
            self.assignments[pos] = rest if rest else "UNASSIGNED"
            return True
        return False

    def _dept_uids(self, positions) -> set:
        out = set()
        for pos in positions:
            out.update(self._members_of(pos))
        return out

    def _spread_cabin(self, pool) -> set:
        placed = set()
        pool = list(pool)
        empty = [c for c in self.available_classes if self.assignments.get(c) == "UNASSIGNED"]
        econ_empty = "Economy Class" in empty
        keep = 1 if econ_empty else 0
        for c in empty:
            if c == "Economy Class":
                continue
            if len(pool) > keep:
                uid = pool.pop(0)
                if self._put(c, uid):
                    placed.add(uid)
        for uid in pool:
            if self._put("Economy Class", uid):
                placed.add(uid)
        return placed

    def _borrow_empty_classes(self) -> list:
        avail = list(self.available_classes)
        filled = [c for c in avail if self._members_of(c)]
        borrowed = []
        if not filled:
            return borrowed
        for i, c in enumerate(avail):
            if self.assignments.get(c) != "UNASSIGNED":
                continue
            best = max(filled, key=lambda f: (len(self._members_of(f)), -abs(avail.index(f) - i)))
            src = self._members_of(best)
            self.assignments[c] = list(src) if c == "Economy Class" else [src[0]]
            borrowed.append(c)
        return borrowed

    def _assign_cabin_duties(self) -> int:
        people = []
        for c in CABIN_CLASS_ORDER:
            for u in self._members_of(c):
                if u not in people:
                    people.append(u)
        if not people:
            return 0
        REC, GUIDE, LOUNGE = "Receptionist", "Airport Guide", "Lounge Agent"
        n = 0
        if len(people) <= 3:
            if self.assignments.get(REC) == "UNASSIGNED":
                for u in people:
                    n += self._put(REC, u)
            return n
        targets = [pos for pos in (REC, GUIDE, LOUNGE) if self.assignments.get(pos) == "UNASSIGNED"]
        for i, u in enumerate(people):
            if targets:
                n += self._put(targets[i % len(targets)], u)
        return n


    def auto_fill_unassigned(self, guild=None) -> int:
        guild = guild or self.guild
        flight = self.flight
        if guild is None:
            return 0
        host_id = flight.get("host_id")
        already = self._assigned_uids()
        members = []
        for uid in flight.get("accepted_users", []):
            if not isinstance(uid, int) or uid in already or uid == host_id:
                continue
            m = guild.get_member(uid)
            if m:
                members.append(m)

        def has(member, role_id):
            if isinstance(role_id, (tuple, list, set)):
                return any(r.id in role_id for r in member.roles)
            return any(r.id == role_id for r in member.roles)


        placed = set()
        cabin_pool = []
        dual_ground = set()

        for m in members:
            uid = m.id
            roles = {
                "Cabin Crew": has(m, ROLE_CABIN_CREWS),
                "Ground Ops": has(m, ROLE_GROUND_OPS),
                "Flight Ops": has(m, ROLE_FLIGHT_OPS),
            }
            pref = (flight.get("shift_requests") or {}).get(str(uid), {}).get("first")

            if has(m, ROLE_EVENT_MANAGERS) and not any(roles.values()):
                roles["Cabin Crew"] = True


            ground_first = roles["Ground Ops"] and (not roles["Cabin Crew"] or pref == "Ground Ops")
            if roles["Ground Ops"] and roles["Cabin Crew"] and not ground_first:
                dual_ground.add(uid)

            flight_first = roles["Flight Ops"] and not (pref == "Cabin Crew" and roles["Cabin Crew"])


            if flight_first and self.assignments.get("Captain") == "UNASSIGNED":
                placed.add(uid) if self._put("Captain", uid) else None
                continue
            if flight_first and self.assignments.get("First Officer") == "UNASSIGNED":
                placed.add(uid) if self._put("First Officer", uid) else None
                continue
            if ground_first and self.assignments.get("Ground Crew") == "UNASSIGNED":
                placed.add(uid) if self._put("Ground Crew", uid) else None
                continue


            dept = pref if pref and roles.get(pref) else next((d for d in ("Cabin Crew", "Ground Ops", "Flight Ops") if roles[d]), None)
            if dept == "Cabin Crew":
                cabin_pool.append(uid)
            elif dept == "Ground Ops":
                placed.add(uid) if self._put("Ground Crew", uid) else None
            elif dept == "Flight Ops":
                placed.add(uid) if self._put("First Officer", uid) else None


        if self.assignments.get("Ground Crew") == "UNASSIGNED" and dual_ground:
            manual_cabin = bool(self._dept_uids(CABIN_CLASS_ORDER))
            candidates = [u for u in cabin_pool if u in dual_ground]
            if candidates and (len(cabin_pool) >= 2 or manual_cabin):
                chosen = candidates[-1]
                if self._put("Ground Crew", chosen):
                    cabin_pool.remove(chosen)
                    placed.add(chosen)


        if cabin_pool:
            placed |= self._spread_cabin(cabin_pool)
            self._borrow_empty_classes()
        return len(placed)


    def ensure_minimum_coverage(self, guild=None) -> list:
        notes = []
        flight = self.flight
        guild = guild or self.guild
        host_id = flight.get("host_id")
        accepted = [u for u in flight.get("accepted_users", []) if isinstance(u, int) and u != host_id]

        def has_role(uid, role_id):
            m = guild.get_member(uid) if guild else None
            if not m:
                return False
            ids = set(role_id) if isinstance(role_id, (tuple, list, set)) else {role_id}
            return any(r.id in ids for r in m.roles)

        def mention(ids):
            return " ".join(f"<@{u}>" for u in ids)

        FC, GC = self.FLIGHT_CREW_POS, self.GROUND_CREW_POS
        CC = tuple(self.available_classes)


        if isinstance(host_id, int):
            self.assignments["Host"] = [host_id]
            self.assignments["Gate Agent"] = [host_id]

            removed = [pos for pos in FC + CC + GC if self._remove_uid(pos, host_id) and pos != "Economy Class"]
            if removed:
                notes.append(f"Host <@{host_id}> is limited to Host, Gate Agent, and Economy Class. Removed from {', '.join(removed)}")


        fc_set = self._dept_uids(FC)
        moved = []
        for pos in CC + GC:
            for uid in list(self._members_of(pos)):
                if uid in fc_set and self._remove_uid(pos, uid):
                    moved.append(uid)
        cc_set, gc_set = self._dept_uids(CC), self._dept_uids(GC)
        for uid in cc_set & gc_set:
            gc_left = self._dept_uids(GC) - {uid}
            cc_left = self._dept_uids(CC) - {uid}
            if gc_left:
                for pos in GC:
                    self._remove_uid(pos, uid)
                moved.append(uid)
            elif cc_left:
                for pos in CC:
                    self._remove_uid(pos, uid)
                moved.append(uid)
        if moved:
            notes.append(f"{mention(dict.fromkeys(moved))}  was in multiple departments, so only one was kept")

        placed_anywhere = self._dept_uids(FC + CC + GC)


        cap, fo = self._members_of("Captain"), self._members_of("First Officer")
        if not cap and fo:
            self.assignments["Captain"] = [fo[0]]
            self.assignments["First Officer"] = fo[1:] if fo[1:] else "UNASSIGNED"
            cap, fo = self._members_of("Captain"), self._members_of("First Officer")
        pilots = [u for u in accepted if has_role(u, ROLE_FLIGHT_OPS) and u not in placed_anywhere]
        if not cap and pilots:
            self.assignments["Captain"] = [pilots.pop(0)]
            notes.append(f"Captain (Flight Ops): {mention(self.assignments['Captain'])}")
        if self.assignments.get("First Officer") == "UNASSIGNED" and pilots:
            self.assignments["First Officer"] = [pilots.pop(0)]
            notes.append(f"First Officer (Flight Ops): {mention(self.assignments['First Officer'])}")
        cap, fo = self._members_of("Captain"), self._members_of("First Officer")

        if not cap:
            notes.append(f"{EMOJI_NOTI_STR} There is no Flight Crew (Captain). The sheet will show 'Please urgently recruit an FC'. The Host cannot be the captain.")


        placed_anywhere = self._dept_uids(FC + CC + GC)
        if not self._dept_uids(CC):
            cabin_pool = [u for u in accepted if u not in placed_anywhere and has_role(u, ROLE_CABIN_CREWS)]
            if not cabin_pool:
                cabin_pool = [u for u in accepted if u not in placed_anywhere and has_role(u, ROLE_EVENT_MANAGERS)]
            if cabin_pool:
                self._spread_cabin(cabin_pool)
                notes.append(f"Cabin Crew: {mention(cabin_pool)}")
        if self._dept_uids(CC):
            borrowed = self._borrow_empty_classes()
            if borrowed:
                notes.append(f"{', '.join(borrowed)}: no staff assigned, so another cabin member will cover it")
        else:
            notes.append(f"{EMOJI_NOTI_STR} There is no Cabin Crew. The sheet will show 'Please urgently recruit a CC'.")


        if not self._dept_uids(GC):
            gc_pool = [u for u in accepted if u not in self._dept_uids(FC + CC + GC) and has_role(u, ROLE_GROUND_OPS)][:1]
            if gc_pool:
                self.assignments["Ground Crew"] = gc_pool
                notes.append(f"Ground Crew (Ground Ops): {mention(gc_pool)}")
            else:
                notes.append(f"{EMOJI_NOTI_STR} There is no Ground Crew. The sheet will show 'Please urgently recruit a GC'.")


        try:
            self._assign_cabin_duties()
        except Exception as e:
            print(f"Cabin duties error ({flight.get('flight_code')}): {e}")



        if isinstance(host_id, int) and "Economy Class" in CC:
            self._put("Economy Class", host_id)
        return notes


    def _needs_recruit(self, key) -> bool:
        v = self.assignments.get(key)
        host_id = self.flight.get("host_id")
        if key in self.FLIGHT_CREW_POS:

            if self._members_of("Captain"):
                return False
            return v == "UNASSIGNED" or not self._dept_uids(self.FLIGHT_CREW_POS)
        if key in CABIN_CLASS_ORDER:

            real_cc = self._dept_uids(tuple(self.available_classes)) - {host_id}
            return v == "UNASSIGNED" or not real_cc
        if key == "Ground Crew":
            return v == "UNASSIGNED" or not self._dept_uids(self.GROUND_CREW_POS)
        return False

    def refresh_ui(self):
        self.clear_items()
        self.add_item(PositionSelect(self))
        self.user_select = AssignUserSelect([discord.SelectOption(label="Select position first", value="NONE")])
        self.user_select.disabled = True
        self.add_item(self.user_select)
        btn_confirm = discord.ui.Button(label="Review & Confirm", style=discord.ButtonStyle.primary, row=2)
        btn_confirm.callback = self.go_to_confirm
        self.add_item(btn_confirm)


    async def go_to_confirm(self, interaction: discord.Interaction):
        await interaction.response.defer()


        auto_filled = 0
        if self._autofill_pending:
            self._autofill_pending = False
            try:
                auto_filled = self.auto_fill_unassigned(interaction.guild or self.guild)
            except Exception as e:
                traceback.print_exc()
                print(f"Briefing auto-fill error ({self.flight.get('flight_code')}): {e}")

        cover_notes = []
        try:
            cover_notes = self.ensure_minimum_coverage(interaction.guild or self.guild)
        except Exception as e:
            traceback.print_exc()
            print(f"Briefing coverage check error ({self.flight.get('flight_code')}): {e}")

        self.show_recruit = True
        self.clear_items()
        btn_send = discord.ui.Button(label="Submit", style=discord.ButtonStyle.success)
        btn_send.callback = self.submit_briefing
        btn_back = discord.ui.Button(label="Back & Edit", style=discord.ButtonStyle.secondary)
        btn_back.callback = self.go_back
        self.add_item(btn_send)
        self.add_item(btn_back)
        self.current_position = None

        msg_text = "**Please confirm.**"
        if auto_filled:
            msg_text += f" (auto-assigned {auto_filled} unselected staff based on role and shift preferences)"
        if cover_notes:
            msg_text += "\n" + "\n".join(f"> {n}" for n in cover_notes)
        msg_text = msg_text[:1900]

        await interaction.edit_original_response(
            content=msg_text,
            embed=self.generate_embed(), view=self,
            allowed_mentions=discord.AllowedMentions.none()
        )


    async def go_back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.is_edit = True
        self.show_recruit = False
        self.refresh_ui()
        await interaction.edit_original_response(content="**Edit Mode**", embed=self.generate_embed(), view=self)

    def generate_embed(self):
        def get_user(key, default="N/A"):
            val = self.assignments.get(key)
            if val in ["DISABLED", "UNASSIGNED", "N/A", None]:
                return "N/A"
            if isinstance(val, list):
                return " ".join([f"<@{uid}>" for uid in val])
            return f"<@{val}>" if isinstance(val, int) else str(val)

        RECRUIT_TEXT = ({
            "FC": f"{EMOJI_NOTI_STR} Please urgently recruit an FC",
            "CC": f"{EMOJI_NOTI_STR} Please urgently recruit a CC",
            "GC": f"{EMOJI_NOTI_STR} Please urgently recruit a GC",
        } if self.lang == "JP" else {
            "FC": f"{EMOJI_NOTI_STR} Flight Crew needed urgently",
            "CC": f"{EMOJI_NOTI_STR} Cabin Crew needed urgently",
            "GC": f"{EMOJI_NOTI_STR} Ground Crew needed urgently",
        })

        def disp(key, default="N/A"):
            val = get_user(key, default)
            if val == "N/A" and getattr(self, "show_recruit", False) and self._needs_recruit(key):
                if key in CABIN_CLASS_ORDER:
                    return RECRUIT_TEXT["CC"]
                return RECRUIT_TEXT["GC"] if key == "Ground Crew" else RECRUIT_TEXT["FC"]
            return val

        tz_offset = parse_timezone_offset(self.flight.get("host_timezone_str", "GMT+9"))
        input_tz = datetime.timezone(datetime.timedelta(hours=tz_offset))
        start_ts = self.flight["start_timestamp"]
        start_dt = datetime.datetime.fromtimestamp(start_ts, tz=input_tz)

        try:
            reception_time = datetime.datetime.strptime(self.state["reception_end"], "%H:%M").time()
            reception_dt = datetime.datetime.combine(start_dt.date(), reception_time).replace(tzinfo=input_tz)
            if reception_dt < start_dt - datetime.timedelta(hours=12):
                reception_dt += datetime.timedelta(days=1)
        except:
            reception_dt = start_dt + datetime.timedelta(minutes=10)

        boarding_dt = reception_dt + datetime.timedelta(minutes=5)
        departure_dt = boarding_dt + datetime.timedelta(minutes=5)

        join_time_str = f"<t:{int(start_dt.timestamp())}:t>"
        st_reception = f"<t:{int(reception_dt.timestamp())}:t>"
        st_boarding = f"<t:{int(boarding_dt.timestamp())}:t>"
        st_departure = f"<t:{int(departure_dt.timestamp())}:t>"
        staff_time_str = f"<t:{self.flight['staff_timestamp']}:t>"


        cabin_str = "\n".join(
            f"> {c}: {disp(c)} " for c in CABIN_CLASS_ORDER if self.assignments.get(c) != "DISABLED")

        if self.lang == "JP":
            desc = f"""**Flight Information**
> Join time: {join_time_str}
> Reception closes: {st_reception}
> Boarding closes: {st_boarding}
> Departure: {st_departure}
> Gate: {self.state['gate']}
> Lounge: {'Available' if self.state['lounge'] == 'Available' else 'Unavailable'}
> Equipment: {self.flight['equipment']}

**Flight Management**
> Host: {get_user('Host')} 
> Co-host: {get_user('Co-host')}

**Airport Services**
> Receptionist: {get_user('Receptionist')} 
> Airport Guide: {get_user('Airport Guide')}
> Gate Agent: {get_user('Gate Agent')}
> Lounge Agent: {get_user('Lounge Agent')}

**Flight Crew Department**
> Captain: {disp('Captain')} 
> First Officer: {disp('First Officer')} 

**Cabin Crew Department**
{cabin_str}

**Ground Crew Department**
> GC Supervisor(MR): {get_user('GC Supervisor(MR)')} 
> Ground Crew: {disp('Ground Crew')}

Please be sure to join the server at the specified time, and also join the voice channel.
**# Staff boarding Time: {staff_time_str}**"""
        else:
            desc = f"""**Flight Information**
> Join Time: {join_time_str}
> Reception Close: {st_reception}
> Boarding Close: {st_boarding}
> Departure: {st_departure}
> Gate: {self.state['gate']}
> Lounge: {self.state['lounge']}
> Aircraft: {self.flight['equipment']}

**Flight Management**
> Host: {get_user('Host')} 
> Co-host: {get_user('Co-host')}

**Airport Services**
> Receptionist: {get_user('Receptionist')} 
> Airport Guide: {get_user('Airport Guide')}
> Gate Agent: {get_user('Gate Agent')}
> Lounge Agent: {get_user('Lounge Agent')}

**Flight Crew Department**
> Captain: {disp('Captain')} 
> First Officer: {disp('First Officer')} 

**Cabin Crew Department**
{cabin_str}

**Ground Crew Department**
> GC Supervisor(MR): {get_user('GC Supervisor(MR)')} 
> Ground Crew: {disp('Ground Crew')}

Please join the server and VC at the specified time.
**# Staff boarding Time: {staff_time_str}**"""

        if self.current_position:
            desc = f"{EMOJI_INFO_STR} Assigning for: **{self.current_position}**\n\n" + desc
        return discord.Embed(
            title=f"{EMOJI_BRAND_STR} | {self.flight['flight_code']} Briefing Sheet",
            description=desc, color=get_embed_color(self.flight.get('color')))

    async def submit_briefing(self, interaction: discord.Interaction):
        global global_db_dirty

        await interaction.response.defer()
        await interaction.edit_original_response(content=EMOJI_CHECK_STR + " Processing...", embed=None, view=None)


        if TEST_MODE or self.flight.get("test_mode"):
            try:
                target = next((f for f in TEST_FLIGHT_CACHE
                               if f.get("flight_code") == self.flight.get("flight_code")), None)
                if target is None:
                    raise ValueError("The isolated test flight was not found.")
                self.current_position = None
                target["briefing_sent"] = True
                target["briefing_assignments"] = copy.deepcopy(self.assignments)
                target["briefing_state"] = copy.deepcopy(self.state)
                target["briefing_lang"] = self.lang
                target["briefing_test_preview"] = self.generate_embed().description
                await _test_mode_record("edit_briefing" if self.is_edit else "briefing", interaction.user.id, "OK", {
                    "flight_code": target["flight_code"],
                    "assigned_positions": len(self.assignments),
                    "saved_without_publication": True,
                })

                await interaction.followup.send(
                    content="**[TEST MODE — visible only to you / sample post]**",
                    embed=self.generate_embed(), ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

                try:
                    _t, _v = await _test_post_briefing_to_test_channels(interaction, target, self.generate_embed())
                    await interaction.followup.send(
                        content=f"Also posted to the test chat {_t.mention} and VC {_v.mention} (visible to admins only).",
                        ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                except Exception as _exc:
                    print(f"[TEST MODE] briefing test channel error: {_exc}")
                    await interaction.followup.send(
                        content=f"Failed to post to the test chat / VC: {type(_exc).__name__}: {_exc}",
                        ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                await interaction.followup.send(ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), view=build_v2_card(
                    "Test briefing saved — not published",
                    [("Test result", f"`{target['flight_code']}` briefing content and assignments were saved to the test JSON.\nNothing was posted to the staff or customer channels.")],
                    color=0x2ECC71))
            except Exception as exc:
                await _test_mode_record("edit_briefing" if self.is_edit else "briefing", interaction.user.id, "FAIL", {"error": str(exc)})
                await interaction.followup.send(ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), view=build_v2_card(
                    "Test briefing failed", [(None, str(exc))], color=0xE74C3C))
            return

        target_channel = client.get_channel(BRIEFING_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send(view=embed_to_v2_layout(create_info_embed('Error', 'Briefing channel not found.', discord.Color.red()), content=None), ephemeral=True)
            return

        self.current_position = None
        final_embed = self.generate_embed()

        uids = set()
        for val in self.assignments.values():
            if isinstance(val, int):
                uids.add(val)
            elif isinstance(val, list):
                for v in val:
                    uids.add(v)
        mention_str = " ".join([f"<@{u}>" for u in uids])

        async with global_json_lock:
            fc_to_search = self.flight["flight_code"]
            target_idx = next(
                (i for i, f in enumerate(FLIGHT_LOG_CACHE) if f["flight_code"] == fc_to_search), -1)

            is_new_msg = True
            sent_msg = None
            edit_failed = None

            if self.is_edit and self.flight.get("briefing_message_id"):
                try:

                    b_msg = await target_channel.fetch_message(self.flight["briefing_message_id"])
                    await b_msg.edit(embed=final_embed)
                    sent_msg = b_msg
                    is_new_msg = False
                except discord.NotFound:

                    is_new_msg = True
                except Exception as e:


                    print(f"Briefing Edit Error: {e}")
                    edit_failed = e

            if edit_failed is None:

                if is_new_msg:
                    sent_msg = await target_channel.send(embed=final_embed)


                    if mention_str:
                        try:
                            ghost = await target_channel.send(mention_str)
                            await ghost.delete()
                        except Exception as e:
                            print(f"Briefing ghost mention failed: {e}")

                if target_idx != -1 and sent_msg:
                    FLIGHT_LOG_CACHE[target_idx]["briefing_message_id"] = sent_msg.id
                    FLIGHT_LOG_CACHE[target_idx]["briefing_sent"] = True
                    FLIGHT_LOG_CACHE[target_idx]["briefing_assignments"] = self.assignments
                    FLIGHT_LOG_CACHE[target_idx]["briefing_state"] = self.state
                    FLIGHT_LOG_CACHE[target_idx]["briefing_lang"] = self.lang
                global_db_dirty = True

        if edit_failed is not None:
            return await interaction.edit_original_response(
                content=(
                    f"{EMOJI_INFO_STR} Failed to edit the briefing sheet."
                    "The existing sheet is left as is.\n"
                    "Please try again later.\n"
                    f"```{edit_failed}```"
                )
            )

        action_text = "update (overwrite)" if not is_new_msg else "send"
        await interaction.edit_original_response(
            content=f"{EMOJI_CHECK_STR} Briefing sheet processed successfully! ({action_text})"
        )





async def assign_next_warning_roles(guild, user_ids):
    try:
        from . import config_core as _cc
        order = [rid for rid in getattr(_cc, "WARNING_ROLE_ORDER", ()) if rid]
    except Exception:
        order = []
    if not order:
        return "Warning role settings not found."

    roles = [guild.get_role(rid) for rid in order]
    me = guild.me
    lines = []
    for uid in user_ids:
        member = guild.get_member(uid)
        if member is None:
            try:
                member = await guild.fetch_member(uid)
            except Exception:
                member = None
        if member is None:
            lines.append(f"• <@{uid}>: member not found")
            continue
        if member.bot:
            lines.append(f"• {member.display_name}: skipped (bot)")
            continue
        have = [i for i, r in enumerate(roles) if r is not None and r in member.roles]
        highest = max(have) if have else -1
        if highest >= len(order) - 1:
            lines.append(f"• {member.display_name}: already at maximum (4 warnings)")
            continue
        nxt = highest + 1
        next_role = roles[nxt]
        if next_role is None:
            lines.append(f"• {member.display_name}: role to assign not found")
            continue
        if not me.guild_permissions.manage_roles or next_role.position >= me.top_role.position:
            lines.append(f"• {member.display_name}: the bot lacks role permissions")
            continue
        remove_roles = [roles[i] for i in have if i < nxt and roles[i] is not None]
        try:
            if remove_roles:
                await member.remove_roles(*remove_roles, reason="Flight-log absentee: warning escalated")
            await member.add_roles(next_role, reason="Flight-log absentee: warning")
            suffix = f" (removed: {', '.join(r.name for r in remove_roles)})" if remove_roles else ""
            lines.append(f"• {member.display_name}: **{next_role.name}** assigned{suffix}")
        except discord.Forbidden:
            lines.append(f"• {member.display_name}: failed (forbidden)")
        except Exception as e:
            lines.append(f"• {member.display_name}: failed ({e})")
    if not lines:
        return "No targets."
    return "Warning assigned:\n" + "\n".join(lines)





class FlightLogAbsentView(discord.ui.View):
    def __init__(self, flight, checks):
        super().__init__(timeout=300)
        self.flight = flight
        self.checks = checks
        self.absent_users = []
        self._warned_ids = set()


        self.absent_select = discord.ui.UserSelect(
            placeholder="Select absent users (optional)", 
            min_values=0, 
            max_values=25
        )
        self.absent_select.callback = self.select_callback
        self.add_item(self.absent_select)

    async def select_callback(self, interaction: discord.Interaction):
        self.absent_users = [user.id for user in self.absent_select.values]
        await interaction.response.defer()

    @discord.ui.button(label="Give Warning", style=discord.ButtonStyle.danger, row=1)
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "This command only works inside a server.", ephemeral=True)

        if self.flight.get("test_mode") or self.flight.get("selftest_log_channel_id"):
            return await interaction.response.send_message(
                "Test flight: no real warning roles will be assigned.", ephemeral=True)
        targets = [uid for uid in self.absent_users if uid not in self._warned_ids]
        if not targets:
            return await interaction.response.send_message(
                "Please select the absent users first (this also prevents assigning twice).\n"
                "Select absent users first (already-assigned users are skipped).", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        result = await assign_next_warning_roles(interaction.guild, targets)
        self._warned_ids.update(targets)
        await interaction.followup.send(result, ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_modal(FlightLogModal(self.flight, self.checks, self.absent_users))





def _test_survey_status_view(sflight, owner_id):
    view = _build_flight_archive_v2(sflight)
    uid = str(owner_id)
    res = (sflight.get("flight_survey_results") or {}).get(uid) or {}
    ratings = res.get("ratings") or {}
    total_q = len([q for q in _survey_questions(sflight, owner_id)])
    sent = owner_id in [int(x) for x in sflight.get("flight_survey_dm_sent_ids", [])]
    failed = owner_id in [int(x) for x in sflight.get("flight_survey_dm_failed_ids", [])]
    dl = sflight.get("flight_survey_deadline")
    lang = {"en": "English", "ja": "Japanese"}.get(res.get("language"), "Not selected")
    lines = [
        "**Survey status (test / visible only to you)**",
        f"DM: {'sent' if sent else ('send failed (DMs closed, etc.)' if failed else 'not sent')}",
        f"Deadline: <t:{int(dl)}:F> (<t:{int(dl)}:R>)" if dl else "Deadline: not set",
        f"Language: {lang}",
        f"Answers: {len(ratings)}/{total_q} questions" + (" / with comment" if (res.get('comment') or '').strip() else "")
        + (" / **complete**" if res.get("completed_at") else ""),
        "This display updates automatically when you answer using the DM buttons.",
    ]
    view.add_item(discord.ui.Container(discord.ui.TextDisplay("\n".join(lines)), accent_color=0x3498DB))
    return view


def _test_survey_signature(sflight, owner_id):
    res = (sflight.get("flight_survey_results") or {}).get(str(owner_id)) or {}
    return (res.get("language"), tuple(sorted((res.get("ratings") or {}).items())),
            res.get("comment"), res.get("completed_at"),
            tuple(sflight.get("flight_survey_dm_sent_ids", [])), tuple(sflight.get("flight_survey_dm_failed_ids", [])))


async def _test_survey_auto_refresh(msg, sflight, owner_id, max_seconds=14 * 60):
    last = _test_survey_signature(sflight, owner_id)
    waited = 0
    while waited < max_seconds:
        await asyncio.sleep(2)
        waited += 2
        cur = _test_survey_signature(sflight, owner_id)
        if cur == last:
            continue
        last = cur
        try:
            await msg.edit(view=_test_survey_status_view(sflight, owner_id))
        except Exception as exc:
            print(f"[TEST MODE] survey status auto-refresh stopped: {exc}")
            return
        if cur[3]:
            return


async def _test_send_chat_archive(interaction, flight):
    code = flight.get("flight_code")
    ids = _TEST_BRIEFING_CHANNELS.get(code) or _TEST_BRIEFING_CHANNELS.get(str(code))
    messages = []
    note = ""
    if ids:
        for cid in ids:
            try:
                ch = client.get_channel(cid) or await client.fetch_channel(cid)
                async for m in ch.history(limit=5000, oldest_first=True):
                    messages.append(m)
            except Exception as exc:
                print(f"[TEST MODE] chat history error ({cid}): {exc}")
        messages.sort(key=lambda x: x.created_at)
    else:
        note = "\n(The test chat has not been created yet, so the history is empty. Please run the test briefing first.)"
    transcript = build_chat_transcript(messages)
    safe = re.sub(r"[^\w\-]+", "_", str(code or "flight")).strip("_") or "flight"
    await interaction.followup.send(
        content="[TEST MODE — chat history TXT / in production this is posted to the archive channel after the Flight-log is submitted]" + note,
        file=discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"{safe}_chat.txt"),
        ephemeral=True)


TEST_BRIEFING_CATEGORY_ID = cfg("channels.test_briefing_category")
_TEST_BRIEFING_CHANNELS = {}


async def _test_post_briefing_to_test_channels(interaction, flight, embed):
    cat = client.get_channel(TEST_BRIEFING_CATEGORY_ID)
    if cat is None:
        cat = await client.fetch_channel(TEST_BRIEFING_CATEGORY_ID)
    if not isinstance(cat, discord.CategoryChannel):
        raise ValueError(f"ID {TEST_BRIEFING_CATEGORY_ID} is not a category")
    guild = cat.guild
    code = str(flight.get("flight_code", "flight"))
    safe = re.sub(r"[^a-z0-9\-]+", "-", code.lower()).strip("-") or "flight"
    ow = _st_overwrites(guild, interaction.user)
    text = discord.utils.get(cat.text_channels, name=f"test-chat-{safe}")
    if text is None:
        text = await guild.create_text_channel(f"test-chat-{safe}", category=cat, overwrites=ow, reason="test_admin briefing")
    vc = discord.utils.get(cat.voice_channels, name=f"test-vc-{safe}")
    if vc is None:
        vc = await guild.create_voice_channel(f"test-vc-{safe}", category=cat, overwrites=ow, reason="test_admin briefing")
    _TEST_BRIEFING_CHANNELS[code] = [text.id, vc.id]
    head = "**[TEST MODE — admins only / sample briefing post]**"
    await text.send(content=head, embed=embed, allowed_mentions=discord.AllowedMentions.none())
    await vc.send(content=head, embed=embed, allowed_mentions=discord.AllowedMentions.none())
    return text, vc


async def _test_cleanup_briefing_channels():
    for code, ids in list(_TEST_BRIEFING_CHANNELS.items()):
        for cid in ids:
            try:
                ch = client.get_channel(cid) or await client.fetch_channel(cid)
                await ch.delete(reason="test_admin finished")
            except Exception:
                pass
        _TEST_BRIEFING_CHANNELS.pop(code, None)


async def _test_show_flight_previews(interaction, flight):
    try:
        host_display = getattr(interaction.user, "display_name", "Host")
        color = get_embed_color(flight.get("color"))
        e = discord.Embed(title=signup_embed_title(flight, flight["flight_code"]), description=render_staff_description(flight), color=color)
        e.add_field(name="Host", value=host_display, inline=False)
        e.add_field(name="Route", value=f"{flight['origin']} ➝ {flight.get('destination', '')}", inline=False)
        e.add_field(name="Aircraft Equipment", value=flight["equipment"], inline=False)
        e.add_field(name="Aircraft Operator", value=flight.get("airline") or default_airline(), inline=False)
        e.add_field(name="Minimum Staff Needed", value=minimum_staff_text(), inline=False)
        e.add_field(name="Action", value=f"React to join.\n**Staff Briefing Time:** <t:{int(flight['staff_timestamp'])}:F>" + google_calendar_suffix(flight), inline=False)
        e.add_field(name="Time", value=f"<t:{flight['start_timestamp']}:F> - <t:{flight['end_timestamp']}:t> (<t:{flight['start_timestamp']}:R>)", inline=False)
        e.add_field(name=f"{EMOJI_CHECK_STR} Accepted (1)", value=f">>> {host_display}", inline=True)
        e.add_field(name=f"{EMOJI_X_STR} Declined (0)", value="-", inline=True)
        e.set_footer(text=signup_footer(flight['flight_code'], host_display))
        await interaction.followup.send(
            content="**[TEST MODE — visible only to you / sample staff recruitment post]**",
            embed=e, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        cust = build_customer_announcement(flight)
        await interaction.followup.send(
            content="**[TEST MODE — visible only to you / sample customer announcement post]**\n" + cust[:1800],
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        print(f"[TEST MODE] preview error: {exc}")
        traceback.print_exc()
        await interaction.followup.send(
            content=f"Error displaying the preview: {type(exc).__name__}: {exc}", ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())


async def _test_flight_log_submit(interaction, flight, checks, comment, content):
    code = flight.get("flight_code")
    try:
        target = next((f for f in TEST_FLIGHT_CACHE if f.get("flight_code") == code), None)
        if target is None:
            raise ValueError("The isolated test flight was not found.")
        target["flight_log_sent"] = True
        target["flight_log_checks"] = checks
        target["flight_log_comments"] = comment
        steps = ["Flight-log creation: OK"]
        await interaction.followup.send(
            content=("[TEST MODE — NOT POSTED]\n" + content)[:1900], ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

        survey_code = str(code)
        sflight = copy.deepcopy(target)
        sflight["selftest"] = True
        sflight["host_id"] = interaction.user.id
        sflight["briefing_assignments"] = {"Host": [interaction.user.id]}
        for k in ("flight_survey_results", "flight_survey_deadline", "flight_survey_dispatched",
                  "flight_survey_dm_sent_ids", "flight_survey_dm_failed_ids"):
            sflight.pop(k, None)
        sflight["end_timestamp"] = int(datetime.datetime.now().timestamp())
        _SELFTEST_FLIGHTS[survey_code] = sflight
        await start_flight_survey(sflight)
        sent = sflight.get("flight_survey_dm_sent_ids", [])
        failed = sflight.get("flight_survey_dm_failed_ids", [])
        if interaction.user.id in sent:
            steps.append("Survey DM sent: OK (to the runner only)")
        elif interaction.user.id in failed:
            steps.append("Survey DM send failed because DMs are closed (WARN)")
        else:
            raise RuntimeError("The survey send process did not complete")
        await _test_mode_record("flight_log", interaction.user.id, "OK", {"flight_code": code, "steps": steps})
        await interaction.followup.send(ephemeral=True, view=build_v2_card(
            "Test Flight-log completed — not posted", [("Result", "\n".join(steps))], color=0x2ECC71))

        try:
            await _test_send_chat_archive(interaction, target)
            steps.append("Chat history TXT created: OK (to the runner only)")
        except Exception as exc2:
            steps.append(f"Chat history TXT creation failed ({type(exc2).__name__}: {exc2})")
        smsg = await interaction.followup.send(ephemeral=True, wait=True,
                                               view=_test_survey_status_view(sflight, interaction.user.id))
        asyncio.create_task(_test_survey_auto_refresh(smsg, sflight, interaction.user.id))
    except Exception as exc:
        await _test_mode_record("flight_log", interaction.user.id, "FAIL", {"flight_code": code, "error": str(exc)})
        await interaction.followup.send(ephemeral=True, view=build_v2_card(
            "Test Flight-log failed", [(None, f"{type(exc).__name__}: {exc}")], color=0xE74C3C))


class FlightLogModal(discord.ui.Modal, title="Flight-log Comments"):
    comments = discord.ui.TextInput(label="Comments", style=discord.TextStyle.paragraph, required=True,
                                    placeholder="Thank you all for joining! It was perfect.")

    def __init__(self, flight, checks, absent_users=None):
        super().__init__()
        self.flight = flight
        self.checks = checks
        self.absent_users = absent_users or []

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)


        assigns = copy.deepcopy(self.flight.get("briefing_assignments", {}))
        for key, val in assigns.items():
            if isinstance(val, list):
                assigns[key] = [uid for uid in val if uid not in self.absent_users]
            elif isinstance(val, int):
                if val in self.absent_users:
                    assigns[key] = "N/A"

        def g(key, default="N/A"):
            v = assigns.get(key)
            if v in ["DISABLED", "UNASSIGNED", "N/A", None] or not v:
                return default
            if isinstance(v, list):
                return " ".join([f"<@{uid}>" for uid in v])
            return f"<@{v}>" if isinstance(v, int) else str(v)

        content = f"**{EMOJI_BRAND_STR} | {self.flight['flight_code']} Flight-log**\n\n"
        content += f"**Flight Management**\n> Host: {g('Host')}\n> Co-host: {g('Co-host')}\n\n"

        content += f"**Flight Crew Department**\n> Captain: {g('Captain')}\n> First Officer: {g('First Officer')}\n\n"
        content += f"**Airport Services**\n> Receptionist: {g('Receptionist')}\n> Airport Guide: {g('Airport Guide')}\n> Gate Agent: {g('Gate Agent')}\n> Lounge Agent: {g('Lounge Agent')}\n\n"
        content += f"**Cabin Crew Department**\n> First Class: {g('First Class')}\n> Business Class: {g('Business Class')}\n> Premium Economy: {g('Premium Economy')}\n> Economy Class: {g('Economy Class')}\n\n"
        content += f"**Ground Crew Department**\n> MR: {g('GC Supervisor(MR)')}\n> Crew: {g('Ground Crew')}\n"

        content += "-" * 65 + "\n"

        c_str = lambda b: EMOJI_CHECK_STR if b else EMOJI_X_STR
        content += f"FC: {c_str(self.checks['fc'])}\n"
        content += f"CC: {c_str(self.checks['cc'])}\n"
        content += f"GC: {c_str(self.checks['gc'])}\n"
        content += "-" * 67 + "\n"
        content += f"{self.comments.value}"



        if self.flight.get("test_mode"):
            await _test_flight_log_submit(interaction, self.flight, self.checks, self.comments.value, content)
            return


        log_channel = interaction.client.get_channel(
            self.flight.get("selftest_log_channel_id") or FLIGHT_LOG_HISTORY_CHANNEL_ID)

        chat_file = None
        try:
            chat_file = await build_flight_chat_transcript_file(self.flight)
        except Exception as e:
            print(f"Flight chat transcript attach error ({self.flight.get('flight_code')}): {e}")
        send_kwargs = {"content": content}
        if chat_file is not None:
            send_kwargs["file"] = chat_file
        if log_channel:
            await log_channel.send(**send_kwargs)
        else:
            await interaction.channel.send(**send_kwargs)

        async with global_json_lock:
            target_idx = next(
                (i for i, f in enumerate(FLIGHT_LOG_CACHE) if f["flight_code"] == self.flight['flight_code']), -1)
            if target_idx != -1:
                FLIGHT_LOG_CACHE[target_idx]["flight_log_sent"] = True
                FLIGHT_LOG_CACHE[target_idx]["flight_log_checks"] = self.checks
                FLIGHT_LOG_CACHE[target_idx]["flight_log_comments"] = self.comments.value


            global global_db_dirty
            global_db_dirty = True

        await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, EMOJI_CHECK_STR + ' Flight-log sent successfully to the log channel!')]))


        if not (self.flight.get("is_test") or self.flight.get("selftest")):
            try:
                await start_flight_survey(self.flight)
            except Exception as e:
                print(f"Flight survey start error ({self.flight.get('flight_code')}): {e}")







HELP_DATA = {
    "operations_group": {
        "name": "Operations / Notices",
        "ja": {
            "title": "Operations / Notices Commands",
            "desc": "Notify customers about flight progress and update information.",
            "usage": "`/join` — Join a voice channel with read-aloud, or send a server-open notice and DMs\n`/delay` — Delay notice\n`/cancel` — Cancellation notice and data removal\n`/host_change` — Change the host\n`/undo` — [Admin] Undo the last `/host_change`\n`/update_ui` — Force-sync images and information to the latest state\n`/close_signup` — Close recruitment early (run again to reopen)\n`/event_thread` — Create a thread for the recruitment message now",
            "params": [],
            "note": "`/cancel` When run, all related events and messages are deleted automatically. Twenty minutes before the join time, a dedicated VC and a listen-only chat are created along with a thread. The listen-only channel has a pinned 'Delete Flight Channels' button that only the host can press (it is deleted automatically when the Flight-log is submitted)."
        },
        "en": {
            "title": "Operations & Notifications",
            "desc": "Commands to update passengers on flight status.",
            "usage": "`/join` — Join your VC to read messages aloud (JP<->EN), or send a server open notice & DM\n`/delay` — Delay notice\n`/cancel` — Cancel notice & delete data\n`/host_change` — Change the host\n`/undo` — [Admin] Undo the latest /host_change\n`/update_ui` — Force-sync images and info\n`/close_signup` — Close signups early (run again to reopen)\n`/event_thread` — Create the signup thread right now",
            "params": [],
            "note": "`/cancel` automatically deletes all related messages and events. 20 minutes before the staff join time, a dedicated VC and chat are created together with the thread. The chat has a pinned \"Delete Flight Channels\" button that only the host can press (they are deleted automatically once the Flight-log is submitted)."
        }
    },
    "briefing_shift_group": {
        "name": "Briefing Management",
        "ja": {
            "title": "Briefing Management",
            "desc": "Commands for arranging staff and checking pre-departure preparations.",
            "usage": "`/briefing` — Create a briefing sheet and assign staff\n`/edit_briefing` — Edit a sheet that has already been sent\n`/checklist` — Check departure preparations (equipment, roles, briefing)\n`/find_staff` — Find flights with the given role unassigned\n`/manual_assign` — Manually set staff participation\n`/request_staff` — Request help for missing roles",
            "params": [],
            "note": "If the sheet is still not submitted 20 minutes before the join time, the host receives a DM."
        },
        "en": {
            "title": "Briefing Management",
            "desc": "Staff assignments and pre-flight checks.",
            "usage": "`/briefing` — Create the briefing sheet & assign staff\n`/edit_briefing` — Edit a sent briefing\n`/checklist` — Pre-flight check (aircraft, positions, briefing)\n`/find_staff` — Find flights missing a given position\n`/manual_assign` — Force add/remove staff\n`/request_staff` — Request help for missing roles",
            "params": [],
            "note": "If the briefing sheet is still missing 20 minutes before the staff join time, the host receives a DM."
        }
    },
    "schedule_group": {
        "name": "Schedule",
        "ja": {
            "title": "Schedule Commands",
            "desc": "View and publish upcoming flights.",
            "usage": "`/publish_schedule` — Force-rebuild the schedule (moves it to the bottom)\n`/flights` — Show active flights in a dropdown",
            "params": [],
            "note": ""
        },
        "en": {
            "title": "Schedules",
            "desc": "View or publish upcoming flight schedules.",
            "usage": "`/publish_schedule` — Force-regenerate the schedule and move it to the bottom\n`/flights` — Dropdown of active flights",
            "params": [],
            "note": ""
        }
    },
    "creation_group": {
        "name": "Flight Creation",
        "ja": {
            "title": "Flight Creation Commands",
            "desc": "Commands for creating and applying for new flights.",
            "usage": "`/flight_app` — Apply to host a new flight\n`/dispatch_app` — Turn your approved application into a live recruitment\n`/suggest_flight` — Suggest a random flight (you can apply directly)\n`/create_flight` — Create a registered flight\n`/create_custom_flight` — Create a custom flight (image required)\n`/create_private_flight` — Private flight (staff only, no customer notice)\n`/create_private_flight_template` — Create a private flight from a template\n`/recurring_flight` — Create a recurring flight (Discord repeating event)\n`/duplicate_flight` — Copy an existing flight to another date/time\n`/create_flighttest` / `/recurring_flighttest` — [Test] For the test server",
            "params": [],
            "note": "Only your own approved applications can be auto-expanded with `/dispatch_app`. If another customer flight is coming up soon, later flights are posted without a mention."
        },
        "en": {
            "title": "Create Events",
            "desc": "Commands to create or apply for new flights.",
            "usage": "`/flight_app` — Apply for a flight\n`/dispatch_app` — Dispatch your approved application\n`/suggest_flight` — Get a random flight suggestion (apply directly)\n`/create_flight` — Standard flight\n`/create_custom_flight` — Custom flight (image required)\n`/create_private_flight` — Private, staff-only flight (no customer notice)\n`/create_private_flight_template` — Private flight from a template\n`/recurring_flight` — Recurring flight (native repeating event)\n`/duplicate_flight` — Copy a flight to a new date/time\n`/create_flighttest` / `/recurring_flighttest` — [Test] Test server",
            "params": [],
            "note": "Approved applications can be dispatched directly. If another customer-facing flight is scheduled nearby, later flights are announced without a mention."
        }
    },
    "logs_records_group": {
        "name": "Flight Logs",
        "ja": {
            "title": "Flight Log Commands",
            "desc": "Record post-flight data and view staff participation history.",
            "usage": "`/flight_log` — Submit the post-flight evaluation log\n`/manual_log` — Manually add a past flight log\n`/flight_backup` — Fill in staff missing from a log\n`/editflightlog` — Edit a Flight-log that was already sent\n`/staff_profile` — View a user's profile, roles, and participation rate\n`/leaderboard` — Show the staff participation ranking",
            "params": [],
            "note": "The ranking switches between monthly and yearly, and can show worst-first. Submitting a Flight-log automatically deletes the dedicated VC and the listen-only channel, and saves the listen-only text history as a TXT file."
        },
        "en": {
            "title": "Logs & Records",
            "desc": "Submit post-flight logs and view participation history.",
            "usage": "`/flight_log` — Submit the log\n`/manual_log` — Add a past log manually\n`/flight_backup` — Add missing staff to a log\n`/editflightlog` — Edit an existing log\n`/staff_profile` — View a user's profile, roles and attendance\n`/leaderboard` — View participation rankings",
            "params": [],
            "note": "Leaderboards can be filtered by month or year. Submitting the Flight-log deletes the dedicated VC and chat automatically and archives the chat text as a TXT file."
        }
    },
    "stats_group": {
        "name": "Statistics",
        "ja": {
            "title": "Statistics Commands",
            "desc": "View route and staff activity as numbers.",
            "usage": "`/route_stats` — Route performance (number of runs, average participants, etc.)\n`/flight_stats_graph` — [Manager] Show flight statistics as a graph\n`/inactive_staff` — [Admin] List staff who have not participated in the last month",
            "params": [],
            "note": ""
        },
        "en": {
            "title": "Statistics & Analysis",
            "desc": "See route and staff activity in numbers.",
            "usage": "`/route_stats` — Route history (times flown, average participants, etc.)\n`/flight_stats_graph` — [Manager] Flight statistics as a graph\n`/inactive_staff` — [Admin] Staff with no flights in the past month",
            "params": [],
            "note": ""
        }
    },
    "loa_group": {
        "name": "Leave System (LOA)",
        "ja": {
            "title": "Leave System (LOA)",
            "desc": "Commands for applying for leave and returning from it.",
            "usage": "`/loa apply` — Apply for leave (schedule start and end times)\n`/loa return` — Return early from leave manually\n`/loa list` — [Admin] List staff currently on, or scheduled for, leave\n`/loa cancel` — [Admin] Force-cancel a leave\n`/loa restore_legacy` — [Admin] Restore leave data from old Flight Hub Core logs",
            "params": [],
            "note": "At the scheduled time the role is removed automatically, and at the end time it is restored."
        },
        "en": {
            "title": "Leave of Absence (LOA)",
            "desc": "Apply for and manage leaves of absence.",
            "usage": "`/loa apply` — Schedule a leave\n`/loa return` — Return early\n`/loa list` — [Admin] View staff on leave\n`/loa cancel` — [Admin] Force-cancel a leave\n`/loa restore_legacy` — [Admin] Restore leave data from old Flight Hub Core logs",
            "params": [],
            "note": "Roles are removed and restored automatically at the scheduled times."
        }
    },
    "hr_events_group": {
        "name": "HR / Game Night",
        "ja": {
            "title": "HR / Game Night Commands",
            "desc": "Evaluate and remind staff, and create events.",
            "usage": "`/send_evaluation` — Create an evaluation sheet and DM it (supports scheduled sending, monthly mode, and editing/cancelling schedules)\n`/remind` — DM staff who have not participated this month\n`/remind_status` — [Manager] List staff already reminded this month\n`/staff_gamenight` — Create a staff-only game night, etc.\n`/edit_gamenight` — Edit a game night you created",
            "params": [],
            "note": "These commands can only be run by administrators or specific roles. Game Nights have no Flight-log, so after they end, delete the VC and the listen-only channel with the pinned Delete Flight Channels button (host only)."
        },
        "en": {
            "title": "HR & Events",
            "desc": "Staff evaluations, reminders and events.",
            "usage": "`/send_evaluation` — Send/schedule evaluation DMs (edit or cancel scheduled sends)\n`/remind` — DM staff who haven't joined a flight this month\n`/remind_status` — [Manager] Staff already reminded this month\n`/staff_gamenight` — Create a staff-only game event\n`/edit_gamenight` — Edit a game night",
            "params": [],
            "note": "Restricted to Managers and Admins. Game Night has no Flight-log, so when it is over, delete the VC and chat with the host-only \"Delete Flight Channels\" button in the chat."
        }
    },
    "admin_tools_group": {
        "name": "Admin / System Tools",
        "ja": {
            "title": "Admin Tools",
            "desc": "Used for system maintenance, the aircraft guide, and troubleshooting.",
            "usage": "`/aircraft_guide` — Look up aircraft and their routes\n`/manage_templates` — Manage and delete registered templates\n`/restore_from_message` — Restore data from a recruitment message ID\n`/backupflight` — Recreate a Discord event that was deleted by mistake\n`/flight_app_backup` — [Admin] Convert old-format application text to the current format\n`/clear_logs` — [Admin] Safely delete old, unneeded data left in the JSON\n`/update` — [Admin] Reload and migrate saved data and check its state (Chief only)\n`/aps` — [Admin] Download a user's message history as JSON\n`/restart` — Force-restart the bot",
            "params": [],
            "note": "Used for system administration and repairing data inconsistencies."
        },
        "en": {
            "title": "Admin Tools",
            "desc": "Tools for system maintenance and troubleshooting.",
            "usage": "`/aircraft_guide` — Fleet guide & route search\n`/manage_templates` — Manage / delete saved templates\n`/restore_from_message` — Restore data from a signup message ID\n`/backupflight` — Recreate an accidentally deleted Discord event\n`/flight_app_backup` — [Admin] Convert an old text application to the current format\n`/clear_logs` — [Admin] Safely remove old unneeded data from the JSON store\n`/update` — [Admin] Reload/migrate saved data and check data status (Chief only)\n`/aps` — [Admin] Download a user's message history as JSON\n`/restart` — Force-restart the bot",
            "params": [],
            "note": "Used for system maintenance and recovery."
        }
    },
    "monitoring_recovery_group": {
        "name": "Monitoring / Recovery",
        "ja": {
            "title": "Monitoring / Recovery Commands",
            "desc": "Check bot health, flight lists, and staff participation, and restore backups.",
            "usage": "`/healthcheck` — [Manager] Check the bot, data loading, and the backup destination\n`/flight_dashboard` — [Manager] List current and upcoming flights\n`/staff_analytics` — [Manager] Summarize staff participation over the past 30 days\n`/restore` — [Manager] Check and restore flight_log.json from a backup message",
            "params": [],
            "note": "A backup of the current data is created before restoring. Please carefully check the source message ID."
        },
        "en": {
            "title": "Monitoring & Recovery",
            "desc": "Check bot health, flight activity, staff participation, and restore backups.",
            "usage": "`/healthcheck` — [Manager] Check bot, data-load and backup-channel health\n`/flight_dashboard` — [Manager] View current and upcoming flights\n`/staff_analytics` — [Manager] Aggregate staff participation over the last 30 days\n`/restore` — [Manager] Preview and restore flight_log.json from a backup message",
            "params": [],
            "note": "A pre-restore backup is created before replacing current data. Verify the source message ID carefully."
        }
    },
    "test_tools_group": {
        "name": "Tests / Diagnostics / Help",
        "ja": {
            "title": "Tests / Diagnostics / Help Commands",
            "desc": "Show bot help and run the isolated test environment and self-diagnostics that do not affect production.",
            "usage": "`/help` — Show how to use commands\n`/test_admin` — [Admin] Turn the isolated test environment on/off (turning it off sends a TXT of all test results)\n`/test_evaluate` — [Admin] Save the operations you did in tests and give an overall evaluation\n`/test_progress` — [Admin] Show test progress (creation, briefing, Flight-log, etc.)\n`/selftest` — [Admin] Run self-diagnostics on all features and post the result to the admin-only channel",
            "params": [],
            "note": "In the test environment, customer announcements, event creation, external sheet syncing, and production logs/surveys are not performed. Survey DMs are sent only to the runner."
        },
        "en": {
            "title": "Test, Diagnostics & Help",
            "desc": "Show the bot help, and run the isolated test environment and self-diagnostics that never touch production.",
            "usage": "`/help` — Show command help\n`/test_admin` — [Admin] Toggle the isolated test environment (turning it off sends a TXT report of every check)\n`/test_evaluate` — [Admin] Save and evaluate the operations run in test mode\n`/test_progress` — [Admin] Show test progress (create, briefing, Flight-log, etc.)\n`/selftest` — [Admin] Run a full self-diagnosis and post the result to the admin-only channel",
            "params": [],
            "note": "Test mode never sends customer announcements, creates events, syncs to external services, or touches the production log/survey. Survey DMs go only to the person running the test."
        }
    },
    "v2_tools_group": {
        "name": "Dashboard / Data / Polls",
        "ja": {
            "title": "Dashboard & Data Commands",
            "desc": "Overview, data export, search, polls, the on-duty role and scheduled announcements.",
            "usage": "`/dashboard` — Overview of flights, signups and configuration\n`/export` — [Manager] Export the flight log as CSV or JSON\n`/search` — Search flights by code, route or aircraft\n`/poll` — Create a poll with buttons and live results\n`/onduty` — Toggle the on-duty role for yourself\n`/news` — [Manager] Schedule an announcement for later\n`/news_list` — [Manager] List or cancel scheduled announcements",
            "params": [],
            "note": "Poll votes and scheduled announcements are written to the misc data backup so they survive a restart."
        },
        "en": {
            "title": "Dashboard, Data & Polls",
            "desc": "Overview, data export, search, polls, the on-duty role and scheduled announcements.",
            "usage": "`/dashboard` — Overview of flights, signups and configuration\n`/export` — [Manager] Export the flight log as CSV or JSON\n`/search` — Search flights by code, route or aircraft\n`/poll` — Create a poll with buttons and live results\n`/onduty` — Toggle the on-duty role for yourself\n`/news` — [Manager] Schedule an announcement for later\n`/news_list` — [Manager] List or cancel scheduled announcements",
            "params": [],
            "note": "Poll votes and scheduled announcements are written to the misc data backup so they survive a restart."
        }
    }
}


_HELP_CMD_TOKEN_RE = re.compile(r"`(/(?:[^`]+?))`")


class HelpView(discord.ui.LayoutView):
    def __init__(self, command_key: str = None, member=None):
        super().__init__(timeout=300)
        self.lang = "en"
        self.command_key = command_key if command_key in HELP_DATA else None
        self.levels = user_permission_levels(member) if member is not None else {PERM_EVERYONE}
        self._build()

    def _lock_usage(self, usage: str) -> str:
        if not usage:
            return usage
        def repl(match):
            command = match.group(1).strip()
            if can_run_command(self.levels, command):
                return match.group(0)
            return f"{EMOJI_X_STR} `{match.group(1)}`"
        return _HELP_CMD_TOKEN_RE.sub(repl, usage)

    def _category_accessible(self, usage: str) -> bool:
        commands = _HELP_CMD_TOKEN_RE.findall(usage or "")
        if not commands:
            return True
        return any(can_run_command(self.levels, c) for c in commands)

    def _permission_line(self) -> str:
        level = highest_permission(self.levels)
        label = PERMISSION_LABELS.get(level, PERMISSION_LABELS[PERM_EVERYONE])
        if self.lang == "ja":
            extra = " (you can run every command)" if level in (PERM_CHIEF, PERM_DISCORD_ADMIN) else ""
            return f"**Your permission: {label['ja']}{extra}**\n{EMOJI_X_STR} = You cannot run this with your permission."
        extra = " (you can run every command)" if level in (PERM_CHIEF, PERM_DISCORD_ADMIN) else ""
        return f"**Your permission: {label['en']}{extra}**\n{EMOJI_X_STR} = your role cannot run this command."

    def _content(self):
        if self.command_key:
            data = HELP_DATA[self.command_key]
            en = data["en"]
            ja = data["ja"]
            if self.lang == "en":
                sections = [("Your permission", self._permission_line()), (None, en["desc"]), ("Usage", self._lock_usage(en["usage"]))]
                if en["params"]:
                    sections.append(("Parameters", "\n".join(f"`{name}` — {desc}" for name, desc in en["params"])))
                if en["note"]:
                    sections.append(("Note", en["note"]))
                return en["title"], sections
            sections = [
                ("Your permission", self._permission_line()),
                ("Description", en['desc']),
                ("Usage", self._lock_usage(en['usage'])),
            ]
            if en["params"] or ja["params"]:
                en_params = "\n".join(f"`{name}` — {desc}" for name, desc in en["params"])
                sections.append(("Parameters", en_params.strip()))
            if en["note"] or ja["note"]:
                sections.append(("Notes", en['note'].strip()))
            return f"{en['title']} / {ja['title']}", sections

        en_lines = []
        ja_lines = []
        for key, data in list(HELP_DATA.items())[:25]:
            en_lines.append(f"`{data['en']['title']}` — {data['en']['desc'][:90]}")
            ja_lines.append(f"`{data['ja']['title']}` — {data['ja']['desc'][:90]}")
        en_legend = f"[Admin] Chief only · [Manager] Event Managers & Chief · [Staff] all staff · [Test] test server only.\n{EMOJI_X_STR} = your role cannot run this command."
        if self.lang == "en":
            return "Flight Hub Help", [
                ("Your permission", self._permission_line()),
                ("Getting started", "Run `/help` to open this menu. Select a category below to view command usage and notes, or use `/help command:` to open a category directly."),
                ("Available commands", "\n".join(en_lines)),
                ("Role labels", en_legend),
            ]
        return "Flight Hub Help", [
            ("Your permission", self._permission_line()),
            ("Getting started", "Run `/help` to open this menu. Select a category below to view its commands.\n"),
            ("Available commands", "\n".join(en_lines)),
            ("Role labels", en_legend),
        ]

    def _build(self):
        self.clear_items()
        title, sections = self._content()
        children = [discord.ui.TextDisplay(f"# {_component_text(title, 250)}")]
        for index, (heading, body) in enumerate(sections):
            if index:
                children.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
            if heading:
                children.append(discord.ui.TextDisplay(f"**{_component_text(heading, 250)}**"))
            if body:
                children.append(discord.ui.TextDisplay(_component_text(body, 3650)))
        children.extend([
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Flight Hub"),
        ])
        self.add_item(discord.ui.Container(*children, accent_color=EMBED_COLOR))

        options = []
        for key, data in list(HELP_DATA.items())[:25]:
            label = data["en"]["title"][:100]


            opt_emoji = None
            if not self._category_accessible(data["en"]["usage"]):
                opt_emoji = discord.PartialEmoji.from_str(EMOJI_X_STR)
            options.append(discord.SelectOption(label=label, value=key, emoji=opt_emoji))
        select_row = discord.ui.ActionRow()
        self.command_select = discord.ui.Select(
            placeholder="Select a command",
            min_values=1, max_values=1, options=options, custom_id=f"help_select_v2_{self.lang}",
        )
        self.command_select.callback = self._select_command
        select_row.add_item(self.command_select)
        self.add_item(select_row)

    async def _select_command(self, interaction: discord.Interaction):
        selected = self.command_select.values[0]
        self.command_key = selected if selected in HELP_DATA else None
        self._build()
        await interaction.response.edit_message(view=self)











async def send_staff_start_notice(item: dict):
    thread_id = item.get("briefing_thread_id")
    if not thread_id:
        return
    thread = client.get_channel(thread_id)
    if thread is None:
        thread = await client.fetch_channel(thread_id)

    mentions = " ".join(f"<@{uid}>" for uid in item.get("accepted_users", []))
    link = item.get("roblox_link") or ""
    has_link = link.startswith("http")
    code = item.get("flight_code", "")

    desc = (
        f"It is now the staff join time for **{code}**.\n"
        "Please join the game via the link below and **also join the voice channel (VC)** (link below)."
    )
    embed = discord.Embed(
        title="Staff join time has started!",
        description=desc,
        color=get_embed_color(item.get("color"))
    )
    embed.add_field(
        name="Game Link",
        value=(link if has_link else "(not set — please ask the host)"),
        inline=False
    )

    vc_url = None
    vc_id = (item.get("flight_channels") or {}).get("vc")
    vc_guild_id = (item.get("flight_channels") or {}).get("guild")
    if vc_id and vc_guild_id:
        vc_url = f"https://discord.com/channels/{vc_guild_id}/{vc_id}"
        embed.add_field(
            name="Voice Channel (VC) / \u30dc\u30a4\u30b9\u30c1\u30e3\u30f3\u30cd\u30eb",
            value=f"<#{vc_id}>\n{vc_url}",
            inline=False
        )

    content = mentions or None

    if has_link or vc_url:
        view = discord.ui.View(timeout=None)
        if has_link:
            view.add_item(discord.ui.Button(
                label="Join Game",
                style=discord.ButtonStyle.link,
                url=link,
                emoji=discord.PartialEmoji.from_str(EMOJI_LINK_STR)
            ))
        if vc_url:
            view.add_item(discord.ui.Button(
                label="Join VC",
                style=discord.ButtonStyle.link,
                url=vc_url
            ))
        await thread.send(content=content, embed=embed, view=view)
    else:
        await thread.send(content=content, embed=embed)


async def notify_host_of_join(flight: dict, member, status: str = "accepted"):
    try:

        if not flight.get("briefing_sent") or flight.get("is_gamenight"):
            return

        _assigned = set()
        for _v in (flight.get("briefing_assignments") or {}).values():
            if isinstance(_v, int):
                _assigned.add(_v)
            elif isinstance(_v, list):
                _assigned.update(x for x in _v if isinstance(x, int))
        if member.id in _assigned:
            return
        staff_ts = flight.get("staff_timestamp", 0)
        if not staff_ts or datetime.datetime.now().timestamp() >= staff_ts:
            return
        host_id = flight.get("host_id")
        if not host_id or member.id == host_id:
            return
        host = client.get_user(host_id) or await client.fetch_user(host_id)
        code = flight.get("flight_code", "")
        count = len(flight.get("accepted_users", []))
        embed = discord.Embed(title="New attendee",
                              description=f"**{member.display_name}** has joined **{code}**.",
                              color=get_embed_color(flight.get("color")))
        embed.add_field(name="Action needed",
                        value=f"{member.mention} is not on the briefing sheet yet. Please add them with `/edit_briefing`.",
                        inline=False)
        embed.add_field(name="Current attendees", value=f"**{count}**", inline=True)
        embed.add_field(name="Staff Briefing Time",
                        value=f"<t:{staff_ts}:F> (<t:{staff_ts}:R>)", inline=True)
        await host.send(embed=embed)
    except Exception as e:
        print(f"Host join notify error: {e}")





FLIGHT_CHANNEL_CATEGORY_ID = cfg("channels.flight_channel_category")




def _flight_channel_names(code: str):
    safe = re.sub(r"[^\w\-]+", "-", str(code or "flight")).strip("-") or "flight"
    return f"{safe}-VC", f"{safe}-chat"


def _flight_channel_people(item: dict):
    managers = set()
    if isinstance(item.get("host_id"), int):
        managers.add(item["host_id"])
    co = (item.get("briefing_assignments") or {}).get("Co-host")
    if isinstance(co, int):
        managers.add(co)
    elif isinstance(co, list):
        managers.update(v for v in co if isinstance(v, int))
    accepted = {u for u in item.get("accepted_users", []) if isinstance(u, int)}
    if item.get("is_gamenight"):
        participants = accepted
    else:
        participants = accepted
    return participants - managers, managers


async def _get_flight_channel_member(guild, uid: int):
    member = guild.get_member(uid)
    if member is None:
        try:
            member = await guild.fetch_member(uid)
        except Exception:
            member = None
    return member


def _flight_participant_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True, read_message_history=True, send_messages=True, attach_files=True,
        embed_links=True, add_reactions=True, use_external_emojis=True,
        connect=True, speak=True, stream=True, use_voice_activation=True)


def _flight_manager_overwrite(guild, for_bot: bool = False) -> discord.PermissionOverwrite:
    perms = discord.Permissions(discord.Permissions.all_channel().value & guild.me.guild_permissions.value)
    if not for_bot:
        perms.update(manage_channels=False, manage_roles=False, manage_webhooks=False, create_instant_invite=False)
    return discord.PermissionOverwrite.from_pair(perms, discord.Permissions.none())


async def sync_flight_channel_perms(item: dict):
    info = item.get("flight_channels")
    if not info:
        return
    participants, managers = _flight_channel_people(item)
    new = {}
    for uid in participants:
        new[uid] = "p"
    for uid in managers:
        new[uid] = "m"
    sig = [sorted(participants), sorted(managers)]
    old = {}
    for k, v in (info.get("members") or {}).items():
        try:
            old[int(k)] = v
        except (TypeError, ValueError):
            continue



    if item.get("flight_channels_sig") == sig and old == new:
        return
    vc = client.get_channel(info.get("vc"))
    chat = client.get_channel(info.get("chat"))
    channels = [c for c in (vc, chat) if c is not None]
    if not channels:
        return
    guild = channels[0].guild

    applied = {}
    for uid, role in new.items():
        if old.get(uid) == role:
            applied[uid] = role
            continue
        member = await _get_flight_channel_member(guild, uid)
        if member is None:
            continue
        ow = _flight_manager_overwrite(guild) if role == "m" else _flight_participant_overwrite()
        ok = True
        for ch in channels:
            try:
                await ch.set_permissions(member, overwrite=ow)
            except Exception as e:
                ok = False
                print(f"Flight channel perm error ({item.get('flight_code')}, {uid}): {e}")
        if ok:
            applied[uid] = role
    for uid in set(old) - set(new):
        member = await _get_flight_channel_member(guild, uid)
        if member is None:
            continue
        removed = True
        for ch in channels:
            try:
                await ch.set_permissions(member, overwrite=None)
            except Exception as e:
                removed = False
                print(f"Flight channel perm remove error ({item.get('flight_code')}, {uid}): {e}")
        if not removed:

            applied[uid] = old.get(uid, "p")


    info["members"] = {str(k): v for k, v in applied.items()}
    if applied.keys() == new.keys():
        item["flight_channels_sig"] = sig
    else:
        item.pop("flight_channels_sig", None)


async def create_flight_channels(item: dict) -> bool:
    category = client.get_channel(FLIGHT_CHANNEL_CATEGORY_ID)
    if not isinstance(category, discord.CategoryChannel):
        print(f"Flight channel category not found: {FLIGHT_CHANNEL_CATEGORY_ID}")
        return False
    guild = category.guild
    participants, managers = _flight_channel_people(item)


    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: _flight_manager_overwrite(guild, for_bot=True),
    }
    members_state = {}
    for uid in managers | participants:
        member = await _get_flight_channel_member(guild, uid)
        if member is None or member.id == guild.me.id:
            continue
        if uid in managers:
            overwrites[member] = _flight_manager_overwrite(guild)
            members_state[str(uid)] = "m"
        else:
            overwrites[member] = _flight_participant_overwrite()
            members_state[str(uid)] = "p"

    vc_name, chat_name = _flight_channel_names(item.get("flight_code"))
    vc = chat = None
    try:
        vc = await category.create_voice_channel(name=vc_name, overwrites=overwrites,
                                                 reason=f"Flight {item.get('flight_code')} VC")
        chat = await category.create_text_channel(name=chat_name, overwrites=overwrites,
                                                  topic=f"{item.get('flight_code')} listen-only chat",
                                                  reason=f"Flight {item.get('flight_code')} chat")
    except Exception:

        for ch in (vc, chat):
            if ch is not None:
                try:
                    await ch.delete()
                except Exception:
                    pass
        raise

    item["flight_channels"] = {"vc": vc.id, "chat": chat.id, "guild": guild.id, "members": members_state}
    item["flight_channels_created"] = True


    if {int(k) for k in members_state} == (managers | participants):
        item["flight_channels_sig"] = [sorted(participants), sorted(managers)]
    else:
        item.pop("flight_channels_sig", None)
    await post_flight_channel_delete_button(item)
    await _save_flight_log_now()
    return True



async def ensure_flight_voice_connection(item: dict):
    try:
        if not voice_libraries_available():

            warn_voice_libraries_once()
            return
        info = item.get("flight_channels") or {}
        vc_id = info.get("vc")
        guild_id = info.get("guild")
        if not vc_id or not guild_id:
            return
        now = datetime.datetime.now().timestamp()
        if now < item.get("staff_timestamp", 0):
            return
        if now > item.get("end_timestamp", 0) + 60:
            return
        guild = client.get_guild(guild_id)
        if guild is None:
            return
        channel = guild.get_channel(vc_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(vc_id)
            except Exception:
                return
        vc = guild.voice_client
        if vc is not None and vc.channel and vc.channel.id == channel.id:
            VOICE_CLIENTS[guild_id] = vc
            VOICE_TARGET_VC[guild_id] = channel.id
            VOICE_TARGET_TEXT.setdefault(guild_id, set()).update({i for i in (channel.id, info.get("chat")) if i})
            TTS_ENABLED[guild_id] = True

            if guild_id not in TTS_TASKS or TTS_TASKS[guild_id].done():
                _get_tts_queue(guild_id)
                TTS_TASKS[guild_id] = asyncio.create_task(_tts_queue_worker(guild_id))
            return
        if vc is not None and vc.channel:

            return
        if vc is None:
            vc = await channel.connect(reconnect=True)
        else:
            await vc.move_to(channel)
        VOICE_CLIENTS[guild_id] = vc
        VOICE_TARGET_VC[guild_id] = channel.id
        VOICE_TARGET_TEXT.setdefault(guild_id, set()).update({i for i in (channel.id, info.get("chat")) if i})
        TTS_ENABLED[guild_id] = True
        if guild_id not in TTS_TASKS or TTS_TASKS[guild_id].done():
            _get_tts_queue(guild_id)
            TTS_TASKS[guild_id] = asyncio.create_task(_tts_queue_worker(guild_id))
    except Exception as e:
        print(f"Flight VC auto-join error ({item.get('flight_code')}): {e}")

FLIGHT_CHAT_ARCHIVE_CHANNEL_ID = cfg("channels.flight_chat_archive")


def build_chat_transcript(messages) -> str:
    lines = []
    prev_date = None
    for m in messages:
        try:
            if m.type not in (discord.MessageType.default, discord.MessageType.reply):
                continue
        except Exception:
            pass
        text = (m.clean_content or "").replace("\r\n", "\n").strip()
        if not text:
            continue
        jst = m.created_at.astimezone(JST)
        if prev_date is not None and jst.date() != prev_date:
            lines.append(f"--- {jst.strftime('%Y-%m-%d')} ---")
        prev_date = jst.date()
        body = text.replace("\n", "\n      ")
        lines.append(f"{jst.strftime('%H:%M')} {m.author.display_name} {body}")
    return "\n".join(lines) if lines else "(\u30c1\u30e3\u30c3\u30c8\u306e\u30e1\u30c3\u30bb\u30fc\u30b8\u306f\u3042\u308a\u307e\u305b\u3093\u3067\u3057\u305f)"


async def build_flight_chat_transcript_file(item: dict):
    info = item.get("flight_channels") or {}
    chat_id = info.get("chat")
    if not chat_id:
        return None
    chat = client.get_channel(chat_id)
    if chat is None:
        try:
            chat = await client.fetch_channel(chat_id)
        except Exception:
            return None
    messages = []
    try:
        async for m in chat.history(limit=5000, oldest_first=True):
            messages.append(m)
    except Exception as e:
        print(f"Flight chat history error ({item.get('flight_code')}): {e}")
        return None

    try:
        vc_id = info.get("vc")
        if vc_id:
            vc = client.get_channel(vc_id) or await client.fetch_channel(vc_id)
            async for m in vc.history(limit=5000, oldest_first=True):
                messages.append(m)
            messages.sort(key=lambda x: x.created_at)
    except Exception:
        pass
    transcript = build_chat_transcript(messages)
    safe = re.sub(r"[^\w\-]+", "_", str(item.get("flight_code") or "flight")).strip("_") or "flight"
    return discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"{safe}_chat.txt")


async def _find_existing_flight_archive(item):
    code = str(item.get("flight_code") or "")
    if not code:
        return None
    safe = re.sub(r"[^\w\-]+", "_", code).strip("_") or "flight"
    fname = f"{safe}_chat.txt"
    try:
        dest_ch = (client.get_channel(FLIGHT_CHAT_ARCHIVE_CHANNEL_ID)
                   or await client.fetch_channel(FLIGHT_CHAT_ARCHIVE_CHANNEL_ID))
    except Exception:
        return None
    start_ts = item.get("start_timestamp") or 0
    end_ts = item.get("end_timestamp") or 0
    lo = (start_ts - 3600) if start_ts else 0
    hi = (end_ts + 43200) if end_ts else float("inf")
    try:
        async for m in dest_ch.history(limit=200):
            if m.author != client.user:
                continue
            if not any((getattr(a, "filename", "") or "") == fname for a in m.attachments):
                continue
            created = m.created_at.timestamp()
            if lo and created < lo:
                continue
            if created > hi:
                continue
            return m, dest_ch
    except Exception:
        pass
    return None


async def archive_flight_chat(item: dict) -> bool:



    _prev_ch = item.get("flight_archive_channel_id")
    _prev_id = item.get("flight_archive_message_id")
    _reuse = None
    if _prev_ch and _prev_id:
        try:
            _pc = client.get_channel(_prev_ch) or await client.fetch_channel(_prev_ch)
            _pm = await _pc.fetch_message(_prev_id)
            if any((getattr(a, "filename", "") or "").lower().endswith(".txt") for a in _pm.attachments):
                _reuse = (_pm, _pc)
        except Exception:
            _reuse = None
    if _reuse is None:

        _reuse = await _find_existing_flight_archive(item)
    if _reuse is not None:
        _pm, _pc = _reuse
        item["flight_archive_channel_id"] = _pc.id
        item["flight_archive_message_id"] = _pm.id
        return True
    info = item.get("flight_channels")
    if not info:
        return False
    file = await build_flight_chat_transcript_file(item)
    if file is None:
        return False

    dest_ch = client.get_channel(FLIGHT_CHAT_ARCHIVE_CHANNEL_ID)
    if dest_ch is None:
        dest_ch = await client.fetch_channel(FLIGHT_CHAT_ARCHIVE_CHANNEL_ID)



    filename = file.filename
    view = _build_flight_archive_v2(item, filename=filename)

    archive_msg = await dest_ch.send(view=view, file=file, allowed_mentions=discord.AllowedMentions.none())
    item["flight_archive_channel_id"] = dest_ch.id
    item["flight_archive_message_id"] = archive_msg.id
    global global_db_dirty
    global_db_dirty = True
    try:
        async with global_json_lock:
            await _save_flight_log_now()
    except Exception as exc:
        print(f"Could not persist archive message reference ({item.get('flight_code')}): {exc}")
    return True


def _build_flight_archive_v2(flight: dict, filename: str = None):
    view = discord.ui.LayoutView(timeout=None)
    code = str(flight.get("flight_code", "Flight"))
    origin, destination = flight.get("origin"), flight.get("destination")
    route = f"{origin}→{destination}" if origin and destination else (origin or destination or "Route unavailable")
    fmt = lambda ts: datetime.datetime.fromtimestamp(ts, JST).strftime("%H:%M") if ts else "--:--"
    host_id = flight.get("host_id")
    host_display = f"<@{host_id}>" if host_id else "N/A"
    start_str = fmt(flight.get('start_timestamp'))
    end_str = fmt(flight.get('end_timestamp'))
    text = f"**{code} - {route}**\nThe flight started normally and the Flight-log was created.\nStart time: {start_str}\nEnd time: {end_str}\nHost: {host_display}\nPlease check the attached TXT file for details.\n\nThis is a flight archive."
    children = [discord.ui.TextDisplay(text)]
    view.add_item(discord.ui.Container(*children, accent_color=EMBED_COLOR))
    if filename:
        view.add_item(discord.ui.File(f"attachment://{filename}"))
    return view







SURVEY_RATING_OPTIONS = [
    ("5", "Very satisfied", "Very satisfied"),
    ("4", "Satisfied", "Satisfied"),
    ("3", "Neutral", "Neutral"),
    ("2", "Dissatisfied", "Dissatisfied"),
    ("1", "Very dissatisfied", "Very dissatisfied"),
]
SURVEY_QUESTIONS = [
    ("overall", "Overall, how satisfied were you with this flight?", "Overall, how satisfied were you with this flight?"),
    ("organization", "How was the flight organization?", "How was the flight organization?"),
    ("briefing", "How clear was the briefing?", "How clear was the briefing?"),
    ("timing", "How was the time management?", "How was the time management?"),
    ("host", "How would you rate the host?", "How would you rate the host?"),
]
_SURVEY_BUSY = set()
_SURVEY_DISPATCHING = set()


_SELFTEST_FLIGHTS = {}


def _find_survey_flight(code):
    if str(code) in _SELFTEST_FLIGHTS:
        return _SELFTEST_FLIGHTS[str(code)]
    matches = [f for f in FLIGHT_LOG_CACHE if str(f.get("flight_code")) == str(code)]
    if not matches:
        return None
    return max(matches, key=lambda f: f.get("start_timestamp", 0))


def _survey_members(flight):
    ids = set()
    def add(v):
        if isinstance(v, int) and not isinstance(v, bool):
            ids.add(v)
        elif isinstance(v, str) and v.isdigit():
            ids.add(int(v))
        elif isinstance(v, (list, tuple, set)):
            for x in v: add(x)
        elif isinstance(v, dict):
            for x in v.values(): add(x)
    add(flight.get("host_id"))
    for value in (flight.get("briefing_assignments") or {}).values(): add(value)
    return sorted(ids)


def _survey_deadline_passed(flight):
    deadline = flight.get("flight_survey_deadline")
    try:
        return bool(deadline) and datetime.datetime.now().timestamp() >= float(deadline)
    except (TypeError, ValueError):
        return False


def _survey_questions(flight, uid):
    qs = list(SURVEY_QUESTIONS)
    try:
        host = int(flight.get("host_id") or 0)
    except (TypeError, ValueError):
        host = 0
    if int(uid) == host:
        qs = [q for q in qs if q[0] != "host"]
    return qs


async def _survey_save(flight=None):
    global global_db_dirty
    if flight is not None and flight.get("selftest"):
        return
    async with global_json_lock:
        global_db_dirty = True
        await _save_flight_log_now()


_SURVEY_ARCHIVE_LAST_ERROR = ""


async def _survey_append_archive(flight):
    global _SURVEY_ARCHIVE_LAST_ERROR
    _SURVEY_ARCHIVE_LAST_ERROR = ""
    ch_id = flight.get("flight_archive_channel_id")
    msg_id = flight.get("flight_archive_message_id")
    if not ch_id or not msg_id:
        return True
    try:
        ch = client.get_channel(ch_id) or await client.fetch_channel(ch_id)
        msg = await ch.fetch_message(msg_id)
    except Exception as e:
        _SURVEY_ARCHIVE_LAST_ERROR = f"archive fetch failed: {e}"
        return False
    filename = None
    reattach = None
    for a in msg.attachments:
        if (getattr(a, "filename", "") or "").lower().endswith(".txt"):
            filename = a.filename
            try:
                reattach = discord.File(io.BytesIO(await a.read()), filename=a.filename)
            except Exception as e:
                _SURVEY_ARCHIVE_LAST_ERROR = f"attachment read failed: {e}"
                return False
            break
    view = _build_flight_archive_v2(flight, filename=filename)
    try:
        edit_kwargs = {"view": view}
        if msg.embeds:

            edit_kwargs["embeds"] = []
        if reattach is not None:

            edit_kwargs["attachments"] = [reattach]
        await msg.edit(**edit_kwargs)
    except Exception as e:
        _SURVEY_ARCHIVE_LAST_ERROR = f"archive edit failed: {e}"
        print(f"Survey archive update failed ({flight.get('flight_code')}): {e}")
        return False
    return True


SURVEY_TEXT = {


    "en": {
        "title": "Post-Flight Survey",
        "ratings_done": "Ratings complete. You may add an optional comment, then press Submit to finish.",
        "comment_btn": "Add Comments",
        "submit_btn": "Submit",
        "thanks": "Thank you for completing the survey!",
        "already": "You have already submitted this survey. It cannot be submitted twice.",
        "closed": "This survey is closed. The 24-hour response window has expired.",
        "modal_title": "Additional Comments",
        "modal_label": "Anything else?",
        "need_all": "Please answer all rating questions first.",
    },
    "ja": {
        "title": "Post-flight Survey",
        "ratings_done": "Your ratings are complete. You may add a comment and then press Submit to finish.",
        "comment_btn": "Add a comment",
        "submit_btn": "Submit",
        "thanks": "Thank you for answering the survey!",
        "already": "This survey has already been answered. You cannot submit it a second time.",
        "closed": "This survey is closed (more than 24 hours past the deadline).",
        "modal_title": "Additional comment",
        "modal_label": "Any other comments are welcome",
        "need_all": "Please answer all rating items first.",
    },
}


def _survey_result(flight, uid):
    return (flight.get("flight_survey_results") or {}).get(str(uid)) or {}


def _survey_lang(flight, uid):
    return "en"


def _survey_render_payload(flight, uid):
    code = str(flight.get("flight_code"))
    res = _survey_result(flight, uid)
    lang = _survey_lang(flight, uid) or "en"
    view = discord.ui.View(timeout=None)
    if res.get("completed_at"):
        return SURVEY_TEXT[lang]["thanks"], view
    t = SURVEY_TEXT[lang]
    qs = _survey_questions(flight, uid)
    ratings = res.get("ratings") or {}
    answered = sum(1 for q in qs if q[0] in ratings)
    nxt = next((q for q in qs if q[0] not in ratings), None)
    if nxt is None:
        view.add_item(SurveyCommentItem(code, uid, lang))
        view.add_item(SurveyDoneItem(code, uid, lang))
        return t["ratings_done"], view
    for score, label_en, label_ja in SURVEY_RATING_OPTIONS:
        view.add_item(SurveyRatingItem(code, uid, nxt[0], score, label_ja if lang == "ja" else label_en))
    question = nxt[2] if lang == "ja" else nxt[1]
    return f"**{t['title']} — {answered + 1}/{len(qs)}**\n{question}", view


async def _survey_finish(flight, uid, comment=None):
    result = (flight.get("flight_survey_results") or {}).get(str(uid))
    if not result or result.get("completed_at"):
        return False
    if comment is not None:
        result["comment"] = comment.strip()
    result.setdefault("comment", "")
    result["completed_at"] = int(datetime.datetime.now().timestamp())
    return True


async def _survey_send_thanks(interaction, flight, uid):
    content, view = _survey_render_payload(flight, uid)
    try:
        await interaction.response.edit_message(content=content, view=view)
    except Exception:
        try:
            await interaction.response.send_message(content, ephemeral=True)
        except Exception:
            pass




class SurveyRatingItem(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"survey:r:(?P<code>[^:]+):(?P<uid>\d+):(?P<qkey>[a-z_]+):(?P<score>[1-5])"):
    def __init__(self, code, uid, qkey, score, label=None):
        self.code, self.uid, self.qkey, self.score = str(code), int(uid), str(qkey), str(score)
        if label is None:
            label = next((l for s, l, _ in SURVEY_RATING_OPTIONS if s == self.score), self.score)
        super().__init__(discord.ui.Button(
            label=label, style=discord.ButtonStyle.secondary,
            custom_id=f"survey:r:{self.code}:{self.uid}:{self.qkey}:{self.score}",
            row=0 if self.score in ("5", "4", "3") else 1))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["code"], int(match["uid"]), match["qkey"], match["score"])

    async def interaction_check(self, interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("This survey belongs to another member.", ephemeral=True)
            return False
        return True

    async def callback(self, interaction):
        flight = _find_survey_flight(self.code)
        if flight is None:
            return await interaction.response.send_message("This survey is no longer available.", ephemeral=True)
        if _survey_deadline_passed(flight):
            return await interaction.response.send_message(
                SURVEY_TEXT[_survey_lang(flight, self.uid) or "en"]["closed"], ephemeral=True)
        key = (self.code, self.uid)
        if key in _SURVEY_BUSY:
            return await interaction.response.send_message(
                "Your previous answer is being processed. Please wait.", ephemeral=True)
        _SURVEY_BUSY.add(key)
        try:
            qs = _survey_questions(flight, self.uid)
            result = flight.setdefault("flight_survey_results", {}).setdefault(
                str(self.uid), {"language": None, "ratings": {}})
            result.setdefault("ratings", {})
            changed = False


            if (not result.get("completed_at") and self.qkey in [q[0] for q in qs]
                    and self.qkey not in result["ratings"]):
                result["ratings"][self.qkey] = self.score
                if result.get("language") not in ("en", "ja"):
                    result["language"] = "en"
                changed = True
            content, view = _survey_render_payload(flight, self.uid)
            try:
                await interaction.response.edit_message(content=content, view=view)
            except discord.NotFound:
                pass
            if changed:
                await _survey_save(flight)
                await _survey_append_archive(flight)
        except Exception as e:
            print(f"Survey rating error ({self.code}, user {self.uid}): {e}")
            if not interaction.response.is_done():
                try:
                    await interaction.response.send_message(
                        "Your answer could not be processed. Please try again.", ephemeral=True)
                except Exception:
                    pass
        finally:
            _SURVEY_BUSY.discard(key)


class SurveyCommentModal(discord.ui.Modal):
    def __init__(self, code, uid):
        flight = _find_survey_flight(code)
        lang = (_survey_lang(flight, uid) if flight else None) or "en"
        t = SURVEY_TEXT[lang]
        super().__init__(title=t["modal_title"])
        self.code, self.uid = str(code), int(uid)
        self.comment = discord.ui.TextInput(label=t["modal_label"], style=discord.TextStyle.paragraph,
                                            required=False, max_length=1000)
        self.add_item(self.comment)

    async def on_submit(self, interaction):
        flight = _find_survey_flight(self.code)
        if interaction.user.id != self.uid:
            return await interaction.response.send_message("This survey is not for you.", ephemeral=True)
        if flight is None:
            return await interaction.response.send_message("This survey is no longer available.", ephemeral=True)
        t = SURVEY_TEXT[_survey_lang(flight, self.uid) or "en"]
        if _survey_deadline_passed(flight):
            return await interaction.response.send_message(t["closed"], ephemeral=True)
        result = (flight.get("flight_survey_results") or {}).get(str(self.uid))
        qs = _survey_questions(flight, self.uid)
        if not result or any(q[0] not in (result.get("ratings") or {}) for q in qs):
            return await interaction.response.send_message(t["need_all"], ephemeral=True)
        if not await _survey_finish(flight, self.uid, self.comment.value):
            return await interaction.response.send_message(t["already"], ephemeral=True)
        await _survey_send_thanks(interaction, flight, self.uid)
        await _survey_save(flight)
        await _survey_append_archive(flight)


class SurveyCommentItem(discord.ui.DynamicItem[discord.ui.Button],
                        template=r"survey:c:(?P<code>[^:]+):(?P<uid>\d+)"):
    def __init__(self, code, uid, lang="en"):
        self.code, self.uid = str(code), int(uid)
        super().__init__(discord.ui.Button(
            label=SURVEY_TEXT.get(lang, SURVEY_TEXT["en"])["comment_btn"], style=discord.ButtonStyle.secondary,
            custom_id=f"survey:c:{self.code}:{self.uid}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["code"], int(match["uid"]))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("This survey belongs to another member.", ephemeral=True)
            return False
        return True

    async def callback(self, interaction):
        flight = _find_survey_flight(self.code)
        if flight is None or _survey_deadline_passed(flight):
            return await interaction.response.send_message(
                "This survey is closed or no longer available.", ephemeral=True)
        if _survey_result(flight, self.uid).get("completed_at"):
            return await _survey_send_thanks(interaction, flight, self.uid)
        await interaction.response.send_modal(SurveyCommentModal(self.code, self.uid))


class SurveyDoneItem(discord.ui.DynamicItem[discord.ui.Button],
                     template=r"survey:d:(?P<code>[^:]+):(?P<uid>\d+)"):
    def __init__(self, code, uid, lang="en"):
        self.code, self.uid = str(code), int(uid)
        super().__init__(discord.ui.Button(
            label=SURVEY_TEXT.get(lang, SURVEY_TEXT["en"])["submit_btn"], style=discord.ButtonStyle.success,
            custom_id=f"survey:d:{self.code}:{self.uid}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["code"], int(match["uid"]))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("This survey belongs to another member.", ephemeral=True)
            return False
        return True

    async def callback(self, interaction):
        flight = _find_survey_flight(self.code)
        if flight is None:
            return await interaction.response.send_message("This survey is no longer available.", ephemeral=True)
        t = SURVEY_TEXT[_survey_lang(flight, self.uid) or "en"]
        if _survey_deadline_passed(flight):
            return await interaction.response.send_message(t["closed"], ephemeral=True)
        result = (flight.get("flight_survey_results") or {}).get(str(self.uid))
        qs = _survey_questions(flight, self.uid)
        if not result or any(q[0] not in (result.get("ratings") or {}) for q in qs):
            return await interaction.response.send_message(t["need_all"], ephemeral=True)
        if not await _survey_finish(flight, self.uid):
            return await _survey_send_thanks(interaction, flight, self.uid)
        await _survey_send_thanks(interaction, flight, self.uid)
        await _survey_save(flight)
        await _survey_append_archive(flight)


async def start_flight_survey(flight):
    code = str(flight.get("flight_code"))
    if code in _SURVEY_DISPATCHING:
        return
    _SURVEY_DISPATCHING.add(code)
    try:
        flight = _find_survey_flight(code) or flight


        if not flight.get("flight_survey_deadline"):
            try:
                flight_end_ts = int(float(flight.get("end_timestamp") or 0))
            except (TypeError, ValueError):
                flight_end_ts = 0
            if not flight_end_ts:

                print(f"Survey dispatch skipped ({code}): missing/invalid end_timestamp")
                return
            flight["flight_survey_deadline"] = flight_end_ts + 24 * 60 * 60
            await _survey_save(flight)
        if _survey_deadline_passed(flight):

            flight["flight_survey_dispatched"] = True
            await _survey_save(flight)
            return
        if flight.get("flight_survey_dispatched"):
            return
        member_ids = _survey_members(flight)
        sent = set(int(x) for x in flight.get("flight_survey_dm_sent_ids", []) if str(x).isdigit())
        failed = set(int(x) for x in flight.get("flight_survey_dm_failed_ids", []) if str(x).isdigit())
        deadline_ts = int(flight["flight_survey_deadline"])
        for uid in member_ids:
            if str(uid) in (flight.get("flight_survey_results") or {}) or uid in sent or uid in failed:
                continue
            try:
                user = client.get_user(uid) or await client.fetch_user(uid)
                body, view = _survey_render_payload(flight, uid)
                await user.send(

                    f"{code} — Post-Flight Survey\n"
                    "Please rate your flight experience using the buttons below.\n"
                    f"Deadline: <t:{deadline_ts}:F> (<t:{deadline_ts}:R>)\n\n{body}",
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none())
                sent.add(uid)
            except (discord.Forbidden, discord.NotFound) as e:
                failed.add(uid)
                print(f"Survey DM not deliverable ({code}, user {uid}): {e}")
            except Exception as e:
                print(f"Survey DM failed ({code}, user {uid}): {e}")
        live = _find_survey_flight(code) or flight
        live["flight_survey_dm_sent_ids"] = sorted(sent)
        live["flight_survey_dm_failed_ids"] = sorted(failed)
        results = live.get("flight_survey_results") or {}
        live["flight_survey_dispatched"] = all(
            uid in sent or uid in failed or str(uid) in results for uid in member_ids)
        await _survey_save(live)
    finally:
        _SURVEY_DISPATCHING.discard(code)


def _find_flight_by_chat_channel(channel_id, message_id=None):
    for f in FLIGHT_LOG_CACHE:
        if (f.get("flight_channels") or {}).get("chat") == channel_id:
            return f
    if message_id:
        for f in FLIGHT_LOG_CACHE:
            if f.get("flight_channel_button_msg_id") == message_id and f.get("flight_channels"):
                return f
    return None


async def _save_flight_log_now():
    global global_db_dirty
    try:
        if await save_json_to_channel(FLIGHT_LOG_CHANNEL_ID, FLIGHT_LOG_CACHE, "flight_log.json"):
            global_db_dirty = False
            return True
    except Exception as e:
        print(f"Immediate flight_log save error: {e}")
    global_db_dirty = True
    return False


class FlightChannelDeleteConfirmView(discord.ui.View):
    def __init__(self, chat_channel_id: int, host_id: int):
        super().__init__(timeout=60)
        self.chat_channel_id = chat_channel_id
        self.host_id = host_id

    @discord.ui.button(label="Yes, delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        global global_db_dirty
        if interaction.user.id != self.host_id:
            return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Not allowed', 'Only the flight host can delete these channels.', discord.Color.red()), content=None), ephemeral=True)
        await interaction.response.edit_message(
            embed=create_info_embed("Deleting...", "The VC and chat channels are being deleted.", discord.Color.orange()), view=None)


        _pre = _find_flight_by_chat_channel(self.chat_channel_id)
        if _pre:
            for _attempt in range(2):
                try:
                    await archive_flight_chat(_pre)
                    break
                except Exception as e:
                    print(f"Flight chat archive error on button ({_pre.get('flight_code')}, try {_attempt + 1}): {e}")
                    await asyncio.sleep(1)
        async with global_json_lock:
            item = _find_flight_by_chat_channel(self.chat_channel_id)
            if item:
                await delete_flight_channels(item)
                item["flight_channels_deleted_by_host"] = True
                global_db_dirty = True
                await _save_flight_log_now()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=create_info_embed("Cancelled", "The channels were not deleted.", discord.Color.green()), view=None)
        self.stop()


class FlightChannelDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Delete Channels", style=discord.ButtonStyle.danger, custom_id="flight_channels_delete")
    async def delete_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = _find_flight_by_chat_channel(interaction.channel.id, getattr(interaction.message, "id", None))
        if not item:
            return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Not found', 'This channel is no longer linked to a flight.', discord.Color.red()), content=None), ephemeral=True)
        host_id = item.get("host_id")
        if interaction.user.id != host_id:
            return await interaction.response.send_message(view=embed_to_v2_layout(create_info_embed('Not allowed', 'Only the flight host can delete these channels.', discord.Color.red()), content=None), ephemeral=True)
        await interaction.response.send_message(
            embed=create_info_embed(
                "Delete channels?",
                f"This will permanently delete **{item.get('flight_code')}-VC** and **{item.get('flight_code')}-chat**. This cannot be undone.",
                discord.Color.red()),
            view=FlightChannelDeleteConfirmView(interaction.channel.id, host_id), ephemeral=True)


async def _find_button_message(chat):
    try:
        async for m in chat.history(limit=100):
            if m.author == client.user and m.embeds and "Delete Flight Channels" in (m.embeds[0].title or ""):
                return m
    except Exception:
        pass
    return None


async def post_flight_channel_delete_button(item: dict) -> bool:
    info = item.get("flight_channels") or {}
    chat = client.get_channel(info.get("chat"))
    if chat is None:
        return False

    msg = None
    msg_id = item.get("flight_channel_button_msg_id")
    if msg_id:
        try:
            msg = await chat.fetch_message(msg_id)
        except discord.NotFound:
            msg = None
        except Exception:
            return False
    if msg is None and item.get("flight_channel_button_posted"):
        msg = await _find_button_message(chat)

    if msg is None:
        embed = discord.Embed(
            title="Delete Flight Channels",
            description=(
                "**Host only.** When you're finished, press the button below to delete this chat and the VC.\n\n"
                "These channels are deleted automatically after the Flight-log is submitted. "
                "Game Night has no Flight-log, so please use this button when the event is over."
            ),
            color=EMBED_COLOR
        )
        embed.set_footer(text=f"{item.get('flight_code', '')}")
        try:
            msg = await chat.send(embed=embed, view=FlightChannelDeleteView())
        except Exception as e:
            print(f"Delete button post error ({item.get('flight_code')}): {e}")
            return False
        item["flight_channel_button_pinned"] = False

    item["flight_channel_button_msg_id"] = msg.id
    item["flight_channel_button_posted"] = True


    if not getattr(msg, "pinned", False):
        try:
            await msg.pin(reason="Flight channel delete button")
            item["flight_channel_button_pinned"] = True
            try:
                async for m in chat.history(limit=5):
                    if m.type == discord.MessageType.pins_add and m.author == client.user:
                        await m.delete()
                        break
            except Exception:
                pass
        except Exception as e:
            item["flight_channel_pin_attempts"] = item.get("flight_channel_pin_attempts", 0) + 1
            print(f"Pin error ({item.get('flight_code')}): {e}")
    else:
        item["flight_channel_button_pinned"] = True
    return True


async def _cleanup_thread_created_notice(channel):
    if channel is None:
        return
    try:
        async for m in channel.history(limit=5):
            if m.type == discord.MessageType.thread_created and m.author == client.user:
                try:
                    await m.delete()
                except Exception:
                    pass
                break
    except Exception:
        pass


async def delete_flight_channels(item: dict, archive: bool = False):
    info = item.get("flight_channels")
    if not info:
        return
    if archive:
        for attempt in range(2):
            try:
                await archive_flight_chat(item)
                break
            except Exception as e:
                print(f"Flight chat archive error ({item.get('flight_code')}, try {attempt + 1}): {e}")
                await asyncio.sleep(1)
    all_deleted = True
    for key in ("vc", "chat"):
        ch = client.get_channel(info.get(key))
        if ch is None:
            continue
        try:
            await ch.delete(reason=f"Flight {item.get('flight_code')} finished")
        except discord.NotFound:
            pass
        except Exception as e:
            all_deleted = False
            print(f"Flight channel delete error ({item.get('flight_code')}, {key}): {e}")


    if all_deleted:
        item["flight_channels"] = None

    try:
        _g = info.get("guild")
        _targets = VOICE_TARGET_TEXT.get(_g)
        if _targets:
            _targets.discard(info.get("vc"))
            _targets.discard(info.get("chat"))
    except Exception:
        pass
    item.pop("flight_channels_sig", None)
    for _k in ("flight_channel_button_posted", "flight_channel_button_msg_id",
               "flight_channel_button_pinned", "flight_channel_pin_attempts"):
        item.pop(_k, None)


























async def get_server_display_name(user_id: int, guild_id: int = None, fallback=None) -> str:
    gids = []
    for g in (guild_id, STAFF_GUILD_ID, CUSTOMER_GUILD_ID):
        if g and g not in gids:
            gids.append(g)
    for gid in gids:
        guild = client.get_guild(gid)
        if guild is None:
            continue
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None
        if member is not None:
            return member.display_name
    user = client.get_user(user_id)
    if user is None:
        try:
            user = await client.fetch_user(user_id)
        except Exception:
            user = None
    if user is not None:
        return user.display_name
    return fallback if fallback is not None else str(user_id)


async def publish_queued_flight(flight: dict):
    global global_db_dirty
    try:
        host_user = client.get_user(flight["host_id"])
        if not host_user:
            host_user = await client.fetch_user(flight["host_id"])
            
        pass_dt = datetime.datetime.fromtimestamp(flight["start_timestamp"], tz=datetime.timezone.utc)
        end_dt = datetime.datetime.fromtimestamp(flight["end_timestamp"], tz=datetime.timezone.utc)
        staff_dt = datetime.datetime.fromtimestamp(flight["staff_timestamp"], tz=JST)

        image_url, image_bytes = await fetch_fresh_image_info(flight.get("source_channel_id"), flight.get("source_message_id"))

        is_private = flight.get("is_private", False)
        airline = flight.get("airline") or default_airline()
        


        c_guild = client.get_guild(STAFF_GUILD_ID if is_private else CUSTOMER_GUILD_ID)
        event_name = flight.get("event_title") or f"{flight['flight_code']} {flight['origin']}→{flight.get('destination', '')}"
        if is_private:
            event_name = f"[Private Flight] {event_name}"
        
        desc = f"`Host` <@{flight['host_id']}>\n`Origin` {flight['origin']}\n`Destination` {flight.get('destination', '')}\n> Information\n`Airline` {airline}\n`Aircraft` {flight['equipment']}\n`Classes` {flight.get('classes', 'Unknown')}"

        event = await c_guild.create_scheduled_event(
            name=event_name, description=desc,
            start_time=pass_dt, end_time=end_dt, location=flight['origin'],
            entity_type=discord.EntityType.external, privacy_level=discord.PrivacyLevel.guild_only,
            image=image_bytes
        )
        flight["event_url"] = event.url


        s_channel = client.get_guild(STAFF_GUILD_ID).get_channel(STAFF_CHANNEL_ID)

        embed_color = PRIVATE_FLIGHT_COLOR if is_private else get_embed_color(flight.get('color'))
        staff_embed = discord.Embed(title=signup_embed_title(flight, event_name), description=render_staff_description(flight), color=embed_color)
        if is_private:
            staff_embed.add_field(name="Private Flight", value="Staff-only recruitment. No customer notification will be sent.", inline=False)
        host_display = await get_server_display_name(flight["host_id"], flight.get("staff_guild_id") or STAFF_GUILD_ID,
                                                     fallback=host_user.display_name)
        staff_embed.add_field(name="Host", value=host_display, inline=False)
        
        staff_embed.add_field(name="Route", value=f"{flight['origin']} ➝ {flight.get('destination', '')}", inline=False)
        staff_embed.add_field(name="Aircraft Equipment", value=flight['equipment'], inline=False)
        staff_embed.add_field(name="Aircraft Operator", value=airline, inline=False)
        staff_embed.add_field(name="Minimum Staff Needed", value=minimum_staff_text(), inline=False)

        staff_embed.add_field(name="Action", value=f"React to join.\n**Staff Briefing Time:** <t:{int(staff_dt.timestamp())}:F>" + google_calendar_suffix(flight), inline=False)
        ts_start = flight["start_timestamp"]
        ts_end = flight["end_timestamp"]
        staff_embed.add_field(name="Time", value=f"<t:{ts_start}:F> - <t:{ts_end}:t> (<t:{ts_start}:R>)", inline=False)
        staff_embed.add_field(name=f"{EMOJI_CHECK_STR} Accepted (1)", value=f">>> {host_display}", inline=True)
        staff_embed.add_field(name=f"{EMOJI_X_STR} Declined (0)", value="-", inline=True)

        staff_embed.set_footer(text=signup_footer(flight['flight_code'], host_display))

        staff_image_file = embed_image_as_attachment(staff_embed, image_bytes, image_url,
                                                     prefix=f"staff_{flight['flight_code']}")
        
        staff_send_kwargs = {"content": "@everyone", "embed": staff_embed, "view": FlightSignupView()}
        if staff_image_file is not None:
            staff_send_kwargs["file"] = staff_image_file
        staff_msg = await s_channel.send(**staff_send_kwargs)
        flight["staff_message_id"] = staff_msg.id



        if is_private:
            flight["customer_msg_content"] = ""
            flight["pending_customer_msg"] = False
            flight["customer_message_id"] = None
            flight["queued_for_limit"] = False
            global_db_dirty = True
            await auto_publish_schedule()
            return

        mention_line = get_customer_mention_line(flight)
        lock_ts = ts_start + 1200
        cust_msg_content = (
            f"{EMOJI_TAIL_STR} **Flight Information**\n"
            f"Flight code: {flight['flight_code']}\n"
            f"Airline: {airline}\n"
            f"Departure Airport: {flight['origin']}\n"
            f"Arrival Airport: {flight.get('destination', '')}\n"
            f"Date: <t:{ts_start}:D>\n"
            f"Check-in Time: <t:{ts_start}:t>\n"
            f"Server Lock: <t:{lock_ts}:t>\n"
            f"Equipment: {flight['equipment']}\n"
            f"Class: {flight.get('classes', 'Unknown')}\n"
            f"{mention_line}"
            f"{EMOJI_LINK_STR} **[Discord Event Link]({event.url})**"
        )
        
        flight["customer_msg_content"] = cust_msg_content
        flight["queued_for_limit"] = False


        now_jst = datetime.datetime.now(JST)

        is_late_night = now_jst.hour >= 22 or now_jst.hour < 7
        if is_late_night:
            target_18 = now_jst.replace(hour=18, minute=0, second=0, microsecond=0)
            if now_jst.hour >= 22: target_18 += datetime.timedelta(days=1)
            flight["pending_customer_msg"] = True
            flight["customer_msg_timestamp"] = target_18.timestamp()
        else:
            c_channel = client.get_channel(CUSTOMER_CHANNEL_ID)
            if c_channel:
                sent = await post_customer_announcement(c_channel, flight, cust_msg_content)
                flight["customer_message_id"] = sent.id
            flight["pending_customer_msg"] = False

        global_db_dirty = True
        await auto_publish_schedule()
        
    except Exception as e:
        print(f"Queue Publish Error: {e}")
        
async def process_flight_creation(host_user, data, image_bytes, saved_image_url, end_time_str=None):
    try:
        _blocked = db_write_blocked_message()
        if _blocked:
            return False, _blocked
        async with global_json_lock:
            check_code = data["flight_code"]
            if any(f["flight_code"] == check_code and not f.get("messages_deleted") for f in FLIGHT_LOG_CACHE):
                return False, f"Flight/operation code `{data['flight_code']}` is already registered as active."

            tz_offset = parse_timezone_offset(data['host_timezone_str'])
            staff_dt = calculate_jst_time(data['staff_meet_datetime_str'], "", tz_offset)
            date_part = data['staff_meet_datetime_str'].split()[0]
            pass_dt = calculate_jst_time(date_part, data['passenger_time_str'], tz_offset)

            if not staff_dt or not pass_dt:
                return False, "Date format error."

            if pass_dt < staff_dt:
                pass_dt += datetime.timedelta(days=1)

            if end_time_str:
                end_dt = calculate_jst_time(date_part, end_time_str, tz_offset)
                if end_dt and end_dt < pass_dt:
                    end_dt += datetime.timedelta(days=1)
            else:
                end_dt = pass_dt + datetime.timedelta(hours=1)

            notify_20min = staff_dt - datetime.timedelta(minutes=20)

            is_custom = data.get("is_custom", False)
            

            used_origins = await get_used_origins(client, ignore_flight_code=data["flight_code"])
            if data["origin"].lower() in used_origins:
                return False, f"The origin '{data['origin']}' is already used by another active flight or application, so this flight cannot be created."


            dup_host_fc = await check_host_duplicate(client, host_user.id, ignore_flight_code=data["flight_code"])
            if dup_host_fc:
                return False, f"You are already the host of another active/pending flight (`{dup_host_fc}`), so you cannot create multiple flights at the same time."

            now_ts = datetime.datetime.now().timestamp()
        pass_ts = pass_dt.timestamp()




        now_ts = datetime.datetime.now().timestamp()
        pass_ts = pass_dt.timestamp()




        if not is_custom:
            app_channel = client.get_channel(FLIGHT_APP_CHANNEL_ID)
            if app_channel:
                is_approved = await check_flight_is_approved(app_channel, data["flight_code"], data["origin"])
                if not is_approved:
                    return False, "This flight has not been applied for and approved yet."

            if pass_ts < now_ts + (48 * 3600):
                return False, "Flights must be created at least 2 days (48 hours) before departure."









        log_channel = client.get_channel(FLIGHT_LOG_HISTORY_CHANNEL_ID)
        if not log_channel:



            return False, "System Error: staff flight-log channel was not found. Please try again in a moment."
        if log_channel:

            now_ts = datetime.datetime.now().timestamp()
            active_flights_count = sum(1 for f in FLIGHT_LOG_CACHE if f.get("end_timestamp", 0) > now_ts and not f.get("messages_deleted") and not f.get("queued_for_limit") and not f.get("is_test"))
            
            is_queued = active_flights_count >= 5

            airline = data.get("airline") or default_airline()

            roblox_link = data.get('roblox_link', '')

            custom_title = data.get('event_title')
            raw_mention = data.get('mention_str', f"<@&{NOTIFICATION_ROLE_ID}>")
            valid_tokens = []
            for token in raw_mention.split():
                if re.match(r'^<@&\d+>$', token) or token in ('@everyone', '@here'):
                    valid_tokens.append(token)
            target_role_str = ' '.join(valid_tokens) if valid_tokens else f"<@&{NOTIFICATION_ROLE_ID}>"

            save_origin = data['origin']
            save_dest = data['destination']
            save_equip = data['equipment']
            save_classes = data['classes']

            save_flight_code = data['flight_code']


            flight_dict = {
                "flight_code": save_flight_code,
                "origin": save_origin,
                "destination": save_dest,
                "equipment": save_equip,
                "classes": save_classes,
                "source_channel_id": data.get('source_channel_id'),
                "source_message_id": data.get('source_message_id'),
                "roblox_link": roblox_link, "airline": airline, "color": data.get('color', '1B3444'),
                "start_timestamp": int(pass_dt.timestamp()), "end_timestamp": int(end_dt.timestamp()),
                "staff_timestamp": int(staff_dt.timestamp()), "event_url": "", 
                "host_id": host_user.id, "staff_guild_id": STAFF_GUILD_ID,
                "staff_channel_id": STAFF_CHANNEL_ID, "staff_message_id": None,
                "customer_guild_id": CUSTOMER_GUILD_ID, "customer_channel_id": CUSTOMER_CHANNEL_ID,
                "customer_message_id": None, "notify_20min_timestamp": notify_20min.timestamp(),
                "notified_20min": False, "accepted_users": [host_user.id], "declined_users": [],
                "briefing_sent": False, "flight_log_sent": False,
                "pending_customer_msg": False, "customer_msg_timestamp": 0,
                "customer_msg_content": "",
                "host_timezone_str": data['host_timezone_str'],
                "messages_deleted": False,
                "event_title": custom_title,
                "mention_str": target_role_str,
                "is_custom": data.get("is_custom", False),
                "is_private": data.get("is_private", False),
                "queued_for_limit": is_queued,
                "no_mention": False
            }
            


            async with global_json_lock:
                if any(f.get("flight_code") == save_flight_code and not f.get("messages_deleted") for f in FLIGHT_LOG_CACHE):
                    return False, f"Flight/operation code `{data['flight_code']}` is already registered as active."
                FLIGHT_LOG_CACHE.append(flight_dict)
                global global_db_dirty
                global_db_dirty = True


        if data.get("is_custom"):
            await update_db_cache()


        if is_queued:
            status_msg = (
                "There are currently 5 or more active flights. Your flight has been **queued** and will be published automatically once an active flight ends."
            )
            if not data.get("is_private"):
                status_msg += "\n\nWhether the announcement mentions customers is decided when it is posted (no mention if one was sent within the last 24 hours)."
            return True, status_msg


        await publish_queued_flight(flight_dict)
        ok_msg = "Flight created and published successfully."
        if not data.get("is_private"):
            if flight_dict.get("pending_customer_msg"):
                ok_msg += "\nLate night: the customer announcement is scheduled for 18:00 JST. The mention is decided when it is posted (earliest departure first; no mention if one was sent within the last 24 hours)."
            elif flight_dict.get("no_mention"):
                ok_msg += "\nA mentioned announcement was already posted within the last 24 hours, so this one was posted **without a mention**."
        return True, ok_msg

    except Exception as e:
        traceback.print_exc()
        return False, f"System Error: {e}"





















_TEMPLATE_LAST_LOAD = 0.0
_TEMPLATE_RELOAD_LOCK = None
TEMPLATE_MAX_AGE_SEC = 60


async def ensure_templates_fresh(max_age: int = TEMPLATE_MAX_AGE_SEC):
    global _TEMPLATE_LAST_LOAD, _TEMPLATE_RELOAD_LOCK
    now = datetime.datetime.now().timestamp()
    if now - _TEMPLATE_LAST_LOAD < max_age:
        return
    if _TEMPLATE_RELOAD_LOCK is None:
        _TEMPLATE_RELOAD_LOCK = asyncio.Lock()
    async with _TEMPLATE_RELOAD_LOCK:
        if datetime.datetime.now().timestamp() - _TEMPLATE_LAST_LOAD < max_age:
            return
        try:
            await update_db_cache()
        except Exception as e:
            print(f"[template] on-demand reload failed (old templates kept): {e}")
        finally:
            _TEMPLATE_LAST_LOAD = datetime.datetime.now().timestamp()







async def flight_code_autocomplete(interaction: discord.Interaction, current: str):

    return [app_commands.Choice(name=item["label"], value=item["value"]) 
            for item in FLIGHT_AUTOCOMPLETE_CACHE 
            if current.lower() in item["search"]][:25]



async def equipment_autocomplete(interaction: discord.Interaction, current: str):
    selected_flight = interaction.namespace.flight_code
    choices = []


    if selected_flight and selected_flight in FLIGHT_DB:
        variants = FLIGHT_DB[selected_flight].get("variants", {})
        for eq in variants.keys():

            if current.lower() in eq.lower():
                choices.append(app_commands.Choice(name=eq, value=eq))




    if not choices:
        unique_eqs = set()
        for route_data in FLIGHT_DB.values():
            unique_eqs.update(route_data.get("variants", {}).keys())
        for eq in sorted(unique_eqs):
            if current.lower() in eq.lower():
                choices.append(app_commands.Choice(name=eq, value=eq))

    return choices[:25]


async def active_flight_autocomplete(interaction: discord.Interaction, current: str):
    now = datetime.datetime.now().timestamp()
    source_flights = TEST_FLIGHT_CACHE if TEST_MODE else FLIGHT_LOG_CACHE
    return [
        app_commands.Choice(
            name=f"{f['flight_code']} | {f.get('origin', 'Game Night')} ➝ {f.get('destination', 'Event')}",
            value=f['flight_code']
        )
        for f in source_flights
        if f["end_timestamp"] > now and current.lower() in f['flight_code'].lower()
    ][:25]

async def log_flight_autocomplete(interaction: discord.Interaction, current: str):
    now = datetime.datetime.now().timestamp()
    source_flights = TEST_FLIGHT_CACHE if TEST_MODE else FLIGHT_LOG_CACHE
    return [
        app_commands.Choice(
            name=f"{f['flight_code']} | {f.get('origin', 'Game Night')} ➝ {f.get('destination', 'Event')}",
            value=f['flight_code']
        ) 
        for f in source_flights 
        if not f.get("flight_log_sent") and f["end_timestamp"] + 86400 > now and current.lower() in f['flight_code'].lower()
    ][:25]


async def backup_flight_autocomplete(interaction: discord.Interaction, current: str):
    now = datetime.datetime.now().timestamp()
    source_flights = TEST_FLIGHT_CACHE if TEST_MODE else FLIGHT_LOG_CACHE
    return [
        app_commands.Choice(
            name=f"{f['flight_code']} | {f.get('origin', 'Game Night')} ➝ {f.get('destination', 'Event')}",
            value=f['flight_code']
        )
        for f in source_flights
        if f.get("flight_log_sent") and f["end_timestamp"] + 30 * 86400 > now and current.lower() in f['flight_code'].lower()
    ][:25]


async def customer_role_autocomplete(interaction: discord.Interaction, current: str):
    c_guild = interaction.client.get_guild(CUSTOMER_GUILD_ID)
    if not c_guild:
        return []
    choices = []
    for role in c_guild.roles:
        if role.is_default():
            continue
        if current.lower() in role.name.lower():
            choices.append(app_commands.Choice(name=role.name, value=str(role.id)))
    return choices[:25]


async def all_template_autocomplete(interaction: discord.Interaction, current: str):

    return [app_commands.Choice(name=item["label"], value=item["value"]) 
            for item in FLIGHT_AUTOCOMPLETE_CACHE 
            if current.lower() in item["search"]][:25]

async def year_month_autocomplete(interaction: discord.Interaction, current: str):
    jst_now = datetime.datetime.now(JST)
    choices = []

    for i in range(12):
        y = jst_now.year
        m = jst_now.month - i
        while m <= 0:
            m += 12
            y -= 1
        label = f"{y}-{m:02d}"
        if current in label:
            choices.append(app_commands.Choice(name=label, value=label))
    return choices[:25]



















loa_group = app_commands.Group(name="loa", description="Leave-of-absence (LOA) system commands.")

def parse_loa_datetime(dt_str: str):
    dt_str = dt_str.strip()
    try:
        return datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    except ValueError:
        pass
    try:
        return datetime.datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=JST)
    except ValueError:
        return None







client.tree.add_command(loa_group)







async def process_flighttest_creation(host_user, data, image_bytes, saved_image_url):
    try:
        async with global_json_lock:
            check_code = data["flight_code"]
            if any(f["flight_code"] == check_code and not f.get("messages_deleted") for f in FLIGHT_LOG_CACHE):
                return False, f"Flight `{data['flight_code']}` is already registered as active."

        tz_offset = parse_timezone_offset(data['host_timezone_str'])
        staff_dt = calculate_jst_time(data['staff_meet_datetime_str'], "", tz_offset)
        date_part = data['staff_meet_datetime_str'].split()[0]
        pass_dt = calculate_jst_time(date_part, data['passenger_time_str'], tz_offset)

        if not staff_dt or not pass_dt:
            return False, "The date format is invalid."
        if pass_dt < staff_dt:
            pass_dt += datetime.timedelta(days=1)
        end_dt = pass_dt + datetime.timedelta(hours=1)
        notify_20min = staff_dt - datetime.timedelta(minutes=20)
        lock_dt = pass_dt + datetime.timedelta(minutes=20)

        airline = data.get("airline") or default_airline()
        embed_color = get_embed_color(data.get('color'))
        

        channel_guild_id = CUSTOMER_GUILD_ID
        category_id = TEST_CUSTOMER_CATEGORY_ID
        channel_guild = client.get_guild(channel_guild_id)
        
        created_channel = None
        if channel_guild:
            category = channel_guild.get_channel(category_id)
            safe_name = host_user.display_name.lower().replace(" ", "-")
            ch_name = f"test-{safe_name}"
            try:
                created_channel = await channel_guild.create_text_channel(name=ch_name, category=category)
            except Exception as e:
                print(f"Test Channel Create Error: {e}")


        event_guild_id = STAFF_GUILD_ID
        event_guild = client.get_guild(event_guild_id)
        event_name = f"[test] {data['flight_code']} {data['origin']}→{data.get('destination', '')}"
        desc = f"`Host` {host_user.mention}\n`Origin` {data['origin']}\n`Destination` {data.get('destination', '')}\n> Information\n`Airline` {airline}\n`Aircraft` {data['equipment']}\n`Classes` {data.get('classes', 'Unknown')}"
        
        event_url = ""
        if event_guild:
            try:
                event = await event_guild.create_scheduled_event(
                    name=event_name, description=desc,
                    start_time=pass_dt, end_time=end_dt, location=data['origin'],
                    entity_type=discord.EntityType.external, privacy_level=discord.PrivacyLevel.guild_only,
                    image=image_bytes
                )
                event_url = event.url
            except Exception as e:
                print(f"Test Event Create Error: {e}")


        cust_msg_id = None
        if created_channel:
            cust_msg_content = (
                f"**Flight Schedule**\n\n"
                f"{EMOJI_TAIL_STR} **Flight Information**\n"
                f"Flight code: {data['flight_code']}\n"
                f"Airline: {airline}\n"
                f"Departure Airport: {data['origin']}\n"
                f"Arrival Airport: {data.get('destination', '')}\n"
                f"Date: <t:{int(pass_dt.timestamp())}:D>\n"
                f"Check-in Time: <t:{int(pass_dt.timestamp())}:t>\n"
                f"Server Lock: <t:{int(lock_dt.timestamp())}:t>\n"
                f"Equipment: {data['equipment']}\n"
                f"Class: {data.get('classes', 'Unknown')}\n"
                f"{EMOJI_LINK_STR} **[Discord Event Link]({event_url})**"
            )
            try:
                cust_msg = await created_channel.send(content=cust_msg_content, suppress_embeds=True, allowed_mentions=discord.AllowedMentions.none())
                cust_msg_id = cust_msg.id
            except Exception as e:
                print(f"Customer Message Send Error: {e}")


        staff_channel_id = TEST_STAFF_CHANNEL_ID
        s_channel = client.get_channel(staff_channel_id)
        
        staff_embed = discord.Embed(title=signup_embed_title(data, event_name), description=render_staff_description(data, "staff_description_test"), color=embed_color)
        host_display = await get_server_display_name(host_user.id, STAFF_GUILD_ID, fallback=host_user.display_name)
        staff_embed.add_field(name="Host", value=host_display, inline=False)
        staff_embed.add_field(name="Route", value=f"{data['origin']} ➝ {data.get('destination', '')}", inline=False)
        staff_embed.add_field(name="Aircraft Equipment", value=data['equipment'], inline=False)
        _cal_flight = {"flight_code": data.get("flight_code"), "origin": data.get("origin"),
                       "destination": data.get("destination"),
                       "start_timestamp": int(pass_dt.timestamp()), "end_timestamp": int(end_dt.timestamp())}
        staff_embed.add_field(name="Action", value=f"React to join.\n**Staff Briefing Time:** <t:{int(staff_dt.timestamp())}:F>" + google_calendar_suffix(_cal_flight, start_ts=int(staff_dt.timestamp())), inline=False)
        
        ts_start = int(pass_dt.timestamp())
        ts_end = int(end_dt.timestamp())
        staff_embed.add_field(name="Time", value=f"<t:{ts_start}:F> - <t:{ts_end}:t> (<t:{ts_start}:R>)", inline=False)
        staff_embed.add_field(name=f"{EMOJI_CHECK_STR} Accepted (1)", value=f">>> {host_display}", inline=True)
        staff_embed.add_field(name=f"{EMOJI_X_STR} Declined (0)", value="-", inline=True)

        save_flight_code = data['flight_code']
        staff_embed.set_footer(text=signup_footer(save_flight_code, host_display))

        staff_image_file = embed_image_as_attachment(staff_embed, image_bytes, saved_image_url,
                                                     prefix=f"staff_{save_flight_code}")


        async with global_json_lock:
            if any(f.get("flight_code") == save_flight_code and not f.get("messages_deleted") for f in FLIGHT_LOG_CACHE):
                return False, f"Flight `{data['flight_code']}` is already registered as active."

        staff_msg = None
        if s_channel:
            test_send_kwargs = {
                "content": "**[TEST FLIGHT]**",
                "embed": staff_embed,
                "view": FlightSignupView(),
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            if staff_image_file is not None:
                test_send_kwargs["file"] = staff_image_file
            staff_msg = await s_channel.send(**test_send_kwargs)

            flight_dict = {
                "flight_code": save_flight_code,
                "origin": data['origin'], "destination": data['destination'],
                "equipment": data['equipment'], "classes": data['classes'],
                "airline": airline, "color": data.get('color', '1B3444'),
                "start_timestamp": int(pass_dt.timestamp()), "end_timestamp": int(end_dt.timestamp()),
                "staff_timestamp": int(staff_dt.timestamp()), "event_url": event_url,
                "host_id": host_user.id, 
                "staff_guild_id": STAFF_GUILD_ID, 
                "staff_channel_id": staff_channel_id, "staff_message_id": staff_msg.id if staff_msg else None,
                "customer_guild_id": channel_guild_id, 
                "customer_channel_id": created_channel.id if created_channel else None,
                "customer_message_id": cust_msg_id, 
                "notify_20min_timestamp": notify_20min.timestamp(),
                "notified_20min": False, "accepted_users": [host_user.id], "declined_users": [],
                "briefing_sent": False, "flight_log_sent": False,
                "pending_customer_msg": False, "customer_msg_timestamp": 0,
                "host_timezone_str": data['host_timezone_str'],
                "messages_deleted": False, "is_custom": False,
                "is_test": True
            }
            async with global_json_lock:
                FLIGHT_LOG_CACHE.append(flight_dict)
                global global_db_dirty
                global_db_dirty = True

        return True, f"Created a test flight.\n- Channel: {created_channel.mention if created_channel else 'creation failed'}\n- Event: {event_url}"
    except Exception as e:
        traceback.print_exc()
        return False, f"System Error: {e}"


















def _signup_view_for(flight: dict):
    return RecurringFlightSignupView() if flight.get("is_recurring") else FlightSignupView()













async def update_discord_recurring_event(guild_id, event_id, name, desc, location, image_bytes=None):
    url = f"https://discord.com/api/v10/guilds/{guild_id}/scheduled-events/{event_id}"
    headers = {"Authorization": f"Bot {TOKEN}"}
    payload = {"name": name, "description": desc, "entity_metadata": {"location": location}}
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        payload["image"] = f"data:image/jpeg;base64,{b64}"
    async with aiohttp.ClientSession() as session:
        await session.patch(url, headers=headers, json=payload)

async def delete_discord_recurring_event(guild_id, event_id):
    url = f"https://discord.com/api/v10/guilds/{guild_id}/scheduled-events/{event_id}"
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as session:
        await session.delete(url, headers=headers)


class RouteChangeSelect(discord.ui.Select):
    def __init__(self, flight_code, routes=None):
        self.target_flight_code = flight_code
        routes = routes if routes is not None else [(i["value"], i["label"]) for i in FLIGHT_AUTOCOMPLETE_CACHE]
        options = [discord.SelectOption(label=label[:100], value=code[:100]) for code, label in routes[:25]]
        if not options:
            options = [discord.SelectOption(label="-", value="_")]
        super().__init__(placeholder="Select the route template for the next flight", min_values=1, max_values=1,
                         options=options, disabled=(options[0].value == "_"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_template_code = self.values[0]
        flight = next((f for f in FLIGHT_LOG_CACHE if f.get("flight_code") == self.target_flight_code), None)
        if not flight:
            return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'Flight not found.')]))
        if interaction.user.id != flight.get("host_id"):
            return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'Only the host can change the route.')]))
        if not FLIGHT_DB.get(new_template_code, {}).get("variants"):
            return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'The template was not found, or its equipment (image) is not registered.')]))
        await ensure_templates_fresh()
        try:
            used = await get_used_origins(interaction.client, ignore_flight_code=self.target_flight_code)
            routes = list_routes_for_edit(flight, used)
            if not routes:
                return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'No registered routes are available.')]))
            view = EditRouteChangeView(flight, self.target_flight_code, routes, is_urgent=False,
                                       preselect_code=new_template_code, guild=interaction.guild,
                                       origin_interaction=None)
            await interaction.followup.send(embed=view.make_embed(), view=view, ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, f'{EMOJI_X_STR} Error: {e}')]))

class RouteChangeView(discord.ui.View):
    def __init__(self, flight_code):
        super().__init__(timeout=300)
        self.add_item(RouteChangeSelect(flight_code))


class RecurringFlightSignupView(FlightSignupView):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="Change Route", style=discord.ButtonStyle.primary, custom_id="recur_change_route", row=1)
    async def change_route_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        flight_code = await self.get_flight_code(interaction)
        flight = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
        if not flight or interaction.user.id != flight.get('host_id'):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Only the host can change the route.')]))
        await interaction.response.send_message("Select the route for the next flight (the time will be kept)", view=RouteChangeView(flight_code), ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="recur_stop", row=1)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        global global_db_dirty
        flight_code = await self.get_flight_code(interaction)
        flight = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
        if not flight or interaction.user.id != flight.get('host_id'):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Only the host can stop this.')]))

        await interaction.response.defer(ephemeral=True)
        async with global_json_lock:

            flight["is_recurring"] = False
            

            if master_event_id := flight.get("master_event_id"):
                guild_id = STAFF_GUILD_ID if flight.get("is_test") else CUSTOMER_GUILD_ID
                await delete_discord_recurring_event(guild_id, master_event_id)
                
                try:
                    target_guild = client.get_guild(guild_id)
                    image_url, image_bytes = await fetch_fresh_image_info(flight.get("source_channel_id"), flight.get("source_message_id"))
                    
                    airline = flight.get("airline") or default_airline()
                    origin = flight.get("origin", "Unknown")
                    dest = flight.get("destination", "Unknown")
                    equipment = flight.get("equipment", "Unknown")
                    display_code = flight_code.replace("[TEST] ", "").replace("TEST_REC_", "").replace("REC_", "")
                    
                    event_name = f"{display_code} {origin}→{dest}"
                    desc = f"`Host` <@{flight['host_id']}>\n`Origin` {origin}\n`Destination` {dest}\n> Information\n`Airline` {airline}\n`Aircraft` {equipment}\n`Classes` {flight.get('classes', 'Unknown')}"
                    
                    pass_dt = datetime.datetime.fromtimestamp(flight["start_timestamp"], tz=datetime.timezone.utc)
                    end_dt = datetime.datetime.fromtimestamp(flight["end_timestamp"], tz=datetime.timezone.utc)
                    
                    new_event = await target_guild.create_scheduled_event(
                        name=event_name,
                        description=desc,
                        start_time=pass_dt,
                        end_time=end_dt,
                        location=origin,
                        entity_type=discord.EntityType.external,
                        privacy_level=discord.PrivacyLevel.guild_only,
                        image=image_bytes
                    )
                    flight["event_url"] = new_event.url
                    flight["master_event_id"] = None
                    

                    c_channel = client.get_channel(flight["customer_channel_id"])
                    if c_channel and flight.get("customer_message_id"):
                        c_msg = await c_channel.fetch_message(flight["customer_message_id"])
                        new_content = re.sub(r'https://discord.com/events/\d+/\d+', new_event.url, c_msg.content)
                        await c_msg.edit(content=new_content)
                except Exception as e:
                    print(f"Single event recreation failed: {e}")
            
            global_db_dirty = True
        

        for child in self.children:
            if child.custom_id in ["recur_change_route", "recur_stop"]:
                child.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'Stopped the automatic rotation of the recurring flight.\n(Note: the current recruitment for this flight continues as a normal one-off flight, and its log is fully deleted after it ends!)')]))


@tasks.loop(minutes=1)
@_resilient_task
async def recurring_spawner_task():
    if _AUTO_TEST_PAUSE:
        return
    global global_db_dirty
    if not data_ready(FLIGHT_LOG_CHANNEL_ID):
        return
    now = datetime.datetime.now().timestamp()
    
    async with global_json_lock:
        for f in FLIGHT_LOG_CACHE:
            if f.get("is_recurring") and now > f["end_timestamp"] and not f.get("messages_deleted"):
                try:
                    s_ch = client.get_channel(f["staff_channel_id"])
                    if s_ch:
                        old_msg = await s_ch.fetch_message(f["staff_message_id"])
                        await old_msg.delete()
                except: pass
                
                freq = f.get("recurring_freq", 2)
                interval_days = 1 if freq == 1 else (7 if freq == 2 else 14)
                add_sec = interval_days * 86400
                
                f["start_timestamp"] += add_sec
                f["end_timestamp"] += add_sec
                f["staff_timestamp"] += add_sec
                f["notify_20min_timestamp"] += add_sec
                
                f["accepted_users"] = [f["host_id"]]
                f["declined_users"] = []
                f["briefing_sent"] = False
                f["flight_log_sent"] = False
                f["staff_start_notified"] = False
                f["notified_20min"] = False
                f["briefing_missing_notified"] = False
                f["flight_log_missing_notified"] = False
                try:
                    await delete_flight_channels(f)
                except Exception:
                    pass
                f["flight_channels_created"] = False
                f["shift_requests"] = {}
                f["is_locked"] = False
                f["flight_channel_attempts"] = 0
                f.pop("flight_channels", None)
                f.pop("flight_channels_sig", None)
                f.pop("briefing_thread_id", None)
                if "briefing_assignments" in f: del f["briefing_assignments"]
                for _k in ("flight_survey_results", "flight_survey_deadline", "flight_survey_dispatched",
                           "flight_survey_dm_sent_ids", "flight_survey_dm_failed_ids",
                           "flight_archive_channel_id", "flight_archive_message_id"):
                    f.pop(_k, None)
                
                s_channel = client.get_channel(f["staff_channel_id"])
                if s_channel:
                    embed_color = get_embed_color(f.get('color'))
                    display_code = f['flight_code'].replace("[TEST] ", "")
                    title = f"{display_code} {f['origin']}→{f['destination']}"
                        
                    staff_embed = discord.Embed(title=signup_embed_title(f, title), description=render_staff_description(f, "staff_description_recurring"), color=embed_color)
                    host_name = await get_server_display_name(f["host_id"], f.get("staff_guild_id") or STAFF_GUILD_ID, fallback="Host")
                    
                    staff_embed.add_field(name="Host", value=host_name, inline=False)
                    staff_embed.add_field(name="Route", value=f"{f['origin']} ➝ {f['destination']}", inline=False)
                    staff_embed.add_field(name="Aircraft Equipment", value=f['equipment'], inline=False)
                    staff_embed.add_field(name="Minimum Staff Needed", value=minimum_staff_text(), inline=False)
                    
                    staff_embed.add_field(name="Action", value=f"React to join.\n**Staff Briefing Time:** <t:{f['staff_timestamp']}:F>" + google_calendar_suffix(f), inline=False)
                    staff_embed.add_field(name="Time", value=f"<t:{f['start_timestamp']}:F> - <t:{f['end_timestamp']}:t> (<t:{f['start_timestamp']}:R>)", inline=False)
                    staff_embed.add_field(name=f"{EMOJI_CHECK_STR} Accepted (1)", value=f">>> {host_name}", inline=True)
                    staff_embed.add_field(name=f"{EMOJI_X_STR} Declined (0)", value="-", inline=True)
                    staff_embed.set_footer(text=signup_footer(f['flight_code'], host_name))
                    
                    image_url, image_bytes = await fetch_fresh_image_info(f.get("source_channel_id"), f.get("source_message_id"))

                    recurring_image_file = embed_image_as_attachment(staff_embed, image_bytes, image_url,
                                                                     prefix=f"staff_{f['flight_code']}")
                    recurring_send_kwargs = {
                        "content": "**[RECURRING FLIGHT]**" if f.get("is_test") else "@everyone",
                        "embed": staff_embed,
                        "view": RecurringFlightSignupView(),
                    }
                    if recurring_image_file is not None:
                        recurring_send_kwargs["file"] = recurring_image_file
                    staff_msg = await s_channel.send(**recurring_send_kwargs)
                    f["staff_message_id"] = staff_msg.id

                c_channel = client.get_channel(f["customer_channel_id"])
                if c_channel and f.get("customer_message_id"):
                    display_code = f['flight_code'].replace("[TEST] ", "")
                    rec = dict(f)
                    rec["flight_code"] = display_code
                    cust_msg_content = render_customer_post(rec, key="customer_post_recurring")
                    try:
                        c_msg = await c_channel.fetch_message(f["customer_message_id"])
                        await c_msg.edit(content=cust_msg_content)
                    except Exception as e:
                        print(f"Customer msg overwrite error: {e}")

                global_db_dirty = True











































def _build_ordered_bar_chart(labels: list, values: list, title: str, ylabel: str, color: str = "#2C5F8A") -> io.BytesIO:
    _apply_chart_style()

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=180)
    fig.patch.set_facecolor("#F7F8FA")
    ax.set_facecolor("#F7F8FA")

    max_val = max(values) if values else 0
    bar_colors = ["#F2A93B" if (v == max_val and max_val > 0) else color for v in values]

    bars = ax.bar(labels, values, color=bar_colors, width=0.62, edgecolor="none", zorder=3)

    ax.set_title(title, fontsize=15, fontweight="bold", color="#1B2733", pad=14, loc="left")
    ax.set_ylabel(ylabel, fontsize=10, color="#5A6472")
    ax.tick_params(axis="x", labelsize=10, colors="#1B2733")
    ax.tick_params(axis="y", labelsize=9, colors="#5A6472")

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#D9DEE4")
    ax.spines["bottom"].set_color("#D9DEE4")

    ax.grid(axis="y", linestyle="-", linewidth=0.7, color="#E3E7EC", zorder=0)
    ax.set_axisbelow(True)

    top_lim = max_val * 1.22 if max_val > 0 else 1
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + top_lim * 0.02,
                 f"{val:g}", ha="center", va="bottom", fontsize=9.5, color="#1B2733", fontweight="normal")

    ax.set_ylim(0, top_lim)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


































        




        












def calculate_tz_offset(local_time_str):
    try:
        lt = datetime.datetime.strptime(local_time_str.strip().replace(":", ":"), "%H:%M")
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        diff_mins = (lt.hour * 60 + lt.minute) - (now_utc.hour * 60 + now_utc.minute)
        if diff_mins < -720: diff_mins += 1440
        elif diff_mins > 720: diff_mins -= 1440
        offset_hrs = round(diff_mins / 60.0)
        return f"UTC{'+' if offset_hrs >= 0 else ''}{offset_hrs}", offset_hrs
    except Exception:
        return "Unknown", 0

def parse_date_time_to_ts(date_str, time_str, offset_hrs):
    try:
        d_match = re.findall(r'\d+', date_str)
        t_match = re.findall(r'\d+', time_str)
        
        if len(d_match) >= 3 and len(t_match) >= 2:
            year, month, day = int(d_match[0]), int(d_match[1]), int(d_match[2])
            if year < 100: year += 2000
            hour, minute = int(t_match[0]), int(t_match[1])
            
            dt_naive = datetime.datetime(year, month, day, hour, minute)
            tz = datetime.timezone(datetime.timedelta(hours=offset_hrs))
            return int(dt_naive.replace(tzinfo=tz).timestamp())
    except Exception:
        pass
    return 0

async def check_flight_duplicate(channel: discord.TextChannel, flight_code: str, origin: str, equipment: str) -> bool:
    now = datetime.datetime.now().timestamp()
    for f in FLIGHT_LOG_CACHE:
        if f["end_timestamp"] > now:
            if f["flight_code"].lower() == flight_code.lower() and \
               f.get("origin", "").lower() == origin.lower() and \
               f.get("equipment", "").lower() == equipment.lower():
                return True


    if channel:
        try:
            async for msg in channel.history(limit=50):
                if msg.author.bot and msg.embeds:
                    embed = msg.embeds[0]
                    if embed.title and "Approved" in embed.title:
                        desc = embed.description or ""
                        fc_match = re.search(r'\*\*Flight Code:\*\*\s*(.+)', desc)
                        or_match = re.search(r'\*\*Origin:\*\*\s*(.+)', desc)
                        eq_match = re.search(r'\*\*Equipment:\*\*\s*(.+)', desc)
                        if fc_match and or_match and eq_match:
                            if fc_match.group(1).strip().lower() == flight_code.lower() and \
                               or_match.group(1).strip().lower() == origin.lower() and \
                               eq_match.group(1).strip().lower() == equipment.lower():
                                return True
        except Exception:
            pass
    return False

async def get_used_origins(bot_client, ignore_flight_code: str = None) -> set:
    used_origins = set()
    now = datetime.datetime.now().timestamp()
    ignore_fc = ignore_flight_code.lower() if ignore_flight_code else None


    for f in FLIGHT_LOG_CACHE:
        if f.get("end_timestamp", 0) > now and not f.get("messages_deleted", False):
            if ignore_fc and f.get("flight_code", "").lower() == ignore_fc:
                continue
            if f.get("origin"):
                used_origins.add(f["origin"].lower())
                

    app_channel = bot_client.get_channel(FLIGHT_APP_CHANNEL_ID)
    if app_channel:
        try:
            async for msg in app_channel.history(limit=50):
                if msg.author.bot and msg.embeds:
                    embed = msg.embeds[0]
                    if embed.title and ("Pending" in embed.title or "Approved" in embed.title):
                        desc = embed.description or ""
                        

                        fc_match = re.search(r'\*\*Flight Code:\*\*\s*(.+)', desc)
                        if ignore_fc and fc_match and fc_match.group(1).strip().lower() == ignore_fc:
                            continue
                            
                        or_match = re.search(r'\*\*Origin:\*\*\s*(.+)', desc)
                        if or_match:
                            used_origins.add(or_match.group(1).strip().lower())
        except Exception:
            pass
            
    return used_origins

async def get_least_used_flight_suggestion(bot_client):
    used_origins = await get_used_origins(bot_client)
    

    usage_counts = {}
    for f in FLIGHT_LOG_CACHE:
        if f.get("is_custom", False) or f.get("messages_deleted", False):
            continue
        fc = f.get("flight_code", "")
        eq = f.get("equipment", "")
        usage_counts[fc] = usage_counts.get(fc, 0) + 1
        usage_counts[eq] = usage_counts.get(eq, 0) + 1
        

    valid_templates = [
        k for k, v in FLIGHT_DB.items() 
        if v.get("origin", "").lower() not in used_origins
    ]
    
    if not valid_templates:
        return None
        

    fc_weights = [1.0 / (usage_counts.get(k, 0) + 1) for k in valid_templates]
    flight_code = random.choices(valid_templates, weights=fc_weights, k=1)[0]
    
    route_data = FLIGHT_DB[flight_code]
    variants = list(route_data.get("variants", {}).keys())
    
    if not variants:
        return None
        

    eq_weights = [1.0 / (usage_counts.get(eq, 0) + 1) for eq in variants]
    equipment = random.choices(variants, weights=eq_weights, k=1)[0]
    
    variant_data = route_data["variants"][equipment]
    
    return {
        "flight_code": flight_code,
        "origin": route_data.get("origin", "Unknown"),
        "dest": route_data.get("destination", "Unknown"),
        "equipment": equipment,
        "airline": variant_data.get("airline") or default_airline(),
        "classes": variant_data.get("classes", "Economy"),
        "color_hex": variant_data.get("color", "1B3444"),
        "src_ch": variant_data.get("source_channel_id"),
        "src_msg": variant_data.get("source_message_id")
    }

async def check_flight_is_approved(channel: discord.TextChannel, flight_code: str, origin: str) -> bool:
    if not channel:
        return True
    try:
        async for msg in channel.history(limit=100):
            if msg.author.bot and msg.embeds:
                embed = msg.embeds[0]
                if embed.title and "Approved" in embed.title:
                    desc = embed.description or ""
                    fc_match = re.search(r'\*\*Flight Code:\*\*\s*(.+)', desc)
                    or_match = re.search(r'\*\*Origin:\*\*\s*(.+)', desc)
                    if fc_match and or_match:
                        if fc_match.group(1).strip().lower() == flight_code.lower() and \
                           or_match.group(1).strip().lower() == origin.lower():
                            return True
    except Exception:
        pass
    return False

def generate_flight_app_embed(data: dict, ts: int = 0) -> discord.Embed:

    time_display = f"<t:{ts}:F>\n*(Local: {data['date']} {data['time']} {data['tz']})*" if ts > 0 else f"{data['date']} {data['time']} ({data['tz']})"
    
    desc = (
        f"**Host:** <@{data['user_id']}>\n"
        f"**Departure Time:** {time_display}\n"
        f"**Origin:** {data['origin']}\n"
        f"**Destination:** {data['dest']}\n"
        f"**Airline:** {data['airline']}\n"
        f"**Flight Code:** {data['flight_code']}\n"
        f"**Equipment:** {data['equipment']}\n"
        f"**Details:** {data['detail']}\n"
    )
    embed = discord.Embed(title="Flight Application (Pending)", description=desc, color=0x1B3444)
    if data['avatar_url']:
        embed.set_footer(text=f"Applicant: {data['user_name']}", icon_url=data['avatar_url'])
    else:
        embed.set_footer(text=f"Applicant: {data['user_name']}")
    return embed

def extract_app_data(embed: discord.Embed) -> dict:
    desc = embed.description or ""
    

    local_m = re.search(r'\*\(Local:\s*([^ ]+)\s+([^ ]+)\s+([^)]+)\)\*', desc)
    

    d_m = re.search(r'\*\*Departure Date:\*\*\s*(.+)', desc)
    t_m = re.search(r'\*\*Departure Time:\*\*\s*(.+?)\s*\(', desc)
    
    if local_m:
        date_str = local_m.group(1).strip()
        time_str = local_m.group(2).strip()
        tz_str = local_m.group(3).strip()
    else:
        date_str = d_m.group(1).strip() if d_m else ""
        time_str = t_m.group(1).strip() if t_m else ""
        tz_m = re.search(r'\((UTC[+-]\d+)\)', desc)
        tz_str = tz_m.group(1).strip() if tz_m else "Unknown"

    or_m = re.search(r'\*\*Origin:\*\*\s*(.+)', desc)
    de_m = re.search(r'\*\*Destination:\*\*\s*(.+)', desc)
    al_m = re.search(r'\*\*Airline:\*\*\s*(.+)', desc)
    fc_m = re.search(r'\*\*Flight Code:\*\*\s*(.+)', desc)
    eq_m = re.search(r'\*\*Equipment:\*\*\s*(.+)', desc)
    dt_m = re.search(r'\*\*Details:\*\*\s*(.+)', desc)
    ho_m = re.search(r'\*\*Host:\*\*\s*<@!?(\d+)>', desc)


    offset_hrs = parse_timezone_offset(tz_str) if tz_str else 9

    return {
        "date": date_str,
        "time": time_str,
        "origin": or_m.group(1).strip() if or_m else "",
        "dest": de_m.group(1).strip() if de_m else "",
        "airline": al_m.group(1).strip() if al_m else default_airline(),
        "flight_code": fc_m.group(1).strip() if fc_m else "",
        "equipment": eq_m.group(1).strip() if eq_m else "",
        "detail": dt_m.group(1).strip() if dt_m else "",
        "host_id": int(ho_m.group(1)) if ho_m else 0,
        "tz": tz_str,
        "offset_hrs": offset_hrs
    }




@tasks.loop(hours=1)
@_resilient_task
async def check_expired_applications():
    if _AUTO_TEST_PAUSE:
        return
    """Periodically checks FLIGHT_APP_CHANNEL_ID and finds pending applications left for more than APP_EXPIRY_HOURS,
    then automatically reminds (nudge DM) or auto-rejects them."""
    channel = client.get_channel(FLIGHT_APP_CHANNEL_ID)
    if not channel:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        async for msg in channel.history(limit=200):
            if not (msg.author == client.user and msg.embeds):
                continue
            embed = msg.embeds[0]
            if not embed.title or "Pending" not in embed.title:
                continue

            age_hours = (now - msg.created_at).total_seconds() / 3600
            if age_hours < APP_EXPIRY_HOURS:
                continue

            data = extract_app_data(embed)
            applicant = client.get_user(data["host_id"]) if data["host_id"] else None

            if APP_EXPIRY_ACTION == "deny":
                embed.color = discord.Color.red()
                embed.title = "Flight Application (Auto-Expired)"
                if not any("Status" in f.name for f in embed.fields):
                    embed.add_field(name="Status", value="Automatically denied due to no response.", inline=False)
                try:
                    view = discord.ui.View.from_message(msg)
                    if view:
                        for child in view.children:
                            child.disabled = True
                        await msg.edit(embed=embed, view=view)
                    else:
                        await msg.edit(embed=embed)
                except Exception as e:
                    print(f"Auto-expire edit error: {e}")

                if applicant:
                    try:
                        await applicant.send(f"Your application ({data.get('flight_code','Unknown')}) was automatically rejected because there was no response for {APP_EXPIRY_HOURS} hours.")
                    except Exception:
                        pass

                await log_audit(
                    actor=client.user,
                    action="Flight Application Auto-Expired (Denied)",
                    detail=f"Flight Code: {data.get('flight_code','Unknown')}\n{APP_EXPIRY_HOURS} hours with no response, so it was automatically rejected.",
                    target=applicant,
                    color=discord.Color.red().value
                )
            else:
                if not any("Reminded" in f.name for f in embed.fields):
                    embed.add_field(name="Reminded", value=f"<t:{int(now.timestamp())}:R>", inline=False)
                    try:
                        await msg.edit(embed=embed)
                    except Exception as e:
                        print(f"Auto-remind edit error: {e}")

                    try:
                        await channel.send(
                            content=f"<@&{FLIGHT_VERIFIER_ROLE_ID}> This application has had no response for over {APP_EXPIRY_HOURS} hours. Please check it.",
                            reference=msg
                        )
                    except Exception:
                        pass

                    await log_audit(
                        actor=client.user,
                        action="Flight Application Reminder Sent",
                        detail=f"Flight Code: {data.get('flight_code','Unknown')}\n{APP_EXPIRY_HOURS} hours with no response, so the administrators were notified.",
                        target=applicant
                    )
    except Exception:
        traceback.print_exc()


class DenyReasonModal(discord.ui.Modal, title="Reason for Denial"):
    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the reason...",
        required=True
    )
    def __init__(self, parent_view, original_embed):
        super().__init__()
        self.parent_view = parent_view
        self.original_embed = original_embed

    async def on_submit(self, interaction: discord.Interaction):
        embed = self.original_embed
        embed.color = discord.Color.red()
        embed.title = "Flight Application (Denied)"
        if not any("Status" in f.name for f in embed.fields):
            embed.add_field(name="Status", value=f"Denied by: {interaction.user.mention}\n**Reason:** {self.reason.value}", inline=False)
        for child in self.parent_view.children: child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self.parent_view)
        await self.parent_view.notify_applicant(interaction, embed, "Denied")

        app_data = extract_app_data(embed)
        await log_audit(
            actor=interaction.user,
            action="Flight Application Denied",
            detail=f"Flight Code: {app_data.get('flight_code','Unknown')}\nReason: {self.reason.value}",
            target=client.get_user(app_data["host_id"]) if app_data.get("host_id") else None,
            color=discord.Color.red().value
        )

class FlightAppEditModal(discord.ui.Modal):
    def __init__(self, data, original_message):
        super().__init__(title="Edit Flight App")
        self.original_message = original_message
        self.tz_str = data.get("tz", "Unknown")
        self.offset_hrs = data.get("offset_hrs", 9)
        self.departure_date = data.get("date", "")
        self.departure_time = data.get("time", "")
        
        self.flight_code_input = discord.ui.TextInput(label="Flight Code", default=data.get("flight_code", ""), required=True, max_length=50)
        self.origin_input = discord.ui.TextInput(label="Origin", default=data.get("origin", ""), required=True, max_length=50)
        self.dest_input = discord.ui.TextInput(label="Destination", default=data.get("dest", ""), required=True, max_length=50)
        self.equipment_input = discord.ui.TextInput(label="Airline / Equipment", default=f"{data.get('airline') or default_airline()} / {data.get('equipment', '')}", required=True, max_length=100)
        self.detail_input = discord.ui.TextInput(label="Details", style=discord.TextStyle.paragraph, default=data.get("detail", ""), required=True, max_length=500)
        
        self.add_item(self.flight_code_input)
        self.add_item(self.origin_input)
        self.add_item(self.dest_input)
        self.add_item(self.equipment_input)
        self.add_item(self.detail_input)

    async def on_submit(self, interaction: discord.Interaction):
        try: await self.original_message.delete()
        except: pass
        await process_flight_application(
            interaction, self.departure_date, self.departure_time, self.tz_str, self.offset_hrs,
            self.flight_code_input.value.strip(), self.origin_input.value.strip(),
            self.dest_input.value.strip(), self.equipment_input.value, self.detail_input.value.strip()
        )

class FlightAppView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def notify_applicant(self, interaction: discord.Interaction, embed: discord.Embed, status_text: str):
        data = extract_app_data(embed)
        user = client.get_user(data["host_id"])
        if user:
            try: await user.send(content=f"Application status updated: **{status_text}**", embed=embed.copy())
            except Exception: pass

    @discord.ui.button(label="", style=discord.ButtonStyle.secondary, emoji=FLIGHT_APPROVED_EMOJI, custom_id="flight_app_approve")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if FLIGHT_VERIFIER_ROLE_ID not in [r.id for r in interaction.user.roles] and not is_chief(interaction.user):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'No permission.')]))



        embed_check = interaction.message.embeds[0]
        app_data = extract_app_data(embed_check)
        recheck_ts = parse_date_time_to_ts(app_data.get("date", ""), app_data.get("time", ""), app_data.get("offset_hrs", 9))
        recheck_fc = app_data.get("flight_code", "")

        recheck_reasons = []
        if recheck_ts > 0:
            ok, reason = check_date_based_spacing(recheck_ts, current_flight_code=recheck_fc)
            if not ok:
                recheck_reasons.append(reason)

        used_origins_recheck = await get_used_origins(client, ignore_flight_code=recheck_fc)
        if app_data.get("origin", "").lower() in used_origins_recheck:
            recheck_reasons.append(f"The origin '{app_data.get('origin')}' is already in use by another active flight or application.")

        dup_host_fc_recheck = await check_host_duplicate(client, app_data.get("host_id", 0), ignore_flight_code=recheck_fc)
        if dup_host_fc_recheck:
            recheck_reasons.append(f"This host already has another active or pending flight (`{dup_host_fc_recheck}`).")

        if recheck_reasons:
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'This application cannot be approved. While it was pending, other applications/flights were confirmed, which conflicts with the following rules.\nPlease review it with "Edit & Re-apply", or deny it.\n\n' + '\n'.join(recheck_reasons))]))

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "Flight Application (Approved)"
        if not any("Status" in f.name for f in embed.fields):
            embed.add_field(name="Status", value=f"Approved by: {interaction.user.mention}", inline=False)
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        await self.notify_applicant(interaction, embed, "Approved")

        app_data = extract_app_data(embed)
        await log_audit(
            actor=interaction.user,
            action="Flight Application Approved",
            detail=f"Flight Code: {app_data.get('flight_code','Unknown')}",
            target=client.get_user(app_data["host_id"]) if app_data.get("host_id") else None,
            color=discord.Color.green().value
        )

    @discord.ui.button(label="", style=discord.ButtonStyle.secondary, emoji=EMOJI_X_STR, custom_id="flight_app_deny")
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if FLIGHT_VERIFIER_ROLE_ID not in [r.id for r in interaction.user.roles] and not is_chief(interaction.user):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'No permission.')]))

        await interaction.response.send_modal(DenyReasonModal(self, interaction.message.embeds[0]))

    @discord.ui.button(label="", style=discord.ButtonStyle.secondary, emoji=EMOJI_X_STR, custom_id="flight_app_reapply")
    async def reapply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        data = extract_app_data(embed)
        is_admin = FLIGHT_VERIFIER_ROLE_ID in [r.id for r in interaction.user.roles] or is_chief(interaction.user)
        is_owner = interaction.user.id == data["host_id"]
        if not (is_admin or is_owner):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'You do not have permission to edit.')]))
        await log_audit(
            actor=interaction.user,
            action="Flight Application Re-apply Opened",
            detail=f"Flight Code: {data.get('flight_code','Unknown')}",
            target=client.get_user(data["host_id"]) if data.get("host_id") else None
        )
        await interaction.response.send_modal(FlightAppEditModal(data, interaction.message))

class FlightAppAutoCancelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


    @discord.ui.button(label="", style=discord.ButtonStyle.secondary, emoji=FLIGHT_APPROVED_EMOJI, custom_id="flight_app_autocancel_approve", disabled=True)
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass


    @discord.ui.button(label="", style=discord.ButtonStyle.secondary, emoji=EMOJI_X_STR, custom_id="flight_app_autocancel_deny", disabled=True)
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass


    @discord.ui.button(label="", style=discord.ButtonStyle.secondary, emoji=EMOJI_X_STR, custom_id="flight_app_autocancel_reapply")
    async def reapply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        data = extract_app_data(embed)
        is_admin = FLIGHT_VERIFIER_ROLE_ID in [r.id for r in interaction.user.roles] or is_chief(interaction.user)
        is_owner = interaction.user.id == data["host_id"]
        if not (is_admin or is_owner):
            return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'You do not have permission to edit.')]))
        await interaction.response.send_modal(FlightAppEditModal(data, interaction.message))

async def send_flight_app_guidance(channel):
    if not channel:
        return
    try:

        async for msg in channel.history(limit=20):
            if msg.author.id == client.user.id and msg.embeds and "About Flight Application" in str(msg.embeds[0].title):
                await msg.delete()
    except Exception as e:
        print(f"Guidance delete error: {e}")
        
    embed = discord.Embed(
        title="About Flight Application",
        description=(
            "Please follow the rules when applying for a flight.\n"
            "Use `/flight_app` to create a flight.\n"
            "Please provide as much detail as possible. If you are unsure, feel free to ask.\n\n"
            "Please follow the rules when submitting a flight application.\n"
            "Use `/flight_app` to create a flight.\n"
            "Please provide as much detail as possible. If you have any questions, feel free to ask."
        ),
        color=0x3498db
    )
    try:

        await channel.send(embed=embed)
    except Exception as e:
        print(f"Guidance send error: {e}")

async def process_flight_application(interaction: discord.Interaction, departure_date: str, departure_time: str, tz_str: str, offset_hrs: int, flight_code: str, origin: str, dest: str, raw_equipment: str, detail: str):


    if not interaction.response.is_done():
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.HTTPException as e:
            print(f"flight_app defer failed: {e}")
    eq_parts = raw_equipment.split("/", 1)
    if len(eq_parts) == 2:
        airline, equipment = eq_parts[0].strip(), eq_parts[1].strip()
    else:
        airline, equipment = default_airline(), raw_equipment.strip()

    ts = parse_date_time_to_ts(departure_date, departure_time, offset_hrs)

    target_channel = client.get_channel(FLIGHT_APP_CHANNEL_ID) or interaction.channel
    is_auto_cancelled, cancel_reasons = False, []
    now_ts = datetime.datetime.now().timestamp()

    if ts > 0 and ts < now_ts + 48 * 3600:
        is_auto_cancelled = True
        cancel_reasons.append("- Flights must be scheduled at least 2 days (48 hours) in advance.\n")

    if await check_flight_duplicate(target_channel, flight_code, origin, equipment):
        is_auto_cancelled = True
        cancel_reasons.append("- A flight with the exact same Flight Code, Origin, and Equipment already exists.\n")


    used_origins = await get_used_origins(client, ignore_flight_code=flight_code)
    if origin.lower() in used_origins:
        is_auto_cancelled = True
        cancel_reasons.append(f"- The origin airport '{origin}' is already in use by another active or pending flight.\n")


    if ts > 0:
        ok, reason = check_date_based_spacing(ts, current_flight_code=flight_code)
        if not ok:
            is_auto_cancelled = True
            cancel_reasons.append(f"- {reason}\n")

        if not is_auto_cancelled:
            ok, reason = await check_date_based_spacing_vs_log(ts)
            if not ok:
                is_auto_cancelled = True
                cancel_reasons.append(f"- {reason}\n")


    dup_host_fc = await check_host_duplicate(client, interaction.user.id, ignore_flight_code=flight_code)
    if dup_host_fc:
        is_auto_cancelled = True
        cancel_reasons.append(f"- You are already the host of another active or pending flight (`{dup_host_fc}`). You cannot host multiple flights at the same time.\n")


    now_ts_limit = datetime.datetime.now().timestamp()
    active_flights_count = sum(
        1 for f in FLIGHT_LOG_CACHE
        if f.get("end_timestamp", 0) > now_ts_limit and not f.get("messages_deleted") and not f.get("queued_for_limit") and not f.get("is_test")
    )
    if active_flights_count >= 5:
        is_auto_cancelled = True
        cancel_reasons.append("- The active flight limit (5 slots) has been reached. Please apply again once a slot opens up.\n")



    data = {"user_id": interaction.user.id, "user_name": interaction.user.display_name, "avatar_url": interaction.user.display_avatar.url if interaction.user.display_avatar else None, "date": departure_date, "time": departure_time, "tz": tz_str, "origin": origin, "dest": dest, "airline": airline, "flight_code": flight_code, "equipment": equipment, "detail": detail}
    embed = generate_flight_app_embed(data, ts)

    if is_auto_cancelled:
        embed.title = "Flight Application (Auto-Cancelled)"
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value="Auto-Cancelled", inline=False)
        
        await target_channel.send(embed=embed, view=FlightAppAutoCancelView())
        
        dm_embed = embed.copy()
        dm_embed.set_field_at(0, name="Status", value="**Auto-Cancelled**\n\n**Reason:**\n" + "\n".join(cancel_reasons), inline=False)
        try: await interaction.user.send(view=embed_to_v2_layout(dm_embed, content='Application auto-cancelled.'))
        except Exception: pass
        

        if interaction.response.is_done():
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'Application auto-cancelled. Check your DM for details.\n')]))
        else:
            await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Application auto-cancelled. Check your DM for details.\n')]))
    else:
        await target_channel.send(content=f"<@&{FLIGHT_VERIFIER_ROLE_ID}>", embed=embed, view=FlightAppView())
        

        if interaction.response.is_done():
            await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'Application submitted successfully.')]))
        else:
            await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Application submitted successfully.')]))


    await send_flight_app_guidance(target_channel)




















EVALUATION_CACHE = []

async def load_eval_tracking():
    global EVALUATION_CACHE
    found, data = await read_latest_json_backup(EVAL_TRACK_CHANNEL_ID, filename="eval_data.json", limit=100)
    if found and isinstance(data, list):
        EVALUATION_CACHE = data
        _ensure_eval_ids()
        print(f"Eval Cache Loaded: {len(EVALUATION_CACHE)} pending evaluations.")
    elif found:
        raise LoadError("eval_data backup has an unexpected format")
    else:
        EVALUATION_CACHE = []

async def save_eval_tracking():
    return await save_json_to_channel(EVAL_TRACK_CHANNEL_ID, EVALUATION_CACHE, "eval_data.json")

def _ensure_eval_ids():
    changed = False
    for ev in EVALUATION_CACHE:
        if not isinstance(ev, dict):
            continue
        if not ev.get("id"):
            ev["id"] = uuid.uuid4().hex[:8]
            changed = True
        if not ev.get("batch_id"):
            ev["batch_id"] = f"legacy-{ev.get('send_timestamp', 0)}-{ev.get('reviewer_name', '')}"
            changed = True
        if "attempts" not in ev:
            ev["attempts"] = 0
            changed = True
    return changed



async def _deliver_scheduled_eval(ev: dict):
    try:
        target_user = client.get_user(ev["target_id"]) or await client.fetch_user(ev["target_id"])
    except discord.NotFound:
        return False, True
    except Exception as e:
        print(f"Eval user lookup error for {ev.get('target_id')}: {e}")
        return False, ev.get("attempts", 0) >= 2
    try:
        view = EvaluationDMView()
        await target_user.send(embed=view.generate_embed(ev, "en"), view=view)
        return True, False
    except discord.Forbidden:
        return False, True
    except Exception as e:
        print(f"Eval Send Error for {ev.get('target_id')}: {e}")
        return False, ev.get("attempts", 0) >= 2

async def _notify_eval_failure(ev: dict):
    cid = ev.get("creator_id")
    if not cid:
        return
    try:
        creator = client.get_user(cid) or await client.fetch_user(cid)
        await creator.send(f"The scheduled evaluation sheet (recipient <@{ev.get('target_id')}> / scheduled at <t:{int(ev.get('send_timestamp', 0))}:F>) could not be sent."
                           f"Check the recipient's DM settings (allow DMs from server members), and if needed, send it again from `/send_evaluation`.")
    except Exception as e:
        print(f"Eval failure notice error: {e}")

@tasks.loop(seconds=30)
@_resilient_task
async def process_evaluations_task():
    if _AUTO_TEST_PAUSE:
        return
    if not data_ready(EVAL_TRACK_CHANNEL_ID):
        return
    now = datetime.datetime.now().timestamp()
    dirty = _ensure_eval_ids()

    for eval_data in EVALUATION_CACHE[:]:
        send_ts = eval_data.get("send_timestamp")
        if not send_ts or "target_id" not in eval_data:
            continue
        if now < send_ts:
            continue
        if eval_data not in EVALUATION_CACHE:
            continue
        ok, permanent = await _deliver_scheduled_eval(eval_data)
        if ok or permanent:
            if eval_data in EVALUATION_CACHE:
                EVALUATION_CACHE.remove(eval_data)
            dirty = True
            if not ok:
                await _notify_eval_failure(eval_data)
        else:
            eval_data["attempts"] = eval_data.get("attempts", 0) + 1
            dirty = True
        await asyncio.sleep(0.5)

    if dirty:
        await save_eval_tracking()

class EvaluationDMView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


    def generate_embed(self, eval_data, lang="en"):
        target_mention = f"<@{eval_data['target_id']}>"
        reviewer = eval_data['reviewer_name']
        grade = eval_data['grade']
        comments = eval_data['comments']
        doc_link = eval_data.get('doc_link', '')

        if lang == "ja":
            embed = discord.Embed(
                title="Periodic Evaluation Report",
                description=f"{target_mention}\n\nHere is your periodic evaluation report.\nThank you for your continued efforts in your daily work.",
                color=0x1B3444
            )
            embed.add_field(name="Reviewer", value=reviewer, inline=False)
            embed.add_field(name="Overall rating", value=f"**{grade}**", inline=False)
            embed.add_field(name="Feedback", value=comments, inline=False)
            if doc_link:
                embed.add_field(name="Evaluation sheet", value=f"[Open the document]({doc_link})", inline=False)
            embed.add_field(name="Action required", value="Click the button below to submit your reflection.", inline=False)
        else:
            embed = discord.Embed(
                title="Employee Evaluation Report",
                description=f"Dear {target_mention},\n\nPlease find your regular evaluation report below.\nThank you for your continued dedication and hard work.",
                color=0x1B3444
            )
            embed.add_field(name="Reviewer", value=reviewer, inline=False)
            embed.add_field(name="Grade", value=f"**{grade}**", inline=False)
            embed.add_field(name="Feedback", value=comments, inline=False)
            if doc_link:
                embed.add_field(name="Evaluation Sheet", value=f"[Open Document]({doc_link})", inline=False)
            embed.add_field(name="Action Required", value="Please click the button below to submit your reflection.", inline=False)
        
        embed.set_footer(text="Flight Hub")
        return embed

    @discord.ui.button(label="Submit Reflection", style=discord.ButtonStyle.primary, custom_id="eval_dm_btn_reflect")
    async def btn_reflection(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReflectionModal(user_locale=interaction.locale))
























def build_checklist_embed(flight, flight_code) -> discord.Embed:
    lines = []
    ok = lambda cond: EMOJI_CHECK_STR if cond else EMOJI_X_STR


    has_equipment = bool(flight.get("equipment")) and flight.get("equipment") != "???"
    lines.append(f"{ok(has_equipment)} Equipment registered: {flight.get('equipment') or 'N/A'}")


    has_host = bool(flight.get("host_id"))
    lines.append(f"{ok(has_host)} Host assigned: {'<@' + str(flight['host_id']) + '>' if has_host else 'Unassigned'}")


    briefing_sent = bool(flight.get("briefing_sent"))
    lines.append(f"{ok(briefing_sent)} Briefing sheet sent")


    unassigned = []
    if briefing_sent and "briefing_assignments" in flight:
        for pos, val in flight["briefing_assignments"].items():
            if val == "UNASSIGNED" and not cabin_class_unavailable(flight, pos):
                unassigned.append(pos)
    all_assigned = briefing_sent and not unassigned
    lines.append(f"{ok(all_assigned) if briefing_sent else '-'} All positions filled: " + (", ".join(unassigned) if unassigned else ("N/A" if not briefing_sent else "OK")))


    lines.append(f"{'-' if not flight.get('flight_log_sent') else EMOJI_CHECK_STR} Flight log: " + ("Sent" if flight.get("flight_log_sent") else "Not sent yet (send it after the flight)"))

    if flight.get("is_gamenight") and not briefing_sent:

        all_good = has_equipment and has_host
    else:
        all_good = has_equipment and has_host and briefing_sent and all_assigned
    embed = discord.Embed(
        title=f"Checklist | {flight_code}",
        description="\n".join(lines),
        color=discord.Color.green() if all_good else discord.Color.orange()
    )
    if not all_good:
        embed.set_footer(text="Some items are incomplete.")
    return embed


@client.tree.command(name="about", description="About this open source bot")
@app_commands.guild_only()
async def about_cmd(interaction: discord.Interaction):
    emb = discord.Embed(
        title=f"Flight Hub {DISPLAY_VERSION}",
        description="Flight Hub is a fully open source flight operations hub for Discord. "
        "It provides flight events, briefings, flight logs, staff management, "
        "surveys, analytics, and more. Released as open source for everyone.",
        color=EMBED_COLOR,
    )
    emb.set_footer(text=f"Open source release · {DISPLAY_VERSION}")
    await interaction.response.send_message(embed=emb, ephemeral=True)

@client.tree.command(name="checklist", description="Check that a flight is ready to go (equipment, positions, briefing).")
@app_commands.describe(flight_code="Target flight code")
@app_commands.autocomplete(flight_code=active_flight_autocomplete)
@event_manager_only
async def checklist_cmd(interaction: discord.Interaction, flight_code: str):
    if not is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'No permission.')]))

    flight = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, f'Flight `{flight_code}` not found.')]))

    embed = build_checklist_embed(flight, flight_code)
    await interaction.response.send_message(view=embed_to_v2_layout(embed, content=None))



@client.tree.command(name="route_stats", description="Show historical stats for a route (e.g. how many times it's flown, avg participants).")
@app_commands.describe(keyword="Origin, destination, or flight code prefix to search for")
@event_manager_only
async def route_stats_cmd(interaction: discord.Interaction, keyword: str):
    if not is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'No permission.')]))

    await interaction.response.defer()
    kw = keyword.lower()

    matches = [
        f for f in FLIGHT_LOG_CACHE
        if kw in f.get("origin", "").lower()
        or kw in f.get("destination", "").lower()
        or kw in f.get("flight_code", "").lower()
    ]

    if not matches:
        return await interaction.followup.send(view=build_v2_card('Notice', [(None, f'`{keyword}` matched no flights.')]))

    total = len(matches)
    total_participants = sum(len(f.get("accepted_users", [])) for f in matches)
    avg_participants = round(total_participants / total, 1) if total else 0
    equip_counter = {}
    for f in matches:
        eq = f.get("equipment", "Unknown")
        equip_counter[eq] = equip_counter.get(eq, 0) + 1
    top_equip = sorted(equip_counter.items(), key=lambda x: -x[1])[:5]

    embed = discord.Embed(
        title=f"Route Stats | \"{keyword}\"",
        description=f"Matching flights: **{total}**\nAverage participants: **{avg_participants}**",
        color=EMBED_COLOR
    )
    if top_equip:
        embed.add_field(name="Most used aircraft", value="\n".join(f"{eq}: {c} flights" for eq, c in top_equip), inline=False)

    recent = sorted(matches, key=lambda x: x.get("start_timestamp", 0), reverse=True)[:5]
    if recent:
        embed.add_field(
            name="Recent flights",
            value="\n".join(f"`{f['flight_code']}` <t:{int(f['start_timestamp'])}:d>" for f in recent),
            inline=False
        )
    await interaction.followup.send(view=embed_to_v2_layout(embed, content=None))



@client.tree.command(name="find_staff", description="Find upcoming flights where a specific position is still unassigned.")
@app_commands.describe(position="Position name to search for (e.g. Captain, Ground Crew, First Officer)")
async def find_staff_cmd(interaction: discord.Interaction, position: str):
    if LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'No permission.')]))

    now = datetime.datetime.now().timestamp()
    pos_kw = position.lower()

    hits = []
    for f in FLIGHT_LOG_CACHE:
        if f.get("end_timestamp", 0) <= now or not f.get("briefing_sent"):
            continue
        assignments = f.get("briefing_assignments", {})
        for pos, val in assignments.items():
            if pos_kw in pos.lower() and val == "UNASSIGNED" and not cabin_class_unavailable(f, pos):
                hits.append((f, pos))
                break

    if not hits:
        return await interaction.response.send_message(view=build_v2_card('Notice', [(None, f'No flights with `{position}` unassigned.')]))

    desc = "\n".join(
        f"`{f['flight_code']}` — {pos} (<t:{int(f['start_timestamp'])}:R>)"
        for f, pos in hits
    )
    embed = discord.Embed(
        title=f"Open positions: \"{position}\" ({len(hits)})",
        description=desc[:4000],
        color=discord.Color.orange()
    )
    await interaction.response.send_message(view=embed_to_v2_layout(embed, content=None))





@client.tree.command(name="undo", description="[Admin] Undo the most recent /host_change.")
async def undo_cmd(interaction: discord.Interaction):
    if not is_chief(interaction.user) and ADMIN_ROLE_ID not in [r.id for r in interaction.user.roles]:
        return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'No permission.')]))

    if not UNDO_STACK:
        return await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'There is no undoable action history.')]))

    await interaction.response.defer(ephemeral=True)
    entry = UNDO_STACK.pop()

    if entry["type"] == "host_change":
        global global_db_dirty
        async with global_json_lock:
            target = next((f for f in FLIGHT_LOG_CACHE if f["flight_code"] == entry["flight_code"]), None)
            if not target:
                return await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'The target flight was not found.')]))
            target["host_id"] = entry["old_host_id"]
            global_db_dirty = True
            if target.get("flight_channels"):
                try:
                    await sync_flight_channel_perms(target)
                except Exception as e:
                    print(f"Flight channel perm sync on undo error: {e}")


        try:
            if s_ch := client.get_channel(target.get("staff_channel_id")):
                msg = await s_ch.fetch_message(target["staff_message_id"])
                embed = msg.embeds[0]
                host_display = await get_server_display_name(entry["old_host_id"], target.get("staff_guild_id") or STAFF_GUILD_ID,
                                                             fallback=f"<@{entry['old_host_id']}>")
                for i, f in enumerate(embed.fields):
                    if f.name == "Host":
                        embed.set_field_at(i, name="Host", value=host_display, inline=False)
                        break
                _ft_u = (embed.footer.text if embed.footer else "") or ""
                if "| Created by " in _ft_u:
                    embed.set_footer(text=re.sub(r"(\| Created by ).*$", lambda m_: m_.group(1) + host_display, _ft_u))
                await msg.edit(embed=embed)
        except Exception:
            pass

        await log_audit(actor=interaction.user, action="Undo: Host Change", detail=f"Flight: {entry['flight_code']} | Reverted to <@{entry['old_host_id']}>")
        await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, f"`{entry['flight_code']}`: reversed the host change, returning to <@{entry['old_host_id']}>.")]))
    else:
        await interaction.followup.send(ephemeral=True, view=build_v2_card('Notice', [(None, 'This type of action is not currently supported by undo.')]))





















































































































































class StaffProfileLayoutView(discord.ui.LayoutView):


    LOG_COPY_ROLE_ID = cfg("roles.profile_export")

    def __init__(self, user_to_check, discord_avatar_url: str,
                 role_mentions: str, stats_str: str, user_logs: list,
                 monthly_image_filename: str = None, weekday_image_filename: str = None,
                 invoking_user=None, interaction_guild=None,
                 items_per_page: int = 10, page: int = 0, show_graphs: bool = False):
        super().__init__(timeout=300)
        self.user_to_check = user_to_check
        self.discord_avatar_url = discord_avatar_url
        self.role_mentions = role_mentions
        self.stats_str = stats_str
        self.user_logs = user_logs
        self.monthly_image_filename = monthly_image_filename
        self.weekday_image_filename = weekday_image_filename
        self.invoking_user = invoking_user
        self.interaction_guild = interaction_guild
        self.items_per_page = items_per_page
        self.page = page
        self.max_page = max(0, (len(user_logs) - 1) // items_per_page)
        self.show_graphs = show_graphs
        self.message = None
        self._build()

    async def on_timeout(self):
        disable_view_items(self)
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:

        if self.invoking_user and interaction.user.id != self.invoking_user.id:
            await interaction.response.send_message(ephemeral=True, view=build_v2_card('Notice', [(None, 'Only the person who ran this command can use these controls.')]))
            return False
        return True

    def _build(self):
        self.clear_items()
        user = self.user_to_check

        header_text = discord.ui.TextDisplay(f"**{user.display_name}** (`{user.id}`)")

        profile_section = discord.ui.Section(
            discord.ui.TextDisplay(f"### Profile\n{self.role_mentions or 'No roles'}"),
            accessory=discord.ui.Thumbnail(self.discord_avatar_url or "https://cdn.discordapp.com/embed/avatars/0.png"),
        )

        container_children = [header_text, profile_section]

        container_children.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large))


        container_children.append(discord.ui.TextDisplay(f"**Flight Participation**\n{self.stats_str}"))
        container_children.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))


        start = self.page * self.items_per_page
        end = start + self.items_per_page
        page_logs = self.user_logs[start:end]
        if page_logs:
            lines = []
            for log in page_logs:
                fc = log["flight_code"]
                pos = role_to_department(log["participants"].get(user.id, "Unknown"))
                host_mention = f"<@{log['host_id']}>" if log.get('host_id') else "Unknown"
                lines.append(f"**{fc}** (<t:{int(log['timestamp'])}:d>)\n└ Host: {host_mention} | Role: **{pos}**")
            records_text = "\n".join(lines)
        else:
            records_text = "No flight records found."

        container_children.append(
            discord.ui.TextDisplay(f"**Flight Records (Page {self.page + 1}/{self.max_page + 1})**\n{records_text}")
        )


        if self.show_graphs:
            container_children.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
            container_children.append(discord.ui.TextDisplay("**Yearly Participation Trend**\nWhen this staff member flies the most"))
            if self.monthly_image_filename:
                container_children.append(
                    discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{self.monthly_image_filename}"))
                )
            if self.weekday_image_filename:
                container_children.append(
                    discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{self.weekday_image_filename}"))
                )

        container = discord.ui.Container(*container_children, accent_color=EMBED_COLOR)
        self.add_item(container)


        row1 = []
        if self.monthly_image_filename or self.weekday_image_filename:
            graph_btn = discord.ui.Button(
                label="Hide Graphs" if self.show_graphs else "Show Graphs",
                style=discord.ButtonStyle.primary,
                custom_id="profile_toggle_graph",
            )
            graph_btn.callback = self.btn_toggle_graph
            row1.append(graph_btn)

        if self.user_logs:
            prev_btn = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary,
                                          custom_id="profile_log_prev", disabled=(self.page == 0))
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary,
                                          custom_id="profile_log_next", disabled=(self.page == self.max_page))
            prev_btn.callback = self.btn_prev
            next_btn.callback = self.btn_next
            row1.extend([prev_btn, next_btn])

        if row1:
            self.add_item(discord.ui.ActionRow(*row1))


        if self.user_logs and hasattr(self.invoking_user, 'roles') and \
                any(r.id == self.LOG_COPY_ROLE_ID for r in self.invoking_user.roles):
            copy_btn = discord.ui.Button(label="Export for Copy", style=discord.ButtonStyle.secondary,
                                          custom_id="profile_log_copy")
            copy_btn.callback = self.btn_copy_callback
            self.add_item(discord.ui.ActionRow(copy_btn))

    async def btn_toggle_graph(self, interaction: discord.Interaction):
        self.show_graphs = not self.show_graphs
        self._build()
        await interaction.response.edit_message(view=self)

    async def btn_prev(self, interaction: discord.Interaction):
        self.page -= 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def btn_next(self, interaction: discord.Interaction):
        self.page += 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def btn_copy_callback(self, interaction: discord.Interaction):

        lines = []
        for log in self.user_logs:
            fc = log["flight_code"]
            dt = datetime.datetime.fromtimestamp(log['timestamp'], tz=JST).strftime("%Y/%m/%d")
            pos = log["participants"].get(self.user_to_check.id, "Unknown")
            if PROFILE_EXPORT_USE_DEPARTMENT:
                pos = role_to_department(pos)

            host_name = "Unknown"
            if log.get('host_id'):
                mem = self.interaction_guild.get_member(log['host_id']) if self.interaction_guild else None
                host_name = mem.display_name if mem else str(log['host_id'])


            lines.append(f"{fc}\t{dt}\t{pos}\t{host_name}")

        tsv_text = "\n".join(lines)
        if not tsv_text:
            tsv_text = "No data."

        file = discord.File(io.BytesIO(tsv_text.encode('utf-8')), filename="flight_logs.txt")
        await interaction.response.send_message(file=file, ephemeral=True)































































































































TEST_MODE = False
TEST_MODE_OWNER_ID = None
TEST_JSON_CHANNEL_ID = cfg("channels.test_json")
TEST_JSON_FILENAME = "flighthub_test_environment.json"
TEST_FLIGHT_CACHE = []
TEST_COMMAND_AUDIT = []


class _TestModeBlocked(app_commands.CheckFailure):
    pass


def _test_admin_allowed(member) -> bool:
    perms = getattr(member, "guild_permissions", None)
    return bool(perms and getattr(perms, "administrator", False))






async def _test_mode_save():
    payload = {
        "schema_version": 1,
        "updated_at": int(datetime.datetime.now(JST).timestamp()),
        "active": TEST_MODE,
        "owner_id": TEST_MODE_OWNER_ID,
        "flights": TEST_FLIGHT_CACHE,
        "command_audit": TEST_COMMAND_AUDIT[-500:],
    }
    return await save_json_to_channel(TEST_JSON_CHANNEL_ID, payload, TEST_JSON_FILENAME)








async def _test_mode_record(command_name, user_id, status, details=None):
    TEST_COMMAND_AUDIT.append({
        "timestamp": int(datetime.datetime.now(JST).timestamp()),
        "command": str(command_name),
        "user_id": int(user_id),
        "status": str(status),
        "details": details or {},
    })
    del TEST_COMMAND_AUDIT[:-500]
    await _test_mode_save()










async def _test_mode_tree_guard(interaction: discord.Interaction) -> bool:

    if not TEST_MODE:
        return True
    command = getattr(interaction, "command", None)
    name = getattr(command, "name", "")
    allowed = {"test_admin", "test_evaluate", "test_progress", "selftest", "create_flight", "briefing", "edit_briefing", "flight_log"}
    if name in allowed:
        return True
    if interaction.response.is_done():
        await interaction.followup.send(
            ephemeral=True, view=build_v2_card("Test mode protection", [(None,
            f"`/{name}` was stopped because isolated-test support is not implemented. No production data was changed.")]))
    else:
        await interaction.response.send_message(
            ephemeral=True, view=build_v2_card("Test mode protection", [(None,
            f"`/{name}` was stopped because isolated-test support is not implemented. No production data was changed.")]))

    try:
        await _test_mode_record(name or "unknown", interaction.user.id, "SKIP", {
            "reason": "Stopped for safety because isolated-test support is not implemented",
        })
    except Exception as exc:
        print(f"[TEST MODE] Could not save blocked-command audit: {exc}")
    raise _TestModeBlocked()


client.tree.interaction_check = _test_mode_tree_guard

















def _st_overwrites(guild, invoker):
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True,
                                              attach_files=True, embed_links=True),
    }
    member = guild.get_member(invoker.id)
    if member:
        ow[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    return ow




























import contextvars
import discord.http as _discord_http


class _AutoTestBlocked(Exception):
    pass


_AUTO_TEST_CTX = contextvars.ContextVar("flighthub_auto_test", default=False)
_AUTO_TEST_PAUSE = False


def _install_auto_test_guards():
    if getattr(_discord_http.HTTPClient, "_flighthub_guarded", False):
        return
    _orig_request = _discord_http.HTTPClient.request

    async def _guarded_request(self, route, *a, **kw):
        if _AUTO_TEST_CTX.get() and str(route.method).upper() != "GET":
            raise _AutoTestBlocked(f"Discord {route.method} {route.url.split('/api/')[-1][:60]}")
        return await _orig_request(self, route, *a, **kw)
    _discord_http.HTTPClient.request = _guarded_request
    _discord_http.HTTPClient._flighthub_guarded = True

    _orig_aio = aiohttp.ClientSession._request

    async def _guarded_aio(self, method, str_or_url, *a, **kw):
        if _AUTO_TEST_CTX.get() and "discord" not in str(str_or_url):
            raise _AutoTestBlocked(f"External communication {method} {str(str_or_url)[:60]}")
        return await _orig_aio(self, method, str_or_url, *a, **kw)
    aiohttp.ClientSession._request = _guarded_aio


_install_auto_test_guards()




























def start():
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN environment variable is required. Set it in your hosting environment.")
    client.run(TOKEN)




from . import eval_sheet
from . import flight_apps
from . import log_survey
from . import ops_features
from . import selftest
from . import test_flight
from . import ui_flights
from . import setup_wizard
from . import admin_tools
from . import v2_features
if __name__ == "__main__":
    start()
