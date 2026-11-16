"""CR2, one-time: the CEO profile loses PEPL Tender Viewer; the two Sales & Tender profiles lose the tender roles
and are renamed PEPL Sales Manager / PEPL Sales Executive (their users keep them). Tender rights now come only from
the PEPL Tender Only profile, and a tender opens only for the users listed in site_config.json."""

from pepl_os.setup.roles import (
	PROFILE_CORRECTIONS_V0_62,
	PROFILE_RENAMES_V0_62,
	remove_roles_from_profiles,
	rename_profiles,
)


def execute():
	remove_roles_from_profiles(PROFILE_CORRECTIONS_V0_62)
	rename_profiles(PROFILE_RENAMES_V0_62)
