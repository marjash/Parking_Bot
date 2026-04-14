import logging
import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import DeepLake
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from google.genai.types import HarmCategory, HarmBlockThreshold
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests

# Loading configuration
load_dotenv(override=True)

# Tool settings (Embeddings, DB, LLM)
embeddings = GoogleGenerativeAIEmbeddings(model=os.getenv("EMBEDDINGS_MODEL"))
dataset_path = f"hub://{os.getenv('ACTIVELOOP_ORG')}/parking_ua_chatbot"
vectorstore = DeepLake(dataset_path=dataset_path, embedding=embeddings, read_only=True)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

llm = ChatGoogleGenerativeAI(
    model=os.getenv("GENERATIVE_MODEL"), 
    temperature=0,
    safety_settings={
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# System prompt template for the chatbot
SYSTEM_TEMPLATE = """
ROLE:
You are a professional Parking Reservation Assistant for 'Lviv-Central Parking'.

CONSTRAINTS ON NAMES (STRICT):
1. ALWAYS address the user ONLY by their First Name (e.g., "Олександре", "Маріє").
2. NEVER use the user's Surname in your response to them. 
3. If you only know the Surname, do not use any name at all.
4. DO NOT invent or guess names. If the name is "Олександр", do not say "Олександре Іваненко".

OPERATIONAL GOALS:
1. Provide accurate information about the parking facility using ONLY the provided Context.
2. If the user wants to book a spot, interactively collect exactly these four pieces of information:
   - Name
   - Surname
   - Car Plate Number (e.g., BC1234HX)
   - Reservation Period (Start and End time/date)
3. If data is missing, ask for it politely in Ukrainian.

Example of end of response:
...буду чекати на ваше прізвище.
5. Be polite, concise, and ALWAYS respond in the UKRAINIAN language.

PRIVACY & GUARDRAILS (STRICT):
- NEVER disclose full names (First Name + Last Name) of any individuals found in the Context.
- If info is missing, say: "Вибачте, я не маю цієї інформації. Зверніться до адміністратора: +380-32-111-2233."

Context: {context}
User Query: {question}

Assistant Response (in Ukrainian):"""

prompt_template = ChatPromptTemplate.from_template(SYSTEM_TEMPLATE)

# Compile patterns once (move to module level for performance)
NAME_PATTERN = re.compile(r"\b[А-ЯҐЄІЇ][а-яґєії']{2,}\s+[А-ЯҐЄІЇ][а-яґєії']{2,}")
WHITELIST_ENTITIES = {
        "героїв майдану", "львів", "україна", 
        "lviv-central", "citycenter", "lviv central"
    }

def privacy_filter(text: str, current_session: dict) -> str:
    """Enhanced privacy filtering with logging."""
    
    print(f"Original response: {text}")
    # Build dynamic whitelist from session
    dynamic_whitelist = set()
    for key in ["Name", "Surname"]:
        if val := current_session.get(key):
            if isinstance(val, str) and len(val) > 2:
                dynamic_whitelist.add(val.lower()[:len(val)-1])  # Add partial name to whitelist
    
    # Check names
    for match in NAME_PATTERN.finditer(text):
        name_str = match.group(0).lower()
        words = name_str.split()
        is_safe = any(
            word in WHITELIST_ENTITIES or word in dynamic_whitelist 
            for word in words
        )
        if not is_safe:
            logging.warning(f"Blocked potential PII: {name_str[:3]}***")
            return "🛡️ Відповідь містить конфіденційні ПІБ."
    
    return text

def is_input_safe(user_input: str) -> tuple[bool, str]:
    """Enhanced input validation with categorized threats."""
    
    # Normalize input
    normalized = user_input.lower().strip()
    
    # Prompt injection patterns
    injection_patterns = [
        r"ignore\s+(all\s+)?(previous\s+)?instructions",
        r"system\s*prompt",
        r"you\s+are\s+now",
        r"act\s+as\s+(a\s+)?different",
        r"forget\s+(everything|all)",
        r"override\s+(security|safety)",
        r"pretend\s+(you|to\s+be)",
        r"jailbreak",
        r"DAN\s+mode",
        r"admin\s*(access|mode|panel)",
        r"execute\s*(code|command)",
        r"<script|javascript:|data:",
    ]
    
    for pattern in injection_patterns:
        if re.search(pattern, normalized):
            return False, "Виявлено підозрілий запит."
    
    # Length check
    if len(user_input) > 2000:
        return False, "Повідомлення занадто довге."
    
    return True, ""

def update_user_session(user_id: str, user_input: str, current_session: dict) -> dict:
    """Extract and validate user data with better error handling."""
    
    # Validate plate number format (Ukrainian format)
    PLATE_PATTERN = re.compile(r"^[A-ZА-ЯҐЄІЇ]{2}\d{4}[A-ZА-ЯҐЄІЇ]{2}$", re.IGNORECASE)
    
    extraction_prompt = """
    Extract parking reservation data from the text. Return ONLY valid JSON.
    
    Text: "{input}"
    Current data: {current}

    FIELDS TO EXTRACT:
    - Name: User's first name.
    - Surname: User's last name.
    - Plate: Ukrainian car plate (e.g., "BC1234HX").
    - StartDateTime: When the parking starts (e.g., "15.01 10:00").
    - EndDateTime: When the parking ends (e.g., "15.01 18:00").

    STRICT EXTRACTION RULES:
    1. DO NOT change or normalize surnames. If user says 'Іваненко', keep 'Іваненко', NEVER change to 'Іванова'.
    2. Extract strings EXACTLY as provided by the user.
    3. If a field is not mentioned, use null.
    4. Return ONLY JSON, no conversational text.

    Example Output:
    {{"Name": "Petro", "Surname": "Ivanenko", "Plate": "BC1111AA", "StartDateTime": "15.01.2026 12:00", "EndDateTime": "15.01.2026 14:00"}}

    JSON:

    """
    
    try:
        response = llm.invoke(
            extraction_prompt.format(
                input=user_input,
                current=json.dumps(current_session, ensure_ascii=False)
            )
        ).content
        
        # Clean and parse
        clean_json = re.sub(r"```json|```", "", response).strip().replace("```", "")
        print(f"Extracted data: {clean_json}")

        new_data = json.loads(clean_json)
        # Validate and update
        for key in ["Name", "Surname", "Plate", "StartDateTime", "EndDateTime"]:
            val = new_data.get(key)
            if val and str(val).lower() not in ("null", "none", ""):
                # Special validation for plate
                if key == "Plate":
                    val = val.upper().replace(" ", "")
                    if not PLATE_PATTERN.match(val):
                        continue  # Skip invalid plates
                elif key in ["Name", "Surname"]:
                        val = val.strip().title()  # Normalize names to title case
                else:
                    if key in ["StartDateTime", "EndDateTime"]:
                        val = datetime.strptime(val, "%d.%m.%Y %H:%M")

                current_session[key] = val
        
        return current_session
        
    except json.JSONDecodeError as e:
        logging.error(f"JSON parsing failed: {e}")
        return current_session
    except Exception as e:
        logging.error(f"Extraction error: {e}")
        return current_session

def get_stored_date(st, key, default=None):
    stored = st.session_state.user_data.get(key)
    if not stored:
        return default
    try:
        return stored.date()
    except:
        return default

def get_stored_time(st, key, default=None):
    stored = st.session_state.user_data.get(key)
    if not stored:
        return default
    try:
        return stored.time()
    except:
        return default

def create_telegram_session() -> requests.Session:
    """Create a session with retry logic."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

TELEGRAM_SESSION = create_telegram_session()

def send_to_admin_telegram(session_data: dict) -> bool:
    """Send booking request with retry logic and validation."""
    
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("ADMIN_CHAT_ID")
    
    if not all([token, chat_id]):
        logging.error("Missing Telegram credentials")
        return False
    
    # Validate required fields
    required = ["Name", "Surname", "Plate", "StartDateTime", "EndDateTime"]
    if not all(session_data.get(k) for k in required):
        logging.error("Incomplete session data")
        return False
    
    message_text = (
        f"🚗 *ЗАПИТ НА БРОНЮВАННЯ*\n\n"
        f"👤 *Клієнт:* {session_data['Name']} {session_data['Surname']}\n"
        f"🔢 *Номер авто:* {session_data['Plate']}\n"
        f"🕒 *З:* {session_data['StartDateTime']}\n"
        f"🕒 *До:* {session_data['EndDateTime']}"
    )
    
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Підтвердити", "callback_data": f"approve:{session_data['Plate']}"},
            {"text": "❌ Відхилити", "callback_data": f"reject:{session_data['Plate']}"}
        ]]
    }
    
    try:
        response = TELEGRAM_SESSION.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message_text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            },
            timeout=10
        )
        response.raise_for_status()
        return True
        
    except requests.RequestException as e:
        logging.error(f"Telegram API error: {e}")
        return False
            
def get_ai_response(user_input, session_data):
    """
    Executes RAG logic and returns a safe response from the bot.
    """

    is_safe, error_msg = is_input_safe(user_input)
    if not is_safe:
        return error_msg

    # Determining whether context is needed
    booking_keywords = ["де", "як", "яка", "ціна", "вартість", "правила", "забронювати", "контакти", "чи", "зарядка", "час", "дата", "парковка", "паркування", "зарядити", "забронювати", "бронювання"]
    missing = [k for k, v in session_data.items() if v is None]
    needs_context = any(word in user_input.lower() for word in booking_keywords) or (not missing)

    if needs_context:
        docs = retriever.invoke(user_input)
        context_text = "\n\n".join(doc.page_content for doc in docs)
    else:
        context_text = "The user is providing personal info or greeting. No context needed."

    session_info = f"Current user data: {session_data}. "
    dynamic_instruction = "All data collected. Summarize." if not missing else f"Ask for: {missing}."
    full_query = f"User said: {user_input}\n{session_info}\nInstruction: {dynamic_instruction}"

    chain = prompt_template | llm | StrOutputParser()
    raw_response = chain.invoke({
        "context": context_text,
        "question": full_query
    })

    surname = session_data.get('Surname')
    if surname and surname in raw_response:
        # Remove surname from response to ensure privacy
        raw_response = raw_response.replace(surname, "").replace("  ", " ").strip()

    return privacy_filter(raw_response, session_data)