            const modal = document.getElementById("patientModal");
            const content = document.getElementById("patientContent");
            const closeBtn = document.getElementById("closeModalBtn");

            document.querySelectorAll(".open-patient-modal").forEach(btn => {

                btn.addEventListener("click", function () {

                    const uid = this.dataset.uid;

                    modal.style.display = "flex";
                    content.innerHTML = "Loading...";

                    fetch(`/get_patient/${uid}`)
                        .then(res => res.json())
                        .then(data => {

                            let html = `
                <h3>${data.full_name}</h3>
                <p><b>UID:</b> ${data.uid}</p>
                <p><b>Sex:</b> ${data.sex ?? ""}</p>
                <p><b>Age:</b> ${data.age ?? ""}</p>
                <p><b>Contact:</b> ${data.contact ?? ""}</p>
                <p><b>Service:</b> ${data.service ?? ""}</p>

                <hr>
                <h4>Procedures</h4>
            `;

                            const procedures = Array.isArray(data.Done_procedure)
                                ? data.Done_procedure
                                : [];

                            // Save globally for View button
                            window.currentProcedures = procedures;

                            const history = document.getElementById("pd-visit-history");

                            if (procedures.length === 0) {

                                html += "<p>No procedure records found.</p>";

                                if (history) {
                                    history.innerHTML = `
                        <tr>
                            <td colspan="6" style="text-align:center;">
                                No visit history found.
                            </td>
                        </tr>
                    `;
                                }

                            } else {

                                html += `
                    <table style="width:100%;border-collapse:collapse;">
                        <thead>
                            <tr>
                                <th>Assigned Dentist</th>
                                <th>Chart</th>
                                <th>Visit Date</th>
                                <th>Procedure</th>
                                <th>Fee Paid</th>
                                <th>Next Appointment</th>
                            </tr>
                        </thead>
                        <tbody>
                `;

                                let historyHTML = "";

                                procedures.forEach((p, index) => {

                                    const row = `
                        <tr>
                            <td>${p.dentist ?? ""}</td>

                            <td>
                                <button class="btn-action"
                                    onclick="openChartViewModal(${index})">
                                    View
                                </button>
                            </td>

                            <td>${p.date ?? ""}</td>
                            <td>${p.procedure ?? ""}</td>
                            <td>₱${p.paid ?? 0}</td>
                            <td>${p.next_appointment ?? ""}</td>
                        </tr>
                    `;

                                    html += row;
                                    historyHTML += row;

                                });

                                html += `
                        </tbody>
                    </table>
                `;

                                if (history) {
                                    history.innerHTML = historyHTML;
                                }
                            }

                            content.innerHTML = html;

                        })
                        .catch(err => {

                            console.error(err);

                            content.innerHTML = `
                <p style="color:red">
                    Failed to load patient.
                </p>
            `;
                        });

                });

            });

            if (closeBtn) {
                closeBtn.onclick = () => {
                    modal.style.display = "none";
                };
            }

            window.onclick = function (e) {
                if (e.target === modal) {
                    modal.style.display = "none";
                }
            };


