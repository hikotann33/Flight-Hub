import discord
from discord import app_commands

from . import core as C
from . import config_store as cs
from . import ui_theme as theme

CHANNEL_SPECS = [
    ("staff", "channels.staff_announce", "staff-announcements", "text"),
    ("staff", "channels.flight_input", "flight-input", "text"),
    ("staff", "channels.flight_log", "flight-log", "text"),
    ("staff", "channels.flight_log_history", "flight-log-history", "text"),
    ("staff", "channels.manual_log", "manual-log", "text"),
    ("staff", "channels.briefing", "briefing", "text"),
    ("staff", "channels.remind_track", "remind-track", "text"),
    ("staff", "channels.command", "commands", "text"),
    ("staff", "channels.reflection", "reflection", "text"),
    ("staff", "channels.flight_app", "flight-applications", "text"),
    ("staff", "channels.eval_track", "evaluations", "text"),
    ("staff", "channels.audit_log", "audit-log", "text"),
    ("staff", "channels.loa_track", "loa", "text"),
    ("staff", "channels.misc_data", "bot-data", "text"),
    ("staff", "channels.test_json", "bot-test-data", "text"),
    ("staff", "channels.test_staff", "test-flight", "text"),
    ("staff", "channels.flight_channel_category", "Flights", "category"),
    ("staff", "channels.test_briefing_category", "Test Briefings", "category"),
    ("customer", "channels.customer_announce", "announcements", "text"),
    ("customer", "channels.test_customer_category", "Test Flights", "category"),
]

ROLE_SPECS = [
    ("roles.event_manager", "Event Managers"),
    ("roles.ground_ops", "Ground Ops"),
    ("roles.cabin_crew", "Cabin Crews"),
    ("roles.flight_ops", "Flight Ops"),
    ("roles.bus_driver", "Bus Driver"),
    ("roles.chief", "Chief"),
    ("roles.flight_verifier", "Flight Verifier"),
    ("roles.loa", "LOA"),
    ("roles.allowed", "Staff"),
    ("roles.notification", "Notifications"),
    ("roles.join_notification", "Join Notifications"),
    ("roles.dm_target", "DM Target"),
    ("roles.dm_staff", "DM Staff"),
    ("roles.dm_exclude", "DM Exclude"),
    ("roles.exclude_remind", "Exclude Reminders"),
]


def _guild_for_scope(scope):
    guild_id = cs.cfg("guilds.staff") if scope == "staff" else cs.cfg("guilds.customer")
    if not guild_id:
        return None
    import sys
    core = sys.modules.get("flighthub.core")
    client = getattr(core, "client", None) if core else None
    return client.get_guild(int(guild_id)) if client else None


def _ensure_channel(guild, name, kind):
    if guild is None:
        return None, f"server not set for '{name}'"
    if kind == "category":
        found = discord.utils.get(guild.categories, name=name)
        if found:
            return found.id, None
    else:
        found = discord.utils.get(guild.text_channels, name=name)
        if found:
            return found.id, None
    return None, f"missing '{name}' in {guild.name}"


def _ensure_role(guild, name):
    if guild is None:
        return None, f"server not set for role '{name}'"
    found = discord.utils.get(guild.roles, name=name)
    if found:
        return found.id, None
    return None, f"missing role '{name}' in {guild.name}"


def apply_config():
    import sys
    core = sys.modules.get("flighthub.core")
    if core is None:
        return []
    applied = cs.apply_to_core(core)
    for attr in ("STAFF_GUILD", "CUSTOMER_GUILD"):
        if hasattr(core, attr):
            gid = cs.cfg("guilds.staff") if attr == "STAFF_GUILD" else cs.cfg("guilds.customer")
            try:
                setattr(core, attr, discord.Object(id=int(gid)) if gid else None)
            except Exception:
                pass
    return applied


class CustomerGuildSelect(discord.ui.Select):
    def __init__(self, guilds, author_id):
        self.author_id = author_id
        options = [discord.SelectOption(label=(g.name or str(g.id))[:100], value=str(g.id)) for g in guilds[:25]]
        super().__init__(placeholder="Select the customer server...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction):
        gid = int(self.values[0])
        cs.set_value("guilds.customer", gid)
        cs.save()
        apply_config()
        guild = interaction.client.get_guild(gid)
        await interaction.response.edit_message(
            embed=theme.success("Customer server set", f"Customer server: **{guild.name if guild else gid}**"),
            view=SetupPanel(interaction.user.id))


class SetupPanel(discord.ui.View):
    def __init__(self, author_id, timeout=600):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        if not cs.cfg("guilds.staff"):
            self.add_item(UseSelfStaffButton())

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=theme.warning("Not allowed", "Only the person who ran /setup can use these controls."),
                ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Auto-detect channels", style=discord.ButtonStyle.primary, row=1)
    async def detect_channels(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        detected, missing = _scan_channels()
        cs.save()
        apply_config()
        lines = [f"Detected **{len(detected)}** channel(s)."]
        if missing:
            lines.append("Not found: " + ", ".join(f"`{m}`" for m in missing[:15]))
        await interaction.followup.send(embed=theme.info("Channel scan", "\n".join(lines)), ephemeral=True)

    @discord.ui.button(label="Auto-detect roles", style=discord.ButtonStyle.primary, row=1)
    async def detect_roles(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        detected, missing = _scan_roles()
        cs.save()
        apply_config()
        lines = [f"Detected **{len(detected)}** role(s)."]
        if missing:
            lines.append("Not found: " + ", ".join(f"`{m}`" for m in missing[:15]))
        await interaction.followup.send(embed=theme.info("Role scan", "\n".join(lines)), ephemeral=True)

    @discord.ui.button(label="Show config", style=discord.ButtonStyle.secondary, row=1)
    async def show_config(self, interaction, button):
        emb = theme.settings("Current configuration", "\n".join(cs.summary_lines()))
        emb.add_field(name="Config file", value=f"`{cs.config_path()}`", inline=False)
        emb.add_field(name="Setup complete", value=str(cs.is_configured()), inline=False)
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @discord.ui.button(label="Save & finish", style=discord.ButtonStyle.success, row=2)
    async def finish(self, interaction, button):
        cs.set_value("setup.completed", bool(cs.cfg("guilds.staff")))
        cs.save()
        apply_config()
        await interaction.response.send_message(
            embed=theme.success("Setup saved",
                                "Configuration has been written to disk.\n"
                                "Restart the bot (`python run.py`) to fully apply every setting."),
            ephemeral=True)

    @discord.ui.button(label="Customer server", style=discord.ButtonStyle.secondary, row=2)
    async def customer_server(self, interaction, button):
        guilds = list(interaction.client.guilds)
        if not guilds:
            await interaction.response.send_message(embed=theme.error("No servers", "The bot is not in any server."), ephemeral=True)
            return
        view = discord.ui.View(timeout=180)
        view.add_item(CustomerGuildSelect(guilds, self.author_id))
        await interaction.response.send_message(embed=theme.info("Select customer server", "Pick the server used for customers."), view=view, ephemeral=True)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=2)
    async def reset(self, interaction, button):
        cs.set_value("setup.completed", False)
        cs.save()
        await interaction.response.send_message(embed=theme.warning("Reset", "The setup-complete flag was cleared (values were kept)."), ephemeral=True)


class UseSelfStaffButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Use this server as staff server", style=discord.ButtonStyle.primary, row=0)

    async def callback(self, interaction):
        if not interaction.guild:
            await interaction.response.send_message(embed=theme.error("Server only", "Run this in a server."), ephemeral=True)
            return
        cs.set_value("guilds.staff", interaction.guild.id)
        cs.set_value("guilds.log", cs.cfg("guilds.log") or interaction.guild.id)
        cs.save()
        apply_config()
        await interaction.response.edit_message(
            embed=theme.success("Staff server set", f"Staff server: **{interaction.guild.name}**"),
            view=SetupPanel(interaction.user.id))


def _scan_channels():
    detected, missing = [], []
    cache = {}
    for scope, path, name, kind in CHANNEL_SPECS:
        if scope not in cache:
            cache[scope] = _guild_for_scope(scope)
        cid, err = _ensure_channel(cache[scope], name, kind)
        if cid:
            cs.set_value(path, cid)
            detected.append(name)
        else:
            missing.append(name)
    return detected, missing


def _scan_roles():
    detected, missing = [], []
    guild = _guild_for_scope("staff")
    for path, name in ROLE_SPECS:
        rid, err = _ensure_role(guild, name)
        if rid:
            cs.set_value(path, rid)
            detected.append(name)
        else:
            missing.append(name)
    return detected, missing


def _is_admin(interaction):
    user = interaction.user
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


@C.client.tree.command(name="setup", description="Configure Flight Hub (server admins only).")
@app_commands.guild_only()
async def setup_cmd(interaction):
    if not _is_admin(interaction):
        await interaction.response.send_message(
            embed=theme.error("Access denied", "You need the **Manage Server** permission to run /setup."),
            ephemeral=True)
        return
    emb = theme.settings(
        "Flight Hub - Setup",
        "Welcome to the setup wizard.\n\n"
        "1. Set the **staff server**.\n"
        "2. Set the **customer server**.\n"
        "3. Auto-detect channels and roles (names must match, see docs/SETUP.md).\n"
        "4. **Save & finish**, then restart the bot.")
    await interaction.response.send_message(embed=emb, view=SetupPanel(interaction.user.id), ephemeral=True)

