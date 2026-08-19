from datetime import UTC, datetime
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Pet Store API",
    description="Example REST API that Azure API Management exposes as MCP tools.",
    version="1.0.0",
)


class PetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    species: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=0, le=100)


class Pet(PetCreate):
    id: int
    created_at: datetime


_pets_lock = Lock()
_pets = [
    Pet(id=1, name="Buddy", species="Dog", age=3, created_at=datetime.now(UTC)),
    Pet(id=2, name="Whiskers", species="Cat", age=2, created_at=datetime.now(UTC)),
]


@app.get("/", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "petstore-api", "version": "1.0.0"}


@app.get("/pets", response_model=list[Pet], operation_id="listPets", tags=["pets"])
def list_pets() -> list[Pet]:
    with _pets_lock:
        return list(_pets)


@app.get("/pets/{pet_id}", response_model=Pet, operation_id="getPet", tags=["pets"])
def get_pet(pet_id: int) -> Pet:
    with _pets_lock:
        for pet in _pets:
            if pet.id == pet_id:
                return pet
    raise HTTPException(status_code=404, detail=f"Pet {pet_id} was not found")


@app.post("/pets", response_model=Pet, status_code=201, operation_id="createPet", tags=["pets"])
def create_pet(request: PetCreate) -> Pet:
    with _pets_lock:
        pet = Pet(
            id=max((item.id for item in _pets), default=0) + 1,
            created_at=datetime.now(UTC),
            **request.model_dump(),
        )
        _pets.append(pet)
        return pet
