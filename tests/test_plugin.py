"""The installed reporter advertises its existing command without an umbrella dependency."""
from importlib.metadata import distribution

from livingproof_capability_report.cli import report


def test_installed_plugin_metadata():
    package = distribution("livingproof-capability-report")
    plugins = [entry for entry in package.entry_points
               if entry.group == "livingproof.capability.commands"]
    assert len(plugins) == 1
    assert plugins[0].name == "report"
    assert plugins[0].load() is report
    assert not any(requirement.split(";")[0].strip().lower() == "livingproof"
                   for requirement in package.requires or [])
