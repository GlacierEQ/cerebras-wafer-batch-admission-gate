from wafer_batch_admission_gate import Decision, WaferBatchAdmissionGate, WaferBatchAdmissionGateRequest


def req(**p):
    payload=dict(batch_size=64,predicted_latency_ms=8.5,predicted_quality_score=.97,required_throughput_tps=8000,available_throughput_tps=12000,queue_depth=2,max_latency_ms=12,min_quality_score=.95,max_batch_size=128,max_queue_depth=8)
    payload.update(p)
    return WaferBatchAdmissionGateRequest(subject_id="batch-1",payload=payload,budget=4)


def test_batch_inside_all_bounds_is_admitted():
    r=WaferBatchAdmissionGate().evaluate(req())
    assert r.decision is Decision.ALLOW
    assert r.result["admitted"] is True
    assert r.result["headroom"]["batch_slots"]==64
    assert WaferBatchAdmissionGate.verify_receipt(r)


def test_latency_violation_has_exact_bound():
    r=WaferBatchAdmissionGate().evaluate(req(predicted_latency_ms=18.4))
    assert r.decision is Decision.REFUSE
    v=r.result["violations"][0]
    assert v=={"metric":"predicted_latency_ms","observed":18.4,"operator":"<=","limit":12.0,"unit":"ms"}


def test_quality_violation_has_exact_bound():
    r=WaferBatchAdmissionGate().evaluate(req(predicted_quality_score=.91))
    assert r.decision is Decision.REFUSE
    assert r.result["violations"][0]["metric"]=="predicted_quality_score"


def test_multiple_violations_are_all_reported():
    r=WaferBatchAdmissionGate().evaluate(req(batch_size=200,predicted_latency_ms=20,predicted_quality_score=.8,required_throughput_tps=20000,queue_depth=20))
    assert r.decision is Decision.REFUSE
    assert {v["metric"] for v in r.result["violations"]}=={"batch_size","predicted_latency_ms","predicted_quality_score","required_throughput_tps","queue_depth"}


def test_throughput_bound_is_enforced():
    r=WaferBatchAdmissionGate().evaluate(req(required_throughput_tps=13000))
    assert r.decision is Decision.REFUSE
    assert r.result["violations"][0]["unit"]=="tokens/s"


def test_queue_bound_is_enforced():
    r=WaferBatchAdmissionGate().evaluate(req(queue_depth=9))
    assert r.decision is Decision.REFUSE
    assert r.result["violations"][0]["metric"]=="queue_depth"


def test_envelope_change_changes_fingerprint():
    gate=WaferBatchAdmissionGate()
    a=gate.evaluate(req())
    b=gate.evaluate(req(max_latency_ms=15))
    assert a.result["envelope_fingerprint"] != b.result["envelope_fingerprint"]


def test_deterministic_replay():
    gate=WaferBatchAdmissionGate(); q=req(); assert gate.evaluate(q)==gate.evaluate(q)
