import os


GROUND_TRUTH = 70992.0

TASK = (
    "Calcule o valor total de imposto cobrado (em R$) sobre as transacoes da Loja A "
    "com ID entre 200 e 250 (inclusive) somado ao imposto cobrado sobre as transacoes "
    "da Loja B com ID entre 400 e 450 (inclusive), utilizando as aliquotas especificadas "
    "em taxas.txt. Responda apenas com 'FINAL: [valor_total_imposto]'."
)


def generate(workspace_dir: str, n_lines: int = 1000) -> None:
    """Generate workspace files. The ground truth (70992.0) is invariant in
    `n_lines` as long as n_lines >= 451, since the relevant IDs (200-250 in
    loja_A, 400-450 in loja_B) and their values (i*15, i*22) don't depend
    on the file length — only the surrounding 'noise' grows."""
    if n_lines < 451:
        raise ValueError(f"n_lines must be >= 451 to keep ground truth valid (got {n_lines})")
    os.makedirs(workspace_dir, exist_ok=True)

    with open(os.path.join(workspace_dir, "loja_A.txt"), "w", encoding="utf-8") as f:
        for i in range(n_lines):
            f.write(f"ID_{i}: Venda de R$ {i * 15}\n")

    with open(os.path.join(workspace_dir, "loja_B.txt"), "w", encoding="utf-8") as f:
        for i in range(n_lines):
            f.write(f"ID_{i}: Venda de R$ {i * 22}\n")

    with open(os.path.join(workspace_dir, "taxas.txt"), "w", encoding="utf-8") as f:
        f.write(
            "POLITICA FISCAL DE TRIBUTACAO ANUAL (REGRAS):\n"
            "- Loja A: Transacoes com ID de 200 a 250 (inclusive) tem taxa de 8% (0.08).\n"
            "- Loja B: Transacoes com ID de 400 a 450 (inclusive) tem taxa de 12% (0.12).\n"
            "- Outros IDs ou Lojas: taxa padrao de 5% (0.05).\n"
        )
