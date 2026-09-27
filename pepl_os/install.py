"""Install and migrate hooks. Everything here must be safe to run repeatedly."""

from pepl_os.setup.custom_fields import apply_custom_fields


def ensure_setup():
	apply_custom_fields()


def after_install():
	ensure_setup()


def after_migrate():
	ensure_setup()
