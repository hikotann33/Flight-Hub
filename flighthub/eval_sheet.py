import discord
import datetime
import asyncio
import uuid

from . import core as C

def eval_blocked_message():
    if C.EVAL_TRACK_CHANNEL_ID in C.LOAD_UNSAFE_CHANNELS:
        return ("Evaluation data is not loaded yet, so this action is temporarily unavailable to protect saved data. Retrying automatically. Please try again in about a minute.\n"
                "Evaluation data could not be loaded yet. Please try again in a minute.")
    return None

def eval_month_send_dt(month: int, now=None) -> datetime.datetime:
    now = now or datetime.datetime.now(C.JST)
    dt = None
    for year in range(now.year, now.year + 3):
        ny, nm = (year, month + 1) if month < 12 else (year + 1, 1)
        dt = datetime.datetime(ny, nm, 1, 0, 0, tzinfo=C.JST)
        if dt > now + datetime.timedelta(minutes=1):
            return dt
    return dt

class EvalInputModal(discord.ui.Modal):
    def __init__(self, target_member: discord.Member, parent_view):
        title_name = target_member.display_name[:20]
        super().__init__(title=f"{title_name}  - Evaluation Input")
        self.target_member = target_member
        self.parent_view = parent_view

        self.grade = discord.ui.TextInput(label="Grade (e.g. A, Pass)", max_length=50, required=True)
        self.comments = discord.ui.TextInput(label="Comments", style=discord.TextStyle.paragraph, max_length=1500, required=True)
        self.doc_link = discord.ui.TextInput(label="Document Link", style=discord.TextStyle.short, required=True)
        
        self.add_item(self.grade)
        self.add_item(self.comments)
        self.add_item(self.doc_link)

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.queued_evals.append({
            "target_member": self.target_member,
            "grade": self.grade.value,
            "comments": self.comments.value,
            "doc_link": self.doc_link.value
        })
        await self.parent_view.update_ui(interaction)

def _eval_user_name(guild, uid) -> str:
    try:
        uid = int(uid)
    except Exception:
        return str(uid)
    m = guild.get_member(uid) if guild else None
    if m:
        return m.display_name
    u = C.client.get_user(uid)
    return getattr(u, "display_name", None) or str(uid)

def _eval_by_id(eid):
    return next((e for e in C.EVALUATION_CACHE if isinstance(e, dict) and e.get("id") == eid), None)

def _eval_month_text(ev) -> str:
    m = ev.get("eval_month")
    return f"Month {m}" if m else "Specified time"

class EvalMonthSelect(discord.ui.Select):
    def __init__(self, on_pick, row=2, placeholder="Select evaluation month (auto-send at 0:00 on the 1st of next month)"):
        options = []
        for m in range(1, 13):
            dt = eval_month_send_dt(m)
            options.append(discord.SelectOption(
                label=f"Evaluation sheet for month {m}",
                description=f"{dt.year}-{dt.month:02d}-{dt.day:02d} 00:00 (JST) auto-send",
                value=str(m)))
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1, row=row)
        self._on_pick = on_pick

    async def callback(self, interaction: discord.Interaction):
        await self._on_pick(interaction, int(self.values[0]))

class EvalEditModal(discord.ui.Modal):
    def __init__(self, entry: dict, manager):
        super().__init__(title="Edit Scheduled Evaluation")
        self.entry_id = entry["id"]
        self.manager = manager
        self.grade = discord.ui.TextInput(label="Grade", default=str(entry.get("grade", ""))[:50], max_length=50, required=True)
        self.comments = discord.ui.TextInput(label="Comments", style=discord.TextStyle.paragraph,
                                             default=str(entry.get("comments", ""))[:1500], max_length=1500, required=True)
        self.doc_link = discord.ui.TextInput(label="Document Link", default=str(entry.get("doc_link", ""))[:1000],
                                             max_length=1000, required=True)
        self.add_item(self.grade)
        self.add_item(self.comments)
        self.add_item(self.doc_link)

    async def on_submit(self, interaction: discord.Interaction):
        ev = _eval_by_id(self.entry_id)
        if not ev:
            return await self.manager.refresh(interaction, "This reservation has already been sent or cancelled.", to_list=True)
        ev["grade"] = self.grade.value
        ev["comments"] = self.comments.value
        ev["doc_link"] = self.doc_link.value
        ok = await C.save_eval_tracking()
        await C.log_audit(actor=interaction.user, action="Evaluation Schedule Edited",
                        detail=f"Target: {_eval_user_name(interaction.guild, ev.get('target_id'))}")
        await self.manager.refresh(interaction, "Reservation updated." if ok else "Updated on screen, but saving failed. Please try again.")

class EvalRescheduleModal(discord.ui.Modal):
    def __init__(self, manager, current_ts: int):
        super().__init__(title="Change Send Time")
        self.manager = manager
        default = datetime.datetime.fromtimestamp(current_ts, C.JST).strftime("%Y-%m-%d %H:%M") if current_ts else ""
        self.new_time = discord.ui.TextInput(label="New send time (YYYY-MM-DD HH:MM / JST)", default=default,
                                             placeholder="e.g. 2026-10-01 00:00", required=True, max_length=20)
        self.add_item(self.new_time)

    async def on_submit(self, interaction: discord.Interaction):
        dt = C.parse_loa_datetime(self.new_time.value)
        if not dt:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Invalid date format. (e.g. 2026-10-01 00:00)')]))
        if dt <= datetime.datetime.now(C.JST):
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Please specify a time in the future.')]))
        await self.manager.apply_new_time(interaction, dt, None)

class EvalScheduleManagerView(discord.ui.View):
    PAGE = 25

    def __init__(self, guild, parent=None):
        super().__init__(timeout=900)
        self.guild = guild
        self.parent = parent
        self.page = 0
        self.selected_id = None
        self.scope = "one"
        self.confirm_cancel = False
        self.note = ""
        self.rebuild()


    def entries(self):
        C._ensure_eval_ids()
        valid = [e for e in C.EVALUATION_CACHE if isinstance(e, dict) and e.get("send_timestamp") and e.get("id")]
        return sorted(valid, key=lambda e: (e["send_timestamp"], str(e.get("batch_id")), str(e.get("id"))))

    def selected(self):
        return _eval_by_id(self.selected_id) if self.selected_id else None

    def scope_entries(self):
        ev = self.selected()
        if not ev:
            return []
        if self.scope == "batch":
            return [e for e in C.EVALUATION_CACHE if isinstance(e, dict) and e.get("batch_id") == ev.get("batch_id")]
        return [ev]


    def _btn(self, label, style, cb, row=0, disabled=False):
        b = discord.ui.Button(label=label, style=style, row=row, disabled=disabled)
        b.callback = cb
        self.add_item(b)
        return b

    def rebuild(self):
        self.clear_items()
        ev = self.selected()
        if self.selected_id and not ev:
            self.selected_id, self.scope, self.confirm_cancel = None, "one", False
            ev = None

        if ev and self.confirm_cancel:
            self._btn("Yes, cancel it", discord.ButtonStyle.danger, self.on_cancel_yes, row=0)
            self._btn("No", discord.ButtonStyle.secondary, self.on_cancel_no, row=0)
            return

        if ev:
            n = len(self.scope_entries())
            self._btn("Edit details (this person)", discord.ButtonStyle.primary, self.on_edit, row=0)
            self._btn("Enter date/time to change", discord.ButtonStyle.primary, self.on_time, row=0)
            self._btn("Cancel reservation", discord.ButtonStyle.danger, self.on_cancel, row=0)
            batch_n = len([e for e in C.EVALUATION_CACHE if isinstance(e, dict) and e.get("batch_id") == ev.get("batch_id")])
            scope_label = "Target: this person only" if self.scope == "one" else f"Target: everyone in the same reservation ({n})"
            self._btn(scope_label + " ⇄", discord.ButtonStyle.secondary, self.on_scope, row=1, disabled=(batch_n <= 1))
            self._btn("Back to list", discord.ButtonStyle.secondary, self.on_back_list, row=1)
            self.add_item(EvalMonthSelect(self.on_month, row=2, placeholder="Change time by evaluation month (1st of next month 0:00)"))
            return


        items = self.entries()
        pages = max(1, (len(items) + self.PAGE - 1) // self.PAGE)
        self.page = min(self.page, pages - 1)
        chunk = items[self.page * self.PAGE:(self.page + 1) * self.PAGE]
        if chunk:
            options = []
            for e in chunk:
                dt = datetime.datetime.fromtimestamp(e["send_timestamp"], C.JST)
                name = _eval_user_name(self.guild, e.get("target_id"))
                options.append(discord.SelectOption(
                    label=f"{name} | {e.get('grade', '-')}"[:100],
                    description=f"{dt:%Y-%m-%d %H:%M} scheduled ({_eval_month_text(e)})"[:100],
                    value=str(e["id"])))
            sel = discord.ui.Select(placeholder="Select a reservation to edit or cancel", options=options, row=0)
            sel.callback = self.on_pick
            self.add_item(sel)
        if pages > 1:
            self._btn("◀ Prev", discord.ButtonStyle.secondary, self.on_prev, row=1, disabled=(self.page == 0))
            self._btn(f"{self.page + 1}/{pages}", discord.ButtonStyle.secondary, self.on_noop, row=1, disabled=True)
            self._btn("Next ▶", discord.ButtonStyle.secondary, self.on_next, row=1, disabled=(self.page >= pages - 1))
        if self.parent is not None:
            self._btn("Back to evaluation creation", discord.ButtonStyle.secondary, self.on_back_parent, row=3)

    def build_embed(self) -> discord.Embed:
        ev = self.selected()
        embed = discord.Embed(title="Evaluation Schedule Management", color=0x1B3444)
        if self.note:
            embed.description = self.note + "\n\n"
        else:
            embed.description = ""

        if ev:
            targets = self.scope_entries()
            embed.description += "Details of the selected reservation. Use the buttons below to edit, change the time, or cancel."
            embed.add_field(name="Recipient", value=f"<@{ev.get('target_id')}> ({_eval_user_name(self.guild, ev.get('target_id'))})", inline=False)
            embed.add_field(name="Grade", value=f"**{ev.get('grade', '-')}**", inline=True)
            embed.add_field(name="Scheduled send", value=f"<t:{int(ev['send_timestamp'])}:F>\n(<t:{int(ev['send_timestamp'])}:R>) / {_eval_month_text(ev)}", inline=True)
            embed.add_field(name="Feedback", value=str(ev.get("comments", "-"))[:900] or "-", inline=False)
            embed.add_field(name="Document", value=str(ev.get("doc_link", "-"))[:500] or "-", inline=False)
            if self.scope == "batch" or len(targets) > 1:
                names = ", ".join(_eval_user_name(self.guild, e.get("target_id")) for e in targets)
                embed.add_field(name=f"Affected scope ({len(targets)})", value=names[:1000], inline=False)
            if self.confirm_cancel:
                names = ", ".join(_eval_user_name(self.guild, e.get("target_id")) for e in targets)
                embed.add_field(name="Are you sure you want to cancel?",
                                value=f"This will cancel the scheduled send for **{len(targets)}** recipient(s) (cannot be undone):\n{names[:900]}", inline=False)
            return embed

        items = self.entries()
        if not items:
            embed.description += "There are currently no scheduled sends."
            return embed
        embed.description += f"There are **{len(items)}** scheduled send(s). Select one from the menu below to edit, change the time, or cancel."
        groups = {}
        for e in items:
            groups.setdefault(e.get("batch_id"), []).append(e)
        for i, (_, grp) in enumerate(sorted(groups.items(), key=lambda kv: kv[1][0]["send_timestamp"])[:8], 1):
            ts = int(grp[0]["send_timestamp"])
            names = ", ".join(_eval_user_name(self.guild, e.get("target_id")) for e in grp)
            if len(names) > 300:
                names = names[:300] + "..."
            embed.add_field(name=f"Reservation {i} ({len(grp)} recipients / {_eval_month_text(grp[0])})",
                            value=f"Send: <t:{ts}:F> (<t:{ts}:R>)\nTarget: {names}", inline=False)
        if len(groups) > 8:
            embed.set_footer(text=f"{len(groups) - 8} more group(s) (selectable from the menu)")
        return embed

    async def refresh(self, interaction: discord.Interaction, note: str = "", to_list: bool = False):
        self.note = note
        if to_list:
            self.selected_id, self.scope, self.confirm_cancel = None, "one", False
        self.rebuild()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)


    async def on_noop(self, interaction):
        await interaction.response.defer()

    async def on_pick(self, interaction: discord.Interaction):
        self.selected_id = interaction.data["values"][0]
        self.scope, self.confirm_cancel = "one", False
        await self.refresh(interaction)

    async def on_prev(self, interaction):
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    async def on_next(self, interaction):
        self.page += 1
        await self.refresh(interaction)

    async def on_back_list(self, interaction):
        await self.refresh(interaction, to_list=True)

    async def on_back_parent(self, interaction: discord.Interaction):
        if self.parent is not None:
            await interaction.response.edit_message(embed=self.parent.generate_embed(), view=self.parent)

    async def on_scope(self, interaction):
        self.scope = "batch" if self.scope == "one" else "one"
        await self.refresh(interaction)

    async def on_edit(self, interaction: discord.Interaction):
        ev = self.selected()
        if not ev:
            return await self.refresh(interaction, "This reservation has already been sent or cancelled.", to_list=True)
        await interaction.response.send_modal(EvalEditModal(ev, self))

    async def on_time(self, interaction: discord.Interaction):
        ev = self.selected()
        if not ev:
            return await self.refresh(interaction, "This reservation has already been sent or cancelled.", to_list=True)
        await interaction.response.send_modal(EvalRescheduleModal(self, int(ev["send_timestamp"])))

    async def on_month(self, interaction: discord.Interaction, month: int):
        await self.apply_new_time(interaction, eval_month_send_dt(month), month)

    async def apply_new_time(self, interaction: discord.Interaction, dt: datetime.datetime, month):
        blocked = eval_blocked_message()
        if blocked:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, blocked)]))
        targets = self.scope_entries()
        if not targets:
            return await self.refresh(interaction, "This reservation has already been sent or cancelled.", to_list=True)
        ts = int(dt.timestamp())
        for e in targets:
            e["send_timestamp"] = ts
            e["eval_month"] = month
            e["attempts"] = 0
        ok = await C.save_eval_tracking()
        names = ", ".join(_eval_user_name(self.guild, e.get("target_id")) for e in targets)
        await C.log_audit(actor=interaction.user, action="Evaluation Schedule Rescheduled", detail=f"{names} → {dt:%Y-%m-%d %H:%M}")
        label = f"(month {month}, 1st of next month 0:00)" if month else ""
        await self.refresh(interaction, (f"Changed the send time for **{len(targets)}** recipient(s) to <t:{ts}:F>. {label}" if ok
                                         else "Changed, but saving failed. Please try again."))

    async def on_cancel(self, interaction):
        self.confirm_cancel = True
        await self.refresh(interaction)

    async def on_cancel_no(self, interaction):
        self.confirm_cancel = False
        await self.refresh(interaction)

    async def on_cancel_yes(self, interaction: discord.Interaction):
        blocked = eval_blocked_message()
        if blocked:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, blocked)]))
        targets = self.scope_entries()
        names = ", ".join(_eval_user_name(self.guild, e.get("target_id")) for e in targets)
        for e in targets:
            if e in C.EVALUATION_CACHE:
                C.EVALUATION_CACHE.remove(e)
        ok = await C.save_eval_tracking()
        await C.log_audit(actor=interaction.user, action="Evaluation Schedule Cancelled", detail=f"{len(targets)} recipients: {names}")
        self.selected_id, self.scope, self.confirm_cancel = None, "one", False
        await self.refresh(interaction, (f"Cancelled the schedule for **{len(targets)}** recipient(s)." if ok
                                         else "Cancelled, but saving failed. Please check again."))

class EvalBuilderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)
        self.queued_evals = []

        self.user_select = discord.ui.UserSelect(placeholder="1. Select a user to enter an individual evaluation", min_values=1, max_values=1, custom_id="eval_user_builder")
        self.user_select.callback = self.select_callback
        self.add_item(self.user_select)

        self.confirm_btn = discord.ui.Button(label="2. Proceed to review & send", style=discord.ButtonStyle.primary, custom_id="eval_confirm_btn", row=1, disabled=True)
        self.confirm_btn.callback = self.confirm_callback
        self.add_item(self.confirm_btn)

        self.manage_btn = discord.ui.Button(label="Manage scheduled sends (edit/cancel)", style=discord.ButtonStyle.secondary, custom_id="eval_manage_btn", row=1)
        self.manage_btn.callback = self.manage_callback
        self.add_item(self.manage_btn)

        self.cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="eval_cancel_btn", row=1)
        self.cancel_btn.callback = self.cancel_callback
        self.add_item(self.cancel_btn)

    async def select_callback(self, interaction: discord.Interaction):
        target_member = self.user_select.values[0]
        await interaction.response.send_modal(EvalInputModal(target_member, self))

    async def update_ui(self, interaction: discord.Interaction):
        self.confirm_btn.disabled = len(self.queued_evals) == 0
        self.user_select.placeholder = f"{len(self.queued_evals)} added so far (add more)"
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    def generate_embed(self):
        embed = discord.Embed(
            title="Evaluation Send Builder",
            description="Select a user from the menu to open the input form.\nYou can set different evaluations for each person and then schedule or send them all at once.\nTo edit or cancel scheduled sends, press the Manage scheduled sends button.",
            color=0x1B3444
        )
        
        queue_str = ""
        for idx, ev in enumerate(self.queued_evals):
            queue_str += f"{idx+1}. {ev['target_member'].mention} (Grade: **{ev['grade']}**)\n"
            
        if not queue_str:
            queue_str = "No one has been added yet."
        elif len(queue_str) > 1000:
            queue_str = queue_str[:1000] + "\n...(and more)"
            
        embed.add_field(name=f"Added list ({len(self.queued_evals)})", value=queue_str, inline=False)
        return embed

    async def confirm_callback(self, interaction: discord.Interaction):
        confirm_view = EvalConfirmView(self.queued_evals)
        await interaction.response.edit_message(embed=confirm_view.generate_embed(), view=confirm_view)

    async def manage_callback(self, interaction: discord.Interaction):
        blocked = eval_blocked_message()
        if blocked:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, blocked)]))
        mv = EvalScheduleManagerView(interaction.guild, parent=self)
        await interaction.response.edit_message(embed=mv.build_embed(), view=mv)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.clear_items()
        await interaction.response.edit_message(content="Operation cancelled.", embed=None, view=self)

class EvalScheduleModal(discord.ui.Modal, title="Schedule Send Time"):
    publish_time = discord.ui.TextInput(
        label="Scheduled date/time (YYYY-MM-DD HH:MM)",
        placeholder="e.g. 2026-08-05 18:00",
        required=True
    )

    def __init__(self, queued_evals, parent_view):
        super().__init__()
        self.queued_evals = queued_evals
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        time_str = self.publish_time.value
        publish_time_dt = C.parse_loa_datetime(time_str)
        
        if not publish_time_dt:
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Invalid date format.')]))
        
        if publish_time_dt < datetime.datetime.now(C.JST):
            return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Please specify a time in the future.')]))

        await self.parent_view.process_send(interaction, publish_time_dt)

@C.client.tree.command(name="send_evaluation", description="[Manager] Send/schedule evaluation sheets via DM, and edit or cancel scheduled sends.")
async def send_evaluation_cmd(interaction: discord.Interaction):
    if C.LOG_MANAGER_ROLE_ID not in [r.id for r in interaction.user.roles] and not C.is_chief(interaction.user):
        return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'You do not have permission to run this command.')]))

    view = EvalBuilderView()
    await interaction.response.send_message(embed=view.generate_embed(), view=view, ephemeral=True)

class EvalConfirmView(discord.ui.View):
    def __init__(self, queued_evals):
        super().__init__(timeout=600)
        self.queued_evals = queued_evals
        self.children[0].label = f"Send to {len(queued_evals)} now"
        self.children[1].label = f"Schedule send to {len(queued_evals)}"

        self.add_item(EvalMonthSelect(self.pick_month, row=2))

    async def pick_month(self, interaction: discord.Interaction, month: int):
        await self.process_send(interaction, eval_month_send_dt(month), month)
        
    def generate_embed(self):
        embed = discord.Embed(
            title="Evaluation Send Confirmation",
            description=f"Send an individual evaluation sheet to each of the **{len(self.queued_evals)}** people in the list.\nChoose the send method (immediate or scheduled) from the buttons below.",
            color=0x1B3444
        )
        member_list_str = " ".join([ev['target_member'].mention for ev in self.queued_evals])
        if len(member_list_str) > 1024:
            member_list_str = member_list_str[:1000] + "... (and more)"
        
        embed.add_field(name="Recipients", value=member_list_str, inline=False)
        embed.add_field(name="Evaluation month mode",
                        value="Selecting an evaluation month (e.g. September) from the menu below schedules an automatic send at **0:00 (JST) on the 1st of the next month** (e.g. Oct 1 0:00 for September).",
                        inline=False)
        return embed

    @discord.ui.button(label="Send now", style=discord.ButtonStyle.primary, row=0)
    async def send_now_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_send(interaction, None)

    @discord.ui.button(label="Schedule send", style=discord.ButtonStyle.success, row=0)
    async def schedule_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EvalScheduleModal(self.queued_evals, self))

    @discord.ui.button(label="Send everyone's preview to me", style=discord.ButtonStyle.secondary, row=1)
    async def preview_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.queued_evals: return
        await interaction.response.defer(ephemeral=True)
        try:
            for ev in self.queued_evals:
                eval_data_for_view = {
                    "target_id": ev["target_member"].id,
                    "reviewer_name": interaction.user.display_name,
                    "grade": ev["grade"],
                    "comments": ev["comments"],
                    "doc_link": ev["doc_link"]
                }
                view = C.EvaluationDMView() 
                await interaction.user.send(
                    content=f"**Test Preview** {ev['target_member'].display_name} - individual content:", 
                    embed=view.generate_embed(eval_data_for_view, "en"), 
                    view=view
                )
                await asyncio.sleep(0.5) 
            await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Sent {len(self.queued_evals)} preview(s) to your DMs.')]))
        except Exception as e:
            await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, f'Could not send DM. ({e})')]))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.clear_items()
        await interaction.response.edit_message(content="Sending cancelled.", embed=None, view=self)

    async def process_send(self, interaction: discord.Interaction, publish_time_dt: datetime.datetime = None, eval_month: int = None):


        if getattr(self, "_sending", False):
            try:
                if not interaction.response.is_done():
                    return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Sending in progress. Please wait a moment.')]))
                return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, 'Sending in progress. Please wait a moment.')]))
            except Exception:
                return
        self._sending = True
        if publish_time_dt:
            blocked = eval_blocked_message()
            if blocked:
                if not interaction.response.is_done():
                    return await interaction.response.send_message(ephemeral=True, view=C.build_v2_card('Notice', [(None, blocked)]))
                return await interaction.followup.send(ephemeral=True, view=C.build_v2_card('Notice', [(None, blocked)]))
        if not interaction.response.is_done():
            await interaction.response.defer()
            

        if publish_time_dt:

            send_ts = int(publish_time_dt.timestamp())
            batch_id = uuid.uuid4().hex[:8]
            for ev in self.queued_evals:
                C.EVALUATION_CACHE.append({
                    "id": uuid.uuid4().hex[:8],
                    "batch_id": batch_id,
                    "creator_id": interaction.user.id,
                    "target_id": ev["target_member"].id,
                    "reviewer_name": interaction.user.display_name,
                    "grade": ev["grade"],
                    "comments": ev["comments"],
                    "doc_link": ev["doc_link"],
                    "send_timestamp": send_ts,
                    "eval_month": eval_month,
                    "attempts": 0
                })
            saved_ok = await C.save_eval_tracking()
            month_txt = f"(month {eval_month}, auto-send at 0:00 on the 1st of next month)" if eval_month else ""
            msg = f"Scheduled evaluation sheets for **{len(self.queued_evals)}** people at <t:{send_ts}:F>. {month_txt}\nYou can edit or cancel from the Manage scheduled sends button in /send_evaluation."
            if not saved_ok:
                msg += "\nSaving the reservation failed. It may disappear after a restart, so please check it in the reservation management of `/send_evaluation`."
        else:

            sent_count = 0
            failed_members = []
            for ev in self.queued_evals:
                eval_data_for_view = {
                    "target_id": ev["target_member"].id,
                    "reviewer_name": interaction.user.display_name,
                    "grade": ev["grade"],
                    "comments": ev["comments"],
                    "doc_link": ev["doc_link"],
                }
                try:
                    view = C.EvaluationDMView()
                    await ev["target_member"].send(embed=view.generate_embed(eval_data_for_view, "en"), view=view)
                    sent_count += 1
                except Exception as e:
                    print(f"Eval Immediate Send Error for {ev['target_member'].id}: {e}")
                    failed_members.append(ev["target_member"].mention)
                await asyncio.sleep(0.5)

            msg = f"Sent evaluation sheets to **{sent_count} / {len(self.queued_evals)}** people immediately."
            if failed_members:
                msg += f"\nFailed to send (DMs may be closed): {', '.join(failed_members)}"

        self.clear_items()
        await interaction.edit_original_response(content=msg, embed=None, view=self)

        target_names = ", ".join(ev["target_member"].display_name for ev in self.queued_evals)
        await C.log_audit(
            actor=interaction.user,
            action="Evaluation Sheets Sent" if not publish_time_dt else "Evaluation Sheets Scheduled",
            detail=f"{len(self.queued_evals)} recipients: {target_names}"
        )
