let currentCheckInfoPatientId = "";
            let currentCheckInfoPatientName = "";


            const CI_PROCEDURE_OPTIONS = [
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
                "Other"
            ];

            function escAttr(s) {
                const d = document.createElement('div');
                d.appendChild(document.createTextNode(s == null ? "" : String(s)));
                return d.innerHTML.replace(/"/g, "&quot;");
            }

            function buildProcedureSelect(selectedValue) {
                const current = (selectedValue || "").trim();
                const isKnown = CI_PROCEDURE_OPTIONS.some(
                    opt => opt.toLowerCase() === current.toLowerCase()
                );

                let optionsHtml = "";

                if (current && !isKnown) {
                    optionsHtml += `<option value="${escAttr(current)}" selected>${current}</option>`;
                }

                CI_PROCEDURE_OPTIONS.forEach(opt => {
                    const isSelected = opt.toLowerCase() === current.toLowerCase();
                    optionsHtml += `<option value="${escAttr(opt)}" ${isSelected ? "selected" : ""}>${opt}</option>`;
                });

                return `<select class="ci-procedure">${optionsHtml}</select>`;
            }

            // ---- Plans: follow-up rows, payments and payment history ------------
            // A plan row carries the price, paid total and balance. A follow-up
            // row (item.plan_ref set) is a later visit with no charge of its own.
            function ciMoney(n) {
                return "₱" + Number(n || 0).toLocaleString("en-PH", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
            }
            function ciIsFollowUp(item) { return !!(item && item.plan_ref); }
            function ciPlanRef(item) {
                return item.plan_id || (item.done_doc_id + ":" + item.proc_index);
            }

            (function ciInjectStyles() {
                if (document.getElementById("ciPlanStyles")) return;
                const st = document.createElement("style");
                st.id = "ciPlanStyles";
                st.textContent = [
                    ".ci-muted{color:#6b7c93;font-size:12px;}",
                    ".ci-badge--follow{background:#e8f0fe;color:#0d47a1;}",
                    ".ci-sub > td{background:#f6f9fd;padding:12px 18px !important;text-align:left !important;}",
                    ".ci-pay-panel{display:flex;flex-wrap:wrap;gap:14px;padding:12px 16px;width:100%;box-sizing:border-box;background:#f8fafc;border:1px solid #dbe4ef;border-radius:10px;align-items:center;}",
                    ".ci-pay-fields{display:flex;flex-wrap:wrap;gap:12px;align-items:center;flex:1 1 auto;}",
                    ".ci-pay-field{display:flex;flex-direction:column;gap:6px;font-size:12px;font-weight:700;color:#546e7a;white-space:nowrap;}",
                    "#checkInfoModal .ci-pay-field input{height:36px;padding:0 11px;border:1px solid #cfd8e3;border-radius:8px;font:inherit;color:#1f2937;background:#fff;box-sizing:border-box;width:160px;min-width:0;display:inline-block;transition:border-color .15s ease,box-shadow .15s ease;}",
                    "#checkInfoModal .ci-pay-field select{height:36px;padding:0 28px 0 11px;border:1px solid #cfd8e3;border-radius:8px;font:inherit;color:#1f2937;background:#fff url('data:image/svg+xml;charset=UTF-8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2216%22 height=%2216%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%2364748b%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22><polyline points=%226 9 12 15 18 9%22></polyline></svg>') no-repeat right 11px center;background-size:16px;-webkit-appearance:none;appearance:none;box-sizing:border-box;width:160px;min-width:0;display:inline-block;cursor:pointer;transition:border-color .15s ease,box-shadow .15s ease;}",
                    "#checkInfoModal .ci-pay-field input:focus,#checkInfoModal .ci-pay-field select:focus{border-color:#0d47a1;box-shadow:0 0 0 3px rgba(13,71,161,.15);outline:none;}",
                    "@keyframes ci-panel-in{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}",
                    ".ci-sub{animation:ci-panel-in 0.25s ease both;}",
                    "@keyframes ci-pay-spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}",
                    ".ci-pay-spinner{display:none;width:14px;height:14px;margin-right:6px;vertical-align:-1px;border:2px solid #cbd5e1;border-top-color:#0d47a1;border-radius:50%;}",
                    ".ci-pay-busy .ci-pay-spinner{display:inline-block;animation:ci-pay-spin 0.8s linear infinite;}",
                    ".ci-pay-busy .ci-pay-label{opacity:0.55;}",
                    ".ci-pay-busy .btn-action{opacity:0.55;cursor:not-allowed;}",
                    "#checkInfoModal .ci-pay-field .adm-select{position:relative;width:160px;margin:0;}",
                    "#checkInfoModal .ci-pay-field .adm-select>select{width:100%;min-width:0;}",
                    ".ci-pay-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center;white-space:nowrap;}",
                    ".ci-hist-panel{display:flex;flex-direction:column;gap:8px;padding:12px 16px;background:#f8fafc;border:1px solid #dbe4ef;border-radius:10px;}",
                    ".ci-hist-title{font-size:13px;font-weight:700;color:#1f2937;}",
                    ".ci-hist{width:100%;max-width:520px;border-collapse:separate;border-spacing:0;font-size:13px;border:1px solid #e3eaf3;border-radius:8px;overflow:hidden;}",
                    ".ci-hist th{padding:8px 10px;text-align:left;background:#eef3fa;color:#475569;font-weight:700;border-bottom:1px solid #e3eaf3;}",
                    ".ci-hist td{padding:8px 10px;border-bottom:1px solid #f1f5f9;color:#1f2937;}",
                    ".ci-hist tbody tr:last-child td{border-bottom:none;}"
                ].join("");
                document.head.appendChild(st);
            })();

            let ciPayBusy = false;

            function ciClosePanels(index) {
                ["ci-pay-", "ci-hist-"].forEach(function (p) {
                    const el = document.getElementById(p + index);
                    if (el) el.remove();
                });
            }

            function ciInsertSubRow(index, id, html) {
                const row = document.getElementById("ci-row-" + index);
                if (!row) return null;
                const sub = document.createElement("tr");
                sub.id = id;
                sub.className = "ci-sub";
                sub.innerHTML = '<td colspan="13">' + html + "</td>";
                // Keep payment panel above the history panel.
                const hist = document.getElementById("ci-hist-" + index);
                if (id.indexOf("ci-pay-") === 0 && hist) hist.before(sub); else row.after(sub);
                return sub;
            }

            function ciTogglePayPanel(index) {
                const existing = document.getElementById("ci-pay-" + index);
                if (existing) { existing.remove(); return; }
                const item = window.currentProcedures[index];
                if (!item || ciIsFollowUp(item)) return;
                const bal = parseFloat(item.balance) || 0;
                if (bal <= 0) { showToast("This procedure is already fully paid."); return; }

                const sub = ciInsertSubRow(index, "ci-pay-" + index,
                    '<div class="ci-pay-panel">' +
                    '<div class="ci-pay-fields">' +
                    '<label class="ci-pay-field"><span class="ci-pay-label">Amount received</span><input type="number" class="ci-pay-amount" min="0.01" max="' + bal + '" step="0.01" placeholder="' + bal + '"></label>' +
                    '<label class="ci-pay-field"><span class="ci-pay-label">Paid via</span><select class="ci-pay-method">' +
                    '<option value="Cash">Cash</option><option value="GCash">GCash</option>' +
                    '<option value="BPI">BPI</option><option value="BDO">BDO</option></select></label>' +
                    '</div>' +
                    '<div class="ci-pay-actions">' +
                    '<button type="button" class="btn-action ci-btn--edit" onclick="ciSubmitPayment(' + index + ', false)"><span class="ci-pay-label">Record payment</span><span class="ci-pay-spinner" aria-hidden="true"></span></button>' +
                    '<button type="button" class="btn-action accept ci-btn--save" onclick="ciSubmitPayment(' + index + ', true)"><span class="ci-pay-label">Mark as paid (' + ciMoney(bal) + ')</span><span class="ci-pay-spinner" aria-hidden="true"></span></button>' +
                    '<button type="button" class="btn-action ci-btn--cancel" onclick="ciClosePanels(' + index + ')">Cancel</button>' +
                    '</div>' +
                    '</div>');
                const amt = sub && sub.querySelector(".ci-pay-amount");
                if (amt) amt.focus();
                // Turn the native "Paid via" popup into the app's custom,
                // stylable option list (Cash / GCash / BPI / BDO) so the
                // options match the rest of the design instead of the OS look.
                if (typeof window.admEnhanceSelects === "function") {
                    window.admEnhanceSelects(sub, ".ci-table-scroll", false);
                }
            }

            async function ciSubmitPayment(index, markPaid) {
                if (ciPayBusy) return;
                const item = window.currentProcedures[index];
                const panel = document.getElementById("ci-pay-" + index);
                if (!item || !panel) return;

                const method = panel.querySelector(".ci-pay-method").value;
                const balance = parseFloat(item.balance) || 0;
                let amount = parseFloat(panel.querySelector(".ci-pay-amount").value);

                if (markPaid) {
                    if (!window.confirm("Mark this procedure as fully paid by recording " + ciMoney(balance) + " via " + method + "?")) return;
                } else {
                    if (!(amount > 0)) { showToast("Enter the amount received."); return; }
                    if (amount > balance + 0.005) { showToast("That is more than the remaining balance (" + ciMoney(balance) + ")."); return; }
                }

                const formData = new FormData();
                formData.append("patient_id", currentCheckInfoPatientId);
                formData.append("plan_ref", ciPlanRef(item));
                formData.append("method", method);
                if (!markPaid) formData.append("amount", String(amount));

                ciPayBusy = true;
                panel.classList.add("ci-pay-busy");
                panel.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
                try {
                    const response = await fetch(markPaid ? "/admin/mark_plan_paid" : "/admin/record_payment",
                        { method: "POST", body: formData });
                    const result = await response.json();
                    if (result.success) {
                        showToast(result.message || "Payment recorded.", 'success');
                        // Re-fetch so every row, the payment history and the
                        // summary card come from the server's numbers.
                        await openCheckInfoModal(currentCheckInfoPatientId);
                    } else {
                        showToast(result.message || "Could not record the payment.");
                        panel.classList.remove("ci-pay-busy");
                        panel.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
                    }
                } catch (error) {
                    console.error("Record payment error:", error);
                    showToast("Could not record the payment. Please try again.");
                    panel.classList.remove("ci-pay-busy");
                    panel.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
                } finally {
                    ciPayBusy = false;
                }
            }

            function ciToggleHistory(index) {
                const existing = document.getElementById("ci-hist-" + index);
                if (existing) { existing.remove(); return; }
                const item = window.currentProcedures[index];
                const pays = (item && Array.isArray(item.payments)) ? item.payments : [];
                if (!pays.length) { showToast("No payments recorded yet."); return; }

                let html = '<div class="ci-hist-panel"><span class="ci-hist-title">Payment history</span>' +
                    '<table class="ci-hist"><thead><tr><th>Date</th><th>Amount</th><th>Paid via</th></tr></thead><tbody>';
                pays.forEach(function (p) {
                    html += "<tr><td>" + escAttr(p.date || "-") + "</td><td>" + ciMoney(p.amount) +
                        "</td><td>" + escAttr(p.method || "-") + "</td></tr>";
                });
                html += "</tbody></table></div>";
                ciInsertSubRow(index, "ci-hist-" + index, html);
            }

            function statusBadge(status) {
                const isPaid = (status || "").trim().toLowerCase() === "paid";
                return `<span class="ci-badge ${isPaid ? "ci-badge--paid" : "ci-badge--unpaid"}">${isPaid ? "Paid" : "Not Paid"}</span>`;
            }

            // Header summary values: set the text, or a
            // dash when empty. Built with textContent: the
            // values come straight from Firestore and must
            // never be parsed as markup.
            function setCiApptText(id, value) {
                const el = document.getElementById(id);
                if (!el) return;
                const text = (value == null ? "" : String(value)).trim();
                el.textContent = text || "-";
            }

            // The appointment summary and its divider
            // show and hide together.
            function setCiApptVisible(visible) {
                const block = document.getElementById("ciAppointment");
                const divider = document.getElementById("ciApptDivider");
                if (block) block.hidden = !visible;
                if (divider) divider.hidden = !visible;
            }

            // Medical history question labels, keyed by the
            // field name the appointment modal submits. Kept
            // here, next to the renderer, so the labels always
            // match the form the answers came from.
            const CI_MEDICAL_QUESTIONS = [
                ["q1", "Are you in good health?"],
                ["q2", "Under medical treatment now?"],
                ["q2_spec", "If so, what condition?"],
                ["q3", "Serious illness / surgical operation?"],
                ["q3_spec", "What illness/operation?"],
                ["q4", "Ever been hospitalized?"],
                ["q4_spec", "When and why?"],
                ["q5", "Taking any medication?"],
                ["q5_spec", "Please specify"],
                ["q6", "Use tobacco products?"],
                ["q7", "Any allergy?"],
                ["q7_spec", "Please specify"],
                ["q9", "Any medical condition/s?"],
                ["q9_spec", "Please specify"],
                ["w_preg", "Pregnant?"],
                ["w_nurse", "Nursing?"],
                ["w_pill", "Birth control pills?"]
            ];

            // Medical history answers from the latest
            // appointment. Built with DOM nodes, not
            // innerHTML: the answers come straight from
            // Firestore and must never be parsed as markup.
            function renderCiMedicalHistory(history) {
                const section = document.getElementById("ciApptMedical");
                const list = document.getElementById("ciApptMedicalList");
                if (!section || !list) return;

                list.textContent = "";

                const entries = [];

                CI_MEDICAL_QUESTIONS.forEach(function (pair) {
                    const answer = String(
                        (history || {})[pair[0]] || ""
                    ).trim();
                    if (answer) {
                        entries.push([pair[1], answer]);
                    }
                });

                if (!entries.length) {
                    // Explicit empty state: keeps the
                    // panel's shape consistent across
                    // patients.
                    const item = document.createElement("div");
                    item.className = "ci-appt-med-item ci-appt-med-empty";

                    const note = document.createElement("span");
                    note.className = "ci-appt-med-q";
                    note.textContent = "No medical history recorded.";

                    item.appendChild(note);
                    list.appendChild(item);
                } else {
                    entries.forEach(function (entry) {
                        const item = document.createElement("div");
                        item.className = "ci-appt-med-item";

                        const question = document.createElement("span");
                        question.className = "ci-appt-med-q";
                        question.textContent = entry[0];

                        const answer = document.createElement("span");
                        answer.className = "ci-appt-med-a";
                        answer.textContent = entry[1];

                        item.appendChild(question);
                        item.appendChild(answer);
                        list.appendChild(item);
                    });
                }

                section.hidden = false;
            }

            // Patient details (address, nationality, religion,
            // occupation) from the same latest-appointment
            // payload. The block is cloned from the medical
            // history section at runtime so it inherits its look
            // without needing new markup. DOM nodes only: values
            // come straight from Firestore.
            const CI_DETAIL_FIELDS = [
                ["address", "Address"],
                ["nationality", "Nationality"],
                ["religion", "Religion"],
                ["occupation", "Occupation"]
            ];

            function renderCiPatientDetails(details) {
                const medical = document.getElementById("ciApptMedical");
                if (!medical || !medical.parentNode) return;

                let section = document.getElementById("ciApptDetails");

                if (!section) {
                    section = medical.cloneNode(true);
                    section.id = "ciApptDetails";

                    const clonedList = section.querySelector("#ciApptMedicalList");
                    if (clonedList) clonedList.id = "ciApptDetailsList";

                    // Retitle the cloned heading and icon.
                    const walker = document.createTreeWalker(
                        section, NodeFilter.SHOW_TEXT);
                    let node;
                    while ((node = walker.nextNode())) {
                        if (/medical\s*history/i.test(node.nodeValue)) {
                            node.nodeValue = node.nodeValue.replace(
                                /medical\s*history/i, "Patient Details");
                        }
                    }
                    const icon = section.querySelector(".material-symbols-rounded");
                    if (icon) icon.textContent = "person";

                    medical.parentNode.insertBefore(section, medical);
                }

                const list = section.querySelector("#ciApptDetailsList");
                if (!list) return;
                list.textContent = "";

                let count = 0;
                CI_DETAIL_FIELDS.forEach(function (pair) {
                    const value = String(
                        (details || {})[pair[0]] || ""
                    ).trim();
                    if (!value) return;

                    const item = document.createElement("div");
                    item.className = "ci-appt-med-item";

                    const label = document.createElement("span");
                    label.className = "ci-appt-med-q";
                    label.textContent = pair[1];

                    const val = document.createElement("span");
                    val.className = "ci-appt-med-a";
                    val.textContent = value;

                    item.appendChild(label);
                    item.appendChild(val);
                    list.appendChild(item);
                    count++;
                });

                // Optional: nothing recorded means no block at all.
                section.hidden = count === 0;
            }

            // At-a-glance figures for the patient, computed
            // from the treatment records already loaded.
            // null (nothing loaded yet) hides the card; an
            // empty list still shows it with dashes.
            function renderCiStats(procedures) {
                const stats = document.getElementById("ciStats");
                if (!stats) return;

                if (procedures == null) {
                    stats.hidden = true;
                    return;
                }

                const list = Array.isArray(procedures) ? procedures : [];

                // Treatment record count.
                setCiApptText("ciStatVisits", String(list.length));

                // Most recent visit date and total
                // outstanding balance. Visit dates are
                // stored as "YYYY-MM-DD", so a plain
                // string comparison orders them.
                let lastVisit = "";
                let balance = 0;

                list.forEach(function (item) {
                    const date = String((item || {}).date || "").trim();
                    if (date > lastVisit) lastVisit = date;
                    balance += parseFloat((item || {}).balance) || 0;
                });

                setCiApptText("ciStatLastVisit",
                    (typeof formatApptDateTime === "function")
                        ? formatApptDateTime(lastVisit)
                        : lastVisit);
                setCiApptText("ciStatBalance",
                    (typeof peso === "function")
                        ? peso(balance)
                        : "₱" + balance.toFixed(2));

                stats.hidden = false;
            }

            function updateCiAppointment(appt) {
                const block = document.getElementById("ciAppointment");
                if (!block) return;

                if (!appt) {
                    setCiApptVisible(false);
                    return;
                }

                setCiApptText("ciApptService", appt.service);
                setCiApptText("ciApptDate",
                    (typeof formatApptDateTime === "function")
                        ? formatApptDateTime(appt.appointment_date)
                        : appt.appointment_date);
                setCiApptText("ciApptDentist",
                    (typeof formatDentistName === "function")
                        ? formatDentistName(appt.dentist_name)
                        : appt.dentist_name);

                renderCiPatientDetails(appt.patient_details);
                renderCiMedicalHistory(appt.medical_history);

                setCiApptVisible(true);
            }

            async function openCheckInfoModal(patientId, patientName) {
                const tbody = document.getElementById("checkInfoBody");
                const modal = document.getElementById("checkInfoModal");
                if (!tbody || !modal) return;

                // Remembered so a re-fetch (e.g. after a delete) keeps the heading.
                if (patientName !== undefined) {
                    currentCheckInfoPatientName = String(patientName || "").trim();
                }

                patientId = String(patientId).replace("Patient ID:", "").trim();
                currentCheckInfoPatientId = patientId;

                const subtitle = document.getElementById("ciSubtitle");
                if (subtitle) {
                    const bits = [];
                    if (currentCheckInfoPatientName) bits.push(currentCheckInfoPatientName);
                    if (patientId) bits.push("Patient ID: " + patientId);
                    subtitle.textContent = bits.join("   ·   ");
                }

                // Header extras: hidden until the
                // treatment-info response says otherwise,
                // so a previous patient's facts never
                // linger here.
                setCiApptVisible(false);
                renderCiStats(null);

                if (!patientId) {
                    modal.style.display = "flex";
                    ciDestroyRowWidgets();
                    tbody.innerHTML = `<tr><td colspan="14" style="text-align:center;">This patient has no booking history yet.</td></tr>`;
                    return;
                }

                ciDestroyRowWidgets();
                tbody.innerHTML = `<tr><td colspan="14" style="text-align:center;">Loading...</td></tr>`;
                modal.style.display = "flex";

                try {
                    const response = await fetch("/get_treatment_info/" + encodeURIComponent(patientId));
                    const result = await response.json();

                    if (result.success && Array.isArray(result.procedures) && result.procedures.length > 0) {
                        window.currentProcedures = result.procedures;
                        renderCheckInfoTable();
                    } else {
                        window.currentProcedures = [];
                        tbody.innerHTML = `<tr><td colspan="14" style="text-align:center;">No treatment history found.</td></tr>`;
                    }

                    // Header: latest appointment facts
                    // and the patient summary figures.
                    updateCiAppointment(result.latest_appointment);
                    renderCiStats(result.success ? result.procedures : null);
                } catch (error) {
                    console.error("Error loading treatment info:", error);
                    tbody.innerHTML = `<tr><td colspan="14" style="text-align:center;color:#ef4444;">Failed to load treatment data.</td></tr>`;
                }
            }

            // Treatment rows are rebuilt constantly (edit, cancel, save, delete), so
            // both widget libraries are torn down before the markup is replaced.
            function ciDestroyRowWidgets() {
                const tbody = document.getElementById("checkInfoBody");
                if (!tbody) return;

                if (typeof window.admDestroySelects === "function") {
                    window.admDestroySelects(tbody);
                }

                tbody.querySelectorAll("input[type='date']").forEach(function (input) {
                    if (input._flatpickr && typeof input._flatpickr.destroy === "function") {
                        input._flatpickr.destroy();
                    }
                });
            }

            // Swap the native <select> popups and <input type="date"> pickers for the
            // same .adm-select listbox and flatpickr calendar the rest of the admin uses.
            // The original elements keep their classes and Y-m-d values, so
            // saveTreatmentEdit() reads them exactly as before.
            function ciEnhanceRow(row) {
                if (!row) return;

                if (typeof window.admEnhanceSelects === "function") {
                    // The Treatment Information body scrolls, so its panels always open
                    // downwards rather than flipping over the column headers.
                    window.admEnhanceSelects(row, ".ci-table-scroll", false);
                }

                if (typeof flatpickr !== "function") return;

                row.querySelectorAll("input[type='date']").forEach(function (input) {
                    if (input._flatpickr) return;
                    flatpickr(input, {
                        disableMobile: true,
                        dateFormat: "Y-m-d",
                        altInput: true,
                        altFormat: "F j, Y",
                        altInputClass: "adm-date-alt",
                        className: "adm-datepicker",
                        allowInput: true
                    });
                });
            }

            function renderCheckInfoTable() {
                const tbody = document.getElementById("checkInfoBody");
                ciDestroyRowWidgets();
                tbody.innerHTML = "";

                window.currentProcedures.forEach((item, index) => {
                    const tr = document.createElement("tr");
                    tr.id = "ci-row-" + index;
                    tr.dataset.doneDocId = item.done_doc_id || "";
                    tr.dataset.procIndex = item.proc_index;

                    const followUp = ciIsFollowUp(item);
                    const hasPayments = Array.isArray(item.payments) && item.payments.length > 0;
                    const valueCell = followUp ? '<span class="ci-muted">Follow-up · no charge</span>' : ciMoney(item.value);
                    const paidCell = followUp
                        ? (parseFloat(item.paid_on_plan) > 0 ? ciMoney(item.paid_on_plan) + ' <span class="ci-muted">to plan</span>' : "-")
                        : ciMoney(item.paid);
                    const balanceCell = followUp ? "-" : ciMoney(item.balance);
                    const statusCell = followUp ? '<span class="ci-badge ci-badge--follow">Follow-up</span>' : statusBadge(item.status);
                    const canPay = !followUp && (parseFloat(item.balance) || 0) > 0;
                    const payBtn = canPay
                        ? `<button type="button" class="btn-action accept ci-btn--save ci-ico" title="Record payment" aria-label="Record payment" onclick="ciTogglePayPanel(${index})"><span class="material-symbols-rounded" aria-hidden="true">payments</span></button>`
                        : "";
                    const histBtn = hasPayments
                        ? `<button type="button" class="btn-action ci-btn--view ci-ico" title="Payment history" aria-label="Payment history" onclick="ciToggleHistory(${index})"><span class="material-symbols-rounded" aria-hidden="true">receipt_long</span></button>`
                        : "";

                    tr.innerHTML = `
            <td data-label="Assigned Dentist">${formatDentistName(item.dentist) || "-"}</td>
            <td data-label="Medicine">${item.medicine || "-"}</td>
            <td data-label="Visit Date">${item.date || "-"}</td>
            <td data-label="Tooth#">${escAttr(item.tooth) || "-"}</td>
            <td data-label="Procedure">${item.procedure || "-"}</td>
            <td data-label="Notes">${item.notes || "-"}</td>
            <td data-label="Value">${valueCell}</td>
            <td data-label="Fee Paid">${paidCell}</td>
            <td data-label="Balance">${balanceCell}</td>
            <td data-label="Status">${statusCell}</td>
            <td data-label="Next Appointment">${item.next_appointment || "-"}</td>
            <td data-label=""><button type="button" class="btn-action ci-btn--view ci-ico" title="View chart" aria-label="View chart" onclick="openChartViewModal(${index})"><span class="material-symbols-rounded" aria-hidden="true">image</span></button></td>
            <td data-label="Payments" class="ci-actions">
                ${payBtn}${histBtn}
            </td>
            <td data-label="Manage" class="ci-actions">
                <button type="button" class="btn-action ci-btn--edit ci-ico" title="Edit record" aria-label="Edit record" onclick="enterEditMode(${index})"><span class="material-symbols-rounded" aria-hidden="true">edit</span></button>
                <button type="button" class="btn-action ci-btn--delete ci-delete-btn ci-ico" title="Delete record" aria-label="Delete record" onclick="deleteTreatmentRecord(${index})"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>
            </td>
        `;
                    tbody.appendChild(tr);
                });
            }

            function enterEditMode(index) {
                const item = window.currentProcedures[index];
                const row = document.getElementById("ci-row-" + index);
                if (!row) return;

                ciClosePanels(index);
                const followUp = ciIsFollowUp(item);
                // On a plan, payments change only through "Record payment" so the
                // payment log can never disagree with Fee Paid. A follow-up
                // visit has no charge, so its money fields are fixed.
                const lockPaid = followUp;
                const lockValue = followUp;
                const lockTip = followUp
                    ? "A follow-up visit has no charge of its own."
                    : "Use the Record payment button to change what has been paid.";
                const statusCellEdit = followUp
                    ? '<span class="ci-badge ci-badge--follow">Follow-up</span>'
                    : statusBadge(item.status);
                const payBtn = "";
                const histBtn = "";
                row.innerHTML = `
        <td data-label="Assigned Dentist">
            <input type="text" class="ci-dentist" value="${escAttr(item.dentist)}">
        </td>
        <td data-label="Medicine"><input type="text" class="ci-medicine" value="${escAttr(item.medicine)}"></td>
        <td data-label="Visit Date"><input type="date" class="ci-date" value="${escAttr(item.date)}"></td>
        <td data-label="Tooth#"><input type="text" class="ci-tooth" value="${escAttr(item.tooth)}"></td>
        <td data-label="Procedure">${buildProcedureSelect(item.procedure)}</td>
        <td data-label="Notes"><input type="text" class="ci-notes" value="${escAttr(item.notes)}"></td>
        <td data-label="Value"><input type="number" class="ci-value" value="${item.value || 0}" step="0.01" ${lockValue ? 'readonly title="' + lockTip + '"' : ""}></td>
        <td data-label="Fee Paid"><input type="number" class="ci-paid" value="${item.paid || 0}" step="0.01" ${lockPaid ? 'readonly title="' + lockTip + '"' : ""}></td>
        <td data-label="Balance"><input type="number" class="ci-balance" value="${item.balance || 0}" step="0.01" readonly></td>
        <td data-label="Status">${statusCellEdit}</td>
        <td data-label="Next Appointment"><input type="date" class="ci-next-appt" value="${escAttr(item.next_appointment)}"></td>
        <td data-label=""><button type="button" class="btn-action ci-btn--view ci-ico" title="View chart" aria-label="View chart" onclick="openChartViewModal(${index})"><span class="material-symbols-rounded" aria-hidden="true">image</span></button></td>
        <td data-label="Payments" class="ci-actions">
            ${payBtn}${histBtn}
        </td>
        <td data-label="Manage" class="ci-actions">
            <button type="button" class="btn-action accept ci-btn--save ci-ico" title="Save changes" aria-label="Save changes" onclick="saveTreatmentEdit(${index})"><span class="material-symbols-rounded" aria-hidden="true">check</span></button>
            <button type="button" class="btn-action ci-btn--cancel ci-ico" title="Discard changes" aria-label="Discard changes" onclick="renderCheckInfoTable()"><span class="material-symbols-rounded" aria-hidden="true">close</span></button>
            <button type="button" class="btn-action ci-btn--delete ci-delete-btn ci-ico" title="Delete record" aria-label="Delete record" onclick="deleteTreatmentRecord(${index})"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>
        </td>
    `;

                ciEnhanceRow(row);
            }

            // Save is icon-only like the rest of the action cluster, so the pending
            // state is shown by swapping the glyph for a spinner rather than by writing
            // text (which would destroy the icon).
            function ciSetSaveState(btn, saving) {
                if (!btn) return;
                const icon = btn.querySelector(".material-symbols-rounded");
                btn.disabled = saving;
                if (saving) {
                    btn.setAttribute("data-saving", "true");
                    btn.setAttribute("aria-busy", "true");
                    btn.title = "Saving…";
                    if (icon) {
                        if (icon.dataset.idleGlyph === undefined) icon.dataset.idleGlyph = icon.textContent;
                        icon.textContent = "progress_activity";
                    }
                } else {
                    btn.removeAttribute("data-saving");
                    btn.removeAttribute("aria-busy");
                    btn.title = "Save changes";
                    if (icon && icon.dataset.idleGlyph !== undefined) {
                        icon.textContent = icon.dataset.idleGlyph;
                    }
                }
            }

            // Live balance recalculation while editing
            document.addEventListener("input", function (e) {
                if (e.target.matches("#checkInfoBody .ci-value, #checkInfoBody .ci-paid")) {
                    const row = e.target.closest("tr");
                    const value = parseFloat(row.querySelector(".ci-value").value) || 0;
                    const paid = parseFloat(row.querySelector(".ci-paid").value) || 0;
                    row.querySelector(".ci-balance").value = (value - paid).toFixed(2);
                }
            });

            async function saveTreatmentEdit(index) {
                const row = document.getElementById("ci-row-" + index);
                if (!row) return;

                const doneDocId = row.dataset.doneDocId;
                const procIndex = row.dataset.procIndex;
                const saveBtn = row.querySelector(".btn-action.accept");

                if (!currentCheckInfoPatientId || !doneDocId || procIndex === undefined) {
                    showToast("Missing information needed to save this record.");
                    return;
                }

                const formData = new FormData();
                formData.append("patient_id", currentCheckInfoPatientId);
                formData.append("done_doc_id", doneDocId);
                formData.append("proc_index", procIndex);
                formData.append("dentist", row.querySelector(".ci-dentist").value.trim());
                formData.append("medicine", row.querySelector(".ci-medicine").value.trim());
                formData.append("date", row.querySelector(".ci-date").value.trim());
                formData.append("tooth", row.querySelector(".ci-tooth").value.trim());
                formData.append("procedure", row.querySelector(".ci-procedure").value.trim());
formData.append("notes", row.querySelector(".ci-notes").value.trim());
                formData.append("value", row.querySelector(".ci-value").value.trim());
                formData.append("paid", row.querySelector(".ci-paid").value.trim());
                formData.append("next_appointment", row.querySelector(".ci-next-appt").value.trim());

                ciSetSaveState(saveBtn, true);

                try {
                    const response = await fetch("/admin/update_treatment_record", { method: "POST", body: formData });
                    const result = await response.json();

                    if (result.success) {
                        const item = window.currentProcedures[index];
                        item.dentist = row.querySelector(".ci-dentist").value.trim();
                        item.medicine = row.querySelector(".ci-medicine").value.trim();
                        item.date = row.querySelector(".ci-date").value.trim();
                        item.tooth = row.querySelector(".ci-tooth").value.trim();
                        item.procedure = row.querySelector(".ci-procedure").value.trim();
item.notes = row.querySelector(".ci-notes").value.trim();
                        item.value = parseFloat(row.querySelector(".ci-value").value) || 0;
                        item.paid = parseFloat(row.querySelector(".ci-paid").value) || 0;
                        item.balance = parseFloat(row.querySelector(".ci-balance").value) || 0;
                        item.next_appointment = row.querySelector(".ci-next-appt").value.trim();
                        // The server works the status out from value and payments.
                        if (!ciIsFollowUp(item)) item.status = item.balance <= 0 ? "Paid" : "Not Paid";

                        renderCheckInfoTable();
                    } else {
                        showToast(result.message || "Failed to update.");
                        ciSetSaveState(saveBtn, false);
                    }
                } catch (error) {
                    console.error("Update treatment record error:", error);
                    showToast("Failed to update treatment record. Please try again.");
                    ciSetSaveState(saveBtn, false);
                }
            }

            function closeCheckInfoModal() {
                document.getElementById("checkInfoModal").style.display = "none";
                ciDestroyRowWidgets();
            }


            let isDeletingTreatmentRecord = false;

            function peso(value) {
                const n = parseFloat(value);
                return "₱" + (isFinite(n) ? n.toFixed(2) : "0.00");
            }

            // Dedicated confirm dialog for treatment records. Kept apart from the shared
            // showConfirm()/#confirmModal that the patient REMOVE flow uses, so the two
            // can be styled and worded independently.
            function showDeleteTreatmentConfirm(item) {
                return new Promise(function (resolve) {
                    const modal = document.getElementById("deleteTreatmentModal");
                    const msgEl = document.getElementById("deleteTreatmentMessage");
                    const listEl = document.getElementById("deleteTreatmentDetails");
                    const okBtn = document.getElementById("deleteTreatmentOkBtn");
                    const cancelBtn = document.getElementById("deleteTreatmentCancelBtn");

                    if (!modal || !msgEl || !listEl || !okBtn || !cancelBtn) {
                        resolve(false);
                        return;
                    }

                    const rows = [
                        ["Procedure", (item.procedure || "").trim() || "—"],
                        ["Assigned dentist", formatDentistName(item.dentist) || "—"],
                        ["Visit date", (item.date || "").trim() || "—"],
                        ["Value", peso(item.value)],
                        ["Fee paid", peso(item.paid)],
                        ["Balance", peso(item.balance)],
                    ];

                    // Built with DOM nodes, not innerHTML: these are free-text fields
                    // from Firestore and must never be parsed as markup.
                    listEl.textContent = "";
                    rows.forEach(function (pair) {
                        const li = document.createElement("li");
                        const key = document.createElement("span");
                        key.className = "ci-danger-key";
                        key.textContent = pair[0];
                        const val = document.createElement("span");
                        val.className = "ci-danger-value";
                        val.textContent = pair[1];
                        li.appendChild(key);
                        li.appendChild(val);
                        listEl.appendChild(li);
                    });

                    const who = currentCheckInfoPatientName || "this patient";
                    msgEl.textContent = "This row will be removed from " + who + "'s treatment history.";

                    modal.style.display = "flex";

                    function cleanup(result) {
                        modal.style.display = "none";
                        okBtn.removeEventListener("click", onOk);
                        cancelBtn.removeEventListener("click", onCancel);
                        document.removeEventListener("keydown", onKey);
                        resolve(result);
                    }
                    function onOk() { cleanup(true); }
                    function onCancel() { cleanup(false); }
                    // Deliberately no backdrop-to-close: a confirmation must be
                    // answered with a button, or dismissed with Escape. A stray click
                    // outside used to close it and look like the action was skipped.
                    function onKey(e) { if (e.key === "Escape") cleanup(false); }

                    okBtn.addEventListener("click", onOk);
                    cancelBtn.addEventListener("click", onCancel);
                    document.addEventListener("keydown", onKey);
                    cancelBtn.focus();
                });
            }

            async function deleteTreatmentRecord(index) {
                // Same in-flight guard as the Submit Information button: this posts a
                // destructive request, so a double click must never send two DELETEs.
                if (isDeletingTreatmentRecord) {
                    showToast("A deletion is already in progress. Please wait.");
                    return;
                }

                const item = (window.currentProcedures || [])[index];
                if (!item) {
                    showToast("Procedure not found.");
                    return;
                }

                const confirmed = await showDeleteTreatmentConfirm(item);

                if (!confirmed) return;

                if (!currentCheckInfoPatientId || !item.done_doc_id || item.proc_index === undefined) {
                    showToast("Missing information needed to delete this record.");
                    return;
                }

                isDeletingTreatmentRecord = true;

                const formData = new FormData();
                formData.append("patient_id", currentCheckInfoPatientId);
                formData.append("done_doc_id", item.done_doc_id);
                formData.append("proc_index", item.proc_index);

                try {
                    const response = await fetch("/admin/delete_treatment_record", {
                        method: "POST",
                        body: formData
                    });
                    const result = await response.json();

                    if (result.success) {
                        showToast(result.message || "Treatment record deleted successfully.");

                        // Re-fetch from the server instead of splicing the local array.
                        // proc_index is relative to its own Done_procedure document, so
                        // every later row in that same document shifts down by one after
                        // a delete. A fresh load is the only way to guarantee that View
                        // and Edit on the remaining rows still target the right row.
                        if (currentCheckInfoPatientId) {
                            await openCheckInfoModal(currentCheckInfoPatientId);
                        }
                    } else {
                        showToast(result.message || "Failed to delete treatment record.");
                    }
                } catch (error) {
                    console.error("Delete treatment record error:", error);
                    showToast("Failed to delete treatment record. Please try again.");
                } finally {
                    isDeletingTreatmentRecord = false;
                }
            }