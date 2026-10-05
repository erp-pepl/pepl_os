"""Install and migrate hooks. Everything here must be safe to run repeatedly."""

from pepl_os.common.letterhead import ensure_default_print_formats
from pepl_os.pepl_governance.retention import apply_log_retention
from pepl_os.pepl_purchase.command_centre import ensure_command_centre_block
from pepl_os.pepl_stores.csm import ensure_return_type
from pepl_os.pepl_stores.heat import allow_same_item_lines_once, enable_batches
from pepl_os.pepl_stores.reorder import switch_off_auto_mr_once
from pepl_os.pepl_stores.scrap import ensure_scrap_masters
from pepl_os.pepl_stores.stock_tree import seed_stock_structure
from pepl_os.setup.custom_fields import apply_custom_fields
from pepl_os.setup.permissions import grant_ceo_view, grant_extra_views, restrict_delete
from pepl_os.setup.property_setters import apply_property_setters
from pepl_os.setup.roles import ensure_role_profiles, ensure_roles


def before_setup():
	# Roles must exist before Reports / Pages that reference them are synced.
	ensure_roles()


def ensure_setup():
	ensure_roles()
	apply_custom_fields()
	apply_property_setters()  # A3
	ensure_role_profiles()  # A2
	restrict_delete()  # A2 / A5
	grant_ceo_view()  # A2: the CEO sees every record, changes none
	grant_extra_views()  # A2: e.g. Accounts sees Purchase Orders
	apply_log_retention()  # A5
	seed_stock_structure()  # C2-04: stock classes, stores, Item Group defaults
	enable_batches()  # C2-15: Batch = heat number needs batches switched on in Stock Settings
	allow_same_item_lines_once()  # C2-15: Split by heat puts the same item on several receipt lines
	ensure_return_type()  # C2-16: Stock Entry Type "CSM Return to Customer"
	ensure_scrap_masters()  # C2-18: CSM Scrap item group, Scrap Buyers, the default scrap items (once)
	switch_off_auto_mr_once()  # C2-19: ERPNext's automatic MR stays off until the Stores HOD asks for it
	ensure_command_centre_block()  # C2-23: the "Purchase Tracker last refreshed" line on both workspaces
	ensure_default_print_formats()  # C2-24: PO, RFQ, weighment, scrap sale, count print on the letterhead


def before_install():
	before_setup()


def after_install():
	ensure_setup()


def before_migrate():
	before_setup()


def after_migrate():
	ensure_setup()
