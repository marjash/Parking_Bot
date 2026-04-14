# Lviv-Central Parking Bot

An intelligent parking booking system built with Python, Streamlit, and LangGraph.

## Features

**AI Agent Orchestration:** Managed by LangGraph for complex decision-making.

**Natural Language Input:** Uses Google Gemini to extract booking details from chat.

**Human-in-the-loop:** Integrated Telegram notifications for admin approval.

**Real-time Monitoring:** Full observability with LangSmith.

### Installation

**1. Clone the repository:**
```
git clone [https://github.com/marjash/Parking_Bot.git](https://github.com/marjash/Parking_Bot.git)
```
**2. Install dependencies:**
```
pip install -r requirements.txt
```
**3. Setup environment variables:**
 - Copy .env.example to .env
 - Add your API keys (Google Gemini, Telegram, LangSmith).

### Usage

**1. Start the Admin Panel:**
```
python admin_panel.py
```
**Run the Streamlit App:**
```
streamlit run app.py
```
**Project Structure**
- app.py: Main user interface (Streamlit).
- orchestrator.py: LangGraph state management.
- chatbot_logic.py: LLM integration and NLP logic.
- admin_panel.py: Telegram bot for administrator actions.
- database.py: SQLite interactions.
- mcp_server.py: write reservation to file
