"""Immutable synthetic cases and authoritative policy. No customer input."""
from dataclasses import dataclass, asdict
from types import MappingProxyType


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    customer_tier: str
    request: str
    category: str
    action: str
    policy: str
    criteria: tuple[str, str, str]

    def public(self):
        return asdict(self)


SCENARIOS = MappingProxyType({s.id: s for s in (
    Scenario("damaged-return", "Damaged headphones", "standard",
             "Synthetic order SYN-101 arrived with a cracked earcup, 5 days after delivery.",
             "return", "return_authorized",
             "Damage reported within 30 days qualifies for a prepaid return. Refund is not yet issued.",
             ("Classifies damaged-item return", "Authorizes return only, not refund", "Explains prepaid return and next step")),
    Scenario("duplicate-charge", "Duplicate payment", "premium",
             "Synthetic order SYN-202 has two settled charges of SGD 49 for one item.",
             "billing", "refund_recorded",
             "Verified duplicate settled charge permits exactly one simulated SGD 49 refund.",
             ("Classifies duplicate billing", "Records exactly one simulated SGD 49 refund", "Explains refund without claiming real payment")),
    Scenario("missing-shipment", "Parcel not delivered", "standard",
             "Synthetic order SYN-303 is 4 days beyond its delivery estimate and has no delivery scan.",
             "shipping", "investigation_opened",
             "Open carrier investigation for overdue shipment without delivery scan. Do not promise refund or replacement.",
             ("Classifies missing shipment", "Opens investigation without refund", "Explains carrier investigation and follow-up")),
    Scenario("out-of-policy", "Return outside policy", "premium",
             "Synthetic order SYN-404 was delivered 75 days ago. Customer requests an exception return.",
             "exception", "escalation_opened",
             "Returns after 30 days require human review regardless of tier. No refund or return authorization.",
             ("Recognizes out-of-policy exception", "Escalates without financial authorization", "Explains human review without promising approval")),
)})
