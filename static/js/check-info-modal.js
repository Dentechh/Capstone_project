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

            function statusBadge(status) {
                const isPaid = (status || "").trim().toLowerCase() === "paid";
                return `<span class="ci-badge ${isPaid ? "ci-badge--paid" : "ci-badge--unpaid"}">${isPaid ? "Paid" : "Not Paid"}</span>`;
            }

            // Header summary of the patient's latest confirmed
            // appointment. Built with textContent: the values come
            // straight from Firestore and must never be parsed as markup.
            function setCiApptText(id, value) {
                const el = document.getElementById(id);
                if (!el) return;
                const text = (value == null ? "" : String(value)).trim();
                el.textContent = text || "-";
            }

            function updateCiAppointment(appt) {
                const block = document.getElementById("ciAppointment");
                if (!block) return;

                if (!appt) {
                    block.hidden = true;
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
                setCiApptText("ciApptUrgency", appt.urgency_level);

                // Firestore stores the appointment status as
                // "accept"; the header reads better in past tense.
                const rawStatus = (appt.status || "").trim();
                const statusText = !rawStatus
                    ? ""
                    : rawStatus.toLowerCase() === "accept"
                        ? "Accepted"
                        : rawStatus.charAt(0).toUpperCase() + rawStatus.slice(1);
                setCiApptText("ciApptStatus", statusText);

                block.hidden = false;
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

                // Latest-appointment summary: hidden until the
                // treatment-info response says otherwise, so a
                // previous patient's facts never linger here.
                const apptBlock = document.getElementById("ciAppointment");
                if (apptBlock) apptBlock.hidden = true;

                if (!patientId) {
                    modal.style.display = "flex";
                    ciDestroyRowWidgets();
                    tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;">This patient has no booking history yet.</td></tr>`;
                    return;
                }

                ciDestroyRowWidgets();
                tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;">Loading...</td></tr>`;
                modal.style.display = "flex";

                try {
                    const response = await fetch("/get_treatment_info/" + encodeURIComponent(patientId));
                    const result = await response.json();

                    if (result.success && Array.isArray(result.procedures) && result.procedures.length > 0) {
                        window.currentProcedures = result.procedures;
                        renderCheckInfoTable();
                    } else {
                        window.currentProcedures = [];
                        tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;">No treatment history found.</td></tr>`;
                    }

                    // Header: latest confirmed appointment facts.
                    updateCiAppointment(result.latest_appointment);
                } catch (error) {
                    console.error("Error loading treatment info:", error);
                    tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#ef4444;">Failed to load treatment data.</td></tr>`;
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

                    tr.innerHTML = `
            <td data-label="Assigned Dentist">${formatDentistName(item.dentist) || "-"}</td>
            <td data-label="Medicine">${item.medicine || "-"}</td>
            <td data-label="Visit Date">${item.date || "-"}</td>
            <td data-label="Tooth#">${escAttr(item.tooth) || "-"}</td>
            <td data-label="Procedure">${item.procedure || "-"}</td>
            <td data-label="Value">₱${item.value || 0}</td>
            <td data-label="Fee Paid">₱${item.paid || 0}</td>
            <td data-label="Balance">₱${item.balance || 0}</td>
            <td data-label="Status">${statusBadge(item.status)}</td>
            <td data-label="Next Appointment">${item.next_appointment || "-"}</td>
            <td data-label=""><button type="button" class="btn-action ci-btn--view ci-ico" title="View chart" aria-label="View chart" onclick="openChartViewModal(${index})"><span class="material-symbols-rounded" aria-hidden="true">image</span></button></td>
            <td data-label="" class="ci-actions">
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

                const isPaid = (item.status || "").trim().toLowerCase() === "paid";
                row.innerHTML = `
        <td data-label="Assigned Dentist">
            <input type="text" class="ci-dentist" value="${escAttr(item.dentist)}">
        </td>
        <td data-label="Medicine"><input type="text" class="ci-medicine" value="${escAttr(item.medicine)}"></td>
        <td data-label="Visit Date"><input type="date" class="ci-date" value="${escAttr(item.date)}"></td>
        <td data-label="Tooth#"><input type="text" class="ci-tooth" value="${escAttr(item.tooth)}"></td>
        <td data-label="Procedure">${buildProcedureSelect(item.procedure)}</td>
        <td data-label="Value"><input type="number" class="ci-value" value="${item.value || 0}" step="0.01"></td>
        <td data-label="Fee Paid"><input type="number" class="ci-paid" value="${item.paid || 0}" step="0.01"></td>
        <td data-label="Balance"><input type="number" class="ci-balance" value="${item.balance || 0}" step="0.01" readonly></td>
        <td data-label="Status">
            <select class="ci-status">
                <option value="Not Paid" ${!isPaid ? "selected" : ""}>Not Paid</option>
                <option value="Paid" ${isPaid ? "selected" : ""}>Paid</option>
            </select>
        </td>
        <td data-label="Next Appointment"><input type="date" class="ci-next-appt" value="${escAttr(item.next_appointment)}"></td>
        <td data-label=""><button type="button" class="btn-action ci-btn--view ci-ico" title="View chart" aria-label="View chart" onclick="openChartViewModal(${index})"><span class="material-symbols-rounded" aria-hidden="true">image</span></button></td>
        <td data-label="" class="ci-actions">
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
                formData.append("value", row.querySelector(".ci-value").value.trim());
                formData.append("paid", row.querySelector(".ci-paid").value.trim());
                formData.append("next_appointment", row.querySelector(".ci-next-appt").value.trim());
                formData.append("status", row.querySelector(".ci-status").value.trim());

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
                        item.value = parseFloat(row.querySelector(".ci-value").value) || 0;
                        item.paid = parseFloat(row.querySelector(".ci-paid").value) || 0;
                        item.balance = parseFloat(row.querySelector(".ci-balance").value) || 0;
                        item.next_appointment = row.querySelector(".ci-next-appt").value.trim();
                        item.status = row.querySelector(".ci-status").value.trim();

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