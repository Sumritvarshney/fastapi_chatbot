import os
import json
from typing import Any, Dict, List, Optional, Literal, TypedDict

import httpx
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# --- 1. CONFIGURATION ---

SPOG_TOKEN = ""
API_BASE_URL = ""
LLAMA_URL = ""

# --- 2. CLIENTS ---

def call_llama(messages: List[Dict[str, str]]) -> str:
    payload = {
        "messages": messages,
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "temperature": 0.0
    }
    headers = {"Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(LLAMA_URL, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Llama Error: {e}")
        return "{}"

def _authenticated_client() -> httpx.Client:
    headers = {"x-token": SPOG_TOKEN, "Content-Type": "application/json"}
    return httpx.Client(headers=headers, timeout=15.0, follow_redirects=True)

# --- 3. TOOLS ---

@tool
def list_tickets(limit: int = 20, offset: int = 0, search_query: str = "") -> Any:
    """Fetches raw tickets."""
    url = f"{API_BASE_URL}/incident/ticket"
    
    # Calculate Page: (Offset // Limit) + 1
    page = (offset // limit) + 1
    
    filters = {
        "Created On": {"range": "Last 90 Days"},
        "Issue Type": ["63e22aec05dd11e5dfa6901b"],
        "Incident Linked": ["false"],
        "search": search_query or ""
    }
    
    params = {
        "page": page, 
        "limit": limit, 
        "filters": json.dumps(filters),
        "fields": "issue_id,summary,priority,assignee,created_by,status,updated_on"
    }
    
    print(f"DEBUG TOOL: Fetching Page {page} (Offset={offset}, Search='{search_query}')")
    
    with _authenticated_client() as client:
        r = client.get(url, params=params)
        if r.status_code != 200:
            return {"error": f"API Error {r.status_code}"}
        
        data = r.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

@tool
def filter_tickets_tool(tickets: List[Dict], assignee_name: Optional[str] = None, status_name: Optional[str] = None) -> List[Dict]:
    """Client-side filtering with ROBUST STRING MATCHING."""
    if not isinstance(tickets, list):
        return []

    filtered = []

    def extract_names(field_data) -> List[str]:
        names = []
        if isinstance(field_data, list):
            for item in field_data:
                names.extend(extract_names(item))
        elif isinstance(field_data, dict):
            for key in ["name", "full_name", "email", "firstName"]:
                if key in field_data and field_data[key]:
                    names.append(str(field_data[key]))
        elif isinstance(field_data, str):
            names.append(field_data)
        return names

    print(f"DEBUG FILTER: Checking {len(tickets)} tickets. AssigneeFilter='{assignee_name}' StatusFilter='{status_name}'")

    for ticket in tickets:
        match_person = True
        match_status = True
        
        # 1. Check Person
        if assignee_name:
            match_person = False
            target = assignee_name.lower().strip()
            all_names = extract_names(ticket.get("assignee")) + extract_names(ticket.get("created_by"))
            for name in all_names:
                n = name.lower().strip()
                if target in n or n in target:
                    match_person = True
                    break
        
        # 2. Check Status
        if status_name:
            match_status = False
            target_status = status_name.lower().strip()
            all_statuses = extract_names(ticket.get("status"))
            for s_name in all_statuses:
                if target_status in s_name.lower():
                    match_status = True
                    break
                
        if match_person and match_status:
            filtered.append(ticket)
            
    return filtered

# --- 4. STATE MANAGEMENT & ROUTER ---

class AgentState(TypedDict):
    messages: List[Any]
    search_query: Optional[str]
    assignee: Optional[str]
    status: Optional[str]
    page_params: Optional[Dict[str, int]]
    search_mode: Literal["single_page", "deep_scan"] 
    recursion_count: int
    api_data: Optional[Dict]

def router_node(state: AgentState):
    messages = state["messages"]
    
    current_params = state.get("page_params") or {"limit": 20, "offset": 0}
    current_offset = current_params.get("offset", 0)
    
    # [FIX] Added 'target_page' integer field to handle math in Python
    llama_messages = [
        {"role": "system", "content": (
            "You are an IT Support Router. Return JSON ONLY.\n"
            f"CURRENT STATE: Offset is {current_offset}.\n"
            "INSTRUCTIONS:\n"
            "1. IF user says 'Page X' -> set 'target_page': X (Integer). DO NOT CALCULATE OFFSET.\n"
            "2. IF user says 'Next' -> set 'target_page': null, 'action': 'next'.\n"
            "3. IF user says 'Previous' -> set 'target_page': null, 'action': 'prev'.\n"
            "\n"
            "SEARCH MODES:\n"
            "- IF 'target_page' is set -> 'single_page'.\n"
            "- IF User says 'Show ALL tickets for X' AND NO PAGE SPECIFIED -> 'deep_scan'.\n"
            "\n"
            "FILTERING:\n"
            "- 'Assigned to X' -> assignee='X', search_query=''.\n"
            "- 'Status X' -> status='X', search_query=''.\n"
            "- 'Reset' -> assignee=null, status=null.\n"
            "\n"
            "Output Format: {\"search_query\": \"\", \"assignee\": null, \"status\": null, \"target_page\": null, \"action\": null, \"search_mode\": \"single_page\"}"
        )}
    ]
    
    for m in messages[-4:]:
        role = "user" if isinstance(m, HumanMessage) else "assistant"
        llama_messages.append({"role": role, "content": m.content})
        
    response = call_llama(llama_messages)
    
    try:
        clean = response.replace("```json", "").replace("```", "").strip()
        if "{" in clean: clean = clean[clean.find("{"):clean.rfind("}")+1]
        parsed = json.loads(clean)
        
        # [PYTHON MATH LOGIC] - 100% Reliable
        new_offset = current_offset
        target_page = parsed.get("target_page")
        action = parsed.get("action")
        
        if target_page and isinstance(target_page, int):
            # Page 1 -> (1-1)*20 = 0
            # Page 4 -> (4-1)*20 = 60
            new_offset = (target_page - 1) * 20
            if new_offset < 0: new_offset = 0
            
        elif action == "next":
            new_offset += 20
        elif action == "prev":
            new_offset -= 20
            if new_offset < 0: new_offset = 0
            
        # [GUARDRAIL] Clear search query if filters exist
        s_query = parsed.get("search_query") or ""
        if parsed.get("assignee") or parsed.get("status"):
            s_query = ""

        return {
            "search_query": s_query,
            "assignee": parsed.get("assignee"),
            "status": parsed.get("status"),
            "search_mode": parsed.get("search_mode", "single_page"),
            "page_params": {"limit": 20, "offset": new_offset}, # Updated Offset
            "recursion_count": 0, 
            "api_data": []
        }
    except:
        return {"search_query": "", "search_mode": "single_page", "page_params": {"limit": 20, "offset": 0}, "recursion_count": 0}

def fetch_process_node(state: AgentState):
    """Fetches EXACT page and then filters."""
    query = state.get("search_query") or ""
    assignee = state.get("assignee")
    status = state.get("status")
    
    params = state.get("page_params")
    current_offset = params.get("offset", 0)
    
    if state.get("search_mode") == "deep_scan" and state.get("recursion_count") == 0:
        current_offset = 0

    raw_data = list_tickets.invoke({
        "limit": 20, 
        "offset": current_offset, 
        "search_query": query
    })
    
    if isinstance(raw_data, dict) and "error" in raw_data:
        return {"api_data": []}

    if assignee or status:
        filtered_data = filter_tickets_tool.invoke({
            "tickets": raw_data,
            "assignee_name": assignee,
            "status_name": status
        })
    else:
        filtered_data = raw_data

    return {"api_data": filtered_data}

def check_results_node(state: AgentState):
    """Loop Logic."""
    data = state.get("api_data") or []
    mode = state.get("search_mode")
    count = state.get("recursion_count", 0)
    params = state.get("page_params")
    current_offset = params.get("offset", 0)
    
    # Stop if data found, or not deep_scan, or limit reached
    if len(data) > 0 or mode != "deep_scan" or count >= 5:
        return "rephrase"
    
    print(f"DEBUG: Deep Scan active. Nothing found on Offset {current_offset}. Checking next page...")
    new_offset = current_offset + 20
    return {
        "page_params": {"limit": 20, "offset": new_offset},
        "recursion_count": count + 1
    }

def rephrase_node(state: AgentState):
    data = state.get("api_data") or []
    count = state.get("recursion_count", 0)
    
    scan_note = ""
    if count > 0:
        scan_note = f"(Scanned {count + 1} pages to find these results.)\n\n"
    
    if not data:
        return {"messages": [AIMessage(content=f"{scan_note}No tickets found matching your criteria.")]}
        
    prompt = (
        f"Data: {json.dumps(data)}\n\n"
        "SYSTEM INSTRUCTIONS:\n"
        "1. You are a Text Formatter. Do NOT write Python code.\n"
        "2. Output a clean Markdown list.\n"
        "3. Format exactly like this example:\n"
        "   - **TASK-123** Summary Text (Status: Open, Assigned: Name)\n"
        f"4. Start your response with this note: {scan_note}"
    )
    
    response = call_llama([{"role": "user", "content": prompt}])
    return {"messages": [AIMessage(content=response)]}

# --- 5. GRAPH CONSTRUCTION ---

def build_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("processor", fetch_process_node)
    workflow.add_node("rephrase", rephrase_node)

    workflow.set_entry_point("router")
    
    workflow.add_edge("router", "processor")
    
    def decision_logic(state):
        data = state.get("api_data") or []
        mode = state.get("search_mode")
        count = state.get("recursion_count", 0)
        
        if len(data) > 0:
            return "rephrase"
        
        if mode == "deep_scan" and count < 5:
            return "loop"
            
        return "rephrase"

    workflow.add_conditional_edges(
        "processor",
        decision_logic,
        {"loop": "processor", "rephrase": "rephrase"}
    )
    
    workflow.add_edge("rephrase", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

def run_chat(message: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
    agent = build_agent()
    tid = thread_id or "default"
    result = agent.invoke(
        {"messages": [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": tid}},
    )
    return {"answer": result["messages"][-1].content, "thread_id": tid}
