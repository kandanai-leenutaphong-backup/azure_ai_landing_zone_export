import ast
import base64
import contextlib
import json
import operator
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

mcp = FastMCP(
    "Math and Text Utilities",
    host="0.0.0.0",
    port=8001,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("Only numbers, parentheses, and +, -, *, / operators are allowed")


def _calculate(expression: str) -> str:
    if len(expression) > 200:
        raise ValueError("Expression must be 200 characters or fewer")
    result = _evaluate(ast.parse(expression, mode="eval"))
    return f"{expression} = {result}"


@mcp.tool()
def calculate(expression: str) -> str:
    """Safely evaluate an arithmetic expression."""
    return _calculate(expression)


def _fibonacci(count: int) -> dict[str, object]:
    if count < 1 or count > 50:
        raise ValueError("count must be between 1 and 50")
    sequence = [0, 1]
    while len(sequence) < count:
        sequence.append(sequence[-1] + sequence[-2])
    sequence = sequence[:count]
    return {"count": count, "sequence": sequence, "last": sequence[-1]}


@mcp.tool()
def fibonacci(count: int) -> dict[str, object]:
    """Generate up to 50 Fibonacci numbers."""
    return _fibonacci(count)


def _is_prime(number: int) -> dict[str, object]:
    if number < 2:
        return {"number": number, "is_prime": False}
    divisor = 2
    while divisor * divisor <= number:
        if number % divisor == 0:
            return {"number": number, "is_prime": False, "divisor": divisor}
        divisor += 1
    return {"number": number, "is_prime": True}


@mcp.tool()
def is_prime(number: int) -> dict[str, object]:
    """Check whether an integer is prime."""
    return _is_prime(number)


def _text_transform(text: str, operation: str) -> str:
    operations = {
        "uppercase": str.upper,
        "lowercase": str.lower,
        "title": str.title,
        "reverse": lambda value: value[::-1],
        "length": lambda value: str(len(value)),
    }
    if operation not in operations:
        raise ValueError(f"operation must be one of: {', '.join(operations)}")
    return operations[operation](text)


@mcp.tool()
def text_transform(text: str, operation: str) -> str:
    """Transform text with uppercase, lowercase, title, reverse, or length."""
    return _text_transform(text, operation)


@mcp.tool()
def word_count(text: str) -> dict[str, int]:
    """Count characters, words, lines, and sentences."""
    sentences = [part for part in text.replace("!", ".").replace("?", ".").split(".") if part.strip()]
    return {
        "characters": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines()) or 1,
        "sentences": len(sentences),
    }


@mcp.tool()
def base64_transform(text: str, operation: str) -> str:
    """Encode or decode UTF-8 text with Base64."""
    if operation == "encode":
        return base64.b64encode(text.encode()).decode()
    if operation == "decode":
        return base64.b64decode(text.encode(), validate=True).decode()
    raise ValueError("operation must be encode or decode")


@mcp.tool()
def current_time() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(UTC).isoformat()


@mcp.tool()
def date_difference(date1: str, date2: str) -> str:
    """Return the absolute difference between two ISO dates."""
    first = datetime.fromisoformat(date1)
    second = datetime.fromisoformat(date2)
    days = abs((second - first).days)
    return json.dumps({"date1": date1, "date2": date2, "difference_days": days})


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "math-mcp-server", "version": "1.0.0"})


async def calculate_api(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse({"result": _calculate(str(body["expression"]))})


async def fibonacci_api(request: Request) -> JSONResponse:
    return JSONResponse(_fibonacci(int(request.path_params["count"])))


async def is_prime_api(request: Request) -> JSONResponse:
    return JSONResponse(_is_prime(int(request.path_params["number"])))


async def text_transform_api(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse({"result": _text_transform(str(body["text"]), str(body["operation"]))})


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/", health),
        Route("/tools/calculate", calculate_api, methods=["POST"]),
        Route("/tools/fibonacci/{count:int}", fibonacci_api),
        Route("/tools/is-prime/{number:int}", is_prime_api),
        Route("/tools/text-transform", text_transform_api, methods=["POST"]),
        Mount("/mcp", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)
