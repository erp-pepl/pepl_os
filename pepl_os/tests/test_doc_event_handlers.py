"""Guard (0.67.1, CI #73): no pepl_os document-event handler returns a value.

Frappe merges the return values of all handlers of one event: a handler returning text followed by one returning a dict
crashed a QC Inspection submit (ncr.on_inspection_submit returned the NCR name, scorecard.on_inspection_change a dict).
Handlers return nothing; helpers that tests need the result of are separate functions.
"""

import ast
import importlib
import inspect
import textwrap

import frappe

from pepl_os.tests.utils import PEPLTestCase


def _handlers():
	paths = set()
	for events in frappe.get_hooks("doc_events").values():
		for methods in events.values():
			for method in methods if isinstance(methods, list | tuple) else [methods]:
				if isinstance(method, str) and method.startswith("pepl_os."):
					paths.add(method)
	return sorted(paths)


def _returns_a_value(fn):
	tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
	for node in ast.walk(tree):
		if isinstance(node, ast.Return) and node.value is not None:
			if not (isinstance(node.value, ast.Constant) and node.value.value is None):
				return True
	return False


class TestDocEventHandlers(PEPLTestCase):
	def test_no_pepl_os_handler_returns_a_value(self):
		paths = _handlers()
		self.assertGreater(len(paths), 50)
		offenders = []
		for path in paths:
			module, name = path.rsplit(".", 1)
			if _returns_a_value(getattr(importlib.import_module(module), name)):
				offenders.append(path)
		self.assertEqual(offenders, [])
