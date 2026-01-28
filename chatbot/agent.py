import os
import json
from typing import Any, Dict, List, Optional, Literal, TypedDict

import httpx
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# --- 1. Client & Tool Definitions ---

def _api_base_url() -> str:
    port = os.getenv("PORT", "8000")
    return os.getenv("API_BASE_URL", f"http://localhost:{port}").rstrip("/")

def _http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))

@tool
def list_users(limit: int = 10, offset: int = 0) -> Dict[str, Any]:
    """
    List all users from the API with pagination.
    Args:
        limit: Number of records to fetch (default 10).
        offset: Number of records to skip (default 0).
    """
    url = f"{_api_base_url()}/api/users"
   
    params = {"limit": limit, "offset": offset}
    
    with _http_client() as client:
        r = client.get(url, params=params)
        return r.json()

@tool
def get_user(user_id: str) -> Dict[str, Any]:
    """Get a single user's details by ID."""
    url = f"{_api_base_url()}/api/users/{user_id}"
    with _http_client() as client:
        r = client.get(url)
        return r.json()

@tool
def list_items(limit: int = 10, offset: int = 0) -> Dict[str, Any]:
    """
    List all items from the API with pagination.
    Args:
        limit: Number of records to fetch (default 10).
        offset: Number of records to skip (default 0).
    """
    url = f"{_api_base_url()}/api/items"
    params = {"limit": limit, "offset": offset}
    
    with _http_client() as client:
        r = client.get(url, params=params)
        return r.json()

@tool
def get_item(item_id: str) -> Dict[str, Any]:
    """Get a single item's details by ID."""
    url = f"{_api_base_url()}/api/items/{item_id}"
    with _http_client() as client:
        r = client.get(url)
        return r.json()

# --- 2. State Definition ---

class AgentState(TypedDict):
    messages: List[Any]
    intent: Literal["user", "item", "unknown"]
    entity_id: Optional[str]
    # NEW: Store pagination params here (e.g. {'limit': 5, 'offset': 10})
    page_params: Optional[Dict[str, int]] 
    api_data: Optional[Dict]

# --- 3. Nodes ---

def router_node(state: AgentState):
    """
    Analyzes request for Intent + ID + Pagination.
    """
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # Updated Prompt to extract pagination
    system_prompt = (
        "Analyze the user's request.\n"
        "Return a JSON object with THREE keys:\n"
        "1. 'intent': strictly 'user' or 'item'. Default 'user'.\n"
        "2. 'entity_id': null if listing, or the string ID if specific.\n"
        "3. 'page_params': A dictionary with 'limit' and 'offset' integers if mentioned.\n"
        "   - Default to { 'limit': 10, 'offset': 0 } if not specified.\n"
        "   - Example: 'Show me 5 users' -> { 'limit': 5, 'offset': 0 }\n"
        "   - Example: 'Next 10 items' -> { 'limit': 10, 'offset': 10 } (infer logic if possible, otherwise default).\n"
    )
    
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=last_message)
    ])
    
    try:
        clean_content = response.content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean_content)
        intent = parsed.get("intent", "user")
        entity_id = parsed.get("entity_id")
        # Extract page params safely
        page_params = parsed.get("page_params", {"limit": 10, "offset": 0})
    except:
        intent = "user"
        entity_id = None
        page_params = {"limit": 10, "offset": 0}
        
    return {"intent": intent, "entity_id": entity_id, "page_params": page_params}

def fetch_user_node(state: AgentState):
    """Execute User API calls."""
    entity_id = state.get("entity_id")
    page_params = state.get("page_params") or {}

    try:
        if entity_id:
            # Single ID fetch (no pagination)
            data = get_user.invoke({"user_id": entity_id})
        else:
            # List fetch (WITH pagination)
            # We pass the dictionary directly; LangChain maps keys to arguments
            data = list_users.invoke(page_params)
    except Exception as e:
        data = {"error": str(e)}
        
    return {"api_data": data}

def fetch_item_node(state: AgentState):
    """Execute Item API calls."""
    entity_id = state.get("entity_id")
    page_params = state.get("page_params") or {}

    try:
        if entity_id:
            data = get_item.invoke({"item_id": entity_id})
        else:
            data = list_items.invoke(page_params)
    except Exception as e:
        data = {"error": str(e)}

    return {"api_data": data}

def rephrase_node(state: AgentState):
    """Summarize the API data."""
    data = state.get("api_data")
    messages = state["messages"]
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    prompt = (
        "You are a helpful assistant. \n"
        f"The user asked: '{messages[-1].content}'\n"
        f"The API returned: {json.dumps(data)}\n\n"
        "Please provide a clear, natural language answer summarizing this data. "
        "If it is a list, mention how many items were retrieved."
        "If there was an error, apologize and explain it."
    )
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    return {"messages": [response]}

# ---  Graph Construction ---

def build_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("user_tool", fetch_user_node)
    workflow.add_node("item_tool", fetch_item_node)
    workflow.add_node("rephrase", rephrase_node)

    workflow.set_entry_point("router")

    def route_decision(state: AgentState):
        if state["intent"] == "item":
            return "item_tool"
        return "user_tool"

    workflow.add_conditional_edges(
        "router",
        route_decision,
        {
            "user_tool": "user_tool",
            "item_tool": "item_tool"
        }
    )

    workflow.add_edge("user_tool", "rephrase")
    workflow.add_edge("item_tool", "rephrase")
    workflow.add_edge("rephrase", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

# --- 5. Execution Wrapper ---

def run_chat(message: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
    agent = build_agent()
    tid = thread_id or "default"

    initial_state = {"messages": [HumanMessage(content=message)]}
    
    result = agent.invoke(
        initial_state,
        config={"configurable": {"thread_id": tid}},
    )
    
    answer = result["messages"][-1].content
    return {"answer": answer, "thread_id": tid}