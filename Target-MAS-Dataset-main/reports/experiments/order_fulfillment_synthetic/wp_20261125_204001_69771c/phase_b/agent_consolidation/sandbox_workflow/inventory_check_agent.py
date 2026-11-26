"""Agent 2: Inventory Check Agent (Parallel Branch A, independent of Fraud Screen)."""

import json
from typing import Any, Dict, Optional
from crewai import Agent
from common.agent_runner import create_crew_agent, run_agent_task
from common.validation import InventoryCheckOutput
from common.metrics import MetricsTracker

AGENT_ID = "inventory_check_agent"
ROLE = "Warehouse Inventory Specialist"
GOAL = "Determine warehouse stock availability strictly from SKU quantities and warehouse region."
BACKSTORY = "You evaluate warehouse inventory counts cleanly and concisely."


def create_agent(llm: Optional[Any] = None) -> Agent:
    return create_crew_agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, agent_id=AGENT_ID, llm=llm)


def run_inventory_check(
    intake_output: Dict[str, Any],
    agent: Optional[Agent] = None,
    tracker: Optional[MetricsTracker] = None,
) -> Dict[str, Any]:
    active_agent = agent or create_agent()
    rec_id = intake_output.get("record_id", "ORD-000")
    skus = intake_output.get("sku_items", [])
    wh_region = intake_output.get("warehouse_region", "US-EAST")
    task_desc = f"""
Check stock availability for order {rec_id}:
- Warehouse Region: {wh_region}
- SKU Items: {json.dumps(skus)}

Rule: If every item has stock_available >= qty (and stock_available > 0), in_stock is true and backorder_skus is []. Otherwise in_stock is false and list affected sku codes in backorder_skus.
Return ONLY valid JSON:
{{
  "record_id": "{rec_id}",
  "in_stock": true or false,
  "warehouse_code": "WH-{wh_region}",
  "backorder_skus": [],
  "inventory_note": "Brief factual stock summary"
}}
"""
    return run_agent_task(
        agent=active_agent,
        agent_id=AGENT_ID,
        task_description=task_desc,
        expected_output_desc="Valid JSON matching InventoryCheckOutput.",
        output_model=InventoryCheckOutput,
        tracker=tracker,
        agent_name=ROLE,
    )
