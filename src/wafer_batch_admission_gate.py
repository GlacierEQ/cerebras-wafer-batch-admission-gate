"""Batch admission control against explicit latency, quality, and capacity envelopes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


def _digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str).encode()).hexdigest()


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"


@dataclass(frozen=True)
class WaferBatchAdmissionGateRequest:
    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    budget: float = 4.0
    grant_id: str | None = None
    not_after: float | None = None


@dataclass(frozen=True)
class WaferBatchAdmissionGateReceipt:
    decision: Decision
    reasons: tuple[str, ...]
    digest: str
    metrics: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"decision":self.decision.value,"reasons":list(self.reasons),"digest":self.digest,"metrics":self.metrics,"result":self.result}


class WaferBatchAdmissionGate:
    """Admit an inference batch only when every declared service bound holds."""

    VALID_PAYLOAD_KEYS = frozenset({
        "batch_size", "predicted_latency_ms", "predicted_quality_score",
        "required_throughput_tps", "available_throughput_tps", "queue_depth",
        "max_latency_ms", "min_quality_score", "max_batch_size", "max_queue_depth",
    })
    MAX_ABSOLUTE_BATCH_SIZE = 1_000_000
    BASE_WORK_UNITS = 1.0
    PER_THOUSAND_ITEMS_WORK_UNITS = 0.1

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.time

    @staticmethod
    def _number(value: Any, name: str, *, min_value: float | None = None) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError(f"{name}_invalid")
        number = float(value)
        if min_value is not None and number < min_value:
            raise ValueError(f"{name}_out_of_range")
        return number

    @staticmethod
    def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"{name}_invalid")
        return value

    def _refuse(self, req: WaferBatchAdmissionGateRequest, reasons: list[str], result: dict[str, Any] | None = None) -> WaferBatchAdmissionGateReceipt:
        unique = tuple(sorted(set(reasons)))
        result = result or {}
        body = {"subject_id":req.subject_id,"payload":req.payload,"budget":req.budget,"not_after":req.not_after,"decision":"REFUSE","reasons":unique,"result":result}
        return WaferBatchAdmissionGateReceipt(Decision.REFUSE, unique, _digest(body), {"bounded":True,"violation_count":len(result.get("violations", []))}, result)

    @staticmethod
    def _violation(metric: str, observed: float | int, operator: str, limit: float | int, unit: str) -> dict[str, Any]:
        return {"metric":metric,"observed":observed,"operator":operator,"limit":limit,"unit":unit}

    def evaluate(self, req: WaferBatchAdmissionGateRequest) -> WaferBatchAdmissionGateReceipt:
        if not isinstance(req, WaferBatchAdmissionGateRequest):
            raise TypeError("req must be WaferBatchAdmissionGateRequest")
        reasons: list[str] = []
        if not req.subject_id or not req.subject_id.strip(): reasons.append("subject_id_missing")
        if not isinstance(req.budget,(int,float)) or isinstance(req.budget,bool) or not math.isfinite(float(req.budget)): reasons.append("budget_invalid")
        elif req.budget <= 0: reasons.append("budget_non_positive")
        if req.not_after is not None:
            if not isinstance(req.not_after,(int,float)) or isinstance(req.not_after,bool) or not math.isfinite(float(req.not_after)): reasons.append("request_expiry_invalid")
            elif self._clock() > float(req.not_after): reasons.append("request_expired")
        unknown=set(req.payload)-self.VALID_PAYLOAD_KEYS
        if unknown: reasons.append("payload_keys_unknown:"+",".join(sorted(unknown)))
        if reasons: return self._refuse(req,reasons)

        try:
            batch_size=self._integer(req.payload.get("batch_size"),"batch_size",minimum=1)
            queue_depth=self._integer(req.payload.get("queue_depth"),"queue_depth",minimum=0)
            max_batch_size=self._integer(req.payload.get("max_batch_size"),"max_batch_size",minimum=1)
            max_queue_depth=self._integer(req.payload.get("max_queue_depth"),"max_queue_depth",minimum=0)
            predicted_latency=self._number(req.payload.get("predicted_latency_ms"),"predicted_latency_ms",min_value=0)
            max_latency=self._number(req.payload.get("max_latency_ms"),"max_latency_ms",min_value=0)
            quality=self._number(req.payload.get("predicted_quality_score"),"predicted_quality_score",min_value=0)
            min_quality=self._number(req.payload.get("min_quality_score"),"min_quality_score",min_value=0)
            required_tps=self._number(req.payload.get("required_throughput_tps"),"required_throughput_tps",min_value=0)
            available_tps=self._number(req.payload.get("available_throughput_tps"),"available_throughput_tps",min_value=0)
        except ValueError as exc:
            return self._refuse(req,[str(exc)])
        if quality > 1 or min_quality > 1:
            return self._refuse(req,["quality_score_out_of_range"])
        if batch_size > self.MAX_ABSOLUTE_BATCH_SIZE:
            return self._refuse(req,["batch_size_over_absolute_limit"])

        work_units=self.BASE_WORK_UNITS+(batch_size/1000.0)*self.PER_THOUSAND_ITEMS_WORK_UNITS
        if work_units>float(req.budget):
            return self._refuse(req,["work_budget_exceeded"],{"work_units":round(work_units,6),"budget_units":float(req.budget)})

        violations=[]
        if batch_size>max_batch_size: violations.append(self._violation("batch_size",batch_size,"<=",max_batch_size,"requests"))
        if predicted_latency>max_latency: violations.append(self._violation("predicted_latency_ms",predicted_latency,"<=",max_latency,"ms"))
        if quality<min_quality: violations.append(self._violation("predicted_quality_score",quality,">=",min_quality,"score"))
        if required_tps>available_tps: violations.append(self._violation("required_throughput_tps",required_tps,"<=",available_tps,"tokens/s"))
        if queue_depth>max_queue_depth: violations.append(self._violation("queue_depth",queue_depth,"<=",max_queue_depth,"batches"))

        envelope={
            "max_batch_size":max_batch_size,"max_latency_ms":max_latency,"min_quality_score":min_quality,
            "available_throughput_tps":available_tps,"max_queue_depth":max_queue_depth,
        }
        observed={
            "batch_size":batch_size,"predicted_latency_ms":predicted_latency,"predicted_quality_score":quality,
            "required_throughput_tps":required_tps,"queue_depth":queue_depth,
        }
        if violations:
            return self._refuse(req,["service_envelope_violated"],{
                "admitted":False,"violations":violations,"observed":observed,"envelope":envelope,
                "envelope_fingerprint":_digest(envelope),
            })

        headroom={
            "batch_slots":max_batch_size-batch_size,
            "latency_ms":round(max_latency-predicted_latency,6),
            "quality_score":round(quality-min_quality,6),
            "throughput_tps":round(available_tps-required_tps,6),
            "queue_slots":max_queue_depth-queue_depth,
        }
        result={"admitted":True,"violations":[],"observed":observed,"envelope":envelope,"headroom":headroom,"envelope_fingerprint":_digest(envelope)}
        metrics={"bounded":True,"work_units":round(work_units,6),"budget_units":float(req.budget),"batch_size":batch_size,"headroom_fingerprint":_digest(headroom)}
        body={"subject_id":req.subject_id,"not_after":req.not_after,"decision":"ALLOW","result":result,"metrics":metrics}
        return WaferBatchAdmissionGateReceipt(Decision.ALLOW,("batch_within_service_envelope",),_digest(body),metrics,result)

    @staticmethod
    def verify_receipt(receipt: WaferBatchAdmissionGateReceipt)->bool:
        return isinstance(receipt,WaferBatchAdmissionGateReceipt) and receipt.metrics.get("bounded") is True and len(receipt.digest)==64 and receipt.decision in {Decision.ALLOW,Decision.REFUSE}

Mechanism=WaferBatchAdmissionGate


def cli(argv: Sequence[str] | None=None)->int:
    p=argparse.ArgumentParser(description="Evaluate an inference batch against a declared service envelope.")
    p.add_argument("--input","-i")
    args=p.parse_args(argv)
    try:
        raw=Path(args.input).read_text() if args.input else sys.stdin.read()
        data=json.loads(raw)
        if not isinstance(data,Mapping): raise ValueError("request JSON must be an object")
        req=WaferBatchAdmissionGateRequest(subject_id=str(data.get("subject_id","")),payload=dict(data.get("payload") or {}),budget=data.get("budget",4),grant_id=data.get("grant_id"),not_after=data.get("not_after"))
        r=WaferBatchAdmissionGate().evaluate(req)
    except Exception as exc:
        print(json.dumps({"decision":"REFUSE","reasons":[f"cli_input_error:{type(exc).__name__}:{exc}"]},sort_keys=True)); return 2
    print(json.dumps(r.as_dict(),indent=2,sort_keys=True)); return 0 if r.decision is Decision.ALLOW else 2
