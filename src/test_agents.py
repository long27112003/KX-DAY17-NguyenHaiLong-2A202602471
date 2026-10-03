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


# ==============================================================================
# BONUS TESTS (90-100 pts Rubric Requirements)
# ==============================================================================


def test_bonus_confidence_threshold_rejects_noise_and_jokes() -> None:
    """Verify that statements with low confidence (jokes/noise) are rejected."""
    from memory_store import extract_profile_entities, extract_profile_updates

    # Case 1: Joke about switching to product manager
    joke_msg = "Có lúc mình đùa chuyển sang product manager cho đỡ canh pipeline nhưng chỉ là đùa thôi."
    entities = extract_profile_entities(joke_msg)
    pm_ent = next((e for e in entities if e.key == "profession"), None)
    assert pm_ent is not None
    assert pm_ent.confidence < 0.50  # Low confidence

    # Filter with threshold 0.70
    updates = extract_profile_updates(joke_msg, min_confidence=0.70)
    assert "profession" not in updates  # Rejected!

    # Case 2: Business trip noise (Hanoi)
    noise_msg = "Hà Nội chỉ là nơi mình vừa bay ra họp hai ngày với đối tác."
    entities_noise = extract_profile_entities(noise_msg)
    hanoi_ent = next((e for e in entities_noise if e.key == "location"), None)
    assert hanoi_ent is not None
    assert hanoi_ent.confidence < 0.50

    updates_noise = extract_profile_updates(noise_msg, min_confidence=0.70)
    assert "location" not in updates_noise  # Rejected!

    # Case 3: High confidence assertion
    assert_msg = "Mình tên là DũngCT và nghề nghiệp hiện tại là MLOps engineer."
    valid_updates = extract_profile_updates(assert_msg, min_confidence=0.70)
    assert valid_updates.get("name") == "DũngCT"
    assert valid_updates.get("profession") == "MLOps engineer"


def test_bonus_conflict_resolution_and_audit_log(tmp_path: Path) -> None:
    """Verify conflict handling properly updates active facts and records audit trail."""
    cfg = make_config(tmp_path)
    store = UserProfileStore(cfg.state_dir / "profiles")
    user_id = "test_conflict_user"

    # Turn 1: Initial fact
    store.upsert_facts(user_id, {"location": "Đà Nẵng", "profession": "backend engineer"}, turn=1)
    facts_t1 = store.facts(user_id)
    assert facts_t1.get("location") == "Đà Nẵng"
    assert facts_t1.get("profession") == "backend engineer"

    # Turn 2: Correction / Conflict (Move to Hue, change job to MLOps)
    store.upsert_facts(user_id, {"location": "Huế", "profession": "MLOps engineer"}, turn=2)
    facts_t2 = store.facts(user_id)

    # Active facts MUST be updated without conflict
    assert facts_t2.get("location") == "Huế"
    assert facts_t2.get("profession") == "MLOps engineer"

    # User.md file must preserve the conflict audit trail
    md_content = store.read_text(user_id)
    assert "Lịch sử điều chỉnh (Conflict & Revision Log)" in md_content
    assert "đổi từ 'Đà Nẵng' -> 'Huế'" in md_content
    assert "đổi từ 'backend engineer' -> 'MLOps engineer'" in md_content


def test_bonus_memory_decay(tmp_path: Path) -> None:
    """Verify exponential memory decay weights based on recency."""
    cfg = make_config(tmp_path)
    store = UserProfileStore(cfg.state_dir / "profiles")
    user_id = "test_decay_user"

    # Facts established at turn 1
    store.upsert_facts(user_id, {"name": "DũngCT", "favorite_drink": "cà phê sữa đá"})

    # Evaluate decay at turn 31 (delta = 30 turns)
    turn_metadata = {"name": 30, "favorite_drink": 1}
    weights = store.calculate_memory_decay(
        user_id, current_turn=31, turn_metadata=turn_metadata, half_life_turns=15
    )

    # Recently confirmed fact (name at turn 30, delta 1) has high weight (~0.95+)
    assert weights["name"] > 0.90
    # Old unrefreshed fact (drink at turn 1, delta 30 = 2 half-lives) decays to ~0.25
    assert weights["favorite_drink"] <= 0.30

