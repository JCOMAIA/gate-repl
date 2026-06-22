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


## FULL READ ME: https://github.com/JCOMAIA/gate-repl/tree/main/dist 

## DEMO
https://joaomaia.com.br/demo/
<img width="1093" height="869" alt="image" src="https://github.com/user-attachments/assets/ca14770a-d75b-473d-ab01-8f79623fa494" />
