// Replaces the stock Datetime control's air-datepicker, whose drag sliders make
// picking a time fiddly.
//
// - Phones get the browser's native picker (`datetime-local`).
// - Desktop gets a popover: quick-date chips, a month calendar, and tap-to-pick
//   hour / minute columns.
//
// The desktop popover writes the user-format string into the input and fires
// "change", so the stock `parse` still does the user-format -> system-format and
// timezone conversion. Typing straight into the input keeps working the same way.
const StockDatetime = frappe.ui.form.ControlDatetime;

const MINUTE_STEP = 5;

frappe.ui.form.ControlDatetime = class EvolveDatetime extends StockDatetime {
	use_stock() {
		// list-view filters expect the stock control's behaviour
		return this.df.is_filter;
	}

	use_native() {
		return frappe.is_mobile() && !this.use_stock();
	}

	make_picker() {
		if (this.use_stock()) return super.make_picker();

		if (this.use_native()) {
			// step=60 drops the seconds spinner; minute precision is enough here
			this.$input.attr({ type: "datetime-local", step: 60 });
			return;
		}

		this.set_t_for_today();
		this.$input.on("focus click", () => evolve_picker.open(this));
		this.$input.on("keydown", (e) => {
			if (e.key === "Escape" || e.key === "Tab") evolve_picker.close();
		});
	}

	set_formatted_input(value) {
		if (this.use_stock()) return super.set_formatted_input(value);

		if (value && value.toLowerCase() === "now") value = frappe.datetime.now_datetime();
		this.$input && this.$input.val(this.format_for_input(value));
		evolve_picker.sync(this);
	}

	format_for_input(value) {
		if (!this.use_native()) return super.format_for_input(value);
		if (!value) return "";
		return frappe.datetime.convert_to_user_tz(value, false).format("YYYY-MM-DDTHH:mm");
	}

	parse(value) {
		if (!this.use_native()) return super.parse(value);
		if (!value) return "";
		const local = moment(value, "YYYY-MM-DDTHH:mm").format("YYYY-MM-DD HH:mm:ss");
		return frappe.datetime.is_system_time_zone()
			? local
			: frappe.datetime.convert_to_system_tz(local);
	}

	// The current value as a moment in the user's timezone, or null.
	get_user_moment() {
		const value = this.get_model_value() || this.value;
		if (!value) return null;
		const m = frappe.datetime.convert_to_user_tz(value, false);
		return m.isValid() ? m : null;
	}

	// Write a user-timezone moment back through the stock parse path.
	set_from_user_moment(m) {
		const date_fmt = frappe.datetime.get_user_date_fmt().toUpperCase();
		const time_fmt = frappe.datetime.get_user_time_fmt();
		this.$input.val(m.format(`${date_fmt} ${time_fmt}`)).trigger("change");
	}
};

// One popover shared by every Datetime field on the page, attached to whichever
// control opened it last.
const evolve_picker = {
	$el: null,
	control: null,
	// month being shown, and the selection being built — both user-timezone moments
	view: null,
	selected: null,

	open(control) {
		if (control.df.read_only || control.disabled) return;
		if (this.is_open_for(control)) return;
		this.ensure_dom();

		this.control = control;
		this.selected = control.get_user_moment();
		this.view = (this.selected || this.now()).clone().startOf("month");

		this.render();
		this.$el.addClass("open");
		this.position();
		this.scroll_time_into_view();
	},

	close() {
		if (!this.$el) return;
		this.$el.removeClass("open");
		this.control = null;
	},

	is_open_for(control) {
		return this.control === control && this.$el?.hasClass("open");
	},

	// Called after the control's value changes (typed, or set by a script).
	sync(control) {
		if (!this.is_open_for(control)) return;
		this.selected = control.get_user_moment();
		if (this.selected) this.view = this.selected.clone().startOf("month");
		this.render();
	},

	now() {
		// now_datetime is already in the user's timezone
		return moment(frappe.datetime.now_datetime(), "YYYY-MM-DD HH:mm:ss");
	},

	// Starting point when the field is empty: now, rounded to the minute step.
	default_moment() {
		const m = this.now().seconds(0);
		return m.minutes(Math.round(m.minutes() / MINUTE_STEP) * MINUTE_STEP);
	},

	commit(m) {
		this.selected = m.clone().seconds(0);
		this.control.set_from_user_moment(this.selected);
		this.render();
	},

	ensure_dom() {
		if (this.$el) return;

		this.$el = $(`<div class="evolve-dtp" role="dialog"></div>`).appendTo(document.body);

		// keep focus in the input so typing still works while the popover is open
		this.$el.on("mousedown", (e) => e.preventDefault());

		this.$el.on("click", "[data-action]", (e) => {
			const $target = $(e.currentTarget);
			const action = $target.attr("data-action");
			const base = this.selected || this.default_moment();

			if (action === "prev-month") {
				this.view.subtract(1, "month");
				this.render();
			} else if (action === "next-month") {
				this.view.add(1, "month");
				this.render();
			} else if (action === "day") {
				const day = moment($target.attr("data-date"), "YYYY-MM-DD");
				this.commit(base.clone().year(day.year()).month(day.month()).date(day.date()));
			} else if (action === "shift-day") {
				const day = this.now().add(cint($target.attr("data-offset")), "days");
				this.view = day.clone().startOf("month");
				this.commit(base.clone().year(day.year()).month(day.month()).date(day.date()));
			} else if (action === "hour") {
				this.commit(base.clone().hours(cint($target.attr("data-value"))));
			} else if (action === "minute") {
				this.commit(base.clone().minutes(cint($target.attr("data-value"))));
			} else if (action === "now") {
				this.view = this.now().startOf("month");
				this.commit(this.now());
			} else if (action === "clear") {
				this.selected = null;
				this.control.$input.val("").trigger("change");
				this.close();
			} else if (action === "done") {
				this.close();
			}
		});

		$(document).on("mousedown.evolve_dtp", (e) => {
			if (!this.control) return;
			if (this.$el[0].contains(e.target) || this.control.$input[0] === e.target) return;
			this.close();
		});
		$(window).on("resize.evolve_dtp", () => this.close());
		// capture phase, so scrolling inside a modal or the page both reposition
		window.addEventListener("scroll", () => this.control && this.position(), true);
		frappe.router?.on("change", () => this.close());
	},

	position() {
		const rect = this.control.$input[0].getBoundingClientRect();
		const width = this.$el.outerWidth();
		const height = this.$el.outerHeight();
		const gap = 6;

		let top = rect.bottom + gap;
		if (top + height > window.innerHeight && rect.top - gap - height > 0) {
			top = rect.top - gap - height;
		}
		const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));

		this.$el.css({ top, left });
	},

	scroll_time_into_view() {
		this.$el.find(".evolve-dtp-col").each((_, col) => {
			const active = col.querySelector(".active");
			if (active) {
				col.scrollTop = active.offsetTop - col.clientHeight / 2 + active.clientHeight / 2;
			}
		});
	},

	render() {
		// re-rendering on every click would otherwise jump the time columns to the top
		const scroll = this.$el
			.find(".evolve-dtp-col")
			.map((_, col) => col.scrollTop)
			.get();

		this.$el.html(`
			<div class="evolve-dtp-chips">
				${this.chip(-1, __("Yesterday"))}
				${this.chip(0, __("Today"))}
				${this.chip(1, __("Tomorrow"))}
			</div>
			<div class="evolve-dtp-body">
				<div class="evolve-dtp-calendar">${this.calendar_html()}</div>
				<div class="evolve-dtp-time">${this.time_html()}</div>
			</div>
			<div class="evolve-dtp-footer">
				<div class="evolve-dtp-summary">${this.summary()}</div>
				<div class="evolve-dtp-actions">
					<button class="btn btn-xs btn-default" data-action="now">${__("Now")}</button>
					<button class="btn btn-xs btn-default" data-action="clear">${__("Clear")}</button>
					<button class="btn btn-xs btn-primary" data-action="done">${__("Done")}</button>
				</div>
			</div>
		`);

		this.$el.find(".evolve-dtp-col").each((i, col) => {
			if (scroll[i] != null) col.scrollTop = scroll[i];
		});
	},

	chip(offset, label) {
		const day = this.now().add(offset, "days");
		const active = this.selected?.isSame(day, "day") ? "active" : "";
		return `<button class="evolve-dtp-chip ${active}" data-action="shift-day" data-offset="${offset}">${label}</button>`;
	},

	calendar_html() {
		const first_dow = frappe.datetime.get_first_day_of_the_week_index();
		const today = this.now();
		const lead = (this.view.day() - first_dow + 7) % 7;
		const cursor = this.view.clone().subtract(lead, "days");

		const weekdays = [];
		for (let i = 0; i < 7; i++) {
			weekdays.push(
				`<div class="evolve-dtp-dow">${moment.weekdaysMin((first_dow + i) % 7)}</div>`
			);
		}

		// always six rows, so the popover keeps its height between months
		const days = [];
		for (let i = 0; i < 42; i++) {
			const classes = ["evolve-dtp-day"];
			if (cursor.month() !== this.view.month()) classes.push("other-month");
			if (cursor.isSame(today, "day")) classes.push("today");
			if (this.selected?.isSame(cursor, "day")) classes.push("active");

			days.push(
				`<button class="${classes.join(" ")}" data-action="day" data-date="${cursor.format(
					"YYYY-MM-DD"
				)}">${cursor.date()}</button>`
			);
			cursor.add(1, "day");
		}

		return `
			<div class="evolve-dtp-month">
				<button class="evolve-dtp-nav" data-action="prev-month" aria-label="${__(
					"Previous month"
				)}">‹</button>
				<span>${this.view.format("MMMM YYYY")}</span>
				<button class="evolve-dtp-nav" data-action="next-month" aria-label="${__(
					"Next month"
				)}">›</button>
			</div>
			<div class="evolve-dtp-grid">${weekdays.join("")}${days.join("")}</div>
		`;
	},

	time_html() {
		const hour = this.selected?.hours();
		const minute = this.selected?.minutes();

		const hours = [];
		for (let h = 0; h < 24; h++) hours.push(h);

		const minutes = [];
		for (let m = 0; m < 60; m += MINUTE_STEP) minutes.push(m);
		// a stored value off the step (e.g. 06:47) still shows as selected
		if (minute != null && !minutes.includes(minute)) {
			minutes.push(minute);
			minutes.sort((a, b) => a - b);
		}

		const cells = (values, current, action) =>
			values
				.map(
					(v) =>
						`<button class="evolve-dtp-cell ${
							v === current ? "active" : ""
						}" data-action="${action}" data-value="${v}">${String(v).padStart(
							2,
							"0"
						)}</button>`
				)
				.join("");

		return `
			<div class="evolve-dtp-time-head"><span>${__("Hour")}</span><span>${__("Min")}</span></div>
			<div class="evolve-dtp-time-cols">
				<div class="evolve-dtp-col">${cells(hours, hour, "hour")}</div>
				<div class="evolve-dtp-col">${cells(minutes, minute, "minute")}</div>
			</div>
		`;
	},

	summary() {
		if (!this.selected) {
			return `<span class="text-muted">${__("Pick a day and time")}</span>`;
		}
		return `${this.selected.format("ddd, D MMM YYYY")} · <b>${this.selected.format("HH:mm")}</b>`;
	},
};
