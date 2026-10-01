"""Tests for the card file handling in frontend.py (no Home Assistant needed)."""

import re
from pathlib import Path

from custom_components.smart_climate import frontend

INTEGRATION = Path(frontend.__file__).parent


def test_every_relative_js_import_is_copied():
    """A card that imports a module frontend.py does not copy would break in HA."""
    for name in frontend.MODULE_FILES:
        source = (INTEGRATION / f"{name}.js").read_text(encoding="utf-8")
        for imported in re.findall(r'from\s+"\./([\w-]+)\.js"', source):
            assert imported in frontend.MODULE_FILES, f"{name}.js imports {imported}.js"


def test_versioned_imports_only_touch_helper_modules():
    src = (
        'import { LitElement } from "https://unpkg.com/lit@3/index.js?module";\n'
        'import { Base } from "./smart-climate-base-editor.js";\n'
        'import { t } from "./smart-climate-shared.js";\n'
    )
    out = frontend._with_versioned_imports(src, "abc123")
    assert 'from "./smart-climate-base-editor.js?hacstag=abc123"' in out
    assert 'from "./smart-climate-shared.js?hacstag=abc123"' in out
    assert 'index.js?module"' in out


def test_copy_modules_copies_all_and_versions_imports(tmp_path):
    frontend._copy_modules(INTEGRATION, tmp_path)
    for name in frontend.MODULE_FILES:
        assert (tmp_path / f"{name}.js").exists(), name
    tag = frontend._modules_hash(INTEGRATION)
    card = (tmp_path / "smart-climate-schedule-card.js").read_text(encoding="utf-8")
    assert f"smart-climate-shared.js?hacstag={tag}" in card


def test_hash_changes_with_any_module(tmp_path):
    for name in frontend.MODULE_FILES:
        (tmp_path / f"{name}.js").write_text("a", encoding="utf-8")
    before = frontend._modules_hash(tmp_path)
    (tmp_path / "smart-climate-shared.js").write_text("b", encoding="utf-8")
    assert frontend._modules_hash(tmp_path) != before
