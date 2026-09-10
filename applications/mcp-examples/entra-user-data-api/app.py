import contextlib
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings


mcp = FastMCP(
    "Entra User Data",
    host="0.0.0.0",
    port=8002,
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
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


def _profile(user: dict[str, str]) -> dict[str, object]:
    departments = ["AI Engineering", "Customer Success", "Finance", "Operations"]
    department = departments[_stable_number(user["object_id"], "department", 0, len(departments) - 1)]
    return {
        **user,
        "department": department,
        "demo_employee_number": _stable_number(user["object_id"], "employee", 10000, 99999),
        "data_scope": "current-user-only",
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def _orders(user: dict[str, str]) -> dict[str, object]:
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


def _mcp_user(ctx: Context) -> dict[str, str]:
    request = ctx.request_context.request
    if request is None:
        raise ValueError("HTTP request context is required")
    return _authenticated_user(
        request.headers.get("x-entra-object-id"),
        request.headers.get("x-entra-display-name"),
        request.headers.get("x-entra-username"),
    )


@mcp.tool()
def getMyProfile(ctx: Context) -> dict[str, object]:
    """Return profile data scoped to the authenticated Entra user."""
    return _profile(_mcp_user(ctx))


@mcp.tool()
def listMyOrders(ctx: Context) -> dict[str, object]:
    """Return orders scoped to the authenticated Entra user."""
    return _orders(_mcp_user(ctx))


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Entra User Data API",
    description="Returns demo data scoped to the user validated by Microsoft Entra ID in API Management.",
    version="1.0.0",
    lifespan=lifespan,
)


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
    return _profile(user)


@app.get("/me/orders", operation_id="listMyOrders")
async def list_my_orders(
    x_entra_object_id: str | None = Header(default=None),
    x_entra_display_name: str | None = Header(default=None),
    x_entra_username: str | None = Header(default=None),
) -> dict[str, object]:
    user = _authenticated_user(x_entra_object_id, x_entra_display_name, x_entra_username)
    return _orders(user)


app.mount("/", mcp.streamable_http_app())
