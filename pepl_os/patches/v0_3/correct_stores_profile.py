"""One-time: take Purchase User out of the PEPL Stores profile (it let Stores create Purchase Orders)."""

from pepl_os.setup.roles import PROFILE_CORRECTIONS_V0_3, remove_roles_from_profiles


def execute():
	remove_roles_from_profiles(PROFILE_CORRECTIONS_V0_3)
