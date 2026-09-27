frappe.pages["pepl-system-health"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("PEPL System Health"),
		single_column: true,
	});
	page.set_primary_action(__("Refresh"), () => render(page));
	render(page);
};

const PEPL_HEALTH_COLOURS = {
	OK: "green",
	Stale: "orange",
	"Never Run": "orange",
	"Last Run Failed": "red",
	Stopped: "red",
	"Not Scheduled": "red",
};

function render(page) {
	const esc = frappe.utils.escape_html;
	$(page.body).html(`<p class="text-muted">${__("Loading...")}</p>`);

	frappe.call("pepl_os.pepl_governance.page.pepl_system_health.pepl_system_health.get_health").then((r) => {
		const d = r.message;
		const scheduler =
			d.scheduler_enabled === false
				? `<span class="indicator-pill red">${__("Scheduler is OFF on this site")}</span>`
				: `<span class="indicator-pill green">${__("Scheduler on")}</span>`;
		const overall = d.all_ok
			? `<span class="indicator-pill green">${__("All jobs healthy")}</span>`
			: `<span class="indicator-pill orange">${__("Attention needed")}</span>`;

		const rows = d.jobs
			.map((j) => {
				const colour = PEPL_HEALTH_COLOURS[j.status] || "gray";
				return `<tr>
					<td>${esc(j.method)}</td>
					<td>${esc(j.frequency)}</td>
					<td><span class="indicator-pill ${colour}">${esc(__(j.status))}</span></td>
					<td>${j.last_success ? frappe.datetime.str_to_user(j.last_success) : "-"}</td>
					<td>${j.records_touched ?? "-"}</td>
					<td>${j.last_failure ? frappe.datetime.str_to_user(j.last_failure) : "-"}</td>
				</tr>`;
			})
			.join("");

		const apps = Object.entries(d.apps)
			.map(([app, v]) => `${esc(app)} ${esc(String(v))}`)
			.join(" · ");

		$(page.body).html(`
			<div class="mb-3">${overall} ${scheduler}</div>
			<p class="text-muted small">${__("Site")}: ${esc(d.site)} · ${__("Apps")}: ${apps}</p>
			<table class="table table-bordered">
				<thead><tr>
					<th>${__("Job")}</th><th>${__("Frequency")}</th><th>${__("Status")}</th>
					<th>${__("Last Success")}</th><th>${__("Records")}</th><th>${__("Last Failure")}</th>
				</tr></thead>
				<tbody>${rows || `<tr><td colspan="6">${__("No PEPL jobs declared")}</td></tr>`}</tbody>
			</table>
			<p class="text-muted small">${__(
				"Every PEPL job writes a PEPL Job Run row each time it runs. 'Stale' means no successful run within the expected interval."
			)}</p>
		`);
	});
}
