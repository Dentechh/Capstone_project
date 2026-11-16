"""About page content (Settings > About page).

One small document, Settings/about_info, holding the text of the dentist
section on the public About page:
    dr_name, dr_title, intro, school, licensed, association,
    technology, vision, community
Until staff first save it, the built-in defaults below (the text the page
had before) are used, so nothing changes until someone edits it.
Every page can read it as `about_info` in its template:
    {{ about_info.dr_name }}   {{ about_info.technology | about_rich }}
`about_rich` escapes the text and turns **word** into bold, so staff can keep
the bold words without typing any HTML.
It is cached in memory for a minute and refreshed on every save.
"""
import re
import time
from datetime import UTC, datetime

from flask import jsonify, request, session
from markupsafe import Markup, escape


class AboutInfoMixin:
    ABOUT_INFO_DOC = "about_info"
    ABOUT_INFO_DEFAULTS = {
        "dr_name": "Dr. Julix Dionne Capizonda",
        "dr_title": "Dentist",
        "intro": (
            "A licensed dentist trained at Iloilo Doctor's College, Dr. Julix Dionne "
            "Capizonda pairs gentle, patient-first care with modern technology \u2014 from "
            "intraoral cameras to UV sterilization \u2014 so every visit is comfortable, "
            "transparent, and thorough."
        ),
        "school": "Iloilo Doctor's College, Batch 2020",
        "licensed": "Since January 2024 (passed the board exams)",
        "association": "PDA Iloilo Chapter",
        "technology": (
            "We invest in modern technology including **Intraoral Cameras**, "
            "**Autoclave**, and **UV Sterilization** for efficient care."
        ),
        "vision": (
            "To reduce early extractions of permanent teeth caused by poor oral "
            "hygiene in the Philippines."
        ),
        "community": (
            "Participated in **INCGiving** dental missions, providing hygiene "
            "education to students in Jaro II Elementary School."
        ),
    }
    # field -> (label used in error messages, max length)
    ABOUT_INFO_LIMITS = {
        "dr_name": ("the dentist's name", 80),
        "dr_title": ("the title under the photo", 40),
        "intro": ("the introduction", 600),
        "school": ("the dental school", 120),
        "licensed": ("the license text", 120),
        "association": ("the association", 120),
        "technology": ("the Our Technology text", 400),
        "vision": ("the Vision text", 400),
        "community": ("the Community Work text", 400),
    }
    ABOUT_INFO_CACHE_SECONDS = 60

    # ------------------------------------------------------------------ utils
    def _about_info_ref(self):
        return self.db.collection("Settings").document(self.ABOUT_INFO_DOC)

    def _read_about_info(self, use_cache=True):
        now = time.time()
        cached = getattr(self, "_about_info_cache", None)
        if use_cache and cached and now - cached[0] < self.ABOUT_INFO_CACHE_SECONDS:
            return dict(cached[1])
        info = dict(self.ABOUT_INFO_DEFAULTS)
        try:
            snap = self._about_info_ref().get()
            if snap.exists:
                saved = snap.to_dict() or {}
                for k in info:
                    v = str(saved.get(k, "") or "").strip()
                    if v:
                        info[k] = v
        except Exception as e:
            print("ABOUT INFO READ ERROR:", e)
        self._about_info_cache = (now, info)
        return dict(info)

    def _write_about_info(self, info):
        doc = dict(info)
        doc["updated_at"] = datetime.now(UTC).isoformat()
        doc["updated_by"] = str(session.get("admin_uid", "") or "")[:80]
        self._about_info_ref().set(doc)
        self._about_info_cache = (time.time(), dict(info))

    def _clean_about_info(self, form):
        """Returns (info, None) or (None, message)."""
        info = {}
        for key, (label, limit) in self.ABOUT_INFO_LIMITS.items():
            v = re.sub(r"\s+", " ", str(form.get(key, "") or "")).strip()
            if not v:
                return None, f"Type {label}."
            if len(v) > limit:
                return None, f"Keep {label} to {limit} characters or fewer."
            info[key] = v
        return info, None

    # ----------------------------------------------------------------- routes
    def admin_settings_about(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        return jsonify({"success": True, "about": self._read_about_info(use_cache=False)})

    def admin_settings_about_save(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            info, err = self._clean_about_info(request.form)
            if err:
                return jsonify({"success": False, "message": err}), 400
            self._write_about_info(info)
            return jsonify({"success": True, "about": info})
        except Exception as e:
            print("SETTINGS ABOUT SAVE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def _register_about_info_routes(self):
        @self.app.context_processor
        def inject_about_info():
            return {"about_info": self._read_about_info()}

        @self.app.template_filter("about_rich")
        def about_rich(text):
            # Escape first, then turn **word** into bold: no raw HTML gets through.
            safe = str(escape(text or ""))
            safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
            return Markup(safe)

        self.app.route("/admin/settings/about")(self.admin_settings_about)
        self.app.route("/admin/settings/about/save", methods=["POST"])(self.admin_settings_about_save)