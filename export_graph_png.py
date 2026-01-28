"""
Generate a local PNG image of the LangGraph agent.

Usage (from this venv folder):
  .\\Scripts\\python.exe export_graph_png.py

Outputs:
  - graph.png            (PNG image, if supported)
  - graph.mermaid.txt    (Mermaid source, always)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from langchain_core.runnables.graph import MermaidDrawMethod
from langgraph.constants import END, START
from langgraph.graph import StateGraph

# Try importing the real build_agent. 
# If chatbot.agent doesn't exist yet, we will rely on the fallback below.
try:
    from chatbot.agent import build_agent
except ImportError:
    build_agent = None


def main() -> None:
    # 1. Try to get the REAL graph from your code
    try:
        if build_agent is None:
            raise RuntimeError("Module chatbot.agent not found")
        
        # This might fail if OPENAI_API_KEY is missing in the real agent code
        app = build_agent()
        graph = app.get_graph()
        print("Successfully loaded the real agent graph.")

    except Exception as e:
        print(f"Could not load real agent (Error: {e}).")
        print("Falling back to a manual 'dummy' graph for visualization...")

        # 2. Manual Fallback: Reconstruct the exact structure of our new pipeline
        #    This ensures you get the correct image even without API keys.

        # Define dummy state and nodes
        class DummyState(dict):
            pass

        def dummy_node(state): return state

        # Create the graph
        sg = StateGraph(DummyState)

        # Add the exact nodes from our new design
        sg.add_node("router", dummy_node)
        sg.add_node("user_tool", dummy_node)
        sg.add_node("item_tool", dummy_node)
        sg.add_node("rephrase", dummy_node)

        # Add the Entry Point
        sg.add_edge(START, "router")

        # Add Conditional Edges (Router -> Tools)
        # We simulate the condition logic for the visualizer
        sg.add_conditional_edges(
            "router",
            lambda x: "user_tool",  # Dummy function
            {
                "user_tool": "user_tool",
                "item_tool": "item_tool"
            }
        )

        # Add Normal Edges (Tools -> Rephrase -> End)
        sg.add_edge("user_tool", "rephrase")
        sg.add_edge("item_tool", "rephrase")
        sg.add_edge("rephrase", END)

        graph = sg.compile().get_graph()

    # 3. Output logic (unchanged)
    out_dir = Path(__file__).parent
    
    # Save Mermaid text
    mermaid = graph.draw_mermaid()
    (out_dir / "graph.mermaid.txt").write_text(mermaid, encoding="utf-8")

    # Save PNG
    try:
        try:
            import pyppeteer  # noqa: F401
            print("Rendering with Pyppeteer...")
            png_bytes = graph.draw_mermaid_png(draw_method=MermaidDrawMethod.PYPPETEER)
        except ImportError:
            print("Pyppeteer not found. Rendering via Mermaid.ink API...")
            png_bytes = graph.draw_mermaid_png()
            
        (out_dir / "graph.png").write_bytes(png_bytes)
        print(f"Success! Graph saved to {out_dir / 'graph.png'}")
        
    except Exception as e:
        print("\n" + "="*50)
        print(f"ERROR: Could not render PNG image.\nDetails: {e}")
        print("="*50)
        print(f"However, the Mermaid text was saved to: {out_dir / 'graph.mermaid.txt'}")
        print("You can paste that text into https://mermaid.live to view your graph.")

if __name__ == "__main__":
    main()