import json
import re
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "scripts" / "codebase_tutor" / "i18n"
APP = Path(__file__).resolve().parents[1] / "assets" / "report" / "app.js"


def test_all_languages_have_same_keys_and_placeholders():
    en = json.loads((I18N / "en.json").read_text())
    for p in I18N.glob("*.json"):
        d = json.loads(p.read_text())
        assert set(d) == set(en), p.name
        for k, v in en.items():
            assert set(re.findall(r"\{\w+\}", v)) == set(re.findall(r"\{\w+\}", d[k])), (p.name, k)


def test_static_keys_used_by_app_exist():
    en = json.loads((I18N / "en.json").read_text())
    used = set(re.findall(r"\bt\('([a-z0-9_\-]+)'", APP.read_text()))
    missing = {k for k in used - set(en) if not k.endswith("_")}
    assert not missing, missing
