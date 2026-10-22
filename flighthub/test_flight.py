import discord
from discord import app_commands
import datetime
import io
import base64
import re
import traceback
import aiohttp
import asyncio

from . import core as C
from . import ui_theme as theme

@C.client.tree.command(name="create_custom_flight",
                     description="Create a completely custom flight without using a template.")
@app_commands.describe(
    flight_code="Flight Code (e.g., JI123)", airline="Airline (e.g., SkyWings)", origin="Origin",
    destination="Destination",
    equipment="Aircraft (e.g., B777)", classes="Classes (e.g., Economy)", roblox_link="Game Link",
    color="Hex Color (e.g., 1B3444)",
    staff_meet_datetime="Staff Meet Time (YYYY-MM-DD HH:MM)", passenger_start_time="Pax Join Time (HH:MM)",
    host_timezone="Timezone (e.g., GMT+9)", image="Upload flight image",
    event_title="[Optional] Custom event title",
    mention_role_1="[Optional] Notification role 1", mention_role_2="[Optional] Notification role 2", mention_all="[Optional] @everyone etc."
)
@app_commands.autocomplete(mention_role_1=C.customer_role_autocomplete, mention_role_2=C.customer_role_autocomplete)
@app_commands.choices(
    mention_all=[
        app_commands.Choice(name="None", value="none"),
        app_commands.Choice(name="@here", value="@here")
    ]
)
@C.event_manager_only
async def create_custom_flight_slash(
        interaction: discord.Interaction, flight_code: str, airline: str, origin: str, destination: str,
        equipment: str, classes: str, roblox_link: str, color: str,
        staff_meet_datetime: str, passenger_start_time: str, image: discord.Attachment,
        host_timezone: str = "GMT+9",
        event_title: str = None, mention_role_1: str = None, mention_role_2: str = None,
        mention_all: str = "none"
        ):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    log_channel = C.client.get_channel(C.FLIGHT_INPUT_CHANNEL_ID)
    if not log_channel:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Error: Channel not found.')]))

    saved_msg = await log_channel.send(content=f"Custom Flight Created: `{flight_code}`",
                                       file=await image.to_file())
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
        "flight_code": flight_code.strip().upper(), "origin": origin, "destination": destination,
        "equipment": equipment, "classes": classes, "roblox_link": roblox_link,
        "airline": airline, "color": color.replace("#", ""),
        "source_channel_id": saved_msg.channel.id, "source_message_id": saved_msg.id,
        "staff_meet_datetime_str": staff_meet_datetime, "passenger_time_str": passenger_start_time,
        "host_timezone_str": host_timezone,
        "event_title": event_title,
        "mention_str": " ".join(mentions_list),
        "is_custom": True
    }

    success, result_msg = await C.process_flight_creation(interaction.user, data, image_bytes,
                                                        saved_msg.attachments[0].url)
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_CHECK_STR + ' Custom Flight Created Successfully', result_msg, theme.SUCCESS), content=None), ephemeral=True)
    else:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_X_STR + ' Creation Error', result_msg, theme.DANGER), content=None), ephemeral=True)

class _CollectFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content=None, *args, **kwargs):
        self.messages.append(str(content) if content is not None else "")

class _CollectInteraction:
    def __init__(self, guild):
        self.guild = guild
        self.guild_id = getattr(guild, "id", None)
        self.followup = _CollectFollowup()

async def refresh_all_active_events(guild=None):
    now = datetime.datetime.now().timestamp()
    codes = [f.get("flight_code") for f in list(C.FLIGHT_LOG_CACHE)
             if f.get("flight_code") and (f.get("end_timestamp") or 0) > now and not f.get("messages_deleted")]
    result = {"total": len(codes), "ok": 0, "failed": []}
    guild = guild or C.client.get_guild(C.STAFF_GUILD_ID)
    for code in codes:
        proxy = _CollectInteraction(guild)
        try:
            await sync_flight_ui(proxy, code)
            text = "\n".join(proxy.followup.messages)
            bad = [ln.strip() for ln in text.splitlines()
                   if any(k in ln for k in ("Failed", "failed", "not found", C.EMOJI_NOTI_STR, "Critical"))]
            if bad:
                result["failed"].append((code, bad[0][:120]))
            else:
                result["ok"] += 1
        except Exception as e:
            traceback.print_exc()
            result["failed"].append((code, str(e)[:120]))
        await asyncio.sleep(3)
    return result

@C.client.tree.command(name="update",
                     description="[Staff] Reload, validate and migrate saved data; does not update bot code.")
@app_commands.describe(full_reload="Reload ALL data from storage channels first (default: Yes. Unsaved changes are saved first)")
@C.event_manager_only
async def update_cmd(interaction: discord.Interaction, full_reload: bool = True):
    if not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission. This admin command is only available to the Chief.')]))
    await interaction.response.defer(ephemeral=True)

    try:
        if full_reload:

            async with C.global_json_lock:
                if C.global_db_dirty and C.FLIGHT_LOG_CHANNEL_ID not in C.LOAD_UNSAFE_CHANNELS:
                    if await C.save_json_to_channel(C.FLIGHT_LOG_CHANNEL_ID, C.FLIGHT_LOG_CACHE, "flight_log.json"):
                        C.global_db_dirty = False
            await C.load_all_data()
        else:
            await C.load_all_data(only_failed=True)

        rep_ = {"total": 0, "migrated": 0, "threads": 0, "mention_restored": 0, "routes": 0, "last_mention": C.LAST_CUSTOMER_MENTION_TS, "warnings": []}
        if C.LOAD_STATUS.get("Flight log (DB)", {}).get("ok"):
            rep_ = await C.v14_upgrade_data()
        else:
            rep_["warnings"].append("Flight DB not loaded; conversion skipped.")


        async with C.global_json_lock:
            if C.global_db_dirty and C.FLIGHT_LOG_CHANNEL_ID not in C.LOAD_UNSAFE_CHANNELS:
                if await C.save_json_to_channel(C.FLIGHT_LOG_CHANNEL_ID, C.FLIGHT_LOG_CACHE, "flight_log.json"):
                    C.global_db_dirty = False

        cleanup_rep = {"removed": {}, "backup": None, "skipped": None}
        try:
            cleanup_rep = await C.cleanup_obsolete_saved_data()
        except Exception as e:
            rep_["warnings"].append(f"Saved-data cleanup failed: {e}")
        try:
            if not await C.save_misc_data():
                rep_["warnings"].append("Could not save misc data.")
        except Exception as e:
            rep_["warnings"].append(f"Could not save misc data: {e}")


        try:
            for _w in C.check_command_visibility_roles(interaction.guild):
                rep_["warnings"].append(_w)
        except Exception as e:
            print(f"Command visibility check error: {e}")


        for w in C.verify_loaded_data():
            rep_["warnings"].append(w)

        if C.load_problems() and not C.LOAD_STATE["retry_running"]:
            C.client.loop.create_task(C.retry_failed_loads_forever())


        ev_rep = {"total": 0, "ok": 0, "failed": []}
        if C.LOAD_STATUS.get("Flight log (DB)", {}).get("ok"):
            try:
                ev_rep = await refresh_all_active_events(interaction.guild)
            except Exception as e:
                traceback.print_exc()
                rep_["warnings"].append(f"Event refresh failed: {e}")
        else:
            rep_["warnings"].append("Flight DB not loaded; event refresh skipped.")

        all_ok = not C.load_problems()
        embed = discord.Embed(
            title="Data Refresh & Migration",
            color=theme.SUCCESS if all_ok and not rep_["warnings"] else theme.WARNING)

        lines = []
        for name, st in C.LOAD_STATUS.items():
            lines.append(f"{'[OK]' if st['ok'] else '[NG]'} {name}" + ("" if st["ok"] else f" — {st['detail'][:80]}"))
        embed.add_field(name="Data loading", value="\n".join(lines)[:1024] or "-", inline=False)

        embed.add_field(
            name="V14 format",
            value=(f"Flights: **{rep_['total']}**\n"
                   f"Converted to V14: **{rep_['migrated']}**\n"
                   f"Already V14: **{max(rep_['total'] - rep_['migrated'], 0)}**\n"
                   f"Routes restored: **{rep_.get('routes', 0)}**\n"
                   f"Threads recovered: **{rep_['threads']}**\n"
                   f"Mention history restored: **{rep_['mention_restored']}**"),
            inline=False)

        ev_text = f"Updated: **{ev_rep['ok']}/{ev_rep['total']}**"
        if ev_rep["failed"]:
            ev_text += "\n" + "\n".join(f"• `{c}` — {r}" for c, r in ev_rep["failed"][:8])
        embed.add_field(name="Active events", value=ev_text[:1024], inline=False)
        if ev_rep["failed"]:
            embed.color = theme.WARNING

        last = int(rep_["last_mention"] or 0)
        if last and C.mention_cooldown_active():
            nxt = last + C.MENTION_SPACING_HOURS * 3600
            clock_txt = (f"Last mention: <t:{last}:F>\n"
                         f"Next mention allowed: <t:{nxt}:F> (<t:{nxt}:R>)")
        elif last:
            clock_txt = f"Last mention: <t:{last}:F>\nCooldown is over."
        else:
            clock_txt = "No mention history found."
        embed.add_field(name="24h mention rule", value=clock_txt, inline=False)

        pend = C.predict_pending_announcements()
        if pend:
            plines = [f"`{p['code']}` → <t:{p['ts']}:f> — " + ("**WITH mention**" if p["mention"] else "**WITHOUT mention**")
                      for p in pend]
            embed.add_field(name="Scheduled announcements", value="\n".join(plines)[:1024], inline=False)

        removed = cleanup_rep.get("removed") or {}
        if cleanup_rep.get("skipped"):
            embed.add_field(name="Saved-data cleanup", value=f"Skipped: {cleanup_rep['skipped']}", inline=False)
        elif any(removed.values()):
            embed.add_field(name="Saved-data cleanup",
                            value=(f"Removed data of retired features:\n"
                                   f"• staff notes: **{removed.get('staff_notes', 0)}** / announce templates: **{removed.get('announce_templates', 0)}** / swap board: **{removed.get('swap_board', 0)}**\n"
                                   f"A backup is attached."),
                            inline=False)
        else:
            embed.add_field(name="Saved-data cleanup", value="Nothing to clean up.", inline=False)

        if rep_["warnings"]:
            embed.add_field(name="Warnings", value="\n".join(f"• {w}" for w in rep_["warnings"])[:1024], inline=False)
        if not all_ok:
            embed.set_footer(text="Failed items are retried automatically every minute.")

        _send_kwargs = {"view": C.embed_to_v2_layout(embed, content=None), "ephemeral": True}
        if cleanup_rep.get("backup"):
            _send_kwargs["file"] = discord.File(io.BytesIO(cleanup_rep["backup"]), filename="removed_features_backup.json")
        await interaction.followup.send(**_send_kwargs)
    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Update failed: {e}')]))

@C.client.tree.command(name="create_private_flight",
                     description="Create a private, staff-only flight (no customer notification, gray color).")
@app_commands.describe(
    flight_code="Flight Code (e.g., JI123)", airline="Airline (e.g., SkyWings)", origin="Origin",
    destination="Destination",
    equipment="Aircraft (e.g., B777)", classes="Classes (e.g., Economy)", roblox_link="Game Link",
    staff_meet_datetime="Staff Meet Time (YYYY-MM-DD HH:MM)", passenger_start_time="Pax Join Time (HH:MM)",
    host_timezone="Timezone (e.g., GMT+9)", image="Upload flight image",
    event_title="[Optional] Custom event title"
)
@C.event_manager_only
async def create_private_flight_slash(
        interaction: discord.Interaction, flight_code: str, airline: str, origin: str, destination: str,
        equipment: str, classes: str, roblox_link: str,
        staff_meet_datetime: str, passenger_start_time: str, image: discord.Attachment,
        host_timezone: str = "GMT+9",
        event_title: str = None
        ):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    log_channel = C.client.get_channel(C.FLIGHT_INPUT_CHANNEL_ID)
    if not log_channel:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Error: Channel not found.')]))

    saved_msg = await log_channel.send(content=f"Private Flight Created: `{flight_code}`",
                                       file=await image.to_file())
    image_bytes = await image.read()

    data = {
        "flight_code": flight_code.strip().upper(), "origin": origin, "destination": destination,
        "equipment": equipment, "classes": classes, "roblox_link": roblox_link,
        "airline": airline, "color": f"{C.PRIVATE_FLIGHT_COLOR:06X}",
        "source_channel_id": saved_msg.channel.id, "source_message_id": saved_msg.id,
        "staff_meet_datetime_str": staff_meet_datetime, "passenger_time_str": passenger_start_time,
        "host_timezone_str": host_timezone,
        "event_title": event_title,
        "mention_str": "",
        "is_custom": True,
        "is_private": True
    }

    success, result_msg = await C.process_flight_creation(interaction.user, data, image_bytes,
                                                        saved_msg.attachments[0].url)
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_CHECK_STR + ' Private Flight Created Successfully', result_msg + '\n(No customer notification will be sent.)', theme.SUCCESS), content=None), ephemeral=True)
    else:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_X_STR + ' Creation Error', result_msg, theme.DANGER), content=None), ephemeral=True)

@C.client.tree.command(name="create_private_flight_template",
                     description="Create a private, staff-only flight from a saved template (no customer notification).")
@app_commands.describe(
    flight_code="Select Flight Code or Search by Airport",
    equipment="Aircraft Type",
    staff_meet_datetime="Staff Meet Time (YYYY-MM-DD HH:MM)",
    passenger_start_time="Pax Join Time (HH:MM)",
    host_timezone="Timezone (e.g., GMT+9)",
    event_title="[Optional] Custom event title"
)
@app_commands.autocomplete(flight_code=C.flight_code_autocomplete, equipment=C.equipment_autocomplete)
@C.event_manager_only
async def create_private_flight_template_slash(
        interaction: discord.Interaction, flight_code: str, equipment: str,
        staff_meet_datetime: str, passenger_start_time: str,
        host_timezone: str = "GMT+9", event_title: str = None):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    await C.ensure_templates_fresh()
    saved_route = C.FLIGHT_DB.get(flight_code)
    if not saved_route:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No template data found for that flight code.')]))

    clean_equip = equipment.replace(" (Registered)", "").replace("(Registered)", "").strip()
    variant_data = None
    for k, v in saved_route.get("variants", {}).items():
        if k.lower() == clean_equip.lower():
            variant_data = v
            clean_equip = k
            break
    if not variant_data:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No template was found for the specified aircraft. Check the aircraft name, or register its image first.')]))

    image_url, image_bytes = await C.fetch_fresh_image_info(variant_data.get("source_channel_id"), variant_data.get("source_message_id"))
    if not image_bytes:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Error: The template image could not be loaded.')]))

    log_channel = C.client.get_channel(C.FLIGHT_INPUT_CHANNEL_ID)
    if not log_channel:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Error: Channel not found.')]))

    code = flight_code.strip().upper()
    img_name = (image_url or "").split("?")[0].rsplit("/", 1)[-1] or "flight.png"
    saved_msg = await log_channel.send(content=f"Private Flight Created: `{code}`",
                                       file=discord.File(io.BytesIO(image_bytes), filename=img_name))

    data = {
        "flight_code": code, "origin": saved_route["origin"], "destination": saved_route["destination"],
        "equipment": clean_equip, "classes": variant_data.get("classes", "Unknown"),
        "roblox_link": variant_data.get("roblox_link", ""),
        "airline": variant_data.get("airline", "Airline"),
        "color": f"{C.PRIVATE_FLIGHT_COLOR:06X}",
        "source_channel_id": saved_msg.channel.id, "source_message_id": saved_msg.id,
        "staff_meet_datetime_str": staff_meet_datetime, "passenger_time_str": passenger_start_time,
        "host_timezone_str": host_timezone,
        "event_title": event_title,
        "mention_str": "",
        "is_custom": True,
        "is_private": True
    }

    success, result_msg = await C.process_flight_creation(interaction.user, data, image_bytes, saved_msg.attachments[0].url)
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_CHECK_STR + ' Private Flight Created Successfully', result_msg + '\n(No customer notification will be sent.)', theme.SUCCESS), content=None), ephemeral=True)
    else:
        try:
            await saved_msg.delete()
        except Exception:
            pass
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_X_STR + ' Creation Error', result_msg, theme.DANGER), content=None), ephemeral=True)

@C.client.tree.command(name="host_change", description="Change the host of a flight.")
@app_commands.describe(flight_code="Target flight code", new_host="Select the new host")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def host_change(interaction: discord.Interaction, flight_code: str, new_host: discord.Member):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(view=C.embed_to_v2_layout(C.create_info_embed('Error', 'No permission.', theme.DANGER), content=None), ephemeral=True)
        
    await interaction.response.defer(ephemeral=True)
    try:
        async with C.global_json_lock:
            target = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
            if not target:
                return await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'Flight `{flight_code}` not found.', theme.DANGER), content=None), ephemeral=True)
                
            old_host_id = target["host_id"]
            target["host_id"] = new_host.id
            C.global_db_dirty = True
            C.UNDO_STACK.append({
                "type": "host_change",
                "flight_code": flight_code,
                "old_host_id": old_host_id,
                "new_host_id": new_host.id,
                "actor_id": interaction.user.id
            })
            if len(C.UNDO_STACK) > 20:
                C.UNDO_STACK.pop(0)



            if target.get("flight_channels"):
                try:
                    await C.sync_flight_channel_perms(target)
                except Exception as e:
                    print(f"Flight channel perm sync on host_change error: {e}")


        if s_ch := C.client.get_channel(target["staff_channel_id"]):
            try:
                msg = await s_ch.fetch_message(target["staff_message_id"])
                embed = msg.embeds[0]
                _new_host_name = await C.get_server_display_name(new_host.id, target.get("staff_guild_id") or C.STAFF_GUILD_ID,
                                                               fallback=new_host.display_name)
                for i, f in enumerate(embed.fields):
                    if f.name == "Host":
                        embed.set_field_at(i, name="Host", value=_new_host_name, inline=False)
                        break
                embed.set_footer(
                    text=f"Flight Code: {target['flight_code']} | Created by {_new_host_name}")
                await msg.edit(embed=embed)
            except:
                pass
                

        if url := target.get("event_url"):
            try:
                eid = int(url.split("/")[-1])
                

                target_guild_id = C.STAFF_GUILD_ID if target.get("is_gamenight") or target.get("is_test") or target.get("is_private") else C.CUSTOMER_GUILD_ID
                c_guild = C.client.get_guild(target_guild_id)
                event = await c_guild.fetch_scheduled_event(eid)
                

                nd = f"`Host` {new_host.mention}\n`Origin` {target['origin']}\n`Destination` {target['destination']}\n> Information\n`Airline` {target.get('airline', 'Airline')}\n`Aircraft` {target['equipment']}\n`Classes` {target['classes']}"
                
                await event.edit(description=nd)
            except:
                pass
                
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Success', f'{C.EMOJI_CHECK_STR} Host changed to {new_host.mention}.', theme.SUCCESS), content=None), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'An error occurred while changing: {e}', theme.DANGER), content=None), ephemeral=True)

@C.client.tree.command(name="update_ui", description="Force update ALL messages & SYNC Event Image from DB.")
@app_commands.describe(flight_code="The flight code to synchronize (e.g., JI54)")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def update_flight_ui(interaction: discord.Interaction, flight_code: str):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C.is_event_manager_or_chief(interaction.user):
        try:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
        except discord.NotFound:
            return


    try:
        await interaction.response.defer(ephemeral=True)
    except discord.NotFound:
        print("[update_ui] Processing timed out due to network lag.")
        return

    await sync_flight_ui(interaction, flight_code)

async def sync_flight_ui(interaction: discord.Interaction, flight_code: str):


    try:
        await C.update_db_cache()
    except Exception as e:
        print(f"[update_ui] template refresh error: {e}")

    try:
        status_log = [C.EMOJI_SEARCH_STR + " **Syncing UI & Images...**"]



        try:
            _fl0 = next((f for f in C.FLIGHT_LOG_CACHE if f.get("flight_code") == flight_code), None)
            if _fl0 and not (_fl0.get("is_custom") or _fl0.get("is_gamenight") or _fl0.get("messages_deleted")):
                _rc0 = _fl0.get("route_code")
                if _rc0 and _rc0 in C.FLIGHT_DB:
                    _expected0 = C.compose_flight_code(_fl0, _rc0)
                    if _expected0 != _fl0.get("flight_code"):
                        _eq0 = (_fl0.get("equipment") or "").lower()
                        _vars0 = C.FLIGHT_DB[_rc0].get("variants", {})
                        _eqkey0 = next((k for k in _vars0 if k.lower() == _eq0), None) or next(iter(_vars0), None)
                        if _eqkey0:
                            _ok0, _msg0, _w0 = await C.perform_route_change(flight_code, _rc0, _eqkey0, guild=interaction.guild)
                            if _ok0:
                                status_log.append(f"Flight code fixed: `{flight_code}` → `{_expected0}`")
                                flight_code = _expected0
                            else:
                                status_log.append(f"{C.EMOJI_NOTI_STR} Flight code could not be fixed automatically: {_msg0}")
                            status_log.extend(f"{C.EMOJI_NOTI_STR} {w}" for w in _w0)
        except Exception as e:
            traceback.print_exc()
            status_log.append(f"{C.EMOJI_NOTI_STR} Flight code check failed: {e}")


        async with C.global_json_lock:
            flight = next((f for f in C.FLIGHT_LOG_CACHE if f.get("flight_code") == flight_code), None)
            if flight is None:
                return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f' {C.EMOJI_X_STR} Flight `{flight_code}` not found in active logs.')]))


            loa_removed_count = 0
            for key in ("accepted_users", "declined_users"):
                for uid in list(flight.get(key, [])):
                    loa_data = C.LOA_CACHE.get(str(uid))
                    if loa_data and loa_data.get("status") == "active":
                        flight[key].remove(uid)
                        loa_removed_count += 1
            if loa_removed_count > 0:
                status_log.append(f"Removed {loa_removed_count} user(s) currently on LOA.")

            clean_equip = (flight.get("equipment", "") or "").replace(" (Registered)", "").replace("(Registered)", "").strip()



            tmpl_code = C.resolve_template_code(flight)
            matched_v_data = None
            if tmpl_code:
                for k, v in C.FLIGHT_DB[tmpl_code].get("variants", {}).items():
                    if k.lower() == clean_equip.lower():
                        matched_v_data = v
                        flight["equipment"] = k
                        break

            if matched_v_data:

                if not flight.get("is_custom"):
                    _t_origin = C.FLIGHT_DB[tmpl_code].get("origin")
                    _t_dest = C.FLIGHT_DB[tmpl_code].get("destination")
                    if _t_origin and (flight.get("origin") != _t_origin or (_t_dest and flight.get("destination") != _t_dest)):
                        status_log.append(f"Route synced: {flight.get('origin')}→{flight.get('destination')} ⇒ {_t_origin}→{_t_dest}")
                        flight["origin"] = _t_origin
                        if _t_dest:
                            flight["destination"] = _t_dest
                flight["classes"] = matched_v_data.get("classes", flight.get("classes", "Unknown"))
                flight["roblox_link"] = matched_v_data.get("roblox_link", flight.get("roblox_link", ""))
                flight["airline"] = matched_v_data.get("airline", flight.get("airline", "Airline"))
                flight["color"] = matched_v_data.get("color", flight.get("color", "1B3444"))
                flight["source_channel_id"] = matched_v_data.get("source_channel_id", flight.get("source_channel_id"))
                flight["source_message_id"] = matched_v_data.get("source_message_id", flight.get("source_message_id"))
                status_log.append(f"Template synced: `{tmpl_code}`")
            else:
                status_log.append("Template not found for this flight/equipment: saved data was kept.")
            C.global_db_dirty = True


        origin = flight.get('origin', 'Unknown')
        dest = flight.get('destination', 'Unknown')
        equipment = flight.get('equipment', 'Unknown')
        airline = flight.get('airline', 'Airline')
        embed_color = C.get_embed_color(flight.get('color'))
        start_ts = int(flight["start_timestamp"])
        end_ts = int(flight["end_timestamp"])
        staff_ts = int(flight.get("staff_timestamp", start_ts - 3600))
        image_url, image_bytes = await C.fetch_image_for_update(flight.get("source_channel_id"), flight.get("source_message_id"))
        is_gn = bool(flight.get("is_gamenight") or str(flight.get("flight_code", "")).startswith("GN_"))
        time_str_new = f"<t:{start_ts}:F> - <t:{end_ts}:t> (<t:{start_ts}:R>)"


        s_channel = None
        if flight.get("staff_channel_id"):
            s_channel = C.client.get_channel(flight["staff_channel_id"])
            if s_channel is None:
                try:
                    s_channel = await C.client.fetch_channel(flight["staff_channel_id"])
                except Exception:
                    s_channel = None
        if s_channel and flight.get("staff_message_id"):
            try:
                msg = await s_channel.fetch_message(flight["staff_message_id"])
                old_embed = msg.embeds[0]
                host_name = "Unknown"
                for field in old_embed.fields:
                    if field.name == "Host":
                        host_name = field.value
                host_name = await C.get_server_display_name(flight["host_id"], flight.get("staff_guild_id") or C.STAFF_GUILD_ID,
                                                          fallback=host_name)

                if is_gn:
                    flight["is_gamenight"] = True
                    new_embed = old_embed.copy()

                    if any("Aircraft" in f.name for f in new_embed.fields):
                        new_embed.clear_fields()
                        new_embed.title = f"Staff Game Night: {flight['flight_code']}"
                        new_embed.description = "The UI was corrupted and has been reset."
                        new_embed.add_field(name="Host", value=host_name, inline=False)
                        new_embed.add_field(name="Game", value="Please Recreate", inline=True)
                        new_embed.add_field(name="Prize", value="Please Recreate", inline=True)
                        new_embed.add_field(name="Action", value=f"React to join the event.\n**Start Time:** <t:{staff_ts}:F>", inline=False)
                        new_embed.add_field(name=f"{C.EMOJI_CHECK_STR} Accepted (0)", value="-", inline=True)
                        new_embed.add_field(name=f"{C.EMOJI_X_STR} Declined (0)", value="-", inline=True)
                    else:
                        for i, f_field in enumerate(new_embed.fields):
                            if f_field.name == "Action":
                                new_embed.set_field_at(i, name="Action", value=f"React to join the event.\n**Start Time:** <t:{staff_ts}:F>", inline=False)
                                break
                    new_embed.set_footer(text=f"Flight Code: {flight['flight_code']} | Created by {host_name}")
                else:


                    new_embed = old_embed.copy()
                    new_embed.title = C.signup_embed_title(flight, C.build_flight_event_name(flight))
                    new_embed.colour = C.PRIVATE_FLIGHT_COLOR if flight.get("is_private") else embed_color
                    min_staff_ui = C.minimum_staff_text()
                    for i, fld in enumerate(new_embed.fields):
                        n, v = fld.name, None
                        if n == "Host":
                            v = host_name
                        elif n == "Route":
                            v = f"{origin} ➝ {dest}"
                        elif n == "Aircraft Equipment":
                            v = equipment
                        elif n == "Aircraft Operator":
                            v = airline
                        elif n == "Minimum Staff Needed":
                            v = min_staff_ui
                        elif n == "Action":
                            head = (fld.value or "React to join.").split("\n")[0]
                            v = f"{head}\n**Staff Briefing Time:** <t:{staff_ts}:F>" + C.google_calendar_suffix(flight, start_ts=staff_ts)
                        elif n == "Time":
                            v = time_str_new
                        if v is not None:
                            new_embed.set_field_at(i, name=n, value=v, inline=fld.inline)

                    _ft = (old_embed.footer.text if old_embed.footer else "") or ""
                    _m = re.match(r"Flight Code: (.+?) \|(.*)", _ft)
                    _tail = _m.group(2) if _m else f" Created by {host_name}"
                    new_embed.set_footer(text=f"Flight Code: {flight['flight_code']} |{_tail}")



                staff_image_file = None
                clear_attachments = False
                if image_bytes:
                    staff_image_file = C.embed_image_as_attachment(
                        new_embed, image_bytes, image_url, prefix=f"staff_{flight['flight_code']}")
                    status_log.append("Image found and synced.")
                elif image_url:
                    new_embed.set_image(url=image_url)
                    clear_attachments = True
                    status_log.append("Image found (URL) and synced.")
                else:
                    status_log.append(f"{C.EMOJI_NOTI_STR} Image could not be fetched: the previous image was kept.")

                await C.update_staff_embed_ui(msg, flight, interaction.guild, embed=new_embed, strict=True,
                                              image_file=staff_image_file, view=C._signup_view_for(flight),
                                              clear_attachments=clear_attachments)
                status_log.append("Staff Message (Names & Image) Updated")
            except Exception as e:
                status_log.append(f"Staff Message Update Failed: {e}")
        else:
            status_log.append("Staff Message Not Found (skipped)")


        c_channel_id = flight.get("customer_channel_id") or C.CUSTOMER_CHANNEL_ID
        c_channel = C.client.get_channel(c_channel_id)
        if c_channel is None:
            try:
                c_channel = await C.client.fetch_channel(c_channel_id)
            except Exception:
                c_channel = None
        if c_channel:
            new_cust_content = C.build_customer_announcement(flight)

            if flight.get("customer_message_id"):
                try:
                    c_msg = await c_channel.fetch_message(flight["customer_message_id"])
                    await c_msg.edit(content=new_cust_content, suppress=True)
                    status_log.append("Customer Message Updated")
                except Exception as e:
                    status_log.append(f"Customer Message Update Failed: {e}")
            elif not (flight.get("is_private") or flight.get("is_gamenight")):


                now_jst = datetime.datetime.now(C.JST)
                is_late_night = now_jst.hour >= 22 or now_jst.hour < 7
                target_18 = now_jst.replace(hour=18, minute=0, second=0, microsecond=0)
                if now_jst.hour >= 22:
                    target_18 += datetime.timedelta(days=1)

                if is_late_night and target_18.timestamp() < start_ts:
                    flight["pending_customer_msg"] = True
                    flight["customer_msg_timestamp"] = target_18.timestamp()
                    flight["customer_msg_content"] = new_cust_content
                    flight["customer_message_id"] = None
                    C.global_db_dirty = True
                    status_log.append(f"Missing Customer Message Scheduled for <t:{int(target_18.timestamp())}:f> (scheduled for 18:00 due to late night)")
                else:
                    try:
                        c_msg = await C.post_customer_announcement(c_channel, flight, new_cust_content)
                        flight["customer_message_id"] = c_msg.id
                        flight["pending_customer_msg"] = False
                        C.global_db_dirty = True
                        status_log.append("Missing Customer Message Re-Sent (recovered immediately)")
                    except Exception as e:
                        status_log.append(f"Customer Message Send Failed: {e}")
        else:
            status_log.append("Customer channel not found (skipped)")


        if flight.get("event_url"):
            try:
                event = await C.get_flight_calendar_event(flight)
                if event is None:
                    status_log.append("Event Sync Failed: calendar event not found.")
                else:
                    kwargs = dict(start_time=datetime.datetime.fromtimestamp(start_ts, datetime.timezone.utc),
                                  end_time=datetime.datetime.fromtimestamp(end_ts, datetime.timezone.utc))
                    if not flight.get("is_gamenight"):
                        kwargs.update(name=C.build_flight_event_name(flight)[:100], location=origin[:100],
                                      description=C.build_flight_event_description(flight))
                    if image_bytes:
                        kwargs["image"] = image_bytes
                    await event.edit(**kwargs)
                    status_log.append("Discord Event Synced" + (" (with Image)" if image_bytes else " (No Image Update)"))
            except Exception as e:
                status_log.append(f"Event Sync Failed: {e}")


        if flight.get("briefing_thread_id") and not is_gn:
            try:
                th = C.client.get_channel(flight["briefing_thread_id"]) or await C.client.fetch_channel(flight["briefing_thread_id"])
                new_th_name = f"{flight['flight_code']} {origin}→{dest}"[:100]
                if th.name != new_th_name:
                    await th.edit(name=new_th_name)
                    status_log.append("Briefing Thread Renamed")
            except Exception as e:
                status_log.append(f"Briefing Thread Update Failed: {e}")


        try:
            await C.auto_publish_schedule()
        except Exception as e:
            status_log.append(f"Schedule Update Failed: {e}")

        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'**Update Complete for `{flight_code}`**\n' + '\n'.join(status_log))]))
    except Exception as e:
        traceback.print_exc()
        try:
            await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Critical Update Failed: {e}')]))
        except Exception:
            pass

@C.client.tree.command(name="join", description="Join your VC to read messages aloud (with translation), or send a server opening notice with flight_code")
@app_commands.describe(
    flight_code="Optional: send the server opening notice for this flight",
    flight_type="Flight type (used together with flight_code)"
)
@app_commands.choices(
    flight_type=[
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="Special", value="special")
    ]
)
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
async def join_server(interaction: discord.Interaction, flight_code: str = None, flight_type: str = "normal"):

    if flight_code is None:
        await interaction.response.defer(ephemeral=True, thinking=False)
        if interaction.guild is None:
            return await interaction.followup.send("This command works only in a guild.", ephemeral=True)
        voice = getattr(interaction.user, "voice", None)
        if not voice or not voice.channel:
            return await interaction.followup.send("Please join a voice channel first.", ephemeral=True)
        channel = voice.channel
        gid = interaction.guild.id
        if not C.voice_libraries_available():
            C.warn_voice_libraries_once()
            return await interaction.followup.send(
                "Voice libraries are missing (PyNaCl).\n"
                "Run `./venv/bin/pip install -r requirements.txt` and restart the bot.",
                ephemeral=True)
        try:
            vc = interaction.guild.voice_client
            if vc is None:
                vc = await channel.connect(reconnect=True)
            elif vc.channel and vc.channel.id != channel.id:
                await vc.move_to(channel)
            C.VOICE_CLIENTS[gid] = vc
            C.VOICE_TARGET_VC[gid] = channel.id
            targets = C.VOICE_TARGET_TEXT.setdefault(gid, set())
            targets.add(channel.id)

            cmd_ch = interaction.channel
            if cmd_ch is not None and getattr(cmd_ch, "guild", None) is not None:
                targets.add(cmd_ch.id)
            C.TTS_ENABLED[gid] = True
            if gid not in C.TTS_TASKS or C.TTS_TASKS[gid].done():
                C._get_tts_queue(gid)
                C.TTS_TASKS[gid] = asyncio.create_task(C._tts_queue_worker(gid))
            _names = ", ".join(
                f"#{ch.name}" for ch in (channel, cmd_ch)
                if ch is not None and getattr(ch, "name", None))
            print(f"[TTS] /join: guild={gid} vc={channel.name}({channel.id}) read_targets={sorted(targets)}")
            _warn = ""
            try:
                _perms = channel.permissions_for(interaction.guild.me)
                if not _perms.speak:
                    _warn = f"\n{C.EMOJI_NOTI_STR} The bot lacks the **Speak** permission in this voice channel. Please check the channel permissions."
                if not _perms.connect:
                    _warn = f"\n{C.EMOJI_NOTI_STR} The bot lacks the **Connect** permission in this voice channel."
            except Exception:
                pass
            return await interaction.followup.send(
                f"Joined voice channel: **{channel.name}**\n"
                f"Reading channels: {_names or channel.name}\n"
                "Messages will be read aloud." + _warn,
                ephemeral=True)
        except Exception as e:
            _msg = str(e)
            if "PyNaCl" in _msg:
                return await interaction.followup.send(
                    "Voice libraries are missing.\n"
                    "Run `./venv/bin/pip install -r requirements.txt` and restart the bot.\n"
                    f"({_msg})", ephemeral=True)
            return await interaction.followup.send(f"Failed to join the voice channel: {e}", ephemeral=True)


    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Error', f'Flight `{flight_code}` not found.', theme.DANGER), content=None), ephemeral=True)


    if flight.get("is_private"):
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Private flights have no customer check-in announcement.')]))

    roblox_link = flight.get("roblox_link", "")
    embed_color = C.get_embed_color(flight.get('color'))
    airline = flight.get('airline', 'Airline')
    destination = flight.get('destination', 'Unknown')


    type_prefix = ""
    if flight_type == "special":
        type_prefix = "**Special Flight**\n\n"

    channel_embed = discord.Embed(
        title=f"{airline} | {flight_code}",
        description=(
            f"{type_prefix}"
            f"Check-in for flight **{flight_code}** to {destination} has started.\n"
            f"Check-in for flight **{flight_code}** to *{destination}* has now opened for all passengers.\n\n"
            f"**Remember:**\n"
            f"- Have **all** required travel documents ready before travel.\n"
            f"  Please have your travel documents ready in advance.\n"
            f"- Travel in a manner that is acceptable.\n"
            f"  Please be considerate of other customers.\n"
            f"- Contact a member of staff if an issue arises.\n"
            f"  If you have any problems, please let a staff member know.\n\n"
            f"We wish you a pleasant flight with **Flight Hub**.\n"
            f"Enjoy a comfortable journey with us.\n\n"
            f"**Server Access:**\n"
            f"There is no server lock. You are free to join the server at any time.\n"
            f"There is no server lock. You may join at any time."
        ),
        color=embed_color
    )
    channel_embed.set_author(name="Travel Update")

    image_url, _ = await C.fetch_fresh_image_info(flight.get("source_channel_id"), flight.get("source_message_id"))
    if image_url:
        channel_embed.set_image(url=image_url)

    channel_view = discord.ui.View(timeout=None)
    if roblox_link and roblox_link.startswith("http"):
        channel_view.add_item(discord.ui.Button(
            label="Join Flight Hub",
            style=discord.ButtonStyle.link,
            url=roblox_link,
            emoji=discord.PartialEmoji.from_str(C.EMOJI_LINK_STR)
        ))
    else:
        channel_view.add_item(discord.ui.Button(
            label="Join Flight Hub",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            emoji=discord.PartialEmoji.from_str(C.EMOJI_LINK_STR)
        ))

    sent_msg = await C.client.get_channel(C.CUSTOMER_CHANNEL_ID).send(
        content=f"@here <@&{C.JOIN_NOTIFICATION_ROLE_ID}>",
        embed=channel_embed,
        view=channel_view
    )

    async def save_join_id():
        async with C.global_json_lock:
            target_idx = next(
                (i for i, f in enumerate(C.FLIGHT_LOG_CACHE) if f["flight_code"] == flight_code), -1)
            if target_idx != -1:
                C.FLIGHT_LOG_CACHE[target_idx]["join_message_id"] = sent_msg.id
            C.global_db_dirty = True

    await save_join_id()


    async def broadcast_dms():
        c_guild = C.client.get_guild(C.CUSTOMER_GUILD_ID)
        if not c_guild:
            print("Customer guild not found")
            return

        dm_count = 0
        for member in c_guild.members:
            if member.bot:
                continue

            role_ids = [r.id for r in member.roles]
            if C.DM_TARGET_ROLE_ID in role_ids and C.DM_STAFF_ROLE_ID not in role_ids and C.DM_EXCLUDE_ROLE_ID not in role_ids:
                try:
                    dm_content = (
                        f"**Boarding Pass | Special Flight {airline} {flight_code} (to {destination})**\n\n"
                        f"Your boarding for the special flight is now ready.\n"
                        f"Please join the flight server using the button or link below!\n\n"
                        f"Dear Passenger, your special flight is ready for boarding.\n"
                        f"Please join the flight server via the button or link below!"
                    )
                    if roblox_link and roblox_link.startswith("http"):
                        dm_content += f"\n\n**Link:** {roblox_link}"

                    dm_view = discord.ui.View(timeout=None)
                    if roblox_link and roblox_link.startswith("http"):
                        dm_view.add_item(discord.ui.Button(
                            label="Join Flight Hub",
                            style=discord.ButtonStyle.link,
                            url=roblox_link,
                            emoji=discord.PartialEmoji.from_str(C.EMOJI_LINK_STR)
                        ))

                    dm_embed = channel_embed.copy()
                    await member.send(content=dm_content, embed=dm_embed, view=dm_view)
                    dm_count += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"DM failed for {member.id} ({member.name}): {e}")

        print(f"DM broadcast complete: {dm_count} members notified")


    if flight_type == "special":
        C.client.loop.create_task(broadcast_dms())
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Sent! ')]))
    else:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Sent! ')]))

async def create_discord_recurring_event(guild_id, name, desc, start_ts, end_ts, location, freq_type, image_bytes=None):
    url = f"https://discord.com/api/v10/guilds/{guild_id}/scheduled-events"
    headers = {"Authorization": f"Bot {C.TOKEN}"}
    
    start_iso = datetime.datetime.fromtimestamp(start_ts, datetime.timezone.utc).isoformat()
    end_iso = datetime.datetime.fromtimestamp(end_ts, datetime.timezone.utc).isoformat()
    


    if freq_type == 1:
        freq = 3
        interval = 1
    elif freq_type == 2:
        freq = 2
        interval = 1
    elif freq_type == 3:
        freq = 2
        interval = 2
    else:
        freq = 2
        interval = 1
    
    payload = {
        "name": name,
        "privacy_level": 2,
        "scheduled_start_time": start_iso,
        "scheduled_end_time": end_iso,
        "description": desc,
        "entity_type": 3,
        "entity_metadata": {"location": location},
        "recurrence_rule": {"start": start_iso, "frequency": freq, "interval": interval}
    }
    
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        payload["image"] = f"data:image/jpeg;base64,{b64}"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status in (200, 201):
                data = await resp.json()
                return data.get("id"), f"https://discord.com/events/{guild_id}/{data.get('id')}"
            else:
                print(f"Recurring Event Error: {await resp.text()}")
                return None, None

async def process_recurring_creation(interaction, flight_code, equipment, frequency, staff_meet, pass_start, host_timezone, is_test=False):
    _blocked = C.db_write_blocked_message()
    if _blocked:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, _blocked)]))
    core_code = f"[TEST] {flight_code}" if is_test else flight_code
    save_flight_code = core_code

    async with C.global_json_lock:
        if any(f["flight_code"] == save_flight_code and not f.get("messages_deleted") for f in C.FLIGHT_LOG_CACHE):
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Flight `{save_flight_code}` is already in progress or registered as a recurring flight.')]))

    await C.ensure_templates_fresh()
    saved_route = C.FLIGHT_DB.get(flight_code)
    if not saved_route:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Template not found.')]))

    clean_equip = equipment.replace(" (Registered)", "").replace("(Registered)", "").strip()
    variant_data = None
    for k, v in saved_route.get("variants", {}).items():
        if k.lower() == clean_equip.lower():
            variant_data = v
            clean_equip = k
            break
    if not variant_data: return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No template found for the specified equipment.')]))

    tz_offset = C.parse_timezone_offset(host_timezone)
    staff_dt = C.calculate_jst_time(staff_meet.split()[0], staff_meet.split()[1] if " " in staff_meet else staff_meet, tz_offset)
    pass_dt = C.calculate_jst_time(staff_meet.split()[0], pass_start, tz_offset)

    if not staff_dt or not pass_dt: return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Invalid date format. (YYYY-MM-DD HH:MM)')]))
    if pass_dt < staff_dt: pass_dt += datetime.timedelta(days=1)
    end_dt = pass_dt + datetime.timedelta(hours=1)
    
    if pass_dt <= datetime.datetime.now(C.JST):
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Due to Discord limitations, the start time cannot be in the past.')]))

    p_jst = pass_dt.astimezone(C.JST)
    for f in ([] if is_test else C.FLIGHT_LOG_CACHE):
        if f.get("messages_deleted", False) or not C.is_customer_flight(f):
            continue
        f_start_ts = f.get("start_timestamp", 0)
        if f_start_ts == 0: continue
        f_jst = datetime.datetime.fromtimestamp(f_start_ts, tz=C.JST)

        gap_days = abs((p_jst.date() - f_jst.date()).days)
        if gap_days < C.FLIGHT_MIN_GAP_DAYS:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f"This is too close to flight `{f['flight_code']}` (gap: {gap_days} day(s)). Flights can only be held once a week.")]))

    now_ts = datetime.datetime.now().timestamp()
    active_count = sum(1 for f in C.FLIGHT_LOG_CACHE if f.get("end_timestamp", 0) > now_ts and not f.get("messages_deleted") and not f.get("queued_for_limit"))
    if active_count >= 5:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The active flight limit (5 slots) has been reached. Please create recurring flights once a slot is free.')]))

    image_url, image_bytes = await C.fetch_fresh_image_info(variant_data.get("source_channel_id"), variant_data.get("source_message_id"))
    airline = variant_data.get("airline", "Airline")

    guild_id = C.STAFF_GUILD_ID if is_test else C.CUSTOMER_GUILD_ID
    
    event_title = f"{flight_code} {saved_route['origin']}→{saved_route['destination']}"
    desc = f"`Host` <@{interaction.user.id}>\n`Origin` {saved_route['origin']}\n`Destination` {saved_route['destination']}\n> Information\n`Airline` {airline}\n`Aircraft` {clean_equip}\n`Classes` {variant_data.get('classes', 'Unknown')}"
    
    event_id, event_url = await create_discord_recurring_event(
        guild_id, event_title, desc, int(pass_dt.timestamp()), int(end_dt.timestamp()), 
        saved_route['origin'], frequency, image_bytes
    )

    if not event_id: return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Failed to create the calendar event. Please check permissions (and make sure the time is not in the past).')]))

    c_channel_id = C.CUSTOMER_CHANNEL_ID
    if is_test:
        c_guild = C.client.get_guild(C.CUSTOMER_GUILD_ID)
        cat = c_guild.get_channel(C.TEST_CUSTOMER_CATEGORY_ID)
        ch_name = f"test-{interaction.user.display_name.lower()}"
        test_ch = await c_guild.create_text_channel(name=ch_name, category=cat)
        c_channel_id = test_ch.id

    data = {
        "flight_code": save_flight_code,
        "origin": saved_route["origin"],
        "destination": saved_route["destination"],
        "equipment": clean_equip,
        "classes": variant_data.get("classes", "Unknown"),
        "airline": airline,
        "color": variant_data.get("color", "1B3444"),
        "roblox_link": variant_data.get("roblox_link", ""),
        "source_channel_id": variant_data.get("source_channel_id"),
        "source_message_id": variant_data.get("source_message_id"),
        "start_timestamp": int(pass_dt.timestamp()),
        "end_timestamp": int(end_dt.timestamp()),
        "staff_timestamp": int(staff_dt.timestamp()),
        "notify_20min_timestamp": int((staff_dt - datetime.timedelta(minutes=20)).timestamp()),
        "event_url": event_url,
        "master_event_id": event_id,
        "host_id": interaction.user.id,
        "staff_guild_id": C.STAFF_GUILD_ID,
        "staff_channel_id": C.STAFF_CHANNEL_ID if not is_test else C.TEST_STAFF_CHANNEL_ID,
        "customer_guild_id": guild_id,
        "customer_channel_id": c_channel_id,
        "mention_str": f"<@&{C.NOTIFICATION_ROLE_ID}>",
        "is_recurring": True,
        "recurring_freq": frequency,
        "child_spawned": False,
        "is_test": is_test,
        "accepted_users": [interaction.user.id],
        "declined_users": []
    }

    s_channel = C.client.get_channel(data["staff_channel_id"])
    staff_embed = discord.Embed(title=event_title, description="Recurring Operation", color=C.get_embed_color(data['color']))
    _creator_name = await C.get_server_display_name(interaction.user.id, C.STAFF_GUILD_ID, fallback=interaction.user.display_name)
    staff_embed.add_field(name="Host", value=_creator_name, inline=False)
    
    staff_embed.add_field(name="Route", value=f"{data['origin']} ➝ {data['destination']}", inline=False)
    staff_embed.add_field(name="Aircraft Equipment", value=data['equipment'], inline=False)
    staff_embed.add_field(name="Minimum Staff Needed", value=C.minimum_staff_text(), inline=False)

    staff_embed.add_field(name="Action", value=f"React to join.\n**Staff Briefing Time:** <t:{data['staff_timestamp']}:F>" + C.google_calendar_suffix(data, start_ts=data['staff_timestamp']), inline=False)
    staff_embed.add_field(name="Time", value=f"<t:{data['start_timestamp']}:F> - <t:{data['end_timestamp']}:t>" + C.google_calendar_suffix(data), inline=False)
    staff_embed.add_field(name=f"{C.EMOJI_CHECK_STR} Accepted (1)", value=f">>> {_creator_name}", inline=True)
    staff_embed.add_field(name=f"{C.EMOJI_X_STR} Declined (0)", value="-", inline=True)
    staff_embed.set_footer(text=f"Flight Code: {data['flight_code']} | Created by {_creator_name}")
    
    if image_url: staff_embed.set_image(url=image_url)
    
    staff_msg = await s_channel.send(content="**[RECURRING FLIGHT]**" if is_test else "@everyone", embed=staff_embed, view=C.RecurringFlightSignupView())
    data["staff_message_id"] = staff_msg.id

    c_channel = C.client.get_channel(data["customer_channel_id"])
    lock_ts = data["start_timestamp"] + 1200
    cust_msg_content = (
        f"{C.EMOJI_TAIL_STR} **Recurring Flight**\n"
        f"Flight code: {flight_code}\n"
        f"Airline: {airline}\n"
        f"Departure Airport: {data['origin']}\n"
        f"Arrival Airport: {data['destination']}\n"
        f"Date: <t:{data['start_timestamp']}:D>\n"
        f"Check-in Time: <t:{data['start_timestamp']}:t>\n"
        f"Server Lock: <t:{lock_ts}:t>\n"
        f"Equipment: {data['equipment']}\n"
        f"Classes: {data.get('classes', 'Unknown')}\n"
        f"{C.get_customer_mention_line(data)}"
        f"{C.EMOJI_LINK_STR} **[Discord Event Link]({event_url})**"
    )
    if is_test:
        cust_msg = await c_channel.send(content=cust_msg_content, suppress_embeds=True)
    else:
        cust_msg = await C.post_customer_announcement(c_channel, data, cust_msg_content)
    data["customer_message_id"] = cust_msg.id

    async with C.global_json_lock:


        if any(f.get("flight_code") == save_flight_code and not f.get("messages_deleted") for f in C.FLIGHT_LOG_CACHE):
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Flight `{save_flight_code}` is already in progress or registered as a recurring flight.')]))
        C.FLIGHT_LOG_CACHE.append(data)
        C.global_db_dirty = True






    await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Recurring flight created!\n**Calendar link:** {event_url}')]))

@C.client.tree.command(name="recurring_flight", description="Create a recurring flight (native Discord repeating event).")
@app_commands.describe(
    flight_code="Select the flight code",
    equipment="Aircraft type",
    frequency="Frequency",
    staff_meet_datetime="Meeting Time (YYYY-MM-DD HH:MM)",
    passenger_start_time="Start Time (HH:MM)",
    host_timezone="Timezone"
)
@app_commands.autocomplete(flight_code=C.flight_code_autocomplete, equipment=C.equipment_autocomplete)
@app_commands.choices(frequency=[
    app_commands.Choice(name="Daily", value=1),
    app_commands.Choice(name="Weekly", value=2),
    app_commands.Choice(name="Bi-Weekly", value=3)
])
@C.event_manager_only
async def recurring_flight_cmd(interaction: discord.Interaction, flight_code: str, equipment: str, frequency: int, staff_meet_datetime: str, passenger_start_time: str, host_timezone: str = "GMT+9"):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)
    await process_recurring_creation(interaction, flight_code, equipment, frequency, staff_meet_datetime, passenger_start_time, host_timezone, is_test=False)

@C.client.tree.command(name="recurring_flighttest", description="[TEST] Create a recurring flight (native Discord repeating event) on the test server.")
@app_commands.describe(
    flight_code="Select the flight code",
    equipment="Aircraft type",
    frequency="Frequency",
    staff_meet_datetime="Meeting Time (YYYY-MM-DD HH:MM)",
    passenger_start_time="Start Time (HH:MM)",
    host_timezone="Timezone"
)
@app_commands.autocomplete(flight_code=C.flight_code_autocomplete, equipment=C.equipment_autocomplete)
@app_commands.choices(frequency=[
    app_commands.Choice(name="Daily", value=1),
    app_commands.Choice(name="Weekly", value=2),
    app_commands.Choice(name="Bi-Weekly", value=3)
])
@C.event_manager_only
async def recurring_flighttest_cmd(interaction: discord.Interaction, flight_code: str, equipment: str, frequency: int, staff_meet_datetime: str, passenger_start_time: str, host_timezone: str = "GMT+9"):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)
    await process_recurring_creation(interaction, flight_code, equipment, frequency, staff_meet_datetime, passenger_start_time, host_timezone, is_test=True)
