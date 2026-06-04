# belief-gate / gate-REPL

Verify what an LLM has, instead of trusting what it says it has. This repo is an
empirical study and a small library for **completeness verification by execution,
not by judgment** — plus the honest map of where that discipline applies and where
it does not.

The core result: an LLM judging "is this context complete?" false-passes on subtle
gaps (7/15 on one model, 2/15 on another). Moving the check into executed code — the
LLM declares the *required* set, the CPU computes `required − present` — drops that
to **0/15, on both models**, and the system never certifies an answer it can't prove.

End-to-end, the payoff is a double dissociation: routed through **LLM → gate → REPL**, a
computable question is answered exactly or abstained — **80/80 correct, 80/80 abstain**
across two models — while the same models answering directly score **3–6/80** on the
arithmetic (gemini: 0/40) and confabulate on incomplete data. The gate fixes calibration;
the REPL fixes arithmetic; only the full pipeline is clean on both.

## Start here

| If you want to… | Read |
| :--- | :--- |
| **See every measured result in one place** | [`docs/FINDINGS.md`](docs/FINDINGS.md) — the consolidated executive summary (start here) |
| **Use the gate in your code** | [`beliefgate/README.md`](beliefgate/README.md) — the installable library + a domain-adaptation guide |
| **Wire it into a pipeline / MCP / Claude Code** | [`beliefgate/INTEGRATION.md`](beliefgate/INTEGRATION.md) and real [`docs/SCENARIOS.md`](docs/SCENARIOS.md) |
| **Understand the method & evidence** | [`docs/GATE_REPL.md`](docs/GATE_REPL.md) — the full write-up: double dissociation, the SPOF and its fix, cross-model, predicate coverage, the real-benchmark scope study, the end-to-end pipeline |
| **See the bigger picture & its limits** | [`docs/UNIFICATION.md`](docs/UNIFICATION.md) — the "coherence arrow" principle, what it unifies (extraction + verification + memory-coherence), and the layer it does *not* (modality is open-class — span-anchoring buys provenance, not CPU teeth) |
| **Run it in Claude Code** | [`plugins/belief-gate/`](plugins/belief-gate/) — the technique packaged as a Claude Code skill |
| **Follow the research log** | [`IDEAS.md`](IDEAS.md) — the lab notebook: every experiment, every paper link, every failure kept as a step |
| **The original RLM/RAG benchmark** | [`WRITEUP.md`](WRITEUP.md) — the cross-provider M1–M4 study this grew out of |

## The library in 30 seconds

```python
from beliefgate import check_set

# required comes from the TASK (an id range, named columns, a list of invoices)
# present comes from a STRUCTURED source (a parser / DB / API), never an LLM
res = check_set(required=range(200, 251), present=present_ids)
if res.ok:
    answer = compute(...)          # safe: coverage is proven
else:
    abstain(res.missing)           # exact gap, e.g. [225]; never guess
```

Zero runtime dependencies. 25/25 unit tests, leak-proof (never false-completes).
Predicate coverage, an LLM-declaration repair loop, bookkeeping memory (`verify_fresh`
— cache coherence with the same guarantee), and an UNDECIDABLE verdict are in the
library too — see its README.

## The one rule that makes it work

> Feed `present` from a parser / DB / API, not from an LLM reading prose. Derive
> `required` from the task, not from the data. Inside that envelope the guarantee is
> absolute; outside it, the gate degrades to whatever produced its inputs.

This is not a slogan — it's the measured boundary. Three real benchmarks (multi-needle
on real text, FinQA, keyed aggregation) showed the gate's core is flawless and its
weak point is always the *extractor* that feeds it. Details in `docs/GATE_REPL.md` §11.

## Repository layout

```
beliefgate/          the installable library (pip install -e beliefgate)  + README + INTEGRATION
docs/
  FINDINGS.md         consolidated executive summary of every measured result
  GATE_REPL.md        the method and the full empirical study (incl. end-to-end pipeline)
  UNIFICATION.md      the coherence-arrow synthesis and its tested limits
  SCENARIOS.md        real usage scenarios (where the gate earns its keep)
plugins/belief-gate/  Claude Code skill packaging
bench/                all experiments (reproducible; read each module's docstring)
  methods/            the original M1–M4 RAG/RLM ablation
  realqa/             real-dataset harness: keyed aggregation + the end-to-end pipeline
  memory/             bookkeeping-memory coherence demo (layer [3])
  modality/           the memory-modality study (slot vs lexicon vs RBF vs span-anchoring)
  openqa/             post-answer grounding guardrail (the open-QA boundary)
IDEAS.md              running research notebook
WRITEUP.md            the original cross-provider RLM/RAG report
```

## Reproducing

```bash
pip install -r bench/requirements.txt
cp .env.example .env        # put your OPENROUTER_API_KEY here (gitignored)
python -m bench.proto_gate_adv     # LLM gate on subtle gaps (~7/15 false-pass)
python -m bench.proto_gate_repl    # the fix (0/15)
```

Each `bench/proto_*.py` and `bench/**/harness*.py` is a self-contained experiment;
its docstring states the question, method, and how to read the output. Raw runs land
in `results/` (gitignored). Benchmarks that use real text/tables need the source
files locally (NIAH haystack papers; FinQA `dev.json`) — see the relevant docstrings.

## Honest scope

belief-gate is **not** general QA. It verifies an enumerable, task-derived
requirement against a structured context. It wins where completeness has a
deterministic anchor (set difference, coverage invariant), ties where the gap is
obvious enough that an LLM already catches it, and does not apply where relevance is
only knowable by understanding the data. The study documents all three — see
`docs/UNIFICATION.md` §7 for the criterion.

## License

MIT (library and code). The `.txt` research papers and downloaded datasets are not
redistributed here (copyright); the benchmarks reference them locally.
