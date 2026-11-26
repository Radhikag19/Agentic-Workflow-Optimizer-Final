"""Agent 5: Tax Classify Agent (Consolidation Chain Step 2 — compact prompt/output)."""

from typing import Any, Dict, Optional
from crewai import Agent
from common.agent_runner import create_crew_agent, run_agent_task
from common.validation import TaxClassifyOutput
from common.metrics import MetricsTracker

AGENT_ID = "tax_classify_agent"
ROLE = "Regional Tax Classifier"
GOAL = "Assign tax jurisdiction, rate percentage, and USD tax amount."
BACKSTORY = "You compute regional tax codes concisely."


def create_agent(llm: Optional[Any] = None) -> Agent:
    return create_crew_agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, agent_id=AGENT_ID, llm=llm)


def run_tax_classify(
    intake_output: Dict[str, Any],
    routing_output: Dict[str, Any],
    agent: Optional[Agent] = None,
    tracker: Optional[MetricsTracker] = None,
) -> Dict[str, Any]:
    active_agent = agent or create_agent()
    rec_id = intake_output.get("record_id", "ORD-000")
    country = intake_output.get("billing_country", "US")
    total = intake_output.get("order_total_usd", 0.0)
    carrier = routing_output.get("carrier_name", "UPS")
    task_desc = (
        f"Classify tax for {rec_id}: country={country}, total={total}, carrier={carrier}. "
        f'Use rates US=8.0, CA=13.0, DE=19.0, UK=20.0, JP=10.0, other=5.0. '
        f'Return ONLY JSON: {{"record_id": "{rec_id}", "tax_jurisdiction": "{country}-TAX", "tax_rate_pct": 8.0, "tax_amount_usd": 0.0}}'
    )
    return run_agent_task(
        agent=active_agent,
        agent_id=AGENT_ID,
        task_description=task_desc,
        expected_output_desc="Valid JSON matching TaxClassifyOutput.",
        output_model=TaxClassifyOutput,
        tracker=tracker,
        agent_name=ROLE,
    )
