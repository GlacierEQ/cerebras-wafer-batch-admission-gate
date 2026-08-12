from wafer_batch_admission_gate import Decision, WaferBatchAdmissionGate, WaferBatchAdmissionGateRequest

BASE=dict(batch_size=64,predicted_latency_ms=8,predicted_quality_score=.98,required_throughput_tps=8000,available_throughput_tps=12000,queue_depth=1,max_latency_ms=12,min_quality_score=.95,max_batch_size=128,max_queue_depth=8)

def make(update=None,**kw):
    p=dict(BASE);p.update(update or {});v=dict(subject_id="adv",payload=p,budget=4);v.update(kw);return WaferBatchAdmissionGateRequest(**v)

def test_unknown_bypass_field_refuses():
    r=WaferBatchAdmissionGate().evaluate(make({"ignore_quality":True})); assert r.decision is Decision.REFUSE

def test_boolean_batch_size_refuses():
    r=WaferBatchAdmissionGate().evaluate(make({"batch_size":True})); assert r.decision is Decision.REFUSE

def test_quality_above_one_refuses():
    r=WaferBatchAdmissionGate().evaluate(make({"predicted_quality_score":1.1})); assert "quality_score_out_of_range" in r.reasons

def test_absurd_batch_hits_absolute_limit():
    r=WaferBatchAdmissionGate().evaluate(make({"batch_size":1_000_001},budget=1000)); assert "batch_size_over_absolute_limit" in r.reasons

def test_work_budget_refuses_large_batch_before_admission():
    r=WaferBatchAdmissionGate().evaluate(make({"batch_size":10000,"max_batch_size":20000},budget=1.5)); assert "work_budget_exceeded" in r.reasons

def test_expired_request_refuses():
    r=WaferBatchAdmissionGate(clock=lambda:101).evaluate(make(not_after=100)); assert "request_expired" in r.reasons

def test_boolean_budget_refuses():
    r=WaferBatchAdmissionGate().evaluate(make(budget=True)); assert "budget_invalid" in r.reasons
