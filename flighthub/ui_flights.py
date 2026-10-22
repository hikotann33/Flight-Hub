import discord
from discord import app_commands
import datetime
import asyncio
import uuid

from . import core as C


class RemindConfirmView(discord.ui.View):
    def __init__(self, target_members, schedule_text, comment):
        super().__init__(timeout=600)
        self.target_members = target_members
        self.schedule_text = schedule_text
        self.comment = comment

    def generate_dm_embed(self):
        month = datetime.datetime.now(C.JST).month
        desc = (
            f"Thank you for your continued activity.\n"
            f"No flight participation has been recorded for you this month ({month}) yet.\n"
            f"To meet the activity requirement, please consider joining one of the flights below.\n\n"
            f"Thank you for your continued support and activity.\n"
            f"We have not yet confirmed your flight participation record for this month ({month}).\n"
            f"To meet the activity requirements, please consider participating in the upcoming flights listed below.\n\n"
            f"**Upcoming Flights This Month**\n{self.schedule_text}"
        )
        
        if self.comment:
            desc += f"\n\n**Message from Manager**\n{self.comment}"

        disclaimer = (
            "Please make sure to attend flights.\n"
            "This reminder may also reach staff who are on an approved leave of absence (LOA); if so, please disregard it.\n"
            "This reminder is sent automatically. If you received it by mistake, please open a ticket to let us know."
        )
        desc += f"\n\n**Notes**\n{disclaimer}"
            
        embed = discord.Embed(
            title=f"Flight Participation Reminder ({month})", 
            description=desc, 
            color=discord.Color.orange()
        )
        embed.set_footer(text="Flight Hub")
        return embed

    @discord.ui.button(label="Preview (test-send to me)", style=discord.ButtonStyle.secondary)
    async def preview_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.generate_dm_embed()
        try:
            await interaction.user.send(view=C.embed_to_v2_layout(embed, content='**Test Preview**\nThis is how it will be sent to customers (staff).'))
            await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, C.EMOJI_CHECK_STR + ' Preview sent to your DMs.')]))
        except Exception as e:
            await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'{C.EMOJI_X_STR} Could not send DM. ({e})')]))

    @discord.ui.button(label="Send to everyone", style=discord.ButtonStyle.danger)
    async def send_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = self.generate_dm_embed()
        success_count = 0
        
        for member in self.target_members:
            try:
                await member.send(embed=embed)
                success_count += 1
                if member.id not in C.remind_tracking_cache["users"]:
                    C.remind_tracking_cache["users"].append(member.id)
                await asyncio.sleep(0.5)
            except:
                pass
        
        await C.save_remind_tracking()
        self.clear_items()
        await interaction.edit_original_response(content=f"{C.EMOJI_CHECK_STR} **{success_count}/{len(self.target_members)}** staff reminded successfully.", embed=None, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.clear_items()
        await interaction.response.edit_message(content=C.EMOJI_X_STR + " Sending cancelled.", embed=None, view=self)

class RandomFlightProposalView(discord.ui.View):
    def __init__(self, departure_date, departure_time, tz_str, offset_hrs, flight_code, origin, dest, equipment, airline, classes):
        super().__init__(timeout=300)
        self.departure_date = departure_date
        self.departure_time = departure_time
        self.tz_str = tz_str
        self.offset_hrs = offset_hrs
        
        self.flight_code = flight_code
        self.origin = origin
        self.dest = dest
        self.equipment = equipment
        self.airline = airline
        self.classes = classes

    @discord.ui.button(label="Apply for this flight", style=discord.ButtonStyle.success)
    async def apply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        raw_eq = f"{self.airline} / {self.equipment}"
        detail = "Randomly Proposed Flight"
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        await C.process_flight_application(
            interaction, self.departure_date, self.departure_time, self.tz_str, self.offset_hrs,
            self.flight_code, self.origin, self.dest, raw_eq, detail
        )

    @discord.ui.button(label="Reroll", style=discord.ButtonStyle.primary)
    async def reroll_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()


        suggestion = await C.get_least_used_flight_suggestion(interaction.client)
        
        if not suggestion:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No valid flight templates available (All origins are currently in use or no equipment registered).')]))

        self.flight_code = suggestion["flight_code"]
        self.origin = suggestion["origin"]
        self.dest = suggestion["dest"]
        self.equipment = suggestion["equipment"]
        self.airline = suggestion["airline"]
        self.classes = suggestion["classes"]
        
        image_url, _ = await C.fetch_fresh_image_info(suggestion["src_ch"], suggestion["src_msg"])
        embed_color = C.get_embed_color(suggestion["color_hex"])
        
        ts = C.parse_date_time_to_ts(self.departure_date, self.departure_time, self.offset_hrs)
        time_display = f"<t:{ts}:F>\n*(Local: {self.departure_date} {self.departure_time} {self.tz_str})*" if ts > 0 else f"{self.departure_date} {self.departure_time} ({self.tz_str})"

        desc = (
            f"How about this flight?\n\n"
            f"**Departure Time:** {time_display}\n"
            f"**Route:** {self.origin} ➝ {self.dest}\n"
            f"**Flight Code:** {self.flight_code}\n"
            f"**Airline:** {self.airline}\n"
            f"**Equipment:** {self.equipment}\n"
            f"**Classes:** {self.classes}\n"
        )
        
        embed = discord.Embed(title="Random Flight Proposal", description=desc, color=embed_color)
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(text="Click 'Apply for this flight' to submit it to the approval queue.")

        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Random flight proposal cancelled.", embed=None, view=self)

@C.client.tree.command(name="suggest_flight", description="Randomly suggests a flight and allows you to apply for it directly.")
@app_commands.describe(
    departure_date="Date (e.g., 2026-08-16)",
    departure_time="Time (e.g., 20:00)",
    current_local_time="Your current local time (e.g., 14:00)"
)
async def suggest_flight_cmd(interaction: discord.Interaction, departure_date: str, departure_time: str, current_local_time: str):
    if interaction.guild_id != C.STAFF_GUILD_ID:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This command can only be used in the staff server.')]))

    await interaction.response.defer(ephemeral=True)
    tz_str, offset_hrs = C.calculate_tz_offset(current_local_time)


    suggestion = await C.get_least_used_flight_suggestion(interaction.client)
    
    if not suggestion:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No valid flight templates available (All origins are currently in use or no equipment registered).')]))

    image_url, _ = await C.fetch_fresh_image_info(suggestion["src_ch"], suggestion["src_msg"])
    embed_color = C.get_embed_color(suggestion["color_hex"])

    ts = C.parse_date_time_to_ts(departure_date, departure_time, offset_hrs)
    time_display = f"<t:{ts}:F>\n*(Local: {departure_date} {departure_time} {tz_str})*" if ts > 0 else f"{departure_date} {departure_time} ({tz_str})"

    desc = (
        f"How about this flight?\n\n"
        f"**Departure Time:** {time_display}\n"
        f"**Route:** {suggestion['origin']} ➝ {suggestion['dest']}\n"
        f"**Flight Code:** {suggestion['flight_code']}\n"
        f"**Airline:** {suggestion['airline']}\n"
        f"**Equipment:** {suggestion['equipment']}\n"
        f"**Classes:** {suggestion['classes']}\n"
    )
    
    embed = discord.Embed(title="Random Flight Proposal", description=desc, color=embed_color)
    if image_url:
        embed.set_image(url=image_url)
    embed.set_footer(text="Click 'Apply for this flight' to submit it to the approval queue.")

    view = RandomFlightProposalView(
        departure_date, departure_time, tz_str, offset_hrs,
        suggestion['flight_code'], suggestion['origin'], suggestion['dest'], 
        suggestion['equipment'], suggestion['airline'], suggestion['classes']
    )

    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@C.client.tree.command(name="edit_gamenight", description="Edit the details of a staff-only game night (date/time, image, description, etc.).")
@app_commands.describe(
    event_code="The code of the event to edit (GN_...)",
    new_start_time="[Optional] New start time (YYYY-MM-DD HH:MM)",
    new_image="[Optional] New image to add or change",
    new_game_name="[Optional] New game name",
    new_prize="[Optional] New prize",
    new_description="[Optional] New description",
    new_game_link="[Optional] New game link"
)
@C.event_manager_only
async def edit_gamenight_cmd(
    interaction: discord.Interaction, 
    event_code: str, 
    new_start_time: str = None, 
    new_image: discord.Attachment = None,
    new_game_name: str = None,
    new_prize: str = None,
    new_description: str = None,
    new_game_link: str = None
):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C.is_event_manager_or_chief(interaction.user):
        try:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
        except discord.NotFound:
            return
            
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.NotFound:
        print("[edit_gamenight] Processing timed out due to network lag.")
        return
    
    async with C.global_json_lock:
        flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == event_code), None)
        if not flight or not flight.get("is_gamenight"):
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The specified Game Night event was not found.')]))
            
        if interaction.user.id != flight['host_id'] and not C.is_chief(interaction.user):
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Only the host can edit this.')]))
        
        modified = False
        

        start_dt = None
        if new_start_time:
            start_dt = C.parse_loa_datetime(new_start_time)
            if not start_dt:
                return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The date/time format is invalid.')]))
            
            flight["start_timestamp"] = int(start_dt.timestamp())
            flight["staff_timestamp"] = int(start_dt.timestamp())
            flight["end_timestamp"] = int((start_dt + datetime.timedelta(hours=1)).timestamp())
            modified = True
        else:
            start_dt = datetime.datetime.fromtimestamp(flight["start_timestamp"], tz=C.JST)
            

        image_url = None
        image_bytes = None
        if new_image:
            image_bytes = await new_image.read()
            log_ch = C.client.get_channel(C.FLIGHT_INPUT_CHANNEL_ID)
            if log_ch:
                saved_msg = await log_ch.send(content=f"GameNight Image Updated: `{event_code}`", file=await new_image.to_file())
                image_url = saved_msg.attachments[0].url
                flight["source_channel_id"] = log_ch.id
                flight["source_message_id"] = saved_msg.id
                modified = True
        

        if new_game_name or new_prize or new_description or new_game_link:
            modified = True
        
        if not modified:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No changes were specified.')]))
            
        C.global_db_dirty = True
        
        current_game_name = "Unknown"
        current_prize = "None"
        current_link = "None"
        current_desc = ""


        s_ch = C.client.get_channel(flight["staff_channel_id"])
        if s_ch:
            try:
                msg = await s_ch.fetch_message(flight["staff_message_id"])
                embed = msg.embeds[0]
                

                current_desc = embed.description or ""
                for f_field in embed.fields:
                    if f_field.name == "Game": current_game_name = f_field.value
                    elif f_field.name == "Prize": current_prize = f_field.value
                    elif f_field.name == "Game Link": current_link = f_field.value


                if new_game_name: current_game_name = new_game_name
                if new_prize: current_prize = new_prize
                if new_description: current_desc = new_description
                if new_game_link: current_link = new_game_link


                if new_game_name:
                    embed.title = f"Staff Game Night: {current_game_name}"
                if new_description:
                    embed.description = current_desc
                    
                for i, f_field in enumerate(embed.fields):
                    if f_field.name == "Action" and new_start_time:
                        embed.set_field_at(i, name="Action", value=f"React to join the event.\n**Start Time:** <t:{flight['start_timestamp']}:F>", inline=False)
                    elif f_field.name == "Game" and new_game_name:
                        embed.set_field_at(i, name="Game", value=current_game_name, inline=True)
                    elif f_field.name == "Prize" and new_prize:
                        embed.set_field_at(i, name="Prize", value=current_prize, inline=True)
                    elif f_field.name == "Game Link" and new_game_link:
                        embed.set_field_at(i, name="Game Link", value=current_link, inline=False)
                        
                if image_url:
                    embed.set_image(url=image_url)
                
                await msg.edit(embed=embed)
            except Exception as e:
                print(f"Edit GameNight Msg Error: {e}")
        

        if flight.get("event_url"):
            try:
                evt_id = int(flight["event_url"].split("/")[-1])
                guild = C.client.get_guild(C.STAFF_GUILD_ID)
                if guild:
                    evt = await guild.fetch_scheduled_event(evt_id)
                    kwargs = {}

                    if new_start_time:
                        kwargs["start_time"] = start_dt
                        kwargs["end_time"] = start_dt + datetime.timedelta(hours=1)

                    if image_bytes:
                        kwargs["image"] = image_bytes

                    if new_game_name:
                        kwargs["name"] = f"{current_game_name}"
                    if new_prize or new_description or new_game_link:
                        kwargs["description"] = f"**Prize** {current_prize}\n\n{current_desc}\n\n**Game Link**\n{current_link}"
                        
                    if kwargs:
                        await evt.edit(**kwargs)
            except Exception as e:
                print(f"Edit GameNight Event Error: {e}")
                
        await C.auto_publish_schedule()
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Game Night details (text, date/time, images) updated successfully!')]))

@C.client.tree.command(name="remind", description="[Manager] Send a participation reminder DM to staff who have not flown this month.")
@app_commands.describe(
    comment="Optional comment to add below the message",
    include_fc="Whether to include Flight Crew (default: True)",
    include_cc="Whether to include Cabin Crew (default: True)",
    include_gc="Whether to include Ground Crew (default: True)"
)
async def remind_cmd(interaction: discord.Interaction, comment: str = None, 
                     include_fc: bool = True, include_cc: bool = True, 
                     include_gc: bool = True):
                     
    if C.LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))

    await interaction.response.defer(ephemeral=True)

    jst_now = datetime.datetime.now(C.JST)
    start_of_month = jst_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_of_month_utc = start_of_month.astimezone(datetime.timezone.utc)
    
    if C.remind_tracking_cache.get("month") != jst_now.month:
        C.remind_tracking_cache["month"] = jst_now.month
        C.remind_tracking_cache["users"] = []
        await C.save_remind_tracking()

    participated_users = set()
    channels_to_check = [C.FLIGHT_LOG_HISTORY_CHANNEL_ID, C.MANUAL_LOG_CHANNEL_ID]
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

    target_role_ids = []
    if include_fc: target_role_ids.append(C.ROLE_FLIGHT_OPS)
    if include_cc: target_role_ids.append(C.ROLE_CABIN_CREWS)
    if include_gc: target_role_ids.append(C.ROLE_GROUND_OPS)

    target_members = []
    staff_guild = C.client.get_guild(C.STAFF_GUILD_ID)
    if not staff_guild:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, C.EMOJI_X_STR + ' Staff server not found.')]))

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

    end_of_month = (start_of_month + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(seconds=1)
    upcoming_flights = [f for f in C.FLIGHT_LOG_CACHE if f["start_timestamp"] >= jst_now.timestamp() and f["start_timestamp"] <= end_of_month.timestamp()]
    upcoming_flights.sort(key=lambda x: x["start_timestamp"])

    schedule_text = ""
    for f in upcoming_flights:
        ts = int(f["start_timestamp"])
        staff_msg_link = f"https://discord.com/channels/{C.STAFF_GUILD_ID}/{C.STAFF_CHANNEL_ID}/{f['staff_message_id']}"
        schedule_text += f"**[{f['flight_code']}]({staff_msg_link})** (<t:{ts}:f>) - {f['origin']} ➝ {f.get('destination', 'Unknown')}\n"

    if not schedule_text:
        schedule_text = "*No upcoming flights are scheduled for the rest of this month.*\n"

    embed = discord.Embed(
        title="Reminder Send Confirmation", 
        description=f"Staff with no activity record this month ({jst_now.month}) who have not yet received a reminder: **{len(target_members)}**.\nYou can preview the content with the Preview button before sending.", 
        color=C.EMBED_COLOR
    )
    
    member_list_str = " ".join([m.mention for m in target_members])
    if len(member_list_str) > 1024:
        member_list_str = member_list_str[:1000] + "... (and more)"
        
    embed.add_field(name="Recipients", value=member_list_str if target_members else "No recipients")

    view = RemindConfirmView(target_members, schedule_text, comment)
    view.children[1].label = f"Send to {len(target_members)} staff"
    if not target_members:
        view.children[1].disabled = True

    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def send_gamenight_task(interaction, game_name, game_link, prize, description, start_dt, end_dt, event_code, wait_seconds, image_bytes, saved_image_url):

    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)


    staff_guild = C.client.get_guild(C.STAFF_GUILD_ID)
    event_url = ""
    if staff_guild:
        try:
            kwargs = {
                "name": f"{game_name}",
                "description": f"**Prize** {prize}\n\n{description}\n\n**Game Link**\n{game_link}",
                "start_time": start_dt,
                "end_time": end_dt,
                "entity_type": discord.EntityType.external,
                "privacy_level": discord.PrivacyLevel.guild_only,
                "location": "Staff Game Night"
            }

            if image_bytes:
                kwargs["image"] = image_bytes

            event = await staff_guild.create_scheduled_event(**kwargs)
            event_url = event.url
        except Exception as e:
            print(f"GameNight Event Creation Error: {e}")


    embed = discord.Embed(
        title=f"Staff Game Night: {game_name}", 
        description=description, 
        color=discord.Color.purple()
    )
    embed.add_field(name="Host", value=interaction.user.display_name, inline=False)
    embed.add_field(name="Game", value=game_name, inline=True)
    embed.add_field(name="Prize", value=prize, inline=True)
    embed.add_field(name="Game Link", value=game_link, inline=False)
    
    embed.add_field(
        name="Action", 
        value=f"React to join the event.\n**Start Time:** <t:{int(start_dt.timestamp())}:F>", 
        inline=False
    )
    
    embed.add_field(name=f"{C.EMOJI_CHECK_STR} Accepted (1)", value=f">>> {interaction.user.display_name}", inline=True)
    embed.add_field(name=f"{C.EMOJI_X_STR} Declined (0)", value="-", inline=True)

    if event_url:
        embed.add_field(name="Event Link", value=f"**[View the Discord Event calendar]({event_url})**", inline=False)


    if saved_image_url:
        embed.set_image(url=saved_image_url)

    embed.set_footer(text=f"Flight Code: {event_code} | Created by {await C.get_server_display_name(interaction.user.id, C.STAFF_GUILD_ID, fallback=interaction.user.display_name)}")


    target_channel = C.client.get_channel(C.TEST_STAFF_CHANNEL_ID)
    if target_channel:
        sent_msg = await target_channel.send(content="@everyone", embed=embed, view=C.FlightSignupView())


        async with C.global_json_lock:
            flight_dict = {
                "flight_code": event_code,
                "origin": "Game Night",       
                "destination": "Event",       
                "equipment": "Game",          
                "classes": "Staff Only",      
                "host_id": interaction.user.id,
                "staff_guild_id": C.STAFF_GUILD_ID,
                "staff_channel_id": target_channel.id,
                "staff_message_id": sent_msg.id,
                "accepted_users": [interaction.user.id],
                "declined_users": [],
                "start_timestamp": int(start_dt.timestamp()),
                "end_timestamp": int(end_dt.timestamp()),
                "staff_timestamp": int(start_dt.timestamp()),
                "is_gamenight": True,
                "event_url": event_url,
                "source_channel_id": C.FLIGHT_INPUT_CHANNEL_ID if saved_image_url else None,
                

                "customer_message_id": None,
                "pending_customer_msg": False,
                "briefing_sent": False,
                "notify_20min_timestamp": int(start_dt.timestamp()) - 1200,
                "notified_20min": False,
                "messages_deleted": False,
                "color": "9B59B6"
            }
            C.FLIGHT_LOG_CACHE.append(flight_dict)
            C.global_db_dirty = True

@C.client.tree.command(name="staff_gamenight", description="Create a staff-only game night / event.")
@app_commands.describe(
    game_name="Game name",
    game_link="Game invite link",
    prize="Prize",
    description="Description",
    start_time="Start time (e.g. 2026-08-08 18:40)",
    end_time="End time (e.g. 2026-08-08 20:00)",
    image="[Optional] Image shown on the event and calendar",
    publish_time="[Optional] Scheduled send time (e.g. 2026-08-01 12:00). Leave blank to send immediately."
)
@C.event_manager_only
async def staff_gamenight_cmd(
    interaction: discord.Interaction, 
    game_name: str, 
    game_link: str, 
    prize: str, 
    description: str, 
    start_time: str, 
    end_time: str,
    image: discord.Attachment = None,
    publish_time: str = None
):

    if interaction.guild_id == C.CUSTOMER_GUILD_ID:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'This command cannot be used on the customer server.')]))
    

    if not C.is_event_manager_or_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this.')]))

    await interaction.response.defer(ephemeral=True)


    start_dt = C.parse_loa_datetime(start_time)
    end_dt = C.parse_loa_datetime(end_time)
    
    if not start_dt or not end_dt:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The event date/time format is invalid. Use `YYYY-MM-DD HH:MM` (e.g. 2026-08-08 18:40).')]))


    wait_seconds = 0
    if publish_time:
        pub_dt = C.parse_loa_datetime(publish_time)
        if not pub_dt:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The scheduled send time format is invalid.')]))
        
        wait_seconds = (pub_dt - datetime.datetime.now(C.JST)).total_seconds()
        if wait_seconds < 0:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'The scheduled send time must be in the future.')]))


    image_bytes = None
    saved_image_url = None
    if image:
        image_bytes = await image.read()
        log_channel = C.client.get_channel(C.FLIGHT_INPUT_CHANNEL_ID)
        if log_channel:
            saved_msg = await log_channel.send(content=f"GameNight Image: `{game_name}`", file=await image.to_file())
            saved_image_url = saved_msg.attachments[0].url

    import time

    event_code = f"GN_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}"


    C.client.loop.create_task(
        send_gamenight_task(interaction, game_name, game_link, prize, description, start_dt, end_dt, event_code, wait_seconds, image_bytes, saved_image_url)
    )
    
    if wait_seconds > 0:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Scheduled! <t:{int(pub_dt.timestamp())}:F> — it will be sent and the calendar event created automatically.')]))
    else:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Staff-only Game Night created, added to the calendar, and sent successfully!')]))

@C.client.tree.command(name="remind_status", description="[Manager] View the list of staff who have already received a reminder this month.")
async def remind_status_cmd(interaction: discord.Interaction):
    if C.LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, C.EMOJI_X_STR + ' You do not have permission to run this command.')]))
        
    jst_now = datetime.datetime.now(C.JST)

    users = C.remind_tracking_cache["users"]
    if not users or C.remind_tracking_cache.get("month") != jst_now.month:
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'{C.EMOJI_INFO_STR} No reminders have been sent to anyone this month ({jst_now.month}) yet.')]))

    desc = ""
    for uid in users:
        desc += f"<@{uid}> "

    embed = discord.Embed(title=f"{C.EMOJI_SEARCH_STR} Reminders Sent List - {jst_now.month} ({len(users)})", description=desc[:4000], color=discord.Color.blue())
    await interaction.response.send_message(view=C.embed_to_v2_layout(embed, content=None), ephemeral=True)
