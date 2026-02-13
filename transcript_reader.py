#!/usr/bin/env python3
"""
transcript_reader — reads Claude Code's native JSONL session transcripts.

Parses the JSONL files at ~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl
and returns structured turn data for reflection analysis.

No data duplication — reads the source of truth on-demand.
"""

import json
import re
import statistics
import string
import sys
from datetime import datetime, timezone
from pathlib import Path


# --- Constants for linguistic analysis ---

STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "not", "no", "so",
    "if", "then", "than", "too", "very", "just", "about", "up", "out",
    "all", "also", "as", "into", "like", "through", "after", "before",
    "between", "each", "more", "some", "such", "only", "other", "new",
    "when", "what", "which", "where", "who", "how", "i", "me", "my",
    "we", "our", "you", "your", "he", "she", "they", "them", "its",
    "been", "being", "am", "were", "here", "there",
})

IMPERATIVE_VERBS = frozenset({
    "fix", "add", "make", "create", "update", "change", "remove", "delete",
    "write", "read", "show", "run", "build", "implement", "move", "rename",
    "refactor", "test", "check", "find", "search", "look", "use", "try",
    "set", "get", "put", "install", "deploy", "push", "pull", "merge",
    "revert", "undo", "do", "go", "stop", "start", "open", "close",
    "list", "print", "log", "debug", "explain", "describe", "summarize",
    "analyze", "compare", "review", "clean", "format", "sort", "filter",
    "group", "split", "join", "combine", "convert", "extract", "parse",
    "validate", "verify", "ensure", "handle", "catch", "throw", "raise",
    "return", "pass", "call", "invoke", "apply", "map", "reduce", "wrap",
    "unwrap", "flatten", "copy", "clone", "extend", "import", "export",
    "require", "include", "load", "save", "store", "fetch", "send",
    "post", "patch",
})

HEDGING_PHRASES = [
    "maybe", "perhaps", "i think", "not sure", "what if", "could we", "might",
]

ASSERTIVE_PHRASES = [
    "must", "always", "definitely", "need to", "should", "have to",
    "make sure", "ensure",
]


def get_transcript_dir(cwd: str) -> Path:
    """Convert a working directory path to the native JSONL directory.

    Claude Code stores transcripts at:
      ~/.claude/projects/{cwd with / replaced by -}/{sessionId}.jsonl
    """
    encoded = cwd.rstrip("/").replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded


def _read_jsonl(path: Path) -> list[dict]:
    """Read all entries from a JSONL file, skipping corrupt lines."""
    entries = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _get_first_timestamp(path: Path) -> str:
    """Get the timestamp of the first entry in a JSONL file."""
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")
                    if ts:
                        return ts
                except json.JSONDecodeError:
                    continue
    return ""


def find_sessions(cwd: str, since=None, transcript_dir=None) -> list:
    """Find session JSONL files, optionally filtered by timestamp.

    Args:
        cwd: Project working directory
        since: ISO timestamp string — only return sessions with entries after this
        transcript_dir: Override directory (for testing)

    Returns:
        List of Path objects sorted by first entry timestamp (oldest first)
    """
    if transcript_dir is None:
        transcript_dir = get_transcript_dir(cwd)

    if not transcript_dir.exists():
        return []

    sessions = []
    for path in transcript_dir.iterdir():
        if not path.is_file() or path.suffix != ".jsonl":
            continue

        first_ts = _get_first_timestamp(path)
        if since and first_ts:
            # Check if the session has any entries after `since`
            # We use the first entry timestamp as a rough filter.
            # Sessions starting before `since` might still have entries after it,
            # so we include them and filter turns later.
            # Only skip sessions whose LAST entry is before `since`.
            entries = _read_jsonl(path)
            last_ts = ""
            for entry in reversed(entries):
                if entry.get("timestamp"):
                    last_ts = entry["timestamp"]
                    break
            if last_ts and last_ts < since:
                continue

        sessions.append((first_ts, path))

    sessions.sort(key=lambda x: x[0])
    return [path for _, path in sessions]


def _extract_user_prompt_text(content):
    """Extract text from user message content (string or structured list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    continue
                elif block.get("type") == "image":
                    parts.append("[image]")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts) if parts else ""
    return ""


def _is_real_user_prompt(entry):
    """Check if a user entry is a real prompt (not just tool results)."""
    content = entry.get("message", {}).get("content", "")
    if isinstance(content, str) and content.strip():
        return True
    if isinstance(content, list):
        return any(
            (isinstance(b, dict) and b.get("type") != "tool_result")
            or isinstance(b, str)
            for b in content
        )
    return False


def _summarize_tool_input(tool_name, tool_input):
    """Create a brief summary of a tool call input."""
    if tool_name == "Bash":
        return tool_input.get("command", "")[:200]
    elif tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "")
    elif tool_name in ("Grep", "Glob"):
        return f"pattern={tool_input.get('pattern', '')}"
    elif tool_name == "WebSearch":
        return tool_input.get("query", "")
    elif tool_name == "WebFetch":
        return tool_input.get("url", "")
    elif tool_name == "Task":
        return tool_input.get("prompt", "")[:200]
    return str(tool_input)[:200]


def _extract_files(tool_name, tool_input):
    """Extract file paths touched by a tool call."""
    if tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "")
    elif tool_name in ("Glob", "Grep"):
        return tool_input.get("path", "")
    return ""


def parse_session(path) -> dict:
    """Parse a native JSONL session file into structured turns.

    Returns dict with session_id, model, version, git_branch, and turns list.
    Each turn has prompt, response, tools, blocks, metrics, and timestamp.
    """
    path = Path(path)
    entries = _read_jsonl(path)

    session_id = ""
    model = ""
    version = ""
    git_branch = ""
    turns = []

    # Extract session metadata from first entries
    for entry in entries:
        if not session_id and entry.get("sessionId"):
            session_id = entry["sessionId"]
        if not version and entry.get("version"):
            version = entry["version"]
        if not git_branch and entry.get("gitBranch"):
            git_branch = entry["gitBranch"]
        if session_id and version and git_branch:
            break

    # Split entries into turns.
    # A turn starts at each "real user prompt" and includes all subsequent
    # assistant entries and tool-result user entries until the next real prompt.
    turn_starts = []
    for i, entry in enumerate(entries):
        if entry.get("type") == "user" and _is_real_user_prompt(entry):
            turn_starts.append(i)

    for t_idx, start_idx in enumerate(turn_starts):
        end_idx = turn_starts[t_idx + 1] if t_idx + 1 < len(turn_starts) else len(entries)

        user_entry = entries[start_idx]
        prompt_text = _extract_user_prompt_text(
            user_entry.get("message", {}).get("content", "")
        )
        turn_timestamp = user_entry.get("timestamp", "")

        response_texts = []
        tools = []
        blocks = []
        seq = 0
        last_tool_name = ""

        # Token/metric accumulators
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_creation = 0
        turn_model = ""
        stop_reason = ""

        for i in range(start_idx + 1, end_idx):
            entry = entries[i]
            entry_type = entry.get("type")

            if entry_type == "assistant":
                msg = entry.get("message", {})
                content = msg.get("content", [])

                # Extract model from first assistant entry
                if not turn_model and msg.get("model"):
                    turn_model = msg["model"]

                # Accumulate token usage
                usage = msg.get("usage", {})
                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)
                total_cache_read += usage.get("cache_read_input_tokens", 0)
                total_cache_creation += usage.get("cache_creation_input_tokens", 0)

                # Update stop_reason (last assistant entry wins)
                if msg.get("stop_reason"):
                    stop_reason = msg["stop_reason"]

                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            response_texts.append(text)
                            blocks.append({
                                "sequence": seq, "type": "text",
                                "content": text, "tool_name": None,
                            })
                            seq += 1

                    elif block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        last_tool_name = tool_name
                        tools.append({
                            "tool_name": tool_name,
                            "input_summary": _summarize_tool_input(tool_name, tool_input),
                            "files_touched": _extract_files(tool_name, tool_input),
                            "is_subagent": tool_name == "Task",
                        })
                        blocks.append({
                            "sequence": seq, "type": "tool_use",
                            "content": _summarize_tool_input(tool_name, tool_input),
                            "tool_name": tool_name,
                        })
                        seq += 1

            elif entry_type == "user":
                # Tool result cycle
                content = entry.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            result_content = block.get("content", "")
                            if isinstance(result_content, str):
                                result_text = result_content[:500]
                            else:
                                result_text = str(result_content)[:500]
                            blocks.append({
                                "sequence": seq, "type": "tool_result",
                                "content": result_text,
                                "tool_name": last_tool_name,
                            })
                            seq += 1

        # Set session-level model from first turn
        if turn_model and not model:
            model = turn_model

        # Synthesize response for tool-only turns
        response = "\n\n".join(response_texts)
        if not response and tools:
            tool_names = ", ".join(t["tool_name"] for t in tools)
            response = f"[tool-only turn: {tool_names}]"

        if not response and not tools:
            continue  # Skip turns with nothing

        turns.append({
            "prompt": prompt_text,
            "response": response,
            "tools": tools,
            "blocks": blocks,
            "metrics": {
                "model": turn_model,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cache_read_tokens": total_cache_read,
                "cache_creation_tokens": total_cache_creation,
                "stop_reason": stop_reason,
            },
            "timestamp": turn_timestamp,
            "session_id": session_id,
        })

    return {
        "session_id": session_id,
        "model": model,
        "version": version,
        "git_branch": git_branch,
        "turns": turns,
    }


def get_turns_since(cwd: str, since_timestamp: str, transcript_dir=None) -> dict:
    """Get all turns across all sessions since a timestamp.

    Single entry point for /reflect. Returns everything needed for analysis.
    """
    sessions = find_sessions(cwd, since=since_timestamp, transcript_dir=transcript_dir)

    all_turns = []
    session_summaries = []
    tool_counts = {}
    subagent_count = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0

    for session_path in sessions:
        parsed = parse_session(session_path)

        # Filter turns by timestamp
        filtered_turns = []
        for turn in parsed["turns"]:
            if turn["timestamp"] >= since_timestamp:
                filtered_turns.append(turn)

        if not filtered_turns:
            continue

        all_turns.extend(filtered_turns)
        session_summaries.append({
            "session_id": parsed["session_id"],
            "model": parsed["model"],
            "version": parsed["version"],
            "git_branch": parsed["git_branch"],
            "turn_count": len(filtered_turns),
        })

        for turn in filtered_turns:
            for tool in turn["tools"]:
                name = tool["tool_name"]
                tool_counts[name] = tool_counts.get(name, 0) + 1
                if tool["is_subagent"]:
                    subagent_count += 1

            metrics = turn["metrics"]
            total_input += metrics["input_tokens"]
            total_output += metrics["output_tokens"]
            total_cache_read += metrics["cache_read_tokens"]
            total_cache_creation += metrics["cache_creation_tokens"]

    return {
        "turns": all_turns,
        "turn_count": len(all_turns),
        "tool_stats": {
            "total": sum(tool_counts.values()),
            "by_tool": tool_counts,
            "subagent_count": subagent_count,
        },
        "token_stats": {
            "total_input": total_input,
            "total_output": total_output,
            "total_cache_read": total_cache_read,
            "total_cache_creation": total_cache_creation,
        },
        "sessions": session_summaries,
    }


# --- Linguistic Analysis ---

def _word_count(text):
    """Count words in a string."""
    return len(text.split())


def _strip_punctuation(word):
    """Strip leading/trailing punctuation from a word."""
    return word.strip(string.punctuation)


def _extract_ngrams(text, n):
    """Extract n-grams from text, filtering stop-word-only n-grams.

    Returns dict of {ngram_string: count}.
    """
    words = [_strip_punctuation(w) for w in text.lower().split()]
    words = [w for w in words if w]  # remove empty after stripping
    counts = {}
    for i in range(len(words) - n + 1):
        gram = words[i:i + n]
        if all(w in STOP_WORDS for w in gram):
            continue
        key = " ".join(gram)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_phrase_occurrences(text, phrases):
    """Count occurrences of each phrase in text (case-insensitive).

    Returns dict of {phrase: count}.
    """
    lower = text.lower()
    return {phrase: lower.count(phrase) for phrase in phrases}


def compute_prompt_linguistics(turns):
    """Compute quantitative linguistic features across user prompts.

    Args:
        turns: List of turn dicts (from parse_session or get_turns_since).

    Returns:
        Dict with question_ratio, imperative_ratio, prompt_length,
        frequent_ngrams, certainty_markers, agency_framing,
        prompt_length_by_position.
    """
    # Filter to non-empty prompts
    prompts = [t["prompt"] for t in turns if t["prompt"].strip()]

    # Empty result structure
    empty = {
        "question_ratio": 0.0,
        "imperative_ratio": 0.0,
        "prompt_length": {
            "median": 0.0, "mean": 0.0, "min": 0, "max": 0,
            "stddev": 0.0, "count": 0,
        },
        "frequent_ngrams": {"bigrams": [], "trigrams": []},
        "certainty_markers": {
            "hedging_count": 0, "assertive_count": 0, "ratio": None,
            "hedging_phrases": {p: 0 for p in HEDGING_PHRASES},
            "assertive_phrases": {p: 0 for p in ASSERTIVE_PHRASES},
        },
        "agency_framing": {
            "i_count": 0, "we_count": 0, "you_count": 0, "lets_count": 0,
            "dominant": "none",
        },
        "prompt_length_by_position": {
            "first_quarter_avg": 0.0, "middle_half_avg": 0.0,
            "last_quarter_avg": 0.0,
        },
    }

    if not prompts:
        return empty

    count = len(prompts)

    # Question ratio
    questions = sum(1 for p in prompts if "?" in p)
    question_ratio = questions / count

    # Imperative ratio
    imperatives = sum(
        1 for p in prompts
        if p.split()[0].lower().strip(string.punctuation) in IMPERATIVE_VERBS
    )
    imperative_ratio = imperatives / count

    # Prompt length distribution
    word_counts = [_word_count(p) for p in prompts]
    median_wc = statistics.median(word_counts)
    mean_wc = statistics.mean(word_counts)
    stddev_wc = statistics.stdev(word_counts) if len(word_counts) >= 2 else 0.0

    # Frequent n-grams (aggregate across all prompts)
    bigram_counts = {}
    trigram_counts = {}
    for p in prompts:
        for gram, c in _extract_ngrams(p, 2).items():
            bigram_counts[gram] = bigram_counts.get(gram, 0) + c
        for gram, c in _extract_ngrams(p, 3).items():
            trigram_counts[gram] = trigram_counts.get(gram, 0) + c

    top_bigrams = sorted(bigram_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    top_trigrams = sorted(trigram_counts.items(), key=lambda x: x[1], reverse=True)[:15]

    # Certainty markers
    hedging_totals = {p: 0 for p in HEDGING_PHRASES}
    assertive_totals = {p: 0 for p in ASSERTIVE_PHRASES}
    for prompt in prompts:
        for phrase, c in _count_phrase_occurrences(prompt, HEDGING_PHRASES).items():
            hedging_totals[phrase] += c
        for phrase, c in _count_phrase_occurrences(prompt, ASSERTIVE_PHRASES).items():
            assertive_totals[phrase] += c
    hedging_count = sum(hedging_totals.values())
    assertive_count = sum(assertive_totals.values())
    certainty_ratio = (assertive_count / hedging_count) if hedging_count > 0 else None

    # Agency framing
    i_count = sum(len(re.findall(r"\bi (want|need|think)\b", p.lower())) for p in prompts)
    we_count = sum(len(re.findall(r"\bwe (should|could|need)\b", p.lower())) for p in prompts)
    you_count = sum(len(re.findall(r"\byou (should|can|need)\b", p.lower())) for p in prompts)
    lets_count = sum(len(re.findall(r"\blet'?s\b", p.lower())) for p in prompts)
    agency = {"i": i_count, "we": we_count, "you": you_count, "lets": lets_count}
    max_agency = max(agency.values())
    dominant = "none" if max_agency == 0 else max(agency, key=agency.get)

    # Prompt length by position
    q1_end = max(1, count // 4)
    q3_start = count - max(1, count // 4)
    first_quarter = word_counts[:q1_end]
    middle_half = word_counts[q1_end:q3_start] if q1_end < q3_start else word_counts
    last_quarter = word_counts[q3_start:]

    return {
        "question_ratio": question_ratio,
        "imperative_ratio": imperative_ratio,
        "prompt_length": {
            "median": median_wc,
            "mean": mean_wc,
            "min": min(word_counts),
            "max": max(word_counts),
            "stddev": stddev_wc,
            "count": count,
        },
        "frequent_ngrams": {
            "bigrams": [{"ngram": g, "count": c} for g, c in top_bigrams],
            "trigrams": [{"ngram": g, "count": c} for g, c in top_trigrams],
        },
        "certainty_markers": {
            "hedging_count": hedging_count,
            "assertive_count": assertive_count,
            "ratio": certainty_ratio,
            "hedging_phrases": hedging_totals,
            "assertive_phrases": assertive_totals,
        },
        "agency_framing": {
            "i_count": i_count,
            "we_count": we_count,
            "you_count": you_count,
            "lets_count": lets_count,
            "dominant": dominant,
        },
        "prompt_length_by_position": {
            "first_quarter_avg": statistics.mean(first_quarter),
            "middle_half_avg": statistics.mean(middle_half),
            "last_quarter_avg": statistics.mean(last_quarter),
        },
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: transcript_reader.py <command> <cwd> [since_timestamp]")
        print("Commands: analyze, sessions, stats")
        sys.exit(1)

    command = sys.argv[1]
    cwd = sys.argv[2]

    if command == "analyze":
        since = sys.argv[3] if len(sys.argv) > 3 else ""
        result = get_turns_since(cwd, since)
        print(json.dumps(result, indent=2))
    elif command == "sessions":
        sessions = find_sessions(cwd)
        result = []
        for path in sessions:
            parsed = parse_session(path)
            result.append({
                "session_id": parsed["session_id"],
                "model": parsed["model"],
                "version": parsed["version"],
                "git_branch": parsed["git_branch"],
                "turn_count": len(parsed["turns"]),
                "path": str(path),
            })
        print(json.dumps(result, indent=2))
    elif command == "stats":
        since = sys.argv[3] if len(sys.argv) > 3 else ""
        result = get_turns_since(cwd, since)
        print(json.dumps({
            "turn_count": result["turn_count"],
            "tool_stats": result["tool_stats"],
            "token_stats": result["token_stats"],
            "session_count": len(result["sessions"]),
        }, indent=2))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
