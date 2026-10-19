import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import re
import traceback
import asyncio
import calendar

from . import core as C

_CHANNEL_CLEANUP_RUNNING = set()

async def _bg_cleanup_flight_channels(item: dict):
    try:
        await C.delete_flight_channels(item, archive=True)
        C.global_db_dirty = True
    except Exception as e:
        print(f"Background flight channel cleanup error ({item.get('flight_code')}): {e}")
    finally:
        _CHANNEL_CLEANUP_RUNNING.discard(item.get("flight_code"))

_ORPHAN_CHECKED_AT = {}
_VC_JOIN_ATTEMPT = {}

async def staff_message_is_gone(item: dict) -> bool:
    ch_id, msg_id = item.get("staff_channel_id"), item.get("staff_message_id")
    if not ch_id or not msg_id:
        return False
    ch = C.client.get_channel(ch_id)
    if ch is None:
        try:
            ch = await C.client.fetch_channel(ch_id)
        except Exception:
            return False
    try:
        await ch.fetch_message(msg_id)
        return False
    except discord.NotFound:
        return True
    except Exception:
        return False

@tasks.loop(minutes=1)
@C._resilient_task
async def task_manager():
    if C._AUTO_TEST_PAUSE:
        return
    if not C.data_ready(C.FLIGHT_LOG_CHANNEL_ID):
        return
    async with C.global_json_lock:
        now = datetime.datetime.now().timestamp()
        dirty = False
        schedule_needs_update = False


        active_count = sum(1 for f in C.FLIGHT_LOG_CACHE if f.get("end_timestamp", 0) > now and not f.get("messages_deleted") and not f.get("queued_for_limit") and not f.get("is_test"))
        

        if active_count < 5:
            queued_flights = [f for f in C.FLIGHT_LOG_CACHE if f.get("queued_for_limit")]
            if queued_flights:

                next_flight = queued_flights[0]
                await C.publish_queued_flight(next_flight)
                schedule_needs_update = True


        for item in sorted(C.FLIGHT_LOG_CACHE, key=lambda x: x.get("start_timestamp", 0)):


            if (item.get("flight_log_sent")
                    and item.get("flight_survey_deadline")
                    and not item.get("flight_survey_dispatched")
                    and not item.get("is_test")
                    and not item.get("selftest")
                    and not item.get("messages_deleted")):
                try:
                    C.client.loop.create_task(C.start_flight_survey(item))
                except Exception as e:
                    print(f"Flight survey dispatch scheduling error ({item.get('flight_code')}): {e}")




            if (item.get("is_gamenight") and not item.get("messages_deleted") and item.get("staff_message_id")
                    and now - _ORPHAN_CHECKED_AT.get(item.get("flight_code"), 0) >= 300):
                _ORPHAN_CHECKED_AT[item.get("flight_code")] = now
                try:
                    if await staff_message_is_gone(item):
                        print(f"Orphan game night cleanup: {item.get('flight_code')}")
                        await C.delete_flight_calendar_event(item)
                        if item.get("flight_channels"):
                            _ck = item.get("flight_code")
                            if _ck not in _CHANNEL_CLEANUP_RUNNING:
                                _CHANNEL_CLEANUP_RUNNING.add(_ck)
                                C.client.loop.create_task(_bg_cleanup_flight_channels(item))
                        C.FLIGHT_LOG_CACHE.remove(item)
                        dirty = True
                        schedule_needs_update = True
                        continue
                except Exception as e:
                    print(f"Orphan game night check error ({item.get('flight_code')}): {e}")


            try:
                if item.get("flight_channels") and item.get("flight_log_sent"):


                    _ck = item.get("flight_code")
                    if _ck not in _CHANNEL_CLEANUP_RUNNING:
                        _CHANNEL_CLEANUP_RUNNING.add(_ck)
                        C.client.loop.create_task(_bg_cleanup_flight_channels(item))
                elif (not item.get("flight_channels_created") and not item.get("flight_log_sent")
                        and item.get("briefing_thread_id")
                        and item.get("notify_20min_timestamp") is not None
                        and now >= item["notify_20min_timestamp"] and now < item.get("end_timestamp", 0)
                        and item.get("flight_channel_attempts", 0) < 5):

                    try:
                        if await C.create_flight_channels(item):
                            dirty = True
                        else:
                            item["flight_channel_attempts"] = item.get("flight_channel_attempts", 0) + 1
                    except Exception as e:
                        item["flight_channel_attempts"] = item.get("flight_channel_attempts", 0) + 1
                        print(f"Flight channel create error ({item.get('flight_code')}): {e}")
                elif item.get("flight_channels"):
                    before = item.get("flight_channels_sig")
                    await C.sync_flight_channel_perms(item)
                    if item.get("flight_channels_sig") != before:
                        dirty = True
                    if ((not item.get("flight_channel_button_posted")
                         or (not item.get("flight_channel_button_pinned") and item.get("flight_channel_pin_attempts", 0) < 3))
                            and await C.post_flight_channel_delete_button(item)):
                        dirty = True
            except Exception as e:
                print(f"Flight channel manage error ({item.get('flight_code')}): {e}")





            try:
                if (item.get("flight_channels") and not item.get("is_gamenight")
                        and not item.get("messages_deleted")
                        and item.get("staff_timestamp", 0) <= now < item.get("end_timestamp", 0) + 60):
                    _vc_info = item["flight_channels"]
                    _gid = _vc_info.get("guild")
                    _vcid = _vc_info.get("vc")
                    _guild = C.client.get_guild(_gid) if _gid else None
                    _cur = _guild.voice_client if _guild else None
                    _vc_ch = _guild.get_channel(_vcid) if (_guild and _vcid) else None
                    _has_human = bool(_vc_ch) and any(not m.bot for m in getattr(_vc_ch, "members", []))
                    if _guild and _vcid and not _cur and _has_human:
                        _ckey = f"vcjoin:{item.get('flight_code')}"
                        if now - _VC_JOIN_ATTEMPT.get(_ckey, 0) >= 60:
                            _VC_JOIN_ATTEMPT[_ckey] = now
                            C.client.loop.create_task(C.ensure_flight_voice_connection(item))
            except Exception as e:
                print(f"Flight VC auto-join schedule error ({item.get('flight_code')}): {e}")





            try:
                _end_ts = item.get("end_timestamp", 0)
                if (not item.get("flight_log_sent") and not item.get("flight_log_missing_notified")
                        and not item.get("is_gamenight") and not item.get("messages_deleted_by_cancel")
                        and _end_ts and _end_ts + 600 <= now < _end_ts + 43200):
                    item["flight_log_missing_notified"] = True
                    dirty = True
                    _code = item.get("flight_code", "?")
                    _need_brief = ("\n(The briefing sheet has not been created yet either. Please create it with `/briefing` first.)\n"
                                   "(The briefing sheet has not been created either, so please run `/briefing` first.)") if not item.get("briefing_sent") else ""
                    _text = (f"**{_code} Flight-log missing!**\n"
                             f"This flight ended more than 10 minutes ago, but the Flight-log has not been submitted yet.\n"
                             f"Please use the `/flight_log` command to submit it.\n"
                             f"10 minutes have passed since the flight ended and the flight log has not been submitted. Please submit it with `/flight_log`."
                             f"{_need_brief}")
                    _sent = False
                    try:
                        _host = C.client.get_user(item["host_id"]) or await C.client.fetch_user(item["host_id"])
                        await _host.send(_text)
                        _sent = True
                    except Exception as e:
                        print(f"Flight-log-missing DM error ({_code}): {e}")
                    if not _sent and item.get("briefing_thread_id"):
                        try:
                            _th = C.client.get_channel(item["briefing_thread_id"]) or await C.client.fetch_channel(item["briefing_thread_id"])
                            await _th.send(f"<@{item['host_id']}> {_text}")
                        except Exception as e:
                            print(f"Flight-log-missing thread notice error ({_code}): {e}")
            except Exception as e:
                print(f"Flight-log-missing check error ({item.get('flight_code')}): {e}")


            if item.get("is_recurring"):
                continue

            if now > item["end_timestamp"] and not item.get("messages_deleted"):
                try:
                    if s_ch := C.client.get_channel(item["staff_channel_id"]):
                        try:
                            await (await s_ch.fetch_message(item["staff_message_id"])).delete()
                        except:
                            pass
                    if c_ch := C.client.get_channel(item["customer_channel_id"]):
                        if item.get("customer_message_id"):
                            try:
                                await (await c_ch.fetch_message(item["customer_message_id"])).delete()
                            except:
                                pass
                    if item.get("is_custom"):
                        if src_ch := C.client.get_channel(item["source_channel_id"]):
                            try:
                                await (await src_ch.fetch_message(item["source_message_id"])).delete()
                            except:
                                pass
                    if item.get("event_url"):
                        try:
                            event_id = int(item["event_url"].split("/")[-1])

                            _evt_gid = C.STAFF_GUILD_ID if (item.get("is_private") or item.get("is_gamenight") or item.get("is_test")) else C.CUSTOMER_GUILD_ID
                            c_guild = C.client.get_guild(_evt_gid)
                            if c_guild:
                                event = await c_guild.fetch_scheduled_event(event_id)
                                await event.delete()
                        except:
                            pass
                except:
                    pass
                item["messages_deleted"] = True
                dirty = True
                schedule_needs_update = True






            if (item.get("is_gamenight") and item.get("messages_deleted")
                    and not item.get("flight_channels") and now > item["end_timestamp"]):

                try:
                    await C.delete_flight_calendar_event(item)
                except Exception as e:
                    print(f"Game night calendar cleanup error ({item.get('flight_code')}): {e}")
                C.FLIGHT_LOG_CACHE.remove(item)
                dirty = True
                schedule_needs_update = True
                continue

            if now > item["end_timestamp"] + 43200 and not item.get("cleanup_12h_done"):
                try:
                    c_ch = C.client.get_channel(item["customer_channel_id"])
                    if c_ch:
                        if item.get("join_message_id"):
                            try:
                                await (await c_ch.fetch_message(item["join_message_id"])).delete()
                            except:
                                pass
                        if item.get("cancel_message_id"):
                            try:
                                await (await c_ch.fetch_message(item["cancel_message_id"])).delete()
                            except:
                                pass
                        for d_id in item.get("delay_message_ids", []):
                            try:
                                await (await c_ch.fetch_message(d_id)).delete()
                            except:
                                pass
                except:
                    pass
                item["cleanup_12h_done"] = True

                if item.get("flight_channels"):
                    _ck = item.get("flight_code")
                    if _ck not in _CHANNEL_CLEANUP_RUNNING:
                        _CHANNEL_CLEANUP_RUNNING.add(_ck)
                        C.client.loop.create_task(_bg_cleanup_flight_channels(item))
                C.FLIGHT_LOG_CACHE.remove(item)
                dirty = True
                schedule_needs_update = True
                continue

            if item.get("cleanup_12h_done") or now > item["end_timestamp"] + 86400:
                if item.get("flight_channels"):
                    _ck = item.get("flight_code")
                    if _ck not in _CHANNEL_CLEANUP_RUNNING:
                        _CHANNEL_CLEANUP_RUNNING.add(_ck)
                        C.client.loop.create_task(_bg_cleanup_flight_channels(item))
                C.FLIGHT_LOG_CACHE.remove(item)
                dirty = True
                schedule_needs_update = True
                continue


            if (not item.get("briefing_sent") and not item.get("briefing_missing_notified")
                    and not item.get("is_gamenight")
                    and not item.get("messages_deleted")
                    and now >= item.get("notify_20min_timestamp", float("inf")) and now < item.get("start_timestamp", 0)):
                try:
                    host = C.client.get_user(item["host_id"]) or await C.client.fetch_user(item["host_id"])
                    await host.send(
                        f"**{item['flight_code']} Briefing Sheet missing!**\nPlease use the `/briefing` command to create and send it.")
                except Exception as e:
                    print(f"Briefing-missing DM error ({item.get('flight_code')}): {e}")
                item["briefing_missing_notified"] = True
                dirty = True




            if (not item.get("notified_20min")
                    and item.get("notify_20min_timestamp") is not None
                    and now >= item["notify_20min_timestamp"]):

                _notify_err = None
                if now < item["start_timestamp"]:
                    try:
                        if ch := C.client.get_channel(item["staff_channel_id"]):
                            msg = await ch.fetch_message(item["staff_message_id"])
                            guild = C.client.get_guild(item["staff_guild_id"])
                            attendee_mentions = []
                            attendee_members = []
                            for uid in item.get("accepted_users", []):
                                if guild and (member := guild.get_member(uid)):
                                    attendee_mentions.append(member.mention)
                                    attendee_members.append(member)
                                else:
                                    attendee_mentions.append(f"<@{uid}>")
                            mention_str = " ".join(attendee_mentions) if attendee_mentions else ""

                            embed_color = C.get_embed_color(item.get('color'))
                            notify_embed = discord.Embed(
                                title="REMINDER: Event starting 20min!",
                                description=f"**{item['flight_code']} {item.get('origin', 'Game Night')} --> {item.get('destination', 'Event')}**\n"
                                            f"**Staff Join Time:** <t:{item.get('staff_timestamp', 0)}:F>\n"
                                            f"Passenger Join: <t:{item['start_timestamp']}:t> - <t:{item['end_timestamp']}:t>",
                                color=embed_color
                            )
                            thread_name = f"{item['flight_code']} {item.get('origin', 'Game Night')}→{item.get('destination', 'Event')}"

                            thread = getattr(msg, "thread", None) or await msg.create_thread(name=thread_name, auto_archive_duration=60)
                            item["briefing_thread_id"] = thread.id
                            item["staff_start_notified"] = False
                            await C._cleanup_thread_created_notice(ch)
                            await thread.send(content=f"**Briefing Time!** {mention_str}", embed=notify_embed)


                            if not item.get("flight_channels_created") and not item.get("flight_log_sent"):
                                try:
                                    if not await C.create_flight_channels(item):
                                        item["flight_channel_attempts"] = item.get("flight_channel_attempts", 0) + 1
                                except Exception as e:
                                    item["flight_channel_attempts"] = item.get("flight_channel_attempts", 0) + 1
                                    print(f"Flight channel create error ({item.get('flight_code')}): {e}")

                            if host := C.client.get_user(item["host_id"]):
                                dm_embed = notify_embed.copy()
                                if attendee_members:
                                    attendee_info = [f"• {m.display_name}" for m in attendee_members]
                                    dm_embed.add_field(name="Attendees", value="\n".join(attendee_info), inline=False)
                                else:
                                    dm_embed.add_field(name="Attendees", value="No participants yet.", inline=False)
                                try:
                                    await host.send(content="**Flight Reminder**", embed=dm_embed)
                                except:
                                    pass

                    except Exception as e:
                        _notify_err = e
                        print(f"20min thread/notify error ({item.get('flight_code')}): {e}")

                if _notify_err is not None:
                    item["notify_20min_attempts"] = item.get("notify_20min_attempts", 0) + 1
                if _notify_err is None or item.get("notify_20min_attempts", 0) >= 3:
                    item["notified_20min"] = True
                dirty = True


            if (item.get("briefing_thread_id") and not item.get("staff_start_notified")
                    and item.get("staff_timestamp") and now >= item["staff_timestamp"]):
                if now < item.get("end_timestamp", 0):
                    try:
                        await C.send_staff_start_notice(item)
                    except Exception as e:
                        print(f"Staff start notice error ({item.get('flight_code')}): {e}")
                item["staff_start_notified"] = True
                dirty = True

            if item.get("pending_customer_msg") and now >= item.get("customer_msg_timestamp", 0):
                _announce_failed = False

                if now < item["start_timestamp"]:
                    try:
                        if c_ch := C.client.get_channel(item["customer_channel_id"]):

                            already_sent = False
                            async for hist_msg in c_ch.history(limit=30):
                                if hist_msg.author == C.client.user and (f"Flight code: {item['flight_code']}" in hist_msg.content
                                                           or f"Operation name: {item['flight_code']}" in hist_msg.content):
                                    already_sent = True
                                    item["customer_message_id"] = hist_msg.id
                                    break
                            

                            if not already_sent:

                                if item.get("customer_msg_content"):
                                    sent = await C.post_customer_announcement(c_ch, item, item["customer_msg_content"])
                                    item["customer_message_id"] = sent.id
                    except Exception as e:

                        print(f"Scheduled customer announce error ({item.get('flight_code')}): {e}")
                        _announce_failed = True
                if not _announce_failed:
                    item["pending_customer_msg"] = False
                dirty = True
                schedule_needs_update = True

        loa_dirty = False
        staff_guild = C.client.get_guild(C.STAFF_GUILD_ID)
        log_channel = C.client.get_channel(C.LOA_TRACK_CHANNEL_ID)
        
        for uid_str, data in list(C.LOA_CACHE.items()):
            uid = int(uid_str)

            if data["status"] == "pending" and now >= data["start_timestamp"]:
                if staff_guild:
                    member = staff_guild.get_member(uid)
                    success = await C.activate_loa(uid, staff_guild)
                    if success:
                        loa_dirty = True
                        if member and log_channel:

                            embed = discord.Embed(title="Leave Processing Notice", description=f"{member.mention}'s leave processing has started.", color=discord.Color.blue())
                            embed.add_field(name="Target User", value=f"{member.display_name} (`{member.id}`)", inline=False)
                            embed.add_field(name="Period", value=f"<t:{data['start_timestamp']}:d> - <t:{data['end_timestamp']}:d>", inline=False)
                            embed.add_field(name="Reason", value=data.get('reason', 'None'), inline=False)
                            await log_channel.send(view=C.embed_to_v2_layout(embed))

                            try:
                                dm_embed = discord.Embed(
                                    title="Leave Start Notice", 
                                    description="The scheduled time has arrived. Your roles were temporarily removed and you have entered leave mode.", 
                                    color=discord.Color.orange()
                                )
                                dm_embed.add_field(name="Expected return", value=f"<t:{data['end_timestamp']}:F>", inline=False)
                                await member.send(view=C.embed_to_v2_layout(dm_embed))
                            except: pass


            elif data["status"] == "active" and now >= data["end_timestamp"]:
                if staff_guild:
                    member = staff_guild.get_member(uid)
                    success = await C.deactivate_loa(uid, staff_guild)
                    if success:
                        loa_dirty = True
                        await C.record_loa_return(uid)
                        if member and log_channel:

                            embed = discord.Embed(title="Leave End Notice", description=f"{member.mention}'s leave has ended and roles were restored.", color=discord.Color.orange())
                            embed.add_field(name="Target User", value=f"{member.display_name} (`{member.id}`)", inline=False)
                            await log_channel.send(view=C.embed_to_v2_layout(embed))

                            try:
                                dm_embed = discord.Embed(
                                    title="Leave End Notice", 
                                    description="Your leave has ended at the scheduled time.\nYour original roles and nickname were restored. Welcome back!", 
                                    color=discord.Color.green()
                                )
                                await member.send(view=C.embed_to_v2_layout(dm_embed))
                            except: pass

        if loa_dirty:
            C.client.loop.create_task(C.save_loa_tracking())
    

        if dirty:
            C.global_db_dirty = True


        if schedule_needs_update:
            try:
                await C.auto_publish_schedule()
            except Exception as e:
                print(f"Schedule update error in task_manager: {e}")

@tasks.loop(hours=24)
@C._resilient_task
async def daily_db_refresh():
    if C._AUTO_TEST_PAUSE:
        return
    print("[Daily Task] Refreshing the database and image expiry...")
    await C.update_db_cache()
    print("Daily refresh complete.")

@tasks.loop(time=datetime.time(hour=12, minute=0, tzinfo=C.JST))
@C._resilient_task
async def auto_remind_task():
    if C._AUTO_TEST_PAUSE:
        return
    if not await C.wait_for_data(C.REMIND_TRACK_CHANNEL_ID, C.LOA_TRACK_CHANNEL_ID):
        print("auto_remind_task skipped: remind/LOA data could not be loaded (prevents duplicate reminders).")
        return
    jst_now = datetime.datetime.now(C.JST)
    

    if C.remind_tracking_cache.get("month") != jst_now.month:
        C.remind_tracking_cache["month"] = jst_now.month
        C.remind_tracking_cache["users"] = []
        await C.save_remind_tracking()


    _, last_day = calendar.monthrange(jst_now.year, jst_now.month)
    target_day = last_day - 14

    if jst_now.day != target_day:
        return

    print("[Auto Task] Starting the automatic reminder two weeks before month-end...")
    
    participated_users = set()
    channels_to_check = [C.FLIGHT_LOG_HISTORY_CHANNEL_ID, C.MANUAL_LOG_CHANNEL_ID]
    start_of_month_utc = jst_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc)

    for ch_id in channels_to_check:
        ch = C.client.get_channel(ch_id)
        if not ch: continue
        try:
            async for msg in ch.history(limit=1000, after=start_of_month_utc):
                parsed = C.parse_log_message(msg)
                if parsed:
                    for uid in parsed["participants"]:
                        participated_users.add(uid)
        except:
            pass

    target_role_ids = [C.ROLE_FLIGHT_OPS, C.ROLE_CABIN_CREWS, C.ROLE_GROUND_OPS]
    target_role_ids.extend(C.ROLE_BUS_DRIVERS)
    
    staff_guild = C.client.get_guild(C.STAFF_GUILD_ID)
    if not staff_guild: return

    target_members = []
    for member in staff_guild.members:
        if member.bot: continue
        role_ids = [r.id for r in member.roles]
        if any(rid in role_ids for rid in C.EXCLUDE_REMIND_ROLE_IDS):
            continue


        if C.is_exempt_from_flight_reminder(member, jst_now):
            continue
        
        has_target_role = any(r_id in role_ids for r_id in target_role_ids)
        if has_target_role and member.id not in participated_users and member.id not in C.remind_tracking_cache["users"]:
            target_members.append(member)

    if not target_members:
        return

    end_of_month = (jst_now.replace(day=1) + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(seconds=1)
    upcoming_flights = [f for f in C.FLIGHT_LOG_CACHE if f["start_timestamp"] >= jst_now.timestamp() and f["start_timestamp"] <= end_of_month.timestamp()]
    upcoming_flights.sort(key=lambda x: x["start_timestamp"])

    schedule_text = ""
    for f in upcoming_flights:
        ts = int(f["start_timestamp"])
        staff_msg_link = f"https://discord.com/channels/{C.STAFF_GUILD_ID}/{C.STAFF_CHANNEL_ID}/{f['staff_message_id']}"
        if f.get("is_bus"):
            schedule_text += f"**[{f['flight_code']}]({staff_msg_link})** (<t:{ts}:f>) - Route: {f['origin']}\n"
        else:
            schedule_text += f"**[{f['flight_code']}]({staff_msg_link})** (<t:{ts}:f>) - {f['origin']} ➝ {f.get('destination', 'Unknown')}\n"
            
    if not schedule_text:
        schedule_text = "*No upcoming flights are scheduled for the rest of this month.*\n"

    month = jst_now.month
    desc = (
        f"Thank you for your continued activity.\nNo flight participation has been recorded for you this month ({month}).\n"
        f"To meet the activity requirement, please consider joining one of the flights below.\n\n"
        f"**Upcoming Flights This Month**\n{schedule_text}\n"
    )
    
    disclaimer = (
        "Please make sure to attend flights.\n"
        "This reminder may also reach staff on an approved leave of absence (LOA); if so, please disregard it.\n"
        "This reminder is sent automatically. If you received it by mistake, please open a ticket to let us know."
    )
    desc += f"\n**Notes**\n{disclaimer}"
    
    embed = discord.Embed(title=f"Flight Participation Reminder ({month})", description=desc, color=discord.Color.orange())
    embed.set_footer(text="Flight Hub")

    success_count = 0
    for member in target_members:
        try:
            await member.send(embed=embed)
            success_count += 1
            C.remind_tracking_cache["users"].append(member.id)
            await asyncio.sleep(0.5)
        except:
            pass
            
    await C.save_remind_tracking()

@C.client.event
async def on_app_command_completion(interaction: discord.Interaction, command):
    return

@C.client.event
async def on_voice_state_update(member, before, after):
    try:
        gid = member.guild.id


        if member.id == C.client.user.id:
            if after.channel is None:

                C._clear_voice_state(gid)
            else:

                C.VOICE_CLIENTS[gid] = member.guild.voice_client
                C.VOICE_TARGET_VC[gid] = after.channel.id
                C.VOICE_TARGET_TEXT.setdefault(gid, set()).add(after.channel.id)
            return


        if after.channel is not None:
            joined_id = after.channel.id
            target_flight = None
            for f in C.FLIGHT_LOG_CACHE:
                info = f.get("flight_channels") or {}
                if info.get("vc") == joined_id and not f.get("is_gamenight"):
                    target_flight = f
                    break
            if target_flight is not None:
                vc = member.guild.voice_client
                already_here = (vc is not None and vc.channel and vc.channel.id == joined_id)
                busy_elsewhere = (member.guild.me.voice and member.guild.me.voice.channel
                                  and member.guild.me.voice.channel.id != joined_id)
                if not already_here and not busy_elsewhere:
                    asyncio.create_task(C.ensure_flight_voice_connection(target_flight))


        await C.maybe_auto_leave_voice(member.guild, before, after)
    except Exception:
        pass


@C.client.event
async def on_ready():
    if C.global_json_lock is None:
        C.global_json_lock = asyncio.Lock()
    
    print(f'Logged in as {C.client.user}')




    if not C.LOAD_STATE["initialized"]:
        try:
            await C.load_all_data()
        except Exception:
            print("load_all_data crashed unexpectedly (startup continues):")
            traceback.print_exc()
        if C.LOAD_STATUS.get("Flight log (DB)", {}).get("ok"):
            try:
                upg = await C.v14_upgrade_data()
                print(f"V14 upgrade: {upg['migrated']}/{upg['total']} records converted, "
                      f"{upg['threads']} threads recovered, {upg['mention_restored']} mention records restored.")
            except Exception:
                traceback.print_exc()
        C.LOAD_STATE["initialized"] = True
    elif C.load_problems():

        await C.load_all_data(only_failed=True)
    C.sync_last_mention_from_cache()
    if C.load_problems():
        await C.report_load_problems()
        C.client.loop.create_task(C.retry_failed_loads_forever())


    def _safe_add_view(factory, label):
        try:
            C.client.add_view(factory())
        except Exception as e:
            print(f"add_view failed ({label}): {e}")
    _safe_add_view(C.FlightSignupView, "FlightSignupView")
    _safe_add_view(C.FlightChannelDeleteView, "FlightChannelDeleteView")
    _safe_add_view(C.ReflectionView, "ReflectionView")
    _safe_add_view(lambda: C.PersistentCustomerView(link_url=None, roblox_url=None), "PersistentCustomerView")
    _safe_add_view(C.FlightAppView, "FlightAppView")
    _safe_add_view(C.FlightAppAutoCancelView, "FlightAppAutoCancelView")
    try:
        C.client.add_dynamic_items(C.SurveyRatingItem, C.SurveyCommentItem, C.SurveyDoneItem)
    except Exception as e:
        print(f"add_dynamic_items failed (survey): {e}")
    _safe_add_view(C.EvaluationDMView, "EvaluationDMView")
    now = datetime.datetime.now().timestamp()
    active_flights = [f for f in C.FLIGHT_LOG_CACHE if f.get("end_timestamp", 0) > now]
    active_flights.sort(key=lambda x: x.get("start_timestamp", 0))
    _safe_add_view(lambda: C.FlightListView(active_flights), "FlightListView")

    if not task_manager.is_running():
        task_manager.start()
    if not C.quick_save_task.is_running():
        C.quick_save_task.start()
    if not daily_db_refresh.is_running():
        daily_db_refresh.start()
    if not auto_remind_task.is_running(): 
        auto_remind_task.start()
    if not C.check_expired_applications.is_running():
        C.check_expired_applications.start()
    if not C.process_evaluations_task.is_running():
        C.process_evaluations_task.start()
    if not C.recurring_spawner_task.is_running():
        C.recurring_spawner_task.start()
    try:
        from . import v2_features as _v2
        _v2.register(C.client)
    except Exception as e:
        print(f"v2 startup failed: {e}")

    try:
        status_emoji = discord.PartialEmoji.from_str(C.EMOJI_LINK_STR)
        activity = discord.CustomActivity(name="Join Flight Hub", emoji=status_emoji)
        await C.client.change_presence(status=discord.Status.online, activity=activity)
    except Exception as e:
        print(f"Custom Status Setup Error: {e}")
        fallback = discord.Activity(type=discord.ActivityType.playing, name="Join Flight Hub")
        await C.client.change_presence(status=discord.Status.online, activity=fallback)



    if C.LOAD_STATE.get("commands_synced"):
        print("Reconnected: command sync skipped (already synced).")
    else:
        all_commands = [c for c in C.client.tree.get_commands()]
        try:
            C.client.tree.clear_commands(guild=None)
            await C.client.tree.sync()
        except Exception as e:
            print(f"Global command cleanup error: {e}")
        finally:
            for cmd in all_commands:
                if C.client.tree.get_command(cmd.name) is None:
                    C.client.tree.add_command(cmd)
        synced_ok, synced_ng = [], []
        try:


            C.sanitize_command_descriptions()
        except Exception as e:
            print(f"Command description sanitize error: {e}")
        for _label, _guild in (("staff", C.STAFF_GUILD), ("customer", C.CUSTOMER_GUILD)):
            try:
                C.client.tree.copy_global_to(guild=_guild)
                _cmds = await C.client.tree.sync(guild=_guild)
                synced_ok.append(f"{_label}={len(_cmds)}")
            except Exception as e:
                synced_ng.append(f"{_label}: {e}")
                traceback.print_exc()
        print(f"Commands synced: {', '.join(synced_ok) or 'none'}" + (f" | FAILED: {' / '.join(synced_ng)}" if synced_ng else ""))
        try:


            for _w in await C.setup_event_manager_command_permissions():
                print(f"[Command visibility] {_w}")
        except Exception as e:
            print(f"Event manager command permissions error: {e}")
        try:
            for _w in C.check_command_visibility_roles():
                print(f"[Command visibility] {_w}")
        except Exception as e:
            print(f"Command visibility check error: {e}")
        if synced_ok and not synced_ng:
            C.LOAD_STATE["commands_synced"] = True
    print(f"Bot is ready. Local slash commands: {len(C.client.tree.get_commands())}")

@C.client.tree.error
async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, C._TestModeBlocked):
        return
    traceback.print_exception(type(error), error, error.__traceback__)
    orig = getattr(error, "original", error)
    if isinstance(error, app_commands.CommandNotFound):
        msg = "This command is not registered with the bot. Discord may still be syncing commands right after startup; please wait about a minute and try again."
    elif isinstance(error, (app_commands.CheckFailure, app_commands.MissingRole, app_commands.MissingPermissions)):
        msg = "You don't have permission to use this command."
    elif isinstance(orig, AttributeError) and "NoneType" in str(orig) and "lock" in str(orig).lower():
        msg = "The bot is still starting up. Please wait a moment and try again."
    else:
        msg = (f"An error occurred while running the command: `{type(orig).__name__}: {str(orig)[:200]}`\n"
               "Please contact an administrator.")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, msg)]))
        else:
            await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, msg)]))
    except Exception:
        pass

SYSTEM_NOTICE_CLEANUP_CHANNEL_IDS: set = set()

def _is_system_notice_cleanup_channel(channel) -> bool:
    try:
        cid = getattr(channel, "id", None)
        parent_id = getattr(channel, "parent_id", None)
        ids = {i for i in (cid, parent_id) if i}
        if ids & SYSTEM_NOTICE_CLEANUP_CHANNEL_IDS:
            return True
        for f in C.FLIGHT_LOG_CACHE:
            fc = f.get("flight_channels") or {}
            managed = {fc.get("chat"), fc.get("vc"),
                       f.get("staff_channel_id"), f.get("customer_channel_id")}
            if ids & {i for i in managed if i}:
                return True
    except Exception:
        return False
    return False

@C.client.event
async def on_message(message):


    if getattr(message, "guild", None) is not None and message.type in (
            discord.MessageType.pins_add, discord.MessageType.thread_created):
        try:
            if message.author == C.client.user or _is_system_notice_cleanup_channel(message.channel):
                await message.delete()
                return
        except discord.Forbidden:
            return
        except Exception:
            pass

    if message.author.bot:
        return


    try:
        gid = message.guild.id if message.guild else None
        if gid and C.TTS_ENABLED.get(gid) and message.guild.voice_client is not None:
            targets = C.VOICE_TARGET_TEXT.get(gid) or set()
            if message.channel.id in targets:
                text = message.clean_content
                if text and len(text) < 150:
                    import asyncio
                    _t = asyncio.create_task(C._tts_enqueue_bilingual(gid, text))
                    C.TTS_PENDING.add(_t)
                    _t.add_done_callback(C.TTS_PENDING.discard)
    except Exception:
        pass

    if message.channel.id == C.FLIGHT_APP_CHANNEL_ID:
        try:
            await message.delete()
        except:
            pass
        return


    if message.channel.id == C.COMMAND_CHANNEL_ID and message.content.startswith('.dm '):
        lines = message.content.split('\n', 1)
        if len(lines) < 2:
            await message.channel.send("No message found. Please add a line break and type your message.")
            return

        target_str = lines[0][4:].strip()
        content_text = lines[1]

        target_user = await C.get_target_user(C.client, target_str)

        if not target_user:
            err_embed = discord.Embed(description=f"User `{target_str}` not found.", color=discord.Color.red())
            await message.channel.send(embed=err_embed)
            return

        dm_embed = discord.Embed(description=content_text, color=discord.Color.dark_blue())
        dm_embed.add_field(
            name="Action Required",
            value="Please click the button below to submit your reflection.",
            inline=False
        )

        view = C.ReflectionView()

        try:
            dm_msg = await target_user.send(embed=dm_embed, view=view)
            C.dm_message_cache[message.id] = dm_msg

            display_name = getattr(target_user, 'display_name', target_user.name)
            success_embed = discord.Embed(description=f"Successfully sent to ***{display_name}***.",
                                          color=0x43b581)
            await message.channel.send(embed=success_embed)

        except discord.Forbidden:
            display_name = getattr(target_user, 'display_name', target_user.name)
            forbidden_embed = discord.Embed(
                description=f"Cannot send DM to ***{display_name}*** (DMs are disabled or no shared servers).",
                color=discord.Color.red())
            await message.channel.send(embed=forbidden_embed)
        return


    if message.channel.id == C.FLIGHT_INPUT_CHANNEL_ID:
        if not C.is_event_manager_or_chief(message.author):
            return
        if not message.attachments:
            return await message.channel.send("Image missing.", delete_after=5)
        try:
            raw_text = message.content.replace("**", "")
            lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
            parse_data = {}
            key_map = {
                "Origin": "origin", "Destination": "destination",
                "Aircraft": "equipment", "Class": "classes",
                "Start Time": "passenger_time_str",
                "Timezone": "host_timezone_str",
                "Airport": "roblox_link", "Airline": "airline",
                "Color": "color",
                "Bus": "equipment"
            }
            for line in lines:
                clean_line = line.lstrip('>').strip()
                if ':' in clean_line:
                    key, val = clean_line.split(':', 1)
                elif ':' in clean_line:
                    key, val = clean_line.split(':', 1)
                else:
                    if "Flight Information" in clean_line:
                        continue

                    if "flight_code" not in parse_data and (re.match(r'^[A-Za-z]{2,3}\d+$', clean_line) or "Transport" in clean_line or "Bus" in clean_line):
                        parse_data["flight_code"] = clean_line
                    continue
                key = key.strip()
                val = val.strip()
                if key in key_map:
                    parse_data[key_map[key]] = val

            parse_data.setdefault("airline", "Airline")
            parse_data.setdefault("color", "1B3444")
            if "color" in parse_data:
                parse_data["color"] = parse_data["color"].replace("#", "")


            fc = parse_data.get("flight_code", "")
            if "Transport" in fc or "Bus" in fc:
                parse_data.setdefault("destination", "")
                parse_data.setdefault("classes", "")
                required_keys = ["flight_code", "origin", "equipment", "roblox_link"]
            else:
                required_keys = ["flight_code", "origin", "destination", "equipment", "classes", "roblox_link"]

            has_static = all(k in parse_data for k in required_keys)
            has_time = all(
                k in parse_data for k in ["staff_meet_datetime_str", "passenger_time_str", "host_timezone_str"])
            image_bytes = await message.attachments[0].read()
            saved_url = message.attachments[0].url

            if has_static and has_time:
                parse_data["source_channel_id"] = message.channel.id
                parse_data["source_message_id"] = message.id
                parse_data["is_custom"] = False
                success, result_msg = await C.process_flight_creation(message.author, parse_data, image_bytes, saved_url)
                if success:
                    await message.channel.send(
                        embed=C.create_info_embed("Created via Message", result_msg, discord.Color.green()))
                else:
                    await message.channel.send(
                        embed=C.create_info_embed("Creation Failed", result_msg, discord.Color.red()))
            elif has_static:
                if parse_data["flight_code"] not in C.FLIGHT_DB:
                    C.FLIGHT_DB[parse_data["flight_code"]] = {"origin": parse_data["origin"],
                                                            "destination": parse_data["destination"], "variants": {}}
                C.FLIGHT_DB[parse_data["flight_code"]]["variants"][parse_data["equipment"]] = {
                    "classes": parse_data["classes"],
                    "roblox_link": parse_data["roblox_link"],
                    "airline": parse_data["airline"],
                    "color": parse_data["color"],
                    "source_channel_id": message.channel.id,
                    "source_message_id": message.id
                }
                await C.update_db_cache()
                await message.channel.send(
                    embed=C.create_info_embed("Template Saved",
                                           f"Route info for `{parse_data['flight_code']}` registered.\nEquipment: {parse_data['equipment']}\nAirline: {parse_data['airline']}",
                                           discord.Color.blue()), delete_after=10)
            else:
                missing = [k for k in required_keys if k not in parse_data]
                await message.channel.send(f"Missing info for template: {', '.join(missing)}", delete_after=10)
        except Exception as e:
            await message.channel.send(f"Error: {e}", delete_after=5)

@C.client.event
async def on_message_edit(before, after):
    if after.author.bot or after.channel.id != C.COMMAND_CHANNEL_ID:
        return

    if after.id in C.dm_message_cache and after.content.startswith('.dm '):
        lines = after.content.split('\n', 1)
        if len(lines) < 2:
            return

        content_text = lines[1]

        new_dm_embed = discord.Embed(description=content_text, color=discord.Color.dark_blue())
        new_dm_embed.add_field(
            name="Action Required (Edited)",
            value="Please click the button below to submit your reflection.",
            inline=False
        )

        dm_msg = C.dm_message_cache[after.id]
        try:
            await dm_msg.edit(embed=new_dm_embed, view=C.ReflectionView())
        except Exception as e:
            print(f"Failed to edit DM: {e}")

async def all_equipment_autocomplete(interaction: discord.Interaction, current: str):
    unique_eqs = set()
    for route_data in C.FLIGHT_DB.values():
        for eq in route_data.get("variants", {}).keys():
            unique_eqs.add(eq)
            
    choices = []
    for eq in sorted(list(unique_eqs)):
        if current.lower() in eq.lower():
            choices.append(app_commands.Choice(name=eq, value=eq))
            
    return choices[:25]

async def help_command_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=f"{data.get('emoji', '•')} {data['name']}", value=key)
        for key, data in C.HELP_DATA.items()
        if current.lower() in data["name"].lower()
    ][:25]

@C.client.tree.command(name="aircraft_guide", description="Aircraft guide: shows routes and details for a selected aircraft.")
@app_commands.describe(equipment="Aircraft name to search for")
@app_commands.autocomplete(equipment=all_equipment_autocomplete)
async def aircraft_guide_cmd(interaction: discord.Interaction, equipment: str):

    await interaction.response.defer()
    
    routes = []
    airlines = set()
    classes_set = set()
    image_url = None
    color_hex = "1B3444"
    

    for fc, route_data in C.FLIGHT_DB.items():

        if "Transport" in fc or "Bus" in fc:
            continue
            
        variants = route_data.get("variants", {})
        for eq, v_data in variants.items():
            if eq.lower() == equipment.lower():

                origin = route_data.get("origin", "Unknown")
                dest = route_data.get("destination", "Unknown")
                routes.append(f"**{fc}** : {origin} ➝ {dest}")
                
                airlines.add(v_data.get("airline", "Airline"))
                classes_set.add(v_data.get("classes", "Unknown"))
                

                if not image_url:
                    src_ch = v_data.get("source_channel_id")
                    src_msg = v_data.get("source_message_id")
                    color_hex = v_data.get("color", "1B3444")
                    image_url, _ = await C.fetch_fresh_image_info(src_ch, src_msg)
    
    if not routes:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'No route data found for equipment `{equipment}`.')]))
        

    airlines_str = " / ".join(list(airlines))
    classes_str = " / ".join(list(classes_set))
    

    embed = discord.Embed(
        title=f"Fleet Guide: {equipment}",
        description=f"**Operating Airline(s):** {airlines_str}\n**Cabin Class(es):** {classes_str}",
        color=C.get_embed_color(color_hex)
    )
    

    route_text = "\n".join(routes)
    if len(route_text) > 1024:
        route_text = route_text[:1000] + "\n...and more"
    
    embed.add_field(name="Destinations", value=route_text, inline=False)
    
    if image_url:
        embed.set_image(url=image_url)
        
    embed.set_footer(text="Flight Hub")
    

    await interaction.followup.send(view=C.embed_to_v2_layout(embed, content=None))

@C.client.tree.command(name="help", description="Show bot command help.")
@app_commands.describe(command="Select a command to view details")
@app_commands.autocomplete(command=help_command_autocomplete)
async def help_command(interaction: discord.Interaction, command: str = None):
    command_key = command if command in C.HELP_DATA else None
    view = C.HelpView(command_key, member=interaction.user)
    await interaction.response.send_message(view=view, ephemeral=True)

@C.client.tree.command(name="publish_schedule", description="Force publish the schedule to designated channels.")
@C.event_manager_only
async def publish_schedule(interaction: discord.Interaction):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await C.auto_publish_schedule()
    await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Schedule published.')]))

@C.client.tree.command(name="flights", description="Show active flight list.")
async def flights_list(interaction: discord.Interaction):
    now = datetime.datetime.now().timestamp()
    active_flights = [f for f in C.FLIGHT_LOG_CACHE if f["end_timestamp"] > now]
    active_flights.sort(key=lambda x: x["start_timestamp"])

    if not active_flights:
        return await interaction.response.send_message(view=C.embed_to_v2_layout(C.create_info_embed('Info', 'No active flights found.', discord.Color.blue()), content=None), ephemeral=True)

    view = C.FlightListView(active_flights)
    embed = discord.Embed(title="Active Flights", description="Please select a flight from the menu below.",
                          color=C.EMBED_COLOR)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@C.loa_group.command(name="apply", description="Reserve a leave of absence. Roles are removed/restored automatically at the scheduled time.")
@app_commands.describe(
    start_date="Start date/time (e.g. 2026-08-01 or 2026-08-01 12:00)",
    end_date="End date/time (e.g. 2027-08-01 or 2028-08-01 12:00). Multi-year spans are allowed.",
    reason="Reason (optional)",
    target_user="[Admin] Target user to file this on behalf of (optional)"
)
async def loa_apply_cmd(interaction: discord.Interaction, start_date: str, end_date: str, reason: str = "Not provided", target_user: discord.Member = None):
    if interaction.guild_id != C.STAFF_GUILD_ID:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This can only be used on the staff server.')]))
    

    target = target_user or interaction.user
    

    if target != interaction.user:
        if C.LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to submit leave on behalf of others.')]))

    start_dt = C.parse_loa_datetime(start_date)
    end_dt = C.parse_loa_datetime(end_date)
    
    if not start_dt or not end_dt:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Invalid date format. Please use `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`.')]))
    

    now_dt = datetime.datetime.now(C.JST)
    if start_dt < now_dt:
        start_dt = now_dt
        
    if end_dt <= start_dt:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The end time must be after the start time.')]))
        
    uid_str = str(target.id)
    if uid_str in C.LOA_CACHE:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'{target.mention} already has a scheduled or active leave. Please cancel it first with `/loa return` or `/loa cancel`.')]))

    C.LOA_CACHE[uid_str] = {
        "status": "pending",
        "start_timestamp": int(start_dt.timestamp()),
        "end_timestamp": int(end_dt.timestamp()),
        "reason": reason,
        "original_role_ids": [],
        "original_nick": ""
    }
    
    await C.save_loa_tracking()
    

    embed = discord.Embed(title="Leave Request (Scheduled)", color=discord.Color.green())
    embed.add_field(name="Target User", value=target.mention, inline=False)
    embed.add_field(name="Start", value=f"<t:{int(start_dt.timestamp())}:F>", inline=False)
    embed.add_field(name="Expected return", value=f"<t:{int(end_dt.timestamp())}:F>", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text="Roles will be changed automatically at the start time.")
    
    await interaction.response.send_message(view=C.embed_to_v2_layout(embed, content=None), ephemeral=True)


    log_channel = C.client.get_channel(C.LOA_TRACK_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(title="Leave Scheduled", color=discord.Color.green())
        log_embed.add_field(name="Target", value=target.mention, inline=True)
        if target != interaction.user:
            log_embed.add_field(name="Requested by", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="Period", value=f"<t:{int(start_dt.timestamp())}:f> - <t:{int(end_dt.timestamp())}:f>", inline=False)
        log_embed.add_field(name="Reason", value=reason, inline=False)
        await log_channel.send(embed=log_embed)

@C.loa_group.command(name="return", description="End your leave (or reservation) early and restore your original state yourself.")
async def loa_return_cmd(interaction: discord.Interaction):
    if interaction.guild_id != C.STAFF_GUILD_ID:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This can only be used on the staff server.')]))
    
    uid_str = str(interaction.user.id)
    if uid_str not in C.LOA_CACHE:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Your leave data was not found.')]))
    
    loa_data = C.LOA_CACHE[uid_str]
    await interaction.response.defer(ephemeral=True)
    
    if loa_data["status"] == "pending":
        del C.LOA_CACHE[uid_str]
        await C.save_loa_tracking()
        await interaction.followup.send(view=C.build_v2_card('Notice', [(None, 'Your scheduled leave has been cancelled.')]))
    else:
        success = await C.deactivate_loa(interaction.user.id, interaction.guild)
        if success:
            await C.save_loa_tracking()
            await C.record_loa_return(interaction.user.id)
            await interaction.followup.send(view=C.build_v2_card('Notice', [(None, 'Your leave was ended early and your roles and nickname were restored. Welcome back!')]))
        else:
            await interaction.followup.send(view=C.build_v2_card('Notice', [(None, 'An error occurred while restoring. Please contact an administrator.')]))

@C.loa_group.command(name="cancel", description="[Admin] Force-cancel/restore a user's leave (or reservation).")
@app_commands.describe(target_user="User to forcibly remove")
async def loa_cancel_cmd(interaction: discord.Interaction, target_user: discord.Member):
    if not C.is_event_manager_or_chief(interaction.user) and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))
    
    uid_str = str(target_user.id)
    if uid_str not in C.LOA_CACHE:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'{target_user.display_name} has no leave data.')]))

    loa_data = C.LOA_CACHE[uid_str]
    await interaction.response.defer(ephemeral=True)
    
    if loa_data["status"] == "pending":
        del C.LOA_CACHE[uid_str]
        await C.save_loa_tracking()
        await interaction.followup.send(view=C.build_v2_card('Notice', [(None, f'Cancelled the scheduled leave for {target_user.mention} with admin privileges.')]))
    else:
        success = await C.deactivate_loa(target_user.id, interaction.guild)
        if success:
            await C.save_loa_tracking()
            await C.record_loa_return(target_user.id)
            await interaction.followup.send(view=C.build_v2_card('Notice', [(None, f'Force-ended leave for {target_user.mention} and restored roles.')]))
        else:
            await interaction.followup.send(view=C.build_v2_card('Notice', [(None, f'An error occurred while restoring {target_user.mention}.')]))

@C.loa_group.command(name="restore_legacy", description="[Admin] Restore and migrate leave data from the old Flight Hub Core logs.")
@app_commands.describe(
    blue_msg_id="Message ID of the \"LOA started\" notice (blue embed)", 
    red_msg_id="Message ID of the \"LOA restore info\" notice (red embed)"
)
async def loa_restore_legacy_cmd(interaction: discord.Interaction, blue_msg_id: str, red_msg_id: str):
    if not C.is_event_manager_or_chief(interaction.user) and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
        
    await interaction.response.defer(ephemeral=True)
    


    log_channel = interaction.channel

    
    try:
        blue_msg = await log_channel.fetch_message(int(blue_msg_id.strip()))
        red_msg = await log_channel.fetch_message(int(red_msg_id.strip()))
        
        user_id = None
        reason = "Restored from the legacy system"
        

        if blue_msg.embeds:
            b_embed = blue_msg.embeds[0]
            for f in b_embed.fields:
                if "Target User" in f.name:

                    match = re.search(r"(\d{17,19})", f.value)
                    if match: user_id = int(match.group(1))
                elif "Reason" in f.name:
                    reason = f.value
                    
        if not user_id:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Could not extract the user ID. Please check the blue message.')]))
            
        orig_nick = ""
        role_ids = []
        end_ts = 0
        

        if red_msg.embeds:
            r_embed = red_msg.embeds[0]
            for f in r_embed.fields:
                if "Original Nickname" in f.name:
                    orig_nick = f.value.strip()
                elif "Original Roles" in f.name:

                    role_ids = [int(r) for r in re.findall(r"<@&(\d+)>", f.value)]
                elif "Leave End" in f.name:
                    try:
                        dt = datetime.datetime.strptime(f.value.strip(), "%Y-%m-%d %H:%M")
                        dt = dt.replace(tzinfo=C.JST)
                        end_ts = int(dt.timestamp())
                    except Exception as e:
                        print(f"Date parse error: {e}")
                        
        if not orig_nick or not role_ids or not end_ts:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Could not extract all required information from the red message.')]))
            

        C.LOA_CACHE[str(user_id)] = {
            "status": "active",
            "start_timestamp": int(datetime.datetime.now().timestamp()),
            "end_timestamp": end_ts,
            "reason": reason,
            "original_role_ids": role_ids,
            "original_nick": orig_nick
        }
        
        await C.save_loa_tracking()
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Restore from the legacy system complete!\nTarget: <@{user_id}>\nExpected end: <t:{end_ts}:f>\nRoles restored: {len(role_ids)}')]))
        
    except discord.NotFound:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The specified message ID was not found. Please provide an ID from the log channel.')]))
    except Exception as e:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'An error occurred: {e}')]))

@C.loa_group.command(name="list", description="[Admin] Show staff who are currently on leave or scheduled for leave.")
async def loa_list_cmd(interaction: discord.Interaction):
    if not C.is_event_manager_or_chief(interaction.user) and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))
    
    if not C.LOA_CACHE:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No staff are currently on leave or have scheduled leave.')]))
        
    embed = discord.Embed(title="Leave (LOA) Staff List", color=discord.Color.blue())
    active_str = ""
    pending_str = ""
    
    for uid_str, data in C.LOA_CACHE.items():
        user = C.client.get_user(int(uid_str))
        user_mention = user.mention if user else f"Unknown ({uid_str})"
        info = f"{user_mention}\n└ Expected return: <t:{data['end_timestamp']}:d>\n└ Reason: {data.get('reason', 'None')}\n\n"
        
        if data["status"] == "active":
            active_str += info
        else:
            pending_str += f"{user_mention}\n└ Start: <t:{data['start_timestamp']}:d> ➝ Return: <t:{data['end_timestamp']}:d>\n\n"

    if active_str:
        embed.add_field(name="Currently on leave (Active)", value=active_str, inline=False)
    if pending_str:
        embed.add_field(name="Scheduled leave (Pending)", value=pending_str, inline=False)

    await interaction.response.send_message(view=C.embed_to_v2_layout(embed, content=None), ephemeral=True)

@C.client.tree.command(name="create_flight", description="Create a new flight event.")
@app_commands.describe(
    flight_code="Select Flight Code or Search by Airport",
    equipment="Aircraft Type",
    staff_meet_datetime="Meeting Time (YYYY-MM-DD HH:MM)",
    passenger_start_time="Start Time (HH:MM)",
    host_timezone="Timezone",
    use_bus="Whether to use the bus service"
)
@app_commands.autocomplete(flight_code=C.flight_code_autocomplete, equipment=C.equipment_autocomplete)
@app_commands.choices(use_bus=[app_commands.Choice(name="Yes", value=1), app_commands.Choice(name="No", value=0)])
@C.event_manager_only
async def create_flight_slash(interaction: discord.Interaction, flight_code: str, equipment: str,
                               staff_meet_datetime: str, passenger_start_time: str, host_timezone: str = "GMT+9",
                               use_bus: int = 0):
    if interaction.guild_id != C.STAFF_GUILD_ID or (not C.is_event_manager_or_chief(interaction.user) and not (C.TEST_MODE and C._test_admin_allowed(interaction.user))):
        return await interaction.response.send_message(ephemeral=True, allowed_mentions=discord.AllowedMentions.none(), view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    await C.ensure_templates_fresh()
    saved_route = C.FLIGHT_DB.get(flight_code)
    if not saved_route:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No data found.')]))

    clean_equip = equipment.replace(" (Registered)", "").replace("(Registered)", "").strip()
    variant_data = None
    
    for k, v in saved_route.get("variants", {}).items():
        if k.lower() == clean_equip.lower():
            variant_data = v
            clean_equip = k
            break

    if not variant_data:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No template found for the specified equipment. Check the equipment name or register an image first.')]))

    src_ch = variant_data.get("source_channel_id")
    src_msg = variant_data.get("source_message_id")
    image_url, image_bytes = await C.fetch_fresh_image_info(src_ch, src_msg)

    data = {
        "flight_code": flight_code.strip().upper(), "origin": saved_route["origin"],
        "destination": saved_route["destination"],
        "equipment": clean_equip, "classes": variant_data.get("classes", "Unknown"),
        "roblox_link": variant_data.get("roblox_link", ""),
        "airline": variant_data.get("airline", "Airline"),
        "color": variant_data.get("color", "1B3444"),
        "source_channel_id": src_ch, "source_message_id": src_msg,
        "staff_meet_datetime_str": staff_meet_datetime, "passenger_time_str": passenger_start_time,
        "host_timezone_str": host_timezone,
        "mention_str": f"<@&{C.NOTIFICATION_ROLE_ID}>",
        "is_custom": False,
        "use_bus": bool(use_bus)
    }

    if C.TEST_MODE:
        try:
            tz_offset = C.parse_timezone_offset(data["host_timezone_str"])
            staff_dt = C.calculate_jst_time(data["staff_meet_datetime_str"], "", tz_offset)
            date_part = data["staff_meet_datetime_str"].split()[0]
            pass_dt = C.calculate_jst_time(date_part, data["passenger_time_str"], tz_offset)
            if not staff_dt or not pass_dt:
                raise ValueError("Please check the date/time format.")
            if pass_dt < staff_dt:
                pass_dt += datetime.timedelta(days=1)
            end_dt = pass_dt + datetime.timedelta(hours=1)
            code = f"[TEST] {data['flight_code']}"
            record = {
                "flight_code": code, "origin": data["origin"], "destination": data["destination"],
                "equipment": data["equipment"], "classes": data["classes"], "airline": data.get("airline", "Airline"),
                "color": data.get("color", "1B3444"), "start_timestamp": int(pass_dt.timestamp()),
                "end_timestamp": int(end_dt.timestamp()), "staff_timestamp": int(staff_dt.timestamp()),
                "host_id": interaction.user.id, "is_test": True, "messages_deleted": False,
                "briefing_sent": False, "briefing_assignments": {}, "briefing_state": {},
                "briefing_lang": "EN", "test_mode": True,
                "use_bus": data.get("use_bus", False), "is_bus": False, "event_url": "",
                "mention_str": data.get("mention_str", ""), "notified_20min": False,
                "accepted_users": [interaction.user.id], "declined_users": [],
            }
            existing = next((f for f in C.TEST_FLIGHT_CACHE if f.get("flight_code") == code), None)
            if existing:
                C.TEST_FLIGHT_CACHE[C.TEST_FLIGHT_CACHE.index(existing)] = record
            else:
                C.TEST_FLIGHT_CACHE.append(record)
            await C._test_mode_record("create_flight", interaction.user.id, "OK", {"flight_code": code})
            result_msg = f"Recorded test flight `{code}` in the isolated environment. No posts to staff/customers, Discord events, or external sheet sync were performed."
            await interaction.followup.send(
                view=C.embed_to_v2_layout(C.create_info_embed("Created in Test Mode", result_msg, discord.Color.green()), content=None),
                ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

            await C._test_show_flight_previews(interaction, record)
            return
        except Exception as exc:
            await C._test_mode_record("create_flight", interaction.user.id, "FAIL", {"error": str(exc)})
            return await interaction.followup.send(
                ephemeral=True, view=C.build_v2_card("Test flight creation failed", [(None, str(exc))], color=0xE74C3C))

    success, result_msg = await C.process_flight_creation(interaction.user, data, image_bytes, image_url)
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_CHECK_STR + ' Created Successfully', result_msg, discord.Color.green()), content=None), ephemeral=True)
    else:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed(C.EMOJI_X_STR + ' Creation Error', result_msg, discord.Color.red()), content=None), ephemeral=True)

@C.client.tree.command(name="create_flighttest", description="[Test] Create a flight using the designated test server and category.")
@app_commands.describe(
    flight_code="Select Flight Code or Search by Airport",
    equipment="Aircraft Type",
    staff_meet_datetime="Meeting Time (YYYY-MM-DD HH:MM)",
    passenger_start_time="Start Time (HH:MM)",
    host_timezone="Timezone",
    use_bus="Whether to use the bus service"
)
@app_commands.autocomplete(flight_code=C.flight_code_autocomplete, equipment=C.equipment_autocomplete)
@app_commands.choices(use_bus=[app_commands.Choice(name="Yes", value=1), app_commands.Choice(name="No", value=0)])
@C.event_manager_only
async def create_flighttest_slash(interaction: discord.Interaction, flight_code: str, equipment: str,
                                  staff_meet_datetime: str, passenger_start_time: str, host_timezone: str = "GMT+9",
                                  use_bus: int = 0):
    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    await interaction.response.defer(ephemeral=True)

    await C.ensure_templates_fresh()
    saved_route = C.FLIGHT_DB.get(flight_code)
    if not saved_route:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Template data not found.')]))

    clean_equip = equipment.replace(" (Registered)", "").replace("(Registered)", "").strip()
    variant_data = None
    for k, v in saved_route.get("variants", {}).items():
        if k.lower() == clean_equip.lower():
            variant_data = v
            clean_equip = k
            break

    if not variant_data:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No template found for the specified equipment.')]))

    src_ch = variant_data.get("source_channel_id")
    src_msg = variant_data.get("source_message_id")
    image_url, image_bytes = await C.fetch_fresh_image_info(src_ch, src_msg)


    data = {
        "flight_code": f"[TEST] {flight_code.strip().upper()}",
        "origin": saved_route["origin"],
        "destination": saved_route["destination"],
        "equipment": clean_equip, 
        "classes": variant_data.get("classes", "Unknown"),
        "color": variant_data.get("color", "1B3444"),
        "staff_meet_datetime_str": staff_meet_datetime, 
        "passenger_time_str": passenger_start_time,
        "host_timezone_str": host_timezone,
        "use_bus": bool(use_bus)
    }

    success, result_msg = await C.process_flighttest_creation(interaction.user, data, image_bytes, image_url, is_bus=bool(use_bus))
    if success:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Created Successfully (TEST)', result_msg, discord.Color.green()), content=None), ephemeral=True)
    else:
        await interaction.followup.send(view=C.embed_to_v2_layout(C.create_info_embed('Creation Error (TEST)', result_msg, discord.Color.red()), content=None), ephemeral=True)
