import bleach


def sanitize_input(value: str) -> str:
    return bleach.clean(value.strip())


def sanitize_form(form_data: dict) -> dict:
    cleaned = {}
    for key, value in form_data.items():
        if isinstance(value, str):
            cleaned[key] = bleach.clean(value.strip())
        else:
            cleaned[key] = value
    return cleaned
