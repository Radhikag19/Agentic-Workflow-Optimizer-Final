"""Agent 3: Fraud Screen Agent (Parallel Branch B, independent of Inventory Check)."""

from typing import Any, Dict, Optional
from crewai import Agent
from common.agent_runner import create_crew_agent, run_agent_task
from common.validation import FraudScreenOutput
from common.metrics import MetricsTracker

AGENT_ID = "fraud_screen_agent"
ROLE = "Order Risk Screener"
GOAL = "Classify transaction risk band from customer tier, billing country, and order total."
BACKSTORY = "You classify transaction risk levels concisely from order metadata."


def create_agent(llm: Optional[Any] = None) -> Agent:
    return create_crew_agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, agent_id=AGENT_ID, llm=llm)


def run_fraud_screen(
    intake_output: Dict[str, Any],
    agent: Optional[Agent] = None,
    tracker: Optional[MetricsTracker] = None,
) -> Dict[str, Any]:
    active_agent = agent or create_agent()
    rec_id = intake_output.get("record_id", "ORD-000")
    cust_id = intake_output.get("customer_id", "")
    tier = intake_output.get("customer_tier", "standard")
    total = intake_output.get("order_total_usd", 0.0)
    country = intake_output.get("billing_country", "US")
    task_desc = f"""
Screen risk for order {rec_id}:
- Customer ID: {cust_id}
- Customer Tier: {tier}
- Order Total USD: {total}
- Billing Country: {country}

Rule: If customer_tier is "new" and order_total_usd >= 5000, risk_band="high" and review_flag=true. Else if order_total_usd >= 2000, risk_band="medium" and review_flag=false. Otherwise risk_band="low" and review_flag=false.
Return ONLY valid JSON:
{{
  "record_id": "{rec_id}",
  "risk_band": "low|medium|high",
  "review_flag": true or false,
  "screen_note": "Brief risk summary"
}}
"""
    return run_agent_task(
        agent=active_agent,
        agent_id=AGENT_ID,
        task_description=task_desc,
        expected_output_desc="Valid JSON matching FraudScreenOutput.",
        output_model=FraudScreenOutput,
        tracker=tracker,
        agent_name=ROLE,
    )
