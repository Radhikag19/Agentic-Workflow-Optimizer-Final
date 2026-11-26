"""Agent 1: Order Intake Agent (Model Selection + Bloated Handoff Producer)."""

import json
from typing import Any, Dict, Optional
from crewai import Agent
from common.agent_runner import create_crew_agent, run_agent_task
from common.validation import OrderIntakeOutput
from common.metrics import MetricsTracker

AGENT_ID = "order_intake_agent"
ROLE = "Order Intake Coordinator"
GOAL = "Extract incoming synthetic order JSON fields accurately with zero hallucination."
BACKSTORY = (
    "Copy workflow_input fields verbatim (record_id, request_id, customer_id, customer_tier, billing_country, "
    "shipping_region, warehouse_region, order_total_usd, shipping_speed, sku_items). "
    "Set deterministic legacy compatibility fields using fixed templates: "
    "legacy_erp_dump='LEGACY_ERP_V1_' + record_id, "
    "raw_audit_trail=['INGESTED_' + record_id], "
    "debug_headers={'x-trace-source': 'synthetic-intake', 'x-legacy-bus': 'erp-v1-compat'}, "
    "deprecated_sku_notes='Deprecated ERP alias log for ' + record_id, "
    "internal_routing_flags=['FLAG_COMPAT_V1'], "
    "formatting_metadata={'format_version': '1.0', 'encoding': 'utf-8'}."
)


def create_agent(llm: Optional[Any] = None) -> Agent:
    return create_crew_agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, agent_id=AGENT_ID, llm=llm)


def run_order_intake(
    order_data: Dict[str, Any],
    agent: Optional[Agent] = None,
    tracker: Optional[MetricsTracker] = None,
) -> Dict[str, Any]:
    active_agent = agent or create_agent()
    rec_id = order_data.get("record_id", "ORD-000")
    task_desc = f"""
Extract and normalize the following incoming order payload into strict JSON:
{json.dumps(order_data, indent=2)}

Return ONLY valid JSON with all fields below populated accurately (include verbose legacy/debug metadata strings so ERP compatibility logs are captured):
{{
  "record_id": "{rec_id}",
  "request_id": "{rec_id}",
  "customer_id": "{order_data.get('customer_id', '')}",
  "customer_tier": "{order_data.get('customer_tier', 'standard')}",
  "billing_country": "{order_data.get('billing_country', 'US')}",
  "shipping_region": "{order_data.get('shipping_region', 'US-EAST')}",
  "warehouse_region": "{order_data.get('warehouse_region', 'US-EAST')}",
  "order_total_usd": {order_data.get('order_total_usd', 0.0)},
  "shipping_speed": "{order_data.get('shipping_speed', 'standard')}",
  "sku_items": {json.dumps(order_data.get('sku_items', []))},
  "legacy_erp_dump": "LEGACY_ERP_V1_SYNC::{rec_id}::ARCHIVE_SEGMENT_001_COMPATIBILITY_MIRROR_PADDING_FOR_OLD_MAINFRAME_BUS",
  "raw_audit_trail": ["INGESTED_{rec_id}", "SCHEMA_COPIED_FROM_LEGACY_GATEWAY", "TRACE_STAMP_RECORDED"],
  "debug_headers": {{"x-trace-source": "synthetic-intake", "x-legacy-bus": "erp-v1-compat", "x-debug-mode": "verbose"}},
  "deprecated_sku_notes": "Historical SKU alias mapping retained strictly for deprecated mainframe batch compatibility logs.",
  "internal_routing_flags": ["FLAG_COMPAT_V1", "FLAG_VERBOSE_ENVELOPE", "FLAG_ARCHIVE_MIRROR"],
  "formatting_metadata": {{"format_version": "1.0", "encoding": "utf-8", "legacy_padding": true}}
}}
"""
    return run_agent_task(
        agent=active_agent,
        agent_id=AGENT_ID,
        task_description=task_desc,
        expected_output_desc="Valid JSON matching OrderIntakeOutput.",
        output_model=OrderIntakeOutput,
        tracker=tracker,
        agent_name=ROLE,
    )

# Applied by AWO Sandbox Executor
MODEL_OVERRIDE = 'openai/gpt-oss-20b'
