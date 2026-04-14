from datetime import datetime
import os

RESERVATIONS_FILE = os.path.join(os.path.dirname(__file__), "reservations.txt")

def write_reservation_to_file(name: str, surname: str, plate: str, start_datetime: str, end_datetime: str) -> bool:
    """
    Write confirmed reservation to file.
    Format: Name | Car Number | Reservation Period | Approval Time
    """
    try:
        approval_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        entry = f"{name} {surname} | {plate} | {start_datetime} - {end_datetime} | {approval_time}\n"
        
        with open(RESERVATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        
        return True
    except Exception as e:
        print(f"Error writing reservation: {e}")
        return False
