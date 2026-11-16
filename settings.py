"""
Clinic settings, edited by staff from the Settings page.

Section 1 - Medicines: the list offered in the Medicine field of the treatment
records. A treatment record saves the medicine as plain text, so adding or
removing a medicine here never changes a record that was already saved.

Stored as ONE document, Settings/medicines:
    {"items": [...], "updated_at": ..., "updated_by": ...}
Until a staff member first edits the list the document does not exist and the
built-in default list below is used. The list is cached in memory for a minute
(and refreshed on every edit), so reading it costs almost no Firestore reads.
"""
import re
import time
from datetime import UTC, datetime

from flask import jsonify, request, session


class SettingsMixin:
    SETTINGS = "Settings"
    MEDICINES_DOC = "medicines"
    DEFAULT_MEDICINES = ("Mefenamic Acid", "Tranexamic Acid", "Amoxicillin", "Co- amoxiclav")
    MEDICINE_MAX_ITEMS = 100
    MEDICINE_MAX_LEN = 60
    MEDICINES_CACHE_SECONDS = 60
    # letters / numbers first, then the punctuation drug names really use
    _MEDICINE_OK = re.compile(r"^[\w][\w .,'()/+%&\-]*$", re.UNICODE)

    # ------------------------------------------------------------------ utils
    def _medicines_ref(self):
        return self.db.collection(self.SETTINGS).document(self.MEDICINES_DOC)

    def _read_medicines(self, use_cache=True):
        """The saved list (or the defaults before the first edit), without 'None'."""
        now = time.time()
        cached = getattr(self, "_medicines_cache", None)
        if use_cache and cached and now - cached[0] < self.MEDICINES_CACHE_SECONDS:
            return list(cached[1])
        snap = self._medicines_ref().get()
        if snap.exists:
            raw = (snap.to_dict() or {}).get("items") or []
            items = [str(x).strip() for x in raw if str(x).strip()]
        else:
            items = list(self.DEFAULT_MEDICINES)
        self._medicines_cache = (now, items)
        return list(items)

    def _write_medicines(self, items):
        self._medicines_ref().set({
            "items": list(items),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": str(session.get("admin_uid", "") or "")[:80],
        })
        self._medicines_cache = (time.time(), list(items))

    def _clean_medicine_name(self, raw):
        """Returns (name, None) or (None, message)."""
        name = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not name:
            return None, "Type a medicine name."
        if len(name) > self.MEDICINE_MAX_LEN:
            return None, "Keep the name to %d characters or fewer." % self.MEDICINE_MAX_LEN
        if name.lower() == "none":
            return None, '"None" is always available, so it does not need to be added.'
        if not self._MEDICINE_OK.match(name):
            return None, "Use letters, numbers and normal punctuation only."
        return name, None

    # ----------------------------------------------------------------- routes
    def admin_settings_medicines(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            return jsonify({"success": True, "medicines": self._read_medicines()})
        except Exception as e:
            print("SETTINGS MEDICINES READ ERROR:", e)
            return jsonify({"success": False, "message": "Could not load the medicine list."}), 500

    def admin_settings_medicines_add(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            name, err = self._clean_medicine_name(request.form.get("name", ""))
            if err:
                return jsonify({"success": False, "message": err}), 400
            items = self._read_medicines(use_cache=False)      # always the latest saved list
            if any(i.lower() == name.lower() for i in items):
                return jsonify({"success": False, "message": "That medicine is already in the list."}), 409
            if len(items) >= self.MEDICINE_MAX_ITEMS:
                return jsonify({"success": False, "message": "The list is full."}), 400
            items.append(name)
            self._write_medicines(items)
            return jsonify({"success": True, "medicines": items})
        except Exception as e:
            print("SETTINGS MEDICINES ADD ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_settings_medicines_remove(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            name = re.sub(r"\s+", " ", str(request.form.get("name", ""))).strip()
            if not name:
                return jsonify({"success": False, "message": "No medicine specified."}), 400
            items = self._read_medicines(use_cache=False)
            kept = [i for i in items if i.lower() != name.lower()]
            if len(kept) == len(items):
                return jsonify({"success": False, "message": "That medicine is not in the list."}), 404
            self._write_medicines(kept)
            return jsonify({"success": True, "medicines": kept})
        except Exception as e:
            print("SETTINGS MEDICINES REMOVE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def _register_settings_routes(self):
        r = self.app.route
        r("/admin/settings/medicines")(self.admin_settings_medicines)
        r("/admin/settings/medicines/add", methods=["POST"])(self.admin_settings_medicines_add)
        r("/admin/settings/medicines/remove", methods=["POST"])(self.admin_settings_medicines_remove)