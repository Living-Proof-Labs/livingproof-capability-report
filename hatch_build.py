"""Embed source provenance using Hatch's supported custom build hook."""
import importlib.util
import json
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        module_path = root / "src/livingproof_capability_report/version.py"
        spec = importlib.util.spec_from_file_location("report_build_version", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        target = root / "src/livingproof_capability_report/_build_provenance.json"
        target.write_text(json.dumps(module.build_provenance(root, self.metadata.version),
                                     sort_keys=True, indent=2) + "\n", encoding="utf-8")
        build_data["artifacts"].append(str(target.relative_to(root)))
