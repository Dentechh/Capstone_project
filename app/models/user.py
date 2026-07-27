from datetime import datetime, UTC


class User:
    def __init__(
        self,
        uid: str = "",
        firstname: str = "",
        lastname: str = "",
        email: str = "",
        contact_number: str = "",
        account_type: str = "Manual",
        name: str = "",
        password_hash: str = "",
        verified: bool = False,
        created_at: str = "",
    ):
        self.uid = uid
        self.firstname = firstname
        self.lastname = lastname
        self.email = email
        self.contact_number = contact_number
        self.account_type = account_type
        self.name = name or f"{firstname} {lastname}".strip()
        self.password_hash = password_hash
        self.verified = verified
        self.created_at = created_at or datetime.now(UTC).isoformat()

    @property
    def display_name(self) -> str:
        return self.firstname or self.name or "User"

    @property
    def full_name(self) -> str:
        return f"{self.firstname} {self.lastname}".strip()

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "firstname": self.firstname,
            "lastname": self.lastname,
            "email": self.email,
            "contact_number": self.contact_number,
            "account_type": self.account_type,
            "name": self.name,
            "verified": self.verified,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            uid=data.get("uid", ""),
            firstname=data.get("firstname", data.get("first_name", "")),
            lastname=data.get("lastname", data.get("last_name", "")),
            email=data.get("email", ""),
            contact_number=data.get("contact_number", ""),
            account_type=data.get("account_type", "Manual"),
            name=data.get("name", ""),
            password_hash=data.get("password", ""),
            verified=data.get("verified", False),
            created_at=data.get("created_at", ""),
        )
