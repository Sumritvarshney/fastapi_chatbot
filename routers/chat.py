from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sys
import logging
from chatbot.agent import run_chat

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/chat", tags=["Chatbot"])


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


@router.post("/", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        logger.info("STARTINGGGGGGGGGGGGGGGGG (Log Message)")
        result = run_chat(message=req.message, thread_id=req.thread_id)
        return result
    except RuntimeError as e:
        # Typically missing API keys/config.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chatbot error: {e}")

