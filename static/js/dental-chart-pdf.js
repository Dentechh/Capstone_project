        async function downloadDentalChartPDF() {
            const { jsPDF } = window.jspdf;
            // Only the chart modal's own button is left; the dashboard-level
            // Download button was removed. Null-guarded because it is hidden and
            // restored around the render below.
            const btn = document.getElementById('modal-download-pdf-btn');
            const modalContent = document.getElementById('live-modal-chart-content');
            const chartSection = (modalContent && modalContent.querySelector('.dental-chart')) || document.querySelector('.dental-chart');

            if (!chartSection) {
                showToast('Dental chart not found. Please open the chart first.');
                return;
            }

            // Hide button so it won't appear in PDF
            if (btn) btn.style.display = 'none';

            // Show loading state
            const loadingMsg = document.createElement('div');
            loadingMsg.id = 'pdf-loading';
            loadingMsg.style.cssText = 'text-align:center; padding:8px; color:#555; font-size:14px;';
            loadingMsg.textContent = 'Generating PDF, please wait...';
            chartSection.parentElement.insertBefore(loadingMsg, chartSection);

            try {
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

                const imgData = canvas.toDataURL('image/png');

                // Use landscape A4 for wide dental charts
                const pdf = new jsPDF({
                    orientation: 'landscape',
                    unit: 'mm',
                    format: 'a4'
                });

                const pageW = pdf.internal.pageSize.getWidth();   // 297mm
                const pageH = pdf.internal.pageSize.getHeight();  // 210mm
                const margin = 8; // mm margin on all sides

                const usableW = pageW - margin * 2;
                const usableH = pageH - margin * 2;

                // Scale image proportionally to fit within usable area
                const imgRatio = canvas.width / canvas.height;
                const pageRatio = usableW / usableH;

                let finalW, finalH;
                if (imgRatio > pageRatio) {
                    // Chart is wider than page ratio — fit by width
                    finalW = usableW;
                    finalH = usableW / imgRatio;
                } else {
                    // Chart is taller — fit by height
                    finalH = usableH;
                    finalW = usableH * imgRatio;
                }

                // Center the image on the page
                const xOffset = margin + (usableW - finalW) / 2;
                const yOffset = margin + (usableH - finalH) / 2;

                pdf.addImage(imgData, 'PNG', xOffset, yOffset, finalW, finalH);

                // Optional: add page number or date footer
                const today = new Date().toLocaleDateString();
                pdf.setFontSize(8);
                pdf.setTextColor(150);
                pdf.text(`Generated: ${today}`, margin, pageH - 3);

                pdf.save('dental-record-chart.pdf');

            } catch (err) {
                console.error('PDF generation failed:', err);
                showToast('Could not generate PDF. Please try again.');
            } finally {
                if (btn) btn.style.display = '';
                const msg = document.getElementById('pdf-loading');
                if (msg) msg.remove();
            }
        }
