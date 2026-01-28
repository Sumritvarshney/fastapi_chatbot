import datetime
from typing import List
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from config import items_collection 
from model.item_model import ItemRequest, ItemResponse 

router = APIRouter(
    prefix="/api/items",
    tags=["Items Management"]
)

# --- CONFIGURATION ---
SECRET_KEY = "your-very-secret-key-change-this" # Keep this safe!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# This tells FastAPI to look for a "Bearer" token in the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/items/login")

# --- JWT UTILS ---

def create_access_token(data: dict):
    """Generates a signed JWT token with an expiration time."""
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_jwt_token(token: str = Depends(oauth2_scheme)):
    """Decodes and validates the token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

# --- AUTH ROUTES ---

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Standard OAuth2 login. 
    In production, verify form_data.password against a hashed DB password.
    """
    if form_data.username == "admin" and form_data.password == "password123":
        access_token = create_access_token(data={"sub": form_data.username})
        return {"access_token": access_token, "token_type": "bearer"}
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, 
        detail="Incorrect username or password"
    )

# --- ITEM ROUTES ---

@router.post("/", response_model=ItemResponse)
def create_item(item: ItemRequest):
    item_dict = item.model_dump()
    result = items_collection.insert_one(item_dict)
    
    return {
        "id": str(result.inserted_id),
        "name": item.name,
        "message": "Item created successfully"
    }

@router.get("/")
def get_all_items():
    items = []
    for doc in items_collection.find():
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return {"items": items}

@router.get("/{item_id}")
def get_item(item_id: str):
    try:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid Item ID format")
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    item["_id"] = str(item["_id"])
    return item

@router.delete("/{item_id}")
def delete_item(item_id: str, current_user: str = Depends(verify_jwt_token)):
    """
    This route is now protected. 
    It requires a valid JWT token in the header.
    """
    try:
        result = items_collection.delete_one({"_id": ObjectId(item_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"message": f"Item deleted successfully by {current_user}"}