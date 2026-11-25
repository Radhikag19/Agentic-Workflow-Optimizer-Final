def run_workflow(input_data=None):
    return {"ok": True}

# Applied by AWO Sandbox Executor
HANDOFF_PROJECTIONS = {'a1->a3': {'candidate_id': 'H1', 'producer_agent': 'a1', 'consumer_agent': 'a3', 'retained_fields': ['candidate_id', 'skills'], 'excluded_fields': ['extra'], 'consumer_required_fields': ['skills'], 'typed_delta_projection': True}}

def project_handoff_payload(producer, consumer, payload):
    """Project approved compact fields on configured edges; pass through unapproved edges unchanged."""
    if not isinstance(payload, dict):
        return payload
    spec = HANDOFF_PROJECTIONS.get(f'{producer}->{consumer}')
    if not spec:
        return payload
    retained = set(spec.get('retained_fields') or [])
    return {k: v for k, v in payload.items() if k in retained}
