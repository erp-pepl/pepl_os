"""CR3, one-time: PEPL's access plan (24 Nov 2026).

Decision 1 - only the holders of the new add-on profile PEPL Item Master make Items, so PEPL Purchase Manager loses
Item Manager. Decision 8 - Quality sees stock but Stores posts it, so PEPL Quality Manager loses Stock User (it gets
PEPL Stock Viewer on the next migrate). Users holding the profiles follow (Frappe re-saves them).
"""

from pepl_os.setup.roles import PROFILE_CORRECTIONS_V0_79, remove_roles_from_profiles


def execute():
	remove_roles_from_profiles(PROFILE_CORRECTIONS_V0_79)
