"""
Patient <-> dentist messaging for the Capizonda app.

Firestore layout (nothing existing is touched):
  Conversations/{patient_uid}                      one doc per patient
      patient_uid, patient_name, last_message, last_sender ("patient"|"admin"),
      last_message_at, unread_admin (int), unread_patient (int)
  Conversations/{patient_uid}/messages/{auto id}   the chat itself
      sender ("patient"|"admin"), text, created_at, staff_name,
      attachment (optional: id, name, ext, mime, kind "image"|"file", size)

Timestamps are ISO strings (same style as the rest of main.py), so
"newer than X" is a plain string comparison and needs no composite index.
Clients poll with a cursor ("after"/"since"), so each poll only reads
what's new -- cheap on Firestore reads.
"""
import io
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from datetime import UTC, datetime, timedelta, timezone

import bleach
from flask import jsonify, request, send_file, session
from werkzeug.utils import secure_filename

MSG_MAX_LEN = 1000

# ---- attachments -------------------------------------------------------
# Files are stored OUTSIDE static/ (so they are never public) in
#   message_uploads/<patient_uid>/<attachment_id>.<ext>
# and are only served by /messages/file/<uid>/<id>, which checks that the
# requester is an admin or that patient. The type is decided from the file's
# real bytes, never from the browser-supplied name or Content-Type.
MSG_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "message_uploads")
MSG_MAX_FILE_BYTES = 10 * 1024 * 1024          # 10 MB per attachment
MSG_ZIP_MAX_UNPACKED = 100 * 1024 * 1024       # reject zip bombs disguised as .docx/.xlsx
_MSG_UID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")
_MSG_ATT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MSG_ATTACH_TYPES = {
    # ext: (mime, kind)
    "png":  ("image/png", "image"),
    "jpg":  ("image/jpeg", "image"),
    "gif":  ("image/gif", "image"),
    "webp": ("image/webp", "image"),
    "pdf":  ("application/pdf", "file"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "file"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "file"),
}


def _msg_sniff_ext(raw):
    """File type from its content ('' if it is not an allowed type)."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:5] == b"%PDF-":
        return "pdf"
    if raw[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist()) > MSG_ZIP_MAX_UNPACKED:
                    return ""
                names = set(z.namelist())
            if "word/document.xml" in names:
                return "docx"
            if "xl/workbook.xml" in names:
                return "xlsx"
        except Exception:
            return ""
    return ""


def _msg_user_dir(uid):
    """Folder for one patient's files, or None if the uid is not a safe name."""
    if not _MSG_UID_RE.match(str(uid or "")):
        return None
    return os.path.join(MSG_UPLOAD_DIR, uid)
MSG_PAGE = 100          # messages returned on first load of a thread
MSG_LIST_LIMIT = 60     # conversations returned on first load of the inbox
_msg_last_sent = {}     # uid -> [timestamps], tiny in-memory flood guard
_msg_log_seen = {}      # (admin uid, patient uid) -> last time a reply was logged
MSG_LOG_EVERY = 3600    # log replies to the same patient at most once an hour
_PH = timezone(timedelta(hours=8))


def _now_iso():
    return datetime.now(UTC).isoformat(timespec="microseconds")


class MessagingMixin:
    Conversations = "Conversations"

    # ---------- helpers ----------
    def _msg_clean(self):
        text = bleach.clean((request.form.get("text") or "").strip())
        return text[:MSG_MAX_LEN]

    def _msg_rate_ok(self, key, per_minute=20):
        now = time.time()
        hits = [t for t in _msg_last_sent.get(key, []) if now - t < 60]
        if len(hits) >= per_minute:
            _msg_last_sent[key] = hits
            return False
        hits.append(now)
        _msg_last_sent[key] = hits
        return True

    def _msg_save_upload(self, uid):
        """
        Validate and save the optional 'file' field of the current request.
        Returns (attachment dict or None, error text or None). Nothing is
        written unless the file passes every check.
        """
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return None, None
        folder = _msg_user_dir(uid)
        if not folder:
            return None, "Invalid conversation."
        raw = upload.read(MSG_MAX_FILE_BYTES + 1)
        if not raw:
            return None, "That file is empty."
        if len(raw) > MSG_MAX_FILE_BYTES:
            return None, "That file is larger than 10 MB."
        ext = _msg_sniff_ext(raw)
        if not ext:
            return None, "Only photos (JPG, PNG, GIF, WebP), PDF, Word (.docx) and Excel (.xlsx) files are allowed."
        mime, kind = MSG_ATTACH_TYPES[ext]
        base = secure_filename(os.path.splitext(upload.filename)[0])[:60] or "attachment"
        att_id = uuid.uuid4().hex
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{att_id}.{ext}"), "wb") as fh:
            fh.write(raw)
        return {"id": att_id, "name": f"{base}.{ext}", "ext": ext,
                "mime": mime, "kind": kind, "size": len(raw)}, None

    def _msg_remove_upload(self, uid, att):
        try:
            folder = _msg_user_dir(uid)
            if folder and att:
                os.remove(os.path.join(folder, f"{att['id']}.{att['ext']}"))
        except OSError:
            pass

    def _msg_serialize(self, doc):
        d = doc.to_dict() or {}
        out = {
            "id": doc.id,
            "sender": d.get("sender", ""),
            "text": d.get("text", ""),
            "created_at": d.get("created_at", ""),
            "staff_name": d.get("staff_name", ""),
        }
        att = d.get("attachment")
        if isinstance(att, dict) and att.get("id"):
            try:
                uid = doc.reference.parent.parent.id
            except Exception:
                uid = ""
            out["attachment"] = {
                "name": att.get("name", "file"),
                "kind": att.get("kind", "file"),
                "mime": att.get("mime", ""),
                "size": att.get("size", 0),
                "url": f"/messages/file/{uid}/{att['id']}",
            }
        return out

    def msg_file(self, uid, att_id):
        """Serve one attachment, only to an admin or to the patient it belongs to."""
        is_admin = bool(session.get("admin_logged_in"))
        if not (is_admin or (session.get("uid") and session.get("uid") == uid)):
            return jsonify({"error": "Unauthorized"}), 403
        folder = _msg_user_dir(uid)
        if not folder or not _MSG_ATT_ID_RE.match(att_id or ""):
            return jsonify({"error": "Not found"}), 404
        try:
            snap = None
            for d in (self.db.collection(self.Conversations).document(uid)
                      .collection("messages")
                      .where("attachment.id", "==", att_id).limit(1).stream()):
                snap = d
            att = ((snap.to_dict() or {}).get("attachment") if snap else None) or {}
            ext = att.get("ext", "")
            if ext not in MSG_ATTACH_TYPES:
                return jsonify({"error": "Not found"}), 404
            path = os.path.join(folder, f"{att_id}.{ext}")
            if not os.path.isfile(path):
                return jsonify({"error": "Not found"}), 404
            mime, kind = MSG_ATTACH_TYPES[ext]
            return send_file(path, mimetype=mime, as_attachment=(kind != "image"),
                             download_name=att.get("name") or f"file.{ext}")
        except Exception as e:
            print("MSG FILE ERROR:", e)
            return jsonify({"error": "Something went wrong."}), 500

    def _msg_thread_query(self, uid, after):
        q = (self.db.collection(self.Conversations).document(uid)
             .collection("messages"))
        if after:
            return q.where("created_at", ">", after).order_by("created_at").limit(200)
        # first load: newest N, then flipped back to oldest-first below
        return q.order_by("created_at", direction="DESCENDING").limit(MSG_PAGE)

    def _msg_load(self, uid, after):
        docs = list(self._msg_thread_query(uid, after).stream())
        msgs = [self._msg_serialize(d) for d in docs]
        if not after:
            msgs.reverse()
        return msgs

    def _msg_store(self, uid, patient_name, sender, text, staff_name="", attachment=None):
        now = _now_iso()
        conv = self.db.collection(self.Conversations).document(uid)
        doc = {
            "sender": sender, "text": text,
            "created_at": now, "staff_name": staff_name,
        }
        if attachment:
            doc["attachment"] = attachment
        preview = text[:120]
        if not preview and attachment:
            preview = ("\U0001F4F7 Photo" if attachment["kind"] == "image"
                       else "\U0001F4CE " + attachment["name"])[:120]
        try:
            conv.collection("messages").document().set(doc)
            fields = {
                "patient_uid": uid,
                "last_message": preview,
                "last_sender": sender,
                "last_message_at": now,
            }
            if patient_name:
                fields["patient_name"] = patient_name
            if sender == "patient":
                fields["unread_admin"] = fb_firestore_increment(1)
            else:
                fields["unread_patient"] = fb_firestore_increment(1)
                fields["unread_admin"] = 0      # replying means the dentist has read it
            conv.set(fields, merge=True)
        except Exception:
            self._msg_remove_upload(uid, attachment)   # don't leave an orphan file
            raise
        return now

    def _msg_log(self, action, patient_name, detail=""):
        """Add one line to the admin Activity Log (never includes message text)."""
        try:
            now = datetime.now(UTC)
            entry = {
                "id": uuid.uuid4().hex[:12],
                "ts": now.isoformat(),
                "day": now.astimezone(_PH).strftime("%Y-%m-%d"),
                "category": "patients",
                "action": action,
                "detail": detail[:240],
                "target": str(patient_name or "")[:120],
                "actor_name": str(session.get("admin_name", "") or "")[:80],
                "actor_email": str(session.get("admin_email", "") or "")[:120],
                "actor_uid": str(session.get("admin_uid", "") or "")[:80],
            }
            threading.Thread(target=self._activity_write, args=(entry,), daemon=True).start()
        except Exception as e:
            print("MSG ACTIVITY LOG skipped:", e)

    # ---------- patient side ----------
    def msg_patient_send(self):
        uid = session.get("uid")
        if not uid:
            return jsonify({"success": False, "message": "Please log in first."}), 401
        text = self._msg_clean()
        has_file = bool(request.files.get("file") and request.files["file"].filename)
        if not text and not has_file:
            return jsonify({"success": False, "message": "Message is empty."}), 400
        if not self._msg_rate_ok("p:" + uid):
            return jsonify({"success": False, "message": "You're sending too fast. Please wait a moment."}), 429
        try:
            # Accounts the admin blocked (Customer_Account.disabled) can't message,
            # even if their session is still alive. One read, only when sending.
            acct = self.db.collection(self.Customer_Account).document(uid).get()
            if acct.exists and (acct.to_dict() or {}).get("disabled"):
                return jsonify({"success": False,
                                "message": "Your account can't send messages. Please contact the clinic."}), 403
            att, err = self._msg_save_upload(uid)
            if err:
                return jsonify({"success": False, "message": err}), 400
            self._msg_store(uid, session.get("name", "Patient"), "patient", text, attachment=att)
            return jsonify({"success": True})
        except Exception as e:
            print("MSG PATIENT SEND ERROR:", e)
            return jsonify({"success": False, "message": "Could not send. Please try again."}), 500

    def msg_patient_thread(self):
        """?after=<iso> returns only newer messages. ?mark_read=1 clears the badge."""
        uid = session.get("uid")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        try:
            after = request.args.get("after", "").strip()
            msgs = self._msg_load(uid, after)
            # Write only if the dentist's messages came back in this batch;
            # an empty poll costs a read but never a write.
            if request.args.get("mark_read") == "1" and any(m["sender"] != "patient" for m in msgs):
                self.db.collection(self.Conversations).document(uid).set(
                    {"unread_patient": 0}, merge=True)
            return jsonify({"messages": msgs})
        except Exception as e:
            print("MSG PATIENT THREAD ERROR:", e)
            return jsonify({"error": "Something went wrong."}), 500

    def msg_patient_unread(self):
        """One document read. Used for the red badge on the Messages button."""
        uid = session.get("uid")
        if not uid:
            return jsonify({"unread": 0}), 401
        try:
            snap = self.db.collection(self.Conversations).document(uid).get()
            n = int((snap.to_dict() or {}).get("unread_patient", 0)) if snap.exists else 0
            return jsonify({"unread": max(n, 0)})
        except Exception as e:
            print("MSG PATIENT UNREAD ERROR:", e)
            return jsonify({"unread": 0}), 500

    # ---------- admin side ----------
    def msg_admin_conversations(self):
        """
        ?since=<iso> returns only conversations updated after that moment
        (so polling is cheap). Without it: the most recent MSG_LIST_LIMIT.
        """
        if not session.get("admin_logged_in"):
            return jsonify({"error": "Unauthorized"}), 403
        try:
            if request.args.get("badge") == "1":
                # sidebar badge only: one aggregate count, no conversation reads
                n = (self.db.collection(self.Conversations)
                     .where("unread_admin", ">", 0).count().get()[0][0].value)
                return jsonify({"unread_total": n})
            since = request.args.get("since", "").strip()
            q = self.db.collection(self.Conversations)
            if since:
                q = q.where("last_message_at", ">", since)
            q = q.order_by("last_message_at", direction="DESCENDING").limit(MSG_LIST_LIMIT)
            out = []
            for d in q.stream():
                c = d.to_dict() or {}
                out.append({
                    "uid": d.id,
                    "name": c.get("patient_name", "Patient"),
                    "last_message": c.get("last_message", ""),
                    "last_sender": c.get("last_sender", ""),
                    "last_message_at": c.get("last_message_at", ""),
                    "unread": int(c.get("unread_admin", 0) or 0),
                })
            return jsonify({"conversations": out})
        except Exception as e:
            print("MSG ADMIN LIST ERROR:", e)
            return jsonify({"error": "Something went wrong."}), 500

    def msg_admin_thread(self, uid):
        if not session.get("admin_logged_in"):
            return jsonify({"error": "Unauthorized"}), 403
        try:
            after = request.args.get("after", "").strip()
            msgs = self._msg_load(uid, after)
            if request.args.get("mark_read") == "1" and any(m["sender"] != "admin" for m in msgs):
                self.db.collection(self.Conversations).document(uid).set(
                    {"unread_admin": 0}, merge=True)
            out = {"messages": msgs}
            if not after:
                # Only when the thread is first opened (one extra read): is this
                # patient's account blocked, and does an account exist to block?
                acct = self.db.collection(self.Customer_Account).document(uid).get()
                out["can_block"] = bool(acct.exists)
                out["blocked"] = bool(acct.exists and (acct.to_dict() or {}).get("disabled"))
            return jsonify(out)
        except Exception as e:
            print("MSG ADMIN THREAD ERROR:", e)
            return jsonify({"error": "Something went wrong."}), 500

    def msg_admin_send(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        uid = bleach.clean((request.form.get("uid") or "").strip())
        text = self._msg_clean()
        has_file = bool(request.files.get("file") and request.files["file"].filename)
        if not uid or (not text and not has_file):
            return jsonify({"success": False, "message": "Missing message or patient."}), 400
        if not self._msg_rate_ok("a:" + str(session.get("admin_uid", "")), per_minute=60):
            return jsonify({"success": False, "message": "Slow down a little."}), 429
        try:
            conv = self.db.collection(self.Conversations).document(uid).get()
            key = (str(session.get("admin_uid", "")), uid)
            if conv.exists:
                att, err = self._msg_save_upload(uid)
                if err:
                    return jsonify({"success": False, "message": err}), 400
                self._msg_store(uid, "", "admin", text,
                                staff_name=str(session.get("admin_name", ""))[:80],
                                attachment=att)
                if time.time() - _msg_log_seen.get(key, 0) > MSG_LOG_EVERY:
                    _msg_log_seen[key] = time.time()
                    self._msg_log("Replied to a patient message",
                                  (conv.to_dict() or {}).get("patient_name", "Patient"))
                return jsonify({"success": True})

            # No conversation yet: the dentist is starting one ("new" must be set,
            # and the account must be a real, unblocked patient account).
            if request.form.get("new") != "1":
                return jsonify({"success": False, "message": "Conversation not found."}), 404
            acct = self.db.collection(self.Customer_Account).document(uid).get()
            if not acct.exists:
                return jsonify({"success": False, "message": "Patient account not found."}), 404
            a = acct.to_dict() or {}
            if a.get("disabled"):
                return jsonify({"success": False, "message": "This account is blocked."}), 403
            name = (f"{a.get('firstname', '')} {a.get('lastname', '')}".strip()
                    or a.get("name") or "Patient")
            att, err = self._msg_save_upload(uid)
            if err:
                return jsonify({"success": False, "message": err}), 400
            self._msg_store(uid, name, "admin", text,
                            staff_name=str(session.get("admin_name", ""))[:80],
                            attachment=att)
            _msg_log_seen[key] = time.time()
            self._msg_log("Started a conversation with a patient", name)
            return jsonify({"success": True})
        except Exception as e:
            print("MSG ADMIN SEND ERROR:", e)
            return jsonify({"success": False, "message": "Could not send. Please try again."}), 500

    def msg_admin_patients(self):
        """Admin: find a patient account to start a new conversation with.
        Uses the same cached account list as User Management (no extra reads)."""
        if not session.get("admin_logged_in"):
            return jsonify({"error": "Unauthorized"}), 403
        try:
            q = (request.args.get("q") or "").strip().lower()[:60]
            out = []
            for uid, d in self._get_manageable_accounts_cached():
                if d.get("provider") not in ("google", "password") or d.get("disabled"):
                    continue
                name = (f"{d.get('firstname', '')} {d.get('lastname', '')}".strip()
                        or d.get("name") or "")
                email = d.get("email") or ""
                if q and q not in name.lower() and q not in email.lower():
                    continue
                out.append({"uid": uid, "name": name or email or "Patient", "email": email})
            out.sort(key=lambda r: r["name"].lower())
            return jsonify({"patients": out[:15]})
        except Exception as e:
            print("MSG ADMIN PATIENTS ERROR:", e)
            return jsonify({"error": "Something went wrong."}), 500

    def msg_admin_mark(self):
        """Admin: mark a conversation unread (unread=1) or read (unread=0)."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        uid = bleach.clean((request.form.get("uid") or "").strip())
        if not uid:
            return jsonify({"success": False, "message": "Missing patient."}), 400
        want_unread = request.form.get("unread") == "1"
        try:
            # update() (not set) so a deleted conversation is never recreated empty
            self.db.collection(self.Conversations).document(uid).update(
                {"unread_admin": 1 if want_unread else 0})
            return jsonify({"success": True})
        except Exception as e:
            print("MSG ADMIN MARK ERROR:", e)
            return jsonify({"success": False, "message": "Could not update. Please try again."}), 500

    def msg_admin_delete(self):
        """Admin: permanently delete one patient's whole conversation."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        uid = bleach.clean((request.form.get("uid") or "").strip())
        if not uid:
            return jsonify({"success": False, "message": "Missing patient."}), 400
        try:
            conv = self.db.collection(self.Conversations).document(uid)
            snap = conv.get()
            patient_name = (snap.to_dict() or {}).get("patient_name", "Patient") if snap.exists else "Patient"
            msgs = conv.collection("messages")
            while True:                      # Firestore batches hold up to 500 writes
                docs = list(msgs.limit(400).stream())
                if not docs:
                    break
                batch = self.db.batch()
                for d in docs:
                    batch.delete(d.reference)
                batch.commit()
            conv.delete()
            folder = _msg_user_dir(uid)
            if folder:
                shutil.rmtree(folder, ignore_errors=True)   # remove this patient's files too
            self._msg_log("Deleted a message conversation", patient_name)
            return jsonify({"success": True})
        except Exception as e:
            print("MSG ADMIN DELETE ERROR:", e)
            return jsonify({"success": False, "message": "Could not delete. Please try again."}), 500

    # ---------- route registration ----------
    def _register_message_routes(self):
        r = self.app.route
        r("/messages/send", methods=["POST"])(self.msg_patient_send)
        r("/messages/thread")(self.msg_patient_thread)
        r("/messages/unread")(self.msg_patient_unread)
        r("/messages/file/<uid>/<att_id>")(self.msg_file)
        r("/admin/messages/conversations")(self.msg_admin_conversations)
        r("/admin/messages/thread/<uid>")(self.msg_admin_thread)
        r("/admin/messages/send", methods=["POST"])(self.msg_admin_send)
        r("/admin/messages/delete", methods=["POST"])(self.msg_admin_delete)
        r("/admin/messages/mark", methods=["POST"])(self.msg_admin_mark)
        r("/admin/messages/patients")(self.msg_admin_patients)


def fb_firestore_increment(n):
    from google.cloud import firestore
    return firestore.Increment(n)