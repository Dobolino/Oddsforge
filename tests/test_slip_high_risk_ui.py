"""Streamlit AppTest: Tippschein high-risk checkbox + bold warning."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from quantbot.dashboard.ux import UXMode
from quantbot.i18n import t

_APP = Path(__file__).resolve().parents[1] / "src" / "quantbot" / "dashboard" / "app.py"


def test_slip_high_risk_checkbox_shows_bold_warning(monkeypatch) -> None:
    import quantbot.preferences as prefs

    monkeypatch.setattr(prefs, "is_welcome_dismissed", lambda path=None: True)
    monkeypatch.setattr(prefs, "set_welcome_dismissed", lambda path=None: None)
    monkeypatch.setattr(prefs, "is_glossary_seen", lambda path=None: True)
    monkeypatch.setattr(prefs, "set_glossary_seen", lambda path=None: Path("/tmp/glossary_seen"))

    at = AppTest.from_file(str(_APP), default_timeout=60)
    at.session_state["ux_mode"] = UXMode.ADVANCED
    at.session_state["nav_page"] = "slip"
    at.session_state["welcome_dismissed"] = True
    at.session_state["glossary_seen"] = True
    at.run()
    assert not at.exception

    keys = {c.key for c in at.checkbox if c.key}
    if "slip_high_risk" not in keys:
        radios = [r for r in at.sidebar.radio if r.key == "nav_page"]
        assert radios, "nav radio missing"
        radios[0].set_value("slip").run()
        keys = {c.key for c in at.checkbox if c.key}

    assert "slip_high_risk" in keys, f"high-risk checkbox missing; keys={sorted(keys)}"

    before = "\n".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "HÖHERES RISIKO AKTIV" not in before

    at.checkbox(key="slip_high_risk").check().run()
    assert not at.exception

    after = "\n".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "HÖHERES RISIKO AKTIV" in after
    assert "font-weight:800" in after
    assert t("slip.high_risk", "de")
