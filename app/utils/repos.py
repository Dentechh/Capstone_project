from app.repositories.user_repo import UserRepository
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.procedure_repo import ProcedureRepository
from app.utils.firebase import get_db

_user_repo = None
_appointment_repo = None
_procedure_repo = None


def get_user_repo() -> UserRepository:
    global _user_repo
    if _user_repo is None:
        _user_repo = UserRepository(get_db())
    return _user_repo


def get_appointment_repo() -> AppointmentRepository:
    global _appointment_repo
    if _appointment_repo is None:
        _appointment_repo = AppointmentRepository(get_db(), get_user_repo())
    return _appointment_repo


def get_procedure_repo() -> ProcedureRepository:
    global _procedure_repo
    if _procedure_repo is None:
        _procedure_repo = ProcedureRepository(get_db(), get_user_repo())
    return _procedure_repo
