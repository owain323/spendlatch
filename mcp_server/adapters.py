"""Simulated provider adapters — the execution surface behind mandates.

Every adapter is clearly labeled `simulated: true`. In production these wrap
real provider APIs (AWS EC2/CE, Figma admin, Zoom billing, OpenAI org
settings). Here they exist to prove the CONTROL FLOW: nothing executes
without a valid, in-scope, unexpired mandate — and every execution returns a
receipt that lands in the decision ledger.

The adapter boundary is deliberate: `actions.py` knows nothing about
providers, and adapters know nothing about mandates. That is what makes the
mandate gate independently testable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import sample_data as data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _base(action: dict, adapter: str, operation: str) -> dict:
    return {
        "adapter": adapter,
        "operation": operation,
        "simulated": True,  # never removed in this repo; production adapters replace the body
        "action_id": action["id"],
        "provider": action["provider"],
        "monthly_before": action["monthly_before"],
        "monthly_after": action["monthly_after"],
    }


def _aws_rightsize(action: dict) -> dict:
    receipt = _base(action, "aws", "ec2:ModifyInstanceAttribute")
    receipt["changes"] = [
        "Instance i-0f3a9c21: t3.2xlarge -> t3.large",
        "Stopped 19-day idle window billing profile; schedule retained",
        "CloudWatch alarm retained: CPU > 60% for 30min pages the owner",
    ]
    receipt["rollback"] = "ec2:ModifyInstanceAttribute back to t3.2xlarge (one call)"
    return receipt


def _figma_cancel_seat(action: dict) -> dict:
    receipt = _base(action, "figma", "admin:RemoveSeat")
    receipt["changes"] = [
        "Seat converted from paid to free-viewer at end of current cycle",
        "Files retained in the team workspace (no data loss)",
        "Owner notified by email (simulated)",
    ]
    receipt["rollback"] = "admin:AddSeat restores the paid seat within the billing cycle"
    return receipt


def _zoom_annual(action: dict) -> dict:
    receipt = _base(action, "zoom", "billing:SwitchPlan(monthly -> annual)")
    receipt["changes"] = [
        "Plan switched: Pro monthly $14.99 -> annual $149.90/yr ($12.49/mo equivalent)",
        "No feature change; meeting history and settings preserved",
    ]
    receipt["rollback"] = "Billing terms: annual plans are committed; switch evaluated before approval"
    return receipt


def _openai_route(action: dict) -> dict:
    receipt = _base(action, "openai", "org:UpdateRoutingPolicy")
    receipt["changes"] = [
        "Routing policy: short classification prompts (< 400 tokens) -> gpt-5-mini class",
        "Guardrail: 2% of traffic still samples the large model for quality drift checks",
        "Rollback switch retained in org settings",
    ]
    receipt["rollback"] = "org:UpdateRoutingPolicy back to single-model routing"
    return receipt


ADAPTERS: dict[str, tuple[str, object]] = {
    # action_id -> (adapter_name, execute_fn)
    "rightsize-ec2": ("aws", _aws_rightsize),
    "cancel-figma": ("figma", _figma_cancel_seat),
    "annual-zoom": ("zoom", _zoom_annual),
    "route-haiku": ("openai", _openai_route),
}


# Operation strings are fixed per adapter; exposed so mandates can name the
# exact operation they authorize without executing anything.
OPERATIONS: dict[str, str] = {
    "rightsize-ec2": "ec2:ModifyInstanceAttribute",
    "cancel-figma": "admin:RemoveSeat",
    "annual-zoom": "billing:SwitchPlan(monthly -> annual)",
    "route-haiku": "org:UpdateRoutingPolicy",
}


def operation_for(action_id: str) -> str | None:
    """The provider operation a mandate for this action would authorize."""
    if action_id not in ADAPTERS:
        return None
    return OPERATIONS[action_id]


def execute(action_id: str) -> dict:
    """Run the simulated provider operation. Returns a receipt.

    Callers (actions.execute_action) are responsible for mandate verification;
    adapters trust the gate and simply perform + report.
    """
    entry = ADAPTERS.get(action_id)
    if not entry:
        return {"error": f"no adapter for action '{action_id}'",
                "known_actions": sorted(ADAPTERS)}
    action = data.SAVING_ACTIONS.get(action_id)
    if not action:
        return {"error": f"unknown action '{action_id}'"}
    receipt = entry[1](action)
    receipt["executed_at"] = _now()
    receipt["monthly_saving"] = round(action["monthly_before"] - action["monthly_after"], 2)
    return receipt
