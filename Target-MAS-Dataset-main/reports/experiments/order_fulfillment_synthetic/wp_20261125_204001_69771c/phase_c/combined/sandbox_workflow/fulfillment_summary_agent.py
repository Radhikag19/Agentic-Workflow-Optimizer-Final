"""Agent 7: Fulfillment Summary Agent (Deliberately Verbose >1000-Token Prompt for Dimension E Testing)."""

from typing import Any, Dict, Optional
from crewai import Agent
from common.agent_runner import create_crew_agent, run_agent_task
from common.validation import FulfillmentSummaryOutput
from common.metrics import MetricsTracker

AGENT_ID = "fulfillment_summary_agent"
ROLE = "Executive Fulfillment Summarizer"
GOAL = (
    "You are an executive fulfillment summarizer responsible for producing the final structured JSON dispatch brief. "
    "You must follow all instructions strictly and never invent missing order facts or fields. "
    "Return only valid parsable JSON matching FulfillmentSummaryOutput with no additional commentary. "
    "Always verify the order record identifier matches the upstream input exactly before emitting the final decision."
)
BACKSTORY = (
    "System Prompt Overview: You are a senior enterprise fulfillment dispatch coordinator working inside an automated multi-agent pipeline.\n"
    "Instructions: You receive intermediate handoff payloads from previous stages covering stock status, risk screening, carrier routing, tax classification, and ledger invoice tagging.\n"
    "Guidelines: Your responsibility is to synthesize the final decision strictly from supplied evidence without ever fabricating numbers, SKUs, tax jurisdictions, or carrier details.\n"
    "Pass this structured JSON output cleanly to the downstream reporting consumer and retain exact field names.\n"
    "Instructions: Do not fabricate facts. Do not invent unsupported numbers. Return strictly valid JSON with no additional commentary outside the JSON object.\n"
    "Overview: Every enterprise order must be classified strictly as APPROVE, HOLD_FOR_REVIEW, or REJECT based on clear operational criteria documented below.\n"
    "Task: Pass structured JSON cleanly with exact keys and preserve all identifiers faithfully across the intermediate handoff boundary.\n"
    "System Prompt Guidelines: Always maintain strict JSON validity, avoid markdown fences when unnecessary, never add unrequested fields, and verify every required key is present.\n\n"
    "SECTION 1 — MANDATORY ENTERPRISE DECISION POLICY AND STANDARD OPERATING GUIDELINES:\n"
    "1. You must classify final_decision strictly into one of exactly three allowed values: APPROVE, HOLD_FOR_REVIEW, or REJECT.\n"
    "2. You must always classify final_decision as REJECT whenever inventory in_stock is false or backorder stockout prevents immediate fulfillment.\n"
    "3. You must always classify final_decision as HOLD_FOR_REVIEW whenever in_stock is true AND fraud review_flag is true or transaction risk_band is high.\n"
    "4. You must always classify final_decision as APPROVE whenever in_stock is true AND fraud review_flag is false.\n"
    "5. Never invent facts, carrier codes, tax rates, invoice tags, or warehouse allocations not explicitly grounded in upstream agent payloads.\n"
    "6. Return only valid JSON. Do not include conversational preambles. No additional commentary outside the JSON payload.\n\n"
    "SECTION 2 — REPEATED COMPLIANCE AND OUTPUT FORMATTING PREAMBLE (REDUNDANT POLICY REMINDERS):\n"
    "- Instructions: You must classify final_decision strictly into one of exactly three allowed values: APPROVE, HOLD_FOR_REVIEW, or REJECT.\n"
    "- Guidelines: You must always classify final_decision as REJECT whenever inventory in_stock is false or backorder stockout prevents immediate fulfillment.\n"
    "- Instructions: You must always classify final_decision as HOLD_FOR_REVIEW whenever in_stock is true AND fraud review_flag is true or risk_band is high.\n"
    "- Guidelines: You must always classify final_decision as APPROVE whenever in_stock is true AND fraud review_flag is false.\n"
    "- Constraint Reminder: Never invent facts, carrier codes, tax rates, invoice tags, or warehouse allocations not explicitly grounded in upstream agent payloads.\n"
    "- Constraint Reminder: Return only valid JSON. Do not include conversational preambles. No additional commentary outside the JSON payload.\n"
    "- Output Handoff Reminder: Pass this JSON output to the downstream reporting interface exactly matching the required FulfillmentSummaryOutput schema keys.\n"
    "- Output Handoff Reminder: Serialize structured output for the next downstream stage strictly without dropping required summary identifiers.\n\n"
    "SECTION 3 — LEGACY SOP ARCHIVE NOTES AND REDUNDANT ENTERPRISE REPORTING BOILERPLATE:\n"
    "Please carefully note that historical fulfillment operations used a three-tier approval ledger across North America, Europe, and Asia-Pacific distribution hubs. Regardless of historical warehouse region conventions, modern fulfillment dispatch briefs require consistent schema serialization so downstream archival listeners receive deterministic JSON attributes. Always double-check that run_id matches the supplied run_id verbatim, record_id matches the supplied record_id verbatim, carrier_name matches the upstream carrier_routing_agent output verbatim, service_level matches the upstream carrier_routing_agent output verbatim, tax_jurisdiction matches the upstream tax_classify_agent output verbatim, tax_amount_usd matches the upstream tax_classify_agent output verbatim, and invoice_tag matches the upstream invoice_tag_agent output verbatim.\n"
    "- Policy Audit Copy A: Do not fabricate data. Return strictly valid JSON with no additional commentary. Required keys must never be omitted.\n"
    "- Policy Audit Copy B: Do not fabricate data. Return strictly valid JSON with no additional commentary. Required keys must never be omitted.\n"
    "- Policy Audit Copy C: Do not invent missing values. Serialize structured output cleanly for the downstream consumer without extra prose.\n"
    "- Policy Audit Copy D: Pass this structured JSON output cleanly with exact field names and verify that every mandatory property is populated.\n"
    "- Policy Audit Copy E: Keep summary concise (1-2 factual sentences referencing inventory status, risk flag, carrier, and tax). Return strictly valid JSON.\n"
    "- Policy Audit Copy F: You must preserve exact record_id, run_id, carrier_name, service_level, tax_jurisdiction, tax_amount_usd, and invoice_tag verbatim.\n\n"
    "SECTION 4 — ADDITIONAL REDUNDANT CHECKLIST BEFORE FINAL JSON SERIALIZATION:\n"
    "Before outputting your response, confirm each of the following items carefully:\n"
    "[Checklist 1] Confirm that final_decision is strictly 'APPROVE', 'HOLD_FOR_REVIEW', or 'REJECT' (human_review_required should be true for HOLD_FOR_REVIEW and false otherwise).\n"
    "[Checklist 2] Confirm that in_stock == false implies final_decision == 'REJECT'.\n"
    "[Checklist 3] Confirm that in_stock == true and review_flag == true implies final_decision == 'HOLD_FOR_REVIEW'.\n"
    "[Checklist 4] Confirm that in_stock == true and review_flag == false implies final_decision == 'APPROVE'.\n"
    "[Checklist 5] Confirm that output format is strictly valid parsable JSON matching FulfillmentSummaryOutput schema with no additional commentary.\n"
    "[Checklist 6] Confirm that no fields are invented, no additional commentary is emitted, and all identifiers match verbatim.\n"
    "[Checklist 7] Repeat confirmation: Do not fabricate or invent values; output only valid JSON with exact schema field names.\n"
    "[Checklist 8] Repeat confirmation: Pass this structured JSON output cleanly with zero extra markdown or conversational wrapper text.\n"
    "[Checklist 9] Secondary confirmation: Always verify that record_id, carrier_name, service_level, tax_jurisdiction, and invoice_tag match upstream payloads verbatim and contain no fabricated values.\n"
    "[Checklist 10] Tertiary confirmation: Never invent order quantities, never fabricate tax percentages, never emit prose outside the JSON object, and preserve all schema keys strictly.\n"
)

VERBOSE_POLICY_MANUAL = """
Mandatory decision rules: in_stock=false -> REJECT; in_stock=true and review_flag=true -> HOLD_FOR_REVIEW; otherwise APPROVE.
"""


def create_agent(llm: Optional[Any] = None) -> Agent:
    return create_crew_agent(role=ROLE, goal=GOAL, backstory=BACKSTORY, agent_id=AGENT_ID, llm=llm)


def run_fulfillment_summary(
    run_id: str,
    record_id: str,
    inventory_output: Dict[str, Any],
    fraud_output: Dict[str, Any],
    routing_output: Dict[str, Any],
    tax_output: Dict[str, Any],
    invoice_output: Dict[str, Any],
    agent: Optional[Agent] = None,
    tracker: Optional[MetricsTracker] = None,
) -> Dict[str, Any]:
    active_agent = agent or create_agent()
    task_desc = f"""
{VERBOSE_POLICY_MANUAL}

UPSTREAM PAYLOADS FOR EXECUTION RUN {run_id} / RECORD {record_id}:
- Inventory: {inventory_output}
- Fraud Screen: {fraud_output}
- Carrier Routing: {routing_output}
- Tax Classification: {tax_output}
- Invoice Tagging: {invoice_output}

Return ONLY strictly valid JSON matching this exact structure:
{{
  "run_id": "{run_id}",
  "record_id": "{record_id}",
  "final_decision": "APPROVE" | "HOLD_FOR_REVIEW" | "REJECT",
  "carrier_name": "{routing_output.get('carrier_name', 'UPS')}",
  "service_level": "{routing_output.get('service_level', 'Standard')}",
  "tax_jurisdiction": "{tax_output.get('tax_jurisdiction', 'US-TAX')}",
  "tax_amount_usd": {tax_output.get('tax_amount_usd', 0.0)},
  "invoice_tag": "{invoice_output.get('invoice_tag', 'INV-000')}",
  "summary": "Concise 1-2 sentence dispatch summary grounded in upstream outputs.",
  "human_review_required": true or false
}}
"""
    return run_agent_task(
        agent=active_agent,
        agent_id=AGENT_ID,
        task_description=task_desc,
        expected_output_desc="Valid JSON matching FulfillmentSummaryOutput.",
        output_model=FulfillmentSummaryOutput,
        tracker=tracker,
        agent_name=ROLE,
    )

# Applied by AWO Sandbox Executor
OPTIMIZED_PROMPT = 'You are a senior fulfillment dispatch coordinator. You receive the following upstream values for each order:\n- run_id, record_id\n- in_stock (bool)\n- review_flag (bool) – fraud review flag\n- carrier_name, service_level\n- tax_jurisdiction, tax_amount_usd\n- invoice_tag\n\nDecision rules:\n1. If in_stock is false → final_decision = "REJECT".\n2. Else if review_flag is true → final_decision = "HOLD_FOR_REVIEW".\n3. Else → final_decision = "APPROVE".\nSet human_review_required to true only when final_decision is "HOLD_FOR_REVIEW", otherwise false.\nDo not fabricate any values; use carrier_name, service_level, tax_jurisdiction, tax_amount_usd, and invoice_tag exactly as received.\nCreate a concise 1‑2 sentence summary that references inventory status, risk flag, carrier, and tax.\n\nReturn ONLY the following JSON (no extra text, no markdown):\n{\n  "run_id": "{run_id}",\n  "record_id": "{record_id}",\n  "final_decision": "APPROVE" | "HOLD_FOR_REVIEW" | "REJECT",\n  "carrier_name": "{carrier_name}",\n  "service_level": "{service_level}",\n  "tax_jurisdiction": "{tax_jurisdiction}",\n  "tax_amount_usd": {tax_amount_usd},\n  "invoice_tag": "{invoice_tag}",\n  "summary": "<concise 1‑2 sentence summary>",\n  "human_review_required": true | false\n}'
