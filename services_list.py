"""Services list (Settings > Treatments).

One saved list of service names feeds every place that shows services:
the patient navbar, the home page cards, the booking dropdowns, the service
detail pages and the Settings > Treatments card.

Only the NAME is stored (Firestore: Settings/treatments -> {"items": [...]}).
The 13 original services keep their slug, short card title, icon and page
content. A service added in Settings gets a generated slug, a generic
description and a generic service page.
"""
import re
import time

from datetime import UTC, datetime

from flask import jsonify, request, session


class ServicesMixin:
    # (name used in booking + records, url slug, home-card title, card icon)
    DEFAULT_SERVICES = [
        ("Dental Consultation",          "consultation",       "Dental Consultation",     "medical_services"),
        ("Oral Prophylaxis (Cleaning)",  "cleaning",           "Oral Prophylaxis",        "cleaning_services"),
        ("Tooth Restoration (Pasta)",    "pasta",              "Tooth Restoration",       "build"),
        ("Tooth Extraction (Gabot)",     "extraction",         "Tooth Extraction",        "remove_circle"),
        ("Dentures (Pustiso)",           "dentures",           "Dentures",                "sentiment_very_satisfied"),
        ("Crowns and Bridges",           "crowns-bridges",     "Crowns and Bridges",      "diamond"),
        ("Teeth Whitening",              "whitening",          "Teeth Whitening",         "auto_awesome"),
        ("Fluoride Treatment",           "fluoride",           "Fluoride Treatment",      "water_drop"),
        ("Pit and Fissure Sealant",      "sealant",            "Pit and Fissure Sealant", "shield"),
        ("Wisdom Teeth Removal",         "wisdom-tooth",       "Wisdom Teeth Removal",    "health_and_safety"),
        ("Root Canal Treatment",         "root-canal",         "Root Canal Treatment",    "biotech"),
        ("Periapical Xray",              "xray",               "Periapical X-ray",        "radiology"),
        ("Orthodontic Braces",           "orthodontic-braces", "Orthodontic Braces",      "grid_3x3"),
    ]
    # The braces follow-up scheduling is built around this exact name, so it
    # can never be removed from the list.
    LOCKED_SERVICES = {"Orthodontic Braces"}

    _SERVICES_TTL = 60          # seconds; saves a Firestore read on every page view
    _services_cache = {"names": None, "at": 0.0}

    # ------------------------------------------------------------------ data
    def _services_doc(self):
        return self.db.collection("Settings").document("treatments")

    def _load_service_names(self):
        snap = self._services_doc().get()
        data = snap.to_dict() if snap.exists else None
        if data and isinstance(data.get("items"), list):
            return [str(n) for n in data["items"]]
        return [d[0] for d in self.DEFAULT_SERVICES]

    def _save_service_names(self, names):
        self._services_doc().set({
            "items": list(names),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": str(session.get("admin_uid", "") or "")[:80],
        })
        self._services_cache["names"] = list(names)
        self._services_cache["at"] = time.time()

    SERVICE_MAX_ITEMS = 100
    SERVICE_MAX_LEN = 60
    _SERVICE_OK = re.compile(r"^[\w][\w .,'()/+%&\-]*$", re.UNICODE)

    def _clean_service_name(self, raw):
        """Returns (name, None) or (None, message)."""
        name = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not name:
            return None, "Type a treatment name."
        if len(name) > self.SERVICE_MAX_LEN:
            return None, "Keep the name to %d characters or fewer." % self.SERVICE_MAX_LEN
        if name.lower() == "other":
            return None, '"Other" is always available, so it does not need to be added.'
        if not self._SERVICE_OK.match(name):
            return None, "Use letters, numbers and normal punctuation only."
        return name, None

    def get_service_names(self):
        c = self._services_cache
        if c["names"] is None or time.time() - c["at"] > self._SERVICES_TTL:
            try:
                c["names"] = self._load_service_names()
            except Exception:
                c["names"] = c["names"] or [d[0] for d in self.DEFAULT_SERVICES]
            c["at"] = time.time()
        return list(c["names"])

    @staticmethod
    def _slugify(name):
        s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return s or "service"

    def get_clinic_services(self):
        """The list the templates loop over: dicts with name, slug,
        card_title, short_desc and icon."""
        defaults = {d[0]: d for d in self.DEFAULT_SERVICES}
        out, used = [], set()
        for name in self.get_service_names():
            if name in defaults:
                _n, slug, card_title, icon = defaults[name]
                short = self.SERVICES_DATA.get(slug, {}).get("short_desc", "")
            else:
                slug, card_title, icon = self._slugify(name), name, "medical_services"
                short = "Professional dental care at Capizonda Dental Clinic."
            base, i = slug, 2
            while slug in used:                     # keep slugs unique
                slug, i = f"{base}-{i}", i + 1
            used.add(slug)
            out.append({"name": name, "slug": slug, "card_title": card_title,
                        "short_desc": short, "icon": icon})
        return out

    def get_service_page(self, slug):
        """Data for /services/<slug>, or None when it is not in the list."""
        for s in self.get_clinic_services():
            if s["slug"] == slug:
                if slug in self.SERVICES_DATA:
                    return self.SERVICES_DATA[slug]
                return {
                    "title": s["name"],
                    "short_desc": s["short_desc"],
                    "full_desc": (f"{s['name']} is one of the services offered at Capizonda "
                                  "Dental Clinic. Book an appointment and our dentist will "
                                  "assess you and explain the treatment, the steps involved "
                                  "and the cost before anything is started."),
                    "benefits": ["Assessed and performed by our licensed dentist",
                                 "Treatment explained before it starts",
                                 "Comfortable, gentle care"],
                    "image": "",
                }
        return None

    # ---------------------------------------------------------------- routes
    def _register_services_routes(self):
        @self.app.context_processor
        def inject_clinic_services():
            return {"clinic_services": self.get_clinic_services()}

        self.app.route("/admin/settings/treatments", methods=["GET"])(self.settings_treatments_get)
        self.app.route("/admin/settings/treatments/add", methods=["POST"])(self.settings_treatments_add)
        self.app.route("/admin/settings/treatments/remove", methods=["POST"])(self.settings_treatments_remove)

    def settings_treatments_get(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            return jsonify({"success": True, "treatments": self._load_service_names()})
        except Exception as e:
            print("SETTINGS TREATMENTS READ ERROR:", e)
            return jsonify({"success": False, "message": "Could not load the treatment list."}), 500

    def settings_treatments_add(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            name, err = self._clean_service_name(request.form.get("name", ""))
            if err:
                return jsonify({"success": False, "message": err}), 400
            names = self._load_service_names()          # always the latest saved list
            if any(n.lower() == name.lower() for n in names):
                return jsonify({"success": False, "message": "That treatment is already in the list."}), 409
            if len(names) >= self.SERVICE_MAX_ITEMS:
                return jsonify({"success": False, "message": "The list is full."}), 400
            names.append(name)
            self._save_service_names(names)
            return jsonify({"success": True, "treatments": names})
        except Exception as e:
            print("SETTINGS TREATMENTS ADD ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def settings_treatments_remove(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            name = re.sub(r"\s+", " ", str(request.form.get("name", ""))).strip()
            if not name:
                return jsonify({"success": False, "message": "No treatment specified."}), 400
            if name in self.LOCKED_SERVICES:
                return jsonify({"success": False,
                                "message": '"%s" can\'t be removed because braces scheduling depends on it.' % name}), 400
            names = self._load_service_names()
            kept = [n for n in names if n.lower() != name.lower()]
            if len(kept) == len(names):
                return jsonify({"success": False, "message": "That treatment is not in the list."}), 404
            self._save_service_names(kept)
            return jsonify({"success": True, "treatments": kept})
        except Exception as e:
            print("SETTINGS TREATMENTS REMOVE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500