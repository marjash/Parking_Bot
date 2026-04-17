import streamlit as st
import time
from html import escape
from datetime import datetime
from dotenv import load_dotenv

from orchestrator import process_step 

from database import get_order_status, create_order

from chatbot_logic import get_stored_date, get_stored_time

load_dotenv()

# --- UI Setup ---
st.set_page_config(page_title="Lviv-Central Parking Bot", page_icon="🚗")
st.title("🚗 Lviv-Central Parking Bot")
st.markdown("---")

# 1. Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {
        "Name": None, 
        "Surname": None, 
        "Plate": None, 
        "StartDateTime": None, 
        "EndDateTime": None
    }
if "status" not in st.session_state:
    st.session_state.status = "collecting"
if "sent_success" not in st.session_state:
    st.session_state.sent_success = False
if "dates_set" not in st.session_state:
    st.session_state.dates_set = False

# 2. Display chat history
for message in st.session_state.messages:
    role = "user" if (isinstance(message, dict) and message.get("role") == "user") else "assistant"
    with st.chat_message(role):
        content = message.content if hasattr(message, 'content') else message.get("content", "")
        st.markdown(content)

# 3. Chat Input & LangGraph Orchestration
if st.session_state.status == "collecting":
    if prompt := st.chat_input("Напишіть ваше запитання або дані для бронювання..."):
        st.session_state.sent_success = False
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("Обробка..."):
            result = process_step(prompt, st.session_state.user_data, st.session_state.status)
        
        st.session_state.user_data = result['user_data']
        st.session_state.status = result['status']
        if result.get('messages'):
            st.session_state.messages.extend(result['messages'])
        st.rerun()

# 4. Date/Time Picker
st.subheader("📅 Оберіть період паркування")

current_sd = get_stored_date(st, "StartDateTime", None)
current_st = get_stored_time(st, "StartDateTime", None)
current_ed = get_stored_date(st, "EndDateTime", None)
current_et = get_stored_time(st, "EndDateTime", None)

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Дата початку", value=current_sd, key="sd", format="DD.MM.YYYY")
    start_time = st.time_input("Час початку", value=current_st, key="st")
with col2:
    end_date = st.date_input("Дата завершення", value=current_ed, key="ed", format="DD.MM.YYYY")
    end_time = st.time_input("Час завершення", value=current_et, key="et")

if all([start_date, start_time, end_date, end_time]):
    start_dt = datetime.combine(start_date, start_time)
    end_dt = datetime.combine(end_date, end_time)
    if end_dt <= start_dt:
        st.error("⚠️ Дата завершення має бути пізніше дати початку.")
        st.session_state.dates_set = False
    else:
        start_datetime = start_dt.strftime("%d.%m.%Y %H:%M")
        end_datetime = end_dt.strftime("%d.%m.%Y %H:%M")
        st.session_state.user_data["StartDateTime"] = start_datetime
        st.session_state.user_data["EndDateTime"] = end_datetime
        st.session_state.dates_set = True
else:
    st.session_state.user_data["StartDateTime"] = None
    st.session_state.user_data["EndDateTime"] = None
    st.session_state.dates_set = False

# 5. Confirmation & Admin Workflow
user_info = st.session_state.user_data

is_complete = all(v is not None and str(v).lower() not in ('null', '', 'none') for v in user_info.values())

is_text_data_complete = all(
    user_info.get(k) not in (None, "", "null", "None") 
    for k in ["Name", "Surname", "Plate"]
)
if not st.session_state.dates_set and is_text_data_complete:
        st.warning("⚠️ Будь ласка, оберіть дату та час паркування вище, щоб продовжити.")

if is_complete and st.session_state.status != "finalized":
    st.divider()
    
    if not st.session_state.sent_success:
        st.success("✅ Дані зібрано! Підтвердіть відправку.")

# --- Admin Agent Setup (for Telegram) ---
        with st.expander("📝 Редагувати дані", expanded=True):
            col_a, col_b = st.columns(2)
            with col_a:
                new_name = st.text_input("Ім'я", value=user_info.get('Name', ''))
                new_surname = st.text_input("Прізвище", value=user_info.get('Surname', ''))
            with col_b:
                new_plate = st.text_input("Номер авто", value=user_info.get('Plate', ''))
            
            # Update session state with edited values
            st.session_state.user_data['Name'] = new_name
            st.session_state.user_data['Surname'] = new_surname
            st.session_state.user_data['Plate'] = new_plate

        col1, col2 = st.columns([2, 1])
        with col1:
            st.write(f"👤 **Клієнт:** {user_info['Name']} {user_info['Surname']}")
            st.write(f"🚗 **Авто:** {user_info['Plate']}")
            st.write(f"⏰ **Дата:** {start_date.strftime('%d.%m.%Y')} → {end_date.strftime('%d.%m.%Y')}")
            st.write(f"🕒 **Час:** {start_time.strftime('%H:%M')} → {end_time.strftime('%H:%M')}")
        
        with col2:
            if st.button("🚀 Надіслати запит", use_container_width=True):
                with st.spinner('Відправка...'):
                    create_order(
                        name=user_info['Name'],
                        surname=user_info['Surname'],
                        plate=user_info['Plate'],
                        start_datetime=datetime.strptime(start_datetime, "%d.%m.%Y %H:%M"),
                        end_datetime=datetime.strptime(end_datetime, "%d.%m.%Y %H:%M")
                    )
                    result = process_step("SEND_TO_ADMIN_TRIGGER", st.session_state.user_data, st.session_state.status)
                    if result.get('error'):
                        st.error("❌ Не вдалося надіслати запит адміністратору. Спробуйте ще раз.")
                    else:
                        st.session_state.status = "pending"
                        st.session_state.sent_success = True
                    st.rerun()

    else:
        current_status = get_order_status(user_info.get('Plate'))
        if current_status == "approved":
            process_step("ADMIN_APPROVED_TRIGGER", st.session_state.user_data, "approved")
            st.session_state.status = "finalized"
            st.balloons()
            st.rerun()
        elif current_status == "rejected":
            st.error(f"❌ Запит для авто **{user_info.get('Plate')}** відхилено.")
            if st.button("Спробувати ще раз"):
                st.session_state.clear()
                st.rerun()
        else:
            with st.status("⏳ Очікуємо на підтвердження адміністратора...", expanded=True):
                time.sleep(4)
                st.rerun()

# 6. Final Ticket
if st.session_state.status == "finalized":
    st.success("### 🎉 БРОНЮВАННЯ ПІДТВЕРДЖЕНО!")
    st.markdown(f"""
    <div style="border: 2px solid #2e7d32; padding: 20px; border-radius: 10px; background-color: #e8f5e9; color: #000;">
        <h3 style="text-align: center; color: #2e7d32;">🅿️ ПАРКУВАЛЬНИЙ ТАЛОН</h3>
        <p><b>Власник:</b> {user_info['Name']} {user_info['Surname']}</p>
        <p><b>Авто:</b> <code>{user_info['Plate']}</code></p>
        <p><b>Дата:</b> {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y') }</p>
        <p><b>Час:</b> {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}</p>
        <hr>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("Нове бронювання", use_container_width=True):
        st.session_state.clear()
        st.rerun()

with st.sidebar:
    st.header("📊 Стан системи")
    st.write(f"Поточний статус: **{st.session_state.status}**")
    st.json(st.session_state.user_data)
    if st.button("🗑️ Скинути сесію"):
        st.session_state.clear()
        st.rerun()