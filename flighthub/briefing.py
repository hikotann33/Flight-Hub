import discord

from . import core as C

class ManualLogModal(discord.ui.Modal, title="Manual Flight Log"):
    flight_code = discord.ui.TextInput(label="Flight Code", placeholder="JI123", required=True)
    host_id = discord.ui.TextInput(label="Host User ID", placeholder="123456789012345678", required=True)
    participants = discord.ui.TextInput(
        label="Participants", 
        style=discord.TextStyle.paragraph, 
        placeholder="e.g.,\n> Captain: <@123456>\n> Cabin Crew: <@234567>", 
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        content = f"**{C.EMOJI_BRAND_STR} | {self.flight_code.value.strip()} Manual-log**\n\n"
        content += f"**Flight Management**\n> Host: <@{self.host_id.value.strip()}>\n\n"
        content += f"**Staff Participants**\n{self.participants.value}\n"
        
        ch = C.client.get_channel(C.MANUAL_LOG_CHANNEL_ID)
        if ch:
            await ch.send(content)
            await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, C.EMOJI_CHECK_STR + ' Manual log added successfully.')]))
        else:
            await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, C.EMOJI_X_STR + ' Error: Storage channel not found.')]))
