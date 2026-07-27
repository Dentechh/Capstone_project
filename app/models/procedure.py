from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Procedure:
    date: str = ""
    tooth: str = ""
    procedure: str = ""
    dentist: str = ""
    value: float = 0.0
    paid: float = 0.0
    balance: float = 0.0
    next_appointment: str = ""
    medicine: str = ""
    status: str = "Pending"

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "tooth": self.tooth,
            "procedure": self.procedure,
            "dentist": self.dentist,
            "value": self.value,
            "paid": self.paid,
            "balance": self.balance,
            "next_appointment": self.next_appointment,
            "medicine": self.medicine,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Procedure":
        return cls(
            date=data.get("date", ""),
            tooth=data.get("tooth", ""),
            procedure=data.get("procedure", ""),
            dentist=data.get("dentist", ""),
            value=float(data.get("value", 0) or 0),
            paid=float(data.get("paid", 0) or 0),
            balance=float(data.get("balance", 0) or 0),
            next_appointment=data.get("next_appointment", ""),
            medicine=data.get("medicine", ""),
            status=data.get("status", "Pending"),
        )


@dataclass
class DoneProcedure:
    uid: str
    chart: dict = field(default_factory=dict)
    chart_image: str = ""
    procedures: List[Procedure] = field(default_factory=list)
    doc_id: str = ""

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "chart": self.chart,
            "chart_image": self.chart_image,
            "procedures": [p.to_dict() for p in self.procedures],
        }

    @classmethod
    def from_dict(cls, data: dict, doc_id: str = "") -> "DoneProcedure":
        procedures = [
            Procedure.from_dict(p) for p in data.get("procedures", [])
        ]
        return cls(
            uid=data.get("uid", ""),
            chart=data.get("chart", {}),
            chart_image=data.get("chart_image", ""),
            procedures=procedures,
            doc_id=doc_id,
        )
