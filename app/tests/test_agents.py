from __future__ import annotations

from bibstudio.agents import AgentFile, estimate_tokens, render_variables
from bibstudio.store import DEFAULT_AGENTS


def test_parse_front_matter_and_sections():
    text = DEFAULT_AGENTS["author"]
    agent = AgentFile.parse("author", text)
    assert agent.meta["id"] == "author"
    assert agent.meta["label"] == "Author"
    assert [s.heading for s in agent.sections][:2] == ["Role", "Absolute constraints"]
    assert "no web access" in agent.section("Role")


def test_render_roundtrip_is_stable():
    agent = AgentFile.parse("critic", DEFAULT_AGENTS["critic"])
    once = agent.to_text()
    twice = AgentFile.parse("critic", once).to_text()
    assert once == twice


def test_system_prompt_contains_locked_contract():
    agent = AgentFile.parse("author", DEFAULT_AGENTS["author"])
    system = agent.system_prompt()
    assert "Engine contract (not editable)" in system
    assert "[P-0007]" in system
    # the user-editable part cannot remove the guarantee, because it is appended
    agent.sections = [s for s in agent.sections if s.heading != "Absolute constraints"]
    assert "Engine contract (not editable)" in agent.system_prompt()


def test_payload_roundtrip():
    agent = AgentFile.parse("researcher", DEFAULT_AGENTS["researcher"])
    payload = agent.as_payload()
    rebuilt = AgentFile.from_payload("researcher", payload)
    assert rebuilt.body() == agent.body()
    assert rebuilt.meta == agent.meta


def test_user_added_section_survives():
    agent = AgentFile.parse("author", DEFAULT_AGENTS["author"])
    agent.sections.append(type(agent.sections[0])(heading="Domain guidance",
                                                  body="Always discuss cost."))
    reparsed = AgentFile.parse("author", agent.to_text())
    assert reparsed.section("Domain guidance") == "Always discuss cost."


def test_variables_render_and_unknown_stay_visible():
    out = render_variables("Study: {{project.title}} / {{ missing }}",
                           {"project.title": "Heat"})
    assert out == "Study: Heat / {{ missing }}"


def test_token_estimate_is_positive():
    assert estimate_tokens("") >= 1
    assert estimate_tokens("a" * 400) == 100
