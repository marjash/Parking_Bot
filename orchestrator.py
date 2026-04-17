from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from chatbot_logic import update_user_session, get_ai_response, send_to_admin_telegram
from mcp_server import write_reservation_to_file

# 1. Graph state determination (State)
class AgentState(TypedDict):
    messages: List[BaseMessage]
    user_data: dict
    status: str  # 'collecting', 'ready_to_submit', 'pending', 'approved', 'rejected', 'finalized'
    last_input: str
    error: Optional[str]

# 2. Nodes

def chatbot_node(state: AgentState):
    """Stage 1: Data collection and trigger processing."""
    user_input = state['last_input']
    current_data = state['user_data']
    
    # Handling manual commands from the UI (Stage 2 & 3)
    if user_input == "SEND_TO_ADMIN_TRIGGER":
        return {"status": "send_now"}
    
    if user_input == "ADMIN_APPROVED_TRIGGER":
        return {"status": "approved"}

    # Update session with new input and get AI response
    updated_data = update_user_session("user_id", user_input, current_data)
    
    required_fields = ["Name", "Surname", "Plate", "StartDateTime", "EndDateTime"]
    is_complete = all(updated_data.get(k) not in [None, "", "null", "None"] for k in required_fields)
    
    if is_complete and state['status'] == 'collecting':
        return {
            "user_data": updated_data,
            "status": "ready_to_submit",
            "messages": state['messages'] + [AIMessage(content="Дякую! Всі дані зібрано. Перевірте їх та натисніть кнопку відправки.")]
        }

    ai_res = get_ai_response(user_input, updated_data)
    return {
        "user_data": updated_data,
        "status": state['status'] if is_complete else "collecting",
        "messages": state['messages'] + [AIMessage(content=ai_res)]
    }

def admin_notification_node(state: AgentState):
    """Stage 2: Ескалація."""
    send_to_admin_telegram(state['user_data'])
    return {"status": "pending"}

def mcp_persistence_node(state: AgentState):
    """Stage 3: Запис у файл (MCP)."""
    data = state['user_data']
    # Calling the write to file function
    success = write_reservation_to_file(
        name=data.get('Name'),
        surname=data.get('Surname'),
        plate=data.get('Plate'),
        start_datetime=data.get('StartDateTime'),
        end_datetime=data.get('EndDateTime')
    )
    
    if success:
        return {
            "status": "finalized",
            "messages": state['messages'] + [AIMessage(content="Бронювання підтверджено та записано в текстовий реєстр.")]
        }
    return {"status": "error", "error": "Помилка запису в reservations.txt"}

# 3. Transition logic
def route_main(state: AgentState):
    """Route the flow based on the current status."""
    if state['status'] == "send_now":
        return "notify_admin"
    if state['status'] == "approved":
        return "write_to_file"
    return END

# 4. Graph construction
workflow = StateGraph(AgentState)

workflow.add_node("chatbot", chatbot_node)
workflow.add_node("notify_admin", admin_notification_node)
workflow.add_node("write_to_file", mcp_persistence_node)

workflow.set_entry_point("chatbot")

# Check the status immediately after entering/processing the text
workflow.add_conditional_edges("chatbot", route_main)

# After notification to admin we just wait (END), 
# since the next step initiates the UI through ADMIN_APPROVED_TRIGGER
workflow.add_edge("notify_admin", END)
workflow.add_edge("write_to_file", END)

app_graph = workflow.compile()

def process_step(user_input, st_user_data, st_status):
    initial_state = {
        "messages": [],
        "user_data": st_user_data,
        "status": st_status,
        "last_input": user_input,
        "error": None
    }
    return app_graph.invoke(initial_state)