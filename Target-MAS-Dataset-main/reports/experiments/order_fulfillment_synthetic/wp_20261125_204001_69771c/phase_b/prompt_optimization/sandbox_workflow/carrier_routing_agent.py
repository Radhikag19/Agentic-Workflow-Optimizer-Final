"""Agent 4: Carrier Routing Agent (Consolidation Chain Step 1 — compact prompt/output)."""

from typing import Any, Dict, Optional
from crewai import Agent
from common.agent_runner import create_crew_agent, run_agent_task
from common.validation import CarrierRoutingOutput
from common.metrics import MetricsTracker

AGENT_ID = "carrier_routing_agent"
ROLE = "Carrier Zone Router"
GOAL = "Assign carrier name, service level, and transit days."
BACKSTORY = "You route shipments cleanly."


def create_agent(llm: Optional[Any] = None) -> Agent:
    return create_crew_agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, agent_id=AGENT_ID, llm=llm)


def run_carrier_routing(
    intake_output: Dict[str, Any],
    inventory_output: Dict[str, Any],
    fraud_output: Dict[str, Any],
    agent: Optional[Agent] = None,
    tracker: Optional[MetricsTracker] = None,
) -> Dict[str, Any]:
    active_agent = agent or create_agent()
    rec_id = intake_output.get("record_id", "ORD-000")
    region = intake_output.get("shipping_region", "US-EAST")
    speed = intake_output.get("shipping_speed", "standard")
    in_stock = inventory_output.get("in_stock", True)
    review_flag = fraud_output.get("review_flag", False)
    task_desc = (
        f"Assign carrier for {rec_id}: region={region}, speed={speed}, in_stock={in_stock}, review_flag={review_flag}. "
        f'Return ONLY JSON: {{"record_id": "{rec_id}", "carrier_name": "UPS|DHL|FedEx", "service_level": "Standard|Expedited|Overnight", "estimated_days": 1|2|5}}'
    )
    return run_agent_task(
        agent=active_agent,
        agent_id=AGENT_ID,
        task_description=task_desc,
        expected_output_desc="Valid JSON matching CarrierRoutingOutput.",
        output_model=CarrierRoutingOutput,
        tracker=tracker,
        agent_name=ROLE,
    )

# Applied by AWO Sandbox Executor
OPTIMIZED_PROMPT = 'You are a unified agent that processes shipment records sequentially.\n\n**Inputs (per record)**: rec_id, shipping_region, shipping_speed, warehouse_code, in_stock, risk_band, review_flag, billing_country, order_total_usd, customer_tier.\n\n**Step 1 – Carrier Routing**: Based on shipping_region, shipping_speed, in_stock, risk_band, and review_flag select:\n- carrier_name: "UPS", "DHL" or "FedEx" (region & speed dependent)\n- service_level: "Standard", "Expedited" or "Overnight" (matches speed)\n- estimated_days: 1 for Overnight, 2 for Expedited, 5 for Standard\nOutput JSON fields: record_id (use rec_id), carrier_name, service_level, estimated_days.\n\n**Step 2 – Tax Classification**: Using carrier_name, service_level, billing_country, and order_total_usd compute:\n- tax_jurisdiction = "{billing_country}-TAX"\n- tax_rate_pct per table: US=8.0, CA=13.0, DE=19.0, UK=20.0, JP=10.0, other=5.0\n- tax_amount_usd = order_total_usd * tax_rate_pct / 100\nOutput JSON fields: record_id, tax_jurisdiction, tax_rate_pct, tax_amount_usd.\n\n**Step 3 – Invoice Tagging**: Using customer_tier, tax_jurisdiction, and tax_amount_usd set:\n- gl_account_code = "GL-4010"\n- invoice_tag = "INV-{record_id}"\n- billing_batch = "BATCH-{customer_tier.upper()}"\nOutput JSON fields: record_id, gl_account_code, invoice_tag, billing_batch.\n\n**Final Output**: Merge the three JSON objects into one JSON per record containing all fields: record_id, carrier_name, service_level, estimated_days, tax_jurisdiction, tax_rate_pct, tax_amount_usd, gl_account_code, invoice_tag, billing_batch. Return only this JSON, no additional text.'
