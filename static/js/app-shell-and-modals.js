        function updateDateTime() {
            const now = new Date();
            const dateEl = document.getElementById('dt-date');
            const timeEl = document.getElementById('dt-time');
            if (!dateEl || !timeEl) return;

            // e.g. Sunday, October 4, 2026
            const dateText = now.toLocaleDateString('en-US', {
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
            });
            if (dateEl.textContent !== dateText) dateEl.textContent = dateText;

            // e.g. 12:41:57 AM
            timeEl.textContent = now.toLocaleTimeString('en-US', {
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
            });
        }

        // Update immediately, then every second
        updateDateTime();
        setInterval(updateDateTime, 1000);

        //teetch backend '



        // =========================
        // SAVE DENTAL RECORD
        // =========================

        let isDentalRecordSaving = false;

        async function saveDentalRecord(uid) {

            // ---- RE-ENTRY GUARD: block duplicate submissions ----
            if (isDentalRecordSaving) {
                showToast("Submission already in progress. Please wait.");
                return;
            }

            isDentalRecordSaving = true;

            const submitBtn = document.getElementById('td-save-btn');
            const submitBtnText = submitBtn ? submitBtn.textContent : null;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "SUBMITTING...";
            }

            let saveSucceeded = false;

            try {

                // =====================================================
                // CLEAN UID
                // =====================================================

                if (!uid) {
                    showToast("Patient UID is missing.");
                    return;
                }

                console.log("====================================");
                console.log("FINAL UID BEING SENT:", uid);
                console.log("====================================");


                // =====================================================
                // GET DENTAL CHART
                // =====================================================

                const chartSection = document.querySelector(".dental-chart");

                if (!chartSection) {
                    showToast("Dental chart not found.");
                    return;
                }

                const tempContainer = document.createElement("div");
                tempContainer.style.cssText =
                    "position:fixed;left:-9999px;top:-9999px;width:" +
                    chartSection.scrollWidth +
                    "px;z-index:-1;";
                document.body.appendChild(tempContainer);

                const cleanClone = chartSection.cloneNode(true);
                tempContainer.appendChild(cleanClone);

                const clonedChart = cleanClone.querySelector(".dental-chart");
                const clonedPalette = cleanClone.querySelector(".action-palette");
                cleanClone.style.colorScheme = "light";   // ADD THIS LINE

                if (clonedChart) {
                    clonedChart.style.backdropFilter = "none";
                    clonedChart.style.webkitBackdropFilter = "none";
                    clonedChart.style.filter = "none";
                }

                if (clonedPalette) {
                    clonedPalette.style.backdropFilter = "none";
                    clonedPalette.style.webkitBackdropFilter = "none";
                    clonedPalette.style.filter = "none";
                }

                cleanClone.querySelectorAll("*").forEach((el) => {
                    el.style.backdropFilter = "none";
                    el.style.webkitBackdropFilter = "none";
                    if (el.style.filter && el.style.filter.includes("blur")) {
                        el.style.filter = "none";
                    }
                });

                // Declare OUTSIDE try — so finally can see them
                let materialFontLink = document.querySelector('link[href*="Material+Symbols"]');
                let materialFontLinkParent = null;
                let materialFontLinkNext = null;

                if (materialFontLink) {
                    materialFontLinkParent = materialFontLink.parentNode;
                    materialFontLinkNext = materialFontLink.nextSibling;
                    materialFontLinkParent.removeChild(materialFontLink);
                }

                let canvas;
                try {
                    canvas = await html2canvas(cleanClone, {
                        scale: 2, // or 1 in saveDentalRecord
                        useCORS: true,
                        allowTaint: true,
                        backgroundColor: '#ffffff',
                        scrollX: 0,
                        scrollY: 0,
                        windowWidth: chartSection.scrollWidth,
                        windowHeight: chartSection.scrollHeight,
                        width: chartSection.scrollWidth,
                        height: chartSection.scrollHeight,
                        ignoreElements: (el) => el.classList.contains("action-palette"),
                        logging: false,
                    });
                } finally {
                    document.body.removeChild(tempContainer);
                    if (materialFontLink && materialFontLinkParent) {
                        materialFontLinkParent.insertBefore(materialFontLink, materialFontLinkNext);
                    }
                }

                // ADD THIS BLOCK — force a white background before JPEG conversion
                const flattenedCanvas = document.createElement('canvas');
                flattenedCanvas.width = canvas.width;
                flattenedCanvas.height = canvas.height;
                const flatCtx = flattenedCanvas.getContext('2d');
                flatCtx.fillStyle = '#ffffff';
                flatCtx.fillRect(0, 0, flattenedCanvas.width, flattenedCanvas.height);
                flatCtx.drawImage(canvas, 0, 0);

                // CHANGE: convert the flattened canvas instead of the original


                // =====================================================
                // CONVERT CANVAS TO IMAGE
                // =====================================================

                const blob = await new Promise(resolve => {
                    flattenedCanvas.toBlob(resolve, "image/jpeg", 0.7);
                });


                if (!blob) {
                    showToast("Failed to create dental chart image.");
                    return;
                }


                // =====================================================
                // FORM DATA
                // =====================================================

                const formData = new FormData();


                // =====================================================
                // UID
                // =====================================================

                formData.append("uid", uid);


                // =====================================================
                // PATIENT UNIQUE ID
                // =====================================================

                const patientElement =
                    document.getElementById("td-Patient_unq_id");

                const patientUnqId =
                    patientElement
                        ? patientElement.textContent.trim()
                        : "";


                console.log(
                    "PATIENT UNIQUE ID:",
                    patientUnqId
                );


                if (!patientUnqId || patientUnqId === "-") {

                    showToast(
                        "Patient Record ID is missing."
                    );

                    return;
                }


                formData.append(
                    "Patient_unq_id",
                    patientUnqId
                );


                // =====================================================
                // DENTAL CHART IMAGE
                // =====================================================

                formData.append(
                    "dental_chart_image",
                    blob,
                    "chart.jpg"
                );


                // =====================================================
                // TOOTH DATA
                // =====================================================

                document
                    .querySelectorAll(".tooth-unit")
                    .forEach(tooth => {

                        const id =
                            tooth.id.replace(
                                "tooth-",
                                ""
                            );

                        let value = "healthy";


                        if (
                            tooth.classList.contains("caries")
                        ) {
                            value = "caries";
                        }

                        else if (
                            tooth.classList.contains("filling")
                        ) {
                            value = "filling";
                        }

                        else if (
                            tooth.classList.contains("crown")
                        ) {
                            value = "crown";
                        }

                        else if (
                            tooth.classList.contains("rootcanal")
                        ) {
                            value = "rootcanal";
                        }

                        else if (
                            tooth.classList.contains("missing")
                        ) {
                            value = "missing";
                        }

                        else if (
                            tooth.classList.contains("extraction")
                        ) {
                            value = "extraction";
                        }

                        else if (
                            tooth.classList.contains("check")
                        ) {
                            value = "check";
                        }


                        formData.append(
                            `tooth_${id}`,
                            value
                        );

                    });


                // =====================================================
                // TREATMENT TABLE
                // =====================================================

                document
                    .querySelectorAll(
                        "#td-treatment-table tbody tr"
                    )
                    .forEach(row => {

                        formData.append(
                            "date[]",
                            row.querySelector(".td-date")?.value || ""
                        );

                        formData.append(
                            "tooth[]",
                            row.querySelector(".td-tooth")?.value || ""
                        );

                        formData.append(
                            "procedure[]",
                            row.querySelector(".td-procedure")?.value || ""
                        );

                        formData.append(
                            "dentist[]",
                            row.querySelector(".td-dentist")?.value || ""
                        );

                        formData.append(
                            "value[]",
                            row.querySelector(".td-value")?.value || ""
                        );

                        formData.append(
                            "paid[]",
                            row.querySelector(".td-paid")?.value || ""
                        );

                        formData.append(
                            "balance[]",
                            row.querySelector(".td-balance")?.value || ""
                        );

                        formData.append(
                            "next_appointment[]",
                            row.querySelector(".td-next-appt")?.value || ""
                        );

                        formData.append(
                            "medicine[]",
                            row.querySelector(".td-medicine")?.value || ""
                        );

                        formData.append(
                            "status[]",
                            row.querySelector(".td-status")?.value || ""
                        );

                    });


                // =====================================================
                // DEBUG
                // =====================================================

                console.log("====================================");
                console.log("SENDING DENTAL RECORD");
                console.log("UID:", uid);
                console.log("Patient_unq_id:", patientUnqId);
                console.log("====================================");


                // =====================================================
                // SEND TO FLASK
                // =====================================================

                const response = await fetch(
                    "/save_dental_record",
                    {
                        method: "POST",
                        body: formData
                    }
                );


                if (!response.ok) {

                    const text = await response.text();

                    throw new Error(
                        "Server returned status " +
                        response.status +
                        ": " +
                        text.slice(0, 200)
                    );

                }


                // =====================================================
                // GET RESPONSE
                // =====================================================

                let result;

                try {

                    result = await response.json();

                } catch (jsonError) {

                    const text = await response.text();

                    throw new Error(
                        "Invalid server response: " +
                        text.slice(0, 200)
                    );

                }


                console.log(
                    "SERVER STATUS:",
                    response.status
                );

                console.log(
                    "SERVER RESPONSE:",
                    result
                );


                // =====================================================
                // SUCCESS
                // =====================================================

                if (result.success) {

                    saveSucceeded = true;

                    showToast(
                        "Dental record saved successfully!"
                    );

                    location.reload();

                }

                else {

                    showToast(
                        "Error: " +
                        (
                            result.message ||
                            "Unknown error"
                        )
                    );

                }

            }

            catch (error) {

                console.error(
                    "SAVE DENTAL RECORD ERROR:",
                    error
                );

                showToast(
                    "Failed to save dental record: " +
                    (
                        error.message ||
                        error.toString() ||
                        "Unknown error"
                    )
                );

            }

            finally {

                isDentalRecordSaving = false;

                // Keep the button locked on success (page is reloading).
                if (submitBtn && !saveSucceeded) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = submitBtnText;
                }

            }

        }

        // =========================
        // SINGLE CLEAN BUTTON HANDLER
        // =========================
        document.getElementById("td-save-btn").addEventListener("click", () => {

            // #pd-id now holds the bare uid (the "Account No" label is in the
            // markup), so no string stripping is needed here. currentPatientUid is
            // the fallback for the empty initial state of the header.
            const uid = (document.getElementById("pd-id")?.textContent || "").trim()
                || window.currentPatientUid
                || "";

            if (!uid) {
                showToast("No patient selected!");
                return;
            }

            const rows = document.querySelectorAll("#td-treatment-table tbody tr");
            let hasValidNote = false;

            rows.forEach(row => {
                const date = row.querySelector(".td-date")?.value.trim() || "";
                const procedure = row.querySelector(".td-procedure")?.value.trim() || "";
                const dentist = row.querySelector(".td-dentist")?.value.trim() || "";
                const valueOfWork = row.querySelector(".td-value")?.value.trim() || "";
                const amountPaid = row.querySelector(".td-paid")?.value.trim() || "";
                const nextAppt = row.querySelector(".td-next-appt")?.value.trim() || "";

                if (date || procedure || dentist || valueOfWork || amountPaid || nextAppt) {
                    hasValidNote = true;
                }
            });

            if (!hasValidNote) {
                showToast("Please fill in at least one treatment note before submitting.");
                return;
            }

            saveDentalRecord(uid);
        });

        // Sidebar Toggle for Mobile
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebar = document.querySelector('.sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');

        if (sidebarToggle && sidebar && sidebarOverlay) {
            sidebarToggle.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                sidebarOverlay.classList.toggle('active');
            });

            sidebarOverlay.addEventListener('click', () => {
                sidebar.classList.remove('open');
                sidebarOverlay.classList.remove('active');
            });

            const navItems = sidebar.querySelectorAll('.nav-item');
            navItems.forEach(item => {
                item.addEventListener('click', () => {
                    if (window.innerWidth <= 768) {
                        sidebar.classList.remove('open');
                        sidebarOverlay.classList.remove('active');
                    }
                });
            });
        }

        // Logout Confirmation Modal
        function openLogoutModal() {
            const modal = document.getElementById('logoutModal');
            if (modal) {
                modal.style.display = 'flex';
            }
        }

        function closeLogoutModal() {
            const modal = document.getElementById('logoutModal');
            if (modal) {
                modal.style.display = 'none';
            }
        }

        function confirmLogout() {
            window.location.href = '/logout';
        }

        // Sidebar Logout Button
        const sidebarLogoutBtn = document.getElementById('sidebarLogoutBtn');
        if (sidebarLogoutBtn) {
            sidebarLogoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                openLogoutModal();
            });
        }

        // Close logout modal when clicking outside
        window.addEventListener('click', function (e) {
            const logoutModal = document.getElementById('logoutModal');
            if (e.target === logoutModal) {
                closeLogoutModal();
            }
        });

        // Dental Chart Modal
        function openLiveChartModal() {
            var chartSection = document.getElementById('section-chart');
            var modalContent = document.getElementById('live-modal-chart-content');
            var modal = document.getElementById('liveChartModal');

            if (!chartSection || !modalContent || !modal) return;

            window._chartSectionRef = chartSection;
            window._chartOriginalParent = chartSection.parentNode;
            window._chartOriginalNextSibling = chartSection.nextSibling;

            modalContent.innerHTML = '';
            modalContent.appendChild(chartSection);
            chartSection.style.display = 'block';
            modal.style.display = 'flex';
            window._chartInModal = true;

            // Force landscape on mobile — request fullscreen first, then lock orientation
            const tryLockLandscape = () => {
                if (screen.orientation && screen.orientation.lock) {
                    screen.orientation.lock('landscape').catch(() => { });
                }
            };

            const onFullscreenEnter = () => {
                tryLockLandscape();
            };

            document.addEventListener('fullscreenchange', onFullscreenEnter, { once: true });
            document.addEventListener('webkitfullscreenchange', onFullscreenEnter, { once: true });

            if (document.documentElement.requestFullscreen) {
                document.documentElement.requestFullscreen().catch(() => { });
            } else if (document.documentElement.webkitRequestFullscreen) {
                document.documentElement.webkitRequestFullscreen();
            } else {
                tryLockLandscape();
            }
        }

        /* ============================================================
           SAVED DENTAL CHART VIEWER
           Zoom / pan / rotate / flip / fullscreen / download.
           The public entry points keep their original names and
           signatures so the four existing View buttons are unaffected.
           ============================================================ */
        const chartView = {
            scale: 1,        // user multiplier on top of the fit scale
            baseScale: 1,    // scale that makes the image fit the viewport
            x: 0,
            y: 0,
            rot: 0,          // degrees
            flipH: false,
            flipV: false,
            fitMode: true,   // true = "fit", false = "1:1"
            ready: false,    // true only once the image has real pixel dimensions
            failed: false,
            drag: null,
            prevBodyOverflow: null
        };

        const CHART_VIEW_MIN = 0.25;
        const CHART_VIEW_MAX = 8;

        function chartViewEls() {
            return {
                modal: document.getElementById('chartViewModal'),
                img: document.getElementById('viewSavedChartImage'),
                viewport: document.getElementById('chartViewViewport'),
                zoom: document.getElementById('chartZoomReadout'),
                dims: document.getElementById('chartViewDims'),
                meta: document.getElementById('chartViewMeta'),
                loading: document.getElementById('chartViewLoading'),
                loadingIcon: document.getElementById('chartViewLoadingIcon'),
                loadingText: document.getElementById('chartViewLoadingText')
            };
        }

        /* Loading / error placeholder. The image has no intrinsic size until its
           data URL decodes, so without this the stage collapses and then jumps. */
        function chartViewerSetLoading(loading, failed) {
            const els = chartViewEls();
            if (els.loading) els.loading.hidden = !loading;
            if (els.viewport) els.viewport.classList.toggle('is-loading', !!loading);
            if (els.loadingIcon) {
                els.loadingIcon.textContent = failed ? 'broken_image' : 'progress_activity';
                els.loadingIcon.classList.toggle('is-error', !!failed);
            }
            if (els.loadingText) {
                els.loadingText.textContent = failed
                    ? 'This chart image could not be loaded.'
                    : 'Loading chart…';
            }
            // Re-apply so the transform, cursor and readouts are all reset to their
            // inert pre-load state in one place.
            chartViewerApply();
        }

        function chartViewerReset() {
            chartView.scale = 1;
            chartView.x = 0;
            chartView.y = 0;
            chartView.rot = 0;
            chartView.flipH = false;
            chartView.flipV = false;
            chartView.fitMode = true;

            const els = chartViewEls();
            if (els.img) els.img.classList.remove('is-panning');

            const fh = document.getElementById('chartFlipHBtn');
            const fv = document.getElementById('chartFlipVBtn');
            if (fh) fh.classList.remove('is-on');
            if (fv) fv.classList.remove('is-on');

            chartViewerFit();
        }

        // Scale that makes the whole image visible inside the viewport.
        function chartViewerComputeFit() {
            const els = chartViewEls();
            if (!els.img || !els.viewport) return 1;

            const iw = els.img.naturalWidth || 0;
            const ih = els.img.naturalHeight || 0;

            // Before the data URL decodes the image is 0x0. Guessing here produced an
            // enormous scale that got painted for a frame, which read as a flicker.
            if (!iw || !ih) return 1;
            const vw = els.viewport.clientWidth || 1;
            const vh = els.viewport.clientHeight || 1;

            // A 90/270 degree rotation swaps the axes.
            const swapped = Math.abs(chartView.rot % 180) === 90;
            const boxW = swapped ? ih : iw;
            const boxH = swapped ? iw : ih;

            const pad = 32;
            return Math.min((vw - pad) / boxW, (vh - pad) / boxH) || 1;
        }

        function chartViewerClamp() {
            const els = chartViewEls();
            if (!els.img || !els.viewport || !chartView.ready) return;

            const iw = els.img.naturalWidth || 1;
            const ih = els.img.naturalHeight || 1;
            const total = chartView.baseScale * chartView.scale;

            const swapped = Math.abs(chartView.rot % 180) === 90;
            const halfW = (swapped ? ih : iw) * total / 2;
            const halfH = (swapped ? iw : ih) * total / 2;

            // Let the image travel at most its own half-diagonal, so it can never
            // be flung completely out of view.
            const maxX = halfW + els.viewport.clientWidth / 2;
            const maxY = halfH + els.viewport.clientHeight / 2;

            chartView.x = Math.max(-maxX, Math.min(maxX, chartView.x));
            chartView.y = Math.max(-maxY, Math.min(maxY, chartView.y));
        }

        function chartViewerApply() {
            const els = chartViewEls();
            if (!els.img) return;

            // Until the image reports real dimensions there is nothing meaningful to
            // transform. Leaving the transform empty also stops the browser from
            // painting a stale one.
            if (!chartView.ready) {
                els.img.style.transform = '';
                els.img.style.cursor = 'default';
                if (els.zoom) els.zoom.textContent = '—';
                if (els.dims) els.dims.textContent = '';
                return;
            }

            const total = chartView.baseScale * chartView.scale;
            const parts = [];
            if (chartView.x || chartView.y) parts.push('translate(' + chartView.x + 'px,' + chartView.y + 'px)');
            if (chartView.rot) parts.push('rotate(' + chartView.rot + 'deg)');
            if (chartView.flipH) parts.push('scaleX(-1)');
            if (chartView.flipV) parts.push('scaleY(-1)');
            parts.push('scale(' + total + ')');

            els.img.style.transform = parts.join(' ');
            els.img.style.cursor = total > 1 ? 'grab' : 'default';

            if (els.zoom) {
                // Fit mode reports the user's multiplier; 1:1 reports true pixels.
                els.zoom.textContent = Math.round(
                    (chartView.fitMode ? chartView.scale : total) * 100
                ) + '%';
            }

            if (els.dims) {
                const nw = els.img.naturalWidth || 0;
                const nh = els.img.naturalHeight || 0;
                els.dims.textContent = nw ? nw + ' × ' + nh + ' px' : '';
            }
        }

        function chartViewerRelayout() {
            const els = chartViewEls();
            if (!els.img || !els.viewport || !chartView.ready) return;
            if (chartView.fitMode) {
                chartView.baseScale = chartViewerComputeFit();
            }
            chartViewerClamp();
            chartViewerApply();
        }

        function chartViewerFit() {
            const els = chartViewEls();
            if (!els.img) return;
            chartView.fitMode = true;
            chartView.scale = 1;
            chartView.x = 0;
            chartView.y = 0;
            chartViewerRelayout();
        }

        function chartViewerActualSize() {
            const els = chartViewEls();
            if (!els.img) return;
            chartView.fitMode = false;
            chartView.baseScale = 1;      // natural pixels
            chartView.scale = 1;
            chartView.x = 0;
            chartView.y = 0;
            chartViewerApply();
        }

        function chartViewerZoomBy(factor) {
            if (!chartView.ready) return;
            const next = chartView.scale * factor;
            chartView.scale = Math.max(CHART_VIEW_MIN, Math.min(CHART_VIEW_MAX, next));
            if (chartView.scale !== 1) chartView.fitMode = false;
            chartViewerClamp();
            chartViewerApply();
        }

        function chartViewerZoomAt(factor, originX, originY) {
            const els = chartViewEls();
            if (!chartView.ready) return;
            if (!els.img || !els.viewport) { chartViewerZoomBy(factor); return; }

            const box = els.viewport.getBoundingClientRect();
            const cx = originX - box.left - box.width / 2;
            const cy = originY - box.top - box.height / 2;

            const before = chartView.scale;
            const next = Math.max(CHART_VIEW_MIN, Math.min(CHART_VIEW_MAX, before * factor));
            if (next === before) return;

            // keep the point under the cursor fixed
            const ratio = next / before;
            chartView.x = cx - (cx - chartView.x) * ratio;
            chartView.y = cy - (cy - chartView.y) * ratio;
            chartView.scale = next;
            if (next !== 1) chartView.fitMode = false;

            chartViewerClamp();
            chartViewerApply();
        }

        function chartViewerRotate(deg) {
            chartView.rot = (chartView.rot + deg) % 360;
            if (chartView.rot < 0) chartView.rot += 360;
            chartViewerRelayout();
        }

        function chartViewerFlip(axis) {
            if (axis === 'h') {
                chartView.flipH = !chartView.flipH;
                const b = document.getElementById('chartFlipHBtn');
                if (b) b.classList.toggle('is-on', chartView.flipH);
            } else {
                chartView.flipV = !chartView.flipV;
                const b = document.getElementById('chartFlipVBtn');
                if (b) b.classList.toggle('is-on', chartView.flipV);
            }
            chartViewerApply();
        }

        function chartViewerToggleFullscreen() {
            const els = chartViewEls();
            if (!els.modal) return;
            const btn = document.getElementById('chartFullscreenBtn');
            const icon = btn ? btn.querySelector('.material-symbols-rounded') : null;

            if (document.fullscreenElement) {
                if (document.exitFullscreen) document.exitFullscreen().catch(function () { });
                if (icon) icon.textContent = 'fullscreen';
            } else if (els.modal.requestFullscreen) {
                els.modal.requestFullscreen().catch(function () { });
                if (icon) icon.textContent = 'fullscreen_exit';
            }
        }

        function chartViewerDownload() {
            const els = chartViewEls();
            if (!els.img || !els.img.src) return;

            const name = (els.meta && els.meta.dataset.name) || 'dental-chart';
            const a = document.createElement('a');
            a.href = els.img.src;
            a.download = name.replace(/[^\w\-]+/g, '-').replace(/-+/g, '-') + '.jpg';
            document.body.appendChild(a);
            a.click();
            a.remove();
        }

        /* ---- pointer panning ---- */
        function chartViewerBindPanning() {
            const els = chartViewEls();
            if (!els.viewport || !els.img) return;

            els.viewport.addEventListener('mousedown', function (e) {
                if (e.button !== 0) return;
                chartView.drag = { startX: e.clientX, startY: e.clientY, origX: chartView.x, origY: chartView.y };
                els.img.classList.add('is-panning');
                e.preventDefault();
            });

            window.addEventListener('mousemove', function (e) {
                if (!chartView.drag) return;
                chartView.x = chartView.drag.origX + (e.clientX - chartView.drag.startX);
                chartView.y = chartView.drag.origY + (e.clientY - chartView.drag.startY);
                chartViewerClamp();
                chartViewerApply();
            });

            window.addEventListener('mouseup', function () {
                if (!chartView.drag) return;
                chartView.drag = null;
                if (els.img) els.img.classList.remove('is-panning');
            });

            // Scroll to zoom, anchored on the pointer.
            els.viewport.addEventListener('wheel', function (e) {
                if (!e.ctrlKey && Math.abs(e.deltaY) < 2) return;
                e.preventDefault();
                chartViewerZoomAt(e.deltaY < 0 ? 1.12 : 0.89, e.clientX, e.clientY);
            }, { passive: false });

            // Double click toggles between fit and 1:1.
            els.viewport.addEventListener('dblclick', function () {
                if (chartView.fitMode) chartViewerActualSize(); else chartViewerFit();
            });
        }

        function chartViewerBindKeys() {
            document.addEventListener('keydown', function (e) {
                const els = chartViewEls();
                if (!els.modal || els.modal.style.display !== 'flex') return;

                const tag = (e.target && e.target.tagName) || '';
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

                let handled = true;
                switch (e.key) {
                    case 'Escape': closeChartViewModal(); break;
                    case '+': case '=': chartViewerZoomBy(1.25); break;
                    case '-': case '_': chartViewerZoomBy(0.8); break;
                    case '0': chartViewerFit(); break;
                    case '1': chartViewerActualSize(); break;
                    case 'r': case 'R': chartViewerRotate(90); break;
                    case 'l': case 'L': chartViewerRotate(-90); break;
                    case 'h': case 'H': chartViewerFlip('h'); break;
                    case 'v': case 'V': chartViewerFlip('v'); break;
                    case 'f': case 'F': chartViewerToggleFullscreen(); break;
                    case 'ArrowLeft': chartView.x += 40; chartViewerClamp(); chartViewerApply(); break;
                    case 'ArrowRight': chartView.x -= 40; chartViewerClamp(); chartViewerApply(); break;
                    case 'ArrowUp': chartView.y += 40; chartViewerClamp(); chartViewerApply(); break;
                    case 'ArrowDown': chartView.y -= 40; chartViewerClamp(); chartViewerApply(); break;
                    default: handled = false;
                }
                if (handled) e.preventDefault();
            });
        }

        let chartViewerBound = false;

        // Panning and key handling are global listeners, so bind them exactly once,
        // lazily, the first time the viewer is opened.
        function chartViewerEnsureBound() {
            if (chartViewerBound) return;
            chartViewerBound = true;
            chartViewerBindPanning();
            chartViewerBindKeys();
        }

        function openChartViewModal(index) {
            chartViewerEnsureBound();

            if (window._chartInModal && window._chartSectionRef && window._chartOriginalParent) {
                window._chartOriginalParent.insertBefore(window._chartSectionRef, window._chartOriginalNextSibling);
                window._chartInModal = false;
                window._chartSectionRef = null;
                window._chartOriginalParent = null;
                window._chartOriginalNextSibling = null;
            }

            if (!window.currentProcedures || !window.currentProcedures[index]) {
                showToast("Procedure not found.");
                return;
            }

            const item = window.currentProcedures[index];
            const chartImage = item.chart_image;

            const els = chartViewEls();
            if (!els.modal || !els.img) return;

            if (!chartImage) {
                showToast("No saved chart image for this record.");
                return;
            }

            els.img.src = "data:image/jpeg;base64," + chartImage;

            // Show what the admin is actually looking at.
            if (els.meta) {
                const bits = [];
                if (item.procedure) bits.push(item.procedure);
                if (item.dentist) bits.push(item.dentist);
                if (item.date) bits.push(item.date);
                els.meta.textContent = bits.join('   ·   ');
                els.meta.dataset.name = item.procedure || item.dentist || 'dental-chart';
            }

            // Start from a clean, inert state: the previous record's transform must
            // not be painted against the new, not-yet-decoded image.
            chartView.ready = false;
            chartView.failed = false;
            chartViewerSetLoading(true, false);
            chartViewerReset();

            els.modal.style.display = 'flex';

            // Lock the page behind while the viewer is open, and restore exactly
            // what was there before.
            chartView.prevBodyOverflow = document.body.style.overflow;
            document.body.style.overflow = 'hidden';

            // naturalWidth is only known once the data URL has decoded. Lay out once,
            // on whichever of these comes first, and not before.
            function settle() {
                if (!els.img.naturalWidth) {
                    chartView.failed = true;
                    chartView.ready = false;
                    chartViewerSetLoading(true, true);
                    chartViewerApply();
                    return;
                }
                chartView.ready = true;
                chartViewerSetLoading(false, false);
                chartViewerRelayout();
            }

            if (els.img.complete) {
                // complete + no naturalWidth means a cached failure, not a pending load
                settle();
            } else {
                els.img.onload = function () {
                    els.img.onload = null;
                    els.img.onerror = null;
                    settle();
                };
                els.img.onerror = function () {
                    els.img.onload = null;
                    els.img.onerror = null;
                    chartView.failed = true;
                    chartView.ready = false;
                    chartViewerSetLoading(true, true);
                    chartViewerApply();
                };
            }
        }

        function closeLiveChartModal() {
            const modal = document.getElementById('liveChartModal');
            if (modal) {
                modal.style.display = 'none';
                document.body.style.overflow = '';

                if (window._chartInModal && window._chartSectionRef && window._chartOriginalParent) {
                    window._chartOriginalParent.insertBefore(window._chartSectionRef, window._chartOriginalNextSibling);
                    window._chartSectionRef.style.display = '';
                    window._chartInModal = false;
                    window._chartSectionRef = null;
                    window._chartOriginalParent = null;
                    window._chartOriginalNextSibling = null;
                }

                if (screen.orientation && screen.orientation.unlock) {
                    screen.orientation.unlock();
                }

                if (document.exitFullscreen) {
                    document.exitFullscreen().catch(() => { });
                }
            }
        }

        function closeChartViewModal() {
            const els = chartViewEls();
            if (!els.modal) return;

            els.modal.style.display = 'none';

            // Drop the handlers first, so a decode that lands after close cannot
            // re-run the layout against a hidden modal.
            if (els.img) {
                els.img.onload = null;
                els.img.onerror = null;
                els.img.src = '';
                els.img.style.transform = '';
            }

            chartView.ready = false;
            chartView.failed = false;
            chartViewerSetLoading(false, false);

            if (document.fullscreenElement && document.exitFullscreen) {
                document.exitFullscreen().catch(function () { });
            }
            const fsBtn = document.getElementById('chartFullscreenBtn');
            const fsIcon = fsBtn ? fsBtn.querySelector('.material-symbols-rounded') : null;
            if (fsIcon) fsIcon.textContent = 'fullscreen';

            if (chartView.prevBodyOverflow !== null) {
                document.body.style.overflow = chartView.prevBodyOverflow;
                chartView.prevBodyOverflow = null;
            }

            chartView.drag = null;
            chartView.scale = 1;
            chartView.baseScale = 1;
            chartView.x = 0;
            chartView.y = 0;
            chartView.rot = 0;
            chartView.flipH = false;
            chartView.flipV = false;
            chartView.fitMode = true;
        }

        // Close live chart modal on backdrop click
        window.addEventListener('click', function (e) {
            const modal = document.getElementById('liveChartModal');
            if (e.target === modal) {
                closeLiveChartModal();
            }
        });

        // Saved chart viewer: deliberately NOT closable by a backdrop click. The
        // panel is a body-level popup, so a click anywhere - including the modal
        // behind it - would otherwise dismiss the viewer mid-zoom. Use the X, the
        // Escape key, or (for a fullscreen viewer) the browser's own Escape.
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            const viewer = document.getElementById('chartViewModal');
            if (viewer && viewer.style.display === 'flex') {
                closeChartViewModal();
            }
        });

        // Close live chart modal on Escape key
        window.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                const liveModal = document.getElementById('liveChartModal');
                if (liveModal && liveModal.style.display === 'flex') {
                    closeLiveChartModal();
                }
            }
        });

        // =========================================
        // DASHBOARD ANIMATIONS & CHARTS
        // =========================================

        // Count-up animation for metric and mini-stat numbers
        function animateCounters() {
            document.querySelectorAll('[data-target]').forEach(el => {
                const target = parseInt(el.getAttribute('data-target'));
                if (isNaN(target)) return;
                const duration = 1500;
                const startTime = performance.now();

                function update(now) {
                    const elapsed = now - startTime;
                    const progress = Math.min(elapsed / duration, 1);
                    const eased = 1 - Math.pow(1 - progress, 3);
                    el.textContent = Math.floor(eased * target);
                    if (progress < 1) {
                        requestAnimationFrame(update);
                    } else {
                        el.textContent = target;
                    }
                }
                requestAnimationFrame(update);
            });
        }

        // Initialize dashboard charts
        let dashboardDonutInstance = null;
        let dashboardBarInstance = null;
        function initDashboardCharts() {
            let dashboardData = {};
            try {
                const raw = document.getElementById('dashboard-data');
                if (raw) dashboardData = JSON.parse(raw.textContent || '{}');
            } catch (e) {
                console.warn('Dashboard data parse failed', e);
            }
            const approvedCount = typeof dashboardData.approvedCount === 'number' ? dashboardData.approvedCount : 0;
            const pendingCount = typeof dashboardData.pendingCount === 'number' ? dashboardData.pendingCount : 0;
            const otherCount = Math.max(0, (typeof dashboardData.totalPatients === 'number' ? dashboardData.totalPatients : 0) - approvedCount);
            const urgencyCounts = (typeof dashboardData.urgencyCounts === 'object' && dashboardData.urgencyCounts !== null) ? dashboardData.urgencyCounts : {};

            const isDark = document.body.classList.contains('dark-mode');
            const textColor = isDark ? '#ffffff' : '#37474f';
            const gridColor = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.05)';

            // Donut Chart - Patient Status
            const donutCtx = document.getElementById('statusDonut');
            if (donutCtx) {
                if (dashboardDonutInstance) dashboardDonutInstance.destroy();
                dashboardDonutInstance = new Chart(donutCtx, {
                    type: 'doughnut',
                    data: {
                        labels: ['Approved', 'Pending', 'Registered'],
                        datasets: [{
                            data: [approvedCount, pendingCount, otherCount],
                            backgroundColor: ['#0d47a1', '#1565c0', '#90caf9'],
                            borderWidth: 0,
                            hoverOffset: 8
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '70%',
                        animation: {
                            animateRotate: true,
                            duration: 1500
                        },
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    padding: 20,
                                    font: { family: 'Kumbh Sans', size: 12, weight: '600' },
                                    color: textColor
                                }
                            }
                        }
                    }
                });
            }

            // Bar Chart - Urgency Levels
            const barCtx = document.getElementById('urgencyBar');
            if (barCtx) {
                if (dashboardBarInstance) dashboardBarInstance.destroy();
                dashboardBarInstance = new Chart(barCtx, {
                    type: 'bar',
                    data: {
                        labels: ['Emergency', 'Normal'],
                        datasets: [{
                            label: 'Appointments',
                            data: [urgencyCounts.Emergency || 0, urgencyCounts.Normal || 0],
                            backgroundColor: ['#0d47a1', '#1565c0', '#90caf9'],
                            borderRadius: 8,
                            borderSkipped: false
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    stepSize: 1,
                                    font: { family: 'Kumbh Sans', size: 12 },
                                    color: textColor
                                },
                                grid: { color: gridColor }
                            },
                            x: {
                                ticks: {
                                    font: { family: 'Kumbh Sans', size: 12, weight: '600' },
                                    color: textColor
                                },
                                grid: { display: false }
                            }
                        },
                        plugins: {
                            legend: { display: false }
                        },
                        animation: {
                            duration: 1500
                        }
                    }
                });
            }
        }

        function rebuildDashboardCharts() {
            initDashboardCharts();
        }

        // Run animations and charts when page loads
        window.addEventListener('load', function () {
            animateCounters();
            initDashboardCharts();
        });


        // NOTE: #newApptModal (and everything inside it) is defined in the HTML
        // AFTER this </main> and after this <script> tag. Any element lookup here
        // that runs immediately (not deferred) will find nothing and silently no-op,
        // which is why this whole block is wrapped in DOMContentLoaded below.
        document.addEventListener('DOMContentLoaded', function () {

            const newApptBtn = document.getElementById('newAppointmentBtn');
            if (newApptBtn) {
                newApptBtn.addEventListener('click', () => {
                    document.getElementById('newApptModal').style.display = 'flex';
                    // Always reopen on the first step of the two-step wizard.
                    if (typeof window.admResetWizard === 'function') window.admResetWizard();
                });
            }

            function togglePatientMode() {
                const mode = document.querySelector('input[name="patientMode"]:checked').value;
                const existingSection = document.getElementById('existingPatientSection');
                const newSection = document.getElementById('newPatientSection');
                const select = document.getElementById('admPatientSelect');
                const firstName = document.getElementById('admFirstName');
                const lastName = document.getElementById('admLastName');

                if (mode === 'existing') {
                    existingSection.style.display = 'block';
                    newSection.style.display = 'none';
                    select.required = true;
                    if (firstName) firstName.required = false;
                    if (lastName) lastName.required = false;
                } else {
                    existingSection.style.display = 'none';
                    newSection.style.display = 'block';
                    select.required = false;
                    select.value = '';
                    document.getElementById('admPatientUid').value = '';
                    if (firstName) firstName.required = true;
                    if (lastName) lastName.required = true;
                }
            }



            // Patient search: type in #admPatientSearch -> query /search_patients -> fill #admPatientSelect
            (function () {
                const searchInput = document.getElementById('admPatientSearch');
                const select = document.getElementById('admPatientSelect');
                const uidField = document.getElementById('admPatientUid');
                if (!searchInput || !select) return;

                let debounceTimer = null;

                searchInput.addEventListener('input', function () {
                    const q = this.value.trim();
                    clearTimeout(debounceTimer);

                    if (q.length < 2) {
                        select.innerHTML = '<option value="">Select a patient</option>';
                        return;
                    }

                    debounceTimer = setTimeout(async () => {
                        try {
                            const res = await fetch('/search_patients', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ q: q })
                            });
                            const results = await res.json();

                            select.innerHTML = '';

                            if (!Array.isArray(results) || results.length === 0) {
                                select.innerHTML = '<option value="">No matching patients</option>';
                                return;
                            }

                            select.innerHTML = '<option value="">Select a patient</option>';
                            results.forEach(p => {
                                const opt = document.createElement('option');
                                opt.value = p.patient_id;
                                opt.dataset.accountUid = p.account_uid || '';
                                opt.textContent = p.name + (p.birthday ? ' (' + p.birthday + ')' : '');
                                select.appendChild(opt);
                            });
                        } catch (err) {
                            console.error('Patient search error:', err);
                            select.innerHTML = '<option value="">Search failed, try again</option>';
                        }
                    }, 300);
                });

                select.addEventListener('change', function () {
                    const selectedOption = this.options[this.selectedIndex];
                    uidField.value = selectedOption ? (selectedOption.dataset.accountUid || '') : '';
                });
            })();

            const admSex = document.getElementById('admSexSelect');
            const admWomen = document.getElementById('admWomenSection');
            if (admSex && admWomen) {
                admSex.addEventListener('change', function () {
                    const enable = this.value === 'Female';
                    admWomen.style.opacity = enable ? '1' : '0.4';
                    admWomen.querySelectorAll('input').forEach(el => el.disabled = !enable);
                });
            }

            // Signature pad
            (function () {
                const canvas = document.getElementById('admSignaturePad');
                if (!canvas) return;
                const ctx = canvas.getContext('2d');
                let drawing = false;
                ctx.strokeStyle = '#000';
                ctx.lineWidth = 2;
                ctx.lineCap = 'round';

                function pos(e) {
                    const r = canvas.getBoundingClientRect();
                    const x = e.touches ? e.touches[0].clientX : e.clientX;
                    const y = e.touches ? e.touches[0].clientY : e.clientY;
                    return { x: x - r.left, y: y - r.top };
                }
                function start(e) { e.preventDefault(); drawing = true; const p = pos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); }
                function move(e) { e.preventDefault(); if (!drawing) return; const p = pos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); }
                function end(e) { e.preventDefault(); drawing = false; }

                canvas.addEventListener('mousedown', start);
                canvas.addEventListener('touchstart', start);
                canvas.addEventListener('mousemove', move);
                canvas.addEventListener('touchmove', move);
                canvas.addEventListener('mouseup', end);
                canvas.addEventListener('touchend', end);
            })();

            function admClearSignature() {
                const canvas = document.getElementById('admSignaturePad');
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }

            function admToggleSpec(q, disable) {
                const el = document.getElementById('adm_' + q + '_spec');
                if (el) el.disabled = disable;
            }

            function admCombineDateTime() {
                const dateInput = document.getElementById('admApptDate');
                const timeInput = document.getElementById('admApptTime');
                const hiddenInput = document.getElementById('admApptDateHidden');
                if (dateInput && timeInput && hiddenInput && dateInput.value && timeInput.value) {
                    hiddenInput.value = dateInput.value + ' ' + timeInput.value;
                }
            }
            (function () {
                const dateInput = document.getElementById('admApptDate');
                const timeInput = document.getElementById('admApptTime');
                if (dateInput) {
                    // Admin may record past/already-done procedures, so no min date.
                    dateInput.addEventListener('change', function () {
                        admCombineDateTime();
                        const todayStr = new Date().toLocaleDateString('en-CA'); // YYYY-MM-DD, local time
                        const isPast = this.value && this.value < todayStr;
                        const info = isPast ? null : (window.__blockedSlotsMap || {})[this.value];
                        Array.from(timeInput.options).forEach(opt => opt.disabled = false);

                        if (info) {
                            if (info.full_day) {
                                showToast('The dentist is unavailable on this date' + (info.reason ? ' (' + info.reason + ')' : '') + '. Please pick another date.');
                                this.value = '';
                                timeInput.value = '';
                                return;
                            }
                            (info.blocked_times || []).forEach(t => {
                                const opt = Array.from(timeInput.options).find(o => o.value === t);
                                if (opt) opt.disabled = true;
                            });
                            if (timeInput.value && (info.blocked_times || []).includes(timeInput.value)) {
                                timeInput.value = '';
                            }
                        }
                    });
                }
                if (timeInput) timeInput.addEventListener('change', admCombineDateTime);
            })();

            const newApptForm = document.getElementById('newApptForm');
            if (newApptForm) {
                newApptForm.addEventListener('submit', async function (e) {
                    e.preventDefault();

                    // Consulting dentist is required before an appointment is
                    // created. The field lives on step 1, which is hidden while
                    // step 2 submits, so jump back there before focusing -
                    // requireDentistInput's own focus() is a no-op until then.
                    const dentistInput = document.getElementById('admDentistName');
                    if (!requireDentistInput(dentistInput)) {
                        if (typeof window.admResetWizard === 'function') {
                            window.admResetWizard();
                        }
                        if (dentistInput) dentistInput.focus();
                        showToast('Please select or type the consulting dentist.');
                        return;
                    }

                    const canvas = document.getElementById('admSignaturePad');
                    const blank = document.createElement('canvas');
                    blank.width = canvas.width; blank.height = canvas.height;
                    if (canvas.toDataURL() === blank.toDataURL()) {
                        showToast('Please provide the patient signature.');
                        return;
                    }

                    const mode = document.querySelector('input[name="patientMode"]:checked').value;
                    if (mode === 'existing' && !document.getElementById('admPatientSelect').value) {
                        showToast('Please select a patient.');
                        return;
                    }

                    admCombineDateTime();
                    if (!document.getElementById('admApptDateHidden').value) {
                        showToast('Please select an appointment date and time.');
                        return;
                    }

                    const formData = new FormData(e.target);
                    formData.append('patientMode', mode);
                    formData.append('signature', canvas.toDataURL());

                    try {
                        const res = await fetch('/admin/create_appointment', { method: 'POST', body: formData });
                        const result = await res.json();
                        if (result.success) {
                            location.reload();
                        } else {
                            showToast(result.message || 'Failed to create appointment.');
                        }
                    } catch (err) {
                        console.error('Create appointment error:', err);
                        showToast('Failed to create appointment. Please try again.');
                    }
                });
            }

            // ---------------------------------------------------------------
            // Two-step wizard for the appointment modal.
            // Step 1 holds the appointment fields, step 2 the informed consent
            // and the signature. Both live inside #newApptForm, so submitting
            // still posts one FormData with every field.
            // ---------------------------------------------------------------
            (function () {
                const modal = document.getElementById('newApptModal');
                const form = document.getElementById('newApptForm');
                const pages = modal ? Array.from(modal.querySelectorAll('.adm-page')) : [];
                const tabs = modal ? Array.from(modal.querySelectorAll('.adm-step')) : [];
                const backBtn = document.getElementById('admStepBack');
                const nextBtn = document.getElementById('admStepNext');
                const submitBtn = document.getElementById('admSubmitBtn');
                const statusText = document.getElementById('admStepStatus');
                const signDate = document.getElementById('admSignDate');
                const signName = document.getElementById('admSignPatientName');
                const TOTAL = pages.length || 1;

                if (!modal || !form || !pages.length || !backBtn || !nextBtn) return;

                function currentStep() {
                    const active = pages.find(function (p) { return p.classList.contains('is-active'); });
                    return active ? Number(active.getAttribute('data-adm-step')) || 1 : 1;
                }

                function showStep(step) {
                    /* Clamp: an out-of-range value would leave every page hidden and
                       strand the admin in a blank modal. */
                    step = Math.min(TOTAL, Math.max(1, step || 1));

                    pages.forEach(function (page) {
                        const on = Number(page.getAttribute('data-adm-step')) === step;
                        page.classList.toggle('is-active', on);
                        page.hidden = !on;
                    });

                    tabs.forEach(function (tab) {
                        const n = Number(tab.getAttribute('data-adm-step-tab'));
                        tab.classList.toggle('is-active', n === step);
                        tab.classList.toggle('is-done', n < step);
                    });

                    const last = step >= TOTAL;
                    backBtn.hidden = step <= 1;
                    nextBtn.hidden = last;
                    submitBtn.hidden = !last;
                    if (statusText) statusText.textContent = 'Step ' + step + ' of ' + TOTAL;

                    // The custom <select> panels are children of step 1 and must not
                    // stay open behind a page that is now hidden.
                    modal.querySelectorAll('.adm-select-panel, .custom-select-dropdown')
                        .forEach(function (panel) { panel.style.display = 'none'; });

                    // Same for the Dentist Name dropdown: its anchor lives on step 1,
                    // so leaving it open would float the popup over step 2.
                    if (typeof closeDentistMenu === 'function') closeDentistMenu();

                    // Keep the signature metadata in step with what was booked.
                    if (!last) return;

                    if (signDate) {
                        signDate.textContent = new Date().toLocaleDateString('en-US', {
                            year: 'numeric', month: 'long', day: 'numeric'
                        });
                    }
                    if (signName) {
                        const mode = document.querySelector('input[name="patientMode"]:checked');
                        const pick = document.getElementById('admPatientSelect');
                        let name = '';
                        if (mode && mode.value === 'existing') {
                            name = pick && pick.selectedIndex > 0 ? pick.options[pick.selectedIndex].text : '';
                        } else {
                            const first = document.getElementById('admFirstName');
                            const lastName = document.getElementById('admLastName');
                            name = [first && first.value, lastName && lastName.value]
                                .filter(Boolean).join(' ').trim();
                        }
                        signName.textContent = name || 'this patient';
                    }
                }

                /* Step 1 only. #admConsentCheck lives on step 2, so it is briefly
                   taken out of native validation - otherwise the browser would try
                   to focus a checkbox the admin cannot see yet. */
                function validateStepOne() {
                    const dateInput = document.getElementById('admApptDate');
                    const timeInput = document.getElementById('admApptTime');
                    const dentistInput = document.getElementById('admDentistName');

                    if (dateInput && !dateInput.value) {
                        showToast('Please select the appointment date.');
                        dateInput.focus();
                        return false;
                    }
                    if (timeInput && !timeInput.value) {
                        showToast('Please select the appointment time.');
                        timeInput.focus();
                        return false;
                    }
                    if (!requireDentistInput(dentistInput)) {
                        showToast('Please select or type the consulting dentist.');
                        return false;
                    }

                    const consent = document.getElementById('admConsentCheck');
                    const wasRequired = consent ? consent.required : false;
                    if (consent) consent.required = false;
                    const ok = form.reportValidity();
                    if (consent) consent.required = wasRequired;

                    if (!ok) {
                        showToast('Please complete the required fields before continuing.');
                        return false;
                    }
                    return true;
                }

                function advance() {
                    if (validateStepOne()) showStep(currentStep() + 1);
                }

                nextBtn.addEventListener('click', advance);
                backBtn.addEventListener('click', function () {
                    showStep(Math.max(1, currentStep() - 1));
                });

                /* Enter inside a step-1 field would otherwise submit the form while
                   the consent and signature are still hidden. Advance instead. */
                pages[0].addEventListener('keydown', function (e) {
                    if (e.key !== 'Enter' || e.shiftKey) return;
                    const tag = (e.target.tagName || '').toLowerCase();
                    if (tag === 'textarea' || tag === 'button') return;
                    e.preventDefault();
                    advance();
                });

                // Reopening the modal always starts from step 1.
                window.admResetWizard = function () { showStep(1); };
                showStep(1);
            })();

            // These are called from inline onchange/onclick attributes in the HTML,
            // which resolve names on `window` — so expose them explicitly since they
            // are now declared inside this DOMContentLoaded callback's local scope.
            window.togglePatientMode = togglePatientMode;
            window.admClearSignature = admClearSignature;
            window.admToggleSpec = admToggleSpec;
            window.admCombineDateTime = admCombineDateTime;

            // ---------------------------------------------------------------
            // Custom option panel for the selects inside the appointment modal.
            // The native <select> stays the real form control (so ids, values,
            // change events and validation keep working) - we only stop the
            // browser popup from opening and draw our own listbox instead.
            // ---------------------------------------------------------------
            (function () {
                // The custom listbox is used by more than one modal now. Each root
                // names the scroll container the panel should size itself against.
                const modal = document.getElementById('newApptModal');
                const roots = [
                    // Short side pane: flipping keeps the panel on screen.
                    { el: modal, scroller: '.adm-form-side', allowFlip: true },
                    // Tall scrolling bodies: always open downwards.
                    { el: document.getElementById('editPatientModal'), scroller: '.ep-body', allowFlip: false },
                    { el: document.getElementById('checkInfoModal'), scroller: '.ci-table-scroll', allowFlip: false }
                ].filter(function (r) { return r.el; });

                if (!roots.length) return;

                const CHECK_SVG =
                    '<svg class="adm-select-check" viewBox="0 0 24 24" fill="none" ' +
                    'stroke="currentColor" stroke-width="3" stroke-linecap="round" ' +
                    'stroke-linejoin="round" aria-hidden="true"><path d="M4.5 12.5l5 5 10-11"/></svg>';

                let openWrap = null;

                function menuOf(wrap) {
                    return wrap.admMenu || wrap.querySelector('.adm-select-menu');
                }

                // Put the panel back inside its wrapper. It is moved to <body> while
                // open (see positionMenu) so the modal's scroll container cannot
                // clip it, which is the same reason flatpickr's calendar escapes the
                // dialog. Restoring it keeps the DOM and the scoped CSS intact.
                function parkMenu(wrap) {
                    const menu = menuOf(wrap);
                    if (!menu) return;
                    menu.classList.remove('is-open', 'is-open-up');
                    // Already home - nothing to undo.
                    if (menu.parentNode === wrap) return;
                    menu.style.position = '';
                    menu.style.left = '';
                    menu.style.top = '';
                    menu.style.width = '';
                    menu.style.minWidth = '';
                    menu.style.maxWidth = '';
                    menu.style.maxHeight = '';
                    wrap.appendChild(menu);
                }

                function closeAll() {
                    if (!openWrap) return;
                    openWrap.classList.remove('is-open', 'is-open-up');
                    parkMenu(openWrap);
                    const s = openWrap.querySelector('select');
                    if (s) s.setAttribute('aria-expanded', 'false');
                    openWrap = null;
                }

                // Position the panel as a body-level popup. Because it no longer
                // lives inside the trigger's wrapper, it is anchored to the trigger's
                // viewport rect and simply cannot be clipped by the modal.
                function positionMenu(wrap, keepScroll) {
                    const select = wrap.querySelector('select');
                    const menu = menuOf(wrap);
                    if (!select || !menu) return;

                    // Only nudge the trigger into view when the panel is opening;
                    // doing it on every reposition would fight the user's scroll.
                    if (!keepScroll) wrap.scrollIntoView({ block: 'nearest' });

                    if (menu.parentNode !== document.body) {
                        document.body.appendChild(menu);
                    }
                    menu.classList.add('is-open');
                    menu.style.position = 'fixed';

                    const trigger = select.getBoundingClientRect();
                    const gap = 6;

                    const below = window.innerHeight - trigger.bottom - gap;
                    const above = trigger.top - gap;

                    const natural = menu.scrollHeight || 0;
                    const need = Math.min(natural, 230) || 150;

                    // Only flip when there is genuinely more room above, otherwise
                    // stay below and let the panel be short.
                    const mayFlip = below < need && above > below;
                    wrap.classList.toggle('is-open-up', mayFlip);
                    menu.classList.toggle('is-open-up', mayFlip);

                    // At least as wide as the trigger, but free to grow so long
                    // procedure names are readable, capped so it stays on screen.
                    const vw = window.innerWidth;
                    const maxW = Math.min(440, vw - 16);
                    menu.style.minWidth = trigger.width + 'px';
                    menu.style.width = 'max-content';
                    menu.style.maxWidth = maxW + 'px';

                    // Never let it hang off either edge.
                    let left = Math.max(8, trigger.left);
                    const width = menu.offsetWidth || trigger.width;
                    if (left + width > vw - 8) left = Math.max(8, vw - 8 - width);
                    menu.style.left = left + 'px';

                    if (mayFlip) {
                        const room = Math.max(110, Math.min(230, above));
                        menu.style.maxHeight = room + 'px';
                        menu.style.top = Math.max(gap, trigger.top - gap - room) + 'px';
                    } else {
                        const room = Math.max(110, Math.min(230, below));
                        menu.style.maxHeight = room + 'px';
                        menu.style.top = (trigger.bottom + gap) + 'px';
                    }
                }

                // Follow the trigger when the page or the table scrolls. The panel
                // is anchored to viewport coordinates, so without this it would
                // detach; and scrolling INSIDE the panel must be left alone.
                function repositionOpenMenu() {
                    if (!openWrap) return;
                    const menu = menuOf(openWrap);
                    const select = openWrap.querySelector('select');
                    if (!select) {
                        closeAll();
                        return;
                    }
                    const r = select.getBoundingClientRect();
                    // Trigger scrolled out of sight - nothing useful left to show.
                    if (r.bottom < 0 || r.top > window.innerHeight) {
                        closeAll();
                        return;
                    }
                    positionMenu(openWrap, true);
                }

                document.addEventListener('click', function (e) {
                    if (!openWrap) return;
                    // The panel is parked on <body> while open, so it is no longer
                    // inside the wrapper: a click on an option must NOT count as
                    // "outside" and close the list before the option is chosen.
                    const menu = menuOf(openWrap);
                    if (openWrap.contains(e.target)) return;
                    if (menu && menu.contains(e.target)) return;
                    closeAll();
                });
                // The panel is positioned against viewport coordinates, so a scroll
                // has to move it with its trigger. Scrolling inside the panel is
                // ignored: that is the panel's own long option list being read.
                window.addEventListener('scroll', function (e) {
                    if (!openWrap) return;
                    const menu = menuOf(openWrap);
                    if (menu && (e.target === menu || (menu.contains && menu.contains(e.target)))) return;
                    repositionOpenMenu();
                }, true);
                window.addEventListener('resize', function () {
                    if (openWrap) closeAll();
                });
                document.addEventListener('keydown', function (e) {
                    if (e.key === 'Escape' && openWrap) {
                        const s = openWrap.querySelector('select');
                        closeAll();
                        if (s) s.focus();
                    }
                });

                function render(wrap) {
                    const select = wrap.querySelector('select');
                    const menu = menuOf(wrap);
                    if (!select || !menu) return;

                    menu.textContent = '';
                    const options = Array.from(select.options);
                    if (!options.length) {
                        const empty = document.createElement('li');
                        empty.className = 'adm-select-empty';
                        empty.textContent = 'No options available';
                        menu.appendChild(empty);
                        return;
                    }

                    options.forEach(function (opt, index) {
                        const li = document.createElement('li');
                        li.className = 'adm-select-option';
                        li.setAttribute('role', 'option');
                        li.dataset.index = String(index);
                        li.textContent = opt.textContent.trim();
                        li.insertAdjacentHTML('beforeend', CHECK_SVG);
                        if (opt.disabled) li.classList.add('is-disabled');
                        if (opt.selected) li.classList.add('is-selected');
                        menu.appendChild(li);
                    });
                }

                function scrollActiveIntoView(menu) {
                    const active = menu.querySelector('.adm-select-option.is-selected') ||
                        menu.querySelector('.adm-select-option.is-active');
                    if (active) {
                        active.scrollIntoView({ block: 'nearest' });
                    }
                }

                function move(step) {
                    const wrap = openWrap;
                    if (!wrap) return;
                    const menu = menuOf(wrap);
                    const select = wrap.querySelector('select');
                    const items = Array.from(menu.querySelectorAll('.adm-select-option:not(.is-disabled)'));
                    if (!items.length) return;
                    const current = items.findIndex(i => i.classList.contains('is-active'));
                    const next = items[Math.min(items.length - 1, Math.max(0, (current === -1 ? 0 : current) + step))];
                    items.forEach(i => i.classList.remove('is-active'));
                    next.classList.add('is-active');
                    scrollActiveIntoView(menu);
                    select.setAttribute('aria-activedescendant', next.dataset.index);
                }

                // Enhance every <select> inside a container. Exposed so the
                // Treatment Information table can re-use this component for the rows
                // it builds on demand; the admEnhanced flag keeps it idempotent.
                function enhanceSelectsIn(container, scroller, allowFlip) {
                    if (!container) return;
                    container.querySelectorAll('select').forEach(function (select) {
                        if (select.dataset.admEnhanced === '1') return;
                        select.dataset.admEnhanced = '1';

                        const wrap = document.createElement('div');
                        wrap.className = 'adm-select';
                        wrap.admScroller = scroller || '.adm-form-side';
                        wrap.admAllowFlip = allowFlip;
                        select.parentNode.insertBefore(wrap, select);
                        wrap.appendChild(select);

                        const menu = document.createElement('ul');
                        menu.className = 'adm-select-menu';
                        menu.setAttribute('role', 'listbox');
                        wrap.appendChild(menu);
                        wrap.admMenu = menu;

                        select.setAttribute('aria-haspopup', 'listbox');
                        select.setAttribute('aria-expanded', 'false');
                        render(wrap);

                        // Keep the panel in sync when JS rewrites the options or the value.
                        new MutationObserver(function () {
                            render(wrap);
                            if (wrap === openWrap) {
                                positionMenu(wrap);
                                scrollActiveIntoView(menu);
                            }
                        }).observe(select, { childList: true, subtree: true });

                        select.addEventListener('change', function () {
                            Array.from(menu.querySelectorAll('.adm-select-option')).forEach(function (li) {
                                const opt = select.options[Number(li.dataset.index)];
                                li.classList.toggle('is-selected', !!(opt && opt.selected));
                            });
                        });

                        // Suppress the native popup and show ours instead.
                        select.addEventListener('mousedown', function (e) {
                            if (select.disabled) return;
                            e.preventDefault();
                            const isOpen = wrap.classList.contains('is-open');
                            closeAll();
                            if (!isOpen) {
                                wrap.classList.add('is-open');
                                select.setAttribute('aria-expanded', 'true');
                                openWrap = wrap;
                                render(wrap);
                                positionMenu(wrap);
                                scrollActiveIntoView(menu);
                            }
                            select.focus();
                        });

                        select.addEventListener('keydown', function (e) {
                            if (select.disabled) return;
                            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                                e.preventDefault();
                                if (!wrap.classList.contains('is-open')) {
                                    select.dispatchEvent(new Event('mousedown'));
                                }
                                move(e.key === 'ArrowDown' ? 1 : -1);
                            } else if (e.key === 'Enter' || e.key === ' ') {
                                if (wrap.classList.contains('is-open')) {
                                    e.preventDefault();
                                    const active = menu.querySelector('.adm-select-option.is-active');
                                    if (active) active.click();
                                }
                            }
                        });

                        menu.addEventListener('click', function (e) {
                            const li = e.target.closest('.adm-select-option');
                            if (!li || li.classList.contains('is-disabled')) return;
                            const index = Number(li.dataset.index);
                            const opt = select.options[index];
                            if (!opt) return;
                            select.selectedIndex = index;
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                            closeAll();
                            select.focus();
                        });
                    });
                }

                // Undo enhanceSelectsIn() for a subtree that is about to be removed.
                function destroySelectsIn(container) {
                    if (!container) return;
                    if (openWrap && container.contains(openWrap)) closeAll();
                    container.querySelectorAll('.adm-select').forEach(function (wrap) {
                        const select = wrap.querySelector('select');
                        const menu = menuOf(wrap);
                        // A panel left on <body> would otherwise outlive its row.
                        if (menu && menu.parentNode === document.body) {
                            menu.classList.remove('is-open', 'is-open-up');
                            document.body.removeChild(menu);
                        }
                        if (select) {
                            select.dataset.admEnhanced = '0';
                            if (select.parentNode === wrap) wrap.parentNode.insertBefore(select, wrap);
                        }
                        wrap.remove();
                    });
                }

                window.admEnhanceSelects = enhanceSelectsIn;
                window.admDestroySelects = destroySelectsIn;

                roots.forEach(function (root) {
                    enhanceSelectsIn(root.el, root.scroller, root.allowFlip);
                });

                // ---------------------------------------------------------------
                // Birthday + Date of Appointment: replace the native date popup
                // with the same flatpickr calendar the patient side already uses.
                // The original inputs keep their ids/names/values (Y-m-d) so the
                // existing submit and blocked-slot logic is unchanged.
                // ---------------------------------------------------------------
                if (typeof flatpickr === 'function') {
                    const baseOptions = {
                        dateFormat: 'Y-m-d',
                        altInput: true,
                        altFormat: 'F j, Y',
                        altInputClass: 'adm-date-alt',
                        className: 'adm-datepicker',
                        allowInput: false,
                        monthSelectorType: 'static'
                    };

                    const birthday = document.getElementById('admBirthday');
                    if (birthday) {
                        flatpickr('#admBirthday', Object.assign({}, baseOptions, {
                            maxDate: 'today'
                        }));
                    }

                    const apptDate = document.getElementById('admApptDate');
                    if (apptDate) {
                        flatpickr('#admApptDate', Object.assign({}, baseOptions, {
                            minDate: 'today',
                            onChange: function () {
                                admCombineDateTime();
                            }
                        }));
                    }

                    // The visible control is now flatpickr's alt input; keep the
                    // real inputs out of sight but still holding their values.
                    if (modal) {
                        modal.querySelectorAll('.adm-date-native').forEach(function (input) {
                            input.style.display = 'none';
                            input.removeAttribute('required');
                        });
                    }
                }
            })();
        });

