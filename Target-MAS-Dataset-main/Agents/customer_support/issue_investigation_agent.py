"""
Agent 3: Issue Investigation Agent (Customer Support)
Investigates customer ticket details, customer history, and logs.
"""

import json
from pathlib import Path
from crewai import Agent, Task
from common.agent_runner import create_groq_llm_for_agent
from common.settings import DATA_DIR

AGENT_ID = "issue_investigation_agent"

def deterministic_customer_lookup(customer_id: str, ticket_category: str = "") -> dict:
    """Retrieves matching customer profile and category-filtered historical cases from local synthetic datasets."""
    cust_file = DATA_DIR / "customer_support" / "customers.json"
    hist_file = DATA_DIR / "customer_support" / "historical_resolutions.json"

    found_customer = None
    if cust_file.exists():
        with open(cust_file, "r", encoding="utf-8") as f:
            for c in json.load(f):
                if c.get("customer_id") == customer_id:
                    found_customer = c
                    break

    related_history = []
    if hist_file.exists():
        cat_norm = str(ticket_category or "").strip().lower()
        with open(hist_file, "r", encoding="utf-8") as f:
            all_hist = json.load(f)
            if cat_norm:
                related_history = [
                    h for h in all_hist
                    if str(h.get("ticket_category") or "").strip().lower() == cat_norm
                    or (customer_id and h.get("customer_id") == customer_id)
                ][:3]
            elif customer_id:
                related_history = [h for h in all_hist if h.get("customer_id") == customer_id][:3]

    return {
        "customer_profile": found_customer,
        "past_case_sample": related_history
    }

def create_agent(llm=None) -> Agent:
    if llm is None:
        llm, _ = create_groq_llm_for_agent(AGENT_ID)
    return Agent(
        role="Technical Support Investigator",
        goal="Investigate root causes, correlate customer account history, and separate confirmed facts from hypotheses.",
        backstory="A diagnostic engineer reviewing backend logs, customer history, and issue symptoms.",
        llm=llm,
        verbose=False
    )

def create_task(agent: Agent, ticket_data: dict) -> Task:
    cust_id = ticket_data.get("customer_id", "")
    cust_cat = ticket_data.get("category", "")
    customer_context = deterministic_customer_lookup(cust_id, ticket_category=cust_cat)
    description = (
        f"Investigate the customer's reported problem.\n"
        f"Ticket Data:\n{json.dumps(ticket_data, indent=2)}\n\n"
        f"Synthetic Customer Record & System History:\n{json.dumps(customer_context, indent=2)}\n\n"
        f"Instructions:\n"
        f"1. Determine likely root cause based on symptoms and customer tier.\n"
        f"2. Separate confirmed facts from unconfirmed hypotheses.\n"
        f"3. State if further diagnostic data or user verification is required.\n"
        f"Return strictly valid JSON with keys: 'investigation_findings', 'root_cause_hypothesis', 'confirmed_facts', and 'data_gaps'."
    )
    expected_output = "Strictly valid JSON containing investigation_findings, root_cause_hypothesis, confirmed_facts, and data_gaps."
    return Task(
        description=description,
        expected_output=expected_output,
        agent=agent
    )
