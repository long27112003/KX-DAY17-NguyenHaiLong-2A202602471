from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A: Baseline Agent.

    Requirements:
    - Within-session memory only (short-term thread state)
    - No persistent `User.md`
    - Forgets all long-term facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = self._maybe_build_langchain_agent() if not force_offline else None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Return the agent response and token accounting."""
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()
        session = self.sessions[thread_id]

        # Live LangChain execution if enabled and configured
        if self.langchain_agent is not None and not self.force_offline:
            try:
                from langchain_core.messages import AIMessage, HumanMessage

                history = []
                for m in session.messages:
                    if m["role"] == "user":
                        history.append(HumanMessage(content=m["content"]))
                    else:
                        history.append(AIMessage(content=m["content"]))
                history.append(HumanMessage(content=message))

                # Estimate prompt token load for all history + new message
                prompt_text = "\n".join(m["content"] for m in session.messages) + "\n" + message
                prompt_tokens = estimate_tokens(prompt_text)
                session.prompt_tokens_processed += prompt_tokens
                session.messages.append({"role": "user", "content": message})

                response = self.langchain_agent.invoke(history)
                reply_text = response.content if hasattr(response, "content") else str(response)

                out_tokens = estimate_tokens(reply_text)
                session.token_usage += out_tokens
                session.messages.append({"role": "assistant", "content": reply_text})

                return {
                    "reply": reply_text,
                    "tokens": out_tokens,
                    "prompt_tokens": prompt_tokens,
                }
            except Exception:
                # Fallback to offline on network/api error
                pass

        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str | None = None) -> int:
        """Return cumulative agent token count for one thread or all threads."""
        if thread_id is not None:
            return self.sessions.get(thread_id, SessionState()).token_usage
        return sum(s.token_usage for s in self.sessions.values())

    def prompt_token_usage(self, thread_id: str | None = None) -> int:
        """Estimate cumulative prompt context load processed for one thread or all threads."""
        if thread_id is not None:
            return self.sessions.get(thread_id, SessionState()).prompt_tokens_processed
        return sum(s.prompt_tokens_processed for s in self.sessions.values())

    def compaction_count(self, thread_id: str | None = None) -> int:
        """Baseline has no compact memory, always returns 0."""
        return 0

    def memory_file_size(self, user_id: str | None = None) -> int:
        """Baseline has no persistent memory file, always returns 0."""
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Implement deterministic offline baseline behavior.

        - Stores messages within current thread only.
        - Calculates prompt context load (growing quadratically on long threads).
        - Cannot recall any facts from other threads.
        """
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()
        session = self.sessions[thread_id]

        # Calculate prompt context load (all past messages in thread + current message)
        prompt_context = "\n".join(m["content"] for m in session.messages) + "\n" + message
        prompt_tokens = estimate_tokens(prompt_context)
        session.prompt_tokens_processed += prompt_tokens

        session.messages.append({"role": "user", "content": message})

        # Generate deterministic response
        # In a new thread (e.g. recall query), baseline has no past knowledge
        if len(session.messages) <= 1:
            reply_text = (
                "Chào bạn, tôi là trợ lý Baseline. Vì đây là phiên trò chuyện mới và tôi không "
                "lưu trữ thông tin cá nhân của bạn, tôi không nhớ tên, nghề nghiệp hay sở thích của bạn."
            )
        else:
            reply_text = (
                f"Ghi nhận phản hồi trong phiên chat {thread_id}. "
                f"Phiên này hiện có {len(session.messages)} lượt trao đổi."
            )

        out_tokens = estimate_tokens(reply_text)
        session.token_usage += out_tokens
        session.messages.append({"role": "assistant", "content": reply_text})

        return {
            "reply": reply_text,
            "tokens": out_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _maybe_build_langchain_agent(self):
        """Instantiate a chat model if API keys or provider config is available."""
        if self.force_offline:
            return None
        try:
            if not self.config.model.api_key and self.config.model.provider != "ollama":
                return None
            return build_chat_model(self.config.model)
        except Exception:
            return None
