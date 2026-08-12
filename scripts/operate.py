#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from wafer_batch_admission_gate import Decision,WaferBatchAdmissionGate,WaferBatchAdmissionGateRequest

def main():
    q=WaferBatchAdmissionGateRequest(subject_id="operate",payload={"batch_size":96,"predicted_latency_ms":9.2,"predicted_quality_score":.975,"required_throughput_tps":9000,"available_throughput_tps":14000,"queue_depth":2,"max_latency_ms":12,"min_quality_score":.95,"max_batch_size":128,"max_queue_depth":8},budget=4)
    r=WaferBatchAdmissionGate().evaluate(q);print(json.dumps(r.as_dict(),indent=2,sort_keys=True))
    if r.decision is not Decision.ALLOW:return 2
    if r.result["headroom"]["batch_slots"]!=32:return 3
    if r.result["headroom"]["throughput_tps"]!=5000:return 4
    if not WaferBatchAdmissionGate.verify_receipt(r):return 5
    return 0
if __name__=="__main__":raise SystemExit(main())
