import discord
from discord import app_commands
import datetime
import json
import io
import re
import traceback
import asyncio
import copy
import calendar
import random
import sys
import os
import matplotlib.pyplot as plt

from . import core as C

class ClearLogSelect(discord.ui.Select):
    def __init__(self, safe_flights):
        options = []
        for f in safe_flights[:25]:
            end_dt = datetime.datetime.fromtimestamp(f['end_timestamp'], tz=C.JST).strftime('%m/%d %H:%M')
            options.append(discord.SelectOption(
                label=f"{f['flight_code']} (Ended)",
                description=f"End time: {end_dt}",
                value=f['flight_code']
            ))
        super().__init__(placeholder="Select data that is safe to delete", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        deleted_codes = []
        
        async with C.global_json_lock:
            for val in self.values:
                idx = next((i for i, f in enumerate(C.FLIGHT_LOG_CACHE) if f["flight_code"] == val), -1)
                if idx != -1:
                    flight = C.FLIGHT_LOG_CACHE[idx]
                    try:
                        if s_ch := C.client.get_channel(flight.get("staff_channel_id")):
                            await (await s_ch.fetch_message(flight["staff_message_id"])).delete()
                    except: pass
                    try:
                        if c_ch := C.client.get_channel(flight.get("customer_channel_id")):
                            if flight.get("customer_message_id"):
                                await (await c_ch.fetch_message(flight["customer_message_id"])).delete()
                    except: pass
                    C.FLIGHT_LOG_CACHE.pop(idx)
                    deleted_codes.append(val)
            C.global_db_dirty = True
        
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f"Completely removed the following data from the DB (JSON):\n`{', '.join(deleted_codes)}`")]))

class ClearLogView(discord.ui.View):
    def __init__(self, safe_flights):
        super().__init__(timeout=300)
        self.add_item(ClearLogSelect(safe_flights))

@C.client.tree.command(name="clear_logs", description="[Admin] Safely remove old, unnecessary flight data left in the JSON store.")
@C.event_manager_only
async def clear_logs_cmd(interaction: discord.Interaction):
    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    
    now = datetime.datetime.now().timestamp()

    safe_flights = [f for f in C.FLIGHT_LOG_CACHE if f["end_timestamp"] < now - 86400]
    
    if not safe_flights:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'There is no old data that can be deleted (ended more than 24 hours ago). The JSON is clean!')]))
        
    view = ClearLogView(safe_flights)
    await interaction.response.send_message(f"**JSON Cleanup Tool**\nFound **{len(safe_flights)}** old ended flight(s) that remained due to bugs.\nSelect the data you want to remove. (multi-select)", view=view, ephemeral=True)

@C.client.tree.command(name="delay", description="Announce a flight delay.")
@app_commands.describe(flight_code="Select Flight Code", new_time="New Departure Time (e.g. 22:30)",
                       reason="Reason for delay")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def delay_flight(interaction: discord.Interaction, flight_code: str, new_time: str, reason: str):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'Flight `{flight_code}` not found.', discord.Color.red()), content=None), ephemeral=True)


    if flight.get("is_gamenight") or flight_code.startswith("GN_"):
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'To change a Game Night time, use **`/edit_gamenight`** instead of this command!')]))


    if flight.get("is_private"):
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Private flights have no customer notifications. Use **`/edit_flight`** to change the time.')]))

    airline = flight.get('airline', 'Airline')
    destination = flight.get('destination', 'Unknown')

    try:
        tz_offset = C.parse_timezone_offset(flight.get("host_timezone_str", "GMT+9"))
        input_tz = datetime.timezone(datetime.timedelta(hours=tz_offset))
        flight_dt = datetime.datetime.fromtimestamp(flight["start_timestamp"], tz=input_tz)

        clean_time = new_time.strip()
        if len(clean_time) == 4 and clean_time.isdigit():
            clean_time = f"{clean_time[:2]}:{clean_time[2:]}"

        parsed_time = datetime.datetime.strptime(clean_time, "%H:%M").time()
        new_dt = datetime.datetime.combine(flight_dt.date(), parsed_time).replace(tzinfo=input_tz)

        if new_dt < flight_dt - datetime.timedelta(hours=12):
            new_dt += datetime.timedelta(days=1)

        new_ts = int(new_dt.timestamp())
        timestamp_str = f"<t:{new_ts}:t> (<t:{new_ts}:R>)"
    except Exception:
        timestamp_str = new_time

    embed = discord.Embed(
        title=f"{airline} | {flight_code} - DELAYED",
        description=(
            f"Flight **{flight_code}** to {destination} is experiencing a **departure delay** for the following reason.\n"
            f"Please be advised that flight **{flight_code}** to *{destination}* has been **delayed**.\n\n"
            f"**Reason:**\n{reason}\n\n"
            f"**New Estimated Time:**\n**{timestamp_str}**\n\n"
            f"We apologize for any inconvenience this may cause and appreciate your patience.\n"
            f"We sincerely apologize for the inconvenience to our customers."
        ),
        color=discord.Color.orange()
    )
    embed.set_author(name="Travel Update")

    sent_msg = await C.client.get_channel(C.CUSTOMER_CHANNEL_ID).send(embed=embed)

    async with C.global_json_lock:
        target_idx = next(
            (i for i, f in enumerate(C.FLIGHT_LOG_CACHE) if f["flight_code"] == flight_code), -1)
        if target_idx != -1:
            C.FLIGHT_LOG_CACHE[target_idx].setdefault("delay_message_ids", []).append(sent_msg.id)
            C.global_db_dirty = True

    await C.auto_publish_schedule()
    await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Delay announced successfully.')]))

@C.client.tree.command(name="dispatch_app", description="[Staff] Select one of your approved flight applications and open it for signup.")
@app_commands.describe(message_id="Select one of your approved flight applications")
@app_commands.autocomplete(message_id=C.approved_my_flight_app_autocomplete)
@C.event_manager_only
async def dispatch_app_cmd(interaction: discord.Interaction, message_id: str):
    if message_id == "none":
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'There are no approved flight applications to select.')]))
        
    if not C.is_event_manager_or_chief(interaction.user) and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    
    await interaction.response.defer(ephemeral=True)
    
    app_channel = C.client.get_channel(C.FLIGHT_APP_CHANNEL_ID)
    if not app_channel:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Application channel not found.')]))

    try:
        msg = await app_channel.fetch_message(int(message_id.strip()))
    except Exception:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The specified message was not found.')]))

    if not msg.embeds:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The message does not contain application data.')]))

    app_data = C.extract_app_data(msg.embeds[0])
    if not app_data.get("flight_code"):
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Failed to extract flight information.')]))

    flight_code = app_data["flight_code"]
    

    now = datetime.datetime.now().timestamp()
    already_exists = any(f["flight_code"].lower() == flight_code.lower() and f.get("end_timestamp", 0) > now for f in C.FLIGHT_LOG_CACHE)
    if already_exists:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This flight is already operating or registered in the schedule. (no flight to display)')]))

    await C.ensure_templates_fresh()
    template = C.FLIGHT_DB.get(flight_code)
    image_url, image_bytes, src_ch, src_msg = None, None, None, None
    classes = "Economy"
    color = "1B3444"

    if template:
        variants = template.get("variants", {})
        clean_equip = app_data["equipment"].split("/")[-1].strip()
        for k, v in variants.items():
            if k.lower() == clean_equip.lower():
                classes = v.get("classes", "Economy")
                color = v.get("color", "1B3444")
                src_ch = v.get("source_channel_id")
                src_msg = v.get("source_message_id")
                break
        if src_ch and src_msg:
            image_url, image_bytes = await C.fetch_fresh_image_info(src_ch, src_msg)

    data = {
        "flight_code": flight_code,
        "origin": app_data["origin"],
        "destination": app_data["dest"],
        "equipment": app_data["equipment"].split("/")[-1].strip(),
        "classes": classes,
        "roblox_link": "",
        "airline": app_data["airline"],
        "color": color,
        "source_channel_id": src_ch,
        "source_message_id": src_msg,
        "staff_meet_datetime_str": f"{app_data['date']} {app_data['time']}",
        "passenger_time_str": app_data["time"],
        "host_timezone_str": app_data["tz"],
        "event_title": None,
        "mention_str": f"<@&{C.NOTIFICATION_ROLE_ID}>",
        "is_custom": False,
        "use_bus": False
    }

    host_user = interaction.guild.get_member(app_data["host_id"]) or interaction.user

    success, result_msg = await C.process_flight_creation(host_user, data, image_bytes, image_url)
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_CHECK_STR + ' Dispatched Successfully', 'Created a flight from the application and started recruitment.', discord.Color.green()), content=None), ephemeral=True)
    else:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Creation Error', result_msg, discord.Color.red()), content=None), ephemeral=True)

@C.client.tree.command(name="staff_profile", description="View a staff profile, flight participation rate, and role stats.")
@app_commands.describe(target_user="Target user (Managers only) - mention, ID, or username")
async def staff_profile_cmd(interaction: discord.Interaction, target_user: str = None):
 if interaction.guild_id != C.STAFF_GUILD_ID:
  return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This command can only be used in the staff server.')]))
 
 if target_user:
  resolved_user = await C.get_target_user(C.client, target_user)
  if not resolved_user:
   return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'User `{target_user}` was not found.')]))
  user_to_check = interaction.guild.get_member(resolved_user.id) or resolved_user
 else:
  user_to_check = interaction.user
 
 is_other_user = user_to_check.id != interaction.user.id
 
 if is_other_user:
  if C.LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
   return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, "You do not have permission to view other users' profiles.")]))
 
 await interaction.response.defer(ephemeral=is_other_user)
 
 jst_now = datetime.datetime.now(C.JST)
 now = jst_now.timestamp()
 month_ago = now - (30 * 24 * 3600)
 start_of_year_dt = datetime.datetime(jst_now.year, 1, 1, tzinfo=C.JST)
 start_of_year_ts = start_of_year_dt.timestamp()



 month_count = 0
 year_count = 0
 first_flight_ts = None
 
 unique_flights_30d = set()
 user_unique_flights_30d = set()
 role_counts = {}
 user_logs = []


 async def _read_log_channel(ch_id):
  parsed_logs = []
  ch = C.client.get_channel(ch_id)
  if not ch:
   return parsed_logs
  try:
   async for msg in ch.history(limit=400):
    parsed = C.parse_log_message(msg)
    if parsed:
     parsed_logs.append(parsed)
  except Exception as e:
   print(f"Log Read Error: {e}")
  return parsed_logs

 channel_logs = await asyncio.gather(
  _read_log_channel(C.FLIGHT_LOG_HISTORY_CHANNEL_ID),
  _read_log_channel(C.MANUAL_LOG_CHANNEL_ID),
 )

 for parsed in (p for logs in channel_logs for p in logs):
  if parsed["timestamp"] >= month_ago:
   unique_flights_30d.add(parsed["flight_code"])
  if user_to_check.id in parsed["participants"]:
   user_logs.append(parsed)
   if parsed["timestamp"] >= month_ago:
    user_unique_flights_30d.add(parsed["flight_code"])
    pos = C.role_to_department(parsed["participants"][user_to_check.id])
    role_counts[pos] = role_counts.get(pos, 0) + 1

 user_logs.sort(key=lambda x: x["timestamp"])
 
 for log in user_logs:
  ts = log["timestamp"]
  if not first_flight_ts:
   first_flight_ts = ts
  if ts >= start_of_year_ts:
   year_count += 1
  if ts >= month_ago:
   month_count += 1
 
 user_logs.reverse()
 
 discord_avatar_url = user_to_check.display_avatar.url if user_to_check.display_avatar else ""
 
 roles = [r.mention for r in reversed(user_to_check.roles) if not r.is_default()][:15] if hasattr(user_to_check, 'roles') else []
 roles_str = " ".join(roles) if roles else ""
 
 first_flight_str = f"<t:{int(first_flight_ts)}:F>" if first_flight_ts else "N/A"
 

 total_flights_30d = len(unique_flights_30d)
 user_flights_30d = len(user_unique_flights_30d)
 participation_rate = min(user_flights_30d / total_flights_30d * 100, 100.0) if total_flights_30d > 0 else 0
 top_roles = sorted(role_counts.items(), key=lambda x: x[1], reverse=True)[:3]
 top_roles_str = " / ".join([f"{role} ({count})" for role, count in top_roles]) if top_roles else "None"
 
 stats_str = (
  f"**First Flight:** {first_flight_str}\n"
  f"**This Year ({jst_now.year}):** {year_count} Flights\n"
  f"**Last 30 Days:** {month_count} Flights\n"
  f"**Participation Rate (30 Days):** {participation_rate:.1f}% ({user_flights_30d}/{total_flights_30d})\n"
  f"**Top Roles (30 Days):** {top_roles_str}"
 )





 month_labels_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
 weekday_labels_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
 monthly_counts = [0] * 12
 weekday_counts = [0] * 7
 for log in user_logs:
  ts = log["timestamp"]
  if ts >= start_of_year_ts:
   dt_jst = datetime.datetime.fromtimestamp(ts, tz=C.JST)
   monthly_counts[dt_jst.month - 1] += 1
   weekday_counts[dt_jst.weekday()] += 1


 graph_display_name = user_to_check.display_name



 monthly_buf = await asyncio.to_thread(
  C._build_ordered_bar_chart,
  month_labels_en, monthly_counts, f"{graph_display_name} - Monthly Flight Participation ({jst_now.year})", "Flights"
 )
 weekday_buf = await asyncio.to_thread(
  C._build_ordered_bar_chart,
  weekday_labels_en, weekday_counts, f"{graph_display_name} - Flight Participation by Day of Week ({jst_now.year})", "Flights"
 )
 monthly_filename = f"profile_monthly_{user_to_check.id}.png"
 weekday_filename = f"profile_weekday_{user_to_check.id}.png"
 graph_files = [
  discord.File(monthly_buf, filename=monthly_filename),
  discord.File(weekday_buf, filename=weekday_filename),
 ]

 view = C.StaffProfileLayoutView(
  user_to_check=user_to_check,
  discord_avatar_url=discord_avatar_url,
  role_mentions=roles_str,
  stats_str=stats_str,
  user_logs=user_logs,
  monthly_image_filename=monthly_filename,
  weekday_image_filename=weekday_filename,
  invoking_user=interaction.user,
  interaction_guild=interaction.guild,
 )
 view.message = await interaction.followup.send(view=view, files=graph_files)

def _is_staff_manager(member) -> bool:
    roles = getattr(member, "roles", []) if member else []
    return bool(member and (C.is_chief(member) or C.LOG_MANAGER_ROLE_ID in [r.id for r in roles]))

def _safe_timestamp(value):
    try:
        result = float(value) if value is not None else None
        return result if result is not None and result > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None

async def _send_ops_error(interaction: discord.Interaction, title: str, message: str):
    view = C.build_v2_card(title, [(None, message)], color=0xB23B3B)
    if interaction.response.is_done():
        return await interaction.followup.send(view=view, ephemeral=True)
    return await interaction.response.send_message(view=view, ephemeral=True)

@C.client.tree.command(name="healthcheck", description="[Managers] Check bot, data-load and backup-channel health.")
async def healthcheck_cmd(interaction: discord.Interaction):
    if interaction.guild_id != C.STAFF_GUILD_ID or not _is_staff_manager(interaction.user):
        return await _send_ops_error(interaction, "Access denied", "This command is available to staff managers in the staff server only.")

    await interaction.response.defer(ephemeral=True)
    latency_ms = C.client.latency * 1000 if C.client.latency is not None else None
    loader_lines = []
    failed_loaders = []
    for name, status in sorted(C.LOAD_STATUS.items()):
        ok = bool(status.get("ok"))
        state = "OK" if ok else "FAILED"
        line = f"**{name}** — {state}; attempts: {status.get('attempts', '?')}"
        if not ok:
            detail = str(status.get("detail", ""))[:180]
            if detail:
                line += f"\n> {detail}"
            failed_loaders.append(name)
        loader_lines.append(line)

    if not loader_lines:
        loader_text = "No loader status has been recorded yet."
    else:
        loader_text = "\n".join(loader_lines)

    channel_lines = []
    for label, channel_id in (
        ("Flight backup", C.FLIGHT_LOG_CHANNEL_ID),
        ("LOA records", C.LOA_TRACK_CHANNEL_ID),
        ("Audit log", C.AUDIT_LOG_CHANNEL_ID),
    ):
        channel = C.client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await C.client.fetch_channel(channel_id)
            except Exception:
                channel_lines.append(f"**{label}** — UNAVAILABLE")
                continue
        channel_lines.append(f"**{label}** — ACCESSIBLE ({channel.id})")

    healthy = (
        bool(C.LOAD_STATE.get("initialized"))
        and not C.LOAD_UNSAFE_CHANNELS
        and not failed_loaders
        and all("UNAVAILABLE" not in line for line in channel_lines)
    )
    status_label = "HEALTHY" if healthy else "ATTENTION REQUIRED"
    sections = [
        ("Overall status", status_label),
        ("Bot connection", f"Connected as {C.client.user}\nGateway latency: {latency_ms:.0f} ms" if latency_ms is not None else f"Connected as {C.client.user}\nGateway latency: unavailable"),
        ("Data initialization", f"Initialized: {'Yes' if C.LOAD_STATE.get('initialized') else 'No'}\nRetry task running: {'Yes' if C.LOAD_STATE.get('retry_running') else 'No'}\nProtected data sources: {len(C.LOAD_UNSAFE_CHANNELS)}"),
        ("Data loaders", loader_text),
        ("Channel access", "\n".join(channel_lines)),
        ("In-memory records", f"Flights: {len(C.FLIGHT_LOG_CACHE)}\nLOA records: {len(C.LOA_CACHE)}"),
    ]
    await interaction.followup.send(
        view=C.build_v2_card("System Healthcheck", sections, color=0x2E8B57 if healthy else 0xC58A2B,
                           footer="Read-only diagnostic. No stored data is modified."),
        ephemeral=True,
    )

@C.client.tree.command(name="flight_dashboard", description="[Managers] Show current and upcoming flights.")
async def flight_dashboard_cmd(interaction: discord.Interaction):
    if interaction.guild_id != C.STAFF_GUILD_ID or not _is_staff_manager(interaction.user):
        return await _send_ops_error(interaction, "Access denied", "This command is available to staff managers in the staff server only.")
    if C.FLIGHT_LOG_CHANNEL_ID in C.LOAD_UNSAFE_CHANNELS:
        return await _send_ops_error(interaction, "Flight data unavailable", "The flight data source did not load safely. Run /healthcheck before relying on this dashboard.")

    await interaction.response.defer(ephemeral=True)
    now = datetime.datetime.now(C.JST).timestamp()
    upcoming = []
    active = 0
    valid_records = 0
    for flight in C.FLIGHT_LOG_CACHE:
        if not isinstance(flight, dict):
            continue
        valid_records += 1
        start_ts = _safe_timestamp(flight.get("start_timestamp"))
        end_ts = _safe_timestamp(flight.get("end_timestamp"))
        if end_ts and end_ts > now:
            active += 1
        if start_ts and start_ts >= now:
            upcoming.append((start_ts, flight))
    upcoming.sort(key=lambda item: item[0])

    lines = []
    for start_ts, flight in upcoming[:10]:
        code = str(flight.get("flight_code") or flight.get("event_code") or "Unknown")[:80]
        origin = str(flight.get("origin") or "Unknown")[:60]
        destination = str(flight.get("destination") or "Unknown")[:60]
        lines.append(f"**{code}** — {origin} → {destination}\nDeparture: <t:{int(start_ts)}:F>")
    upcoming_text = "\n\n".join(lines) if lines else "No upcoming departures were found."
    sections = [
        ("Tracked records", str(valid_records)),
        ("Flights not yet ended", str(active)),
        ("Upcoming departures", f"{len(upcoming)} total\n\n{upcoming_text}"),
    ]
    await interaction.followup.send(
        view=C.build_v2_card("Flight Dashboard", sections, color=C.EMBED_COLOR,
                           footer="Based on the loaded flight_log cache. Run /healthcheck if data appears incomplete."),
        ephemeral=True,
    )

@C.client.tree.command(name="staff_analytics", description="[Managers] Show aggregate staff participation analytics for the last 30 days.")
async def staff_analytics_cmd(interaction: discord.Interaction):
    if interaction.guild_id != C.STAFF_GUILD_ID or not _is_staff_manager(interaction.user):
        return await _send_ops_error(interaction, "Access denied", "This command is available to staff managers in the staff server only.")
    await interaction.response.defer(ephemeral=True)
    cutoff = datetime.datetime.now(C.JST).timestamp() - 30 * 24 * 3600
    unique_flights = set()
    staff_counts = {}
    total_recent_logs = 0
    errors = []

    cutoff_dt = datetime.datetime.fromtimestamp(cutoff, tz=datetime.timezone.utc)



    async def _read_analytics_channel(channel_id):
        channel = C.client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await C.client.fetch_channel(channel_id)
            except Exception as exc:
                print(f"[STAFF ANALYTICS] Could not access channel {channel_id}: {exc}")
                return [], f"A log channel could not be accessed ({channel_id})."
        if not hasattr(channel, "history"):
            return [], f"Configured log target {channel_id} does not support message history."
        found = []
        try:
            async for message in channel.history(limit=1000, after=cutoff_dt):
                parsed = C.parse_log_message(message)
                if not parsed or (_safe_timestamp(parsed.get("timestamp")) or 0) < cutoff:
                    continue
                found.append(parsed)
        except Exception as exc:
            print(f"[STAFF ANALYTICS] Failed reading channel {channel_id}: {exc}")
            return [], f"A log channel could not be read ({channel_id})."
        return found, None

    channel_results = await asyncio.gather(
        _read_analytics_channel(C.FLIGHT_LOG_HISTORY_CHANNEL_ID),
        _read_analytics_channel(C.MANUAL_LOG_CHANNEL_ID),
    )

    for found, err in channel_results:
        if err:
            errors.append(err)
        for parsed in found:
            total_recent_logs += 1
            flight_code = str(parsed.get("flight_code") or "Unknown")
            unique_flights.add(flight_code)
            participants = parsed.get("participants", {})
            if not isinstance(participants, dict):
                continue
            host_id = parsed.get("host_id")
            try:
                host_id = int(host_id) if host_id is not None else None
            except (TypeError, ValueError):
                host_id = None
            for raw_uid, role in participants.items():
                try:
                    uid = int(raw_uid)
                except (TypeError, ValueError):
                    continue
                if uid == host_id:
                    continue
                entry = staff_counts.setdefault(uid, {"count": 0, "roles": {}})
                entry["count"] += 1
                department = C.role_to_department(role) or "Unknown"
                entry["roles"][department] = entry["roles"].get(department, 0) + 1

    ranked = sorted(staff_counts.items(), key=lambda item: item[1]["count"], reverse=True)[:10]
    ranking_lines = [f"{rank}. <@{uid}> — **{stats['count']}** participations" for rank, (uid, stats) in enumerate(ranked, 1)]
    ranking_text = "\n".join(ranking_lines) if ranking_lines else "No participation records were found for this period."
    department_totals = {}
    for stats in staff_counts.values():
        for department, count in stats["roles"].items():
            department_totals[department] = department_totals.get(department, 0) + count
    department_lines = [f"{name}: {count}" for name, count in sorted(department_totals.items(), key=lambda item: item[1], reverse=True)]
    sections = [
        ("Reporting period", "Last 30 days"),
        ("Summary", f"Unique flights: {len(unique_flights)}\nLog messages counted: {total_recent_logs}\nStaff members counted: {len(staff_counts)}"),
        ("Most active staff", ranking_text),
        ("Participation by department", "\n".join(department_lines) if department_lines else "No department data available."),
    ]
    if errors:
        sections.append(("Data warnings", "\n".join(errors)))
    await interaction.followup.send(
        view=C.build_v2_card("Staff Analytics", sections, color=C.EMBED_COLOR,
                           footer="Aggregate staff view. Use /staff_profile for an individual profile and role breakdown."),
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )

async def _prune_pre_restore_backups(keep: int = 10):
    try:
        channel = C.client.get_channel(C.FLIGHT_LOG_CHANNEL_ID) or await C.client.fetch_channel(C.FLIGHT_LOG_CHANNEL_ID)
        snaps = []
        async for message in channel.history(limit=200):
            if message.author == C.client.user and any(re.fullmatch(r"flight_log_pre_restore_\d+\.json", a.filename) for a in message.attachments):
                snaps.append(message)
        snaps.sort(key=lambda m: m.created_at, reverse=True)
        for old in snaps[keep:]:
            try:
                await old.delete()
            except Exception as e:
                print(f"[RESTORE] Could not delete an old pre-restore snapshot: {e}")
    except Exception as e:
        print(f"[RESTORE] Snapshot cleanup skipped: {e}")

class FlightBackupRestoreView(discord.ui.LayoutView):
    def __init__(self, invoking_user_id: int, candidate_data: list, preview_text: str):
        super().__init__(timeout=120)
        self.invoking_user_id = invoking_user_id
        self.candidate_data = copy.deepcopy(candidate_data)
        self.completed = False
        self.preview_text = preview_text
        self.status_text = None
        self._build()

    def _build(self):
        self.clear_items()
        body = self.status_text or self.preview_text
        restore_children = [discord.ui.TextDisplay("# Flight Data Restore"),
                            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                            discord.ui.TextDisplay("**Review**"),
                            discord.ui.TextDisplay(C._component_text(body))]
        restore_children.extend([discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                                 discord.ui.TextDisplay("-# No data changes are made until Confirm restore is selected." if not self.completed else "-# Restore operation closed.")])
        self.add_item(discord.ui.Container(*restore_children, accent_color=0xB87924 if not self.completed else C.EMBED_COLOR))
        if not self.completed:
            row = discord.ui.ActionRow()
            self.confirm_button = discord.ui.Button(label="Confirm restore", style=discord.ButtonStyle.danger, custom_id="v16_restore_confirm")
            self.confirm_button.callback = self.confirm_restore
            self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="v16_restore_cancel")
            self.cancel_button.callback = self.cancel_restore
            row.add_item(self.confirm_button)
            row.add_item(self.cancel_button)
            self.add_item(row)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoking_user_id or not _is_staff_manager(interaction.user):
            await interaction.response.send_message(
                view=C.build_v2_card("Access denied", [(None, "Only the staff manager who started this restore can confirm or cancel it.")], color=0xB23B3B),
                ephemeral=True,
            )
            return False
        return True

    async def confirm_restore(self, interaction: discord.Interaction):
        if self.completed:
            return await _send_ops_error(interaction, "Restore already closed", "This restore request has already been processed.")
        await interaction.response.defer(ephemeral=True)
        if C.FLIGHT_LOG_CHANNEL_ID in C.LOAD_UNSAFE_CHANNELS:
            return await interaction.followup.send(view=C.build_v2_card("Restore blocked", [(None, "Flight data did not load safely. Run /healthcheck before restoring.")], color=0xB23B3B), ephemeral=True)
        if C.global_json_lock is None:
            return await interaction.followup.send(view=C.build_v2_card("Restore unavailable", [(None, "The data lock is not initialized. Check the bot startup state.")], color=0xB23B3B), ephemeral=True)

        async with C.global_json_lock:
            current = copy.deepcopy(C.FLIGHT_LOG_CACHE)

            pre_restore_name = f"flight_log_pre_restore_{int(datetime.datetime.now(C.JST).timestamp() * 1000000)}.json"
            if not await C.save_json_to_channel(C.FLIGHT_LOG_CHANNEL_ID, current, pre_restore_name):
                return await interaction.followup.send(view=C.build_v2_card("Restore aborted", [(None, "The pre-restore backup could not be saved. No data was changed.")], color=0xB23B3B), ephemeral=True)
            C.FLIGHT_LOG_CACHE = copy.deepcopy(self.candidate_data)
            C.global_db_dirty = True
            if not await C.save_json_to_channel(C.FLIGHT_LOG_CHANNEL_ID, C.FLIGHT_LOG_CACHE, "flight_log.json"):
                C.FLIGHT_LOG_CACHE = current
                C.global_db_dirty = True
                return await interaction.followup.send(view=C.build_v2_card("Restore failed", [(None, "The restored data could not be saved. In-memory data has been returned to its previous state; the pre-restore backup remains available.")], color=0xB23B3B), ephemeral=True)
            C.global_db_dirty = False
            self.completed = True
            self.status_text = f"Restore completed successfully.\nRecords restored: **{len(self.candidate_data)}**\nPre-restore backup: `{pre_restore_name}`"
            self._build()
            try:
                await interaction.edit_original_response(view=self)
            except Exception as exc:
                print(f"[RESTORE] Could not update confirmation view: {exc}")

        await _prune_pre_restore_backups(keep=10)
        try:
            channel = C.client.get_channel(C.AUDIT_LOG_CHANNEL_ID) or await C.client.fetch_channel(C.AUDIT_LOG_CHANNEL_ID)
            await channel.send(
                f"Flight data restore completed by {interaction.user.id}; records={len(self.candidate_data)}.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            print(f"[RESTORE] Restore succeeded but audit logging failed: {exc}")
        await interaction.followup.send(view=C.build_v2_card("Restore complete", [(None, f"Restored {len(self.candidate_data)} flight records.\nPre-restore backup: `{pre_restore_name}`")], color=C.EMBED_COLOR), ephemeral=True)

    async def cancel_restore(self, interaction: discord.Interaction):
        self.completed = True
        self.status_text = "Restore cancelled. No data was changed."
        self._build()
        await interaction.response.edit_message(view=self)

@C.client.tree.command(name="restore", description="[Managers] Preview and restore flight_log.json from a backup message.")
@app_commands.describe(backup_message_id="Message ID of an older flight_log.json backup in the backup channel")
async def restore_cmd(interaction: discord.Interaction, backup_message_id: str):
    if interaction.guild_id != C.STAFF_GUILD_ID or not _is_staff_manager(interaction.user):
        return await _send_ops_error(interaction, "Access denied", "This command is available to staff managers in the staff server only.")
    if not backup_message_id.isdigit():
        return await _send_ops_error(interaction, "Invalid message ID", "Enter a numeric Discord message ID.")
    await interaction.response.defer(ephemeral=True)
    channel = C.client.get_channel(C.FLIGHT_LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await C.client.fetch_channel(C.FLIGHT_LOG_CHANNEL_ID)
        except Exception:
            return await interaction.followup.send(view=C.build_v2_card("Backup unavailable", [(None, "The flight backup channel could not be accessed.")], color=0xB23B3B), ephemeral=True)
    try:
        message = await channel.fetch_message(int(backup_message_id))
    except Exception:
        return await interaction.followup.send(view=C.build_v2_card("Backup not found", [(None, "The selected message could not be retrieved. Check the message ID and channel permissions.")], color=0xB23B3B), ephemeral=True)
    backup_attachment = next(
        (attachment for attachment in message.attachments
         if attachment.filename == "flight_log.json"
         or re.fullmatch(r"flight_log_pre_restore_\d+\.json", attachment.filename)),
        None,
    )
    if message.author != C.client.user or backup_attachment is None:
        return await interaction.followup.send(view=C.build_v2_card("Invalid backup", [(None, "The selected message is not a bot-created flight_log.json or pre-restore backup in the configured backup channel.")], color=0xB23B3B), ephemeral=True)
    attachment = backup_attachment
    if attachment.size > 15 * 1024 * 1024:
        return await interaction.followup.send(view=C.build_v2_card("Restore blocked", [(None, "The selected backup exceeds the 15 MiB safety limit.")], color=0xB23B3B), ephemeral=True)
    try:
        parsed = json.loads((await attachment.read()).decode("utf-8"))
    except Exception as exc:
        print(f"[RESTORE] Could not parse backup message {message.id}: {exc}")
        return await interaction.followup.send(view=C.build_v2_card("Invalid backup data", [(None, "The selected backup JSON could not be read.")], color=0xB23B3B), ephemeral=True)
    if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
        return await interaction.followup.send(view=C.build_v2_card("Invalid backup format", [(None, "Only a JSON array of flight records can be restored.")], color=0xB23B3B), ephemeral=True)
    if len(parsed) > 10000:
        return await interaction.followup.send(view=C.build_v2_card("Restore blocked", [(None, "The backup exceeds the safety limit of 10,000 records.")], color=0xB23B3B), ephemeral=True)
    candidate = copy.deepcopy(parsed)
    try:
        for record in candidate:
            C.migrate_flight_record(record)
    except Exception as exc:
        print(f"[RESTORE] Migration failed for backup message {message.id}: {exc}")
        return await interaction.followup.send(view=C.build_v2_card("Backup migration failed", [(None, "The selected backup could not be converted to the current record format. No data was changed.")], color=0xB23B3B), ephemeral=True)

    preview_text = (
        f"Source message: `{message.id}`\n"
        f"Backup created: <t:{int(message.created_at.timestamp())}:F>\n"
        f"Records to restore: **{len(candidate)}**\n\n"
        "Confirm only if this is the intended backup. The current data will be backed up before replacement."
    )
    view = FlightBackupRestoreView(interaction.user.id, candidate, preview_text)
    await interaction.followup.send(view=view, ephemeral=True)

class LeaderboardView(discord.ui.View):
    def __init__(self, ranked_list, title_period, total_flights, sort_order, my_rank_info, invoking_user=None):
        super().__init__(timeout=300)
        self.ranked_list = ranked_list
        self.title_period = title_period
        self.total_flights = total_flights
        self.sort_order = sort_order
        self.my_rank_info = my_rank_info
        self.invoking_user = invoking_user
        
        self.current_page = 0
        self.items_per_page = 15
        self.max_page = max(0, (len(ranked_list) - 1) // self.items_per_page)
        
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:

        if self.invoking_user and interaction.user.id != self.invoking_user.id:
            await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Only the person who ran this command can use these controls.')]))
            return False
        return True

    def update_buttons(self):
        for child in self.children:
            if child.custom_id == "lb_prev":
                child.disabled = (self.current_page == 0)
            elif child.custom_id == "lb_next":
                child.disabled = (self.current_page == self.max_page)

    def generate_embed(self):
        desc = f"**Total Flights in {self.title_period}:** {self.total_flights}\n"
        desc += "━━━━━━━━━━━━━━━━━━━━\n"
        desc += f"{self.my_rank_info}\n"
        desc += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_items = self.ranked_list[start_idx:end_idx]
        
        if not current_items:
            desc += "*No flight records found.*\n"
        else:
            medals = {1: "**1st**", 2: "**2nd**", 3: "**3rd**"}
            for item in current_items:
                rank = item["rank"]
                uid = item["uid"]
                count = item["count"]
                

                rank_icon = medals.get(rank, f"**#{rank}**")
                
                if rank == 1:
                    desc += f"{rank_icon} <@{uid}> : **{count}** Flights\n"
                else:
                    desc += f"{rank_icon} <@{uid}> : **{count}** Flights\n"
        
        title_prefix = "Worst" if self.sort_order == "worst" else "Top"
        embed_color = 0xFFD700 if self.sort_order == "top" else 0x8B0000
        
        embed = discord.Embed(
            title=f"{title_prefix} Flight Leaderboard ({self.current_page + 1}/{self.max_page + 1})",
            description=desc,
            color=embed_color
        )
        embed.set_footer(text="Flight Hub")
        return embed

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, custom_id="lb_prev")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="lb_next")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

@C.client.tree.command(name="leaderboard", description="Show the staff flight participation leaderboard.")
@app_commands.describe(
    period_type="Aggregation period (monthly or yearly)",
    period="Target month or year (monthly: YYYY-MM, yearly: YYYY). Defaults to the current period.",
    sort_order="Sort order (top or worst)"
)
@app_commands.choices(
    period_type=[
        app_commands.Choice(name="Monthly", value="monthly"),
        app_commands.Choice(name="Yearly", value="yearly")
    ],
    sort_order=[
        app_commands.Choice(name="Top", value="top"),
        app_commands.Choice(name="Worst", value="worst")
    ]
)
@app_commands.autocomplete(period=C.year_month_autocomplete)
async def leaderboard_cmd(interaction: discord.Interaction, period_type: str = "monthly", period: str = None, sort_order: str = "top"):
    if interaction.guild_id != C.STAFF_GUILD_ID:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This command can only be used in the staff server.')]))


    await interaction.response.defer(ephemeral=False)

    jst_now = datetime.datetime.now(C.JST)
    

    if period_type == "monthly":
        if period:
            try:
                target_year, target_month = map(int, period.split("-"))
            except:
                target_year, target_month = jst_now.year, jst_now.month
        else:
            target_year, target_month = jst_now.year, jst_now.month

        start_date = datetime.datetime(target_year, target_month, 1, tzinfo=C.JST)
        _, last_day = calendar.monthrange(target_year, target_month)
        end_date = datetime.datetime(target_year, target_month, last_day, 23, 59, 59, tzinfo=C.JST)
        title_period = f"{target_year}/{target_month:02d}"
    else:

        if period:
            try:
                target_year = int(period[:4])
            except:
                target_year = jst_now.year
        else:
            target_year = jst_now.year
            
        start_date = datetime.datetime(target_year, 1, 1, tzinfo=C.JST)
        end_date = datetime.datetime(target_year, 12, 31, 23, 59, 59, tzinfo=C.JST)
        title_period = f"{target_year}"

    start_utc = start_date.astimezone(datetime.timezone.utc)
    end_utc = end_date.astimezone(datetime.timezone.utc)

    user_counts = {}
    unique_flights = set()
    channels_to_check = [C.FLIGHT_LOG_HISTORY_CHANNEL_ID, C.MANUAL_LOG_CHANNEL_ID]


    fetch_limit = 5000 if period_type == "yearly" else 2000

    for ch_id in channels_to_check:
        ch = C.client.get_channel(ch_id)
        if not ch: continue
        try:
            async for msg in ch.history(limit=fetch_limit, after=start_utc, before=end_utc):
                parsed = C.parse_log_message(msg)
                if parsed:
                    unique_flights.add(parsed["flight_code"])
                    for uid in parsed["participants"]:
                        user_counts[uid] = user_counts.get(uid, 0) + 1
        except Exception as e:
            print(f"Leaderboard fetch error: {e}")

    total_flights = len(unique_flights)


    sorted_users_desc = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)


    ranked_list = []
    current_rank = 0
    previous_count = -1
    
    for uid, count in sorted_users_desc:

        if count != previous_count:
            current_rank += 1
            
        ranked_list.append({"uid": uid, "count": count, "rank": current_rank})
        previous_count = count


    my_id = interaction.user.id
    my_rank_info = "**Your Rank:** Unranked (0 Flights)"
    for item in ranked_list:
        if item["uid"] == my_id:
            my_rank_info = f"**Your Rank:** #{item['rank']} ({item['count']} Flights)"
            break


    if sort_order == "worst":
        ranked_list.reverse()


    view = LeaderboardView(ranked_list, title_period, total_flights, sort_order, my_rank_info, invoking_user=interaction.user)
    

    if not ranked_list:
        embed = discord.Embed(
            title="Flight Participation Leaderboard",
            description=f"**Total Flights in {title_period}:** {total_flights}\n━━━━━━━━━━━━━━━━━━━━\n{my_rank_info}\n━━━━━━━━━━━━━━━━━━━━\n\n*No flight records found for this period.*",
            color=0xFFD700
        )
        return await interaction.followup.send(view=C.embed_to_v2_layout(embed, content=None))
        
    await interaction.followup.send(embed=view.generate_embed(), view=view)

def _build_bar_chart(labels: list, values: list, title: str, ylabel: str, color: str = "#2C5F8A") -> io.BytesIO:
    C._apply_chart_style()

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=180)
    fig.patch.set_facecolor("#F7F8FA")
    ax.set_facecolor("#F7F8FA")


    pairs = sorted(zip(labels, values), key=lambda x: x[1])
    sorted_labels = [p[0] for p in pairs]
    sorted_values = [p[1] for p in pairs]

    n = len(sorted_values)
    cmap = plt.get_cmap("Blues")
    bar_colors = [cmap(0.45 + 0.5 * (i / max(n - 1, 1))) for i in range(n)]

    bars = ax.barh(sorted_labels, sorted_values, color=bar_colors, height=0.62, edgecolor="none", zorder=3)

    ax.set_title(title, fontsize=15, fontweight="bold", color="#1B2733", pad=14, loc="left")
    ax.set_xlabel(ylabel, fontsize=10, color="#5A6472")
    ax.tick_params(axis="y", labelsize=10.5, colors="#1B2733")
    ax.tick_params(axis="x", labelsize=9, colors="#5A6472")

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#D9DEE4")

    ax.grid(axis="x", linestyle="-", linewidth=0.7, color="#E3E7EC", zorder=0)
    ax.set_axisbelow(True)

    max_val = max(sorted_values) if sorted_values else 1
    for bar, val in zip(bars, sorted_values):
        ax.text(bar.get_width() + max_val * 0.015, bar.get_y() + bar.get_height() / 2,
                 f"{val:g}", va="center", ha="left", fontsize=9.5, color="#1B2733", fontweight="normal")

    ax.set_xlim(0, max_val * 1.18 if max_val > 0 else 1)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf

def _build_line_chart(x_labels: list, values: list, title: str, ylabel: str, color: str = "#2C5F8A") -> io.BytesIO:
    C._apply_chart_style()

    fig, ax = plt.subplots(figsize=(9.5, 5), dpi=180)
    fig.patch.set_facecolor("#F7F8FA")
    ax.set_facecolor("#F7F8FA")

    ax.plot(x_labels, values, marker="o", markersize=6, color=color, linewidth=2.4,
            markerfacecolor="white", markeredgecolor=color, markeredgewidth=1.8, zorder=3)
    ax.fill_between(range(len(x_labels)), values, color=color, alpha=0.12, zorder=2)

    ax.set_title(title, fontsize=15, fontweight="bold", color="#1B2733", pad=14, loc="left")
    ax.set_ylabel(ylabel, fontsize=10, color="#5A6472")
    ax.tick_params(axis="x", labelsize=9.5, colors="#5A6472")
    ax.tick_params(axis="y", labelsize=9.5, colors="#5A6472")

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#D9DEE4")
    ax.spines["bottom"].set_color("#D9DEE4")

    ax.grid(axis="y", linestyle="-", linewidth=0.7, color="#E3E7EC", zorder=0)
    ax.set_axisbelow(True)

    for x, val in enumerate(values):
        ax.annotate(f"{val:g}", (x, val), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=9, color="#1B2733")

    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf

@C.client.tree.command(name="flight_stats_graph", description="[Manager] Show flight statistics as a graph.")
@app_commands.describe(
    graph_type="Type of graph to display",
    months="Number of past months to include (trend graph only, default 6)"
)
@app_commands.choices(
    graph_type=[
        app_commands.Choice(name="Top Participants", value="top_users"),
        app_commands.Choice(name="Monthly Trend", value="monthly_trend"),
        app_commands.Choice(name="Top Routes", value="top_routes"),
    ]
)
async def flight_stats_graph_cmd(interaction: discord.Interaction, graph_type: str, months: int = 6):
    if interaction.guild_id != C.STAFF_GUILD_ID:
        return await interaction.response.send_message(view=C.embed_to_v2_layout(C.create_info_embed('Error', 'This command can only be used in the staff server.', discord.Color.red()), content=None), ephemeral=True)
    if C.LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
        return await interaction.response.send_message(view=C.embed_to_v2_layout(C.create_info_embed('Error', 'You do not have permission to use this command.', discord.Color.red()), content=None), ephemeral=True)

    await interaction.response.defer(ephemeral=False)

    months = max(1, min(months, 12))
    jst_now = datetime.datetime.now(C.JST)
    channels_to_check = [C.FLIGHT_LOG_HISTORY_CHANNEL_ID, C.MANUAL_LOG_CHANNEL_ID]

    try:
        if graph_type == "top_users":
            user_counts = {}
            month_ago = (jst_now - datetime.timedelta(days=30)).astimezone(datetime.timezone.utc)
            for ch_id in channels_to_check:
                ch = C.client.get_channel(ch_id)
                if not ch: continue
                async for msg in ch.history(limit=2000, after=month_ago):
                    parsed = C.parse_log_message(msg)
                    if parsed:
                        for uid in parsed["participants"]:
                            user_counts[uid] = user_counts.get(uid, 0) + 1

            top = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if not top:
                return await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('No Data', 'No flight records found for the last 30 days.', discord.Color.orange()), content=None))

            labels = []
            for uid, _ in top:
                member = interaction.guild.get_member(uid)
                labels.append(member.display_name if member else str(uid))
            values = [c for _, c in top]




            buf = await asyncio.to_thread(_build_bar_chart, labels, values, "Top Participants (Last 30 Days)", "Flights")
            file = discord.File(buf, filename="top_users.png")
            embed = discord.Embed(title="Top Participants (Last 30 Days)", color=C.EMBED_COLOR)
            embed.set_image(url="attachment://top_users.png")
            await interaction.followup.send(view=C.embed_to_v2_layout(embed, content=None), file=file)

        elif graph_type == "monthly_trend":
            monthly_counts = {}
            oldest = (jst_now.replace(day=1) - datetime.timedelta(days=31 * (months - 1)))
            start_utc = datetime.datetime(oldest.year, oldest.month, 1, tzinfo=C.JST).astimezone(datetime.timezone.utc)

            for ch_id in channels_to_check:
                ch = C.client.get_channel(ch_id)
                if not ch: continue
                async for msg in ch.history(limit=5000, after=start_utc):
                    parsed = C.parse_log_message(msg)
                    if parsed:
                        dt_jst = datetime.datetime.fromtimestamp(parsed["timestamp"], tz=datetime.timezone.utc).astimezone(C.JST)
                        key = f"{dt_jst.year}-{dt_jst.month:02d}"
                        monthly_counts.setdefault(key, set()).add(parsed["flight_code"])


            labels, values = [], []
            cursor = oldest.replace(day=1)
            for _ in range(months):
                key = f"{cursor.year}-{cursor.month:02d}"
                labels.append(key)
                values.append(len(monthly_counts.get(key, set())))

                if cursor.month == 12:
                    cursor = cursor.replace(year=cursor.year + 1, month=1)
                else:
                    cursor = cursor.replace(month=cursor.month + 1)


            buf = await asyncio.to_thread(_build_line_chart, labels, values, f"Monthly Flight Trend (Last {months} Months)", "Flights")
            file = discord.File(buf, filename="monthly_trend.png")
            embed = discord.Embed(title="Monthly Flight Trend", color=C.EMBED_COLOR)
            embed.set_image(url="attachment://monthly_trend.png")
            await interaction.followup.send(view=C.embed_to_v2_layout(embed, content=None), file=file)

        elif graph_type == "top_routes":
            route_counts = {}
            month_ago = (jst_now - datetime.timedelta(days=30)).astimezone(datetime.timezone.utc)
            for ch_id in channels_to_check:
                ch = C.client.get_channel(ch_id)
                if not ch: continue
                async for msg in ch.history(limit=2000, after=month_ago):
                    parsed = C.parse_log_message(msg)
                    if parsed and parsed["flight_code"] != "Unknown":
                        route_counts[parsed["flight_code"]] = route_counts.get(parsed["flight_code"], 0) + 1

            top = sorted(route_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if not top:
                return await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('No Data', 'No flight records found for the last 30 days.', discord.Color.orange()), content=None))

            labels = [code for code, _ in top]
            values = [c for _, c in top]


            buf = await asyncio.to_thread(_build_bar_chart, labels, values, "Top Routes (Last 30 Days)", "Flights", color="#8B5E3C")
            file = discord.File(buf, filename="top_routes.png")
            embed = discord.Embed(title="Top Routes (Last 30 Days)", color=C.EMBED_COLOR)
            embed.set_image(url="attachment://top_routes.png")
            await interaction.followup.send(view=C.embed_to_v2_layout(embed, content=None), file=file)

        await C.log_audit(
            actor=interaction.user,
            action="Stats Graph Generated",
            detail=f"Type: {graph_type}"
        )

    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'An error occurred while generating the graph: {e}', discord.Color.red()), content=None))

@C.client.tree.command(name="cancel", description="Announce a flight cancellation.")
@app_commands.describe(flight_code="Select Flight Code", reason="Reason for cancellation")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def cancel_flight(interaction: discord.Interaction, flight_code: str, reason: str):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'Flight `{flight_code}` not found.', discord.Color.red()), content=None), ephemeral=True)

    airline = flight.get('airline', 'Airline')
    destination = flight.get('destination', 'Unknown')

    embed = discord.Embed(
        title=f"{airline} | {flight_code} - CANCELED",
        description=(
            f"We sincerely apologize. Flight **{flight_code}** to {destination} has been **cancelled** for the following reason.\n"
            f"We deeply apologize to inform you that flight **{flight_code}** to *{destination}* has been **canceled**.\n\n"
            f"**Reason:**\n{reason}\n\n"
            f"We apologize for any inconvenience this may cause and appreciate your understanding.\n"
            f"We sincerely apologize for the major inconvenience to our customers."
        ),
        color=discord.Color.red()
    )
    embed.set_author(name="Travel Update")

    if flight.get("event_url"):
        try:
            event_id = int(flight["event_url"].split("/")[-1])

            target_guild_id = C.STAFF_GUILD_ID if (flight.get("is_gamenight") or flight.get("is_private")) else C.CUSTOMER_GUILD_ID
            target_guild = C.client.get_guild(target_guild_id)
            if target_guild:
                event = await target_guild.fetch_scheduled_event(event_id)
                await event.delete()
        except:
            pass


    cancel_msg = None
    if not flight.get("is_private"):
        cancel_msg = await C.client.get_channel(C.CUSTOMER_CHANNEL_ID).send(embed=embed)

    try:
        if s_ch := C.client.get_channel(flight["staff_channel_id"]):
            await (await s_ch.fetch_message(flight["staff_message_id"])).delete()
    except:
        pass

    try:
        if flight.get("customer_message_id") and (c_ch := C.client.get_channel(flight["customer_channel_id"])):
            await (await c_ch.fetch_message(flight["customer_message_id"])).delete()
    except:
        pass

    if flight.get("is_custom"):
        try:
            if src_ch := C.client.get_channel(flight["source_channel_id"]):
                await (await src_ch.fetch_message(flight["source_message_id"])).delete()
        except:
            pass

    async with C.global_json_lock:
        target_idx = next(
            (i for i, f in enumerate(C.FLIGHT_LOG_CACHE) if f["flight_code"] == flight_code), -1)
        if target_idx != -1:
            flight = C.FLIGHT_LOG_CACHE[target_idx]
            if cancel_msg:
                flight["cancel_message_id"] = cancel_msg.id
            flight["end_timestamp"] = int(datetime.datetime.now().timestamp()) - 1
            flight["messages_deleted"] = True
            C.global_db_dirty = True
            


    await C.auto_publish_schedule()
    await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Cancellation announced and related data removed.')]))

@C.client.tree.command(name="briefing", description="Create a briefing sheet and assign staff.")
@app_commands.describe(
    flight_code="Select Flight Code",
    language="Briefing output language (English)",
    lounge="Lounge Availability",
    gate="Gate",
    reception_close="Reception Close (HH:MM) - Optional"
)
@app_commands.choices(
    language=[app_commands.Choice(name="English", value="EN")],
    lounge=[app_commands.Choice(name="Available", value="Available"),
            app_commands.Choice(name="Unavailable", value="Unavailable")]
)
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def briefing_command(interaction: discord.Interaction, flight_code: str, language: str, lounge: str, gate: str,
                           reception_close: str = None):
    if not C.is_event_manager_or_chief(interaction.user) and not (C.TEST_MODE and C._test_admin_allowed(interaction.user)):
        return await interaction.response.send_message(ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), view=C.build_v2_card('Notice', [(None, 'No permission.')]))

    if C.TEST_MODE:
        flight = next((f for f in C.TEST_FLIGHT_CACHE if f["flight_code"] == flight_code), None)
        if not flight:
            await C._test_mode_record("briefing", interaction.user.id, "FAIL", {"flight_code": flight_code, "error": "test flight not found"})
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card(
                "Test flight not found", [(None, "Please create a test flight with `/create_flight` first.")]))
        if flight["end_timestamp"] < datetime.datetime.now().timestamp():
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This test flight has already ended.')]))
    else:
        flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Flight not found.')]))
    if flight["end_timestamp"] < datetime.datetime.now().timestamp():
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This flight has already ended.')]))

    start_ts = flight["start_timestamp"]
    if not reception_close:


        try:
            host_offset = C.parse_timezone_offset(flight.get("host_timezone_str", "GMT+9"))
        except Exception:
            host_offset = 9
        host_tz = datetime.timezone(datetime.timedelta(hours=host_offset))
        start_dt = datetime.datetime.fromtimestamp(start_ts, tz=host_tz)
        reception_close = (start_dt + datetime.timedelta(minutes=10)).strftime("%H:%M")

    state = {"gate": gate, "lounge": lounge, "reception_end": reception_close}



    if C.TEST_MODE and not flight.get("briefing_sent"):
        staff_guild = interaction.guild
        eligible = []
        test_role_ids = {C.ROLE_FLIGHT_OPS, C.ROLE_CABIN_CREWS, C.ROLE_GROUND_OPS}
        if isinstance(C.ROLE_BUS_DRIVERS, (tuple, list, set)):
            test_role_ids.update(C.ROLE_BUS_DRIVERS)
        else:
            test_role_ids.add(C.ROLE_BUS_DRIVERS)
        if staff_guild:
            for member in staff_guild.members:
                if member.bot or member.id == flight.get("host_id"):
                    continue
                if any(role.id in test_role_ids for role in member.roles):
                    eligible.append(member)
        random.shuffle(eligible)
        sample_size = min(len(eligible), 30)
        flight["accepted_users"] = [m.id for m in eligible[:sample_size]]
        flight["test_random_staff_selection"] = True
        flight["test_random_staff_count"] = sample_size
        flight["test_random_staff_ids"] = flight["accepted_users"][:]
        await C._test_mode_save()

    is_edit = flight.get("briefing_sent", False)
    assignments = copy.deepcopy(flight.get("briefing_assignments")) if is_edit else None
    if is_edit and not assignments:


        return await interaction.response.send_message(ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), view=C.build_v2_card(
            'Notice', [(None, 'No briefing assignment data was found for this flight, so the process was stopped to prevent overwriting.\n'
                              'If it has already been sent, please check the content instead of using `/edit_briefing`.')]))


    view = C.BriefingSetupView(flight, state, language, interaction.guild, assignments=assignments, is_edit=is_edit)
    if C.TEST_MODE:
        setattr(view, "_flighthub_test_mode", True)
        if not is_edit:

            try:
                view.auto_fill_unassigned(interaction.guild)
                view.ensure_minimum_coverage(interaction.guild)
                view._autofill_pending = False
                await C._test_mode_save()
            except Exception as exc:
                await C._test_mode_record("briefing", interaction.user.id, "FAIL", {"stage": "random_staff_assignment", "error": str(exc)})
    msg_text = ("[TEST MODE — NOT SENT TO STAFF OR CUSTOMERS]\n" if C.TEST_MODE else "") + ("Please assign the staff.\n1. Select a position.\n2. Select a user.\n3. Click Review & Confirm.\n"
                "Staff you did not select are assigned automatically when you click Review & Confirm.\n"
                "(Staff not selected will be assigned automatically when you press Proceed to Confirm)")
    if is_edit:
        msg_text = ("[TEST MODE — NOT SENT TO STAFF OR CUSTOMERS]\n" if C.TEST_MODE else "") + "**Edit Mode**"

    await interaction.response.send_message(content=msg_text, embed=view.generate_embed(), view=view, ephemeral=True,
                                            allowed_mentions=discord.AllowedMentions.none())

@C.client.tree.command(name="edit_briefing", description="Edit an already sent briefing sheet.")
@app_commands.describe(flight_code="Select Flight Code")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def edit_briefing_cmd(interaction: discord.Interaction, flight_code: str):
    if not C.is_event_manager_or_chief(interaction.user) and not (C.TEST_MODE and C._test_admin_allowed(interaction.user)):
        return await interaction.response.send_message(ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), view=C.build_v2_card('Notice', [(None, 'No permission.')]))

    source_flights = C.TEST_FLIGHT_CACHE if C.TEST_MODE else C.FLIGHT_LOG_CACHE
    flight = next((f for f in source_flights if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Flight not found.')]))
    if flight["end_timestamp"] < datetime.datetime.now().timestamp():
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This flight has already ended. Cannot edit.')]))
    if not flight.get("briefing_sent"):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Briefing sheet not sent yet. Use `/briefing` first.')]))

    state = flight.get("briefing_state")
    lang = flight.get("briefing_lang", "EN")
    assignments = copy.deepcopy(flight.get("briefing_assignments"))
    if not assignments:

        return await interaction.response.send_message(ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), view=C.build_v2_card(
            'Notice', [(None, 'There is no saved assignment data for this flight, so editing was stopped to avoid accidentally deleting all staff.\n'
                              'Please recreate it with `/briefing`.')]))


    view = C.BriefingSetupView(flight, state, lang, interaction.guild, assignments=assignments, is_edit=True)
    if C.TEST_MODE:
        setattr(view, "_flighthub_test_mode", True)
    await interaction.response.send_message(content=("[TEST MODE — NOT SENT TO STAFF OR CUSTOMERS]\n" if C.TEST_MODE else "") + "**Edit Mode**", embed=view.generate_embed(), view=view,
                                            ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

@C.client.tree.command(name="flight_log", description="Send a Flight-log after the flight.")
@app_commands.describe(flight_code="Select Flight Code", fc="Flight Crew Status", cc="Cabin Crew Status", gc="Ground Crew Status", bus="Bus Driver Status (only for flights using the bus service)")
@app_commands.choices(
    fc=[app_commands.Choice(name="Perfect (Check)", value=1), app_commands.Choice(name="Issues (X)", value=0)],
    cc=[app_commands.Choice(name="Perfect (Check)", value=1), app_commands.Choice(name="Issues (X)", value=0)],
    gc=[app_commands.Choice(name="Perfect (Check)", value=1), app_commands.Choice(name="Issues (X)", value=0)],
    bus=[app_commands.Choice(name="Perfect (Check)", value=1), app_commands.Choice(name="Issues (X)", value=0)]
)
@app_commands.autocomplete(flight_code=C.log_flight_autocomplete)
@C.event_manager_only
async def flight_log_cmd(interaction: discord.Interaction, flight_code: str, fc: int = None, cc: int = None, gc: int = None, bus: int = None):
    if not C.is_event_manager_or_chief(interaction.user) and not (C.TEST_MODE and C._test_admin_allowed(interaction.user)):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))

    source_flights = C.TEST_FLIGHT_CACHE if C.TEST_MODE else C.FLIGHT_LOG_CACHE
    flight = next((f for f in source_flights if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Flight not found.')]))
    if not flight.get("briefing_sent"):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Briefing sheet has not been created. Cannot generate review without assignments.')]))

    if flight.get("flight_log_sent"):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Flight-log has already been sent for this flight.')]))

    is_pure_bus = flight.get("is_bus")
    has_bus_service = flight.get("use_bus")


    if not is_pure_bus and (fc is None or cc is None):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Ratings for `fc` and `cc` are required.')]))
    if gc is None:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'A rating for `gc` is required.')]))
    if (is_pure_bus or has_bus_service) and bus is None:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This flight uses a bus, so please also enter a `bus` rating.')]))

    uses_bus = bool(is_pure_bus or has_bus_service)
    if bus is not None and not uses_bus:

        bus = None

    checks = {"fc": bool(fc) if fc is not None else False, "cc": bool(cc) if cc is not None else False, "gc": bool(gc), "bus": bool(bus) if bus is not None else None}
    

    view = C.FlightLogAbsentView(flight, checks)
    await interaction.response.send_message(
        "**[Select Absent Users]**\nIf any users did not attend, select them from the menu.\nIf no one was absent, just press Next.",
        view=view,
        ephemeral=True
    )

@C.client.tree.command(name="editflightlog", description="[Admin] Edit an already-sent Flight-log.")
@app_commands.describe(message_id="Enter the message ID of the Flight-log to edit")
@C.event_manager_only
async def editflightlog_cmd(interaction: discord.Interaction, message_id: str):
    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))

    await interaction.response.defer(ephemeral=True)

    target_msg = None
    channels_to_check = [C.FLIGHT_LOG_HISTORY_CHANNEL_ID, C.MANUAL_LOG_CHANNEL_ID]
    for ch_id in channels_to_check:
        ch = C.client.get_channel(ch_id)
        if ch:
            try:
                target_msg = await ch.fetch_message(int(message_id.strip()))
                if target_msg:
                    break
            except:
                pass

    if not target_msg:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The specified message was not found.')]))

    key_mapping = {
        "Host": "Host", "Co-host": "Co-host", "Captain": "Captain", "First Officer": "First Officer",
        "Receptionist": "Receptionist",
        "Airport Guide": "Airport Guide",
        "Gate Agent": "Gate Agent",
        "Lounge Agent": "Lounge Agent",
        "First Class": "First Class", "Business Class": "Business Class",
        "Premium Economy": "Premium Economy", "Economy Class": "Economy Class",
        "MR": "GC Supervisor(MR)", "GC Supervisor(MR)": "GC Supervisor(MR)",
        "Crew": "Ground Crew", "Ground Crew": "Ground Crew",
        "Bus Driver": "Bus Driver", "Dispatcher": "Dispatcher"
    }

    content_to_parse = target_msg.content
    if target_msg.embeds:
        for e in target_msg.embeds:
            content_to_parse += f"\n{e.title}\n{e.description}\n"
            for f in e.fields:
                content_to_parse += f"\n{f.name}\n{f.value}\n"

    flight_code = "Unknown"
    assignments = {}

    fc_match = re.search(r"(?:Flight Code:|\|)\s*\*?([^|\n]+?)\*?\s*(?:\||\n|$)", content_to_parse, re.IGNORECASE)
    if fc_match:
        flight_code = fc_match.group(1).strip().strip("*").strip()


        flight_code = re.sub(r"\s*\(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}[^)]*\)\s*$", "", flight_code).strip()

    lines = content_to_parse.split('\n')
    for line in lines:
        if "> " in line and ":" in line:
            parts = line.replace("> ", "").split(":", 1)
            if len(parts) == 2:
                raw_key = parts[0].strip()
                uids = re.findall(r'<@!?(\d+)>', parts[1])
                uids += re.findall(r'\b(\d{17,19})\b', parts[1])

                mapped_key = raw_key
                for k, v in key_mapping.items():
                    if k in raw_key:
                        mapped_key = v
                        break

                if mapped_key not in assignments:
                    assignments[mapped_key] = []

                for uid in uids:
                    uid_int = int(uid)
                    if uid_int not in assignments[mapped_key]:
                        assignments[mapped_key].append(uid_int)

    log_date_str = "Unknown"
    date_match = re.search(r"\|\s*[A-Za-z0-9]+\s*\((\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}[^)]*)\)", content_to_parse)
    if date_match:
        log_date_str = date_match.group(1).strip()
    else:
        log_date_str = f"<t:{int(target_msg.created_at.timestamp())}:D>"

    if target_msg.author == C.client.user:
        log_type = "EditLog"
        edit_msg_obj = target_msg
    else:
        log_type = "Manual"
        edit_msg_obj = None

    view = LogAssignmentView(flight_code, log_type, initial_assignments=assignments, edit_message_obj=edit_msg_obj, log_date=log_date_str)
    await interaction.followup.send(embed=view.generate_embed(), view=view, ephemeral=True)

class LogPositionSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Host", description="Flight Host")]
        for pos, desc, _ in C.POSITIONS_DATA:
            options.append(discord.SelectOption(label=pos, description=desc))
        super().__init__(placeholder="① Select Position", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):

        view = self.view
        
        view.current_position = self.values[0]
        view.refresh_ui()
        await interaction.response.edit_message(embed=view.generate_embed(), view=view)

class LogUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="② Select Staff", min_values=1, max_values=25)

    async def callback(self, interaction: discord.Interaction):

        view = self.view
        
        if not view.current_position:
            return await interaction.response.defer()
            
        selected_ids = [user.id for user in self.values]


        for pos, uids in view.assignments.items():
            if pos == view.current_position or not isinstance(uids, list):
                continue
            view.assignments[pos] = [uid for uid in uids if uid not in selected_ids]

        if view.current_position in view.assignments:
            existing_ids = view.assignments[view.current_position]
            for uid in selected_ids:
                if uid not in existing_ids:
                    existing_ids.append(uid)
        else:
            view.assignments[view.current_position] = selected_ids
            
        view.current_position = None
        view.refresh_ui()
        await interaction.response.edit_message(embed=view.generate_embed(), view=view)

class LogAssignmentView(discord.ui.View):
    def __init__(self, flight_code, log_type, initial_assignments=None, edit_message_obj=None, log_date=None):
        super().__init__(timeout=900)
        self.flight_code = flight_code
        self.log_type = log_type
        self.assignments = initial_assignments or {}
        self.edit_message_obj = edit_message_obj
        self.log_date = log_date
        self.current_position = None
        self.absent_users = []
        self.refresh_ui()

    def refresh_ui(self):
        self.clear_items()
        

        self.add_item(LogPositionSelect())
        

        user_select = LogUserSelect()
        user_select.disabled = (self.current_position is None)
        self.add_item(user_select)


        absent_select = discord.ui.UserSelect(
            placeholder="③ Select Absent Users (optional)",
            min_values=0,
            max_values=25
        )
        
        async def absent_cb(interaction: discord.Interaction):
            self.absent_users = [user.id for user in absent_select.values]
            

            for pos, uids in self.assignments.items():
                self.assignments[pos] = [uid for uid in uids if uid not in self.absent_users]
            
            self.current_position = None
            self.refresh_ui()
            await interaction.response.edit_message(embed=self.generate_embed(), view=self)
            
        absent_select.callback = absent_cb
        self.add_item(absent_select)


        btn_clear = discord.ui.Button(label="Clear Position", style=discord.ButtonStyle.danger, row=3)
        btn_clear.disabled = (self.current_position is None)
        
        async def clear_cb(interaction):
            if self.current_position in self.assignments:
                del self.assignments[self.current_position]
            self.current_position = None
            self.refresh_ui()
            await interaction.response.edit_message(embed=self.generate_embed(), view=self)
            
        btn_clear.callback = clear_cb
        self.add_item(btn_clear)

        btn_submit = discord.ui.Button(label="Submit Log", style=discord.ButtonStyle.success, row=3)
        async def submit_cb(interaction):
            await self.submit_log(interaction)
        btn_submit.callback = submit_cb
        self.add_item(btn_submit)

    def generate_embed(self):
        title = "Manual Flight Log Setup" 
        if self.log_type == "EditLog":
            title = "Edit Existing Log"
        elif self.log_type == "Backup":
            title = "Flight Backup Setup"
        
        desc = f"**Flight Code:** {self.flight_code}\n"
        if self.log_date and self.log_date != "Unknown":
            desc += f"**Date:** {self.log_date}\n"
        desc += "\n"
        
        if self.current_position:
            desc += f"Assigning for: **{self.current_position}**\n\n"

        desc += "**Assignments:**\n"
        if not self.assignments:
            desc += "No staff assigned yet."
        else:
            for pos, uids in self.assignments.items():
                if uids:
                    mentions = " ".join([f"<@{uid}>" for uid in uids])
                    desc += f"> {pos}: {mentions}\n"

        return discord.Embed(title=title, description=desc, color=0x1B3444)

    async def submit_log(self, interaction: discord.Interaction):

        if getattr(self, "_submitting", False):
            try:
                await interaction.response.send_message(
                    "This log is already being submitted. Please wait a moment.", ephemeral=True)
            except Exception:
                pass
            return
        self._submitting = True
        await interaction.response.defer()
        

        bottom_text = ""
        if self.log_type == "EditLog" and self.edit_message_obj:
            original_content = self.edit_message_obj.content
            if "----------------" in original_content:
                parts = re.split(r'-{10,}', original_content, maxsplit=1)
                if len(parts) > 1:
                    bottom_text = "\n-----------------------------------------------------------------\n" + parts[1].strip()


        def g(key, default="N/A"):
            v = self.assignments.get(key, [])
            if not v: return default
            return " ".join([f"<@{uid}>" for uid in v])


        header_title = 'Flight-log' if self.log_type == 'EditLog' else ('Manual-log' if self.log_type == 'Manual' else 'Flight Backup')
        if self.log_type == "EditLog" and self.edit_message_obj:
            if "Manual-log" in self.edit_message_obj.content:
                header_title = "Manual-log"
            elif "Flight Backup" in self.edit_message_obj.content:
                header_title = "Flight Backup"


        fc_str = self.flight_code
        if self.log_date and self.log_date != "Unknown" and not self.log_date.startswith("<t:"):
            fc_str += f" ({self.log_date})"

        content = f"**{C.EMOJI_BRAND_STR} | {fc_str} {header_title}**\n\n"

        _ftype = None
        if self.log_type == "EditLog" and self.edit_message_obj:
            _m_ft = re.search(r"Flight Type:\s*([^\n*]+)", self.edit_message_obj.content or "")
            _ftype = _m_ft.group(1).strip() if _m_ft else None
        if not _ftype:
            _fl_t = next((f for f in C.FLIGHT_LOG_CACHE if f.get("flight_code") == self.flight_code), None)
            if _fl_t is not None and not C.is_customer_flight(_fl_t):
                _ftype = ("Game Night" if _fl_t.get("is_gamenight") else "Private" if _fl_t.get("is_private") else "Test")
            elif str(self.flight_code).upper().startswith("[TEST]"):
                _ftype = "Test"
        if _ftype:
            content += f"> Flight Type: {_ftype}\n"
        content += f"**Flight Management**\n> Host: {g('Host')}\n> Co-host: {g('Co-host')}\n\n"
        content += f"**Flight Crew Department**\n> Captain: {g('Captain')}\n> First Officer: {g('First Officer')}\n\n"
        content += f"**Airport Services**\n> Receptionist: {g('Receptionist', 'Not assigned')}\n> Airport Guide: {g('Airport Guide', 'Not assigned')}\n> Gate Agent: {g('Gate Agent', 'Not assigned')}\n> Lounge Agent: {g('Lounge Agent')}\n\n"
        content += f"**Cabin Crew Department**\n> First Class: {g('First Class', 'Not assigned')}\n> Business Class: {g('Business Class', 'Not assigned')}\n> Premium Economy: {g('Premium Economy', 'Not assigned')}\n> Economy Class: {g('Economy Class', 'Not assigned')}\n\n"
        content += f"**Ground Crew Department**\n> MR: {g('GC Supervisor(MR)')}\n> Crew: {g('Ground Crew')}\n"
        
        if self.assignments.get('Bus Driver') or self.assignments.get('Dispatcher'):
            content += f"\n**Bus Driver Department**\n> Dispatcher: {g('Dispatcher')}\n> Bus Driver: {g('Bus Driver')}\n"

        if bottom_text:
            content += bottom_text


        mentions = discord.AllowedMentions.none()

        if self.log_type == "EditLog" and self.edit_message_obj:
            try:

                await self.edit_message_obj.edit(content=content, embed=None, allowed_mentions=mentions)
                await interaction.edit_original_response(content="Log edited successfully.", embed=None, view=None)
            except Exception as e:
                await interaction.edit_original_response(content=f"Edit failed: {e}", embed=None, view=None)
        else:
            ch_id = C.MANUAL_LOG_CHANNEL_ID if self.log_type == "Manual" else C.FLIGHT_LOG_HISTORY_CHANNEL_ID
            ch = interaction.client.get_channel(ch_id)
            if ch:
                await ch.send(content=content, allowed_mentions=mentions)
                await interaction.edit_original_response(content="Log submitted successfully.", embed=None, view=None)
            else:
                await interaction.edit_original_response(content="Error: Log channel not found.", embed=None, view=None)

class ManualLogInitModal(discord.ui.Modal, title="Manual Flight Log"):
    flight_code = discord.ui.TextInput(label="Flight Code", placeholder="JI123", required=True)
    log_date = discord.ui.TextInput(label="Date (YYYY-MM-DD etc.)", placeholder="2026-07-22", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        fc = self.flight_code.value.strip().upper()
        date_val = self.log_date.value.strip() if self.log_date.value else None
        view = LogAssignmentView(fc, "Manual", log_date=date_val)
        await interaction.response.send_message(embed=view.generate_embed(), view=view, ephemeral=True)

@C.client.tree.command(name="restore_from_message", description="[Admin] Force-restore flight data from a staff message ID.")
@app_commands.describe(message_id="Enter the signup message ID from the staff channel")
@C.event_manager_only
async def restore_from_message_cmd(interaction: discord.Interaction, message_id: str):
    if not C.is_chief(interaction.user):
        try:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
        except discord.NotFound:
            return


    is_timeout = False
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.NotFound:
        print("[restore_from_message] Processing timed out due to network lag, but it will continue in the background.")
        is_timeout = True


    async def send_reply(msg_text):
        if is_timeout:
            try:
                await interaction.channel.send(f"{interaction.user.mention}\n{msg_text}")
            except:
                pass
        else:
            await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, msg_text)]))

    try:
        msg_id_int = int(message_id.strip())
        s_channel = C.client.get_channel(C.STAFF_CHANNEL_ID)
        if not s_channel:
            return await send_reply("Staff channel not found.")

        try:
            msg = await s_channel.fetch_message(msg_id_int)
        except discord.NotFound:
            return await send_reply("Message not found. Please check that the ID is correct.")

        if not msg.embeds:
            return await send_reply("This message does not contain an embed.")

        embed = msg.embeds[0]


        flight_code = "Unknown"
        if embed.footer and embed.footer.text:
            match = re.search(r"Flight Code: (\w+)", embed.footer.text)
            if match:
                flight_code = match.group(1)
        if flight_code == "Unknown":
            match = re.search(r"(\w+\d+)", embed.title)
            if match:
                flight_code = match.group(1)

        origin, destination, equipment, airline = "Unknown", "Unknown", "Unknown", "Airline"
        start_ts, end_ts, staff_ts = 0, 0, 0
        host_name = ""
        accepted_names, declined_names = [], []

        for f in embed.fields:
            if "Route" in f.name:
                parts = f.value.split(" ➝ ")
                if len(parts) == 2:
                    origin, destination = parts[0].strip(), parts[1].strip()
            elif "Aircraft Equipment" in f.name or "Vehicle" in f.name or "Game" in f.name:
                equipment = f.value.strip()
            elif "Aircraft Operator" in f.name:
                airline = f.value.strip()
            elif "Host" in f.name:
                host_name = f.value.strip()
            elif "Action" in f.name:
                match = re.search(r"<t:(\d+):F>", f.value)
                if match: staff_ts = int(match.group(1))
            elif "Time" in f.name:
                match = re.search(r"<t:(\d+):F>\s*-\s*<t:(\d+):t>", f.value)
                if match:
                    start_ts, end_ts = int(match.group(1)), int(match.group(2))
            elif "Accepted" in f.name:
                if f.value and f.value != "-":
                    accepted_names = [n.strip() for n in f.value.replace(">>>", "").split("\n") if n.strip()]
            elif "Declined" in f.name:
                if f.value and f.value != "-":
                    declined_names = [n.strip() for n in f.value.replace(">>>", "").split("\n") if n.strip()]

        guild = interaction.guild
        accepted_users, declined_users = [], []
        for name in accepted_names:
            u = discord.utils.get(guild.members, display_name=name) or discord.utils.get(guild.members, name=name)
            if u: accepted_users.append(u.id)
        for name in declined_names:
            u = discord.utils.get(guild.members, display_name=name) or discord.utils.get(guild.members, name=name)
            if u: declined_users.append(u.id)

        host_id = interaction.user.id
        if host_name:
            h = discord.utils.get(guild.members, display_name=host_name) or discord.utils.get(guild.members, name=host_name)
            if h: host_id = h.id


        event_url, found_event = "", None
        c_guild = C.client.get_guild(C.CUSTOMER_GUILD_ID)
        s_guild = C.client.get_guild(C.STAFF_GUILD_ID)


        if c_guild:
            for e in await c_guild.fetch_scheduled_events():
                if flight_code in e.name or flight_code in getattr(e, 'description', ''):
                    event_url, found_event = e.url, e
                    break

        if not found_event and s_guild:
            for e in await s_guild.fetch_scheduled_events():
                if flight_code in e.name or "Game Night" in e.name:
                    event_url, found_event = e.url, e
                    break

        is_gamenight = False
        if found_event:

            start_ts = int(found_event.start_time.timestamp())
            if found_event.end_time:
                end_ts = int(found_event.end_time.timestamp())

            if "Game Night" in found_event.name or found_event.location == "Staff Game Night" or flight_code.startswith("GN_"):
                is_gamenight = True

            if found_event.location and found_event.location != "Staff Game Night":
                origin = found_event.location

            if found_event.description:
                desc = found_event.description
                if "`Destination`" in desc:
                    match = re.search(r"`Destination`\s+([^\n]+)", desc)
                    if match: destination = match.group(1).strip()
                if "`Airline`" in desc or "`Operator`" in desc:
                    match = re.search(r"`(?:Airline|Operator)`\s+([^\n]+)", desc)
                    if match: airline = match.group(1).strip()
                if "`Aircraft`" in desc or "`Vehicle`" in desc:
                    match = re.search(r"`(?:Aircraft|Vehicle)`\s+([^\n]+)", desc)
                    if match: equipment = match.group(1).strip()


        customer_msg_id = None
        if not is_gamenight:

            c_ch = C.client.get_channel(C.CUSTOMER_CHANNEL_ID)


            if c_ch is None:
                try:
                    c_ch = await C.client.fetch_channel(C.CUSTOMER_CHANNEL_ID)
                except Exception as e:
                    print(f"Failed to fetch the customer channel: {e}")


            if c_ch:

                async for cmsg in c_ch.history(limit=50):
                    if cmsg.author == C.client.user and flight_code in cmsg.content:
                        customer_msg_id = cmsg.id
                        break


        classes, color, roblox_link, src_ch, src_msg = "Economy", "1B3444", "", None, None
        if is_gamenight:
            color = "9B59B6"
        elif flight_code in C.FLIGHT_DB:
            variants = C.FLIGHT_DB[flight_code].get("variants", {})
            for k, v in variants.items():
                if k.lower() in equipment.lower():
                    classes = v.get("classes", "Economy")
                    color = v.get("color", "1B3444")
                    roblox_link = v.get("roblox_link", "")
                    src_ch = v.get("source_channel_id")
                    src_msg = v.get("source_message_id")
                    break

        restored_flight = {
            "flight_code": flight_code, "origin": origin, "destination": destination,
            "equipment": equipment, "classes": classes, "roblox_link": roblox_link,
            "airline": airline, "color": color,
            "source_channel_id": src_ch, "source_message_id": src_msg,
            "start_timestamp": start_ts, "end_timestamp": end_ts, "staff_timestamp": staff_ts,
            "event_url": event_url, "host_id": host_id,
            "staff_guild_id": C.STAFF_GUILD_ID, "staff_channel_id": C.STAFF_CHANNEL_ID,
            "staff_message_id": msg.id,
            "customer_guild_id": C.CUSTOMER_GUILD_ID, "customer_channel_id": C.CUSTOMER_CHANNEL_ID,
            "customer_message_id": customer_msg_id,
            "notify_20min_timestamp": staff_ts - 1200, "notified_20min": False,
            "accepted_users": accepted_users, "declined_users": declined_users,
            "briefing_sent": False,
            "flight_log_sent": False, "messages_deleted": False, "is_custom": False,
            "host_timezone_str": "GMT+9",
            "is_gamenight": is_gamenight, "pending_customer_msg": False
        }

        async with C.global_json_lock:
            target_idx = next((i for i, f in enumerate(C.FLIGHT_LOG_CACHE) if f["flight_code"] == flight_code), -1)
            if target_idx != -1:
                C.FLIGHT_LOG_CACHE[target_idx] = restored_flight
            else:
                C.FLIGHT_LOG_CACHE.append(restored_flight)
            C.global_db_dirty = True


        msg_text = f"** `{flight_code}` information was restored from the calendar and messages!**\n"
        if found_event:
            msg_text += f"Got the exact time from the calendar: <t:{start_ts}:F>\n"
            
        await send_reply(msg_text + "To sync more precisely, use `/update_ui`.")

    except Exception as e:
        await send_reply(f"An error occurred during restore: {e}")

@C.client.tree.command(name="backupflight", description="[Admin] Silently recreate a calendar (Discord event) that was accidentally deleted.")
@app_commands.describe(flight_code="Flight code of the event to recreate")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def backupflight_cmd(interaction: discord.Interaction, flight_code: str):
    

    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))
    
    await interaction.response.defer(ephemeral=True)


    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'No active flight `{flight_code}` was found.', discord.Color.red()), content=None), ephemeral=True)


    c_guild = C.client.get_guild(C.CUSTOMER_GUILD_ID)
    if not c_guild:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Customer server not found.')]))


    image_url, image_bytes = await C.fetch_fresh_image_info(flight.get("source_channel_id"), flight.get("source_message_id"))


    is_bus = flight.get("is_bus", False)
    airline = flight.get("airline", "Airline")
    origin = flight.get("origin", "Unknown")
    dest = flight.get("destination", "Unknown")
    equipment = flight.get("equipment", "Unknown")
    classes = flight.get("classes", "Unknown")
    host_id = flight.get("host_id")

    if is_bus:
        event_name = flight.get("event_title") or flight_code
        desc = f"`Host` <@{host_id}>\n`Server` {origin}\n> Information\n`Operator` {airline}\n`Vehicle` {equipment}"
    else:
        event_name = flight.get("event_title") or f"{flight_code} {origin}→{dest}"
        desc = f"`Host` <@{host_id}>\n`Origin` {origin}\n`Destination` {dest}\n> Information\n`Airline` {airline}\n`Aircraft` {equipment}\n`Classes` {classes}"


    pass_dt = datetime.datetime.fromtimestamp(flight["start_timestamp"], tz=datetime.timezone.utc)
    end_dt = datetime.datetime.fromtimestamp(flight["end_timestamp"], tz=datetime.timezone.utc)

    try:

        event = await c_guild.create_scheduled_event(
            name=event_name,
            description=desc,
            start_time=pass_dt,
            end_time=end_dt,
            location=origin,
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            image=image_bytes
        )


        async with C.global_json_lock:
            flight["event_url"] = event.url
            C.global_db_dirty = True
        

        

        success_embed = C.create_info_embed(
            C.EMOJI_CHECK_STR + " Backup Event Created", 
            f"Recreated the calendar (Discord event) silently.\n\n**New event link:**\n{event.url}\n\nIf needed, run `/update_ui` to update links in already-sent recruitment messages.", 
            discord.Color.green()
        )
        await interaction.followup.send(view=C.embed_to_v2_layout(success_embed, content=None), ephemeral=True)
    
    except Exception as e:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_X_STR + ' Creation Failed', f'Failed to create the calendar: {e}', discord.Color.red()), content=None), ephemeral=True)

@C.client.tree.command(name="restart", description="[Admin] Restart the bot (use when it is misbehaving).")
async def restart_cmd(interaction: discord.Interaction):

    if getattr(interaction.user, 'roles', None) and C.CHIEF_ROLE_ID not in [r.id for r in interaction.user.roles]:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))

    await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Restarting the bot. It will come back online automatically within seconds to tens of seconds.')]))
    

    if C.global_db_dirty:
        async with C.global_json_lock:
            saved = await C.save_json_to_channel(C.FLIGHT_LOG_CHANNEL_ID, C.FLIGHT_LOG_CACHE, "flight_log.json")
        if not saved:

            return await interaction.followup.send(
                ephemeral=True,
                view=C.build_v2_card('Notice', [(None, 'Failed to save the data, so the restart was aborted. Please wait a moment and try again.')]))
        C.global_db_dirty = False
            
    print(f"[{datetime.datetime.now()}] Bot is restarting by {interaction.user.display_name}...")
    

    await C.client.close()
    

    os.execv(sys.executable, ['python'] + sys.argv)

@C.client.tree.command(name="create_bus", description="Create a bus operation event.")
@app_commands.describe(
    template_name="Template name (e.g. City Bus Service)",
    title="Event title (e.g. City Bus Service)",
    staff_meet_datetime="Staff Meet Time (YYYY-MM-DD HH:MM)",
    start_time="Start Time (HH:MM)",
    host_timezone="Timezone"
)
@app_commands.autocomplete(template_name=C.bus_template_autocomplete)
@C.event_manager_only
async def create_bus_slash(interaction: discord.Interaction, template_name: str, title: str,
                           staff_meet_datetime: str, start_time: str, host_timezone: str = "GMT+9"):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)


    if " | " in template_name:
        template_name = template_name.split(" | ")[0].strip()

    await C.ensure_templates_fresh()
    saved_route = C.FLIGHT_DB.get(template_name)
    if not saved_route:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Template not found. Please check the Flight Information channel.')]))


    variants = saved_route.get("variants", {})
    if not variants:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The template does not contain any information.')]))
    
    first_equip_name = list(variants.keys())[0]
    variant_data = variants[first_equip_name]

    src_ch = variant_data.get("source_channel_id")
    src_msg = variant_data.get("source_message_id")
    image_url, image_bytes = await C.fetch_fresh_image_info(src_ch, src_msg)

    data = {
        "flight_code": template_name.strip(), 
        "origin": saved_route["origin"],
        "destination": "",
        "equipment": "Bus",
        "classes": "",
        "roblox_link": variant_data.get("roblox_link", ""),
        "airline": variant_data.get("airline", "Airline"),
        "color": variant_data.get("color", "74BCF6"),
        "source_channel_id": src_ch, "source_message_id": src_msg,
        "staff_meet_datetime_str": staff_meet_datetime, 
        "passenger_time_str": start_time,
        "host_timezone_str": host_timezone,
        "mention_str": f"<@&{C.NOTIFICATION_ROLE_ID}>",
        "is_custom": False,
        "use_bus": True,
        "event_title": title
    }


    success, result_msg = await C.process_flight_creation(interaction.user, data, image_bytes, image_url, is_bus=True)
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Bus Event Created', result_msg, discord.Color.green()), content=None), ephemeral=True)
    else:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', result_msg, discord.Color.red()), content=None), ephemeral=True)

@C.client.tree.command(name="create_custom_bus", description="Create fully customized bus operation events without using templates.")
@app_commands.describe(
    title="Event title (e.g. City Bus Service)",
    vehicle="Vehicle (e.g. Isuzu Gala)",
    server_name="Server name (e.g. City Line)",
    roblox_link="Game Link",
    color="Hex color (e.g. 74BCF6)",
    staff_meet_datetime="Staff Meet Time (YYYY-MM-DD HH:MM)",
    start_time="Start Time (HH:MM)",
    host_timezone="Timezone (e.g., GMT+9)",
    image="Upload bus image",
    mention_role_1="[Optional] Notification role 1",
    mention_role_2="[Optional] Notification role 2",
    mention_all="[Optional] @everyone etc."
)
@app_commands.autocomplete(mention_role_1=C.customer_role_autocomplete, mention_role_2=C.customer_role_autocomplete)
@app_commands.choices(mention_all=[
    app_commands.Choice(name="None", value="none"),
    app_commands.Choice(name="@here", value="@here")
])
@C.event_manager_only
async def create_custom_bus_slash(
        interaction: discord.Interaction, title: str, vehicle: str, server_name: str,
        roblox_link: str, color: str, staff_meet_datetime: str, start_time: str,
        image: discord.Attachment, host_timezone: str = "GMT+9",
        mention_role_1: str = None, mention_role_2: str = None, mention_all: str = "none"
):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    log_channel = C.client.get_channel(C.FLIGHT_INPUT_CHANNEL_ID)
    if not log_channel:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Error: Channel not found.')]))


    saved_msg = await log_channel.send(content=f"Custom Bus Created: `{title}`", file=await image.to_file())
    image_bytes = await image.read()

    mentions_list = []
    if mention_all != "none":
        mentions_list.append(mention_all)
    if mention_role_1:
        mentions_list.append(f"<@&{mention_role_1}>")
    if mention_role_2:
        mentions_list.append(f"<@&{mention_role_2}>")

    if not mentions_list:
        mentions_list.append(f"<@&{C.NOTIFICATION_ROLE_ID}>")

    data = {
        "flight_code": title.strip(),
        "origin": server_name,
        "destination": "",
        "equipment": vehicle,
        "classes": "",
        "roblox_link": roblox_link,
        "airline": "Airline", 
        "color": color.replace("#", ""),
        "source_channel_id": saved_msg.channel.id, 
        "source_message_id": saved_msg.id,
        "staff_meet_datetime_str": staff_meet_datetime, 
        "passenger_time_str": start_time,
        "host_timezone_str": host_timezone,
        "event_title": title,
        "mention_str": " ".join(mentions_list),
        "is_custom": True,
        "use_bus": True
    }


    success, result_msg = await C.process_flight_creation(interaction.user, data, image_bytes, saved_msg.attachments[0].url, is_bus=True)
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Custom Bus Created Successfully', result_msg, discord.Color.green()), content=None), ephemeral=True)
    else:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Creation Error', result_msg, discord.Color.red()), content=None), ephemeral=True)

@C.client.tree.command(name="manual_assign", description="[Admin] Manually change a staff member's attending/not-attending status.")
@app_commands.describe(
    flight_code="Flight code to modify",
    action="Add or Remove",
    status="Accepted or Declined",
    user="Target user"
)
@app_commands.choices(
    action=[app_commands.Choice(name="Add", value="add"),
            app_commands.Choice(name="Remove", value="remove")],
    status=[app_commands.Choice(name="Accepted", value="accept"),
            app_commands.Choice(name="Declined", value="decline")]
)
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def manual_assign_cmd(interaction: discord.Interaction, flight_code: str, action: str, status: str, user: discord.Member):
    if not C.can_remote_assign(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission. Only EventManager/Chief (and permitted roles) can use this.')]))
    await interaction.response.defer(ephemeral=True)

    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if flight is None:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Flight not found.')]))

    uid = user.id
    if action == "remove":
        async with C.global_json_lock:
            flight.setdefault("accepted_users", [])
            flight.setdefault("declined_users", [])
            if status == "accept" and uid in flight["accepted_users"]:
                flight["accepted_users"].remove(uid)
            elif status == "decline" and uid in flight["declined_users"]:
                flight["declined_users"].remove(uid)
            C.global_db_dirty = True
    else:
        await C.set_member_attendance(flight, uid, status)


    if s_ch := C.client.get_channel(flight["staff_channel_id"]):
        try:
            msg = await s_ch.fetch_message(flight["staff_message_id"])
            await C.update_staff_embed_ui(msg, flight, interaction.guild)
        except:
            pass

    action_text = "added" if action == "add" else "removed"
    status_text = "Participating (Accepted)" if status == "accept" else "Not participating (Declined)"
    await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'{user.mention} has been {action_text} as **{status_text}**.')]))






def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(C.__file__)))


def _read_repo_version(project_dir):
    try:
        with open(os.path.join(project_dir, "run.py"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r'\s*__version__\s*=\s*[\'"]([^\'"]+)[\'"]', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None


async def _git_run(args, timeout=120):
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError("timeout: " + " ".join(args))
    return proc.returncode, (stdout or b"").decode("utf-8", "replace"), (stderr or b"").decode("utf-8", "replace")


@C.client.tree.command(name="up", description="Pull the latest code from GitHub and restart the bot (Staff server / Chief only).")
@app_commands.describe(restart="Whether to restart the bot after pulling (default True)")
async def up_cmd(interaction: discord.Interaction, restart: bool = True):
    if interaction.guild_id != C.STAFF_GUILD_ID:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice',
            [(None, 'This command is only available on the staff server.')]))
    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice',
            [(None, 'No permission. **Only the Chief** can run this admin command.')]))
    await interaction.response.defer(ephemeral=True)

    project_dir = _project_root()
    try:
        ok, stdout, _ = await _git_run(["git", "-C", project_dir, "rev-parse", "--is-inside-work-tree"])
        if ok != 0 or stdout.strip() != "true":
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice',
                [(None, 'This folder is not a git repository.\nYou must run it from a `git clone` of the GitHub repository.')]))

        _, branch, _ = await _git_run(["git", "-C", project_dir, "rev-parse", "--abbrev-ref", "HEAD"])
        branch = branch.strip()
        _, before, _ = await _git_run(["git", "-C", project_dir, "rev-parse", "HEAD"])
        before = before.strip()[:7]
        ver_before = _read_repo_version(project_dir)


        f_ok, _, f_err = await _git_run(["git", "-C", project_dir, "fetch", "origin"])
        if f_ok != 0:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Update',
                [(None, f"`git fetch` failed.\n```\n{chr(10).join((f_err or 'unknown error').strip().splitlines()[-6:])}\n```")], color=0xE74C3C))

        p_ok, p_out, p_err = await _git_run(["git", "-C", project_dir, "pull", "--ff-only", "origin", branch])
        if p_ok != 0:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Update',
                [(None, f"`git pull` failed (there may be local changes).\n```\n{chr(10).join((p_err or p_out or 'unknown error').strip().splitlines()[-8:])}\n```\nThe update was aborted. Please commit uncommitted changes and try again.")], color=0xE74C3C))

        _, after, _ = await _git_run(["git", "-C", project_dir, "rev-parse", "HEAD"])
        after = after.strip()[:7]
        ver_after = _read_repo_version(project_dir)
        changed = before != after
        summary = f"`{branch}` `{before}` → `{after}`" + ("" if changed else " (already up to date)")

        if ver_before and ver_after and ver_before != ver_after:
            summary += f"\nVersion: **v{ver_before} → v{ver_after}**"
        elif ver_after or ver_before:
            summary += f"\nVersion: **v{ver_after or ver_before}**"
    except FileNotFoundError:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, '`git` is not installed in this environment.')]))
    except Exception as e:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Update error: {e}')]))

    if not changed and not restart:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Update', [(None, f"Fetched the latest code from GitHub. {summary}")]))

    msg = (f"{C.EMOJI_CHECK_STR} Latest code fetched. {summary}\n"
           f"**Restarting the bot...** (it will restart with the new code about 2 seconds after this message)")
    await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Updater', [(None, msg)]))


    print(f"[/up] {summary}. Restarting bot process to load new version...")
    try:
        await asyncio.sleep(2)
    except Exception:
        pass
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"[/up] execv failed: {e}")
    sys.exit(0)

@C.client.tree.command(name="setup_em_permissions", description="[Admin] Reset event-manager command visibility to everyone (runtime EM/Chief execution guard).")
async def setup_em_permissions_cmd(interaction: discord.Interaction):
    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice',
            [(None, 'No permission. This admin command is only available to the Chief.')]))
    await interaction.response.defer(ephemeral=True)
    try:
        warnings = await C.setup_event_manager_command_permissions()
    except Exception as e:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Update',
            [(None, f'An error occurred while resetting: {e}')], color=0xE74C3C))
    if warnings:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Update',
            [(None, 'Failed to reset permissions for some commands.\n' + '\n'.join(warnings))], color=0xE74C3C))
    else:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice',
            [(None, f"{C.EMOJI_CHECK_STR} Restored event-manager commands to 'visible to everyone' (execution still restricted to EventManager/Chief on the staff server).")]))

@C.client.tree.command(name="close_signup", description="Close signups for a flight early (lock), or reopen them.")
@app_commands.describe(flight_code="Target flight code", lock="True to lock, False to unlock")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def close_signup_cmd(interaction: discord.Interaction, flight_code: str, lock: bool = True):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    
    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Flight not found.')]))
    
    flight["is_locked"] = lock
    C.global_db_dirty = True
    

    if s_ch := C.client.get_channel(flight["staff_channel_id"]):
        try:
            msg = await s_ch.fetch_message(flight["staff_message_id"])
            view = C._signup_view_for(flight)
            for child in view.children:
                if getattr(child, 'custom_id', None) in ["flight_btn_accept", "flight_btn_decline"]:
                    child.disabled = lock
            await msg.edit(view=view)
        except: pass
        
    status_str = "closed (locked)" if lock else "reopened (unlocked)"
    await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'The recruitment panel for **{flight_code}** has been {status_str}.')]))

@C.client.tree.command(name="duplicate_flight", description="Copy an existing flight and create a new one at a different date/time.")
@app_commands.describe(
    source_flight_code="Flight code to copy from",
    new_staff_meet="New staff meet time (YYYY-MM-DD HH:MM)",
    new_pax_start="New boarding start time (HH:MM)"
)
@app_commands.autocomplete(source_flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def duplicate_flight_cmd(interaction: discord.Interaction, source_flight_code: str, new_staff_meet: str, new_pax_start: str):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    
    await interaction.response.defer(ephemeral=True)
    

    source = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == source_flight_code), None)
    if not source:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The source flight was not found.')]))
    

    new_data = copy.deepcopy(source)
    new_data["staff_meet_datetime_str"] = new_staff_meet
    new_data["passenger_time_str"] = new_pax_start
    new_data["accepted_users"] = [interaction.user.id]
    new_data["declined_users"] = []
    

    image_url, image_bytes = await C.fetch_fresh_image_info(source.get("source_channel_id"), source.get("source_message_id"))
    

    success, result_msg = await C.process_flight_creation(interaction.user, new_data, image_bytes, image_url, is_bus=source.get("is_bus", False))
    if success:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Copied the information for **{source_flight_code}** and created a new flight!')]))
    else:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Failed to create the copy: {result_msg}')]))

@C.client.tree.command(name="manual_log", description="[Admin] Manually enter past flight data or edit existing flight logs.")
@app_commands.describe(message_id="Enter a message ID to edit an existing log (leave blank to enter manually)")
@C.event_manager_only
async def manual_log_cmd(interaction: discord.Interaction, message_id: str = None):
    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))

    if not message_id:
        return await interaction.response.send_modal(ManualLogInitModal())

    await interaction.response.defer(ephemeral=True)

    target_msg = None
    channels_to_check = [C.FLIGHT_LOG_HISTORY_CHANNEL_ID, C.MANUAL_LOG_CHANNEL_ID]
    for ch_id in channels_to_check:
        ch = C.client.get_channel(ch_id)
        if ch:
            try:
                target_msg = await ch.fetch_message(int(message_id.strip()))
                if target_msg:
                    break
            except:
                pass

    if not target_msg:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The specified message was not found.')]))

    key_mapping = {
        "Host": "Host", "Co-host": "Co-host", "Captain": "Captain", "First Officer": "First Officer",
        "Receptionist": "Receptionist",
        "Airport Guide": "Airport Guide",
        "Gate Agent": "Gate Agent",
        "Lounge Agent": "Lounge Agent",
        "First Class": "First Class", "Business Class": "Business Class",
        "Premium Economy": "Premium Economy", "Economy Class": "Economy Class",
        "MR": "GC Supervisor(MR)", "GC Supervisor(MR)": "GC Supervisor(MR)",
        "Crew": "Ground Crew", "Ground Crew": "Ground Crew",
        "Bus Driver": "Bus Driver", "Dispatcher": "Dispatcher"
    }

    content_to_parse = target_msg.content
    if target_msg.embeds:
        for e in target_msg.embeds:
            content_to_parse += f"\n{e.title}\n{e.description}\n"
            for f in e.fields:
                content_to_parse += f"\n{f.name}\n{f.value}\n"

    flight_code = "Unknown"
    assignments = {}
    
    fc_match = re.search(r"(?:Flight Code:|\|)\s*\*?([^|\n]+?)\*?\s*(?:\||\n|$)", content_to_parse, re.IGNORECASE)
    if fc_match:
        flight_code = fc_match.group(1).strip().strip("*").strip()


        flight_code = re.sub(r"\s*\(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}[^)]*\)\s*$", "", flight_code).strip()
        
    lines = content_to_parse.split('\n')
    for line in lines:
        if "> " in line and ":" in line:
            parts = line.replace("> ", "").split(":", 1)
            if len(parts) == 2:
                raw_key = parts[0].strip()
                uids = re.findall(r'<@!?(\d+)>', parts[1])
                uids += re.findall(r'\b(\d{17,19})\b', parts[1])
                
                mapped_key = raw_key
                for k, v in key_mapping.items():
                    if k in raw_key:
                        mapped_key = v
                        break
                        
                if mapped_key not in assignments:
                    assignments[mapped_key] = []
                    
                for uid in uids:
                    uid_int = int(uid)
                    if uid_int not in assignments[mapped_key]:
                        assignments[mapped_key].append(uid_int)


    log_date_str = "Unknown"
    date_match = re.search(r"\|\s*[A-Za-z0-9]+\s*\((\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}[^)]*)\)", content_to_parse)
    if date_match:
        log_date_str = date_match.group(1).strip()
    else:
        log_date_str = f"<t:{int(target_msg.created_at.timestamp())}:D>"

    if target_msg.author == C.client.user:
        log_type = "EditLog"
        edit_msg_obj = target_msg
    else:
        log_type = "Manual"
        edit_msg_obj = None

    view = LogAssignmentView(flight_code, log_type, initial_assignments=assignments, edit_message_obj=edit_msg_obj, log_date=log_date_str)
    await interaction.followup.send(embed=view.generate_embed(), view=view, ephemeral=True)

@C.client.tree.command(name="flight_backup", description="Add missing/additional staff to a flight log.")
@app_commands.describe(flight_code="Select Flight Code")
@app_commands.autocomplete(flight_code=C.backup_flight_autocomplete)
@C.event_manager_only
async def flight_backup_cmd(interaction: discord.Interaction, flight_code: str):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    
    view = LogAssignmentView(flight_code, "Backup")
    await interaction.response.send_message(embed=view.generate_embed(), view=view, ephemeral=True)

@C.client.tree.command(name="request_staff", description="Send a request for backup staff to fill a missing position shortly before a flight.")
@app_commands.describe(
    flight_code="Target flight code",
    needed_role="Select the position that is short-staffed",
    message="Additional message (e.g. \"Need 1 more person\")"
)
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@app_commands.choices(needed_role=[
    app_commands.Choice(name="Flight Operations", value=str(C.ROLE_FLIGHT_OPS)),
    app_commands.Choice(name="Cabin Crews", value=str(C.ROLE_CABIN_CREWS)),
    app_commands.Choice(name="Ground Operations", value=str(C.ROLE_GROUND_OPS)),
    app_commands.Choice(name="Bus Driver", value=str(C.ROLE_BUS_DRIVER_1))
])
@C.event_manager_only
async def request_staff_cmd(interaction: discord.Interaction, flight_code: str, needed_role: str, message: str = None):

    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))


    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.response.send_message(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'Flight `{flight_code}` not found.', discord.Color.red()), content=None), ephemeral=True)

    await interaction.response.defer(ephemeral=True)


    role_mention = f"<@&{needed_role}>"
    if needed_role == str(C.ROLE_BUS_DRIVER_1):
        role_mention = f"<@&{C.ROLE_BUS_DRIVER_1}>"


    route_text = f"{flight.get('origin')}"
    if flight.get('destination'):
        route_text += f" ➝ {flight.get('destination')}"


    embed = discord.Embed(
        title=f"Staff Request | {flight_code}",
        description=(f"Additional staff are needed for **{flight_code}**.\n"
                     f"If you can help, please join as soon as possible.\n\n"
                     f"**Route:** {route_text}\n**Role:** {role_mention}"),
        color=discord.Color.orange()
    )
    if message:
        embed.add_field(name="Message", value=message, inline=False)

    view = discord.ui.View()

    staff_msg_link = f"https://discord.com/channels/{flight['staff_guild_id']}/{flight['staff_channel_id']}/{flight['staff_message_id']}"
    view.add_item(discord.ui.Button(label="Go to signup message", style=discord.ButtonStyle.link, url=staff_msg_link))

    staff_channel = C.client.get_channel(C.STAFF_CHANNEL_ID)
    if staff_channel:

        await staff_channel.send(content=role_mention, embed=embed, view=view)
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Staff request sent to the staff channel.')]))
    else:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Staff channel not found. / Staff channel not found.')]))

@C.client.tree.command(name="manage_templates", description="[Admin] View and delete registered flight/bus templates.")
@app_commands.describe(template_name="Template to manage (flight code or service name)")
@app_commands.autocomplete(template_name=C.all_template_autocomplete)
@C.event_manager_only
async def manage_templates_cmd(interaction: discord.Interaction, template_name: str):

    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))

    saved_route = C.FLIGHT_DB.get(template_name)
    if not saved_route:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The specified template was not found.')]))

    embed = discord.Embed(
        title=f"Template Management: {template_name}",
        description=f"**Departure / Server:** {saved_route.get('origin', 'N/A')}\n**Arrival:** {saved_route.get('destination', 'N/A')}\n\n**Registered Equipment Variations**",
        color=C.EMBED_COLOR
    )

    for equip, v_data in saved_route.get("variants", {}).items():
        embed.add_field(
            name=f"Equipment: {equip}",
            value=f"Airline: {v_data.get('airline', 'N/A')}\nClass: {v_data.get('classes', 'N/A')}",
            inline=False
        )

    view = discord.ui.View(timeout=120)
    delete_btn = discord.ui.Button(label="Delete this template", style=discord.ButtonStyle.danger, custom_id="delete_template")

    async def delete_cb(i: discord.Interaction):
        if not C.is_chief(i.user):
            return await i.response.send_message("No permission.", ephemeral=True)
        
        await i.response.defer()
        input_channel = C.client.get_channel(C.FLIGHT_INPUT_CHANNEL_ID)
        deleted_count = 0
        

        if input_channel:
            for equip, v_data in saved_route.get("variants", {}).items():
                msg_id = v_data.get("source_message_id")
                if msg_id:
                    try:
                        msg = await input_channel.fetch_message(msg_id)
                        await msg.delete()
                        deleted_count += 1
                    except Exception as e:
                        print(f"Template message delete error: {e}")


        await C.update_db_cache()
        await i.edit_original_response(content=f"Deleted template `{template_name}` from the database. (related messages removed: {deleted_count})", embed=None, view=None)

    delete_btn.callback = delete_cb
    view.add_item(delete_btn)

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
