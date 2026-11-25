from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import ClinicStore, normalize_doctor_query, normalize_phone, normalize_time


def test_normalization_helpers():
    assert normalize_phone("+1 (415) 555-0142") == "4155550142"
    assert normalize_phone("415-555-0198") == "4155550198"
    assert normalize_doctor_query("Dr. Maya Patel") == "maya patel"
    assert normalize_doctor_query("Dr Maya Patel") == "maya patel"
    assert normalize_time("9:00 am") == "09:00 AM"
    assert normalize_time("14:30") == "02:30 PM"
    assert normalize_time("1:30pm") == "01:30 PM"


def test_availability_booking_and_cancellation(tmp_path: Path):
    store = ClinicStore(tmp_path / "test_clinic.db")
    today = date.today().isoformat()

    avail = store.check_availability(doctor_name="Dr Patel", target_date=today)
    assert avail["total_open_slots"] >= 2
    first_slot = avail["doctors"][0]["available_slots"][0]
    second_slot = avail["doctors"][0]["available_slots"][1]

    # Book using unpadded/lowercase time and doctor name without period
    booked = store.book_appointment(
        phone_number="650-555-0111",
        doctor_name="Dr Maya Patel",
        target_date=first_slot["date"],
        target_time=first_slot["time"].lstrip("0").lower(),
        patient_name="Samira Rao",
    )
    assert booked["ok"] is True
    assert booked["appointment"]["status"] == "confirmed"

    # Double booking the same slot should fail
    duplicate = store.book_appointment(
        phone_number="650-555-0222",
        doctor_name="Dr. Maya Patel",
        target_date=first_slot["date"],
        target_time=first_slot["time"],
    )
    assert duplicate["ok"] is False

    # Booking a second appointment for the same caller triggers disambiguation on cancel
    second_booked = store.book_appointment(
        phone_number="6505550111",
        doctor_name="Patel",
        target_date=second_slot["date"],
        target_time=second_slot["time"],
    )
    assert second_booked["ok"] is True

    ambiguous = store.cancel_appointment(phone_number="6505550111")
    assert ambiguous["ok"] is False
    assert ambiguous["multiple"] is True
    assert len(ambiguous["appointments"]) == 2

    # Cancel specific appointment by ID + phone
    cancelled = store.cancel_appointment(
        phone_number="650-555-0111",
        appointment_id=booked["appointment"]["id"],
    )
    assert cancelled["ok"] is True
    assert cancelled["cancelled"]["status"] == "cancelled"

    # Remaining single appointment can now be cancelled with phone number alone
    cancelled_two = store.cancel_appointment(phone_number="6505550111")
    assert cancelled_two["ok"] is True

    # Both slots should be open again
    reopened = store.check_availability(doctor_name="Patel", target_date=today)
    times = [s["time"] for s in reopened["doctors"][0]["available_slots"]]
    assert first_slot["time"] in times
    assert second_slot["time"] in times
