Lviv-Central Parking Bot System Documentation

1. Architecture Description

The system is built on a modern agentic architecture utilizing the Human-in-the-loop concept (incorporating human decision-making into the automated process). It is divided into three main layers:

Frontend Layer

Streamlit App: A web interface for user interaction. It provides a chat interface, date/time picker widgets, and visualization of the final parking permit.

Session State: Manages the dialogue state, user data, and current booking status within a single browser session.

Orchestration Layer (Agent Logic)

LangGraph Orchestrator: The "brain" of the system. It uses a directed state graph to manage transitions between data collection, admin notification, and finalization.

Gemini AI (Google): Used for Natural Language Processing (NLP), entity extraction (Name, Plate Number), and answering general parking-related questions.

LangSmith: A tool for monitoring, tracing, and debugging LLM performance.

Data & Communication Layer (Backend/Server)

SQLite Database: A local database used to store orders and their respective statuses.

Telegram Bot API: A communication channel with the administrator to receive instant "Approve" or "Reject" decisions for requests.

File Persistence: Saves successful bookings into a text-based registry or JSON file.

2. Agent & Server Logic

Agent Logic (Orchestrator)

The agent operates based on a Finite State Machine (FSM) logic:

NODE: Chatbot: Receives input, updates the user data JSON via LLM. Once all textual data is collected, it moves to the UI date selection phase.

EDGE: Conditional Routing: Evaluates whether the data is complete and ready for submission.

NODE: Admin Notification: Sends the collected data to the admin via Telegram. The status changes to pending.

NODE: Persistence: Upon admin approval (status approved), the system records the data into the database and a registry file.

Server Logic (Admin Panel & DB)

Polling/Webhook: The Telegram bot continuously polls Telegram servers for "Approve" or "Reject" button clicks.

Callback Query Handling: When a button is pressed, the admin_panel.py script updates the specific record in the SQLite database.

Status Sync: The Streamlit app polls the SQLite database every few seconds to retrieve the admin's decision and update the user interface.

3. Setup & Deployment Guidelines

Prerequisites

Python 3.10 or higher.

Telegram Bot Token (obtained via @BotFather).

Google Gemini API Key.

LangSmith API Key (optional for monitoring).

Step 1: Cloning and Installation

git clone <your-repo-url>
cd parking-project
python -m venv .venv
source .venv/bin/activate  # For Windows: .venv\Scripts\activate
pip install -r requirements.txt

Step 2: Environment Configuration

Create a .env file in the root directory:

GOOGLE_API_KEY="your_gemini_key"
TELEGRAM_TOKEN="your_bot_token"
ADMIN_CHAT_ID="your_admin_chat_id"

# LangSmith Configuration (Monitoring)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT="[https://eu.api.smith.langchain.com](https://eu.api.smith.langchain.com)"
LANGCHAIN_API_KEY="your_lsv2_key"
LANGCHAIN_PROJECT="parking-chatbot"


Step 3: Running the System

To ensure full functionality, you must run two processes simultaneously:

Start the Web Interface (Client Side):

streamlit run app.py


Start the Admin Panel (Server Side):

python admin_panel.py