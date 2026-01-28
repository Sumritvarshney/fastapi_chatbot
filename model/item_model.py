from pydantic import BaseModel
from typing import Optional

class ItemRequest(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
    category: str

class ItemResponse(BaseModel):
    id: str
    name: str
    message: str