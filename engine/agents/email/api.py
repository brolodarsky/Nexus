"""
api.py — Public entry points for the Email Agent.
"""
from langchain_core.messages import SystemMessage, HumanMessage

from agents.email.prompts import EMAIL_SYSTEM_PROMPT
from agents.email.graph import app, email_tracer

def fetch_emails(query: str, thread_id: str = None) -> str:
    """
    Entry point for the Email Agent.
    Accepts a natural language query, runs the agent to fetch/search emails,
    and returns a structured JSON array of the results.
    """
    email_tracer.agent_start(f"Query: {query[:80]}")
    messages = [
        SystemMessage(content=EMAIL_SYSTEM_PROMPT),
        HumanMessage(content=query)
    ]
    
    config = {}
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}
        
    try:
        final_state = app.invoke({"messages": messages}, config=config)
        last_message = final_state["messages"][-1]
        email_tracer.agent_end()
        return last_message.content
    except Exception as e:
        email_tracer.info(f"❌ Error: {e}")
        return f"[]"  # Return empty array on error to keep JSON parsing safe in Router
