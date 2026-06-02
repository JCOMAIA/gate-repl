import io
import os
import re
import sys
import traceback


_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*(.*?)\s*```", re.DOTALL)


def extract_code_blocks(text: str) -> list[str]:
    return _CODE_BLOCK.findall(text)


def run_code(code: str, workspace_dir: str, glb: dict | None = None) -> str:
    """Execute code in workspace_dir, optionally seeding the global namespace
    (e.g. with a `context` string the model should parse). stdout is captured."""
    cwd = os.getcwd()
    target = os.path.abspath(workspace_dir)
    os.chdir(target)
    buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = buf
    sys.stderr = buf
    namespace = {"__name__": "__main__"}
    if glb:
        namespace.update(glb)
    try:
        exec(code, namespace)
    except Exception:
        buf.write("\n" + traceback.format_exc())
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        os.chdir(cwd)
    out = buf.getvalue()
    if not out.strip():
        return "(no stdout)"
    if len(out) > 8000:
        out = out[:8000] + f"\n... [truncated {len(out) - 8000} chars]"
    return out
