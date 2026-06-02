import re

from ..client import ORClient
from ..pricing import cost_usd
from ..repl import extract_code_blocks, run_code


_CODE_BLOCK_RE = re.compile(r"```(?:python|py)?\s*.*?\s*```", re.DOTALL)


SYSTEM_PROMPT = (
    "You are an expert data analyst with access to a local file Workspace.\n"
    "The workspace contains: 'loja_A.txt', 'loja_B.txt', 'taxas.txt'.\n"
    "Write Python code wrapped in ```python ... ``` blocks. The stdout of print() "
    "statements will be returned to you. Do NOT echo file contents in your text.\n"
    "When you have the final numeric answer, output 'FINAL: <number>' and nothing else."
)


def run(client: ORClient, task: str, workspace_dir: str, max_turns: int = 10, **_) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}"},
    ]
    total_prompt = 0
    total_completion = 0
    total_elapsed = 0.0
    code_history: set[str] = set()
    last_output = ""
    last_error = ""
    turns_used = 0

    for turn in range(max_turns):
        turns_used = turn + 1
        r = client.chat(messages)
        total_elapsed += r.elapsed_s
        if not r.ok:
            last_error = r.error
            break
        total_prompt += r.prompt_tokens
        total_completion += r.completion_tokens
        last_output = r.content
        blocks = extract_code_blocks(r.content)

        # FINAL counts only when it appears OUTSIDE any code block — otherwise
        # 'FINAL:' inside `print(f'FINAL: ...')` would short-circuit the loop
        # before the REPL output ever returns to the model.
        text_outside_code = _CODE_BLOCK_RE.sub("", r.content)
        has_final_outside = "FINAL:" in text_outside_code

        if blocks:
            outputs = []
            for i, b in enumerate(blocks):
                if b in code_history:
                    outputs.append(f"--- Block {i + 1} ---\n(loop: same code already executed; try a different approach)")
                else:
                    code_history.add(b)
                    outputs.append(f"--- Block {i + 1} ---\n{run_code(b, workspace_dir)}")
            messages.append({"role": "assistant", "content": r.content})
            messages.append({"role": "user", "content": "REPL output:\n" + "\n\n".join(outputs)})
            continue

        if has_final_outside:
            messages.append({"role": "assistant", "content": r.content})
            break

        messages.append({"role": "assistant", "content": r.content})
        messages.append({
            "role": "user",
            "content": "Please write Python code in ```python blocks to inspect the files, or output 'FINAL: <number>' as plain text when you have the answer.",
        })

    return {
        "ok": "FINAL:" in last_output and not last_error,
        "output": last_output,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "elapsed_s": total_elapsed,
        "turns": turns_used,
        "cost_usd": cost_usd(client.model, total_prompt, total_completion),
        "error": last_error,
    }
