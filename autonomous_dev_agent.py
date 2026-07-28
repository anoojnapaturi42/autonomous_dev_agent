"""Local bootstrap so `python -m autonomous_dev_agent` works from the repo root."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


def _load_cli_main():
    root = Path(__file__).resolve().parent
    package_dir = root / "src" / "autonomous_dev_agent"
    package_name = "_autonomous_dev_agent_impl"

    package_spec = importlib.util.spec_from_file_location(
        package_name,
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    if package_spec is None or package_spec.loader is None:
        raise RuntimeError("Unable to load the autonomous dev agent package.")

    package_module = importlib.util.module_from_spec(package_spec)
    sys.modules[package_name] = package_module
    package_spec.loader.exec_module(package_module)

    cli_module = importlib.import_module(f"{package_name}.cli")
    return cli_module.main


main = _load_cli_main()


if __name__ == "__main__":
    main()

