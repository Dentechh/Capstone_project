"""Patient data backup / restore for the admin "My Patients" page.

Kept in its own module (like messaging.py) so main.py only needs a few lines:

    from patient_backup import BackupMixin
    class DentalClinicApp(BaseFlaskApp, MessagingMixin, BackupMixin): ...
    self._register_backup_routes()        # at the end of _register_routes()

Routes (all admin-only, all POST so they are CSRF protected):
    /admin/backup/export    download one .json file with everything
    /admin/backup/preview   read an uploaded backup and report what it holds
                            (writes nothing)
    /admin/backup/import    restore it

Restore rules:
  * It NEVER overwrites. A Patients document or an account that already exists
    is skipped, so an import can never replace newer data with older data.
  * An account's treatment records (Approve, Done_procedure, appointments) are
    only restored together with an account that did not exist.
  * Each account's records are written BEFORE the account document itself, so
    if an import is interrupted, running it again finishes the job.
"""

import base64
import hashlib
import json
import re
import threading
from datetime import UTC, datetime, timedelta, timezone

from flask import Response, jsonify, request, session

try:  # the real Firestore types; only needed to (de)serialise special values
    from google.cloud import firestore as _firestore
    _GeoPoint = _firestore.GeoPoint
    _DocumentReference = _firestore.DocumentReference
except Exception:  # pragma: no cover - lets the helpers be unit tested alone
    _firestore = None

    class _GeoPoint:  # type: ignore
        def __init__(self, latitude, longitude):
            self.latitude, self.longitude = latitude, longitude

    class _DocumentReference:  # type: ignore
        path = ""

_PH_TZ = timezone(timedelta(hours=8))

BACKUP_FORMAT = "capizonda-backup"
BACKUP_VERSION = 1
BACKUP_MAX_BYTES = 200 * 1024 * 1024          # largest backup file we accept
BACKUP_SUBCOLLECTIONS = ("Approve", "Done_procedure", "appointments")
_FS = "__fs__"                                  # marks an encoded special value
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.@+:\-]{1,150}$")
_PATIENT_NUM = re.compile(r"^P-(\d+)$")


# ---------------------------------------------------------------------------
# Firestore value <-> JSON helpers (module level so they can be tested alone)
# ---------------------------------------------------------------------------
def fs_encode(value):
    """Turn a Firestore value into something json.dumps can write."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return {_FS: "datetime", "v": value.isoformat()}
    if isinstance(value, _GeoPoint):
        return {_FS: "geopoint", "lat": value.latitude, "lng": value.longitude}
    if isinstance(value, _DocumentReference):
        return {_FS: "ref", "v": value.path}
    if isinstance(value, (bytes, bytearray)):
        return {_FS: "bytes", "v": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): fs_encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [fs_encode(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def fs_decode(value, db=None):
    """Inverse of fs_encode."""
    if isinstance(value, dict):
        kind = value.get(_FS)
        if kind == "datetime":
            return datetime.fromisoformat(value["v"])
        if kind == "geopoint":
            return _GeoPoint(value["lat"], value["lng"])
        if kind == "bytes":
            return base64.b64decode(value["v"])
        if kind == "ref":
            path = str(value.get("v", ""))
            if db is not None and path and len(path.split("/")) % 2 == 0:
                return db.document(path)
            return path
        return {k: fs_decode(v, db) for k, v in value.items()}
    if isinstance(value, list):
        return [fs_decode(v, db) for v in value]
    return value


def backup_checksum(body):
    """SHA-256 over the data part of a backup (detects damaged/edited files)."""
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class _BatchWriter:
    """Firestore batched writes, flushed by operation count and by size."""

    def __init__(self, db, max_ops=300, max_bytes=6 * 1024 * 1024):
        self.db, self.max_ops, self.max_bytes = db, max_ops, max_bytes
        self.batch, self.ops, self.size = db.batch(), 0, 0

    def set(self, ref, data, approx_bytes):
        if self.ops and (self.ops >= self.max_ops or self.size + approx_bytes > self.max_bytes):
            self.flush()
        self.batch.set(ref, data)
        self.ops += 1
        self.size += approx_bytes

    def flush(self):
        if self.ops:
            self.batch.commit()
        self.batch, self.ops, self.size = self.db.batch(), 0, 0


# ---------------------------------------------------------------------------
# The mixin
# ---------------------------------------------------------------------------
class BackupMixin:
    _backup_lock = threading.Lock()

    def _register_backup_routes(self):
        self.app.route("/admin/backup/export", methods=["POST"])(self.admin_backup_export)
        self.app.route("/admin/backup/preview", methods=["POST"])(self.admin_backup_preview)
        self.app.route("/admin/backup/import", methods=["POST"])(self.admin_backup_import)
        self.app.route("/admin/backup/report", methods=["POST"])(self.admin_backup_report)

    # --- export -----------------------------------------------------------
    def _backup_build(self, include_charts):
        patients = []
        for doc in self.db.collection(self.Doc_Patients).stream():
            patients.append({"id": doc.id, "data": fs_encode(doc.to_dict() or {})})

        sub_names = self._backup_sub_names()
        accounts = []
        for doc in self.db.collection(self.Customer_Account).stream():
            subs = {}
            for name in sub_names:
                items = []
                for sd in doc.reference.collection(name).stream():
                    d = sd.to_dict() or {}
                    if not include_charts and name == "Done_procedure":
                        d.pop("chart_image", None)
                    items.append({"id": sd.id, "data": fs_encode(d)})
                if items:
                    subs[name] = items
            accounts.append({
                "id": doc.id,
                "data": fs_encode(doc.to_dict() or {}),
                "subcollections": subs,
            })

        counters = {}
        snap = self.db.collection("Counters").document("patients").get()
        if snap.exists:
            counters["patients"] = fs_encode(snap.to_dict() or {})

        body = {"patients": patients, "accounts": accounts, "counters": counters}
        procedures = sum(
            len((item["data"] or {}).get("procedures") or [])
            for a in accounts for item in a["subcollections"].get("Done_procedure", [])
        )
        return {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": str(session.get("admin_name", "") or "")[:80],
            "include_charts": bool(include_charts),
            "counts": {
                "patients": len(patients),
                "accounts": len(accounts),
                "treatment_records": procedures,
            },
            "note": "Confidential patient records. Keep this file somewhere safe.",
            "sha256": backup_checksum(body),
            **body,
        }

    def _backup_sub_names(self):
        names = list(BACKUP_SUBCOLLECTIONS)
        client_sub = getattr(self, "Appointment_cliets", "appointments")
        return [client_sub if n == "appointments" else n for n in names]

    def admin_backup_export(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        include_charts = request.form.get("include_charts", "1") != "0"
        try:
            payload = self._backup_build(include_charts)
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            stamp = datetime.now(_PH_TZ).strftime("%Y-%m-%d_%H%M")
            resp = Response(body, mimetype="application/json")
            resp.headers["Content-Disposition"] = (
                f'attachment; filename="capizonda-backup-{stamp}.json"'
            )
            return resp
        except Exception as e:
            print("BACKUP EXPORT ERROR:", e)
            return jsonify({"success": False,
                            "message": "Could not create the backup. Please try again."}), 500

    # --- readable copy: Excel / Word (for reading and printing only) ------
    def admin_backup_report(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        fmt = request.form.get("format", "").strip().lower()
        if fmt not in ("xlsx", "docx"):
            return jsonify({"success": False, "message": "Choose Excel or Word."}), 400
        try:
            import patient_report
            payload = self._backup_build(include_charts=False)
            if fmt == "xlsx":
                data = patient_report.build_xlsx(payload)
                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:
                data = patient_report.build_docx(payload)
                mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            stamp = datetime.now(_PH_TZ).strftime("%Y-%m-%d_%H%M")
            resp = Response(data, mimetype=mime)
            resp.headers["Content-Disposition"] = (
                f'attachment; filename="capizonda-patient-records-{stamp}.{fmt}"'
            )
            return resp
        except ImportError:
            return jsonify({"success": False,
                            "message": "Excel/Word export needs two packages. On the server run: "
                                       "pip install openpyxl python-docx"}), 501
        except Exception as e:
            print("BACKUP REPORT ERROR:", e)
            return jsonify({"success": False,
                            "message": "Could not create the document. Please try again."}), 500

    # --- reading + checking an uploaded backup ---------------------------
    def _backup_read_upload(self):
        """-> (data, error_message, http_status)"""
        f = request.files.get("backup_file")
        if not f or not f.filename:
            return None, "Choose a backup file first.", 400
        if not f.filename.lower().endswith(".json"):
            return None, "That is not a backup file (it must end in .json).", 400
        raw = f.read(BACKUP_MAX_BYTES + 1)
        if len(raw) > BACKUP_MAX_BYTES:
            return None, "That backup file is too large to import here.", 413
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except Exception:
            return None, "That file could not be read. It may be damaged.", 400
        err = self._backup_validate(data)
        if err:
            return None, err, 400
        return data, None, 200

    def _backup_validate(self, data):
        """Return an error message, or None when the backup is usable."""
        if not isinstance(data, dict) or data.get("format") != BACKUP_FORMAT:
            return "That is not a Capizonda backup file."
        version = data.get("version")
        if not isinstance(version, int) or version < 1 or version > BACKUP_VERSION:
            return "This backup was made by a newer version and cannot be imported."
        patients, accounts = data.get("patients"), data.get("accounts")
        counters = data.get("counters", {})
        if not isinstance(patients, list) or not isinstance(accounts, list) \
                or not isinstance(counters, dict):
            return "The backup file is incomplete."
        allowed_subs = set(self._backup_sub_names())
        for p in patients:
            if not isinstance(p, dict) or not isinstance(p.get("data"), dict) \
                    or not _SAFE_ID.match(str(p.get("id", ""))):
                return "The backup file contains an invalid patient entry."
        for a in accounts:
            if not isinstance(a, dict) or not isinstance(a.get("data"), dict) \
                    or not _SAFE_ID.match(str(a.get("id", ""))):
                return "The backup file contains an invalid account entry."
            subs = a.get("subcollections", {})
            if not isinstance(subs, dict) or not set(subs) <= allowed_subs:
                return "The backup file contains unknown record types."
            for items in subs.values():
                if not isinstance(items, list):
                    return "The backup file is incomplete."
                for it in items:
                    if not isinstance(it, dict) or not isinstance(it.get("data"), dict) \
                            or not _SAFE_ID.match(str(it.get("id", ""))):
                        return "The backup file contains an invalid record."
        body = {"patients": patients, "accounts": accounts, "counters": counters}
        if data.get("sha256") != backup_checksum(body):
            return "The backup file was changed or damaged and cannot be trusted."
        return None

    def _backup_existing_ids(self, collection, ids):
        existing = set()
        col = self.db.collection(collection)
        ids = list(ids)
        for i in range(0, len(ids), 300):
            refs = [col.document(x) for x in ids[i:i + 300]]
            for snap in self.db.get_all(refs):
                if snap.exists:
                    existing.add(snap.id)
        return existing

    def _backup_plan(self, data):
        """Work out what an import would add and what it would skip."""
        existing_p = self._backup_existing_ids(
            self.Doc_Patients, [p["id"] for p in data["patients"]])
        existing_a = self._backup_existing_ids(
            self.Customer_Account, [a["id"] for a in data["accounts"]])
        new_patients = [p for p in data["patients"] if p["id"] not in existing_p]
        new_accounts = [a for a in data["accounts"] if a["id"] not in existing_a]
        records = {n: 0 for n in self._backup_sub_names()}
        treatments = 0
        for a in new_accounts:
            for name, items in a.get("subcollections", {}).items():
                records[name] = records.get(name, 0) + len(items)
                if name == "Done_procedure":
                    treatments += sum(len((i["data"].get("procedures") or [])) for i in items)
        summary = {
            "created_at": data.get("created_at", ""),
            "created_by": data.get("created_by", ""),
            "include_charts": bool(data.get("include_charts", True)),
            "patients_in_file": len(data["patients"]),
            "patients_new": len(new_patients),
            "patients_skipped": len(data["patients"]) - len(new_patients),
            "accounts_in_file": len(data["accounts"]),
            "accounts_new": len(new_accounts),
            "accounts_skipped": len(data["accounts"]) - len(new_accounts),
            "treatment_records_new": treatments,
            "appointments_new": records.get(self.Appointment_cliets, 0),
        }
        return summary, new_patients, new_accounts

    def admin_backup_preview(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            data, err, status = self._backup_read_upload()
            if err:
                return jsonify({"success": False, "message": err}), status
            summary, _, _ = self._backup_plan(data)
            return jsonify({"success": True, "summary": summary})
        except Exception as e:
            print("BACKUP PREVIEW ERROR:", e)
            return jsonify({"success": False,
                            "message": "Could not read the backup. Please try again."}), 500

    # --- restore ----------------------------------------------------------
    def admin_backup_import(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        if not self._backup_lock.acquire(blocking=False):
            return jsonify({"success": False,
                            "message": "A restore is already running. Please wait."}), 409
        try:
            data, err, status = self._backup_read_upload()
            if err:
                return jsonify({"success": False, "message": err}), status
            summary, new_patients, new_accounts = self._backup_plan(data)

            writer = _BatchWriter(self.db)
            pat_col = self.db.collection(self.Doc_Patients)
            acc_col = self.db.collection(self.Customer_Account)
            restored_rows = []
            max_number = 0

            def write(ref, enc):
                writer.set(ref, fs_decode(enc, self.db), len(json.dumps(enc)) + 200)

            for p in new_patients:
                write(pat_col.document(p["id"]), p["data"])
                m = _PATIENT_NUM.match(p["id"])
                if m:
                    max_number = max(max_number, int(m.group(1)))

            for a in new_accounts:
                acc_ref = acc_col.document(a["id"])
                # records first, the account document last (see module note)
                for name, items in a.get("subcollections", {}).items():
                    for it in items:
                        write(acc_ref.collection(name).document(it["id"]), it["data"])
                        if name == "Done_procedure":
                            rows = it["data"].get("procedures") or []
                            restored_rows.extend(r for r in rows if isinstance(r, dict))
                write(acc_ref, a["data"])
            writer.flush()

            self._backup_bump_counter(data.get("counters", {}), max_number)
            self._backup_after_restore(restored_rows)

            detail = (f"{summary['patients_new']} patients, "
                      f"{summary['accounts_new']} accounts, "
                      f"{summary['treatment_records_new']} treatment records restored")
            return jsonify({"success": True, "summary": summary, "detail": detail,
                            "message": "Backup restored. " + detail + "."})
        except Exception as e:
            print("BACKUP IMPORT ERROR:", e)
            return jsonify({"success": False,
                            "message": "The restore stopped part-way. Run the same "
                                       "import again to finish it; nothing is overwritten."}), 500
        finally:
            self._backup_lock.release()

    def _backup_bump_counter(self, counters, restored_max):
        """Make sure new Patient IDs never collide with restored ones."""
        try:
            wanted = restored_max
            saved = (counters.get("patients") or {}).get("last_number")
            if isinstance(saved, int):
                wanted = max(wanted, saved)
            if wanted <= 0:
                return
            ref = self.db.collection("Counters").document("patients")
            snap = ref.get()
            current = (snap.to_dict() or {}).get("last_number", 0) if snap.exists else 0
            if not isinstance(current, int) or current < wanted:
                ref.set({"last_number": wanted}, merge=True)
        except Exception as e:
            print("BACKUP counter bump failed:", e)

    def _backup_after_restore(self, restored_rows):
        """Refresh caches and the daily financial aggregates."""
        for fn in ("_invalidate_accounts_cache", "_invalidate_patients_cache",
                   "_invalidate_financial_cache"):
            try:
                getattr(self, fn)()
            except Exception as e:
                print("BACKUP cache refresh failed:", fn, e)
        if restored_rows:
            try:
                self._agg_apply_rows(add=restored_rows)   # never raises
            except Exception as e:
                print("BACKUP aggregate update failed (run /admin/aggregates/repair):", e)