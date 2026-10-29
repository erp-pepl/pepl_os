// C3a-B1 - Foreman view: one row per machine that runs, for the chosen day and shift.
(function () {
	const root = document.getElementById("pepl-foreman");
	if (!root || !document.getElementById("f-rows")) return;
	const $ = (id) => document.getElementById(id);
	const t = (s, args) => (window.__ ? window.__(s, args) : s.replace(/\{(\d)\}/g, (m, i) => (args || [])[i]));

	async function call(method, args) {
		const query = new URLSearchParams(args || {}).toString();
		const res = await fetch("/api/method/pepl_os.pepl_production.kiosk." + method + (query ? "?" + query : ""), {
			headers: { Accept: "application/json" },
			credentials: "same-origin",
		});
		const out = await res.json().catch(() => ({}));
		if (!res.ok) throw new Error(t("Could not load the shift entries."));
		return out.message;
	}

	function td(tr, content, className) {
		const cell = document.createElement("td");
		if (content instanceof Node) cell.appendChild(content);
		else cell.textContent = content == null ? "" : content;
		if (className) cell.className = className;
		tr.appendChild(cell);
	}

	async function load(first) {
		try {
			const data = await call("foreman_board", first ? {} : { posting_date: $("f-date").value, shift: $("f-shift").value });
			if (first) {
				$("f-date").value = data.posting_date;
				data.shifts.forEach((s) => {
					const o = document.createElement("option");
					o.value = o.textContent = s;
					o.selected = s === data.shift;
					$("f-shift").appendChild(o);
				});
			}
			$("f-summary").textContent = t("{0} submitted · {1} draft · {2} missing", [data.submitted, data.drafts, data.missing]);
			const body = $("f-rows");
			body.innerHTML = "";
			data.rows.forEach((r) => {
				const tr = document.createElement("tr");
				td(tr, r.machine, "fm-dot fm-" + r.colour);
				if (r.entries && r.entries.length) {
					const box = document.createElement("span");
					r.entries.forEach((name, i) => {
						const a = document.createElement("a");
						a.href = "/app/pepl-shift-production-entry/" + encodeURIComponent(name);
						a.textContent = name + (i < r.entries.length - 1 ? ", " : "");
						box.appendChild(a);
					});
					box.appendChild(document.createTextNode(" · " + t(r.state)));
					td(tr, box);
				} else {
					td(tr, t(r.state));
				}
				td(tr, r.operators || "");
				td(tr, r.good || "");
				td(tr, r.rejected || "");
				td(tr, r.unexplained == null ? "" : r.unexplained);
				td(tr, r.text || "");
				body.appendChild(tr);
			});
			$("f-message").textContent = "";
		} catch (e) {
			$("f-message").textContent = e.message;
		}
	}

	$("f-date").addEventListener("change", () => load(false));
	$("f-shift").addEventListener("change", () => load(false));
	load(true);
	setInterval(() => load(false), 120000);
})();
