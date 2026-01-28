from fastapi import APIRouter, HTTPException, Body, Depends
from bson import ObjectId
from config import users_collections
from model.user_model import UserRequest, UserResponse
from auth import authenticate

router = APIRouter(
    prefix="/api/users",
    tags=["Users Management"]
)

@router.post("/", response_model=UserResponse)
def create_user(user: UserRequest):
    user_dict = user.model_dump()
    users_collections.insert_one(user_dict)
    return {"message": "User created successfully!", "username": user.username}

@router.get("/")
def get_all_users():
    users = []
    for user in users_collections.find():
        user["_id"] = str(user["_id"])
        users.append(user)
    return {"users": users}

@router.get("/{user_id}")
def get_user_by_id(user_id: str):
    try:
        user = users_collections.find_one({"_id": ObjectId(user_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    if user:
        user["_id"] = str(user["_id"])
        return user
    raise HTTPException(status_code=404, detail="User not found")

@router.put("/{user_id}")
def update_user(user_id: str, updated_user: UserRequest, admin_name: str = Depends(authenticate)):
    try:
        oid = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    result = users_collections.update_one({"_id": oid}, {"$set": updated_user.model_dump()})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User updated successfully by {admin_name}"}

@router.delete("/{user_id}")
def delete_user(user_id: str,admin_name: str = Depends(authenticate)):
    try:
        oid = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    result = users_collections.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User deleted successfully by {admin_name}"}