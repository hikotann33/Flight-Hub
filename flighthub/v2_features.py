"""Flight Hub V2 feature set.

Commands added in V2.0: ``/dashboard``, ``/export``, ``/search``, ``/poll``,
``/onduty``, ``/news`` and ``/news_list``.

The polling and scheduling state lives next to the other bot caches in
``core.POLL_CACHE`` / ``core.NEWS_CACHE`` so it is persisted through the
regular ``misc_data.json`` backup channel.

The helpers in this module are pure functions (they never touch Discord) so
they can be unit tested without a live connection.
"""

import csv
import datetime
import io
import json
import traceback
import uuid

import discord
from discord import app_commands
from discord.ext import tasks

from . import config_store as cs
from . import core as C

MAX_POLL_OPTIONS = 6
DAY_SECONDS = 86400
MAX_SEARCH_RESULTS = 20
MAX_NEWS_ITEMS = 50

SCOPE_CHOICES = [
    app_commands.Choice(name="All flights", value="all"),
    app_commands.Choice(name="Upcoming", value="upcoming"),
    app_commands.Choice(name="Completed", value="completed"),
]


def _now_ts():
    return datetime.datetime.now().timestamp()


def notice_card(title, body):
    """Ephemeral card used for every "something went wrong" reply."""
    return C.build_v2_card(title, [(None, body)])


# ---------------------------------------------------------------------------
# Flight helpers
# ---------------------------------------------------------------------------

def upcoming_flights(flights=None, now=None):
    flights = C.FLIGHT_LOG_CACHE if flights is None else flights
    now = _now_ts() if now is None else now
    return [f for f in flights if isinstance(f, dict) and float(f.get("end_timestamp") or 0) > now]


def completed_flights(flights=None, now=None, within_days=None):
    flights = C.FLIGHT_LOG_CACHE if flights is None else flights
    now = _now_ts() if now is None else now
    result = []
    for f in flights:
        if not isinstance(f, dict):
            continue
        if float(f.get("end_timestamp") or 0) > now:
            continue
        if within_days is not None and float(f.get("start_timestamp") or 0) < now - within_days * DAY_SECONDS:
            continue
        result.append(f)
    return result


def _flight_search_text(flight):
    parts = []
    for key in ("flight_code", "origin", "destination", "equipment", "classes", "airline"):
        parts.append(str(flight.get(key) or ""))
    return " ".join(parts).lower()


def filter_flights(query="", scope="all", limit=25, flights=None, now=None):
    """Return flights matching *query* inside *scope*, newest first when possible."""
    flights = C.FLIGHT_LOG_CACHE if flights is None else flights
    now = _now_ts() if now is None else now

    if scope == "upcoming":
        pool = upcoming_flights(flights, now)
    elif scope == "completed":
        pool = completed_flights(flights, now)
    else:
        pool = [f for f in flights if isinstance(f, dict)]

    needle = (query or "").strip().lower()
    if needle:
        pool = [f for f in pool if needle in _flight_search_text(f)]

    pool.sort(key=lambda f: float(f.get("start_timestamp") or 0), reverse=(scope != "upcoming"))
    if not limit or limit <= 0:
        limit = len(pool)
    return pool[: int(limit)]


def flight_line(flight):
    code = str(flight.get("flight_code") or "???")
    origin = str(flight.get("origin") or "???")
    destination = str(flight.get("destination") or "")
    route = f"{origin} -> {destination}" if destination else origin
    start = float(flight.get("start_timestamp") or 0)
    when = f"<t:{int(start)}:f>" if start > 0 else "TBD"
    return f"`{code}` {route} | {when}"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard_stats(flights=None, now=None):
    flights = C.FLIGHT_LOG_CACHE if flights is None else flights
    now = _now_ts() if now is None else now
    upcoming = sorted(
        upcoming_flights(flights, now),
        key=lambda f: float(f.get("start_timestamp") or 0),
    )
    recent = completed_flights(flights, now, within_days=1)
    crew = sum(len(f.get("accepted_users") or []) for f in upcoming)
    return {
        "upcoming": len(upcoming),
        "next": upcoming[0] if upcoming else None,
        "recent_24h": len(recent),
        "total": len([f for f in flights if isinstance(f, dict)]),
        "crew_signups": crew,
        "now": now,
    }


def _config_summary():
    if not cs.is_configured():
        return "Not configured yet. Run `/setup` on the staff server."
    channels = len(cs.CONFIG.get("channels") or {})
    roles = len(cs.CONFIG.get("roles") or {})
    return (
        f"Airline: **{cs.cfg('brand.airline', 'Airline')}** | "
        f"Timezone: **{cs.cfg('options.timezone', 'Asia/Tokyo')}** | "
        f"Channels: **{channels}** | Roles: **{roles}**"
    )


def dashboard_sections(stats):
    next_flight = flight_line(stats["next"]) if stats.get("next") else "No upcoming flight registered."
    return [
        ("Upcoming flights", f"**{stats['upcoming']}** scheduled or running.\nNext: {next_flight}"),
        ("Crew signups", f"**{stats['crew_signups']}** staff accepted across upcoming flights."),
        ("Finished in the last 24h", str(stats["recent_24h"])),
        ("Stored flight records", str(stats["total"])),
        ("Configuration", _config_summary()),
        ("Quick commands", "`/flights` `/search` `/poll` `/flight_app` `/help`"),
    ]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "flight_code", "origin", "destination", "equipment", "classes", "airline",
    "start_time", "end_time", "start_timestamp", "end_timestamp",
    "host_id", "is_bus", "use_bus", "is_test", "briefing_sent",
    "accepted_count", "declined_count",
]


def _iso(ts):
    try:
        ts = float(ts or 0)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def flight_to_row(flight):
    return {
        "flight_code": flight.get("flight_code", ""),
        "origin": flight.get("origin", ""),
        "destination": flight.get("destination", ""),
        "equipment": flight.get("equipment", ""),
        "classes": flight.get("classes", ""),
        "airline": flight.get("airline", ""),
        "start_time": _iso(flight.get("start_timestamp")),
        "end_time": _iso(flight.get("end_timestamp")),
        "start_timestamp": flight.get("start_timestamp", ""),
        "end_timestamp": flight.get("end_timestamp", ""),
        "host_id": flight.get("host_id", ""),
        "is_bus": bool(flight.get("is_bus")),
        "use_bus": bool(flight.get("use_bus")),
        "is_test": bool(flight.get("is_test")),
        "briefing_sent": bool(flight.get("briefing_sent")),
        "accepted_count": len(flight.get("accepted_users") or []),
        "declined_count": len(flight.get("declined_users") or []),
    }


def flights_to_csv(rows, columns=None):
    columns = list(columns or CSV_COLUMNS)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def flights_to_json(rows):
    return json.dumps(rows, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------
# Polls
# ---------------------------------------------------------------------------

def parse_poll_options(raw):
    """Split poll input into options. ``|`` and ``,`` are both accepted."""
    text = (raw or "").replace("|", ",")
    return [part.strip() for part in text.split(",") if part.strip()]


def tally_poll(poll):
    options = poll.get("options") or []
    counts = [0] * len(options)
    for index in (poll.get("votes") or {}).values():
        try:
            slot = int(index)
        except (TypeError, ValueError):
            continue
        if 0 <= slot < len(counts):
            counts[slot] += 1
    return counts


def poll_embed(poll, color=None):
    options = poll.get("options") or []
    counts = tally_poll(poll)
    total = sum(counts)
    lines = []
    for position, (label, count) in enumerate(zip(options, counts), start=1):
        percent = int(round(count * 100.0 / total)) if total else 0
        plural = "vote" if count == 1 else "votes"
        lines.append(f"**{position}.** {label} - {count} {plural} ({percent}%)")
    embed = discord.Embed(
        title=str(poll.get("question") or "Poll"),
        description="\n".join(lines) if lines else "No options were provided.",
        color=color or C.EMBED_COLOR,
    )
    plural = "vote" if total == 1 else "votes"
    if poll.get("closed"):
        embed.set_footer(text=f"Poll closed | {total} {plural}")
    else:
        embed.set_footer(text=f"{total} {plural} | press a number to vote, press it again to remove your vote")
    return embed


class PollOptionButton(discord.ui.Button):
    def __init__(self, index: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=str(index + 1),
                         custom_id=f"fh_poll_option_{index}")
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await handle_vote(interaction, self.index)


class PollCloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Close", custom_id="fh_poll_close")

    async def callback(self, interaction: discord.Interaction):
        await handle_close(interaction)


class PollView(discord.ui.View):
    """Persistent view.

    ``option_count=None`` renders every possible button and is what gets
    registered on startup so any earlier poll keeps accepting votes after a
    restart; commands pass an explicit count so the posted message only shows
    the options that actually exist.
    """

    def __init__(self, option_count: int = None):
        super().__init__(timeout=None)
        if option_count is None:
            count = MAX_POLL_OPTIONS
        else:
            count = max(0, min(int(option_count), MAX_POLL_OPTIONS))
        for index in range(count):
            self.add_item(PollOptionButton(index))
        self.add_item(PollCloseButton())


async def _save_state():
    if not C.MISC_DATA_CHANNEL_ID:
        return
    try:
        await C.save_misc_data()
    except Exception as exc:
        print(f"v2: could not persist poll/news state: {exc}")


async def handle_vote(interaction: discord.Interaction, index: int):
    poll = C.POLL_CACHE.get(str(getattr(interaction.message, "id", "")))
    if poll is None:
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("Poll", "This poll is no longer available."))
    if poll.get("closed"):
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("Poll", "This poll is closed."))

    options = poll.get("options") or []
    if not 0 <= index < len(options):
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("Poll", "That option is not part of this poll."))

    votes = poll.setdefault("votes", {})
    user_id = str(interaction.user.id)
    previous = votes.get(user_id)
    if previous == index:
        votes.pop(user_id, None)
        message = "Your vote was removed."
    else:
        votes[user_id] = index
        message = f"You voted for **{index + 1}. {options[index]}**."

    await _save_state()
    try:
        await interaction.response.edit_message(embed=poll_embed(poll), view=PollView(len(options)))
    except Exception as exc:
        print(f"v2: could not refresh poll message: {exc}")
        return
    try:
        await interaction.followup.send(message, ephemeral=True)
    except Exception:
        pass


async def handle_close(interaction: discord.Interaction):
    poll = C.POLL_CACHE.get(str(getattr(interaction.message, "id", "")))
    if poll is None:
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("Poll", "This poll is no longer available."))
    if interaction.user.id != poll.get("author_id") and not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("Poll", "Only the poll author or a manager can close this poll."))

    poll["closed"] = True
    poll["closed_ts"] = _now_ts()
    await _save_state()
    try:
        await interaction.response.edit_message(embed=poll_embed(poll), view=None)
    except Exception as exc:
        print(f"v2: could not close poll: {exc}")


async def _refresh_poll_message(poll):
    channel_id = int(poll.get("channel_id") or 0)
    message_id = int(poll.get("message_id") or 0)
    if not channel_id or not message_id:
        return
    try:
        channel = C.client.get_channel(channel_id) or await C.client.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)
        await message.edit(embed=poll_embed(poll), view=None)
    except Exception as exc:
        print(f"v2: could not update poll message: {exc}")


def due_polls(polls, now=None):
    now = _now_ts() if now is None else now
    result = []
    for poll in (polls or {}).values():
        if poll.get("closed"):
            continue
        due = float(poll.get("auto_close_ts") or 0)
        if due and due <= now:
            result.append(poll)
    return result


# ---------------------------------------------------------------------------
# Scheduled announcements
# ---------------------------------------------------------------------------

def news_due(items, now=None):
    now = _now_ts() if now is None else now
    return [
        item for item in (items or [])
        if str(item.get("status") or "scheduled") == "scheduled"
        and float(item.get("due_ts") or 0) <= now
    ]


def prune_news(items, now=None, keep=MAX_NEWS_ITEMS):
    """Keep recent entries only so the cache cannot grow without bound."""
    now = _now_ts() if now is None else now
    cutoff = now - 7 * DAY_SECONDS
    items = [i for i in (items or []) if i]
    alive = [
        i for i in items
        if str(i.get("status") or "scheduled") == "scheduled" or float(i.get("due_ts") or 0) >= cutoff
    ]
    alive.sort(key=lambda i: float(i.get("due_ts") or 0), reverse=True)
    return alive[: max(int(keep), 1)]


async def _resolve_channel(channel_id):
    try:
        channel_id = int(channel_id or 0)
    except (TypeError, ValueError):
        return None
    if not channel_id:
        return None
    channel = C.client.get_channel(channel_id)
    if channel is not None:
        return channel
    try:
        return await C.client.fetch_channel(channel_id)
    except Exception:
        return None


async def dispatch_due_news(now=None):
    now = _now_ts() if now is None else now
    due = news_due(C.NEWS_CACHE, now)
    if not due:
        return 0
    for item in due:
        channel = await _resolve_channel(item.get("channel_id"))
        if channel is None:
            item["status"] = "failed"
            item["error"] = "channel not found"
            continue
        try:
            await channel.send(content=str(item.get("content") or ""))
            item["status"] = "posted"
            item["posted_ts"] = now
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = str(exc)[:200]
    C.NEWS_CACHE[:] = prune_news(C.NEWS_CACHE, now)
    await _save_state()
    return len(due)


async def close_due_polls(now=None):
    now = _now_ts() if now is None else now
    due = due_polls(C.POLL_CACHE, now)
    for poll in due:
        poll["closed"] = True
        poll["closed_ts"] = now
        await _refresh_poll_message(poll)
    if due:
        await _save_state()
    return len(due)


@tasks.loop(seconds=30)
async def v2_maintenance_loop():
    try:
        await dispatch_due_news()
        await close_due_polls()
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@C.client.tree.command(name="dashboard", description="Show an overview of flights, signups and configuration.")
async def dashboard_cmd(interaction: discord.Interaction):
    stats = dashboard_stats()
    view = C.build_v2_card("Flight Hub Dashboard", dashboard_sections(stats),
                           footer=f"Flight Hub {C.DISPLAY_VERSION}")
    await interaction.response.send_message(view=view, ephemeral=True)


@C.client.tree.command(name="export", description="[Manager] Export the flight log as a CSV or JSON file.")
@app_commands.describe(
    format="File format to export",
    scope="Which flights to include",
    limit="Maximum number of rows (1-2000)",
)
@app_commands.choices(format=[
    app_commands.Choice(name="CSV (Excel friendly)", value="csv"),
    app_commands.Choice(name="JSON", value="json"),
], scope=SCOPE_CHOICES)
@C.event_manager_only
async def export_cmd(interaction: discord.Interaction, format: str = "csv",
                     scope: str = "all", limit: int = 250):
    try:
        limit = int(limit or 250)
    except (TypeError, ValueError):
        limit = 250
    limit = max(1, min(limit, 2000))
    rows = [flight_to_row(f) for f in filter_flights("", scope, limit)]

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    if format == "json":
        payload = flights_to_json(rows).encode("utf-8")
        filename = f"flight_log_{stamp}.json"
    else:
        payload = flights_to_csv(rows).encode("utf-8-sig")
        filename = f"flight_log_{stamp}.csv"

    await interaction.response.send_message(
        content=f"Exported **{len(rows)}** flight record(s) from `{scope}`.",
        file=discord.File(io.BytesIO(payload), filename=filename),
        ephemeral=True,
    )


@C.client.tree.command(name="search", description="Search flights by code, route or aircraft.")
@app_commands.describe(
    query="Text to look for (flight code, route, aircraft, class)",
    scope="Which flights to search",
    limit="Maximum results (1-20)",
)
@app_commands.choices(scope=SCOPE_CHOICES)
async def search_cmd(interaction: discord.Interaction, query: str = "",
                     scope: str = "upcoming", limit: int = 10):
    try:
        limit = int(limit or 10)
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, MAX_SEARCH_RESULTS))

    results = filter_flights(query, scope, limit)
    if not results:
        return await interaction.response.send_message(
            ephemeral=True,
            view=notice_card("Flight search", f"No flight matched `{query or 'any'}` in `{scope}`."))

    sections = [
        ("Search", f"Query: `{query or 'any'}` | Scope: **{scope}** | Showing {len(results)} of at most {limit}"),
        (None, "\n".join(flight_line(f) for f in results)),
        (None, "Use `/flights` for the interactive list or `/search` with another `scope`."),
    ]
    await interaction.response.send_message(
        ephemeral=True,
        view=C.build_v2_card("Flight search", sections, footer=f"Flight Hub {C.DISPLAY_VERSION}"))


@C.client.tree.command(name="poll", description="Create a poll with buttons and live results.")
@app_commands.describe(
    question="The question to vote on",
    options="Options separated by commas or | (2 to 6)",
    minutes="Auto-close after this many minutes (0 = close manually)",
)
async def poll_cmd(interaction: discord.Interaction, question: str, options: str, minutes: int = 0):
    found = parse_poll_options(options)
    if len(found) < 2:
        return await interaction.response.send_message(
            ephemeral=True,
            view=notice_card("Poll", "Provide at least 2 options, separated by commas."))
    if len(found) > MAX_POLL_OPTIONS:
        return await interaction.response.send_message(
            ephemeral=True,
            view=notice_card("Poll", f"A poll can have at most {MAX_POLL_OPTIONS} options."))

    minutes = int(minutes or 0)
    if minutes < 0:
        minutes = 0

    poll = {
        "id": uuid.uuid4().hex[:8],
        "question": str(question).strip()[:256] or "Poll",
        "options": found[:MAX_POLL_OPTIONS],
        "author_id": interaction.user.id,
        "channel_id": interaction.channel_id,
        "guild_id": interaction.guild_id,
        "created_ts": _now_ts(),
        "auto_close_ts": (_now_ts() + minutes * 60) if minutes else 0,
        "votes": {},
        "closed": False,
    }

    await interaction.response.send_message(embed=poll_embed(poll), view=PollView(len(poll["options"])))
    try:
        message = await interaction.original_response()
    except Exception as exc:
        print(f"v2: could not register poll message: {exc}")
        return
    poll["message_id"] = str(message.id)
    C.POLL_CACHE[str(message.id)] = poll
    await _save_state()


@C.client.tree.command(name="onduty", description="Toggle the on-duty role for yourself.")
@app_commands.guild_only()
async def onduty_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("On duty", "This command only works in a server."))
    role_id = cs.cfg("roles.on_duty")
    if not role_id:
        return await interaction.response.send_message(
            ephemeral=True,
            view=notice_card("On duty",
                             "The on-duty role is not configured. Set `roles.on_duty` to a role id in "
                             "`config/config.json`, then restart the bot."))
    try:
        role = interaction.guild.get_role(int(role_id))
    except (TypeError, ValueError):
        role = None
    if role is None:
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("On duty", "The configured on-duty role does not exist in this server."))

    me = interaction.guild.me
    if me is not None and me.top_role and role.position >= me.top_role.position:
        return await interaction.response.send_message(
            ephemeral=True,
            view=notice_card("On duty", "I cannot manage that role: place it below my highest role."))

    try:
        if role in interaction.user.roles:
            await interaction.user.remove_roles(reason="On duty toggle")
            state = "off duty"
        else:
            await interaction.user.add_roles(reason="On duty toggle")
            state = "on duty"
    except discord.Forbidden:
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("On duty", "I am missing the **Manage Roles** permission."))
    except discord.HTTPException as exc:
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("On duty", f"Could not update your roles: {exc}"))

    await interaction.response.send_message(
        ephemeral=True,
        view=C.build_v2_card("On duty",
                             [("Role", role.mention), ("Status", f"You are now **{state}**.")],
                             footer=f"Flight Hub {C.DISPLAY_VERSION}"))


@C.client.tree.command(name="news", description="[Manager] Schedule an announcement to be posted later.")
@app_commands.describe(
    content="Message to post",
    schedule="When to post (YYYY-MM-DD HH:MM in the configured timezone)",
    channel="Target channel (defaults to the current one)",
)
@C.event_manager_only
async def news_cmd(interaction: discord.Interaction, content: str, schedule: str,
                   channel: discord.TextChannel = None):
    when = C.parse_loa_datetime(schedule)
    if when is None:
        return await interaction.response.send_message(
            ephemeral=True,
            view=notice_card("Scheduled announcement",
                             "Invalid date/time. Use `YYYY-MM-DD HH:MM` or `YYYY-MM-DD`."))
    due_ts = when.timestamp()
    now_ts = _now_ts()
    if due_ts <= now_ts:
        return await interaction.response.send_message(
            ephemeral=True,
            view=notice_card("Scheduled announcement", "The scheduled time must be in the future."))

    target = channel or interaction.channel
    target_id = getattr(target, "id", None) or interaction.channel_id
    item = {
        "id": uuid.uuid4().hex[:8],
        "content": str(content)[:2000],
        "channel_id": target_id,
        "guild_id": interaction.guild_id,
        "due_ts": due_ts,
        "created_by": interaction.user.id,
        "created_ts": now_ts,
        "status": "scheduled",
    }
    C.NEWS_CACHE.append(item)
    C.NEWS_CACHE[:] = prune_news(C.NEWS_CACHE, now_ts)
    await _save_state()

    sections = [
        ("Channel", f"<#{target_id}>"),
        ("Post at", f"<t:{int(due_ts)}:F> (<t:{int(due_ts)}:R>)"),
        ("Message", str(content)[:500]),
        ("Status", f"scheduled | id `{item['id']}`"),
        (None, "Check or cancel with `/news_list`."),
    ]
    await interaction.response.send_message(
        ephemeral=True,
        view=C.build_v2_card("Scheduled announcement", sections, footer=f"Flight Hub {C.DISPLAY_VERSION}"))


@C.client.tree.command(name="news_list", description="[Manager] List scheduled announcements, optionally cancelling one.")
@app_commands.describe(id="Announcement id to cancel (as shown by /news)")
@C.event_manager_only
async def news_list_cmd(interaction: discord.Interaction, id: str = ""):
    wanted = (id or "").strip()
    if wanted:
        target = next((item for item in C.NEWS_CACHE if str(item.get("id")) == wanted), None)
        if target is None:
            return await interaction.response.send_message(
                ephemeral=True, view=notice_card("Scheduled announcement", f"No announcement with id `{wanted}`."))
        if str(target.get("status") or "scheduled") != "scheduled":
            return await interaction.response.send_message(
                ephemeral=True, view=notice_card("Scheduled announcement", "That announcement was already handled."))
        C.NEWS_CACHE.remove(target)
        await _save_state()
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("Scheduled announcement", f"Cancelled `{wanted}`."))

    pending = sorted(
        [i for i in C.NEWS_CACHE if str(i.get("status") or "scheduled") == "scheduled"],
        key=lambda i: float(i.get("due_ts") or 0),
    )
    if not pending:
        return await interaction.response.send_message(
            ephemeral=True, view=notice_card("Scheduled announcement", "There is nothing scheduled right now."))

    lines = []
    for item in pending[:15]:
        channel_id = item.get("channel_id")
        lines.append(f"`{item.get('id')}` | <#{channel_id}> | <t:{int(float(item.get('due_ts') or 0))}:f> | "
                     f"{str(item.get('content') or '')[:60]}")
    sections = [(None, "\n".join(lines))]
    if len(pending) > 15:
        sections.append((None, f"{len(pending) - 15} more not shown."))
    sections.append((None, "Cancel one with `/news_list id:<id>`."))
    await interaction.response.send_message(
        ephemeral=True,
        view=C.build_v2_card("Scheduled announcements", sections, footer=f"Flight Hub {C.DISPLAY_VERSION}"))


def register(client=None):
    """Hook the persistent view and the background loop (used by on_ready)."""
    target = client or C.client
    try:
        target.add_view(PollView())
    except Exception as exc:
        print(f"v2: could not register the poll view: {exc}")
    try:
        if not v2_maintenance_loop.is_running():
            v2_maintenance_loop.start()
    except Exception as exc:
        print(f"v2: could not start the maintenance loop: {exc}")
