"""Controlled modality dataset: statements with ground-truth modal status.

Three modalities, ordered by commitment:
  decision    — a firm commitment ("we will use Postgres")
  option      — a possibility under consideration ("we could use Postgres")
  hypothesis  — a tentative belief ("Postgres might be faster")

The dangerous error (analogue of belief-gate's false-complete) is UPWARD
INVERSION: a hedge (option/hypothesis) stored or recalled as a decision — the
agent then ACTS on a maybe as if it were decided. The "missing arrow" critique
observed exactly this: a "could" came back as a "did".

We generate sentences from templates so ground truth is controlled. Each item
also records the surface modal markers that a deterministic checker could key on
(the §5 test: is the modality bounded/checkable, or only judgable?).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


# (template, modality, surface_markers) — markers are the deterministic cues.
TEMPLATES = [
    # decisions (committed)
    ("Vamos usar {x} para {y}.", "decision", ["vamos"]),
    ("Decidimos adotar {x} no {y}.", "decision", ["decidimos"]),
    ("{x} será o nosso {y} a partir de agora.", "decision", ["será"]),
    ("Está definido: {x} para {y}.", "decision", ["está definido", "definido"]),
    ("Confirmado, seguimos com {x} no {y}.", "decision", ["confirmado"]),
    # options (under consideration)
    ("Poderíamos usar {x} para {y}.", "option", ["poderíamos", "poderia"]),
    ("Uma alternativa é {x} no {y}.", "option", ["alternativa", "uma opção"]),
    ("Talvez valha considerar {x} para {y}.", "option", ["talvez", "considerar"]),
    ("{x} é uma possibilidade para {y}.", "option", ["possibilidade", "possível"]),
    ("Estamos avaliando {x} para {y}.", "option", ["avaliando", "avaliar"]),
    # hypotheses (tentative belief)
    ("{x} pode ser mais rápido que a alternativa no {y}.", "hypothesis", ["pode ser", "talvez"]),
    ("Acho que {x} reduziria o custo de {y}.", "hypothesis", ["acho que", "reduziria"]),
    ("Suponho que {x} resolveria o problema de {y}.", "hypothesis", ["suponho", "resolveria"]),
    ("É possível que {x} melhore o {y}.", "hypothesis", ["é possível que", "melhore"]),
    ("Hipoteticamente, {x} escalaria melhor no {y}.", "hypothesis", ["hipoteticamente", "escalaria"]),
]

SUBJECTS = ["Postgres", "Redis", "uma fila Kafka", "cache em memória", "GraphQL",
            "microsserviços", "um índice composto", "sharding", "o modelo gemma",
            "rate limiting", "uma CDN", "índice invertido"]
OBJECTS = ["o backend", "a camada de dados", "o pipeline de ingestão", "a API pública",
           "o serviço de busca", "o processamento batch", "a autenticação",
           "o armazenamento de logs", "a feature de relatórios"]


@dataclass
class ModalityItem:
    text: str
    modality: str            # ground truth: decision | option | hypothesis
    markers: list            # surface cues a deterministic checker could use
    meta: dict = field(default_factory=dict)


COMMITMENT = {"decision": 2, "option": 1, "hypothesis": 0}


def is_upward_inversion(true_mod: str, recalled_mod: str) -> bool:
    """True if a less-committed statement was recalled as MORE committed — the
    dangerous direction (a hedge acted on as a decision)."""
    return COMMITMENT.get(recalled_mod, -1) > COMMITMENT.get(true_mod, 99)


def generate(n: int, seed: int = 7) -> list[ModalityItem]:
    rng = random.Random(seed)
    items = []
    for _ in range(n):
        tmpl, mod, markers = rng.choice(TEMPLATES)
        x, y = rng.choice(SUBJECTS), rng.choice(OBJECTS)
        items.append(ModalityItem(text=tmpl.format(x=x, y=y), modality=mod,
                                   markers=markers, meta={"x": x, "y": y}))
    return items
