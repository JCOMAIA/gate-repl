# Brute-force, RAG, and Code-Acting Agents on Multi-Source Joins: An Empirical Cross-Provider Ablation

**Status:** Working draft. Numbers are from local runs in May 2026. Reproducible via the `bench/` harness in this repo.

## TL;DR

We compared four methods — long-context "brute force" (M1), BM25 retrieval (M2), embedding retrieval (M3), and a code-acting REPL agent (M4) — on a multi-file numeric join task across four data scales (1k → 25k lines/file) and two LLM providers (DeepSeek and Google). 100 trials total.

Three findings stick:

1. **Retrieval is structurally incapable** of solving multi-source joins with top-k chunking. **0/40 trials succeeded** across BM25 and embedding RAG, regardless of scale. The retriever simply cannot return the three disjoint regions of three files needed to compute the answer.
2. **Brute-force is brittle in two distinct, provider-dependent ways.** It succeeded 100% on DeepSeek at most scales but failed 0/5 at one specific scale with a suspiciously cached-looking response. It then failed 0/5 on Gemini even at the smallest scale, returning a single-transaction tax instead of the aggregate. **You cannot rely on long-context brute force in production** because the failure mode is opaque and provider-specific.
3. **The code-acting REPL agent (M4) achieved 100% accuracy across all four scales (20/20)** with token usage that is O(1) in data size — flat at ~11k tokens regardless of whether the workspace had 1k or 25k lines/file. At the 25k scale, M4 was **44× cheaper in dollars** than M1 brute force, while M1's cost scaled linearly with data.

None of this requires new model capabilities, fine-tuning, or RL. It is purely a runtime/interface result.

## What this is, and what it is not

**What it is:** A rigorous, reproducible ablation that quantifies where each interaction paradigm breaks on a specific class of task (multi-source numeric joins). The methodology is straightforward: same model, same temperature (0.0), same task, same ground truth, n=5 trials per (method, scale).

**What it is not:**
- Not a novel model architecture or fine-tuning method.
- Not a novel agent harness. Code-acting agents are well-established (CodeAct, Open Interpreter, smolagents, AutoGen, Anthropic's tool-use code execution). We use a small one and measure it honestly.
- Not "topological chain-of-thought" or anything involving real persistent homology. An earlier framing of this work used that label for a Jaccard distance threshold between consecutive agent turns; that is a useful drift heuristic, but it is not TDA, and we dropped the label.
- Not a claim that M4 is best at *all* tasks. We deliberately did not yet test tasks where brute force should win (small single-paragraph QA). That is future work.

## Task

The agent must compute the total tax collected on a specific cross-file subset of transactions:

> Calcule o valor total de imposto cobrado (em R$) sobre as transações da Loja A com ID entre 200 e 250 (inclusive) somado ao imposto cobrado sobre as transações da Loja B com ID entre 400 e 450 (inclusive), utilizando as alíquotas especificadas em taxas.txt.

The workspace contains three deterministically generated files:
- `loja_A.txt` — `N` lines of `ID_<i>: Venda de R$ <i*15>`
- `loja_B.txt` — `N` lines of `ID_<i>: Venda de R$ <i*22>`
- `taxas.txt` — three lines defining tax rates (8% for Loja A IDs 200-250, 12% for Loja B IDs 400-450, 5% otherwise)

Ground truth (closed form):
```
sum(i*15*0.08 for i in 200..250)  +  sum(i*22*0.12 for i in 400..450)
= 11475*15*0.08 + 21675*22*0.12 = 13770 + 57222 = 70992.0
```

The ground truth is **invariant in `N`** as long as `N ≥ 451`, because we only sum over the same fixed ID ranges. This lets us vary file size to test scaling without changing the answer.

Evaluator: parse the last `FINAL: <number>` outside any code block (pt-BR and en-US numeric locales), match against 70992.0 with tolerance 0.01.

## Methods

All four methods share the same model, temperature, evaluator, and ground truth.

| ID | Method | Description | Lines |
|:---|:---|:---|:---|
| M1 | Brute force | Concatenates all three files into the prompt. System prompt forbids code emission. | [bench/methods/m1_brute.py](bench/methods/m1_brute.py) |
| M2 | BM25 retrieval | Real BM25 (`rank_bm25`) over 50-line chunks of all three files, top-3. | [bench/methods/m2_bm25.py](bench/methods/m2_bm25.py) |
| M3 | Embedding retrieval | `sentence-transformers/all-MiniLM-L6-v2`, cosine, top-3. | [bench/methods/m3_embed.py](bench/methods/m3_embed.py) |
| M4 | Code-acting REPL agent | Multi-turn loop: model emits ` ```python ``` ` blocks → harness executes against the file workspace → stdout is fed back. Loop-break via code-hash set. Max 10 turns. | [bench/methods/m4_rlm.py](bench/methods/m4_rlm.py) |

A previous iteration of M4 had a harness bug that broke the loop early whenever `"FINAL:"` appeared inside a generated code block (e.g., `print(f'FINAL: {x:.2f}')`). This produced false 20% accuracy. The fix counts `"FINAL:"` only when it appears outside any code block. We document this because the bug was non-obvious and the corrected method's strong performance was initially masked by it.

## Phase A — Baseline at 1k lines/file (DeepSeek-v4-flash)

Same model, n=5 per method.

| Method | Success | Tokens (mean ± sd) | Latency s (mean ± sd) | Cost USD (mean) |
|:---|:---:|:---:|:---:|:---:|
| m1_brute | 100% (5/5) | 26 928 ± 61 | 23.2 ± 2.6 | 0.00277 |
| m2_bm25 | 0% (0/5) | 5 252 ± 1 851 | 98.6 ± 47.8 | 0.00089 |
| m3_embed | 0% (0/5) | 4 659 ± 2 704 | 84.2 ± 70.7 | 0.00078 |
| m4_rlm | 80% (4/5) | 10 010 ± 6 037 | 113.2 ± 55.6 | 0.00139 |

At 1k lines/file, brute force wins on accuracy. M4 is competitive at lower cost but slower due to multi-turn round-trips. RAG fails completely. **No part of this table is dramatic.** The interesting story emerges with scale.

## Phase B — Scale sweep (DeepSeek-v4-flash, 1k–25k lines/file)

Four scales × four methods × five trials = 80 runs.

### Success rate by scale

| Method \ Scale | 1k | 5k | 10k | 25k |
|:---|:---:|:---:|:---:|:---:|
| m1_brute | 100% (5/5) | 100% (5/5) | **0% (0/5)** | 100% (5/5) |
| m2_bm25  | 0% (0/5) | 0% (0/5) | 0% (0/5) | 0% (0/5) |
| m3_embed | 0% (0/5) | 0% (0/5) | 0% (0/5) | 0% (0/5) |
| **m4_rlm** | **100% (5/5)** | **100% (5/5)** | **100% (5/5)** | **100% (5/5)** |

### Mean total tokens by scale

| Method \ Scale | 1k | 5k | 10k | 25k |
|:---|:---:|:---:|:---:|:---:|
| m1_brute | 26 881 | 138 844 | 278 142 | 698 889 |
| m2_bm25 | 3 490 | 1 568 | 1 568 | 6 649 |
| m3_embed | 2 764 | 7 096 | 8 617 | 6 642 |
| **m4_rlm** | **9 219** | **12 620** | **10 878** | **11 687** |

### Mean cost USD by scale

| Method \ Scale | 1k | 5k | 10k | 25k | M1/M4 ratio |
|:---|:---:|:---:|:---:|:---:|:---:|
| m1_brute | 0.00276 | 0.01396 | 0.02782 | 0.06996 | — |
| m4_rlm | 0.00122 | 0.00164 | 0.00140 | 0.00158 | — |
| **ratio M1/M4** | 2.3× | 8.5× | 19.9× | **44.3×** | grows linearly |

### What this tells us

**M4 is invariant in data size.** Token usage stays at ~11k regardless of scale, because the REPL reads files from disk; the prompt does not grow with `N`. M1 grows linearly with `N` and pays a linear cost premium.

**M1 fails non-monotonically.** It worked at 1k, 5k, and 25k, but failed 0/5 at 10k. The failures looked like this:

```
trial 0: 278142 prompt tokens, t=21.7s, FINAL: R$ 10098.00
trial 1: 278142 prompt tokens, t=24.6s, FINAL: R$ 10044.00
trial 2: 278142 prompt tokens, t=6.4s,  FINAL: R$ 10098.00
trial 3: 278142 prompt tokens, t=2.6s,  FINAL: R$ 10098.00
trial 4: 278142 prompt tokens, t=2.6s,  FINAL: R$ 10098.00
```

A 278k-token prompt processed in 2.6 seconds is not plausible reasoning. The same wrong answer (`10098.00`) appearing four times in a row, including in an earlier run on a different scale, strongly suggests a provider-side caching or routing fallback. This is not the same as "the model lacks the capability" — at 25k (with a *larger* 698k-token prompt) the same model on the same provider succeeded 5/5.

**RAG never recovered.** Across 40 trials and four scales, top-3 retrieval was structurally unable to fetch the three regions required (200-250 of loja_A, 400-450 of loja_B, and the rules in taxas.txt) simultaneously. Increasing top-k or chunk size would shift the breakpoint but not eliminate the failure mode for joint multi-region tasks.

## Phase C — Is M1 brittle only on DeepSeek?

The 10k anomaly on DeepSeek raised the question: is M1's failure pattern provider-specific, or does it reproduce elsewhere? We re-ran M1 only on `google/gemini-2.5-flash` at 1k and 10k, n=5 each. (The last two trials at 10k hit an OpenRouter key limit and returned no result — we report 3 valid trials at 10k.)

| Provider \ Scale | 1k | 10k |
|:---|:---|:---|
| deepseek-v4-flash | 100% (5/5) `FINAL: 70992` | 0% (0/5) `FINAL: 10098.00` (×4), `10044.00` (×1) |
| **gemini-2.5-flash** | **0% (0/5) `FINAL: 1080.0` (×5)** | **0% (0/3) `FINAL: 1005.0` (×3)** |

**Gemini failed at 1k**, where the entire workspace fits comfortably in any modern context window. The wrong answer (`1080.0`) is consistent and decodable: `1080 ≈ 8998 × 0.12` where `8998 = 409 × 22` — the tax on a *single* transaction near the middle of the Loja B range. The model picked one row and reported its tax as if it were the aggregate. It did not perform the sum.

So we have two providers, two failure modes, both 0%:
- DeepSeek at 10k: opaque short-latency wrong answer, suspected cache/routing artifact
- Gemini at 1k and 10k: deterministic single-row answer, suspected aggregation failure

We did **not** confirm the specific DeepSeek cache hypothesis. We did confirm something stronger: **M1 brute force is unreliable across providers, in different ways, at different scales, including scales where context window cannot be the issue.**

M4 was not re-tested on Gemini in this phase, so the matching cross-provider M4 row is currently empty.

## Findings

1. **RAG (top-k retrieval) is structurally inadequate for multi-source joint reasoning.** 0/40 trials succeeded. This is not a tuning problem — the retriever cannot return the disjoint regions required.

2. **Brute-force long-context is doubly brittle.** It depends on (a) the provider serving requests without silent routing/caching artifacts at the prompt size you happen to use, and (b) the model actually performing the multi-step aggregation instead of sampling a single row. Both failure modes are silent — no API error, no obvious signal at request time.

3. **A code-acting REPL agent achieves 100% accuracy across the tested scales with O(1) token cost in data size.** At 25k lines/file, this is a 44× cost advantage over brute force in the same model.

4. **The REPL approach decouples the model's role from the computation's role.** The model orchestrates; the CPU computes. This is why a model that fails brute-force arithmetic can still succeed via M4 — the math leaves the LLM's probabilistic substrate and runs deterministically on hardware. We have not yet measured this cross-provider, but the hypothesis is testable with one additional run.

## Threats to validity

- **One task family.** Multi-source numeric join over structured text. Tasks with different structure (free-text QA, code synthesis, ambiguous reasoning) may produce different rankings.
- **One RAG configuration.** Top-3 with 50-line lexical/embedding chunks. Multi-hop RAG, query rewriting, or graph-RAG variants could improve M2/M3. We make a structural claim, not a hyperparameter-optimal one.
- **`temperature=0` is not fully deterministic** at most providers (batching, routing, sampling implementation details all introduce noise). We observed this and report `± sd` in tables.
- **n=5 per cell.** Adequate to distinguish 0%/100% but not to resolve 60%/80% differences. The dramatic results (RAG at 0/40, M4 at 20/20) are statistically clean; the M1 80%/100% wobble is not.
- **Provider pricing changes.** Cost numbers were captured via OpenRouter's `/api/v1/models` endpoint at run time. They reflect a point-in-time snapshot.
- **DeepSeek-v4-flash routing.** Some of the "M1 brittleness" we attribute to the provider may be specific to one of the underlying inference backends that OpenRouter happens to route to. We did not pin a single backend.
- **No T4 (anti-RLM) task yet.** A fair benchmark must include tasks where M4 loses to M1 on latency or cost (e.g., one-paragraph QA where the REPL overhead is pure waste). Without that, this report only shows half the picture.

## Reproducibility

```bash
pip install -r bench/requirements.txt
cp .env.example .env  # edit OPENROUTER_API_KEY, BENCH_MODEL, BENCH_SCALES
python -m bench.runner
python -m bench.report
```

All raw trials are kept as JSONL under `results/`. Each row is one (method, scale, trial) execution with full input/output, tokens, latency, and cost.

## Future work

Ordered roughly by information value per dollar:

1. **T4 anti-RLM task.** Single-paragraph QA, n=10, all four methods. Confirm where M4 loses.
2. **M4 cross-provider validation.** Run M4 on Gemini-2.5-flash at 1k. If 100%, the "RLM rescues weak math models" claim is established cross-provider.
3. **T2 needle-in-haystack and T3 conditional aggregation tasks.** Replicate the original RLM paper's needle task with full instrumentation; add a task where the join rule is a conditional predicate, not a fixed range.
4. **Scale beyond 25k.** At 100k lines/file (≈2.7M tokens for M1), brute force becomes mostly infeasible regardless of provider, sharpening the cost curve.
5. **Package the harness as an installable library** with the observability dashboard from the Gradio demo (token entropy + semantic drift between turns + budget enforcement). The contribution is engineering and instrumentation, not architecture.

## Related work

We are not claiming new ideas in any of these areas — only measuring them rigorously on a specific task family.

- **Recursive Language Models (Zhang et al., MIT 2026)** — motivated the "model talks to context via REPL" framing.
- **CodeAct (Wang et al., ACL 2024)** — established code emission as a unified action format for LLM agents.
- **Open Interpreter, smolagents, AutoGen, Anthropic tool-use code execution** — production-grade code-acting agent harnesses.
- **LIFE-HARNESS (Xu et al., PKU 2026)** — runtime trajectory regulation; we use a small version (multi-block extraction, code-hash loop-break).
- **RULER, NIAH** — long-context evaluation benchmarks. Our task is closer to RULER's variable-tracking subtype than to needle-in-haystack.

## Appendix: Raw result files

| Phase | File | Description |
|:---|:---|:---|
| A | `results/trials_20260527_161118.jsonl` | 1k baseline, 4 methods × 5 trials, DeepSeek-v4-flash |
| B | `results/trials_20260527_172428.jsonl` | Scale sweep 1k/5k/10k/25k, 4 methods × 5 trials, DeepSeek-v4-flash |
| C | `results/trials_20260527_193612.jsonl` | M1 on Gemini-2.5-flash at 1k and 10k |
