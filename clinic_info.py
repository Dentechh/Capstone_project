"""Clinic information (Settings > Clinic information).

One small document, Settings/clinic_info:
    {"address": ..., "phone": ..., "email": ..., "facebook": ...,
     "updated_at": ..., "updated_by": ...}
Until staff first save it, the built-in defaults below (the clinic's current
details) are used. Every page can read it as `clinic_info` in its template:
    {{ clinic_info.address }}  {{ clinic_info.phone }}
    {{ clinic_info.email }}    {{ clinic_info.facebook }}
It is cached in memory for a minute and refreshed on every save.
"""
import re
import time
from datetime import UTC, datetime

from flask import jsonify, request, session


class ClinicInfoMixin:
    CLINIC_INFO_DOC = "clinic_info"
    CLINIC_INFO_DEFAULTS = {
        "address": "231 Lopez Jaena St, Molo, Iloilo City",
        "phone": "0962 687 6076",
        "email": "capizondadental@gmail.com",
        "facebook": "https://www.facebook.com/profile.php?id=61564525660056",
    }
    CLINIC_INFO_CACHE_SECONDS = 60
    _PHONE_OK = re.compile(r"^[0-9+()\- ]{6,30}$")
    _EMAIL_OK = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    _FACEBOOK_OK = re.compile(r"^https://(www\.|m\.)?(facebook\.com|fb\.com)/\S+$", re.IGNORECASE)

    # ------------------------------------------------------------------ utils
    def _clinic_info_ref(self):
        return self.db.collection("Settings").document(self.CLINIC_INFO_DOC)

    def _read_clinic_info(self, use_cache=True):
        now = time.time()
        cached = getattr(self, "_clinic_info_cache", None)
        if use_cache and cached and now - cached[0] < self.CLINIC_INFO_CACHE_SECONDS:
            return dict(cached[1])
        info = dict(self.CLINIC_INFO_DEFAULTS)
        try:
            snap = self._clinic_info_ref().get()
            if snap.exists:
                saved = snap.to_dict() or {}
                for k in info:
                    v = str(saved.get(k, "") or "").strip()
                    if v:
                        info[k] = v
        except Exception as e:
            print("CLINIC INFO READ ERROR:", e)
        self._clinic_info_cache = (now, info)
        return dict(info)

    def _write_clinic_info(self, info):
        doc = dict(info)
        doc["updated_at"] = datetime.now(UTC).isoformat()
        doc["updated_by"] = str(session.get("admin_uid", "") or "")[:80]
        self._clinic_info_ref().set(doc)
        self._clinic_info_cache = (time.time(), dict(info))

    def _clean_clinic_info(self, form):
        """Returns (info, None) or (None, message)."""
        def val(k):
            return re.sub(r"\s+", " ", str(form.get(k, "") or "")).strip()
        address, phone, email, facebook = val("address"), val("phone"), val("email"), val("facebook")
        if not address:
            return None, "Type the clinic address."
        if len(address) > 120:
            return None, "Keep the address to 120 characters or fewer."
        if not self._PHONE_OK.match(phone):
            return None, "Type a valid contact number (digits, spaces, + ( ) - only)."
        if len(email) > 80 or not self._EMAIL_OK.match(email):
            return None, "Type a valid email address."
        if len(facebook) > 200 or not self._FACEBOOK_OK.match(facebook):
            return None, "The Facebook link must start with https:// and be a facebook.com page."
        return {"address": address, "phone": phone, "email": email, "facebook": facebook}, None

    # ----------------------------------------------------------------- routes
    def admin_settings_clinic(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        return jsonify({"success": True, "clinic": self._read_clinic_info()})

    def admin_settings_clinic_save(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            info, err = self._clean_clinic_info(request.form)
            if err:
                return jsonify({"success": False, "message": err}), 400
            self._write_clinic_info(info)
            return jsonify({"success": True, "clinic": info})
        except Exception as e:
            print("SETTINGS CLINIC SAVE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def _register_clinic_info_routes(self):
        @self.app.context_processor
        def inject_clinic_info():
            return {"clinic_info": self._read_clinic_info()}

        self.app.route("/admin/settings/clinic")(self.admin_settings_clinic)
        self.app.route("/admin/settings/clinic/save", methods=["POST"])(self.admin_settings_clinic_save)