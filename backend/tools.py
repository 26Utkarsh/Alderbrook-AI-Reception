from dataclasses import dataclass
from typing import Awaitable, Callable

from pipecat.services.llm_service import FunctionCallParams

from backend.database import ClinicStore


@dataclass
class ClinicAppResources:
    store: ClinicStore
    emit_event: Callable[[dict], Awaitable[None]]


async def check_doctor_availability(
    params: FunctionCallParams,
    doctor_name: str = "",
    specialty: str = "",
    date: str = "",
):
    """Check available appointment slots for clinic doctors.

    Args:
        doctor_name: Optional doctor name or partial name (e.g. "Patel", "Dr. Maya Patel").
        specialty: Optional medical specialty (e.g. "Cardiology", "Dermatology").
        date: Optional date in YYYY-MM-DD format.
    """
    resources: ClinicAppResources = params.app_resources
    result = resources.store.check_availability(
        doctor_name=doctor_name,
        specialty=specialty,
        target_date=date,
    )
    await params.result_callback(result)


async def book_appointment(
    params: FunctionCallParams,
    phone_number: str,
    doctor_name: str,
    date: str,
    time: str,
    patient_name: str = "",
):
    """Book an available appointment slot for a caller using their spoken phone number.

    Args:
        phone_number: The caller's phone number confirmed out loud.
        doctor_name: The doctor's name (e.g. "Dr. Maya Patel").
        date: Appointment date in YYYY-MM-DD format.
        time: Appointment time (e.g. "09:00 AM" or "02:30 PM").
        patient_name: Optional caller name if provided.
    """
    resources: ClinicAppResources = params.app_resources
    result = resources.store.book_appointment(
        phone_number=phone_number,
        doctor_name=doctor_name,
        target_date=date,
        target_time=time,
        patient_name=patient_name,
    )
    if result.get("ok"):
        await resources.emit_event(
            {
                "type": "appointment_booked",
                "appointment": result["appointment"],
            }
        )
    await params.result_callback(result)


async def cancel_appointment(
    params: FunctionCallParams,
    phone_number: str,
    appointment_id: str = "",
):
    """Cancel an existing appointment using the caller's spoken phone number.

    Args:
        phone_number: The caller's phone number confirmed out loud.
        appointment_id: Optional appointment ID if the caller has more than one booking.
    """
    resources: ClinicAppResources = params.app_resources
    result = resources.store.cancel_appointment(
        phone_number=phone_number,
        appointment_id=appointment_id,
    )
    if result.get("ok"):
        await resources.emit_event(
            {
                "type": "appointment_cancelled",
                "appointment": result["cancelled"],
            }
        )
    await params.result_callback(result)


CLINIC_TOOLS = [
    check_doctor_availability,
    book_appointment,
    cancel_appointment,
]
