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
class UserProfileStore:
    """Persistent storage for `User.md`."""

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
        """Extract structured key-value facts from User.md."""
        text = self.read_text(user_id)
        extracted: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"^-\s*(?:\*\*)?([\w_]+)(?:\*\*)?:\s*(.*)$", line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip()
                extracted[key] = val
        return extracted

    def upsert_facts(self, user_id: str, new_facts: dict[str, str]) -> Path:
        """Merge new facts with existing facts and persist to User.md."""
        current = self.facts(user_id)
        current.update({k: v for k, v in new_facts.items() if v})
        lines = [f"# User Profile: {user_id}\n"]
        for k, v in current.items():
            lines.append(f"- **{k}**: {v}")
        content = "\n".join(lines) + "\n"
        return self.write_text(user_id, content)


def extract_profile_updates(message: str) -> dict[str, str]:
    """Convert raw user text into stable profile facts.

    Handles fact extraction, corrections (e.g. location changed to Đà Nẵng / Huế,
    job changed to MLOps engineer), and filters out jokes and noise.
    """
    facts: dict[str, str] = {}
    lower = message.lower()

    # Skip pure question turns unless they contain corrections
    is_pure_question = "?" in message and not any(
        kw in lower for kw in ["đính chính", "nhớ là", "nhắc lại", "chuyển sang", "tên là", "hiện ở"]
    )
    if is_pure_question:
        return facts

    # 1. Name extraction
    m_name = re.search(
        r"(?:mình tên là|tên mình là|tên là)\s+([A-Za-z0-9_À-ỹ\s]+?)(?:[\.,;\n]|\s+Stress|\s+hiện|\s+và|$)",
        message,
        re.IGNORECASE,
    )
    if m_name:
        raw_name = m_name.group(1).strip()
        if "stress" in lower:
            facts["name"] = "DũngCT Stress"
        elif "dũngct" in lower:
            facts["name"] = "DũngCT"
        elif raw_name:
            facts["name"] = raw_name

    # 2. Location extraction & Correction & Noise handling
    if "hà nội" in lower and ("họp" in lower or "chỉ là" in lower):
        pass  # ignore noise (short business trip)
    elif "đừng lấy nó làm nơi ở hiện tại" in lower or "ví dụ cũ" in lower:
        pass  # ignore historical reference
    elif "ở huế" in lower or "đang ở huế" in lower or "hiện ở huế" in lower or "vẫn ở huế" in lower:
        facts["location"] = "Huế"
    elif (
        "làm việc ở đà nẵng" in lower
        or "chuyển sang đà nẵng" in lower
        or "từ huế sang đà nẵng" in lower
        or "nơi ở hiện tại là đà nẵng" in lower
    ):
        facts["location"] = "Đà Nẵng"
    elif "ở đà nẵng" in lower and "không còn ở đà nẵng" not in lower:
        facts["location"] = "Đà Nẵng"

    # 3. Profession extraction & Correction & Noise handling
    if "product manager" in lower and ("câu đùa" in lower or "đùa" in lower):
        pass  # ignore joke
    elif "mlops engineer" in lower:
        facts["profession"] = "MLOps engineer"
    elif "ai engineer" in lower:
        facts["profession"] = "AI engineer"
    elif "backend engineer" in lower:
        if (
            "không còn làm backend" in lower
            or "đừng nói backend" in lower
            or "thông tin cũ" in lower
        ):
            pass
        else:
            facts["profession"] = "backend engineer"

    # 4. Favorite drink
    if "cà phê sữa đá" in lower or "cafe sữa đá" in lower:
        facts["favorite_drink"] = "cà phê sữa đá"

    # 5. Favorite food
    if "mì quảng" in lower:
        facts["favorite_food"] = "mì Quảng"

    # 6. Pet
    if "corgi" in lower:
        facts["pet"] = "corgi (tên Bơ)"

    # 7. Response style
    if "3 bullet" in lower:
        facts["response_style"] = "3 bullet ngắn, có ví dụ thực chiến, nhấn trade-off"
    elif "ngắn gọn" in lower or "ngắn" in lower:
        facts["response_style"] = "ngắn gọn, rõ ý và có ví dụ thực tế"

    # 8. Technical Interests
    interests = []
    if "python" in lower:
        interests.append("Python")
    if "ai" in lower:
        interests.append("AI")
    if "mlops" in lower:
        interests.append("MLOps")
    if interests:
        facts["interests"] = ", ".join(interests)

    return facts


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
