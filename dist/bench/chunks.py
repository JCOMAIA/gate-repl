import os


FILES = ["loja_A.txt", "loja_B.txt", "taxas.txt"]


def load_chunks(workspace_dir: str, chunk_lines: int = 50) -> list[dict]:
    chunks = []
    for fn in FILES:
        path = os.path.join(workspace_dir, fn)
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        for i in range(0, len(lines), chunk_lines):
            text = "".join(lines[i : i + chunk_lines])
            chunks.append(
                {
                    "src": fn,
                    "start": i,
                    "end": i + chunk_lines,
                    "text": f"--- {fn} (linhas {i}-{i + chunk_lines}) ---\n{text}",
                }
            )
    return chunks
