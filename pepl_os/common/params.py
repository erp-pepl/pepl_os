"""Single entry point for reading PEPL System Parameters.

Every threshold lives in PEPL System Parameters (a pepl_sales DocType).
pepl_os adds its own fields there as Custom Fields (see pepl_os/setup),
and every module reads them only through these helpers.
"""

from frappe.utils import cint, flt
from pepl_sales.pepl_sales.doctype.pepl_system_parameters.pepl_system_parameters import (
	get_param as _get_param,
)

SYSTEM_PARAMETERS = "PEPL System Parameters"


def get(field_name, default=None):
	"""Return a System Parameter, or `default` when it is empty or missing."""
	return _get_param(field_name, default)


def get_int(field_name, default=0):
	return cint(get(field_name, default))


def get_float(field_name, default=0.0):
	return flt(get(field_name, default))


def is_enabled(field_name, default=0):
	return bool(cint(get(field_name, default)))
