import discord
from discord import app_commands
import datetime
import re

from . import core as C

class FlightAppModal(discord.ui.Modal):
    def __init__(self, departure_date, departure_time, flight_code, event_type, tz_str, offset_hrs, default_equipment=""):
        super().__init__(title="Flight App Details")
        self.departure_date = departure_date
        self.departure_time = departure_time
        self.tz_str = tz_str
        self.offset_hrs = offset_hrs
        self.event_type = event_type
        
        self.flight_code_input = discord.ui.TextInput(label="Flight Code", default=flight_code if flight_code != "Other" else "", required=True, max_length=50)
        self.origin_input = discord.ui.TextInput(label="Origin", required=True, max_length=50)
        self.dest_input = discord.ui.TextInput(label="Destination", required=True, max_length=50)
        

        def_eq_str = f"Airline / {default_equipment}".strip(" /") if default_equipment else "Airline / "
        self.equipment_input = discord.ui.TextInput(label="Airline / Equipment", placeholder="e.g., Airline / A321neo", default=def_eq_str, required=True, max_length=100)
        self.detail_input = discord.ui.TextInput(label="Details (e.g. event type)", style=discord.TextStyle.paragraph, default=event_type if event_type != "Other" else "", required=True, max_length=500)
        
        self.add_item(self.flight_code_input)
        self.add_item(self.origin_input)
        self.add_item(self.dest_input)
        self.add_item(self.equipment_input)
        self.add_item(self.detail_input)

    async def on_submit(self, interaction: discord.Interaction):
        await C.process_flight_application(interaction, self.departure_date, self.departure_time, self.tz_str, self.offset_hrs, self.flight_code_input.value.strip(), self.origin_input.value.strip(), self.dest_input.value.strip(), self.equipment_input.value, self.detail_input.value.strip())

async def flight_app_code_autocomplete(interaction: discord.Interaction, current: str):
    choices = [app_commands.Choice(name=item["label"], value=item["value"]) for item in C.FLIGHT_AUTOCOMPLETE_CACHE if "Bus" not in item["value"] and "Transport" not in item["value"] and current.lower() in item["search"]][:24]
    choices.append(app_commands.Choice(name="Other", value="Other"))
    return choices

@C.client.tree.command(name="event_thread", description="Manually and immediately create a dedicated thread for a flight signup message.")
@app_commands.describe(flight_code="Flight code to create a thread for")
@app_commands.autocomplete(flight_code=C.active_flight_autocomplete)
@C.event_manager_only
async def event_thread_cmd(interaction: discord.Interaction, flight_code: str):
    if not C.is_event_manager_or_chief(interaction.user) and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this.')]))
    
    await interaction.response.defer(ephemeral=True)
    
    flight = next((f for f in C.FLIGHT_LOG_CACHE if f["flight_code"] == flight_code), None)
    if not flight:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Flight not found.')]))
    
    s_ch = C.client.get_channel(flight["staff_channel_id"])
    if not s_ch:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Staff channel not found.')]))
    
    try:
        msg = await s_ch.fetch_message(flight["staff_message_id"])
        

        if msg.thread:
            return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Thread already exists: {msg.thread.mention}')]))
            
        thread_name = f"Discussion: {flight['flight_code']}"
        thread = await msg.create_thread(name=thread_name, auto_archive_duration=1440)
        await C._cleanup_thread_created_notice(s_ch)
        

        attendees = [f"<@{uid}>" for uid in flight.get("accepted_users", [])]
        mention_str = " ".join(attendees) if attendees else "No participants yet"
        
        await thread.send(content=f"**{flight['flight_code']} Discussion Thread**\n{mention_str}")
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Discussion thread created manually: {thread.mention}')]))
        
    except Exception as e:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Failed to create thread: {e}')]))

@C.client.tree.command(name="inactive_staff", description="[Admin] List staff who have not participated in any flight in the past month.")
async def inactive_staff_cmd(interaction: discord.Interaction):
    if C.LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))

    await interaction.response.defer(ephemeral=False)

    jst_now = datetime.datetime.now(C.JST)
    month_ago = (jst_now - datetime.timedelta(days=30)).timestamp()
    
    participated_users = set()
    channels_to_check = [C.FLIGHT_LOG_HISTORY_CHANNEL_ID, C.MANUAL_LOG_CHANNEL_ID]
    

    for ch_id in channels_to_check:
        ch = C.client.get_channel(ch_id)
        if not ch: continue
        try:
            async for msg in ch.history(limit=1500):
                parsed = C.parse_log_message(msg)
                if parsed and parsed["timestamp"] >= month_ago:
                    for uid in parsed["participants"]:
                        participated_users.add(uid)
        except Exception as e:
            print(f"Log fetch error: {e}")

    staff_guild = C.client.get_guild(C.STAFF_GUILD_ID)
    if not staff_guild:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Could not fetch staff server information.')]))


    target_roles = [C.ROLE_FLIGHT_OPS, C.ROLE_CABIN_CREWS, C.ROLE_GROUND_OPS, C.ROLE_BUS_DRIVER_1]
    inactive_members = []

    for member in staff_guild.members:
        if member.bot: continue
        role_ids = [r.id for r in member.roles]
        

        if any(rid in role_ids for rid in C.EXCLUDE_REMIND_ROLE_IDS) or C.LOA_ROLE_ID in role_ids:
            continue


        if C.is_exempt_from_flight_reminder(member, jst_now):
            continue
            
        has_target_role = any(r_id in role_ids for r_id in target_roles)
        if has_target_role and member.id not in participated_users:
            inactive_members.append(member)

    if not inactive_members:
        embed = discord.Embed(title="Staff inactive for the past month", description="No inactive staff (everyone is active).", color=discord.Color.green())
        return await interaction.followup.send(view=C.embed_to_v2_layout(embed, content=None))

    desc = "\n".join([m.mention for m in inactive_members])
    if len(desc) > 4000:
        desc = desc[:4000] + "\n...(and more)"

    embed = discord.Embed(
        title=f"Staff inactive for the past month ({len(inactive_members)})",
        description=desc,
        color=discord.Color.red()
    )
    embed.set_footer(text="Staff on leave (LOA) are automatically excluded.")
    await interaction.followup.send(view=C.embed_to_v2_layout(embed, content=None))

@C.client.tree.command(name="flight_app", description="Submit a flight/event hosting application.")
@app_commands.describe(
    departure_date="Date (e.g., 2026/08/16)",
    departure_time="Time (e.g., 20:00)",
    current_local_time="Your current local time (e.g., 14:00)",
    flight_code="Flight Code (Search or select 'Other')",
    equipment="Aircraft (Search or type manually)",
    event_type="Select event type"
)
@app_commands.autocomplete(flight_code=flight_app_code_autocomplete, equipment=C.equipment_autocomplete)
@app_commands.choices(event_type=[
    app_commands.Choice(name="Normal Event", value="Normal Event"),
    app_commands.Choice(name="Airshow", value="Airshow"),
    app_commands.Choice(name="Special Event", value="Special Event"),
    app_commands.Choice(name="Other", value="Other")
])
async def flight_app_cmd(interaction: discord.Interaction, departure_date: str, departure_time: str, current_local_time: str, flight_code: str, equipment: str, event_type: str):
    tz_str, offset_hrs = C.calculate_tz_offset(current_local_time)
    
    if flight_code != "Other" and flight_code in C.FLIGHT_DB:
        origin = C.FLIGHT_DB[flight_code].get("origin", "")
        dest = C.FLIGHT_DB[flight_code].get("destination", "")
        variants = C.FLIGHT_DB[flight_code].get("variants", {})
        
        airline = "Airline"
        clean_equip = equipment.replace(" (Registered)", "").replace("(Registered)", "").strip()
        

        for k, v in variants.items():
            if k.lower() == clean_equip.lower():
                airline = v.get("airline", "Airline")
                clean_equip = k
                break
                
        detail = event_type if event_type != "Other" else "Normal Event"
        await C.process_flight_application(interaction, departure_date, departure_time, tz_str, offset_hrs, flight_code, origin, dest, f"{airline} / {clean_equip}", detail)
    else:

        modal = FlightAppModal(departure_date, departure_time, flight_code, event_type, tz_str, offset_hrs, equipment)
        await interaction.response.send_modal(modal)

@C.client.tree.command(name="flight_app_backup", description="[Admin] Convert an old text-format flight application into the current digital format.")
@app_commands.describe(message_id="Message ID of the old application to convert")
async def flight_app_backup_cmd(interaction: discord.Interaction, message_id: str):
    if C.FLIGHT_VERIFIER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this.')]))
        
    await interaction.response.defer(ephemeral=True)
    target_channel = interaction.channel
    
    try:
        msg = await target_channel.fetch_message(int(message_id.strip()))
    except Exception:
        return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Message not found. Run this command in the channel that contains the target message.')]))

    lines = msg.content.split('\n')
    data = {
        "user_id": interaction.user.id, "user_name": "Unknown", "avatar_url": None,
        "date": "", "time": "", "tz": "UTC+9", "origin": "", "dest": "",
        "airline": "Airline", "flight_code": "", "equipment": "", "detail": ""
    }
    offset_hrs = 9

    for line in lines:
        line_clean = line.strip()
        if not line_clean: continue
        
        if "Host" in line_clean:
            match = re.search(r'<@!?(\d+)>', line_clean)
            if match:
                data["user_id"] = int(match.group(1))
                member = interaction.guild.get_member(data["user_id"])
                if member:
                    data["user_name"] = member.display_name
                    data["avatar_url"] = member.display_avatar.url if member.display_avatar else None
            else:
                name_match = re.search(r'@([^\s|]+)', line_clean)
                if name_match:
                    search_name = name_match.group(1).strip()
                    for m in interaction.guild.members:
                        if search_name.lower() in m.display_name.lower() or search_name.lower() in m.name.lower():
                            data["user_id"] = m.id
                            data["user_name"] = m.display_name
                            data["avatar_url"] = m.display_avatar.url if m.display_avatar else None
                            break
        elif "Date" in line_clean:
            data["date"] = line_clean.split(":", 1)[-1].strip()
        elif "Time" in line_clean:
            t_str = line_clean.split(":", 1)[-1].strip()
            time_match = re.search(r'(\d{1,2}:\d{2})', t_str)
            if time_match:
                data["time"] = time_match.group(1)
            else:
                data["time"] = t_str
                
            if "GMT" in t_str or "UTC" in t_str:

                match = re.search(r'(?:GMT|UTC)\s*([+-]\d{1,2}(?::?\d{2})?)', t_str)
                if match:
                    data["tz"] = f"UTC{match.group(1)}"
                    offset_hrs = C.parse_timezone_offset(f"UTC{match.group(1)}")
        elif "Origin" in line_clean:
            data["origin"] = line_clean.split(":", 1)[-1].strip()
        elif "Destination" in line_clean:
            data["dest"] = line_clean.split(":", 1)[-1].strip()
        elif "Airline" in line_clean:
            data["airline"] = line_clean.split(":", 1)[-1].strip()
        elif "Flight Code" in line_clean:
            data["flight_code"] = line_clean.split(":", 1)[-1].strip()
        elif "Equipment" in line_clean:
            data["equipment"] = line_clean.split(":", 1)[-1].strip()
        elif "Detail" in line_clean:
            data["detail"] = line_clean.split(":", 1)[-1].strip()

    ts = C.parse_date_time_to_ts(data["date"], data["time"], offset_hrs)
    
    is_approved = False
    if any(emoji in msg.content for emoji in [C.FLIGHT_APPROVED_EMOJI, "☑️", "✅", "✔️", "☑"]):
        is_approved = True
    for reaction in msg.reactions:
        if getattr(reaction.emoji, "id", None) == C.FLIGHT_APPROVED_EMOJI_ID or str(reaction.emoji) in [C.FLIGHT_APPROVED_EMOJI, "☑️", "✅", "✔️", "☑"]:
            is_approved = True

    embed = C.generate_flight_app_embed(data, ts)
    view = C.FlightAppView()
    
    if is_approved:
        embed.color = discord.Color.green()
        embed.title = "Flight Application (Approved)"
        embed.add_field(name="Status", value="Approved (Legacy Backup)", inline=False)
        for child in view.children:
            child.disabled = True
            
    await target_channel.send(content=f"<@&{C.FLIGHT_VERIFIER_ROLE_ID}>", embed=embed, view=view)
    
    try: await msg.delete()
    except Exception: pass
        
    await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Backup (digitization) complete. Old messages were converted and removed.')]))
    

    await C.send_flight_app_guidance(target_channel)
