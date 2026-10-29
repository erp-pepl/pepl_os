// C3a-B1 - Shift-entry kiosk. Plain JavaScript: the page must work on a basic tablet browser.
(function () {
	const root = document.getElementById("pepl-kiosk");
	if (!root || !root.dataset.machine) return;
	const machine = root.dataset.machine;
	const M = "pepl_os.pepl_production.kiosk.";
	const t = (s, args) => (window.__ ? window.__(s, args) : s.replace(/\{(\d)\}/g, (m, i) => (args || [])[i]));
	const $ = (id) => document.getElementById(id);
	const state = { token: null, data: null, rows: { production: [], downtime: [], tool_changes: [] }, dirty: false, ctx: null };

	function text(html) {
		const d = document.createElement("div");
		d.innerHTML = html || "";
		return d.textContent || "";
	}

	async function call(method, args) {
		const body = new URLSearchParams();
		Object.entries(args || {}).forEach(([k, v]) => body.append(k, typeof v === "object" && v !== null ? JSON.stringify(v) : v == null ? "" : v));
		const res = await fetch("/api/method/" + M + method, {
			method: "POST",
			headers: { "X-Frappe-CSRF-Token": window.frappe && frappe.csrf_token, Accept: "application/json" },
			body,
			credentials: "same-origin",
		});
		const out = await res.json().catch(() => ({}));
		if (!res.ok || out.exc_type || out.exception) {
			let msg = "";
			try {
				msg = JSON.parse(out._server_messages || "[]").map((m) => text(JSON.parse(m).message)).join(" ");
			} catch (e) {
				msg = "";
			}
			if (out.exc_type === "AuthenticationError" && state.token) signOutLocal();
			throw new Error(msg || text(out.exception) || t("Something went wrong. Try again."));
		}
		return out.message;
	}

	function say(message, colour) {
		$("k-message").innerHTML = message ? `<div class="kiosk-card kiosk-${colour || "red"}"></div>` : "";
		if (message) $("k-message").firstChild.textContent = message;
	}

	function panel(el, rows) {
		el.innerHTML = "";
		(rows || []).forEach((r) => {
			const div = document.createElement("div");
			div.className = "kiosk-row " + (r.colour || "gray");
			div.textContent = r.text;
			el.appendChild(div);
		});
	}

	function option(select, value, label, selected) {
		const o = document.createElement("option");
		o.value = value;
		o.textContent = label;
		if (selected) o.selected = true;
		select.appendChild(o);
	}

	// ---- before sign-in ----
	async function load() {
		try {
			const ctx = await call("kiosk_context", { machine });
			state.ctx = ctx;
			ctx.dates.forEach((d, i) => option($("k-date"), d, i === 0 ? t("Today") + " " + d : t("Yesterday") + " " + d, d === ctx.date));
			ctx.shifts.forEach((s) => option($("k-shift"), s.name, `${s.name} (${s.start}-${s.end})`, s.name === ctx.shift));
		} catch (e) {
			say(e.message);
		}
	}

	async function signIn() {
		say("");
		const btn = $("k-signin-btn");
		btn.disabled = true;
		try {
			const out = await call("sign_in", {
				machine,
				shift: $("k-shift").value,
				posting_date: $("k-date").value,
				employee_code: $("k-code").value,
				pin: $("k-pin").value,
			});
			state.token = out.token;
			$("k-pin").value = "";
			show(out);
		} catch (e) {
			say(e.message);
			$("k-pin").value = "";
		} finally {
			btn.disabled = false;
		}
	}

	function signOutLocal() {
		state.token = null;
		state.data = null;
		$("k-entry").style.display = "none";
		$("k-signin").style.display = "";
		$("k-who").textContent = "";
		$("k-date").disabled = $("k-shift").disabled = false;
		$("k-code").value = "";
	}

	async function signOut() {
		if (state.dirty && !confirmLeave()) return;
		try {
			if (state.token) await call("sign_out", { token: state.token });
		} catch (e) {
			/* ended already */
		}
		signOutLocal();
		say(t("Signed out."), "green");
	}

	function confirmLeave() {
		return window.confirm(t("Changes are not saved. Leave anyway?"));
	}

	// ---- the entry ----
	function show(data) {
		state.data = data;
		state.rows.production = (data.production || []).map((r) => Object.assign({}, r));
		state.rows.downtime = (data.downtime || []).map((r) => Object.assign({}, r));
		state.rows.tool_changes = (data.tool_changes || []).map((r) => Object.assign({}, r));
		state.dirty = false;
		$("k-signin").style.display = "none";
		$("k-entry").style.display = "";
		$("k-date").disabled = $("k-shift").disabled = true;
		const status = data.docstatus === 1 ? t("submitted") : data.entry ? t("draft {0}", [data.entry]) : t("new entry");
		$("k-who").textContent = `${data.operator_name || data.operator} · ${status}`;
		render();
		panel($("k-shift-panel"), data.shift_panel);
		panel($("k-aids"), data.aids);
		$("k-reason").style.display = data.needs_reason ? "" : "none";
		$("k-reason-text").textContent = data.needs_reason || "";
		if (data.docstatus === 1) say(t("This shift is submitted. Thank you."), "green");
	}

	function cell(tr, el) {
		const td = document.createElement("td");
		td.appendChild(el);
		tr.appendChild(td);
		return el;
	}

	function input(row, key, type, extra) {
		const el = document.createElement("input");
		el.type = type || "text";
		el.value = row[key] == null ? "" : row[key];
		Object.assign(el, extra || {});
		el.addEventListener("input", () => {
			row[key] = el.value;
			state.dirty = true;
		});
		return el;
	}

	function select(row, key, options) {
		const el = document.createElement("select");
		option(el, "", "—", !row[key]);
		options.forEach(([value, label]) => option(el, value, label, value === row[key]));
		el.addEventListener("change", () => {
			row[key] = el.value;
			state.dirty = true;
		});
		return el;
	}

	function removeButton(table, index) {
		const b = document.createElement("button");
		b.className = "kiosk-remove";
		b.textContent = "✕";
		b.title = t("Remove this row");
		b.addEventListener("click", () => {
			state.rows[table].splice(index, 1);
			state.dirty = true;
			render();
		});
		return b;
	}

	function render() {
		const locked = state.data && state.data.docstatus === 1;
		const cards = (state.data.job_cards || []).map((c) => [c.name, c.label]);
		const prod = $("k-production");
		prod.innerHTML = "";
		state.rows.production.forEach((row, i) => {
			const tr = document.createElement("tr");
			const known = cards.some(([v]) => v === row.job_card);
			cell(tr, select(row, "job_card", known || !row.job_card ? cards : cards.concat([[row.job_card, row.job_card]])));
			cell(tr, input(row, "from_time", "time"));
			cell(tr, input(row, "to_time", "time"));
			cell(tr, input(row, "good_qty", "number", { min: 0, step: "any", inputMode: "decimal" }));
			cell(tr, input(row, "rejected_qty", "number", { min: 0, step: "any", inputMode: "decimal" }));
			cell(tr, input(row, "rejection_reason", "text"));
			cell(tr, removeButton("production", i));
			prod.appendChild(tr);
		});
		const cats = (state.ctx.categories || []).map((c) => [c.name, c.name]);
		const down = $("k-downtime");
		down.innerHTML = "";
		state.rows.downtime.forEach((row, i) => {
			const tr = document.createElement("tr");
			cell(tr, select(row, "downtime_category", cats));
			cell(tr, input(row, "from_time", "time"));
			cell(tr, input(row, "to_time", "time"));
			cell(tr, removeButton("downtime", i));
			down.appendChild(tr);
		});
		const tools = $("k-tools");
		tools.innerHTML = "";
		state.rows.tool_changes.forEach((row, i) => {
			const tr = document.createElement("tr");
			cell(tr, input(row, "change_time", "time"));
			cell(tr, input(row, "tool_description", "text"));
			cell(tr, select(row, "reason", (state.ctx.tool_reasons || []).map((r) => [r, t(r)])));
			const box = document.createElement("div");
			const file = document.createElement("input");
			file.type = "file";
			file.accept = "image/*";
			file.setAttribute("capture", "environment");
			file.addEventListener("change", () => file.files[0] && shrink(file.files[0], (url) => {
				row.photo = url;
				state.dirty = true;
				render();
			}));
			box.appendChild(file);
			if (row.photo) {
				const img = document.createElement("img");
				img.className = "kiosk-photo";
				img.src = row.photo;
				box.appendChild(img);
			}
			cell(tr, box);
			cell(tr, removeButton("tool_changes", i));
			tools.appendChild(tr);
		});
		root.querySelectorAll("#k-entry input, #k-entry select, .kiosk-add, .kiosk-remove, #k-save").forEach((el) => (el.disabled = locked));
		$("k-submit").disabled = locked || !state.data.entry;
	}

	function shrink(fileObj, done) {
		// A phone photo is several MB: resize to 1280 px and JPEG before sending.
		const reader = new FileReader();
		reader.onload = () => {
			const img = new Image();
			img.onload = () => {
				const scale = Math.min(1, 1280 / Math.max(img.width, img.height));
				const canvas = document.createElement("canvas");
				canvas.width = Math.round(img.width * scale);
				canvas.height = Math.round(img.height * scale);
				canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
				done(canvas.toDataURL("image/jpeg", 0.75));
			};
			img.src = reader.result;
		};
		reader.readAsDataURL(fileObj);
	}

	function addRow(table) {
		const blank = {
			production: { job_card: "", from_time: "", to_time: "", good_qty: "", rejected_qty: "", rejection_reason: "" },
			downtime: { downtime_category: "", from_time: "", to_time: "" },
			tool_changes: { change_time: "", tool_description: "", reason: "", photo: "" },
		}[table];
		state.rows[table].push(blank);
		state.dirty = true;
		render();
	}

	async function save() {
		say("");
		$("k-save").disabled = true;
		try {
			const out = await call("save_entry", {
				token: state.token,
				production: state.rows.production,
				downtime: state.rows.downtime,
				tool_changes: state.rows.tool_changes,
			});
			show(out);
			say(t("Saved."), "green");
			return true;
		} catch (e) {
			say(e.message);
			return false;
		} finally {
			$("k-save").disabled = false;
		}
	}

	async function submit(reason) {
		if (state.dirty && !(await save())) return;
		say("");
		try {
			const out = await call("submit_entry", { token: state.token, reason: reason || "" });
			show(out);
			if (out.needs_reason) say(t("A reason is needed before this shift can be submitted."), "orange");
		} catch (e) {
			say(e.message);
		}
	}

	$("k-signin-btn").addEventListener("click", signIn);
	$("k-pin").addEventListener("keydown", (e) => e.key === "Enter" && signIn());
	$("k-save").addEventListener("click", save);
	$("k-submit").addEventListener("click", () => submit());
	$("k-reason-btn").addEventListener("click", () => submit($("k-reason-input").value));
	$("k-signout").addEventListener("click", signOut);
	root.querySelectorAll(".kiosk-add").forEach((b) => b.addEventListener("click", () => addRow(b.dataset.table)));
	window.addEventListener("beforeunload", (e) => {
		if (state.dirty) {
			e.preventDefault();
			e.returnValue = "";
		}
	});
	load();
})();
