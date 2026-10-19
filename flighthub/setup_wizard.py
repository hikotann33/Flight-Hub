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
    applied += cs.apply_ui_to_core(core)
    try:
        theme.refresh()
    except Exception:
        pass
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


# ---------------------------------------------------------------------------
# Appearance: colours and emojis (everything here is applied live)
# ---------------------------------------------------------------------------

_RESTART_NOTE = ("Changes take effect immediately. Controls that were built at "
                 "startup - such as the approve button of `/flight_app` - need a "
                 "bot restart.")

# A Discord modal holds at most five inputs, so the six colours are split.
COLOR_GROUPS = {
    "main": ("primary", "private"),
    "status": ("success", "warning", "danger", "info"),
}


def color_panel_embeds():
    """A summary embed plus one colour swatch embed per setting."""
    lines = []
    for key in cs.COLOR_KEYS:
        value = cs.cfg(f"colors.{key}", cs.DEFAULTS["colors"][key])
        lines.append(f"{key} - `{cs.format_hex_color(value)}`")
    head = theme.settings(
        "Color settings",
        "\n".join(lines) + "\n\nEvery colour is a 6 digit hex value such as `#1B3444`.\n" + _RESTART_NOTE)
    return [head] + [
        discord.Embed(title=cs.COLOR_LABELS[key], color=cs.cfg(f"colors.{key}", cs.DEFAULTS["colors"][key]))
        for key in cs.COLOR_KEYS
    ]


def emoji_panel_embed():
    lines = [
        "Paste a **Unicode emoji** or a **custom emoji** (`<:name:id>`).",
        "Leave the field empty to go back to the default.",
        "",
        "**Standard icons**",
    ]
    for key, label in cs.EMOJI_LABELS.items():
        lines.append(f"{label} - {cs.current_emoji(key)}")
    lines += ["", "**Recruitment heading icons**"]
    for key, label in cs.SIGNUP_TYPE_LABELS.items():
        lines.append(f"{label} - {cs.current_signup_icon(key)}")
    return theme.settings("Emoji settings", "\n".join(lines) + "\n\n" + _RESTART_NOTE)


class OwnerView(discord.ui.View):
    """A view that only the person who ran /setup may operate."""

    def __init__(self, author_id, timeout=600):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=theme.warning("Not allowed", "Only the person who ran /setup can use these controls."),
                ephemeral=True)
            return False
        return True


class ColorPanelView(OwnerView):
    @discord.ui.button(label="Main colors", style=discord.ButtonStyle.primary, emoji="\U0001f3a8")
    async def edit_main_colors(self, interaction, button):
        await interaction.response.send_modal(ColorModal(self.author_id, COLOR_GROUPS["main"]))

    @discord.ui.button(label="Status colors", style=discord.ButtonStyle.primary)
    async def edit_status_colors(self, interaction, button):
        await interaction.response.send_modal(ColorModal(self.author_id, COLOR_GROUPS["status"]))

    @discord.ui.button(label="Reset colors", style=discord.ButtonStyle.danger)
    async def reset_colors_btn(self, interaction, button):
        cs.reset_colors()
        cs.save()
        apply_config()
        await interaction.response.edit_message(embeds=color_panel_embeds(), view=self)


class ColorModal(discord.ui.Modal):
    """A modal edits at most five colours, so the six are split in two groups."""

    def __init__(self, author_id, keys):
        keys = list(keys)[:5]
        super().__init__(title=("Colors: " + ", ".join(keys))[:45], timeout=600)
        self.author_id = author_id
        self.fields = {}
        for key in keys:
            item = discord.ui.TextInput(
                label=cs.COLOR_LABELS[key],
                default=cs.format_hex_color(cs.cfg(f"colors.{key}", cs.DEFAULTS["colors"][key])),
                placeholder="#1B3444 - leave empty to keep",
                required=False,
                max_length=9,
            )
            self.add_item(item)
            self.fields[key] = item

    async def on_submit(self, interaction):
        errors, new_values = [], {}
        for key, item in self.fields.items():
            raw = (item.value or "").strip()
            if not raw:
                new_values[key] = cs.cfg(f"colors.{key}", cs.DEFAULTS["colors"][key])
                continue
            parsed = cs.parse_hex_color(raw)
            if parsed is None:
                errors.append(f"**{key}**: `{raw}` is not a hex color (use e.g. `#1B3444`).")
            else:
                new_values[key] = parsed
        if errors:
            await interaction.response.send_message(
                embed=theme.error("Check the colors", "\n".join(errors)), ephemeral=True)
            return
        for key, value in new_values.items():
            cs.set_value(f"colors.{key}", value)
        cs.save()
        applied = apply_config()
        await interaction.response.send_message(
            embeds=color_panel_embeds(), view=ColorPanelView(self.author_id), ephemeral=True)
        print(f"[setup] appearance settings applied ({len(applied)} core values updated)")


class EmojiSelect(discord.ui.Select):
    def __init__(self, author_id):
        self.author_id = author_id
        options = []
        for key, label in list(cs.EMOJI_LABELS.items()) + list(cs.SIGNUP_TYPE_LABELS.items()):
            current = cs.current_emoji(key) if key in cs.EMOJI_LABELS else cs.current_signup_icon(key)
            options.append(discord.SelectOption(label=label[:100], value=key, description=f"Now: {current}"[:100]))
        super().__init__(placeholder="Choose an emoji to change...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction):
        key = self.values[0]
        label = cs.EMOJI_LABELS.get(key) or cs.SIGNUP_TYPE_LABELS.get(key, key)
        await interaction.response.send_modal(EmojiEditModal(self.author_id, key, label))


class EmojiPanelView(OwnerView):
    def __init__(self, author_id, timeout=600):
        super().__init__(author_id, timeout)
        self.add_item(EmojiSelect(author_id))

    @discord.ui.button(label="Reset all emojis", style=discord.ButtonStyle.danger, row=1)
    async def reset_all_emojis_btn(self, interaction, button):
        cs.reset_all_emojis()
        cs.save()
        apply_config()
        await interaction.response.edit_message(embed=emoji_panel_embed(), view=EmojiPanelView(self.author_id))


class EmojiEditModal(discord.ui.Modal):
    def __init__(self, author_id, key, label):
        super().__init__(title=f"Emoji: {label}"[:45], timeout=300)
        self.author_id = author_id
        self.key = key
        self.label = label
        current = cs.current_emoji(key) if key in cs.EMOJI_LABELS else cs.current_signup_icon(key)
        self.field = discord.ui.TextInput(
            label="New emoji",
            placeholder="✅ or <:name:123456789012345678>",
            default=(str(current)[:60] if current else None),
            required=False,
            max_length=80,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction):
        value, error = cs.parse_emoji_value(self.field.value, as_id=(self.key == "flight_approved"))
        if error:
            await interaction.response.send_message(
                embed=theme.error("Invalid emoji", error), ephemeral=True)
            return
        if value is None:
            cs.reset_emoji(self.key)
            action = "reset to the default"
        else:
            if self.key == "flight_approved":
                cs.set_value("emojis.flight_approved", value)
            elif self.key in cs.DEFAULT_SIGNUP_TYPE_ICONS:
                cs.set_value(f"emojis.signup_type.{self.key}", value)
            else:
                cs.set_value(f"emojis.{self.key}", value)
            action = "saved"
        cs.save()
        apply_config()
        shown = cs.current_emoji(self.key) if self.key in cs.EMOJI_LABELS else cs.current_signup_icon(self.key)
        await interaction.response.send_message(
            embed=theme.success("Emoji updated",
                                f"{self.label} is now {shown} ({action}).\n" + _RESTART_NOTE),
            view=EmojiPanelView(self.author_id), ephemeral=True)


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

    @discord.ui.button(label="Colors", style=discord.ButtonStyle.secondary, row=3, emoji="\U0001f3a8")
    async def colors(self, interaction, button):
        await interaction.response.send_modal(ColorModal(self.author_id, COLOR_GROUPS["main"]))

    @discord.ui.button(label="Emojis", style=discord.ButtonStyle.secondary, row=3, emoji="\U0001f3ad")
    async def emojis(self, interaction, button):
        await interaction.response.send_message(
            embed=emoji_panel_embed(), view=EmojiPanelView(self.author_id), ephemeral=True)


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
        "4. Set the **colors** (the main dark blue and the status colors).\n"
        "5. Set the **emojis** (stock Unicode emoji are built in, custom emoji are optional).\n"
        "6. **Save & finish**, then restart the bot.")
    await interaction.response.send_message(embed=emb, view=SetupPanel(interaction.user.id), ephemeral=True)

