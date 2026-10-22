import re

from .config_store import cfg

TOKEN_RE = re.compile(r"\{([^{}\n\r]+)\}")

DEFAULT_TEMPLATES = {
    "staff_description": "Informational Guidelines for operation",
    "staff_description_test": "Informational Guidelines for Test Operation",
    "staff_description_recurring": "Recurring Operation",
    "customer_post": (
        "{Emoji} **Flight Information**{Updated}\n"
        "Flight code: {Flight Code}\n"
        "Airline: {Airline}\n"
        "Departure Airport: {Origin}\n"
        "Arrival Airport: {Destination}\n"
        "Date: {Date}\n"
        "Check-in Time: {Check-in Time}\n"
        "Server Lock: {Server Lock}\n"
        "Equipment: {Equipment}\n"
        "Classes: {Classes}\n"
        "{Reason}{Mention}{Event Link}"
    ),
    "customer_post_recurring": (
        "{Emoji} **Recurring Flight**\n"
        "Flight code: {Flight Code}\n"
        "Airline: {Airline}\n"
        "Departure Airport: {Origin}\n"
        "Arrival Airport: {Destination}\n"
        "Date: {Date}\n"
        "Check-in Time: {Check-in Time}\n"
        "Server Lock: {Server Lock}\n"
        "Equipment: {Equipment}\n"
        "Classes: {Classes}\n"
        "{Mention}{Event Link}"
    ),
    "calendar_description": (
        "`Host` {Host Mention}\n"
        "`Origin` {Origin}\n"
        "`Destination` {Destination}\n"
        "> Information\n"
        "`Airline` {Airline}\n"
        "`Aircraft` {Equipment}\n"
        "`Classes` {Classes}"
    ),
}


def get_template(key):
    value = cfg(f"templates.{key}", None)
    if value is None:
        value = DEFAULT_TEMPLATES.get(key, "")
    return value


def render(text, context):
    if not text:
        return ""
    context = context or {}

    def _replace(match):
        token = match.group(1)
        if token in context:
            value = context[token]
            return "" if value is None else str(value)
        return match.group(0)

    return TOKEN_RE.sub(_replace, text)
