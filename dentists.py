"""Settings -> Dentists: the list of dentists offered in the dentist dropdowns.

The list is kept in Firestore (Settings/dentists, field "names"). The default
dentist is always available and is not stored, so it can never be removed.
Removing a dentist never changes a record or appointment that already has
that dentist saved (they keep the name as plain text).

Routes (admin only, same shape as the Medicines routes):
    GET  /api/dentists                     -> {success, dentists}  (public, names only)
    GET  /admin/settings/dentists          -> {success, dentists}
    POST /admin/settings/dentists/add      form field "name"
    POST /admin/settings/dentists/remove   form field "name"
"""
import re

from flask import jsonify, request, session

DEFAULT_DENTIST = "Dr. Julix Dionne Capizonda"
MAX_DENTISTS = 30
MAX_NAME_LEN = 60


class DentistsMixin:
    def _register_dentist_routes(self):
        self.app.route("/api/dentists", methods=["GET"])(self.public_dentists_list)
        self.app.route("/admin/settings/dentists", methods=["GET"])(self.settings_dentists_list)
        self.app.route("/admin/settings/dentists/add", methods=["POST"])(self.settings_dentists_add)
        self.app.route("/admin/settings/dentists/remove", methods=["POST"])(self.settings_dentists_remove)

    # ---- storage -------------------------------------------------------
    def _dentists_ref(self):
        return self.db.collection("Settings").document("dentists")

    def _load_dentists(self):
        snap = self._dentists_ref().get()
        names = (snap.to_dict() or {}).get("names", []) if snap.exists else []
        return [n for n in names if isinstance(n, str) and n.strip()]

    def _save_dentists(self, names):
        self._dentists_ref().set({"names": names})

    # ---- helpers -------------------------------------------------------
    @staticmethod
    def _clean_dentist_name(raw):
        name = re.sub(r"\s+", " ", (raw or "")).strip()
        if not name:
            return "", "Type a dentist name."
        if re.search(r"[<>]", name):
            return "", "Dentist names cannot contain < or >."
        if len(name) > MAX_NAME_LEN:
            return "", "Name is too long (max %d characters)." % MAX_NAME_LEN
        if not re.match(r"(?i)^dr\.?\s", name):
            name = "Dr. " + name
        elif re.match(r"(?i)^dr\s", name):
            name = "Dr. " + name[3:].strip()
        if len(name) <= 4:
            return "", "Type the dentist's full name."
        return name, ""

    def _dentists_payload(self, names, **extra):
        data = {"success": True, "dentists": names}
        data.update(extra)
        return jsonify(data)

    @staticmethod
    def _dentists_forbidden():
        return jsonify({"success": False, "message": "Not authorized."}), 403

    # ---- routes --------------------------------------------------------
    def public_dentists_list(self):
        """Read-only list for the booking dropdowns (names only, no login needed)."""
        try:
            names = [DEFAULT_DENTIST] + [n for n in self._load_dentists() if n.lower() != DEFAULT_DENTIST.lower()]
            resp = jsonify({"success": True, "dentists": names[1:]})
        except Exception:
            resp = jsonify({"success": True, "dentists": []})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def settings_dentists_list(self):
        if not session.get("admin_logged_in"):
            return self._dentists_forbidden()
        try:
            return self._dentists_payload(self._load_dentists())
        except Exception:
            return jsonify({"success": False, "message": "Could not load dentists."}), 500

    def settings_dentists_add(self):
        if not session.get("admin_logged_in"):
            return self._dentists_forbidden()
        name, err = self._clean_dentist_name(request.form.get("name", ""))
        if err:
            return jsonify({"success": False, "message": err}), 400
        try:
            names = self._load_dentists()
            taken = {n.lower() for n in names} | {DEFAULT_DENTIST.lower()}
            if name.lower() in taken:
                return jsonify({"success": False, "message": "That dentist is already in the list."}), 409
            if len(names) >= MAX_DENTISTS:
                return jsonify({"success": False, "message": "The list is full (max %d)." % MAX_DENTISTS}), 400
            names.append(name)
            self._save_dentists(names)
            return self._dentists_payload(names, message="Added.")
        except Exception:
            return jsonify({"success": False, "message": "Could not save the dentist."}), 500

    def settings_dentists_remove(self):
        if not session.get("admin_logged_in"):
            return self._dentists_forbidden()
        name = re.sub(r"\s+", " ", request.form.get("name", "")).strip()
        if not name:
            return jsonify({"success": False, "message": "No dentist given."}), 400
        if name.lower() == DEFAULT_DENTIST.lower():
            return jsonify({"success": False, "message": "The default dentist cannot be removed."}), 400
        try:
            names = self._load_dentists()
            kept = [n for n in names if n.lower() != name.lower()]
            if len(kept) == len(names):
                return jsonify({"success": False, "message": "That dentist is not in the list."}), 404
            self._save_dentists(kept)
            return self._dentists_payload(kept, message="Removed.")
        except Exception:
            return jsonify({"success": False, "message": "Could not remove the dentist."}), 500