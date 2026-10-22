from .config_store import cfg

ROLE_WARNING_1 = cfg("roles.warning_1")
ROLE_WARNING_2_A = cfg("roles.warning_2_a")
ROLE_WARNING_2_B = cfg("roles.warning_2_b")
ROLE_LAST_WARNING = cfg("roles.last_warning")

WARNING_ROLE_ORDER = (ROLE_WARNING_1, ROLE_WARNING_2_A, ROLE_WARNING_2_B, ROLE_LAST_WARNING)
