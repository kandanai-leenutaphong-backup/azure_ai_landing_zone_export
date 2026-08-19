import hashlib
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(
    title="Entra User Data API",
    description="Returns demo data scoped to the user validated by Microsoft Entra ID in API Management.",
    version="1.0.0",
)


def _authenticated_user(
    object_id: str | None,
    display_name: str | None,
    username: str | None,
) -> dict[str, str]:
    if not object_id:
        raise HTTPException(status_code=401, detail="Authenticated Entra user context is required")
    return {
        "object_id": object_id,
        "display_name": display_name or username or "Entra user",
        "username": username or "not-provided",
    }


def _stable_number(object_id: str, namespace: str, minimum: int, maximum: int) -> int:
    digest = hashlib.sha256(f"{object_id}:{namespace}".encode()).digest()
    return minimum + int.from_bytes(digest[:4], "big") % (maximum - minimum + 1)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "entra-user-data-api"}


@app.get("/me", operation_id="getMyProfile")
async def get_my_profile(
    x_entra_object_id: str | None = Header(default=None),
    x_entra_display_name: str | None = Header(default=None),
    x_entra_username: str | None = Header(default=None),
) -> dict[str, object]:
    user = _authenticated_user(x_entra_object_id, x_entra_display_name, x_entra_username)
    departments = ["AI Engineering", "Customer Success", "Finance", "Operations"]
    department = departments[_stable_number(user["object_id"], "department", 0, len(departments) - 1)]
    return {
        **user,
        "department": department,
        "demo_employee_number": _stable_number(user["object_id"], "employee", 10000, 99999),
        "data_scope": "current-user-only",
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


@app.get("/me/orders", operation_id="listMyOrders")
async def list_my_orders(
    x_entra_object_id: str | None = Header(default=None),
    x_entra_display_name: str | None = Header(default=None),
    x_entra_username: str | None = Header(default=None),
) -> dict[str, object]:
    user = _authenticated_user(x_entra_object_id, x_entra_display_name, x_entra_username)
    products = ["Copilot Studio Workshop", "Azure AI Sandbox", "Agent Governance Review"]
    orders = []
    for index, product in enumerate(products, start=1):
        order_number = _stable_number(user["object_id"], f"order-{index}", 100000, 999999)
        orders.append(
            {
                "order_id": f"ORD-{order_number}",
                "product": product,
                "status": ["active", "pending", "complete"][order_number % 3],
            }
        )
    return {
        "object_id": user["object_id"],
        "username": user["username"],
        "data_scope": "current-user-only",
        "orders": orders,
    }
