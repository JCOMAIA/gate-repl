# bench/ — Fase A: ablation rigoroso

Refaz o experimento de `ablation_test.py` no mesmo harness para todos os 4 métodos,
com múltiplos trials, custos reais do OpenRouter e parser numérico contra
ground truth (não substring).

## Métodos avaliados

| ID | Método | O que muda |
| :--- | :--- | :--- |
| `m1_brute` | Brute-force: 3 arquivos no prompt | Linha de base de "context-stuffing" |
| `m2_bm25`  | Retrieval BM25 real (`rank_bm25`) | Substitui o Jaccard que o script antigo chamava de "BM25" |
| `m3_embed` | Retrieval por embedding (MiniLM-L6) | Substitui o Jaccard renomeado de "Semantic Vector" |
| `m4_rlm`   | Agente com REPL Python + harness loop-break | Mesma lógica do `rlmbdemo.py`, agora medida no mesmo runner |

## Setup

```powershell
# 1. instalar deps
pip install -r bench/requirements.txt

# 2. criar .env na raiz do projeto (rotacione a key antiga antes!)
Copy-Item .env.example .env
# edite .env e preencha OPENROUTER_API_KEY
```

O `bench/config.py` chama `load_dotenv()` automaticamente. Variáveis suportadas:
`OPENROUTER_API_KEY`, `BENCH_MODEL`, `BENCH_TRIALS`, `BENCH_TEMP`, `BENCH_MAX_TURNS`.

## Rodar

```powershell
python -m bench.runner          # roda 5 trials × 4 métodos, salva results/trials_<ts>.jsonl
python -m bench.report          # tabela média ± sd em Markdown
```

## Decisões de design

- **Temperature 0.0** para reduzir variância entre trials.
- **n=5 trials por método** por padrão. Reporta média ± desvio padrão populacional.
- **Sucesso = `abs(parsed - 70992) ≤ 0.01`**, não substring `"70992" in output`.
- **Custo via `/api/v1/models`** do OpenRouter (não constante arbitrária).
- **Mesmo cliente, mesma temperatura, mesmo modelo** em todos os 4 métodos — diferente
  do `ablation_test.py` original onde o RLM tinha métricas hard-coded no template.
- **`workspace/`** é regerado a cada execução (determinístico, mesmos arquivos sempre).

## O que ainda não é honesto / TODO Fase B

- Um único modelo por execução — ainda não cruzamos modelos.
- Uma única tarefa — ainda falta T2 (needle), T3 (regra condicional), T4 (anti-RLM).
- Sem variação de escala (1k linhas fixas).
- `repl.run_code` usa `exec()` direto, sem sandbox. OK para benchmark local, não para
  produção. Documentar como ameaça antes de empacotar como tool.
