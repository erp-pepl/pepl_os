"""Install and migrate hooks. Everything here must be safe to run repeatedly."""

from pepl_os.pepl_governance.retention import apply_log_retention
from pepl_os.setup.custom_fields import apply_custom_fields
from pepl_os.setup.permissions import restrict_delete
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
	apply_log_retention()  # A5


def before_install():
	before_setup()


def after_install():
	ensure_setup()


def before_migrate():
	before_setup()


def after_migrate():
	ensure_setup()
