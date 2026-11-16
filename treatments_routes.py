# ---------------------------------------------------------------------------
# Treatments / Services  (paste into main.py, next to the medicines + dentists routes)
#
# Replace "# <-- same decorators as medicines ... route" with the exact
# decorator lines (login check, role check, csrf, etc.) that your medicines
# routes use. Also use the same Firestore variable name your file uses
# (this code assumes it is called `db`).
# ---------------------------------------------------------------------------

DEFAULT_TREATMENTS = [
    "Dental Consultation",
    "Oral Prophylaxis (Cleaning)",
    "Tooth Restoration (Pasta)",
    "Tooth Extraction (Gabot)",
    "Dentures (Pustiso)",
    "Crowns and Bridges",
    "Teeth Whitening",
    "Fluoride Treatment",
    "Pit and Fissure Sealant",
    "Wisdom Teeth Removal",
    "Root Canal Treatment",
    "Periapical Xray",
    "Orthodontic Braces",
]


def _load_treatments():
    """Saved list from Settings/treatments. Falls back to the defaults until
    the first add/remove saves a list."""
    snap = db.collection("Settings").document("treatments").get()
    data = snap.to_dict() if snap.exists else None
    if data and isinstance(data.get("items"), list):
        return list(data["items"])
    return list(DEFAULT_TREATMENTS)


def _save_treatments(items):
    db.collection("Settings").document("treatments").set({"items": items})


# Admin: read the list
@app.route("/admin/settings/treatments", methods=["GET"])
# <-- same decorators as medicines GET route
def settings_treatments_get():
    return jsonify(success=True, treatments=_load_treatments())


# Admin: add one
@app.route("/admin/settings/treatments/add", methods=["POST"])
# <-- same decorators as medicines add route
def settings_treatments_add():
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify(success=False, message="Type a treatment name."), 400
    if len(name) > 60:
        return jsonify(success=False, message="Name is too long (max 60 characters)."), 400
    items = _load_treatments()
    if name.lower() in (t.lower() for t in items):
        return jsonify(success=False, message="That treatment is already in the list."), 400
    items.append(name)
    _save_treatments(items)
    return jsonify(success=True, treatments=items)


# Admin: remove one
@app.route("/admin/settings/treatments/remove", methods=["POST"])
# <-- same decorators as medicines remove route
def settings_treatments_remove():
    name = (request.form.get("name") or "").strip()
    items = [t for t in _load_treatments() if t != name]
    _save_treatments(items)
    return jsonify(success=True, treatments=items)


# Public: the patient site reads the same list (no admin login needed,
# it only returns service names).
@app.route("/api/services", methods=["GET"])
def public_services():
    return jsonify(success=True, services=_load_treatments())