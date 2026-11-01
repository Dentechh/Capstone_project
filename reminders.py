"""
Reminders: follow-up visits taken from the treatment records.

One document per follow-up row in  Reminders/<id>.  Created / refreshed /
removed by _reminders_sync() whenever a treatment record is saved, edited or
deleted, so the Reminders page always matches the records.

Patients WITH a login: Orthodontic Braces keeps its existing patient-side
proposal flow (Braces_Proposals); the Reminders page reads that status and
shows it, it never changes it.

Patients WITHOUT a login (walkin_* accounts): the admin / dentist sees the
contact number, can call or text, and can book the visit. If nobody acts in
BRACES_DECISION_DAYS days, the daily cron books it automatically from the
patient's previous details (see _reminders_auto_book).
"""
import hashlib
import re
import threading
from datetime import UTC, datetime, timedelta, timezone

import bleach
from flask import jsonify, request, session
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

PH_TZ = timezone(timedelta(hours=8))


class RemindersMixin:
    REMINDERS = "Reminders"
    REMINDER_ACTIVE = ("awaiting", "contacted", "needs_review")
    REMINDER_HISTORY_DAYS = 60
    _TIME_RE = re.compile(r"^\d{2}:\d{2}$")

    # ------------------------------------------------------------------ utils
    def _reminder_ref(self, rid):
        return self.db.collection(self.REMINDERS).document(str(rid))

    @staticmethod
    def _reminder_key(uid, done_doc_id, procedure, day_str):
        raw = f"{uid}|{done_doc_id}|{str(procedure).strip().lower()}|{day_str}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]

    def _reminder_deadline(self, day):
        """ISO (UTC) time the 10-day window ends: 10 days from now, but never
        later than the end of the day before the due date (same rule as the
        braces proposals)."""
        now_ph = datetime.now(PH_TZ)
        today = now_ph.date()
        deadline = now_ph + timedelta(days=self.BRACES_DECISION_DAYS)
        last_ok = day - timedelta(days=1)
        cap = datetime(last_ok.year, last_ok.month, last_ok.day, 23, 59, 59, tzinfo=PH_TZ)
        if cap < now_ph:
            cap = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=PH_TZ)
        return min(deadline, cap).astimezone(UTC).isoformat()

    def _reminders_fetch(self, refs):
        """Batched get_all; returns {doc_id: dict} for docs that exist."""
        out = {}
        refs = list(refs)
        for i in range(0, len(refs), 200):
            try:
                for snap in self.db.get_all(refs[i:i + 200]):
                    if snap.exists:
                        out[snap.id] = snap.to_dict() or {}
            except Exception as e:
                print("REMINDERS FETCH ERROR:", e)
        return out

    @staticmethod
    def _clean_phone(value):
        """Digits (and a leading +) only, or '' if it is not a plausible number."""
        value = str(value or "").strip()
        if not re.fullmatch(r"[+0-9][0-9 ()\-+]{5,24}", value):
            return ""
        digits = re.sub(r"\D", "", value)
        if not 7 <= len(digits) <= 15:
            return ""
        return ("+" if value.startswith("+") else "") + digits


    def _reminder_patient_id(self, uid, patient_id):
        """The id of the real Patients document: the one passed in if it exists,
        otherwise the patient linked to this account. Falls back to what was given."""
        patient_id = str(patient_id or "").strip()
        try:
            if patient_id and self.db.collection(self.Doc_Patients).document(patient_id).get().exists:
                return patient_id
            linked = self.db.collection(self.Doc_Patients).where(
                filter=FieldFilter("account_uid", "==", str(uid))
            ).limit(1).get()
            if linked:
                return linked[0].id
        except Exception as e:
            print("REMINDER PATIENT ID LOOKUP ERROR:", e)
        return patient_id

    # ------------------------------------------------------------------- sync
    def _reminders_sync(self, uid, patient_id, done_doc_id, rows):
        """
        Make Reminders match ONE treatment record (done_doc_id) after it was
        saved, edited or deleted. `rows` is the record's full procedure list
        (an empty list when the record was deleted). Never raises.

        - new follow-up date           -> reminder created (clock starts now)
        - same procedure + same date   -> left alone (clock NOT restarted)
        - date changed / row removed   -> unanswered reminder deleted
        - answered / booked reminders  -> kept as history
        """
        try:
            uid = str(uid or "").strip()
            done_doc_id = str(done_doc_id or "").strip()
            if not uid or not done_doc_id:
                return
            today = self._braces_today()
            has_account = not self._is_walkin_uid(uid)

            desired = {}
            for r in rows or []:
                r = r or {}
                raw = str(r.get("next_appointment") or "").strip()
                proc = str(r.get("procedure") or "").strip()
                day = self._braces_parse_day(raw)
                if not raw or not proc or day is None or day < today:
                    continue
                day_str = day.strftime("%Y-%m-%d")
                time_str = raw[11:16] if len(raw) >= 16 and self._TIME_RE.match(raw[11:16]) else ""
                key = self._reminder_key(uid, done_doc_id, proc, day_str)
                desired[key] = {
                    "procedure": proc,
                    "day": day,
                    "day_str": day_str,
                    "time": time_str,
                    "dentist": str(r.get("dentist") or "").strip() or self.BRACES_DEFAULT_DENTIST,
                }

            coll = self.db.collection(self.REMINDERS)
            existing = {
                s.id: (s.to_dict() or {})
                for s in coll.where(filter=FieldFilter("source_doc", "==", done_doc_id)).stream()
            }

            batch = self.db.batch()
            ops = 0
            for rid, d in existing.items():
                if rid in desired:
                    if d.get("status") in self.REMINDER_ACTIVE and (
                        d.get("DentistName") != desired[rid]["dentist"]
                        or d.get("appointment_time", "") != desired[rid]["time"]
                    ):
                        batch.update(coll.document(rid), {
                            "DentistName": desired[rid]["dentist"],
                            "appointment_time": desired[rid]["time"],
                            "updated_at": datetime.now(UTC).isoformat(),
                        })
                        ops += 1
                elif d.get("status") in ("awaiting", "contacted"):
                    batch.delete(coll.document(rid))
                    ops += 1

            name = None
            now_iso = datetime.now(UTC).isoformat()
            for rid, info in desired.items():
                if rid in existing:
                    continue
                if name is None:
                    patient_id = self._reminder_patient_id(uid, patient_id)
                    name = self._braces_patient_name(patient_id, uid)
                deadline = self._reminder_deadline(info["day"])
                data = {
                    "uid": uid,
                    "patient_id": str(patient_id or ""),
                    "patient_name": name,
                    "has_account": has_account,
                    "procedure": info["procedure"],
                    "appointment_date": info["day_str"],
                    "appointment_time": info["time"],
                    "DentistName": info["dentist"],
                    "status": "awaiting",
                    "source_doc": done_doc_id,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "deadline_at": deadline,
                    "admin_seen": True,
                }
                if not has_account:
                    # Only walk-in reminders are auto-booked by this module,
                    # so only they appear in the cron's range query.
                    data["auto_confirm_at"] = deadline
                batch.set(coll.document(rid), data)
                ops += 1

            if ops:
                batch.commit()
        except Exception as e:
            print("REMINDERS SYNC ERROR:", e)

    # --------------------------------------------------------------- the list
    def admin_reminders(self):
        """Every active reminder, anything unread, and the last 60 days."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            coll = self.db.collection(self.REMINDERS)
            found = {}
            cutoff = (datetime.now(UTC) - timedelta(days=self.REMINDER_HISTORY_DAYS)).isoformat()
            queries = (
                coll.where(filter=FieldFilter("status", "in", list(self.REMINDER_ACTIVE))),
                coll.where(filter=FieldFilter("admin_seen", "==", False)),
                coll.where(filter=FieldFilter("updated_at", ">=", cutoff)),
            )
            for q in queries:
                for snap in q.limit(500).stream():
                    found[snap.id] = snap.to_dict() or {}

            # Braces + login: status lives in Braces_Proposals (patient answers there).
            brace_uids = {
                d.get("uid") for d in found.values()
                if d.get("has_account") and d.get("procedure") == self.BRACES_PROCEDURE
            }
            proposals = self._reminders_fetch(
                [self._braces_proposal_ref(u) for u in brace_uids if u]
            )
            # Contact details come from the patient's account, exactly as My Patients
            # resolves them (account number, else their latest appointment).
            account_uids = {d.get("uid") for d in found.values() if d.get("uid")}
            accounts = self._reminders_fetch(
                [self.db.collection(self.Customer_Account).document(str(u)) for u in account_uids]
            )
            identity_cache = {}

            now = datetime.now(UTC)
            rows = []
            for rid, d in found.items():
                status = d.get("status", "")
                chosen = d.get("chosen_appointment_date", "")
                reason = d.get("reason", "")
                responded = d.get("responded_at", "")
                deadline = d.get("deadline_at", "")
                unseen = d.get("admin_seen") is False and status != "awaiting"
                managed = False

                prop = proposals.get(d.get("uid")) if d.get("procedure") == self.BRACES_PROCEDURE else None
                if d.get("has_account") and prop and prop.get("appointment_date") == d.get("appointment_date"):
                    managed = True
                    pst = prop.get("status", "")
                    status = {"auto_confirmed": "auto_booked"}.get(pst, pst) or status
                    chosen = prop.get("chosen_appointment_date", chosen)
                    reason = prop.get("reason", reason)
                    responded = prop.get("responded_at", responded)
                    deadline = prop.get("auto_confirm_at", deadline) if pst == "awaiting" else deadline
                    unseen = pst != "awaiting" and prop.get("admin_seen") is False
                elif d.get("has_account") and d.get("procedure") == self.BRACES_PROCEDURE:
                    managed = True      # patient answers it; admin only watches

                days_left = None
                if status in ("awaiting", "contacted") and deadline:
                    try:
                        secs = (datetime.fromisoformat(deadline) - now).total_seconds()
                        days_left = max(0, int(-(-secs // 86400)))
                    except ValueError:
                        days_left = None

                acct = accounts.get(d.get("uid")) or {}
                number = ""
                try:
                    number = str(self._resolve_account_identity(
                        d.get("uid"), acct, identity_cache)[0] or "").strip()
                except Exception as e:
                    print("REMINDERS CONTACT LOOKUP ERROR:", e)
                    number = str(acct.get("contact_number") or acct.get("ContactNumber") or "").strip()
                email = ""
                if d.get("has_account"):
                    email = str(acct.get("email", "") or "").strip()

                rows.append({
                    "id": rid,
                    "uid": d.get("uid", ""),
                    "patient_id": d.get("patient_id", ""),
                    "patient_name": d.get("patient_name") or "Patient",
                    "has_account": bool(d.get("has_account")),
                    "procedure": d.get("procedure", ""),
                    "appointment_date": d.get("appointment_date", ""),
                    "appointment_time": d.get("appointment_time", ""),
                    "dentist": d.get("DentistName", ""),
                    "status": status,
                    "chosen_appointment_date": chosen,
                    "reason": reason,
                    "responded_at": responded,
                    "days_left": days_left,
                    "unseen": bool(unseen),
                    "managed_by_patient": managed,
                    "contact_number": number,
                    "email": email,
                })
            return jsonify({"success": True, "rows": rows})
        except Exception as e:
            print("ADMIN REMINDERS ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_reminders_count(self):
        """Sidebar badge: walk-ins that need a call, items needing review, unread answers."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            coll = self.db.collection(self.REMINDERS)
            ids = set()
            for snap in coll.where(filter=FieldFilter("status", "==", "awaiting")).limit(500).stream():
                if not (snap.to_dict() or {}).get("has_account", True):
                    ids.add(snap.id)
            for snap in coll.where(filter=FieldFilter("status", "==", "needs_review")).limit(500).stream():
                ids.add(snap.id)
            for snap in coll.where(filter=FieldFilter("admin_seen", "==", False)).limit(500).stream():
                ids.add(snap.id)
            n = len(ids)
            q = self.db.collection(self.BRACES_PROPOSALS).where(
                filter=FieldFilter("admin_seen", "==", False)
            )
            for snap in q.limit(200).stream():
                if (snap.to_dict() or {}).get("status") != "awaiting":
                    n += 1
            return jsonify({"success": True, "count": n})
        except Exception as e:
            print("ADMIN REMINDERS COUNT ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong."}), 500

    # ---------------------------------------------------------------- actions
    def _reminder_load_active(self, rid):
        """(ref, data, error_response). Only unanswered, admin-actionable reminders."""
        rid = bleach.clean(str(rid or "")).strip()
        if not rid:
            return None, None, (jsonify({"success": False, "message": "No reminder specified"}), 400)
        ref = self._reminder_ref(rid)
        snap = ref.get()
        if not snap.exists:
            return None, None, (jsonify({"success": False, "message": "Reminder not found"}), 404)
        d = snap.to_dict() or {}
        if d.get("status") not in self.REMINDER_ACTIVE:
            return None, None, (jsonify({"success": False, "message": "This reminder was already handled."}), 409)
        if d.get("has_account") and d.get("procedure") == self.BRACES_PROCEDURE:
            return None, None, (jsonify({
                "success": False,
                "message": "The patient answers this braces follow-up from their own account."
            }), 409)
        return ref, d, None

    def admin_reminders_seen(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        rid = bleach.clean(request.form.get("id", "")).strip()
        if not rid:
            return jsonify({"success": False, "message": "No reminder specified"}), 400
        try:
            coll = self.db.collection(self.REMINDERS)
            if rid == "all":
                q = coll.where(filter=FieldFilter("admin_seen", "==", False))
                for snap in q.limit(500).stream():
                    if (snap.to_dict() or {}).get("status") != "awaiting":
                        snap.reference.update({"admin_seen": True})
            else:
                ref = coll.document(rid)
                snap = ref.get()
                if snap.exists:
                    ref.update({"admin_seen": True})
            return jsonify({"success": True})
        except Exception as e:
            print("ADMIN REMINDERS SEEN ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_reminders_contacted(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            ref, d, err = self._reminder_load_active(request.form.get("id"))
            if err:
                return err
            now_iso = datetime.now(UTC).isoformat()
            ref.update({
                "status": "contacted",
                "contacted_at": now_iso,
                "contacted_by": session.get("admin_uid", ""),
                "updated_at": now_iso,
            })
            return jsonify({"success": True})
        except Exception as e:
            print("ADMIN REMINDERS CONTACTED ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_reminders_cancel(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            ref, d, err = self._reminder_load_active(request.form.get("id"))
            if err:
                return err
            ref.update({
                "status": "cancelled",
                "responded_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "auto_confirm_at": firestore.DELETE_FIELD,
            })
            return jsonify({"success": True})
        except Exception as e:
            print("ADMIN REMINDERS CANCEL ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_reminders_open_times(self):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        day_str = bleach.clean(request.args.get("date", "")).strip()
        dentist = bleach.clean(request.args.get("dentist", "")).strip()
        if len(day_str) != 10 or self._braces_parse_day(day_str) is None:
            return jsonify({"success": False, "message": "Invalid date"}), 400
        return jsonify({
            "success": True, "date": day_str,
            "times": self._braces_open_times(day_str, dentist or self.BRACES_DEFAULT_DENTIST),
        })

    def admin_reminders_contact_number(self):
        """Save a missing contact number where My Patients reads it (the account),
        and onto the linked Patients record too."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        uid = bleach.clean(request.form.get("uid", "")).strip()
        patient_id = bleach.clean(request.form.get("patient_id", "")).strip()
        number = self._clean_phone(request.form.get("number", ""))
        if not uid:
            return jsonify({"success": False, "message": "No patient specified"}), 400
        if not number:
            return jsonify({"success": False, "message": "Enter a valid mobile number."}), 400
        try:
            acct_ref = self.db.collection(self.Customer_Account).document(uid)
            if not acct_ref.get().exists:
                return jsonify({"success": False, "message": "Patient not found"}), 404
            acct_ref.set({"contact_number": number}, merge=True)
            try:
                pid = self._reminder_patient_id(uid, patient_id)
                if pid:
                    pref = self.db.collection(self.Doc_Patients).document(pid)
                    if pref.get().exists:
                        pref.update({"contact_number": number})
            except Exception as e:
                print("REMINDER CONTACT NUMBER PATIENT UPDATE ERROR:", e)
            return jsonify({"success": True, "number": number})
        except Exception as e:
            print("ADMIN REMINDERS CONTACT NUMBER ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    # ---------------------------------------------------------------- booking
    def _reminder_commit_booking(self, rid, rem, chosen, dentist, auto):
        """
        Write an ACCEPTED appointment (Approve) from the patient's previous
        details and mark the reminder booked. Returns the booking dict, or
        None when there are not enough details on file to build one.
        """
        uid = str(rem.get("uid", ""))
        booking = self._braces_build_booking(uid, rem.get("patient_id"), chosen)
        if booking is None:
            return None
        booking["Service"] = rem.get("procedure", "")

        account_ref = self.db.collection(self.Customer_Account).document(uid)
        approve_ref = account_ref.collection("Approve").document()
        now_iso = datetime.now(UTC).isoformat()
        data = dict(booking)
        data.update({
            "status": "accept",
            "Patient_unq_id": approve_ref.id,
            "DentistName": dentist,
            "accepted_at": now_iso,
            "followup_reminder": True,
            "reminder_id": rid,
            "proposal_date": rem.get("appointment_date", ""),
        })
        if rem.get("procedure") == self.BRACES_PROCEDURE:
            data["braces_followup"] = True
        if auto:
            data["auto_confirmed"] = True
            if not rem.get("has_account"):
                data["unconfirmed"] = True      # nobody reached the patient yet
        else:
            data["confirmed_by"] = session.get("admin_uid", "")

        batch = self.db.batch()
        batch.set(approve_ref, data)
        batch.set(self._reminder_ref(rid), {
            "status": "auto_booked" if auto else "booked",
            "chosen_appointment_date": chosen,
            "responded_at": now_iso,
            "updated_at": now_iso,
            "approve_id": approve_ref.id,
            "admin_seen": not auto,
            "auto_confirm_at": firestore.DELETE_FIELD,
        }, merge=True)
        batch.commit()

        try:
            account_ref.update({"has_history": True, "last_approved_at": now_iso})
        except Exception as e:
            print("REMINDER BOOKING ACCOUNT UPDATE ERROR:", e)
        try:
            email = (data.get("email") or "").strip()
            if email:
                fullname = f"{data.get('FirstName', '')} {data.get('LastName', '')}".strip()
                threading.Thread(
                    target=self.send_appointment_email,
                    args=(email, fullname, "accept", data), daemon=True
                ).start()
        except Exception as e:
            print("REMINDER BOOKING EMAIL ERROR:", e)
        return data

    def admin_reminders_book(self):
        """Admin / dentist books the follow-up (after calling or texting the patient)."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            ref, d, err = self._reminder_load_active(request.form.get("id"))
            if err:
                return err
            day_str = bleach.clean(request.form.get("date", "")).strip()
            time_str = bleach.clean(request.form.get("time", "")).strip()
            day = self._braces_parse_day(day_str)
            if day is None or len(day_str) != 10 or day < self._braces_today():
                return jsonify({"success": False, "message": "Choose a date that is today or later."}), 400
            dentist = d.get("DentistName") or self.BRACES_DEFAULT_DENTIST
            if time_str not in self._braces_open_times(day_str, dentist):
                return jsonify({"success": False, "message": "That time is no longer open. Please pick another."}), 409
            data = self._reminder_commit_booking(ref.id, d, f"{day_str} {time_str}", dentist, auto=False)
            if data is None:
                return jsonify({
                    "success": False,
                    "message": "No saved details for this patient to book from. Use New Appointment instead."
                }), 409
            return jsonify({"success": True, "chosen": f"{day_str} {time_str}"})
        except Exception as e:
            print("ADMIN REMINDERS BOOK ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    # ------------------------------------------------------------- auto-book
    def _reminders_auto_book(self):
        """
        Called by the daily cron. Books every walk-in (no login) reminder whose
        10-day window ended with nobody acting, using the previous details.
        Returns {result: count}.
        """
        counts = {}
        now_iso = datetime.now(UTC).isoformat()
        query = self.db.collection(self.REMINDERS).where(
            filter=FieldFilter("auto_confirm_at", "<=", now_iso)
        )
        for snap in query.stream():
            d = snap.to_dict() or {}
            try:
                if d.get("status") not in ("awaiting", "contacted") or d.get("has_account"):
                    snap.reference.update({"auto_confirm_at": firestore.DELETE_FIELD})
                    result = "skipped"
                else:
                    result = self._reminder_auto_book_one(snap.id, d)
            except Exception as e:
                print("REMINDER AUTO BOOK ERROR:", snap.id, e)
                result = "failed"
            counts[result] = counts.get(result, 0) + 1
        return counts

    def _reminder_auto_book_one(self, rid, rem):
        ref = self._reminder_ref(rid)
        today = self._braces_today()
        day = self._braces_parse_day(rem.get("appointment_date"))
        now_iso = datetime.now(UTC).isoformat()
        if day is None or day < today:
            ref.update({
                "status": "expired", "responded_at": now_iso, "updated_at": now_iso,
                "admin_seen": False, "auto_confirm_at": firestore.DELETE_FIELD,
            })
            return "expired"

        dentist = rem.get("DentistName") or self.BRACES_DEFAULT_DENTIST
        preferred = rem.get("appointment_time", "")
        chosen = None
        day = self._braces_open_day(day)
        for offset in range(15):
            ds = (day + timedelta(days=offset)).strftime("%Y-%m-%d")
            times = self._braces_open_times(ds, dentist)
            if not times:
                continue
            pick = preferred if (offset == 0 and preferred in times) else times[0]
            chosen = f"{ds} {pick}"
            break
        if not chosen:
            return "no_slot"                # retried by the next daily run

        if self._reminder_commit_booking(rid, rem, chosen, dentist, auto=True) is None:
            ref.update({
                "status": "needs_review", "responded_at": now_iso, "updated_at": now_iso,
                "admin_seen": False, "auto_confirm_at": firestore.DELETE_FIELD,
            })
            return "no_details"
        return "confirmed"

    # ----------------------------------------------------------------- routes
    def _register_reminder_routes(self):
        r = self.app.route
        r("/admin/reminders")(self.admin_reminders)
        r("/admin/reminders/count")(self.admin_reminders_count)
        r("/admin/reminders/open_times")(self.admin_reminders_open_times)
        r("/admin/reminders/seen", methods=["POST"])(self.admin_reminders_seen)
        r("/admin/reminders/contacted", methods=["POST"])(self.admin_reminders_contacted)
        r("/admin/reminders/book", methods=["POST"])(self.admin_reminders_book)
        r("/admin/reminders/cancel", methods=["POST"])(self.admin_reminders_cancel)
        r("/admin/reminders/contact_number", methods=["POST"])(self.admin_reminders_contact_number)