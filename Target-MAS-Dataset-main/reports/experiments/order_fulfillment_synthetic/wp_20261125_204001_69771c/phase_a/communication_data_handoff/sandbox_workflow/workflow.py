"""
Workflow Orchestrator: Synthetic Order Fulfillment (7 CrewAI Agents).

Baseline execution runs all 7 agents strictly sequentially so:
- Parallelization discovers (inventory_check_agent, fraud_screen_agent)
- Data Handoff discovers unused bloated fields on order_intake_agent
- Model Selection discovers JEV downgrade on order_intake_agent
- Agent Consolidation discovers [carrier_routing_agent, tax_classify_agent, invoice_tag_agent]
- Prompt Optimization discovers >1000-token bloated prompt on fulfillment_summary_agent
"""

import json
import os
import uuid
from typing import Any, Dict, Optional

from common.metrics import MetricsTracker
from common.tracing import init_tracing

from Agents.order_fulfillment_synthetic import (
    order_intake_agent,
    inventory_check_agent,
    fraud_screen_agent,
    carrier_routing_agent,
    tax_classify_agent,
    invoice_tag_agent,
    fulfillment_summary_agent,
)

WORKFLOW_NAME = "order_fulfillment_synthetic"
EXPECTED_AGENT_COUNT = 7


def load_sample_order_input(
    order_index: int = 0,
    data_dir: str = "data/order_fulfillment_synthetic",
) -> Dict[str, Any]:
    orders_path = os.path.join(data_dir, "orders.json")
    with open(orders_path, "r", encoding="utf-8") as f:
        orders = json.load(f)
    return orders[order_index % len(orders)]


class OrderFulfillmentSyntheticWorkflow:
    """Sequential baseline orchestrator supporting optional per-agent LLM injection."""

    def __init__(
        self,
        llm: Optional[Any] = None,
        llm_map: Optional[Dict[str, Any]] = None,
        enable_tracing: bool = False,
    ):
        self.llm = llm
        self.llm_map = llm_map or {}
        if enable_tracing:
            init_tracing(project_name="awo-order-fulfillment-synthetic")

        self.agent_1_intake = order_intake_agent.create_agent(llm=self.llm_map.get("order_intake_agent") or self.llm)
        self.agent_2_inventory = inventory_check_agent.create_agent(llm=self.llm_map.get("inventory_check_agent") or self.llm)
        self.agent_3_fraud = fraud_screen_agent.create_agent(llm=self.llm_map.get("fraud_screen_agent") or self.llm)
        self.agent_4_carrier = carrier_routing_agent.create_agent(llm=self.llm_map.get("carrier_routing_agent") or self.llm)
        self.agent_5_tax = tax_classify_agent.create_agent(llm=self.llm_map.get("tax_classify_agent") or self.llm)
        self.agent_6_invoice = invoice_tag_agent.create_agent(llm=self.llm_map.get("invoice_tag_agent") or self.llm)
        self.agent_7_summary = fulfillment_summary_agent.create_agent(llm=self.llm_map.get("fulfillment_summary_agent") or self.llm)

    def get_agent_count(self) -> int:
        return EXPECTED_AGENT_COUNT

    def run(
        self,
        input_data: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        runs_base_dir: str = "runs",
    ) -> Dict[str, Any]:
        active_run_id = run_id or f"ord_{uuid.uuid4().hex[:8]}"
        tracker = MetricsTracker(workflow_name=WORKFLOW_NAME, run_id=active_run_id)
        order_data = input_data if input_data is not None else load_sample_order_input()

        try:
            intake_res = order_intake_agent.run_order_intake(
                order_data=order_data,
                agent=self.agent_1_intake,
                tracker=tracker,
            )
            rec_id = str(intake_res.get("record_id") or order_data.get("record_id") or "ORD-000")

            inv_res = inventory_check_agent.run_inventory_check(
                intake_output=intake_res,
                agent=self.agent_2_inventory,
                tracker=tracker,
            )

            fraud_res = fraud_screen_agent.run_fraud_screen(
                intake_output=intake_res,
                agent=self.agent_3_fraud,
                tracker=tracker,
            )

            carrier_res = carrier_routing_agent.run_carrier_routing(
                intake_output=intake_res,
                inventory_output=inv_res,
                fraud_output=fraud_res,
                agent=self.agent_4_carrier,
                tracker=tracker,
            )

            tax_res = tax_classify_agent.run_tax_classify(
                intake_output=intake_res,
                routing_output=carrier_res,
                agent=self.agent_5_tax,
                tracker=tracker,
            )

            invoice_res = invoice_tag_agent.run_invoice_tag(
                intake_output=intake_res,
                tax_output=tax_res,
                agent=self.agent_6_invoice,
                tracker=tracker,
            )

            final_summary = fulfillment_summary_agent.run_fulfillment_summary(
                run_id=active_run_id,
                record_id=rec_id,
                inventory_output=inv_res,
                fraud_output=fraud_res,
                routing_output=carrier_res,
                tax_output=tax_res,
                invoice_output=invoice_res,
                agent=self.agent_7_summary,
                tracker=tracker,
            )

            record = tracker.finalize(
                output=final_summary,
                status="success",
                runs_base_dir=runs_base_dir,
            )
            output_dict = dict(final_summary) if isinstance(final_summary, dict) else {}
            output_dict.update({
                "run_id": active_run_id,
                "status": "SUCCESS",
                "duration_seconds": record.total_duration_seconds,
                "total_tokens": record.token_usage.get("total_tokens", 0) if record.token_usage else 0,
                "prompt_tokens": record.token_usage.get("prompt_tokens", 0) if record.token_usage else 0,
                "completion_tokens": record.token_usage.get("completion_tokens", 0) if record.token_usage else 0,
                "estimated_cost_usd": record.estimated_cost_usd or 0.0,
                "agent_executions": [m.model_dump() for m in record.agent_metrics],
                "final_output": final_summary,
            })
            return output_dict

        except Exception as exc:
            tracker.finalize(
                output=None,
                status="failed",
                error=str(exc),
                runs_base_dir=runs_base_dir,
            )
            raise


def run_order_fulfillment_synthetic_workflow(
    input_data: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    wf = OrderFulfillmentSyntheticWorkflow(enable_tracing=False)
    return wf.run(input_data=input_data, run_id=run_id)

# Applied by AWO Sandbox Executor
HANDOFF_PROJECTIONS = {'order_intake_agent->inventory_check_agent': {'candidate_id': 'HANDOFF-ORDER_INTAKE_AGENT-TO-INVENTORY_CHECK_AGENT', 'producer_agent': 'order_intake_agent', 'consumer_agent': 'inventory_check_agent', 'retained_fields': ['record_id', 'shipping_region', 'warehouse_region', 'order_total_usd', 'sku_items', 'legacy_erp_dump', 'deprecated_sku_notes'], 'excluded_fields': ['request_id', 'customer_id', 'customer_tier', 'billing_country', 'shipping_speed', 'raw_audit_trail', 'debug_headers', 'internal_routing_flags', 'formatting_metadata'], 'consumer_required_fields': ['record_id', 'warehouse_region', 'sku_items'], 'typed_delta_projection': True}, 'order_intake_agent->fraud_screen_agent': {'candidate_id': 'HANDOFF-ORDER_INTAKE_AGENT-TO-FRAUD_SCREEN_AGENT', 'producer_agent': 'order_intake_agent', 'consumer_agent': 'fraud_screen_agent', 'retained_fields': ['record_id', 'customer_id', 'customer_tier', 'billing_country', 'order_total_usd', 'deprecated_sku_notes', 'internal_routing_flags'], 'excluded_fields': ['request_id', 'shipping_region', 'warehouse_region', 'shipping_speed', 'sku_items', 'legacy_erp_dump', 'raw_audit_trail', 'debug_headers', 'formatting_metadata'], 'consumer_required_fields': ['record_id', 'customer_id', 'customer_tier', 'billing_country', 'order_total_usd'], 'typed_delta_projection': True}, 'inventory_check_agent->carrier_routing_agent': {'candidate_id': 'HANDOFF-INVENTORY_CHECK_AGENT-TO-CARRIER_ROUTING_AGENT', 'producer_agent': 'inventory_check_agent', 'consumer_agent': 'carrier_routing_agent', 'retained_fields': ['record_id', 'in_stock', 'warehouse_code'], 'excluded_fields': ['backorder_skus', 'inventory_note'], 'consumer_required_fields': ['record_id', 'in_stock', 'warehouse_code'], 'typed_delta_projection': True}, 'fraud_screen_agent->carrier_routing_agent': {'candidate_id': 'HANDOFF-FRAUD_SCREEN_AGENT-TO-CARRIER_ROUTING_AGENT', 'producer_agent': 'fraud_screen_agent', 'consumer_agent': 'carrier_routing_agent', 'retained_fields': ['record_id', 'risk_band', 'review_flag'], 'excluded_fields': ['screen_note'], 'consumer_required_fields': ['record_id', 'risk_band', 'review_flag'], 'typed_delta_projection': True}, 'carrier_routing_agent->tax_classify_agent': {'candidate_id': 'HANDOFF-CARRIER_ROUTING_AGENT-TO-TAX_CLASSIFY_AGENT', 'producer_agent': 'carrier_routing_agent', 'consumer_agent': 'tax_classify_agent', 'retained_fields': ['record_id', 'carrier_name', 'service_level'], 'excluded_fields': ['estimated_days'], 'consumer_required_fields': ['record_id', 'carrier_name', 'service_level'], 'typed_delta_projection': True}, 'invoice_tag_agent->fulfillment_summary_agent': {'candidate_id': 'HANDOFF-INVOICE_TAG_AGENT-TO-FULFILLMENT_SUMMARY_AGENT', 'producer_agent': 'invoice_tag_agent', 'consumer_agent': 'fulfillment_summary_agent', 'retained_fields': ['record_id', 'gl_account_code', 'invoice_tag'], 'excluded_fields': ['billing_batch'], 'consumer_required_fields': ['record_id', 'invoice_tag'], 'typed_delta_projection': True}}

def project_handoff_payload(producer, consumer, payload):
    """Project approved compact fields on configured edges; pass through unapproved edges unchanged."""
    if not isinstance(payload, dict):
        return payload
    spec = HANDOFF_PROJECTIONS.get(f'{producer}->{consumer}')
    if not spec:
        return payload
    retained = set(spec.get('retained_fields') or [])
    return {k: v for k, v in payload.items() if k in retained}
