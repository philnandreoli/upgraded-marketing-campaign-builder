from pathlib import Path


CANONICAL_MODULES = {
    "backend.services.auth": "backend.infrastructure.auth",
    "backend.services.database": "backend.infrastructure.database",
    "backend.services.campaign_store": "backend.infrastructure.campaign_store",
}


def test_runtime_and_tests_use_canonical_import_boundaries():
    """Guard against new import-boundary drift for core backend dependencies."""
    root = Path(__file__).resolve().parents[2] / "backend"

    violations: list[str] = []
    for py_file in root.rglob("*.py"):
        if py_file.parts[1] == "services":
            continue

        text = py_file.read_text(encoding="utf-8")
        for legacy_module, canonical_module in CANONICAL_MODULES.items():
            if f"from {legacy_module} import " in text or f"import {legacy_module}" in text:
                rel = py_file.relative_to(root.parent)
                violations.append(
                    f"{rel}: use {canonical_module} instead of {legacy_module}"
                )

    assert not violations, "Import boundary violations found:\n" + "\n".join(sorted(violations))
