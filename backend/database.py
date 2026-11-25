import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def format_phone(digits: str) -> str:
    clean = normalize_phone(digits)
    if len(clean) == 10:
        return f"({clean[:3]}) {clean[3:6]}-{clean[6:]}"
    return digits.strip()


def normalize_doctor_query(raw: str) -> str:
    cleaned = re.sub(r"^\s*dr\.?\s+", "", (raw or "").strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).lower()


def normalize_time(raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip().upper())
    text = text.replace(".", "")
    for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%I:%M %p")
        except ValueError:
            continue
    return text


class ClinicStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()
        self._seed_if_empty()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS doctors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    specialty TEXT NOT NULL,
                    room TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS slots (
                    id TEXT PRIMARY KEY,
                    doctor_id TEXT NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
                    slot_date TEXT NOT NULL,
                    slot_time TEXT NOT NULL,
                    is_booked INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(doctor_id, slot_date, slot_time)
                );

                CREATE TABLE IF NOT EXISTS appointments (
                    id TEXT PRIMARY KEY,
                    slot_id TEXT NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
                    doctor_id TEXT NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
                    phone_digits TEXT NOT NULL,
                    phone_display TEXT NOT NULL,
                    patient_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )

    def _seed_if_empty(self) -> None:
        schedules = {
            "dr-patel": ["09:00 AM", "10:30 AM", "01:30 PM", "03:00 PM", "04:15 PM"],
            "dr-okafor": ["09:30 AM", "11:00 AM", "02:00 PM", "03:45 PM"],
            "dr-lin": ["08:45 AM", "10:15 AM", "01:00 PM", "02:30 PM"],
            "dr-garcia": ["09:15 AM", "11:30 AM", "02:15 PM", "04:00 PM"],
        }

        with self._conn() as conn:
            first_run = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0
            if first_run:
                doctors = [
                    ("dr-patel", "Dr. Maya Patel", "Family Medicine", "Suite 204"),
                    ("dr-okafor", "Dr. Samuel Okafor", "Cardiology", "Suite 310"),
                    ("dr-lin", "Dr. Hannah Lin", "Dermatology", "Suite 118"),
                    ("dr-garcia", "Dr. Carlos Garcia", "Orthopedics", "Suite 402"),
                ]
                conn.executemany(
                    "INSERT INTO doctors (id, name, specialty, room) VALUES (?, ?, ?, ?)",
                    doctors,
                )

            today = date.today()
            dates = [today + timedelta(days=offset) for offset in range(3)]
            slot_rows = []
            for d in dates:
                d_str = d.isoformat()
                for doc_id, times in schedules.items():
                    for t in times:
                        slot_id = f"{doc_id}_{d_str}_{t.replace(' ', '').replace(':', '')}"
                        slot_rows.append((slot_id, doc_id, d_str, t, 0))

            conn.executemany(
                "INSERT OR IGNORE INTO slots (id, doctor_id, slot_date, slot_time, is_booked) VALUES (?, ?, ?, ?, ?)",
                slot_rows,
            )

            if first_run:
                first_day = dates[0].isoformat()
                second_day = dates[1].isoformat()
                sample_bookings = [
                    ("dr-patel", first_day, "10:30 AM", "4155550142", "Liam Mercer"),
                    ("dr-okafor", second_day, "11:00 AM", "4155550198", "Priya Nair"),
                ]
                for doc_id, d_str, t_str, phone, patient in sample_bookings:
                    row = conn.execute(
                        "SELECT id FROM slots WHERE doctor_id = ? AND slot_date = ? AND slot_time = ?",
                        (doc_id, d_str, t_str),
                    ).fetchone()
                    if row:
                        conn.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (row["id"],))
                        appt_id = f"APT-{uuid.uuid4().hex[:6].upper()}"
                        conn.execute(
                            """
                            INSERT INTO appointments (id, slot_id, doctor_id, phone_digits, phone_display, patient_name, status)
                            VALUES (?, ?, ?, ?, ?, ?, 'confirmed')
                            """,
                            (appt_id, row["id"], doc_id, phone, format_phone(phone), patient),
                        )

    def list_doctors_with_slots(self) -> list[dict[str, Any]]:
        today_str = date.today().isoformat()
        with self._conn() as conn:
            docs = [dict(r) for r in conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()]
            for doc in docs:
                slots = conn.execute(
                    """
                    SELECT id, slot_date, slot_time, is_booked
                    FROM slots
                    WHERE doctor_id = ? AND slot_date >= ?
                    ORDER BY slot_date, slot_time
                    """,
                    (doc["id"], today_str),
                ).fetchall()
                doc["slots"] = [dict(s) for s in slots]
            return docs

    def list_appointments(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.slot_id,
                    a.doctor_id,
                    d.name AS doctor_name,
                    d.specialty,
                    d.room,
                    s.slot_date,
                    s.slot_time,
                    a.phone_digits,
                    a.phone_display,
                    a.patient_name,
                    a.status,
                    a.created_at
                FROM appointments a
                JOIN doctors d ON d.id = a.doctor_id
                JOIN slots s ON s.id = a.slot_id
                ORDER BY
                    CASE WHEN a.status = 'confirmed' THEN 0 ELSE 1 END,
                    s.slot_date ASC,
                    s.slot_time ASC,
                    a.created_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def check_availability(
        self, doctor_name: str = "", specialty: str = "", target_date: str = ""
    ) -> dict[str, Any]:
        today_str = date.today().isoformat()
        clean_doc = normalize_doctor_query(doctor_name)
        with self._conn() as conn:
            query = """
                SELECT
                    d.id AS doctor_id,
                    d.name AS doctor_name,
                    d.specialty,
                    d.room,
                    s.id AS slot_id,
                    s.slot_date,
                    s.slot_time
                FROM slots s
                JOIN doctors d ON d.id = s.doctor_id
                WHERE s.is_booked = 0 AND s.slot_date >= ?
            """
            params: list[Any] = [today_str]

            if clean_doc:
                query += " AND LOWER(REPLACE(d.name, '.', '')) LIKE ?"
                params.append(f"%{clean_doc}%")
            if specialty.strip():
                query += " AND LOWER(d.specialty) LIKE ?"
                params.append(f"%{specialty.strip().lower()}%")
            if target_date.strip():
                query += " AND s.slot_date = ?"
                params.append(target_date.strip())

            query += " ORDER BY d.name, s.slot_date, s.slot_time"
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

            grouped: dict[str, dict[str, Any]] = {}
            for r in rows:
                doc_id = r["doctor_id"]
                if doc_id not in grouped:
                    grouped[doc_id] = {
                        "doctor_name": r["doctor_name"],
                        "specialty": r["specialty"],
                        "room": r["room"],
                        "available_slots": [],
                    }
                grouped[doc_id]["available_slots"].append(
                    {"date": r["slot_date"], "time": r["slot_time"]}
                )

            return {
                "today": today_str,
                "doctors": list(grouped.values()),
                "total_open_slots": len(rows),
            }

    def book_appointment(
        self,
        phone_number: str,
        doctor_name: str,
        target_date: str,
        target_time: str,
        patient_name: str = "",
    ) -> dict[str, Any]:
        digits = normalize_phone(phone_number)
        if len(digits) < 7:
            return {"ok": False, "error": "Invalid or incomplete phone number."}

        clean_doc = normalize_doctor_query(doctor_name)
        canonical_time = normalize_time(target_time)

        with self._conn() as conn:
            slot = conn.execute(
                """
                SELECT s.id AS slot_id, s.is_booked, s.slot_date, s.slot_time,
                       d.id AS doctor_id, d.name AS doctor_name, d.specialty, d.room
                FROM slots s
                JOIN doctors d ON d.id = s.doctor_id
                WHERE LOWER(REPLACE(d.name, '.', '')) LIKE ?
                  AND s.slot_date = ?
                  AND UPPER(s.slot_time) = UPPER(?)
                """,
                (f"%{clean_doc}%", target_date.strip(), canonical_time),
            ).fetchone()

            if not slot:
                return {
                    "ok": False,
                    "error": f"No matching slot found for {doctor_name} on {target_date} at {target_time}.",
                }
            if slot["is_booked"]:
                return {
                    "ok": False,
                    "error": f"{slot['doctor_name']} at {slot['slot_time']} on {slot['slot_date']} is already booked.",
                }

            conn.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (slot["slot_id"],))
            appt_id = f"APT-{uuid.uuid4().hex[:6].upper()}"
            phone_display = format_phone(digits)
            conn.execute(
                """
                INSERT INTO appointments (id, slot_id, doctor_id, phone_digits, phone_display, patient_name, status)
                VALUES (?, ?, ?, ?, ?, ?, 'confirmed')
                """,
                (
                    appt_id,
                    slot["slot_id"],
                    slot["doctor_id"],
                    digits,
                    phone_display,
                    patient_name.strip(),
                ),
            )

            return {
                "ok": True,
                "appointment": {
                    "id": appt_id,
                    "slot_id": slot["slot_id"],
                    "doctor_name": slot["doctor_name"],
                    "specialty": slot["specialty"],
                    "room": slot["room"],
                    "date": slot["slot_date"],
                    "time": slot["slot_time"],
                    "phone_display": phone_display,
                    "patient_name": patient_name.strip(),
                    "status": "confirmed",
                },
            }

    def cancel_appointment(
        self, phone_number: str, appointment_id: str = ""
    ) -> dict[str, Any]:
        digits = normalize_phone(phone_number)
        if len(digits) < 7:
            return {"ok": False, "error": "Invalid or incomplete phone number."}

        with self._conn() as conn:
            if appointment_id.strip():
                row = conn.execute(
                    """
                    SELECT a.id, a.slot_id, a.phone_display, a.patient_name,
                           d.name AS doctor_name, d.specialty, s.slot_date, s.slot_time
                    FROM appointments a
                    JOIN doctors d ON d.id = a.doctor_id
                    JOIN slots s ON s.id = a.slot_id
                    WHERE a.id = ? AND a.phone_digits = ? AND a.status = 'confirmed'
                    """,
                    (appointment_id.strip().upper(), digits),
                ).fetchone()
            else:
                rows = conn.execute(
                    """
                    SELECT a.id, a.slot_id, a.phone_display, a.patient_name,
                           d.name AS doctor_name, d.specialty, s.slot_date, s.slot_time
                    FROM appointments a
                    JOIN doctors d ON d.id = a.doctor_id
                    JOIN slots s ON s.id = a.slot_id
                    WHERE a.phone_digits = ? AND a.status = 'confirmed'
                    ORDER BY s.slot_date ASC, s.slot_time ASC
                    """,
                    (digits,),
                ).fetchall()
                if len(rows) > 1:
                    return {
                        "ok": False,
                        "multiple": True,
                        "appointments": [dict(r) for r in rows],
                        "error": "Multiple confirmed appointments found for this phone number.",
                    }
                row = rows[0] if rows else None

            if not row:
                return {
                    "ok": False,
                    "error": f"No confirmed appointment found for {format_phone(digits)}.",
                }

            conn.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (row["id"],))
            conn.execute("UPDATE slots SET is_booked = 0 WHERE id = ?", (row["slot_id"],))

            return {
                "ok": True,
                "cancelled": {
                    "id": row["id"],
                    "slot_id": row["slot_id"],
                    "doctor_name": row["doctor_name"],
                    "specialty": row["specialty"],
                    "date": row["slot_date"],
                    "time": row["slot_time"],
                    "phone_display": row["phone_display"],
                    "patient_name": row["patient_name"],
                    "status": "cancelled",
                },
            }
