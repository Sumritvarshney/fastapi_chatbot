import uvicorn  
from fastapi import FastAPI

from routers import chat, users, items

app = FastAPI(
    title="Times Internet_intern task User Management API",
    description="learning_task",
    version="1.0.0"
)

@app.get("/api")
def api_root():
    return {
        "status": "Success",
        "message": "Welcome to the Times Internet API",
        "version": "1.0.0",
        "endpoints": {
            "users": "/api/users",
            "items": "/api/items"
        }
    }

app.include_router(users.router)
app.include_router(items.router)
app.include_router(chat.router)

@app.get("/ping")
def health_check():
    return {"status": "Backend is running", "framework": "FastAPI"}


if __name__ == "__main__":
    
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)