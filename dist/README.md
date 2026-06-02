# belief-gate / gate-REPL

Verify what an LLM has, instead of trusting what it says it has. This repo is an
empirical study and a small library for **completeness verification by execution,
not by judgment** — plus the honest map of where that discipline applies and where
it does not.

The core result: an LLM judging "is this context complete?" false-passes on subtle
gaps (7/15 on one model, 2/15 on another). Moving the check into executed code — the
LLM declares the *required* set, the CPU computes `required − present` — drops that
to **0/15, on both models**, and the system never certifies an answer it can't prove.

## Start here

| If you want to… | Read |
| :--- | :--- |
| **Use the gate in your code** | [`beliefgate/README.md`](beliefgate/README.md) — the installable library + a domain-adaptation guide |
| **Understand the method & evidence** | [`docs/GATE_REPL.md`](docs/GATE_REPL.md) — the full write-up: double dissociation, the SPOF and its fix, cross-model, predicate coverage, the real-benchmark scope study |
| **See the bigger picture & its limits** | [`docs/UNIFICATION.md`](docs/UNIFICATION.md) — the "coherence arrow" principle, what it unifies (extraction + verification), and the layer it does *not* (modality is irreducibly semantic — tested and refuted) |
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

Zero runtime dependencies. 15/15 unit tests, leak-proof (never false-completes).
Predicate coverage, an LLM-declaration repair loop, and an UNDECIDABLE verdict are
in the library too — see its README.

## The one rule that makes it work

> Feed `present` from a parser / DB / API, not from an LLM reading prose. Derive
> `required` from the task, not from the data. Inside that envelope the guarantee is
> absolute; outside it, the gate degrades to whatever produced its inputs.

This is not a slogan — it's the measured boundary. Three real benchmarks (multi-needle
on real text, FinQA, keyed aggregation) showed the gate's core is flawless and its
weak point is always the *extractor* that feeds it. Details in `docs/GATE_REPL.md` §11.

## Repository layout

```
beliefgate/          the installable library (pip install -e beliefgate)  + its README
docs/
  GATE_REPL.md        the method and the full empirical study
  UNIFICATION.md      the coherence-arrow synthesis and its tested limits
plugins/belief-gate/  Claude Code skill packaging
bench/                all experiments (reproducible; read each module's docstring)
  methods/            the original M1–M4 RAG/RLM ablation
  realqa/             real-dataset harness (DROP / FinQA adapters)
  modality/           the §5 memory-modality study (LLM vs lexicon vs RBF vs logistic)
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
