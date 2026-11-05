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
    APPT_CHANGE_REQUESTS = "Appointment_Change_Requests"
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
                resched = bool(d.get("rescheduled_from"))
                if rid in desired:
                    # A rescheduled reminder keeps its own time: the record still
                    # holds the original visit's time.
                    if d.get("status") in self.REMINDER_ACTIVE and (
                        d.get("DentistName") != desired[rid]["dentist"]
                        or (not resched and d.get("appointment_time", "") != desired[rid]["time"])
                    ):
                        upd = {
                            "DentistName": desired[rid]["dentist"],
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                        if not resched:
                            upd["appointment_time"] = desired[rid]["time"]
                        batch.update(coll.document(rid), upd)
                        ops += 1
                elif d.get("status") in ("awaiting", "contacted"):
                    # Moved off an original date that has since passed: the record
                    # no longer lists it (it only lists future dates), so keep it.
                    if resched and str(d.get("rescheduled_from")) < today.strftime("%Y-%m-%d"):
                        continue
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

    # ------------------------------------------------------------ done visits
    def _reminders_complete(self, uid, new_done_doc_id, approve_ids, rows):
        """
        A treatment record was just saved: remove the reminders it completes, so
        Reminders only ever lists what is still to do. Never raises.

        - a booked reminder whose appointment was just used for this record
          (its approve_id is one of the appointments consumed by the save);
        - an unanswered reminder (needs call / awaiting / overdue) for a
          procedure this record covers: the patient came, so there is nothing
          left to remind them about (also covers visits days before or after
          the date that was planned).
        The reminders this very record creates (its own next appointment) stay.
        """
        try:
            uid = str(uid or "").strip()
            if not uid:
                return
            approve_ids = {str(a) for a in (approve_ids or []) if a}
            procs = {
                str((r or {}).get("procedure") or "").strip().lower()
                for r in (rows or []) if (r or {}).get("procedure")
            }
            batch = self.db.batch()
            ops = 0
            for snap in self.db.collection(self.REMINDERS).where(
                filter=FieldFilter("uid", "==", uid)
            ).stream():
                d = snap.to_dict() or {}
                if str(d.get("source_doc") or "") == str(new_done_doc_id or ""):
                    continue
                status = d.get("status")
                visit_used = (
                    status in ("booked", "auto_booked")
                    and str(d.get("approve_id") or "") in approve_ids
                )
                answered = (
                    status in self.REMINDER_ACTIVE
                    and str(d.get("procedure") or "").strip().lower() in procs
                )
                if visit_used or answered:
                    batch.delete(snap.reference)
                    ops += 1
            if ops:
                batch.commit()
        except Exception as e:
            print("REMINDERS COMPLETE ERROR:", e)

    def _reminders_prune_completed(self, found):
        """
        Safety net for reminders booked before this cleanup existed: a booked
        reminder whose appointment already has a saved treatment record is done.
        Deletes it and drops it from `found` (the dict the list is built from).
        """
        try:
            for rid, d in list(found.items()):
                if d.get("status") not in ("booked", "auto_booked"):
                    continue
                aid, uid = str(d.get("approve_id") or ""), str(d.get("uid") or "")
                if not aid or not uid:
                    continue
                hit = self.db.collection(self.Customer_Account).document(uid) \
                    .collection("Done_procedure") \
                    .where(filter=FieldFilter("Patient_unq_id", "==", aid)).limit(1).get()
                if hit:
                    self.db.collection(self.REMINDERS).document(rid).delete()
                    found.pop(rid, None)
        except Exception as e:
            print("REMINDERS PRUNE ERROR:", e)

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

            # Visits that were already treated are done: they leave the list.
            self._reminders_prune_completed(found)

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
                    "rescheduled_from": d.get("rescheduled_from", ""),
                    "reschedule_count": int(d.get("reschedule_count") or 0),
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
            # Patients asking to change / cancel an appointment they booked.
            try:
                oq = self.db.collection(self.APPT_CHANGE_REQUESTS).where(
                    filter=FieldFilter("status", "==", "open")
                )
                n += sum(1 for _ in oq.limit(200).stream())
            except Exception as e:
                print("CHANGE REQUEST COUNT ERROR:", e)
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

    # ------------------------------------------------------------- reschedule
    def admin_reminders_reschedule(self):
        """
        Move a follow-up to the date the patient asked for (patients often come
        days before or after the original date). Only the due date moves; the
        reminder stays on the list and the clinic can still Book a slot later.
        The 10-day window is restarted from the new date.
        """
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            ref, d, err = self._reminder_load_active(request.form.get("id"))
            if err:
                return err
            day_str = bleach.clean(request.form.get("date", "")).strip()
            day = self._braces_parse_day(day_str)
            if day is None or len(day_str) != 10 or day < self._braces_today():
                return jsonify({"success": False, "message": "Choose a date that is today or later."}), 400
            old_date = str(d.get("appointment_date", ""))
            if day_str == old_date:
                return jsonify({"success": False, "message": "That is already the due date."}), 400

            now_iso = datetime.now(UTC).isoformat()
            deadline = self._reminder_deadline(day)
            upd = {
                "appointment_date": day_str,
                "status": "awaiting" if d.get("status") == "needs_review" else d.get("status"),
                "deadline_at": deadline,
                "rescheduled_at": now_iso,
                "rescheduled_by": session.get("admin_uid", ""),
                "reschedule_count": int(d.get("reschedule_count") or 0) + 1,
                "updated_at": now_iso,
                "admin_seen": True,
            }
            if not d.get("rescheduled_from"):
                upd["rescheduled_from"] = old_date      # keep the ORIGINAL date
            if not d.get("has_account"):
                upd["auto_confirm_at"] = deadline       # walk-ins: auto-book clock restarts
            ref.update(upd)

            # Keep the date the patient sees in their own schedule in step.
            try:
                uid = str(d.get("uid", ""))
                if uid:
                    nv_ref = self.db.collection(self.Customer_Account).document(uid) \
                        .collection("Approve").document("next_visit")
                    nv = nv_ref.get()
                    if nv.exists:
                        nvd = nv.to_dict() or {}
                        raw = str(nvd.get("appointment_date", ""))
                        if raw[:10] == old_date[:10] and nvd.get("Service") == d.get("procedure"):
                            nv_ref.update({"appointment_date": day_str + raw[10:]})
            except Exception as e:
                print("REMINDER RESCHEDULE NEXT VISIT ERROR:", e)

            return jsonify({"success": True, "date": day_str})
        except Exception as e:
            print("ADMIN REMINDERS RESCHEDULE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    # ------------------------------------------------- patient change requests
    def patient_request_appointment_change(self):
        """
        A patient asks the clinic to change or cancel an appointment THEY booked.
        Nothing is changed here: the request is stored on the appointment and in
        Appointment_Change_Requests, the dentist sees it in Reminders and makes
        the final change. The uid always comes from the session.
        """
        uid = session.get("uid")
        if not uid:
            return jsonify({"success": False, "message": "Not logged in"}), 401

        appointment_id = bleach.clean(request.form.get("appointment_id", "")).strip()
        source = request.form.get("source", "").strip()
        kind = request.form.get("kind", "").strip()
        if not appointment_id or "/" in appointment_id or source not in ("pending", "accepted") \
                or kind not in ("reschedule", "cancel"):
            return jsonify({"success": False, "message": "Invalid request."}), 400

        note = bleach.clean(request.form.get("note", "")).strip()[:300]
        preferred = ""
        if kind == "reschedule":
            raw = bleach.clean(request.form.get("preferred_date", "")).strip()
            if raw:
                day = self._braces_parse_day(raw)
                if day is None or len(raw) != 10 or day < self._braces_today():
                    return jsonify({"success": False, "message": "Choose a date that is today or later."}), 400
                preferred = raw

        # Optional new time of day (patients often only need a different time).
        preferred_time = ""
        if kind == "reschedule":
            rt = bleach.clean(request.form.get("preferred_time", "")).strip()
            if rt:
                if not self._TIME_RE.match(rt) or int(rt[:2]) > 23 or int(rt[3:]) > 59:
                    return jsonify({"success": False, "message": "Choose a valid time."}), 400
                preferred_time = rt
            if not preferred and not preferred_time and not note:
                return jsonify({"success": False,
                                "message": "Choose a new date or time, or add a note for the clinic."}), 400

        try:
            account_ref = self.db.collection(self.Customer_Account).document(str(uid))
            coll = account_ref.collection(self.Appointment_cliets if source == "pending" else "Approve")
            ref = coll.document(appointment_id)
            snap = ref.get()
            if not snap.exists:
                return jsonify({"success": False, "message": "Appointment not found."}), 404
            data = snap.to_dict() or {}
            if source == "accepted" and (appointment_id == "next_visit" or data.get("booked_by") != "patient"):
                return jsonify({"success": False,
                                "message": "You can only request changes to appointments you booked yourself."}), 403
            if (data.get("change_request") or {}).get("status") == "open":
                return jsonify({"success": False, "message": "You already sent a request for this appointment."}), 409

            now_iso = datetime.now(UTC).isoformat()
            cr = {"kind": kind, "preferred_date": preferred, "preferred_time": preferred_time, "note": note,
                  "status": "open", "requested_at": now_iso}
            name = f"{data.get('FirstName', '')} {data.get('LastName', '')}".strip()
            batch = self.db.batch()
            batch.update(ref, {"change_request": cr})
            batch.set(self.db.collection(self.APPT_CHANGE_REQUESTS).document(f"{uid}_{appointment_id}"), {
                "uid": str(uid),
                "appointment_id": appointment_id,
                "source": source,
                "patient_name": name,
                "appointment_date": data.get("appointment_date", ""),
                "service": data.get("Service", ""),
                "dentist": data.get("DentistName", ""),
                "kind": kind,
                "preferred_date": preferred,
                "preferred_time": preferred_time,
                "note": note,
                "status": "open",
                "requested_at": now_iso,
                "admin_seen": False,
            })
            batch.commit()
            return jsonify({"success": True,
                            "message": "Your request was sent. The clinic will contact you to confirm."})
        except Exception as e:
            print("PATIENT CHANGE REQUEST ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong. Please try again."}), 500

    def admin_change_requests(self):
        """Open patient change / cancel requests, oldest first."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            q = self.db.collection(self.APPT_CHANGE_REQUESTS).where(
                filter=FieldFilter("status", "==", "open")
            )
            rows = []
            for snap in q.limit(200).stream():
                d = snap.to_dict() or {}
                rows.append({
                    "id": snap.id,
                    "uid": d.get("uid", ""),
                    "appointment_id": d.get("appointment_id", ""),
                    "source": d.get("source", ""),
                    "patient_name": d.get("patient_name", ""),
                    "appointment_date": d.get("appointment_date", ""),
                    "service": d.get("service", ""),
                    "dentist": d.get("dentist", ""),
                    "kind": d.get("kind", ""),
                    "preferred_date": d.get("preferred_date", ""),
                    "preferred_time": d.get("preferred_time", ""),
                    "note": d.get("note", ""),
                    "requested_at": d.get("requested_at", ""),
                })
            rows.sort(key=lambda r: r["requested_at"])
            return jsonify({"success": True, "rows": rows})
        except Exception as e:
            print("ADMIN CHANGE REQUESTS ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong."}), 500

    def _close_change_request(self, rid, d, applied=False):
        """Close a request and clear the "change requested" flag on the patient's appointment."""
        self.db.collection(self.APPT_CHANGE_REQUESTS).document(rid).update({
            "status": "handled",
            "applied": bool(applied),
            "handled_at": datetime.now(UTC).isoformat(),
            "handled_by": session.get("admin_uid", ""),
            "admin_seen": True,
        })
        try:
            acct = self.db.collection(self.Customer_Account).document(str(d.get("uid", "")))
            for cname in (self.Appointment_cliets, "Approve"):
                aref = acct.collection(cname).document(str(d.get("appointment_id", "")))
                s = aref.get()
                if s.exists and (s.to_dict() or {}).get("change_request"):
                    aref.update({"change_request": firestore.DELETE_FIELD})
        except Exception as e:
            print("CHANGE REQUEST CLEAR FLAG ERROR:", e)

    def admin_change_requests_handle(self):
        """Dismiss: close the request without changing the appointment."""
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            rid = bleach.clean(request.form.get("id", "")).strip()
            if not rid or "/" in rid:
                return jsonify({"success": False, "message": "No request specified."}), 400
            snap = self.db.collection(self.APPT_CHANGE_REQUESTS).document(rid).get()
            if not snap.exists:
                return jsonify({"success": False, "message": "Request not found."}), 404
            self._close_change_request(rid, snap.to_dict() or {})
            return jsonify({"success": True})
        except Exception as e:
            print("ADMIN CHANGE REQUEST HANDLE ERROR:", e)
            return jsonify({"success": False, "message": "Something went wrong."}), 500

    def admin_change_requests_apply(self):
        """
        Apply a patient's date/time request to their appointment, using the same
        rules, patient notification and email as the Appointments reschedule
        (blocked days, taken slots, past dates). On success the request is closed.
        The appointment stays pending (or accepted) exactly as it was.
        """
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        try:
            rid = bleach.clean(request.form.get("id", "")).strip()
            if not rid or "/" in rid:
                return jsonify({"success": False, "message": "No request specified."}), 400
            snap = self.db.collection(self.APPT_CHANGE_REQUESTS).document(rid).get()
            if not snap.exists:
                return jsonify({"success": False, "message": "Request not found."}), 404
            d = snap.to_dict() or {}
            if d.get("status") != "open":
                return jsonify({"success": False, "message": "This request was already handled."}), 409
            if d.get("kind") != "reschedule":
                return jsonify({"success": False,
                                "message": "Cancellations are declined in Appointments, not applied here."}), 400

            res = self._reschedule_appointment_core(
                uid=str(d.get("uid", "")),
                appointment_id=str(d.get("appointment_id", "")),
                new_date=bleach.clean(request.form.get("date", "")).strip(),
                new_time=bleach.clean(request.form.get("time", "")).strip(),
                dentist_name="",
                source=d.get("source") if d.get("source") in ("pending", "accepted") else "pending",
            )
            payload, status = res if isinstance(res, tuple) else (res, 200)
            if status != 200 or not payload.get("success"):
                return jsonify(payload), status

            self._close_change_request(rid, d, applied=True)
            payload.update({
                "uid": d.get("uid", ""),
                "appointment_id": d.get("appointment_id", ""),
                "source": d.get("source", "pending"),
            })
            return jsonify(payload)
        except Exception as e:
            print("ADMIN CHANGE REQUEST APPLY ERROR:", e)
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
        r("/admin/reminders/reschedule", methods=["POST"])(self.admin_reminders_reschedule)
        r("/patient/appointment_change_request", methods=["POST"])(self.patient_request_appointment_change)
        r("/admin/change_requests")(self.admin_change_requests)
        r("/admin/change_requests/handle", methods=["POST"])(self.admin_change_requests_handle)
        r("/admin/change_requests/apply", methods=["POST"])(self.admin_change_requests_apply)