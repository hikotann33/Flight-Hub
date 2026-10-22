import discord
from discord import app_commands
import datetime
import json
import io
import traceback
import asyncio
import copy

from . import core as C
from . import ui_theme as theme

SELFTEST_STAFF_CATEGORY_ID = 0

SELFTEST_CUSTOMER_CATEGORY_ID = C.SELFTEST_CUSTOMER_CATEGORY_ID

SELFTEST_CATEGORY_NAME = "Bot Self-Test"

SELFTEST_RESP_UID = 1

_SELFTEST_RUNNING = False

TEST_MODE_CATEGORY_NAME = "Flight-Hub-Test-Environment"

TEST_JSON_GUILD_ID = C.LOG_GUILD_ID

_TEST_MODE_LOCK = asyncio.Lock()

_TEST_SESSION_START_TS = None

_TEST_AUTO_REPORT_TEXT = ""

def _test_mode_category_overwrites(guild, member):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }


    if isinstance(member, discord.Member) and C._test_admin_allowed(member):
        overwrites[member] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_channels=True, attach_files=True, embed_links=True
        )
    return overwrites

async def _test_mode_get_category(guild, member):
    if guild is None or guild.id != C.STAFF_GUILD_ID:
        return None
    category = discord.utils.get(guild.categories, name=TEST_MODE_CATEGORY_NAME)
    if category is None:
        category = await guild.create_category(
            TEST_MODE_CATEGORY_NAME,
            overwrites=_test_mode_category_overwrites(guild, member),
            reason="/test_admin isolated test environment"
        )
    else:
        await category.edit(
            overwrites=_test_mode_category_overwrites(guild, member),
            reason="Ensure test category is admin-only"
        )
    return category

async def _test_mode_load():
    found, data = await C.read_latest_json_backup(C.TEST_JSON_CHANNEL_ID, filename=C.TEST_JSON_FILENAME, limit=100)
    if found and isinstance(data, dict):
        flights = data.get("flights", [])
        audit = data.get("command_audit", [])
        C.TEST_FLIGHT_CACHE = flights if isinstance(flights, list) else []
        C.TEST_COMMAND_AUDIT = audit if isinstance(audit, list) else []
        return True
    C.TEST_FLIGHT_CACHE, C.TEST_COMMAND_AUDIT = [], []
    return not found

_TEST_SUITE_LABELS = [
    ("create_flight", "Create test flight (/create_flight)"),
    ("briefing", "Create briefing / random staff selection (/briefing)"),
    ("edit_briefing", "Edit briefing (/edit_briefing)"),
    ("flight_log", "Create Flight-log → chat history TXT → send survey (/flight_log)"),
]

def _test_build_final_report(owner) -> str:
    now = datetime.datetime.now(C.JST)
    rows = [r for r in C.TEST_COMMAND_AUDIT
            if _TEST_SESSION_START_TS is None or int(r.get("timestamp", 0)) >= int(_TEST_SESSION_START_TS)]
    ok = sum(1 for r in rows if r.get("status") == "OK")
    ng = sum(1 for r in rows if r.get("status") == "FAIL")
    sk = sum(1 for r in rows if r.get("status") == "SKIP")
    verdict = ("Not evaluated (no runs)" if not rows else "Needs fixes (failures)" if ng else "Pass (no failures)")
    lines = ["Flight Hub Test Environment Report",
             f"Output: {now:%Y-%m-%d %H:%M:%S} JST",
             f"Run by: {owner} ({getattr(owner, 'id', '?')})"]
    if _TEST_SESSION_START_TS:
        lines.append(f"Start: {datetime.datetime.fromtimestamp(int(_TEST_SESSION_START_TS), C.JST):%Y-%m-%d %H:%M:%S} JST")
    lines += [f"Overall: {verdict}", f"Records {len(rows)} / OK {ok} / Failed {ng} / Stopped (SKIP) {sk}", "",
              "=" * 60, "1. Manual test items (create_flight / briefing / edit_briefing / flight_log)", "=" * 60]
    latest = {}
    for r in rows:
        latest[r.get("command")] = r
    for cmd, label in _TEST_SUITE_LABELS:
        r = latest.get(cmd)
        if r is None:
            lines.append(f"[Not run] {label}")
        else:
            lines.append(f"[{r.get('status')}] {label}  ({datetime.datetime.fromtimestamp(int(r.get('timestamp', 0)), C.JST):%H:%M:%S})")
    lines += ["", "=" * 60, "2. All operation logs from this run (chronological)", "=" * 60]
    if not rows:
        lines.append("(no operation records)")
    for r in rows:
        t = datetime.datetime.fromtimestamp(int(r.get("timestamp", 0)), C.JST)
        lines.append(f"{t:%H:%M:%S} [{r.get('status')}] {r.get('command')}")
        det = r.get("details") or {}
        if det:
            try:
                lines.append("      " + json.dumps(det, ensure_ascii=False, default=str)[:1500])
            except Exception:
                lines.append(f"      {det}")
    lines += ["", "=" * 60, "3. Automatic checks at startup (all commands, persistent buttons, events, JSON saving, surveys, etc.)", "=" * 60,
              _TEST_AUTO_REPORT_TEXT or "(no automatic check results; they may have been lost due to a bot restart, etc.)"]
    return "\n".join(lines)

async def _test_mode_auto_check(interaction) -> str:
    global _SELFTEST_RUNNING
    if _SELFTEST_RUNNING:
        return "Automatic check: skipped because another /selftest is running."
    _SELFTEST_RUNNING = True
    try:
        result_ch, rep, started, finished = await _selftest_run(interaction.user, False)
    except Exception as exc:
        traceback.print_exc()
        await C._test_mode_record("auto_check", interaction.user.id, "FAIL", {"error": str(exc)})
        return f"Error during automatic check: {type(exc).__name__}: {exc}"
    finally:
        _SELFTEST_RUNNING = False

    try:
        await _auto_run_commands(interaction.user, interaction.guild, rep)
    except Exception as exc:
        traceback.print_exc()
        rep.add("FAIL", "Auto command run", "Automatic run setup/cleanup", f"{type(exc).__name__}: {exc}")
    global _TEST_AUTO_REPORT_TEXT
    try:
        _TEST_AUTO_REPORT_TEXT = _st_report_text(rep, interaction.user, started, datetime.datetime.now(C.JST))
    except Exception as exc:
        _TEST_AUTO_REPORT_TEXT = f"(could not turn the automatic check details into text: {exc})"
    if result_ch:
        try:
            await result_ch.send(file=discord.File(
                io.BytesIO(_st_report_text(rep, interaction.user, started, datetime.datetime.now(C.JST)).encode("utf-8")),
                filename=f"test_admin_{started:%Y%m%d_%H%M%S}.txt"))
        except Exception as exc:
            print(f"auto check report upload error: {exc}")
    fails, warns = rep.count("FAIL"), rep.count("WARN")
    await C._test_mode_record("auto_check", interaction.user.id, "FAIL" if fails else "OK",
                            {"ok": rep.count("OK"), "warn": warns, "fail": fails, "skip": rep.count("SKIP")})
    bad = [f"• [{st}] {sec} / {name}: {detail[:120]}" for st, sec, name, detail in rep.rows if st in ("FAIL", "WARN")]
    head = (f"**Auto check result: {'All code OK' if not fails and not warns else f'{fails} issue(s) / {warns} warning(s)'}**\n"
            f"OK {rep.count('OK')} / WARN {warns} / FAIL {fails} / SKIP {rep.count('SKIP')}")
    if result_ch:
        head += f"\nDetails: {result_ch.mention}"
    return head + ("\n" + "\n".join(bad[:10]) if bad else "")

@C.client.tree.command(name="test_admin", description="[Administrator only] Toggle isolated test mode; production announcements are disabled.", guild=C.STAFF_GUILD)
@app_commands.guild_only()
async def test_admin_cmd(interaction: discord.Interaction):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C._test_admin_allowed(interaction.user):
        return await interaction.response.send_message(
            ephemeral=True, view=C.build_v2_card("Permission denied", [(None, "Discord administrator (Administrator) permission is required.")]))
    await interaction.response.defer(ephemeral=True, thinking=True)
    started_now = False
    _send_final_report = False
    _final_report_txt = ""
    global _TEST_SESSION_START_TS, _TEST_AUTO_REPORT_TEXT
    async with _TEST_MODE_LOCK:
        if C.TEST_MODE:
            try:
                _final_report_txt = _test_build_final_report(interaction.user)
            except Exception as _exc:
                _final_report_txt = f"Could not create the report: {type(_exc).__name__}: {_exc}"
            _send_final_report = True
            C.TEST_MODE = False
            C.TEST_MODE_OWNER_ID = None
            for _c in [c for c, f in C._SELFTEST_FLIGHTS.items() if str(c).startswith("[TEST]")]:
                C._SELFTEST_FLIGHTS.pop(_c, None)
            await C._test_cleanup_briefing_channels()
            await C._test_mode_save()
            _tot = len(C.TEST_COMMAND_AUDIT)
            _ok = sum(1 for r in C.TEST_COMMAND_AUDIT if r.get("status") == "OK")
            _ng = sum(1 for r in C.TEST_COMMAND_AUDIT if r.get("status") == "FAIL")
            _sk = sum(1 for r in C.TEST_COMMAND_AUDIT if r.get("status") == "SKIP")
            _recent = "\n".join(
                f"• `{r.get('command')}` — {r.get('status')} — <t:{int(r.get('timestamp', 0))}:R>"
                for r in reversed(C.TEST_COMMAND_AUDIT[-10:])) or "No test history."
            _verdict = ("Not evaluated (no runs)" if _tot == 0 else
                        "Needs fixes (failures)" if _ng else "Pass (no failures)")
            msg = ("Test environment ended. Subsequent commands will run in normal mode.\n\n"
                   f"**Result: {_verdict}**\nRuns: {_tot} / OK: {_ok} / Failed: {_ng} / Safe stop (SKIP): {_sk}\n\n"
                   f"Recent operations:\n{_recent}\n\nDetails are also available via `/test_evaluate`, and progress via `/test_progress`.")
        else:
            try:
                await _test_mode_load()
                await _test_mode_get_category(interaction.guild, interaction.user)
            except Exception as exc:
                return await interaction.followup.send(
                    ephemeral=True, view=C.build_v2_card("Test mode could not start", [(None, f"Failed to create the category or read JSON: {exc}")]))
            C.TEST_MODE = True
            C.TEST_MODE_OWNER_ID = interaction.user.id
            _TEST_SESSION_START_TS = int(datetime.datetime.now(C.JST).timestamp())
            _TEST_AUTO_REPORT_TEXT = ""
            await C._test_mode_save()
            msg = (f"Test environment started. Save location: `{TEST_JSON_GUILD_ID}/{C.TEST_JSON_CHANNEL_ID}`."
                   "Production announcements, event creation, and external sheet sync will not be performed.\n"
                   "Commands to try manually: `/create_flight` → `/briefing` → `/edit_briefing` → `/flight_log`")
            started_now = True
    if started_now:


        await interaction.followup.send(ephemeral=True, view=C.build_v2_card("Flight Hub Test Environment", [(None, msg + "\n\nRunning automatic checks. This takes a few minutes...")]))
        auto = await _test_mode_auto_check(interaction)
        msg = msg + "\n\n" + auto
    await interaction.followup.send(ephemeral=True, view=C.build_v2_card("Flight Hub Test Environment", [(None, msg)]))
    if _send_final_report:

        _stamp = datetime.datetime.now(C.JST).strftime("%Y%m%d_%H%M%S")
        try:
            await interaction.followup.send(
                content="This is the test report (all items). Please check the TXT file.",
                file=discord.File(io.BytesIO(_final_report_txt.encode("utf-8")), filename=f"test_admin_report_{_stamp}.txt"),
                ephemeral=True)
        except Exception as exc:
            print(f"test_admin final report send error: {exc}")
            await interaction.followup.send(
                ephemeral=True, view=C.build_v2_card("Report failed", [(None, f"Failed to send the report TXT: {exc}")], color=theme.DANGER))

@C.client.tree.command(name="test_evaluate", description="[Administrator only] Save and evaluate all commands run in test mode.", guild=C.STAFF_GUILD)
@app_commands.guild_only()
async def test_evaluate_cmd(interaction: discord.Interaction):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C._test_admin_allowed(interaction.user):
        return await interaction.response.send_message(
            ephemeral=True, view=C.build_v2_card("Permission denied", [(None, "Discord administrator (Administrator) permission is required.")]))
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await C._test_mode_save()
        total = len(C.TEST_COMMAND_AUDIT)
        ok = sum(1 for r in C.TEST_COMMAND_AUDIT if r.get("status") == "OK")
        fail = sum(1 for r in C.TEST_COMMAND_AUDIT if r.get("status") == "FAIL")
        other = total - ok - fail
        pct = (ok / total * 100) if total else 0.0
        if total == 0:
            verdict = "Not evaluated — there are no test command runs recorded yet."
        elif fail == 0 and other == 0:
            verdict = "Pass — none of the recorded test operations failed."
        elif fail:
            verdict = "Needs fixes — some operations failed. Please check the details."
        else:
            verdict = "Provisional — there are incomplete or undecidable operations."
        latest = C.TEST_COMMAND_AUDIT[-12:]
        detail = "\n".join(
            f"• `{r.get('command')}` — {r.get('status')} — <t:{int(r.get('timestamp', 0))}:R>"
            for r in reversed(latest)
        ) or "No test history."
        saved = await C._test_mode_save()
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card(
            "Test Evaluation",
            [("Result", verdict), ("Summary", f"Runs: {total} / OK: {ok} / Failed: {fail} / Other: {other} / Success rate: {pct:.1f}%"),
             ("JSON save", "Saved" if saved else "Save failed — check the bot permissions and the save channel."),
             ("Recent operations", detail)],
            color=theme.SUCCESS if total and fail == 0 and other == 0 and saved else (theme.DANGER if fail or not saved else theme.WARNING)))
    except Exception as exc:
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card(
            "Evaluation error", [(None, f"Failed to evaluate or save JSON: {exc}")], color=theme.DANGER))

@C.client.tree.command(name="test_progress", description="Show visual test coverage and current progress.", guild=C.STAFF_GUILD)
@app_commands.guild_only()
async def test_progress_cmd(interaction: discord.Interaction):
    if interaction.guild_id != C.STAFF_GUILD_ID or not C._test_admin_allowed(interaction.user):
        return await interaction.response.send_message(
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            view=C.build_v2_card("Permission denied", [(None, "Discord administrator (Administrator) permission is required.")]))

    suite = [
        ("create_flight", "Create test flight"),
        ("briefing", "Create briefing / random staff selection"),
        ("edit_briefing", "Edit briefing"),
        ("flight_log", "Create Flight-log → send survey (runner only)"),
    ]
    latest = {}
    for row in C.TEST_COMMAND_AUDIT:
        latest[row.get("command")] = row
    lines = []
    passed = failed = pending = 0
    for cmd, label in suite:
        row = latest.get(cmd)
        if row and row.get("status") == "OK":
            symbol, status = "🟩", "Done"
            passed += 1
        elif row and row.get("status") == "FAIL":
            symbol, status = "🟥", "Failed / needs fixes"
            failed += 1
        else:
            symbol, status = "⬜", "Incomplete"
            pending += 1
        lines.append(f"{symbol} **{label}** — `{status}`")
    total = len(suite)
    done = passed + failed
    pct = round(done / total * 100) if total else 0
    filled = round(pct / 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    skipped = sum(1 for r in C.TEST_COMMAND_AUDIT if r.get("status") == "SKIP")
    saved = await C._test_mode_save()
    lines.append(r"\n**Progress Bar**\n" + bar + f" **{pct}%**")
    lines.append(f"**Summary:** Done {passed} / Failed {failed} / Incomplete {pending} / Safe stop (SKIP) {skipped}")
    lines.append("**Note:** This progress covers only the implemented isolated test items. It does not mean that all commands, including unsupported ones, have been fully tested.")
    lines.append("JSON save: " + ("OK" if saved else "Failed (check the save channel permissions)"))
    await interaction.response.send_message(
        ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        view=C.build_v2_card("Flight Hub Test Progress Dashboard", [("Test items", "\n".join(lines))],
                           color=theme.SUCCESS if failed == 0 and pending == 0 and saved else (theme.DANGER if failed or not saved else theme.WARNING)))

class _StNamespace:
    def __getattr__(self, name):
        return None

class _StUser:
    def __init__(self, uid, name="selftest"):
        self.id = int(uid)
        self.name = self.display_name = name
        self.mention = f"<@{uid}>"
        self.roles = []
        self.bot = False
        self.guild_permissions = discord.Permissions.none()

class _StResponse:
    def __init__(self):
        self.sent = []
        self._done = False
    def is_done(self):
        return self._done
    async def send_message(self, content=None, **kw):
        self._done = True
        self.sent.append(("send", content, kw))
    async def edit_message(self, **kw):
        self._done = True
        self.sent.append(("edit", kw.get("content"), kw))
    async def defer(self, **kw):
        self._done = True
        self.sent.append(("defer", None, kw))
    async def send_modal(self, modal):
        self._done = True
        self.sent.append(("modal", modal, {}))

class _StFollowup:
    def __init__(self):
        self.sent = []
    async def send(self, *a, **kw):
        self.sent.append((a, kw))

class _StInteraction:
    def __init__(self, user, channel=None, guild=None):
        self.user = user
        self.channel = channel
        self.guild = guild
        self.guild_id = getattr(guild, "id", None)
        self.client = C.client
        self.response = _StResponse()
        self.followup = _StFollowup()
        self.namespace = _StNamespace()
        self.message = None
        self.data = {}
        self.locale = discord.Locale.american_english

class _StReport:
    def __init__(self):
        self.rows = []
    def add(self, status, section, name, detail=""):
        self.rows.append((status, section, name, str(detail or "")))
    def count(self, status):
        return sum(1 for r in self.rows if r[0] == status)

async def _st_step(rep, section, name, fn, timeout=90):
    try:
        res = await asyncio.wait_for(fn(), timeout)
        if isinstance(res, tuple) and len(res) == 2 and res[0] in ("WARN", "SKIP"):
            rep.add(res[0], section, name, res[1])
        else:
            rep.add("OK", section, name, res or "")
        return True
    except asyncio.TimeoutError:
        rep.add("FAIL", section, name, f"Timeout ({timeout}s)")
    except AssertionError as e:
        rep.add("FAIL", section, name, str(e) or "assertion failed")
    except discord.Forbidden as e:
        rep.add("FAIL", section, name, f"Insufficient permissions (Forbidden): {e}")
    except Exception as e:
        rep.add("FAIL", section, name, f"{type(e).__name__}: {e}")
        traceback.print_exc()
    return False

def _st_all_commands():
    out, seen = [], set()
    def walk(cmd):
        if isinstance(cmd, app_commands.Group):
            for c in cmd.commands:
                walk(c)
        elif id(cmd) not in seen:
            seen.add(id(cmd))
            out.append(cmd)
    for c in C.client.tree.get_commands():
        walk(c)
    for g in (C.STAFF_GUILD, C.CUSTOMER_GUILD):
        for c in C.client.tree.get_commands(guild=g):
            walk(c)
    return out

def _st_find(view, cls, **attrs):
    for child in view.children:
        if isinstance(child, cls) and all(getattr(child, k, None) == v for k, v in attrs.items()):
            return child
    return None

def _st_png(w=480, h=270, rgb=(27, 52, 68)):
    import zlib, struct
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

def _st_make_flight(invoker, code):
    now = int(datetime.datetime.now().timestamp())
    return {
        "flight_code": code, "host_id": invoker.id, "origin": "RJTT", "destination": "RJAA",
        "equipment": "B737-800", "start_timestamp": now, "end_timestamp": now + 3600,
        "staff_timestamp": now - 1800, "notify_20min_timestamp": now - 1200,
        "accepted_users": [invoker.id], "declined_users": [],
        "briefing_assignments": {
            "Host": [invoker.id], "Co-host": "N/A", "Captain": [invoker.id],
            "First Officer": [SELFTEST_RESP_UID], "Economy Class": [SELFTEST_RESP_UID],
            "Ground Crew": [invoker.id],
        },
        "is_test": True, "selftest": True, "survey_skip_lang": True,
    }

async def _st_registry(rep, invoker, staff_guild):
    sec = "Commands"
    cmds = _st_all_commands()

    async def t_coroutines():
        bad = [c.qualified_name for c in cmds if not asyncio.iscoroutinefunction(c.callback)]
        assert not bad, "Non-coroutine commands: " + ", ".join(bad)
        return f"Checked {len(cmds)} commands"
    await _st_step(rep, sec, "All command callbacks", t_coroutines)

    async def t_names():
        names = [c.qualified_name for c in cmds]
        dup = sorted({n for n in names if names.count(n) > 1})
        assert not dup, "Duplicate registration: " + ", ".join(dup)
    await _st_step(rep, sec, "Duplicate command names", t_names)

    async def t_selftest_hidden():
        me = next((c for c in cmds if c.name == "selftest"), None)
        assert me is not None, "/selftest is not registered"
        dp = getattr(me, "default_permissions", None)
        assert dp is not None and dp.administrator, "/selftest is not admin-only (default_permissions=administrator)"
        assert getattr(me, "guild_only", False), "/selftest is not guild_only"
    await _st_step(rep, sec, "/selftest is visible only to admins", t_selftest_hidden)

    async def t_sync():
        problems = []
        for label, g in (("staff", C.STAFF_GUILD), ("customer", C.CUSTOMER_GUILD)):
            remote = {c.name for c in await C.client.tree.fetch_commands(guild=g)}
            local = {c.name for c in C.client.tree.get_commands(guild=g)}
            if local - remote:
                problems.append(f"{label}: not synced {sorted(local - remote)}")
            if remote - local:
                problems.append(f"{label}: exists only on Discord {sorted(remote - local)}")
            if len(remote) > 100:
                problems.append(f"{label}: more than 100 commands ({len(remote)})")
            if label == "customer" and "selftest" in remote:
                problems.append("customer: /selftest is registered on the customer server")
        assert not problems, " / ".join(problems)
    await _st_step(rep, sec, "Command sync (matches the Discord registration)", t_sync)


    pairs = {}
    for c in cmds:
        for pname, p in getattr(c, "_params", {}).items():
            cb = getattr(p, "autocomplete", None)
            if callable(cb):
                pairs.setdefault(id(cb), (cb, []))[1].append(f"/{c.qualified_name} {pname}")
    for cb, users in pairs.values():
        async def t_ac(cb=cb):
            fake = _StInteraction(invoker, guild=staff_guild)
            res = await cb(fake, "")
            assert isinstance(res, list), f"Return value is not a list ({type(res).__name__})"
            assert len(res) <= 25, f"More than 25 choices ({len(res)})"
            for ch in res:
                assert isinstance(ch, app_commands.Choice), "Contains something other than Choice"
                assert len(str(ch.name)) <= 100, f"Choice name exceeds 100 characters: {str(ch.name)[:30]}"
            return f"{len(res)}"
        await _st_step(rep, sec, f"Autocomplete {getattr(cb, '__name__', 'cb')} ({users[0]}{' and more' if len(users) > 1 else ''})", t_ac)

async def _st_guild_suite(rep, label, gid, cat_id, invoker, events, created, auto_category, st):
    sec = f"{label} server"
    guild = C.client.get_guild(gid)

    async def t_guild():
        assert guild is not None, f"The bot is not in server {gid} / cannot fetch it"
        return guild.name
    if not await _st_step(rep, sec, "Connect to the server", t_guild):
        return
    st["guild"] = guild

    async def t_perms():
        p = guild.me.guild_permissions
        need = ["manage_channels", "send_messages", "embed_links", "attach_files", "read_message_history", "view_channel"]
        missing = [n for n in need if not getattr(p, n)]
        assert not missing, "Missing required permissions: " + ", ".join(missing)
        soft = ["manage_roles", "manage_events", "manage_threads", "mention_everyone", "create_public_threads"]
        soft_missing = [n for n in soft if not getattr(p, n)]
        if soft_missing:
            return ("WARN", "Permissions required by some features are missing: " + ", ".join(soft_missing))
    await _st_step(rep, sec, "Bot permissions", t_perms)

    async def t_category():
        cat = guild.get_channel(cat_id)
        if isinstance(cat, discord.CategoryChannel):
            st["cat"] = cat
            return f"Using category '{cat.name}'"
        assert auto_category, f"Category with ID {cat_id} was not found (check the category ID and grant the bot view permission)"
        cat = discord.utils.get(guild.categories, name=SELFTEST_CATEGORY_NAME)
        note = "reused"
        if cat is None:
            cat = await guild.create_category(SELFTEST_CATEGORY_NAME, overwrites=C._st_overwrites(guild, invoker),
                                              reason="selftest")
            note = "newly created"
        st["cat"] = cat
        return f"The specified ID ({cat_id}) is not a category, so '{SELFTEST_CATEGORY_NAME}' was {note}"
    await _st_step(rep, sec, "Test category", t_category)
    cat = st.get("cat")
    if cat is None:
        return
    stamp = datetime.datetime.now(C.JST).strftime("%m%d-%H%M%S")

    async def t_create():
        ch = await guild.create_text_channel(f"selftest-{label}-{stamp}", category=cat,
                                             overwrites=C._st_overwrites(guild, invoker), reason="selftest")
        created.append(ch)
        st["chan"] = ch
        assert ch.overwrites_for(guild.default_role).view_channel is False, "view is not denied for @everyone"
        assert not ch.permissions_for(guild.default_role).view_channel, "@everyone can view the channel"
        return "hidden from non-admins"
    if not await _st_step(rep, sec, "Create an admin-only text channel", t_create):
        return
    ch = st["chan"]

    async def t_msg():
        m = await ch.send("selftest message")
        await m.edit(content="selftest message (edited)")
        await m.delete()
    await _st_step(rep, sec, "Send, edit, and delete a message", t_msg)

    async def t_v2():
        await ch.send(view=C.build_v2_card("Self-Test", [("Components V2", "OK")], footer="selftest"))
        await ch.send(view=C.embed_to_v2_layout(discord.Embed(title="selftest", description="embed→V2", color=C.EMBED_COLOR)))
    await _st_step(rep, sec, "Send a Components V2 card", t_v2)

    async def t_embed_file():
        await ch.send(embed=discord.Embed(title="selftest", description="embed", color=C.EMBED_COLOR),
                      file=discord.File(io.BytesIO(b"selftest"), filename="selftest.txt"))
    await _st_step(rep, sec, "Embed + file attachment", t_embed_file)

    async def t_thread():
        m = await ch.send("thread base")
        th = await m.create_thread(name="selftest-thread", auto_archive_duration=60)
        await th.send("thread message")
        await th.delete()
    await _st_step(rep, sec, "Create, send in, and delete a thread", t_thread)

    async def t_pin_notice():
        base = await ch.send("pin base")
        await base.pin(reason="selftest")
        gone = False
        for _ in range(16):
            await asyncio.sleep(0.5)
            found = False
            async for h in ch.history(limit=15):
                if h.type == discord.MessageType.pins_add:
                    found = True
                    break
            if not found:
                gone = True
                break
        try:
            await base.unpin(reason="selftest")
        except Exception:
            pass
        assert gone, "The pinned system notification was not auto-deleted"
    await _st_step(rep, sec, "Auto-deletion of the pin notification", t_pin_notice)

    async def t_vc():
        vc = await guild.create_voice_channel(f"selftest-vc-{stamp}", category=cat,
                                              overwrites=C._st_overwrites(guild, invoker), reason="selftest")
        created.append(vc)
        await vc.send("vc chat test")
    await _st_step(rep, sec, "Create and send a dedicated VC (+VC chat)", t_vc)

    async def t_perm_edit():
        m = guild.get_member(invoker.id)
        assert m is not None, "The runner is not in this server, so permission overwrites cannot be tested"
        await ch.set_permissions(m, view_channel=True, send_messages=True, read_message_history=True)
        await ch.set_permissions(m, overwrite=None)
        await ch.set_permissions(m, view_channel=True, send_messages=True, read_message_history=True)
    if guild.get_member(invoker.id):
        await _st_step(rep, sec, "Channel permission overwrite (same process as granting view permission for a dedicated channel)", t_perm_edit)

    async def t_views():
        problems = []
        for name, factory in (("FlightSignupView", C.FlightSignupView), ("PersistentCustomerView",
                              lambda: C.PersistentCustomerView(link_url="https://discord.com", roblox_url=None)),
                              ("ReflectionView", C.ReflectionView), ("FlightChannelDeleteView", C.FlightChannelDeleteView),
                              ("FlightAppView", C.FlightAppView), ("FlightAppAutoCancelView", C.FlightAppAutoCancelView),
                              ("EvaluationDMView", C.EvaluationDMView)):
            try:
                v = factory()
                await ch.send(content=f"selftest: {name}", view=v)
                v.stop()
            except Exception as e:
                problems.append(f"{name}: {type(e).__name__}: {e}")
        assert not problems, " / ".join(problems)
        return "Successfully sent a message with persistent buttons"
    await _st_step(rep, sec, "Send a message with persistent buttons (View)", t_views)

    if events:
        async def t_event():
            now = datetime.datetime.now(datetime.timezone.utc)
            ev = await guild.create_scheduled_event(
                name=f"[SELFTEST] {label} {stamp}", description="selftest (deleted automatically)",
                start_time=now + datetime.timedelta(hours=1), end_time=now + datetime.timedelta(hours=2),
                entity_type=discord.EntityType.external, location="selftest",
                privacy_level=discord.PrivacyLevel.guild_only, image=_st_png())
            try:
                assert ev.url and str(ev.id) in ev.url, "Could not get the event URL"
                flight = {"flight_code": "ZZSELFTEST", "event_url": ev.url, "is_test": True}
                got = await C.get_flight_calendar_event(flight)
                assert got is not None and got.id == ev.id, "get_flight_calendar_event could not find the event"
                await got.edit(name=f"[SELFTEST] edited {stamp}", description="selftest edited")
                ok = await C.delete_flight_calendar_event(flight)
                assert ok, "delete_flight_calendar_event returned False"
                assert await C.get_flight_calendar_event(flight) is None, "The event still remains after deletion"
                return "Create with image → get → edit → delete (uses production get/delete logic)"
            finally:
                try:
                    await ev.delete()
                except Exception:
                    pass
        await _st_step(rep, sec, "Create, get, edit, and delete a Discord event (calendar)", t_event)

async def _st_data_suite(rep, invoker, st):
    sec = "Data / Flight-log / Survey"
    ch = st.get("chan")
    guild = st.get("guild")
    if ch is None:
        rep.add("SKIP", sec, "Data check", "Skipped because the staff server test channel could not be created")
        return
    tag = datetime.datetime.now().strftime("%H%M%S")
    code = f"ZZSELFTEST{tag}"
    flight = _st_make_flight(invoker, code)

    async def t_json():
        data = [copy.deepcopy(flight)]
        assert await C.save_json_to_channel(ch.id, data, "selftest.json"), "Failed to save a new entry"
        data[0]["round"] = 2
        assert await C.save_json_to_channel(ch.id, data, "selftest.json"), "Failed to overwrite"
        found, back = await C.read_latest_json_backup(ch.id, "selftest.json")
        assert found and back and back[0]["flight_code"] == code and back[0].get("round") == 2, "The read-back content does not match"
        n = 0
        async for m in ch.history(limit=50):
            if m.author == C.client.user and any(a.filename == "selftest.json" for a in m.attachments):
                n += 1
        assert n == 1, f"There are {n} JSON message(s) (should be 1)"
        return "Save → overwrite → read → no duplicates"
    await _st_step(rep, sec, "JSON save/read (on the test channel)", t_json)

    async def t_migrate():
        f2 = copy.deepcopy(flight)
        C.migrate_flight_record(f2)
        json.dumps(f2, ensure_ascii=False)
    await _st_step(rep, sec, "Flight record migration (migrate_flight_record)", t_migrate)

    async def t_load_state():
        assert C.LOAD_STATE.get("initialized"), "Startup data loading is not complete"
        bad = C.load_problems()
        assert not bad, "Items that failed to load: " + ", ".join(bad.keys())
        return f"All {len(C.LOAD_STATUS)} items are normal"
    await _st_step(rep, sec, "Production data load status", t_load_state)


    async def t_flightlog():
        fl = copy.deepcopy(flight)
        fl["selftest_log_channel_id"] = ch.id
        checks = {"fc": True, "cc": True, "gc": False}
        modal = C.FlightLogModal(fl, checks, absent_users=[])
        modal.comments._value = "selftest comment"
        fi = _StInteraction(invoker, channel=ch, guild=guild)
        await modal.on_submit(fi)
        assert fi.followup.sent, "The completion notification was not sent"
        found = None
        async for m in ch.history(limit=10):
            if m.author == C.client.user and "Flight-log" in (m.content or "") and code in (m.content or ""):
                found = m
                break
        assert found is not None, "The Flight-log message was not posted to the test channel"
        parsed = C.parse_log_message(found)
        assert parsed, "parse_log_message could not parse"
        assert parsed["flight_code"] == code, f"Flight code parse mismatch: {parsed['flight_code']}"
        assert parsed["host_id"] == invoker.id, f"Host parse mismatch: {parsed['host_id']}"
        assert invoker.id in parsed["participants"], "The test Host/Captain is not in the parsed participants"
        assert not any(f.get("flight_code") == code for f in C.FLIGHT_LOG_CACHE), "A test flight leaked into the production cache"
        return "Flight-log generation → posting → parsing all OK"
    await _st_step(rep, sec, "Flight-log (post → parse with test data)", t_flightlog)

    async def t_flightlog_view():
        v = C.FlightLogAbsentView(copy.deepcopy(flight), {"fc": True, "cc": True, "gc": True})
        await ch.send(content="selftest: FlightLogAbsentView", view=v)
        v.stop()
    await _st_step(rep, sec, "Send the Flight-log absentee-selection view", t_flightlog_view)


    C._SELFTEST_FLIGHTS[code] = flight
    try:
        async def t_archive_setup():


            txt = f"{code}_chat.txt"
            view = C._build_flight_archive_v2(flight, filename=txt)
            msg = await ch.send(view=view,
                                file=discord.File(io.BytesIO("selftest".encode()), filename=txt),
                                allowed_mentions=discord.AllowedMentions.none())
            flight["flight_archive_channel_id"] = ch.id
            flight["flight_archive_message_id"] = msg.id
        if not await _st_step(rep, sec, "Survey: send the archive (V2) message", t_archive_setup):
            return

        async def t_respondent():
            for i in range(len(C.SURVEY_QUESTIONS)):
                content, view = C._survey_render_payload(flight, SELFTEST_RESP_UID)
                item = _st_find(view, C.SurveyRatingItem, score="5" if i % 2 == 0 else "3")
                assert item is not None, f"Question {i + 1}: rating buttons were not generated"
                assert f"{i + 1}/{len(C.SURVEY_QUESTIONS)}" in content, f"Question {i + 1}: invalid progress display ({content[:40]})"
                fi = _StInteraction(_StUser(SELFTEST_RESP_UID), channel=ch, guild=guild)
                assert await item.interaction_check(fi), "The user's own button was rejected"
                await item.callback(fi)
                assert fi.response.sent and fi.response.sent[-1][0] == "edit", f"Question {i + 1}: the screen was not updated"
            ratings = flight["flight_survey_results"][str(SELFTEST_RESP_UID)]["ratings"]
            assert len(ratings) == len(C.SURVEY_QUESTIONS), f"Recorded answer count mismatch ({len(ratings)})"
            _, view = C._survey_render_payload(flight, SELFTEST_RESP_UID)
            assert _st_find(view, C.SurveyCommentItem) is not None, "The comment button does not appear after all questions are answered"
            return f"Answered {len(ratings)} question(s)"
        await _st_step(rep, sec, "Survey: response flow (regular member)", t_respondent)

        async def t_stale():
            before = dict(flight["flight_survey_results"][str(SELFTEST_RESP_UID)]["ratings"])
            fi = _StInteraction(_StUser(SELFTEST_RESP_UID), channel=ch, guild=guild)
            await C.SurveyRatingItem(code, SELFTEST_RESP_UID, "overall", "1").callback(fi)
            after = flight["flight_survey_results"][str(SELFTEST_RESP_UID)]["ratings"]
            assert before == after, "An answered question was overwritten by a stale button"
        await _st_step(rep, sec, "Survey: prevent double answers via stale buttons", t_stale)

        async def t_other_user():
            item = C.SurveyRatingItem(code, SELFTEST_RESP_UID, "overall", "5")
            fi = _StInteraction(_StUser(999999), channel=ch, guild=guild)
            assert not await item.interaction_check(fi), "Another person's button was accepted"
        await _st_step(rep, sec, "Survey: reject another person's button", t_other_user)

        async def t_comment():
            _, view = C._survey_render_payload(flight, SELFTEST_RESP_UID)
            btn = _st_find(view, C.SurveyCommentItem)
            fi = _StInteraction(_StUser(SELFTEST_RESP_UID), channel=ch, guild=guild)
            await btn.callback(fi)
            assert fi.response.sent and fi.response.sent[-1][0] == "modal", "The comment input modal does not open"
            modal = C.SurveyCommentModal(code, SELFTEST_RESP_UID)
            modal.comment._value = "selftest comment"
            fi2 = _StInteraction(_StUser(SELFTEST_RESP_UID), channel=ch, guild=guild)
            await modal.on_submit(fi2)
            res = flight["flight_survey_results"][str(SELFTEST_RESP_UID)]
            assert res.get("comment") == "selftest comment" and res.get("completed_at"), "The comment was not saved"
        await _st_step(rep, sec, "Survey: comment input", t_comment)

        async def t_host():
            hid = invoker.id
            n = len([q for q in C.SURVEY_QUESTIONS if q[0] != "host"])
            for i in range(n):
                _, view = C._survey_render_payload(flight, hid)
                item = _st_find(view, C.SurveyRatingItem, score="4")
                assert item is not None, f"Host question {i + 1}: rating buttons were not generated"
                assert item.qkey != "host", "The host is being asked a host-evaluation question"
                await item.callback(_StInteraction(_StUser(hid), channel=ch, guild=guild))
            ratings = flight["flight_survey_results"][str(hid)]["ratings"]
            assert "host" not in ratings and len(ratings) == n, f"Invalid host answers: {list(ratings)}"
        await _st_step(rep, sec, "Survey: do not show a host evaluation to the host", t_host)

        async def t_archive_update():
            ok = await C._survey_append_archive(flight)
            assert ok, f"Failed to update the archive: {C._SURVEY_ARCHIVE_LAST_ERROR or '(reason unknown)'}"
            msg = await ch.fetch_message(flight["flight_archive_message_id"])
            assert msg.edited_at is not None, "The archive was not updated by aggregation"
            assert any(a.filename.endswith("_chat.txt") for a in msg.attachments), "The chat TXT attachment was lost"
            return "Updated the archive with V2 aggregation while keeping the TXT attachment"
        await _st_step(rep, sec, "Survey: archive (V2) aggregation update", t_archive_update)

        async def t_deadline():
            flight["flight_survey_deadline"] = int(datetime.datetime.now().timestamp()) - 5
            fi = _StInteraction(_StUser(SELFTEST_RESP_UID), channel=ch, guild=guild)
            await C.SurveyRatingItem(code, SELFTEST_RESP_UID, "overall", "5").callback(fi)
            assert fi.response.sent and "closed" in str(fi.response.sent[-1][1]), "Answers are still accepted after the deadline"
            flight["flight_survey_dispatched"] = False
            await C.start_flight_survey(flight)
            assert flight.get("flight_survey_dispatched") is True, "The per-minute retry does not stop after the deadline"
        await _st_step(rep, sec, "Survey: rejection after the deadline and retry stop", t_deadline)

        async def t_dispatch():
            code2 = f"ZZSELFTEST{tag}B"
            f2 = _st_make_flight(invoker, code2)
            f2["briefing_assignments"] = {"Host": [invoker.id]}
            C._SELFTEST_FLIGHTS[code2] = f2
            try:
                await C.start_flight_survey(f2)
                assert f2.get("flight_survey_dispatched") is True, "The send is not treated as complete"
                sent, failed = f2.get("flight_survey_dm_sent_ids", []), f2.get("flight_survey_dm_failed_ids", [])
                assert invoker.id in sent or invoker.id in failed, "Neither a send nor a failure was recorded"
                if invoker.id in failed:
                    return ("WARN", "Sending failed because the runner cannot receive DMs (retry-stop on failure works correctly)")
                return "Sent a test survey DM to the runner (buttons are disabled after the check)"
            finally:
                C._SELFTEST_FLIGHTS.pop(code2, None)
        await _st_step(rep, sec, "Survey: DM sending", t_dispatch)
    finally:
        C._SELFTEST_FLIGHTS.pop(code, None)

async def _st_views_global(rep):
    sec = "Persistent views"
    async def t_ids():
        views = [C.FlightSignupView(), C.FlightChannelDeleteView(), C.ReflectionView(),
                 C.PersistentCustomerView(link_url=None, roblox_url=None),
                 C.FlightAppView(), C.FlightAppAutoCancelView(), C.EvaluationDMView()]
        ids = []
        for v in views:
            assert v.is_persistent(), f"{type(v).__name__} is not a persistent View (its buttons will die after a restart)"
            assert len(v.children) <= 25, f"{type(v).__name__} has more than 25 buttons"
            for c in v.children:
                cid = getattr(c, "custom_id", None)
                if cid:
                    assert len(cid) <= 100, f"custom_id exceeds 100 characters: {cid[:30]}"
                    ids.append(cid)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        assert not dup, "Duplicate persistent View custom_id (one of the buttons will stop working): " + ", ".join(dup)
        return f"{len(views)} views / {len(ids)} buttons with no duplicates"
    await _st_step(rep, sec, "Persistent View registrations (same as on_ready registration)", t_ids)

    async def t_dynamic():
        for cls, cid in ((C.SurveyRatingItem, "survey:r:JI54:123456789012345678:organization:3"),
                         (C.SurveyCommentItem, "survey:c:Custom (JI54):123456789012345678")):
            tmpl = getattr(cls, "__discord_ui_compiled_template__", None)
            assert tmpl is not None and tmpl.fullmatch(cid), f"custom_id template mismatch for {cls.__name__}"
        c = C.SurveyRatingItem("JI54", 1, "overall", "5")
        assert len(c.item.custom_id) <= 100
    await _st_step(rep, sec, "custom_id of survey DM buttons (DynamicItem)", t_dynamic)

    async def t_list():
        now = datetime.datetime.now().timestamp()
        active = [f for f in C.FLIGHT_LOG_CACHE if f.get("end_timestamp", 0) > now]
        C.FlightListView(active)
        return f"Generated from {len(active)} active flight(s)"
    await _st_step(rep, sec, "FlightListView (generated from the current active flights)", t_list)

_AUTO_HEAVY_TIMEOUTS = {"update": 90, "aps": 20}

_AUTO_SKIP_COMMANDS = {"test_admin", "test_evaluate", "test_progress", "selftest",
                       "create_flight", "briefing", "edit_briefing", "flight_log",
                       "restart"}

class _AutoAttachment:
    id = 0
    filename = "autotest.png"
    content_type = "image/png"
    url = proxy_url = "https://cdn.discordapp.com/attachments/0/0/autotest.png"
    description = None
    ephemeral = False
    def __init__(self):
        self._data = _st_png(16, 16)
        self.size = len(self._data)
        self.width = self.height = 16
    async def read(self, *a, **kw): return self._data
    async def save(self, *a, **kw): return len(self._data)
    async def to_file(self, **kw): return discord.File(io.BytesIO(self._data), filename=self.filename)
    def is_spoiler(self): return False

class _AutoMessage:
    id = 0
    content = ""
    async def edit(self, **kw): return self
    async def delete(self, **kw): return None

class _AutoInteraction(_StInteraction):
    def __init__(self, user, channel, guild, command):
        super().__init__(user, channel=channel, guild=guild)
        self.command = command
        self.channel_id = getattr(channel, "id", None)
        self.id = 0
        self.token = ""
        self.application_id = C.client.user.id if C.client.user else 0
        self.type = discord.InteractionType.application_command
        self.permissions = getattr(user, "guild_permissions", discord.Permissions.none())
        self.app_permissions = guild.me.guild_permissions if guild else discord.Permissions.none()
        self.created_at = datetime.datetime.now(datetime.timezone.utc)
        self.expires_at = self.created_at + datetime.timedelta(minutes=15)

    def is_expired(self):
        return False

    async def original_response(self):
        return _AutoMessage()

    async def edit_original_response(self, **kw):
        self.response._done = True
        self.response.sent.append(("edit_original", kw.get("content"), kw))
        return _AutoMessage()

    async def delete_original_response(self):
        return None

def _auto_snapshot():
    snap = {}
    for name, val in list(globals().items()):
        if not isinstance(val, (list, dict, set)):
            continue
        if name.startswith(("TEST_", "_SELFTEST", "_TEST", "_AUTO")) or not (name.isupper() or name.endswith("cache")):
            continue
        try:
            snap[name] = copy.deepcopy(val)
        except Exception:
            pass
    return snap

def _auto_restore(snap):
    g = globals()
    for name, saved in snap.items():
        cur = g.get(name)
        try:
            if isinstance(cur, list):
                cur[:] = saved
            elif isinstance(cur, (dict, set)):
                cur.clear()
                cur.update(saved)
        except Exception:
            pass

async def _auto_build_kwargs(cmd, fi, invoker, test_ch, guild):
    T = discord.AppCommandOptionType
    kwargs = {}
    for pname, p in getattr(cmd, "_params", {}).items():
        if not p.required:
            continue
        t, val = p.type, None
        if p.choices:
            val = p.choices[0].value
        elif t == T.string:
            if callable(p.autocomplete):
                try:
                    res = await p.autocomplete(fi, "")
                    val = res[0].value if res else None
                except Exception:
                    val = None
            val = val if val is not None else "TEST"
        elif t == T.integer:
            val = int(p.min_value) if p.min_value is not None else 1
        elif t == T.number:
            val = float(p.min_value) if p.min_value is not None else 1.0
        elif t == T.boolean:
            val = False
        elif t in (T.user, T.mentionable):
            val = invoker
        elif t == T.channel:
            val = test_ch
        elif t == T.role:
            val = next((r for r in guild.roles if not r.is_default()), None)
        elif t == T.attachment:
            val = _AutoAttachment()
        if val is None:
            return None
        kwargs[pname] = val
    return kwargs

async def _auto_run_commands(invoker, guild, rep):
    sec = "Auto command run"
    cmds = [c for c in _st_all_commands() if c.name not in _AUTO_SKIP_COMMANDS]
    member = guild.get_member(invoker.id) or invoker
    test_ch = None
    try:
        test_ch = await guild.create_text_channel(
            f"autotest-{datetime.datetime.now(C.JST):%m%d-%H%M%S}", overwrites=C._st_overwrites(guild, invoker),
            reason="test_admin auto check")
        C._AUTO_TEST_PAUSE = True

        prev_mentions = C.client.allowed_mentions
        C.client.allowed_mentions = discord.AllowedMentions.none()
        await asyncio.sleep(3)
        dirty_before = C.global_db_dirty
        snap = _auto_snapshot()
        try:
            for cmd in cmds:
                name = cmd.qualified_name
                fi = _AutoInteraction(member, test_ch, guild, cmd)
                tok = C._AUTO_TEST_CTX.set(True)
                try:
                    kwargs = await _auto_build_kwargs(cmd, fi, member, test_ch, guild)
                    if kwargs is None:
                        rep.add("SKIP", sec, f"/{name}", "Not executed because it has arguments that cannot be auto-generated (e.g. attachments)")
                        continue
                    await asyncio.wait_for(cmd._do_call(fi, kwargs), _AUTO_HEAVY_TIMEOUTS.get(cmd.name, 30))
                    replied = bool(fi.response.sent or fi.followup.sent)
                    rep.add("OK", sec, f"/{name}", "Completed" + ("" if replied else " (no response message)"))
                except C._AutoTestBlocked as e:
                    rep.add("OK", sec, f"/{name}", f"Ran to completion (external writes blocked: {e})")
                except asyncio.TimeoutError:
                    if cmd.name in _AUTO_HEAVY_TIMEOUTS:
                        rep.add("OK", sec, f"/{name}", f"Ran without errors for {_AUTO_HEAVY_TIMEOUTS[cmd.name]}s from start (cut short because it is a time-consuming read)")
                    else:
                        rep.add("WARN", sec, f"/{name}", "Did not complete within 30 seconds (possibly waiting for input)")
                except Exception as e:
                    orig = getattr(e, "original", e)
                    if isinstance(orig, C._AutoTestBlocked):
                        rep.add("OK", sec, f"/{name}", f"Ran to completion (external writes blocked: {orig})")
                    else:
                        rep.add("FAIL", sec, f"/{name}", f"{type(orig).__name__}: {str(orig)[:300]}")
                        traceback.print_exception(type(orig), orig, orig.__traceback__)
                finally:
                    C._AUTO_TEST_CTX.reset(tok)
        finally:
            _auto_restore(snap)
            C.global_db_dirty = dirty_before
    finally:
        C._AUTO_TEST_PAUSE = False
        try:
            C.client.allowed_mentions = prev_mentions
        except NameError:
            pass
        if test_ch is not None:
            try:
                await test_ch.delete(reason="test_admin auto check cleanup")
            except Exception:
                pass

def _st_report_text(rep, invoker, started, finished):
    lines = ["Self-Test Report",
             f"Run by: {invoker} ({invoker.id})",
             f"Start: {started:%Y-%m-%d %H:%M:%S} JST / Duration: {(finished - started).total_seconds():.1f}s",
             f"OK={rep.count('OK')} WARN={rep.count('WARN')} FAIL={rep.count('FAIL')} SKIP={rep.count('SKIP')}", ""]
    for status, sec, name, detail in rep.rows:
        lines.append(f"[{status}] {sec} / {name}" + (f"\n      {detail}" if detail else ""))
    return "\n".join(lines)

def _st_cards(rep, invoker, started, finished):
    fails = rep.count("FAIL")
    warns = rep.count("WARN")
    title = "Self-Test Result — No issues" if not fails and not warns else (
        f"Self-Test Result — {fails} issue(s)" + (f" / {warns} warning(s)" if warns else "") if fails else f"Self-Test Result — {warns} warning(s)")
    per = {}
    for status, sec, name, detail in rep.rows:
        t = per.setdefault(sec, [0, 0])
        t[1] += 1
        if status in ("OK", "WARN"):
            t[0] += 1
    summary = "\n".join(f"{sec}: {ok}/{total}" for sec, (ok, total) in per.items())
    head = [(None, f"OK {rep.count('OK')} / WARN {warns} / FAIL {fails} / SKIP {rep.count('SKIP')}\n"
                   f"Run by: {invoker.mention} / Duration {(finished - started).total_seconds():.1f}s"),
            ("By section (OK+WARN / total)", summary)]
    problems = [(f"[{s}] {sec} / {name}", (d[:700] or "(no details)")) for s, sec, name, d in rep.rows]
    problems.sort(key=lambda x: 0 if x[0].startswith("[FAIL]") else (1 if x[0].startswith("[WARN]") else 2))
    cards, cur, size = [], list(head), sum(len(h[1] or "") for h in head)
    for heading, body in problems:
        add = len(heading) + len(body)
        if cur and (size + add > 3000 or len(cur) >= 12):
            cards.append(cur)
            cur, size = [], 0
        cur.append((heading, body))
        size += add
    if cur:
        cards.append(cur)
    color = theme.SUCCESS if not fails and not warns else (theme.DANGER if fails else theme.WARNING)
    out = []
    for i, sections in enumerate(cards):
        out.append(C.build_v2_card(title if i == 0 else f"{title} (continued {i + 1})", sections,
                                 color=color, footer="Bot Self-Test"))
    return out

async def _selftest_run(invoker, events):
    started = datetime.datetime.now(C.JST)
    rep, created = _StReport(), []
    staff_state, cust_state = {}, {}
    staff_guild = C.client.get_guild(C.STAFF_GUILD_ID)
    try:
        await _st_registry(rep, invoker, staff_guild)
        await _st_guild_suite(rep, "staff", C.STAFF_GUILD_ID, SELFTEST_STAFF_CATEGORY_ID, invoker, events,
                              created, True, staff_state)
        await _st_guild_suite(rep, "customer", C.CUSTOMER_GUILD_ID, SELFTEST_CUSTOMER_CATEGORY_ID, invoker, events,
                              created, False, cust_state)
        await _st_data_suite(rep, invoker, staff_state)
        await _st_views_global(rep)
    except Exception as e:
        rep.add("FAIL", "Self-Test", "Run the self-test", f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:

        for c in reversed(created):
            try:
                await c.delete(reason="selftest cleanup")
            except discord.NotFound:
                pass
            except Exception as e:
                rep.add("WARN", "Cleanup", f"Deleting the temporary channel ({c.name})", f"Please delete it manually: {e}")
    finished = datetime.datetime.now(C.JST)


    guild = staff_guild
    cat = staff_state.get("cat")
    result_ch = None
    if guild is not None:
        try:
            result_ch = await guild.create_text_channel(
                f"SelfTestResult-{started:%m%d-%H%M%S}", category=cat,
                overwrites=C._st_overwrites(guild, invoker), reason="selftest result")
            for card in _st_cards(rep, invoker, started, finished):
                await result_ch.send(view=card)
            await result_ch.send(file=discord.File(io.BytesIO(_st_report_text(rep, invoker, started, finished).encode("utf-8")),
                                                   filename=f"selftest_{started:%Y%m%d_%H%M%S}.txt"))
        except Exception as e:
            print(f"Self-test result post error: {e}")
            traceback.print_exc()
    return result_ch, rep, started, finished

@C.client.tree.command(name="selftest", description="[Admin] Run a full self-diagnostic and output the results to the admin-only channel.", guild=C.STAFF_GUILD)
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.describe(events="Also test creating, editing and deleting Discord events (default: yes; temporarily visible to members).")
async def selftest_cmd(interaction: discord.Interaction, events: bool = True):
    global _SELFTEST_RUNNING
    perms = getattr(interaction.user, "guild_permissions", None)
    if interaction.guild_id != C.STAFF_GUILD_ID or not (perms and perms.administrator):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'No permission.')]))
    if _SELFTEST_RUNNING:
        return await interaction.response.send_message(
            ephemeral=True, view=C.build_v2_card('Notice', [(None, 'A self-test is already running.')]))
    _SELFTEST_RUNNING = True
    try:
        await interaction.response.defer(ephemeral=True, thinking=True)
        result_ch, rep, started, finished = await _selftest_run(interaction.user, events)
        fails, warns = rep.count("FAIL"), rep.count("WARN")
        text = (f"OK {rep.count('OK')} / WARN {warns} / FAIL {fails} / SKIP {rep.count('SKIP')}\n"
                + (f"Details: {result_ch.mention}" if result_ch else "Could not create the Self-Test Result channel. Please check the logs."))
        await interaction.followup.send(ephemeral=True, view=C.build_v2_card(
            "Self-Test Result — No issues" if not fails and not warns else f"Self-Test Result — {fails} issue(s) / {warns} warning(s)",
            [(None, text)], color=theme.SUCCESS if not fails and not warns else theme.DANGER))
    except Exception as e:
        traceback.print_exc()
        try:
            await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Self-Test Result', [(None, f'Error while running the self-test: {e}')]))
        except Exception:
            pass
    finally:
        _SELFTEST_RUNNING = False
