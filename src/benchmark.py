import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig, load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read JSON conversations from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def recall_points(answer: str, expected: list[str]) -> float:
    """Return 0 to 1 depending on fraction of expected facts present in answer."""
    if not expected:
        return 1.0
    ans_lower = answer.lower()
    matched = sum(1 for exp in expected if exp.lower() in ans_lower)
    return matched / len(expected)


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Compute a lightweight response quality score for offline evaluation."""
    rec = recall_points(answer, expected)
    score = rec * 0.6

    # Reward well-structured, concise formatting (bullets, line breaks)
    if "\n" in answer or "- " in answer or "•" in answer:
        score += 0.2
    if 30 <= len(answer) <= 1200:
        score += 0.2

    return round(min(1.0, score), 2)


def run_agent_benchmark(
    agent_name: str, agent: Any, conversations: list[dict[str, Any]], config: LabConfig
) -> BenchmarkRow:
    """Evaluate one agent over conversations."""
    # Reset/clean memory profiles for tested users to accurately track memory growth
    if hasattr(agent, "profile_store"):
        for conv in conversations:
            uid = conv.get("user_id")
            if uid:
                p = agent.profile_store.path_for(uid)
                if p.exists():
                    p.unlink()

    recall_scores: list[float] = []
    quality_scores: list[float] = []

    for conv in conversations:
        user_id = conv.get("user_id", "default_user")
        thread_id = conv.get("id", "thread-1")

        # 1. Feed conversation turns in current thread
        for turn in conv.get("turns", []):
            agent.reply(user_id=user_id, thread_id=thread_id, message=turn)

        # 2. Ask recall questions in a FRESH thread to measure cross-session memory
        recall_thread_id = f"{thread_id}-recall"
        for q_item in conv.get("recall_questions", []):
            question = q_item.get("question", "")
            expected = q_item.get("expected_contains", [])

            res = agent.reply(
                user_id=user_id, thread_id=recall_thread_id, message=question
            )
            answer = str(res.get("reply", ""))

            rec = recall_points(answer, expected)
            qual = heuristic_quality(answer, expected)
            recall_scores.append(rec)
            quality_scores.append(qual)

    # Calculate metrics
    avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0.0
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    # Calculate memory growth across all users in this benchmark
    total_mem_bytes = 0
    if hasattr(agent, "memory_file_size"):
        for conv in conversations:
            uid = conv.get("user_id")
            if uid:
                total_mem_bytes += agent.memory_file_size(uid)

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=agent.token_usage(),
        prompt_tokens_processed=agent.prompt_token_usage(),
        recall_score=round(avg_recall, 4),
        response_quality=round(avg_quality, 4),
        memory_growth_bytes=total_mem_bytes,
        compactions=agent.compaction_count(),
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Format benchmark rows as a clean Markdown table."""
    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth",
        "Compactions",
    ]
    table_data = []
    for r in rows:
        table_data.append(
            [
                r.agent_name,
                f"{r.agent_tokens_only:,}",
                f"{r.prompt_tokens_processed:,}",
                f"{r.recall_score * 100:.1f}%",
                f"{r.response_quality:.2f}",
                f"{r.memory_growth_bytes:,} B",
                str(r.compactions),
            ]
        )

    try:
        from tabulate import tabulate

        return tabulate(table_data, headers=headers, tablefmt="github")
    except ImportError:
        # Fallback manual markdown table
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        rows_lines = [
            "| " + " | ".join(row) + " |" for row in table_data
        ]
        return "\n".join([header_line, sep_line] + rows_lines)


def main() -> None:
    """Run both Standard Benchmark and Long-Context Stress Benchmark."""
    base_repo_dir = Path(__file__).resolve().parent.parent
    config = load_config(base_repo_dir)

    std_data_path = config.data_dir / "conversations.json"
    stress_data_path = config.data_dir / "advanced_long_context.json"

    print("Loading benchmark datasets...")
    std_convs = load_conversations(std_data_path)
    stress_convs = load_conversations(stress_data_path)
    print(f"- Standard dataset: {len(std_convs)} conversations loaded.")
    print(f"- Stress dataset: {len(stress_convs)} long-context conversations loaded.\n")

    # 1. Run Standard Benchmark
    print("Running Suite 1: Standard Benchmark...")
    baseline_std = BaselineAgent(config=config, force_offline=True)
    advanced_std = AdvancedAgent(config=config, force_offline=True)

    row_base_std = run_agent_benchmark(
        "Baseline Agent", baseline_std, std_convs, config
    )
    row_adv_std = run_agent_benchmark(
        "Advanced Agent", advanced_std, std_convs, config
    )

    print("\n" + "=" * 95)
    print("STANDARD BENCHMARK (data/conversations.json - 10 Conversations)")
    print("=" * 95)
    print(format_rows([row_base_std, row_adv_std]))
    print("=" * 95 + "\n")

    # 2. Run Long-Context Stress Benchmark
    print("Running Suite 2: Long-Context Stress Benchmark...")
    baseline_stress = BaselineAgent(config=config, force_offline=True)
    advanced_stress = AdvancedAgent(config=config, force_offline=True)

    row_base_stress = run_agent_benchmark(
        "Baseline Agent", baseline_stress, stress_convs, config
    )
    row_adv_stress = run_agent_benchmark(
        "Advanced Agent", advanced_stress, stress_convs, config
    )

    print("\n" + "=" * 95)
    print("LONG-CONTEXT STRESS BENCHMARK (data/advanced_long_context.json - 16 Long Turns)")
    print("=" * 95)
    print(format_rows([row_base_stress, row_adv_stress]))
    print("=" * 95 + "\n")


if __name__ == "__main__":
    main()
