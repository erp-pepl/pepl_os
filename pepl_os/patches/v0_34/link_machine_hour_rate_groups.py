"""C3a-R1 - Machine-Hour Rates: the machine group becomes a link to the machine group (Workstation Type).

Each row written before keeps its rate: a group that matches a Workstation Type in any upper / lower case is set
to that Workstation Type; a group with no Workstation Type yet gets one, so nothing is lost and the machines
can be put in it.
"""

from pepl_os.pepl_production.machine_hour_rates import link_rate_groups


def execute():
	link_rate_groups()
