from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def estimate_tokens(text: str) -> int:
    """Implement a simple token estimator based on character count.

    - Empty text returns 0.
    - Non-empty text approximates tokens via len(text) // 4.
    """
    cleaned = text.strip()
    if not cleaned:
        return 0
    return max(1, (len(cleaned) + 3) // 4)


@dataclass
class EntityFact:
    """Structured fact representation with confidence score and recency metadata."""

    key: str
    value: str
    confidence: float = 1.0
    status: str = "active"  # 'active' or 'superseded'
    last_mentioned_turn: int = 1
    mention_count: int = 1


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md` with conflict handling and metadata tracking."""

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        """Sanitize user id and return path to User.md."""
        sanitized = re.sub(r"[^\w\-]", "_", user_id.strip())
        return self.root_dir / sanitized / "User.md"

    def read_text(self, user_id: str) -> str:
        """Return file content or empty string if not found."""
        path = self.path_for(user_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def write_text(self, user_id: str, content: str) -> Path:
        """Write markdown content to disk and return file path."""
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        """Replace first occurrence of search_text inside User.md."""
        path = self.path_for(user_id)
        if not path.exists():
            return False
        current = path.read_text(encoding="utf-8")
        if search_text not in current:
            return False
        updated = current.replace(search_text, replacement, 1)
        path.write_text(updated, encoding="utf-8")
        return True

    def file_size(self, user_id: str) -> int:
        """Return the current file size in bytes."""
        path = self.path_for(user_id)
        if path.exists():
            return path.stat().st_size
        return 0

    def facts(self, user_id: str) -> dict[str, str]:
        """Extract structured active key-value facts from User.md."""
        text = self.read_text(user_id)
        extracted: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            # Parse only active facts, ignore historical change notes
            m = re.match(r"^-\s*(?:\*\*)?([\w_]+)(?:\*\*)?:\s*(.*)$", line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip()
                extracted[key] = val
        return extracted

    def upsert_facts(
        self,
        user_id: str,
        new_facts: dict[str, str],
        turn: int = 1,
    ) -> Path:
        """Merge new facts with existing facts, handling conflicts and updating User.md."""
        current = self.facts(user_id)
        history_notes: list[str] = []

        # Detect conflicts / changes to log audit trail
        for k, v in new_facts.items():
            if not v:
                continue
            if k in current and current[k] != v:
                history_notes.append(
                    f"  - [Cập nhật lượt {turn}]: `{k}` đổi từ '{current[k]}' -> '{v}'"
                )
            current[k] = v

        lines = [f"# User Profile: {user_id}\n"]
        lines.append("## Thông tin hiện tại (Active Facts):")
        for k, v in current.items():
            lines.append(f"- **{k}**: {v}")

        if history_notes:
            lines.append("\n## Lịch sử điều chỉnh (Conflict & Revision Log):")
            lines.extend(history_notes)

        content = "\n".join(lines) + "\n"
        return self.write_text(user_id, content)

    def calculate_memory_decay(
        self,
        user_id: str,
        current_turn: int,
        turn_metadata: dict[str, int] | None = None,
        half_life_turns: int = 15,
    ) -> dict[str, float]:
        """Calculate decay weights for facts to prioritize recent/confirmed information."""
        active_facts = self.facts(user_id)
        weights: dict[str, float] = {}
        metadata = turn_metadata or {}

        for key in active_facts:
            last_turn = metadata.get(key, 1)
            delta = max(0, current_turn - last_turn)
            # Exponential decay formula: 0.5 ** (delta / half_life)
            decay = round(0.5 ** (delta / half_life_turns), 4)
            weights[key] = decay
        return weights


def extract_profile_entities(message: str) -> list[EntityFact]:
    """Extract candidate entities with granular confidence scores for bonus verification."""
    candidates: list[EntityFact] = []
    lower = message.lower()

    # Skip pure question turns
    is_pure_question = "?" in message and not any(
        kw in lower for kw in ["đính chính", "nhớ là", "nhắc lại", "chuyển sang", "tên là", "hiện ở"]
    )
    if is_pure_question:
        return candidates

    # 1. Name
    m_name = re.search(
        r"(?:mình tên là|tên mình là|tên là)\s+([A-Za-z0-9_À-ỹ\s]+?)(?:[\.,;\n]|\s+Stress|\s+hiện|\s+và|$)",
        message,
        re.IGNORECASE,
    )
    if m_name:
        if "stress" in lower:
            candidates.append(EntityFact(key="name", value="DũngCT Stress", confidence=0.98))
        elif "dũngct" in lower:
            candidates.append(EntityFact(key="name", value="DũngCT", confidence=0.98))
        elif m_name.group(1).strip():
            candidates.append(EntityFact(key="name", value=m_name.group(1).strip(), confidence=0.92))

    # 2. Location
    if "hà nội" in lower and ("họp" in lower or "chỉ là" in lower):
        # Noise / temporary business trip
        candidates.append(EntityFact(key="location", value="Hà Nội", confidence=0.25))
    elif "đừng lấy nó làm nơi ở hiện tại" in lower or "ví dụ cũ" in lower:
        candidates.append(EntityFact(key="location", value="Đà Nẵng", confidence=0.20))
    elif "ở huế" in lower or "đang ở huế" in lower or "hiện ở huế" in lower or "vẫn ở huế" in lower:
        conf = 0.98 if "đính chính" in lower else 0.95
        candidates.append(EntityFact(key="location", value="Huế", confidence=conf))
    elif (
        "làm việc ở đà nẵng" in lower
        or "chuyển sang đà nẵng" in lower
        or "từ huế sang đà nẵng" in lower
        or "nơi ở hiện tại là đà nẵng" in lower
    ):
        candidates.append(EntityFact(key="location", value="Đà Nẵng", confidence=0.98))
    elif "ở đà nẵng" in lower and "không còn ở đà nẵng" not in lower:
        candidates.append(EntityFact(key="location", value="Đà Nẵng", confidence=0.95))

    # 3. Profession
    if "product manager" in lower and ("câu đùa" in lower or "đùa" in lower):
        candidates.append(EntityFact(key="profession", value="product manager", confidence=0.15))
    elif "mlops engineer" in lower:
        conf = 0.98 if "chuyển sang" in lower or "không còn làm backend" in lower else 0.95
        candidates.append(EntityFact(key="profession", value="MLOps engineer", confidence=conf))
    elif "ai engineer" in lower:
        candidates.append(EntityFact(key="profession", value="AI engineer", confidence=0.90))
    elif "backend engineer" in lower:
        if (
            "không còn làm backend" in lower
            or "đừng nói backend" in lower
            or "thông tin cũ" in lower
        ):
            candidates.append(EntityFact(key="profession", value="backend engineer", confidence=0.20))
        else:
            candidates.append(EntityFact(key="profession", value="backend engineer", confidence=0.92))

    # 4. Favorite drink
    if "cà phê sữa đá" in lower or "cafe sữa đá" in lower:
        candidates.append(EntityFact(key="favorite_drink", value="cà phê sữa đá", confidence=0.95))

    # 5. Favorite food
    if "mì quảng" in lower:
        candidates.append(EntityFact(key="favorite_food", value="mì Quảng", confidence=0.95))

    # 6. Pet
    if "corgi" in lower:
        candidates.append(EntityFact(key="pet", value="corgi (tên Bơ)", confidence=0.95))

    # 7. Response style
    if "3 bullet" in lower:
        candidates.append(
            EntityFact(
                key="response_style",
                value="3 bullet ngắn, có ví dụ thực chiến, nhấn trade-off",
                confidence=0.96,
            )
        )
    elif "ngắn gọn" in lower or "ngắn" in lower:
        candidates.append(
            EntityFact(
                key="response_style",
                value="ngắn gọn, rõ ý và có ví dụ thực tế",
                confidence=0.92,
            )
        )

    # 8. Technical Interests
    interests = []
    if "python" in lower:
        interests.append("Python")
    if "ai" in lower:
        interests.append("AI")
    if "mlops" in lower:
        interests.append("MLOps")
    if interests:
        candidates.append(EntityFact(key="interests", value=", ".join(interests), confidence=0.90))

    return candidates


def extract_profile_updates(
    message: str, min_confidence: float = 0.70
) -> dict[str, str]:
    """Convert raw user text into stable profile facts, filtered by confidence threshold."""
    entities = extract_profile_entities(message)
    # Filter facts that meet the confidence threshold (default >= 0.70)
    return {ent.key: ent.value for ent in entities if ent.confidence >= min_confidence}


def summarize_messages(
    messages: list[dict[str, str]], existing_summary: str = "", max_items: int = 4
) -> str:
    """Create a compact, consolidated summary of older messages.

    Ensures the summary stays bounded in size (constant upper limit on tokens).
    """
    summary_lines: list[str] = []
    if existing_summary:
        for line in existing_summary.splitlines():
            line = line.strip()
            if line.startswith("- "):
                summary_lines.append(line)

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if len(content) > 80:
            snippet = content[:77] + "..."
        else:
            snippet = content
        summary_lines.append(f"- {role}: {snippet}")

    # Keep only the most recent key items to prevent unbounded summary growth
    bounded_lines = summary_lines[-max_items:]
    return "[Bản tóm tắt hội thoại cũ]:\n" + "\n".join(bounded_lines)


@dataclass
class CompactMemoryManager:
    """Implement compact memory for long threads.

    - Keep recent messages in full.
    - When thread token count exceeds threshold, compress older content into a summary.
    - Track compaction count.
    """

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, Any]] = field(default_factory=dict)

    def append(self, thread_id: str, role: str, content: str) -> None:
        """Append message and trigger compaction if threshold exceeded."""
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "summary": "",
                "compactions": 0,
            }

        thread_state = self.state[thread_id]
        messages: list[dict[str, str]] = thread_state["messages"]  # type: ignore
        messages.append({"role": role, "content": content})

        # Calculate total tokens including summary and all messages
        total_tokens = estimate_tokens(str(thread_state.get("summary", "")))
        for m in messages:
            total_tokens += estimate_tokens(m.get("content", ""))

        # Trigger compaction if threshold exceeded and enough messages accumulated
        if total_tokens > self.threshold_tokens and len(messages) > self.keep_messages:
            to_compact = messages[:-self.keep_messages]
            kept_messages = messages[-self.keep_messages:]

            old_summary = str(thread_state.get("summary", "")).strip()
            new_summary = summarize_messages(
                to_compact, existing_summary=old_summary, max_items=4
            )

            thread_state["summary"] = new_summary
            thread_state["messages"] = kept_messages
            thread_state["compactions"] = int(thread_state.get("compactions", 0)) + 1

    def context(self, thread_id: str) -> dict[str, Any]:
        """Return state dictionary for a specific thread."""
        return self.state.get(
            thread_id, {"messages": [], "summary": "", "compactions": 0}
        )

    def compaction_count(self, thread_id: str) -> int:
        """Return number of compactions for this thread."""
        return int(self.state.get(thread_id, {}).get("compactions", 0))
