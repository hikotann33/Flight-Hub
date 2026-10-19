import datetime

import discord

from . import config_store as _cs


def _color(name, fallback):
    return _cs.cfg(f"colors.{name}", fallback)


PRIMARY = _color("primary", 0x1B3444)
SUCCESS = _color("success", 0x2ECC71)
WARNING = _color("warning", 0xF1C40F)
DANGER = _color("danger", 0xE74C3C)
INFO = _color("info", 0x3498DB)
NEUTRAL = 0x4F545C


def color(name, fallback=0x1B3444):
    return _cs.cfg(f"colors.{name}", fallback)


def refresh():
    global PRIMARY, SUCCESS, WARNING, DANGER, INFO
    PRIMARY = _color("primary", 0x1B3444)
    SUCCESS = _color("success", 0x2ECC71)
    WARNING = _color("warning", 0xF1C40F)
    DANGER = _color("danger", 0xE74C3C)
    INFO = _color("info", 0x3498DB)
    return PRIMARY

ICON_SUCCESS = "\u2705"
ICON_WARNING = "\u26a0\ufe0f"
ICON_ERROR = "\u274c"
ICON_INFO = "\u2139\ufe0f"
ICON_SETTINGS = "\u2699\ufe0f"
ICON_SHIELD = "\U0001f6e1\ufe0f"
ICON_WAVE = "\U0001f44b"


def brand_name():
    return _cs.cfg("brand.name", "Flight Hub")


def footer_text():
    return _cs.cfg("brand.footer", brand_name())


def _apply_common(embed, footer=None, timestamp=True, thumbnail=None, author=None):
    embed.set_footer(text=footer or footer_text())
    if timestamp:
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if author:
        embed.set_author(name=author)
    return embed


def embed(title=None, description=None, color=None, fields=None, footer=None,
          thumbnail=None, author=None, timestamp=True, url=None):
    emb = discord.Embed(title=title, description=description,
                        color=color if color is not None else PRIMARY, url=url)
    for name, value, inline in (fields or []):
        emb.add_field(name=name, value=value, inline=inline)
    return _apply_common(emb, footer, timestamp, thumbnail, author)


def success(title=None, description=None, **kwargs):
    return embed(title=f"{ICON_SUCCESS} {title}" if title else None,
                 description=description, color=SUCCESS, **kwargs)


def warning(title=None, description=None, **kwargs):
    return embed(title=f"{ICON_WARNING} {title}" if title else None,
                 description=description, color=WARNING, **kwargs)


def error(title=None, description=None, **kwargs):
    return embed(title=f"{ICON_ERROR} {title}" if title else None,
                 description=description, color=DANGER, **kwargs)


def info(title=None, description=None, **kwargs):
    return embed(title=f"{ICON_INFO} {title}" if title else None,
                 description=description, color=INFO, **kwargs)


def notice(title=None, description=None, **kwargs):
    return embed(title=title, description=description, color=NEUTRAL, **kwargs)


def settings(title=None, description=None, **kwargs):
    return embed(title=f"{ICON_SETTINGS} {title}" if title else None,
                 description=description, color=PRIMARY, **kwargs)


class ConfirmView(discord.ui.View):
    def __init__(self, author_id=None, timeout=120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction):
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=warning("Not allowed", "Only the person who ran this command can use these controls."),
                ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji=ICON_SUCCESS)
    async def confirm(self, interaction, button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji=ICON_ERROR)
    async def cancel(self, interaction, button):
        self.value = False
        self.stop()
        await interaction.response.defer()
