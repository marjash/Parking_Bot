import telebot
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
import re

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.agents import tool, AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

# Import database functions
from database import update_order_status

# 1. Logging and Configuration Setup
logging.basicConfig(
    filename='admin_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chatbot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

load_dotenv(override=True)
token = os.getenv("TELEGRAM_TOKEN")

if not token:
    logging.error("TELEGRAM_TOKEN not found in .env file")
    exit()

# 2. Model Setup and Tools creation
llm = ChatGoogleGenerativeAI(model=os.getenv("GENERATIVE_MODEL"), temperature=0)

@tool
def approve_booking(plate: str) -> str:
    """Use this tool to confirm a parking booking for a specific car license plate."""
    try:
        success = update_order_status(plate, "approved")
        if success:
            return f"Booking for vehicle {plate} has been successfully APPROVED in the system."
        else:
            return f"Error: Could not approve booking for {plate}"
    except Exception as e:
        return f"Error during approval process: {str(e)}"

@tool
def reject_booking(plate: str) -> str:
    """Use this tool to decline/reject a parking booking for a specific car license plate."""
    try:
        success = update_order_status(plate, "rejected")
        if success:
            return f"Booking for vehicle {plate} has been successfully REJECTED in the system."
        else:
            return f"Error: Could not reject booking for {plate}"
    except Exception as e:
        return f"Error during rejection process: {str(e)}"

# List of tools available to the agent
tools = [approve_booking, reject_booking]

# 3. Prompt for ReAct Agent
template = """You are the Parking System Administrator Agent. 
Your goal is to process booking approval or rejection commands sent by the human administrator.

You have access to the following tools:
{tools}

To use a tool, you MUST use the following format:

Thought: Do I need to use a tool? Yes.
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action (specifically the license plate string, e.g., 'AA1111BB')
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer.
Final Answer: A concise confirmation message for the admin about the completed action.

User Request: {input}
{agent_scratchpad}"""

prompt = PromptTemplate.from_template(template)

# 4. Agent Initialization
agent = create_react_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    verbose=True, 
    handle_parsing_errors=True
)

# 5. Telegram Bot
bot = telebot.TeleBot(token)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve:", "reject:")))
def handle_admin_action(call):
    """Process admin actions with plate encoded in callback_data."""
    try:
        action, plate = call.data.split(":", 1)
        
        if not plate or not re.match(r'^[A-ZА-Я0-9]{6,10}$', plate, re.IGNORECASE):
            bot.answer_callback_query(call.id, "❌ Invalid plate number")
            return
        
        action_map = {"approve": "approve", "reject": "reject"}
        
        if action not in action_map:
            bot.answer_callback_query(call.id, "❌ Unknown action")
            return
        
        query = f"Please {action_map[action]} the booking for plate {plate}"
        result = agent_executor.invoke({"input": query})
        
        now = datetime.now().strftime("%H:%M:%S")
        status_emoji = "✅" if action == "approve" else "❌"
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"{call.message.text}\n\n{status_emoji} {result['output']} ({now})",
            parse_mode="Markdown",
            reply_markup=None
        )

        bot.answer_callback_query(call.id, f"Booking {action}d!")
        logging.info(f"Admin {action}d booking for {plate}")
        
    except Exception as e:
        logging.exception(f"Admin action failed: {e}")
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)[:50]}")

if __name__ == "__main__":
    print("🚀 Admin Agent (LangChain) is running and listening for commands...")
    bot.infinity_polling()