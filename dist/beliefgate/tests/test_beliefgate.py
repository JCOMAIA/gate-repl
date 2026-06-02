"""Tests for belief-gate. The leak-proof tests ARE the safety guarantee.

Run:  python -m pytest beliefgate/tests/ -q
  or: python beliefgate/tests/test_beliefgate.py   (runs without pytest)
"""
from beliefgate import (
    check_set, Verdict,
    CoverageKind, CoverageClaim, SourceFacts, verify_coverage,
    check_consistency, run_with_repair,
)


# ----------------------------- set gate -----------------------------

def test_set_complete():
    r = check_set(required=range(200, 251), present=range(200, 251))
    assert r.verdict is Verdict.COMPLETE and r.ok

def test_set_interior_gap():
    present = set(range(200, 251)) - {225}
    r = check_set(required=range(200, 251), present=present)
    assert r.verdict is Verdict.INCOMPLETE
    assert r.missing == [225]            # exact interior hole, not a range judgment

def test_set_non_numeric_keys():
    req = {"Jan", "Feb", "Mar"}
    r = check_set(required=req, present={"Jan", "Mar"})
    assert r.verdict is Verdict.INCOMPLETE and r.missing == ["Feb"]

def test_set_never_false_completes():
    # missing anything -> never COMPLETE, for many random gaps
    import random
    rng = random.Random(0)
    for _ in range(200):
        full = set(range(0, 100))
        drop = set(rng.sample(sorted(full), rng.randint(1, 20)))
        r = check_set(required=full, present=full - drop)
        assert r.verdict is Verdict.INCOMPLETE
        assert set(r.missing) == drop


# ----------------------------- coverage gate -----------------------------

def _facts(present, keys=None, sorted_desc=False, boundary=False, evaluable=True):
    return SourceFacts(present_count=present, keys=keys or list(range(present)),
                       sorted_desc=sorted_desc, boundary_crossed=boundary,
                       predicate_evaluable=evaluable)

def test_full_count_certifies():
    r = verify_coverage(CoverageClaim(CoverageKind.FULL_COUNT, 200), _facts(200))
    assert r.ok

def test_sorted_is_not_deletion_proof():
    # sorted + boundary crossed but a mid record deleted -> must NOT certify
    r = verify_coverage(CoverageClaim(CoverageKind.SORTED_TO_THRESHOLD),
                        _facts(199, sorted_desc=True, boundary=True))
    assert r.verdict is Verdict.INCOMPLETE

def test_contiguous_certifies_and_gap_rejects():
    assert verify_coverage(CoverageClaim(CoverageKind.CONTIGUOUS_IDS, 200),
                           _facts(200, keys=list(range(200)))).ok
    holed = list(range(200)); holed.remove(97)
    assert verify_coverage(CoverageClaim(CoverageKind.CONTIGUOUS_IDS, 200),
                           _facts(199, keys=holed)).verdict is Verdict.INCOMPLETE

def test_undecidable_when_unevaluable():
    r = verify_coverage(CoverageClaim(CoverageKind.FULL_COUNT, 200),
                        _facts(200, evaluable=False))
    assert r.verdict is Verdict.UNDECIDABLE       # coverage can't rescue evaluability

def test_undue_undecidable_rejected():
    r = verify_coverage(CoverageClaim(CoverageKind.UNDECIDABLE), _facts(200, evaluable=True))
    assert r.verdict is Verdict.INCOMPLETE

def test_coverage_leak_proof():
    # For a genuinely INCOMPLETE source, NO declared claim may certify. Each
    # scenario has a REAL gap in every dimension a deletion-proof invariant checks:
    #   - count short:      140 present vs a claimed 200
    #   - id hole:          one id missing from the middle (breaks contiguity)
    #   - sorted mid-delete: sorted by value, one record gone -> id hole too
    keys_with_hole = [i for i in range(200) if i != 97]   # 199 keys, gap at 97
    short = _facts(140, keys=keys_with_hole[:140])
    id_hole = _facts(199, keys=keys_with_hole)
    sorted_hole = _facts(199, keys=keys_with_hole, sorted_desc=True, boundary=True)
    for facts, total in [(short, 200), (id_hole, 200), (sorted_hole, 200), (sorted_hole, None)]:
        for kind in CoverageKind:
            r = verify_coverage(CoverageClaim(kind, total), facts)
            assert r.verdict is not Verdict.COMPLETE, (kind, total, facts.present_count)


# ----------------------------- repair loop -----------------------------

def _buggy_declarer(answer_value):
    """A declarer that slips on attempt 1 (answer in total), fixes on repair."""
    def fn(facts, source_total, repair_msg):
        if not repair_msg:
            return CoverageClaim(CoverageKind.FULL_COUNT, answer_value)   # the slip
        return CoverageClaim(CoverageKind.FULL_COUNT, source_total)        # honest fix
    return fn

def test_repair_recovers_form_slip_on_complete():
    facts = _facts(200)
    res, trace = run_with_repair(_buggy_declarer(666945), facts, source_total=200)
    assert res.ok
    assert trace[0]["coherent"] is False and trace[1]["coherent"] is True

def test_repair_never_false_completes_on_partial():
    # 140 present, source claims 200 -> even after repair, len != total -> INCOMPLETE
    facts = _facts(140)
    res, trace = run_with_repair(_buggy_declarer(446511), facts, source_total=200)
    assert res.verdict is Verdict.INCOMPLETE

def test_consistency_flags_undue_undecidable():
    c = check_consistency(CoverageClaim(CoverageKind.UNDECIDABLE), _facts(200, evaluable=True), 200)
    assert c.coherent is False

def test_consistency_accepts_legit_undecidable():
    c = check_consistency(CoverageClaim(CoverageKind.UNDECIDABLE), _facts(200, evaluable=False), 200)
    assert c.coherent is True

def test_consistency_flags_form_slip():
    c = check_consistency(CoverageClaim(CoverageKind.FULL_COUNT, 999999), _facts(200), 200)
    assert c.coherent is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  OK  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} passed")
