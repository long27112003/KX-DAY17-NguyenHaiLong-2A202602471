from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Build an isolated configuration for tests using tmp_path."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)

    dummy_model = ProviderConfig(
        provider="custom",
        model_name="mock-model",
        temperature=0.0,
        api_key="mock-key",
        base_url="http://mock-url",
    )

    return LabConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=state_dir,
        compact_threshold_tokens=80,  # low threshold so compaction triggers quickly in tests
        compact_keep_messages=2,
        model=dummy_model,
        judge_model=dummy_model,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify `User.md` can be created, read, and edited."""
    cfg = make_config(tmp_path)
    store = UserProfileStore(cfg.state_dir / "profiles")
    user_id = "test_dungct"

    # 1. Test creation and writing
    path = store.write_text(
        user_id, "# User Profile: test_dungct\n- **name**: DũngCT\n- **location**: Đà Nẵng\n"
    )
    assert path.exists()
    assert store.file_size(user_id) > 0

    # 2. Test reading
    content = store.read_text(user_id)
    assert "DũngCT" in content
    assert "Đà Nẵng" in content

    # 3. Test editing
    changed = store.edit_text(user_id, "Đà Nẵng", "Huế")
    assert changed is True
    updated = store.read_text(user_id)
    assert "Huế" in updated
    assert "Đà Nẵng" not in updated

    # 4. Test structured facts parsing
    facts = store.facts(user_id)
    assert facts.get("name") == "DũngCT"
    assert facts.get("location") == "Huế"


def test_compact_trigger(tmp_path: Path) -> None:
    """Verify long threads trigger compaction and update compactions counter."""
    cfg = make_config(tmp_path)
    agent = AdvancedAgent(config=cfg, force_offline=True)
    thread_id = "test_compact_thread"

    # Send multiple turns exceeding threshold (80 tokens)
    for i in range(8):
        agent.reply(
            "user_compact",
            thread_id,
            f"Lượt trao đổi số {i} với độ dài đủ lớn để vượt ngưỡng nén ngữ cảnh.",
        )

    assert agent.compaction_count(thread_id) > 0
    ctx = agent.compact_memory.context(thread_id)
    assert len(ctx["messages"]) <= cfg.compact_keep_messages  # type: ignore
    assert len(str(ctx["summary"])) > 0


def test_cross_session_recall(tmp_path: Path) -> None:
    """Verify Advanced remembers across sessions while Baseline does not."""
    cfg = make_config(tmp_path)
    advanced = AdvancedAgent(config=cfg, force_offline=True)
    baseline = BaselineAgent(config=cfg, force_offline=True)
    user_id = "user_recall"

    # Session 1: User introduces themselves
    intro = "Chào bạn, mình tên là DũngCT và đồ uống yêu thích là cà phê sữa đá."
    advanced.reply(user_id, "session_1", intro)
    baseline.reply(user_id, "session_1", intro)

    # Session 2: Recall question in a fresh thread
    query = "Mình tên gì và đồ uống yêu thích là gì?"
    res_adv = advanced.reply(user_id, "session_2_fresh", query)
    res_base = baseline.reply(user_id, "session_2_fresh", query)

    # Advanced Agent remembers via User.md
    assert "DũngCT" in res_adv["reply"]
    assert "cà phê sữa đá" in res_adv["reply"]

    # Baseline Agent forgets long-term facts in a new thread
    assert "DũngCT" not in res_base["reply"]
    assert "cà phê sữa đá" not in res_base["reply"]


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Compare prompt load of baseline vs advanced on a long thread."""
    cfg = make_config(tmp_path)
    advanced = AdvancedAgent(config=cfg, force_offline=True)
    baseline = BaselineAgent(config=cfg, force_offline=True)
    thread_id = "long_thread_comparison"

    for i in range(12):
        msg = (
            f"Lượt {i}: Đoạn văn bản mô tả kỹ thuật chi tiết về hệ thống AI, "
            "nhằm tạo áp lực ngữ cảnh và kiểm tra khả năng tiết kiệm token khi nén."
        )
        advanced.reply("user_load", thread_id, msg)
        baseline.reply("user_load", thread_id, msg)

    assert advanced.compaction_count(thread_id) > 0
    assert baseline.compaction_count(thread_id) == 0

    adv_load = advanced.prompt_token_usage(thread_id)
    base_load = baseline.prompt_token_usage(thread_id)

    assert (
        adv_load < base_load
    ), f"Advanced prompt load ({adv_load}) must be less than Baseline ({base_load})"
