import asyncio
import datetime
import io
import json
import traceback

import discord
from discord import app_commands

from . import core as C


@C.client.tree.command(name="aps", description="[Admin] Download a user's message history as JSON.")
@app_commands.describe(user="The user whose message history you want to download", months="How many months to look back. Defaults to 6 months.")
@app_commands.choices(months=[
    app_commands.Choice(name="1 month", value=1),
    app_commands.Choice(name="3 months", value=3),
    app_commands.Choice(name="6 months", value=6),
    app_commands.Choice(name="12 months", value=12),
])
async def aps_cmd(interaction: discord.Interaction, user: discord.Member, months: app_commands.Choice[int] = None):
    if C.ADMIN_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
        await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))
        return

    await interaction.response.defer(ephemeral=True)

    guild = C.client.get_guild(C.STAFF_GUILD_ID)
    if guild is None:
        try:
            guild = await C.client.fetch_guild(C.STAFF_GUILD_ID)
        except Exception:
            guild = None
    if guild is None:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Could not access the staff server.')]))
        return

    try:
        selected_months = months.value if months is not None else 6
        lookback_days = int(round(selected_months * 30.44))
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=lookback_days)

        target_channels = list(guild.text_channels) + list(guild.threads)

        me = guild.me or guild.get_member(C.client.user.id)
        scannable = []
        for ch in target_channels:
            try:
                perms = ch.permissions_for(me) if me else None
                if perms and perms.view_channel and perms.read_message_history:
                    scannable.append(ch)
            except Exception:
                continue

        collected = []
        error_channels = []
        progress_lock = asyncio.Lock()
        done_count = 0
        last_edit_time = datetime.datetime.now(datetime.timezone.utc)

        async def scan_channel(channel):
            nonlocal done_count, last_edit_time
            local_msgs = []
            try:
                async for message in channel.history(after=since, limit=None, oldest_first=True):
                    if message.author.id == user.id:
                        if message.content:
                            local_msgs.append({"content": message.content})
            except discord.Forbidden:
                async with progress_lock:
                    error_channels.append(getattr(channel, "name", str(channel.id)))
            except Exception as e:
                print(f"/aps Channel Scan Error ({getattr(channel, 'name', channel.id)}): {e}")
                async with progress_lock:
                    error_channels.append(getattr(channel, "name", str(channel.id)))

            async with progress_lock:
                done_count += 1
                collected.extend(local_msgs)
                now = datetime.datetime.now(datetime.timezone.utc)
                if (now - last_edit_time).total_seconds() >= 3:
                    last_edit_time = now
                    try:
                        await interaction.edit_original_response(
                            content=f"Collecting... {done_count}/{len(scannable)} channels done ({len(collected)} messages)")
                    except Exception:
                        pass

        SEM = asyncio.Semaphore(8)

        async def scan_with_sem(channel):
            async with SEM:
                await scan_channel(channel)

        if scannable:
            await interaction.edit_original_response(content=f"Starting collection... (target channels: {len(scannable)})")
            await asyncio.gather(*(scan_with_sem(ch) for ch in scannable))

        export_data = {
            "user_id": user.id,
            "user_name": str(user),
            "display_name": user.display_name,
            "range_months": selected_months,
            "message_count": len(collected),
            "messages": [m["content"] for m in collected],
        }

        json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
        file_buffer = io.BytesIO(json_bytes)
        filename = f"aps_{user.id}_{datetime.datetime.now(C.JST).strftime('%Y%m%d_%H%M%S')}.json"
        discord_file = discord.File(fp=file_buffer, filename=filename)

        summary = (
            f"Exported the message history of **{user.display_name}**.\n"
            f"Range: last {selected_months} month(s) (~{lookback_days} days)\n"
            f"Messages collected: **{len(collected)}**\n"
            f"Channels scanned: {len(scannable)}"
        )
        if error_channels:
            summary += f"\nSome channels could not be read ({len(error_channels)}, likely missing permissions)."

        await interaction.edit_original_response(content=summary, attachments=[discord_file])
    except Exception as e:
        print(f"/aps Fatal Error: {e}")
        traceback.print_exc()
        try:
            await interaction.edit_original_response(content=f"An error occurred while collecting the message history: {e}")
        except Exception:
            try:
                await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'An error occurred while collecting the message history: {e}')]))
            except Exception:
                pass
