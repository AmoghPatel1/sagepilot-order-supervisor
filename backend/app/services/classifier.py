# Lightweight classifier — no LLM needed here.
# Maps event types to urgency. Urgent = wake agent immediately.
# Non-urgent = agent stays asleep until scheduled wake_at.

URGENT_EVENTS = {
    "payment_failed",
    "refund_requested", 
    "customer_message_received",
    "shipment_delayed",
    "delivered",
}

NON_URGENT_EVENTS = {
    "order_created",
    "payment_confirmed",
    "shipment_created",
    "no_update_for_n_hours",
}

def is_urgent(event_type: str) -> bool:
    """
    Returns True if the event should wake the agent immediately.
    Unknown events are treated as urgent (safe default).
    """
    if event_type in URGENT_EVENTS:
        return True
    if event_type in NON_URGENT_EVENTS:
        return False
    # Unknown event — escalate to be safe
    return True