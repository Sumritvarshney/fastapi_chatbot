from pydantic import BaseModel

class UserRequest(BaseModel):
    username: str
    age: int 
    email: str

class UserResponse(BaseModel):
    message: str
    username: str