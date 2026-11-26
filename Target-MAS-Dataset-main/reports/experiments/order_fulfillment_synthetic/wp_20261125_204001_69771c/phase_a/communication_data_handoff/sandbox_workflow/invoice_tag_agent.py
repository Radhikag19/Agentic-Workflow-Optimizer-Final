"""Agent 6: Invoice Tag Agent (Consolidation Chain Step 3 — compact prompt/output)."""

from typing import Any, Dict, Optional
from crewai import Agent
from common.agent_runner import create_crew_agent, run_agent_task
from common.validation import InvoiceTagOutput
from common.metrics import MetricsTracker

AGENT_ID = "invoice_tag_agent"
ROLE = "Ledger Invoice Tagger"
GOAL = "Attach general ledger account code, invoice tag, and billing batch."
BACKSTORY = "You tag invoices concisely."


def create_agent(llm: Optional[Any] = None) -> Agent:
    return create_crew_agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, agent_id=AGENT_ID, llm=llm)


def run_invoice_tag(
    intake_output: Dict[str, Any],
    tax_output: Dict[str, Any],
    agent: Optional[Agent] = None,
    tracker: Optional[MetricsTracker] = None,
) -> Dict[str, Any]:
    active_agent = agent or create_agent()
    rec_id = intake_output.get("record_id", "ORD-000")
    tier = intake_output.get("customer_tier", "standard")
    juris = tax_output.get("tax_jurisdiction", "US-TAX")
    tax_usd = tax_output.get("tax_amount_usd", 0.0)
    task_desc = (
        f"Tag invoice for {rec_id}: tier={tier}, tax_jurisdiction={juris}, tax_amount_usd={tax_usd}. "
        f'Return ONLY JSON: {{"record_id": "{rec_id}", "gl_account_code": "GL-4010", "invoice_tag": "INV-{rec_id}", "billing_batch": "BATCH-{tier.upper()}"}}'
    )
    return run_agent_task(
        agent=active_agent,
        agent_id=AGENT_ID,
        task_description=task_desc,
        expected_output_desc="Valid JSON matching InvoiceTagOutput.",
        output_model=InvoiceTagOutput,
        tracker=tracker,
        agent_name=ROLE,
    )
