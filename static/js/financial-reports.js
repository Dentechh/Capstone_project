        // --- Financial Chart (Income Trend) ---
        let incomeChartInstance = null; // Store chart instance to destroy/update it

        // Shared state for whatever period is currently on screen -- read by
        // downloadFinancialReportPDF() so the report always matches the view,
        // without a separate fetch. Seeded from the server-rendered (all-time)
        // values, then kept in sync by loadFinancialChart() on every period switch.
        let financialReportState = { period: 'weekly', totalIncome: 0, totalOutstanding: 0, unpaidProcedures: 0 };
        (function seedFinancialReportState() {
            try {
                const raw = document.getElementById('financial-report-data');
                if (raw) financialReportState = Object.assign(financialReportState, JSON.parse(raw.textContent || '{}'));
            } catch (e) {
                console.warn('Financial report data seed failed', e);
            }
        })();

        // Which week / month / year is on screen for the Weekly, Monthly and
        // Yearly views. null month / year means "the current one".
        let financialNav = { period: 'weekly', week: 0, month: null, year: null, canPrev: false, canNext: false, minYear: null, maxYear: null, maxMonth: 12 };
        let financialChartRequestId = 0; // so a slow, older response can't overwrite a newer one

        function loadFinancialChart(period) {
            // Switching to a different period button starts at the current
            // week / month / year. Reloading the SAME period (e.g. the
            // light/dark theme toggle) keeps whatever was selected.
            if (period !== financialNav.period) {
                financialNav = { period: period, week: 0, month: null, year: null, canPrev: false, canNext: false,
                    minYear: financialNav.minYear, maxYear: financialNav.maxYear, maxMonth: financialNav.maxMonth };
            }

            // Update active button state
            document.querySelectorAll('.period-btn').forEach(btn => {
                btn.classList.remove('active');
                if (btn.dataset.period === period) btn.classList.add('active');
            });

            const query = new URLSearchParams({ period: period });
            if (period === 'weekly') query.set('week', financialNav.week);
            if (period === 'monthly' && financialNav.month) query.set('month', financialNav.month);
            if (period === 'yearly' && financialNav.year) query.set('year', financialNav.year);

            const requestId = ++financialChartRequestId;

            fetch(`/admin/financial_chart_data?${query.toString()}`)
                .then(response => response.json())
                .then(data => {
                    if (requestId !== financialChartRequestId) return; // a newer request is in flight
                    if (data.success) {
                        updateIncomeChart(data.labels, data.data, data.chart_type);
                        updateFinancialCards(data.total_income, data.total_outstanding, data.unpaid_procedures);

                        // Remember what the server actually resolved (it clamps
                        // out-of-range picks), then redraw the picker.
                        financialNav.week = data.week || 0;
                        financialNav.month = data.month || null;
                        financialNav.year = data.year || null;
                        financialNav.canPrev = !!data.can_prev;
                        financialNav.canNext = !!data.can_next;
                        financialNav.minYear = data.min_year;
                        financialNav.maxYear = data.max_year;
                        financialNav.maxMonth = data.max_month;
                        renderFinancialNav(period, data.range_label);

                        financialReportState = {
                            period: period,
                            totalIncome: data.total_income,
                            totalOutstanding: data.total_outstanding,
                            unpaidProcedures: data.unpaid_procedures,
                            rangeLabel: data.range_label || '',
                            asOfLabel: data.as_of_label || '',
                            selection: period === 'monthly' ? (data.month || '')
                                : period === 'yearly' ? String(data.year || '')
                                : period === 'weekly' ? (data.week ? 'week-' + data.week + '-back' : '')
                                : ''
                        };
                    }
                })
                .catch(err => console.error('Failed to load financial chart:', err));
        }

        // Shows the  < label >  picker for Weekly / Monthly / Yearly only.
        function renderFinancialNav(period, rangeLabel) {
            const nav = document.getElementById('financialNav');
            if (!nav) return;
            const hasPicker = period === 'weekly' || period === 'monthly' || period === 'yearly';
            nav.style.display = hasPicker ? 'flex' : 'none';
            if (!hasPicker) return;
            document.getElementById('finNavLabel').textContent = rangeLabel || '';
            document.getElementById('finNavPrev').disabled = !financialNav.canPrev;
            document.getElementById('finNavNext').disabled = !financialNav.canNext;

            // Weekly shows the text label; Monthly shows Month + Year
            // dropdowns; Yearly shows a Year dropdown.
            const label = document.getElementById('finNavLabel');
            const monthSel = document.getElementById('finMonthSel');
            const yearSel = document.getElementById('finYearSel');
            const showYear = period === 'monthly' || period === 'yearly';
            const showMonth = period === 'monthly';
            label.style.display = (showYear || showMonth) ? 'none' : '';
            monthSel.style.display = showMonth ? '' : 'none';
            yearSel.style.display = showYear ? '' : 'none';

            if (showYear && financialNav.minYear != null) {
                const selYear = period === 'monthly'
                    ? Number((financialNav.month || '').split('-')[0])
                    : financialNav.year;
                yearSel.innerHTML = '';
                for (let y = financialNav.maxYear; y >= financialNav.minYear; y--) { // newest first
                    const opt = document.createElement('option');
                    opt.value = y;
                    opt.textContent = y;
                    if (y === selYear) opt.selected = true;
                    yearSel.appendChild(opt);
                }
            }
            if (showMonth) {
                const parts = (financialNav.month || '').split('-');
                const selYear = Number(parts[0]);
                const selMonth = Number(parts[1]);
                monthSel.innerHTML = '';
                FIN_MONTH_NAMES.forEach(function (name, idx) {
                    const opt = document.createElement('option');
                    opt.value = idx + 1;
                    opt.textContent = name;
                    // months that haven't happened yet can't be picked
                    if (selYear === financialNav.maxYear && idx + 1 > financialNav.maxMonth) opt.disabled = true;
                    if (idx + 1 === selMonth) opt.selected = true;
                    monthSel.appendChild(opt);
                });
            }
        }

        const FIN_MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'];

        // Called when the Month or Year dropdown changes.
        function financialNavPick() {
            const n = financialNav;
            const yearSel = document.getElementById('finYearSel');
            const monthSel = document.getElementById('finMonthSel');
            if (n.period === 'yearly') {
                n.year = Number(yearSel.value);
            } else if (n.period === 'monthly') {
                const y = Number(yearSel.value);
                let m = Number(monthSel.value);
                // picking the current year while on a later month snaps to the latest valid month
                if (y === n.maxYear && m > n.maxMonth) m = n.maxMonth;
                n.month = y + '-' + String(m).padStart(2, '0');
            } else {
                return;
            }
            loadFinancialChart(n.period);
        }

        // dir = -1 goes to the previous week / month / year, +1 to the next.
        function financialNavStep(dir) {
            const n = financialNav;
            if ((dir < 0 && !n.canPrev) || (dir > 0 && !n.canNext)) return;

            if (n.period === 'weekly') {
                n.week = Math.max(0, n.week - dir); // "previous" = further back in time
            } else if (n.period === 'monthly' && n.month) {
                const parts = n.month.split('-');
                const d = new Date(Number(parts[0]), Number(parts[1]) - 1 + dir, 1);
                n.month = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
            } else if (n.period === 'yearly' && n.year) {
                n.year = n.year + dir;
            } else {
                return;
            }
            loadFinancialChart(n.period);
        }

        function updateFinancialCards(totalIncome, totalOutstanding, unpaidProcedures) {
            const incomeEl = document.getElementById('finTotalIncome');
            const outstandingEl = document.getElementById('finTotalOutstanding');
            const unpaidEl = document.getElementById('finUnpaidProcedures');

            if (incomeEl && typeof totalIncome === 'number') {
                incomeEl.textContent = '₱' + totalIncome.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }
            if (outstandingEl && typeof totalOutstanding === 'number') {
                outstandingEl.textContent = '₱' + totalOutstanding.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }
            if (unpaidEl && typeof unpaidProcedures === 'number') {
                unpaidEl.textContent = unpaidProcedures;
            }
        }

        function updateIncomeChart(labels, dataValues, chartType) {
            const ctx = document.getElementById('incomeChart').getContext('2d'); // Ensure ID matches your canvas

            if (incomeChartInstance) {
                incomeChartInstance.destroy();
            }

            const isDark = document.body.classList.contains('dark-mode');
            const lineColor = '#42A5F6';
            const fillColor = isDark ? 'rgba(66, 165, 246, 0.15)' : 'rgba(66, 165, 246, 0.1)';
            const textColor = '#42A5F6';
            const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)';

            // Overall (one point per year) reads better as bars; everything
            // else is the same line chart as before.
            const isBar = chartType === 'bar';

            incomeChartInstance = new Chart(ctx, {
                type: isBar ? 'bar' : 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Revenue (₱)',
                        data: dataValues,
                        borderColor: lineColor, // Matches unpaid procedures number color
                        backgroundColor: isBar ? 'rgba(66, 165, 246, 0.55)' : fillColor,
                        fill: true,
                        tension: 0.4,
                        cubicInterpolationMode: 'monotone',
                        borderRadius: isBar ? 8 : 0,
                        maxBarThickness: 60
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: textColor, // Matches unpaid procedures number color
                                callback: function (value) { return '₱' + value; }
                            },
                            grid: {
                                color: gridColor
                            }
                        },
                        x: {
                            ticks: {
                                color: textColor
                            },
                            grid: {
                                color: gridColor
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: textColor
                            }
                        }
                    }
                }
            });
        }

        // --- Procedure Charts ---
        let procCountChartInstance = null;
        let procRevenueChartInstance = null;

        function loadProcedureCharts(period) {
            // Update active button state for procedure buttons
            document.querySelectorAll('.proc-period-btn').forEach(btn => {
                btn.classList.remove('active');
                if (btn.dataset.period === period) btn.classList.add('active');
            });

            fetch(`/admin/procedure_chart_data?period=${period}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateBarChart('procedureCountChart', data.counts.labels, data.counts.data, 'Count', procCountChartInstance, (instance) => procCountChartInstance = instance, '#64B5F6');
                        updateBarChart('procedureRevenueChart', data.revenue.labels, data.revenue.data, 'Revenue (₱)', procRevenueChartInstance, (instance) => procRevenueChartInstance = instance, '#42A5F6');
                    }
                });
        }

        function updateBarChart(canvasId, labels, dataValues, labelName, currentInstance, setInstance, barColor) {
            const ctx = document.getElementById(canvasId).getContext('2d'); // Ensure IDs match your canvases

            if (currentInstance) {
                currentInstance.destroy();
            }

            const isDark = document.body.classList.contains('dark-mode');
            const resolvedColor = barColor || '#1e40af';
            const textColor = isDark ? '#ffffff' : '#37474f';
            const gridColor = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.05)';

            const newChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: labelName,
                        data: dataValues,
                        backgroundColor: resolvedColor
                    }]
                },
                options: {
                    indexAxis: 'y', // Horizontal bar chart
                    responsive: true,
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: { color: textColor },
                            grid: { color: gridColor }
                        },
                        y: {
                            ticks: { color: textColor },
                            grid: { display: false }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: textColor
                            }
                        }
                    }
                }
            });
            setInstance(newChart);
        }

        // Initialize charts on load
        document.addEventListener('DOMContentLoaded', () => {
            loadFinancialChart('weekly'); // Default for income
            loadProcedureCharts('overall'); // Default for procedures (shows all time)
        });

        // --- Downloadable Financial Report (PDF) ---
        const FINANCIAL_PERIOD_LABELS = {
            today: 'Today',
            weekly: 'Weekly',
            monthly: 'Monthly',
            yearly: 'Yearly',
            overall: 'All Time (by year)'
        };

        function formatPesoForPdf(value) {
            // jsPDF's built-in fonts (Helvetica/Times/Courier) only cover the
            // WinAnsi/Latin-1 character set, which does NOT include the ₱ Peso
            // sign (U+20B1) -- that's what was rendering as garbled "±" text.
            // Using "PHP" here (ASCII-only) keeps the summary text readable
            // and consistent. The ₱ symbol on-screen and inside the chart image
            // is unaffected -- those are drawn by the browser's own fonts.
            const num = typeof value === 'number' ? value : parseFloat(String(value).replace(/,/g, '')) || 0;
            return 'PHP ' + num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        async function downloadFinancialReportPDF() {
            const { jsPDF } = window.jspdf;
            const btn = document.getElementById('download-financial-report-btn');
            const chartCanvas = document.getElementById('incomeChart');

            if (!chartCanvas) {
                showToast('Income chart not found.');
                return;
            }

            if (btn) btn.disabled = true;

            try {
                // Chart.js draws straight onto a <canvas>, so it can be exported
                // directly -- no html2canvas needed here. We flatten it onto a
                // white background first so the transparent areas of the chart
                // don't come out black in the PDF.
                const flat = document.createElement('canvas');
                flat.width = chartCanvas.width;
                flat.height = chartCanvas.height;
                const fctx = flat.getContext('2d');
                fctx.fillStyle = '#ffffff';
                fctx.fillRect(0, 0, flat.width, flat.height);
                fctx.drawImage(chartCanvas, 0, 0);
                const chartImg = flat.toDataURL('image/png', 1.0);

                const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
                const pageW = pdf.internal.pageSize.getWidth();
                const margin = 15;
                let y = margin;

                const basePeriodLabel = FINANCIAL_PERIOD_LABELS[financialReportState.period] || financialReportState.period;
                // e.g. "Monthly - September 2026", "Yearly - 2025"
                const periodLabel = financialReportState.rangeLabel
                    ? `${basePeriodLabel} - ${financialReportState.rangeLabel}`
                    : basePeriodLabel;

                pdf.setFontSize(18);
                pdf.setTextColor(13, 71, 161);
                pdf.text('Capizonda Dental Clinic', margin, y);
                y += 8;

                pdf.setFontSize(13);
                pdf.setTextColor(40, 40, 40);
                pdf.text('Financial Report', margin, y);
                y += 8;

                pdf.setFontSize(10);
                pdf.setTextColor(90, 90, 90);
                pdf.text(`Period: ${periodLabel}`, margin, y);
                pdf.text(`Generated: ${new Date().toLocaleString()}`, pageW - margin, y, { align: 'right' });
                y += 10;

                pdf.setDrawColor(220, 220, 220);
                pdf.line(margin, y, pageW - margin, y);
                y += 12;

                const summaryItems = [
                    ['Total Income Collected', formatPesoForPdf(financialReportState.totalIncome)],
                    ['Outstanding Balance', formatPesoForPdf(financialReportState.totalOutstanding)],
                    ['Unpaid Procedures', String(financialReportState.unpaidProcedures || 0)]
                ];
                const colWidth = (pageW - margin * 2) / summaryItems.length;
                summaryItems.forEach(([label, value], i) => {
                    const x = margin + colWidth * i;
                    pdf.setFontSize(9);
                    pdf.setTextColor(90, 90, 90);
                    pdf.text(label, x, y);
                    pdf.setFontSize(14);
                    pdf.setTextColor(13, 71, 161);
                    pdf.text(value, x, y + 7);
                });
                if (financialReportState.asOfLabel) {
                    pdf.setFontSize(8);
                    pdf.setTextColor(120, 120, 120);
                    pdf.text(`Outstanding Balance and Unpaid Procedures cover all unpaid items as of ${financialReportState.asOfLabel}, not only the selected period.`, margin, y + 14);
                }
                y += 22;

                pdf.setDrawColor(220, 220, 220);
                pdf.line(margin, y, pageW - margin, y);
                y += 10;

                pdf.setFontSize(11);
                pdf.setTextColor(40, 40, 40);
                pdf.text('Income Trend', margin, y);
                y += 6;

                const usableW = pageW - margin * 2;
                const imgRatio = chartCanvas.width / chartCanvas.height;
                const imgH = usableW / imgRatio;
                pdf.addImage(chartImg, 'PNG', margin, y, usableW, imgH);
                y += imgH + 14;

                drawUnpaidSectionInPdf(pdf, y, margin);

                const dateStamp = new Date().toISOString().slice(0, 10);
                const selectionPart = financialReportState.selection ? `-${financialReportState.selection}` : '';
                pdf.save(`financial-report-${financialReportState.period}${selectionPart}-${dateStamp}.pdf`);
            } catch (err) {
                console.error('Financial report PDF generation failed:', err);
                showToast('Could not generate the report. Please try again.');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        // --- Unpaid Procedures table (Financial Reports) ---
        // Own filters; deliberately independent of the Today/Weekly/... buttons,
        // which only drive the three cards and the Income Trend chart. The server
        // sends every unpaid procedure once and filtering happens here, so
        // changing a filter costs no request and no Firestore read.
        let unpaidRows = [];
        let unpaidRange = 'all';

        const UNPAID_RANGE_LABELS = {
            all: 'All',
            today: 'Today',
            '7d': 'Last 7 days',
            '30d': 'Last 30 days',
            '12m': 'Last 12 months'
        };

        function unpaidEsc(value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function unpaidPeso(n) {
            return '\u20B1' + (Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function unpaidParseDate(str) {
            // Procedure dates are stored as YYYY-MM-DD. Parsed as a LOCAL date so
            // "today" and the day counts follow the clinic's own clock.
            const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(str || ''));
            if (!m) return null;
            return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
        }

        function unpaidFormatDate(str) {
            const d = unpaidParseDate(str);
            if (!d) return '\u2014';
            return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
        }

        function unpaidInRange(row, range) {
            if (range === 'all') return true;
            const d = unpaidParseDate(row.date);
            if (!d) return false; // no usable date: only shown under "All"
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            let start;
            if (range === 'today') {
                start = today;
            } else if (range === '7d') {
                start = new Date(today); start.setDate(start.getDate() - 6);
            } else if (range === '30d') {
                start = new Date(today); start.setDate(start.getDate() - 29);
            } else if (range === '12m') {
                start = new Date(today.getFullYear(), today.getMonth() - 11, 1);
            } else {
                return true;
            }
            return d >= start && d <= today;
        }

        function getUnpaidFiltered() {
            const searchEl = document.getElementById('unpaidSearch');
            const q = searchEl ? searchEl.value.trim().toLowerCase() : '';
            return unpaidRows.filter(r =>
                unpaidInRange(r, unpaidRange) &&
                (!q || String(r.patient_name || '').toLowerCase().includes(q))
            );
        }

        function renderUnpaidTable() {
            const body = document.getElementById('unpaidTableBody');
            const footLabel = document.getElementById('unpaidFootLabel');
            const footTotal = document.getElementById('unpaidFootTotal');
            if (!body) return;

            const rows = getUnpaidFiltered();
            const total = rows.reduce((sum, r) => sum + (Number(r.balance) || 0), 0);

            if (!rows.length) {
                body.innerHTML = '<tr><td colspan="7" class="unpaid-empty">No unpaid procedures found.</td></tr>';
            } else {
                body.innerHTML = rows.map(r => {
                    const proc = unpaidEsc(r.procedure || '\u2014') +
                        (r.tooth ? ' <span style="color:#78909c;">(Tooth ' + unpaidEsc(r.tooth) + ')</span>' : '');
                    return '<tr>' +
                        '<td>' + unpaidEsc(r.patient_name) + '</td>' +
                        '<td>' + proc + '</td>' +
                        '<td>' + unpaidEsc(unpaidFormatDate(r.date)) + '</td>' +
                        '<td>' + unpaidEsc(r.dentist || '\u2014') + '</td>' +
                        '<td class="num">' + unpaidPeso(r.value) + '</td>' +
                        '<td class="num">' + unpaidPeso(r.paid) + '</td>' +
                        '<td class="num unpaid-balance-cell">' + unpaidPeso(r.balance) + '</td>' +
                        '</tr>';
                }).join('');
            }

            if (footLabel) footLabel.textContent = 'Total balance (' + rows.length + ' unpaid procedure' + (rows.length === 1 ? '' : 's') + ')';
            if (footTotal) footTotal.textContent = unpaidPeso(total);
        }

        function setUnpaidRange(range) {
            unpaidRange = range;
            document.querySelectorAll('#unpaidRangeGroup .unpaid-filter-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.range === range);
            });
            renderUnpaidTable();
        }

        function loadUnpaidProcedures() {
            const body = document.getElementById('unpaidTableBody');
            if (!body) return;
            fetch('/admin/unpaid_procedures')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        unpaidRows = data.rows || [];
                        renderUnpaidTable();
                    } else {
                        body.innerHTML = '<tr><td colspan="7" class="unpaid-empty">Could not load unpaid procedures.</td></tr>';
                    }
                })
                .catch(() => {
                    body.innerHTML = '<tr><td colspan="7" class="unpaid-empty">Could not load unpaid procedures.</td></tr>';
                });
        }

        function drawUnpaidSectionInPdf(pdf, startY, margin) {
            const pageW = pdf.internal.pageSize.getWidth();
            const pageH = pdf.internal.pageSize.getHeight();
            const rows = getUnpaidFiltered();
            const total = rows.reduce((sum, r) => sum + (Number(r.balance) || 0), 0);

            // [header, width in mm, right-aligned?]
            const cols = [
                ['Patient', 46, false],
                ['Procedure', 46, false],
                ['Date', 24, false],
                ['Total', 21, true],
                ['Paid', 21, true],
                ['Balance', 22, true]
            ];
            const lineH = 4.2;
            let y = startY;

            const searchEl = document.getElementById('unpaidSearch');
            const q = searchEl ? searchEl.value.trim() : '';
            const filterText = 'Filter: ' + (UNPAID_RANGE_LABELS[unpaidRange] || unpaidRange) + (q ? ' / Search: "' + q + '"' : '');

            function drawHeader() {
                pdf.setFontSize(9);
                pdf.setTextColor(90, 90, 90);
                pdf.setFont(undefined, 'bold');
                let x = margin;
                cols.forEach(([label, w, right]) => {
                    pdf.text(label, right ? x + w - 1 : x + 1, y, right ? { align: 'right' } : undefined);
                    x += w;
                });
                pdf.setFont(undefined, 'normal');
                y += 2;
                pdf.setDrawColor(200, 200, 200);
                pdf.line(margin, y, pageW - margin, y);
                y += 5;
            }

            if (y + 40 > pageH - margin) { pdf.addPage(); y = margin; }

            pdf.setFontSize(11);
            pdf.setTextColor(40, 40, 40);
            pdf.text('Unpaid Procedures', margin, y);
            pdf.setFontSize(9);
            pdf.setTextColor(90, 90, 90);
            pdf.text(filterText, pageW - margin, y, { align: 'right' });
            y += 7;

            if (!rows.length) {
                pdf.setFontSize(10);
                pdf.text('No unpaid procedures found.', margin, y);
                return;
            }

            drawHeader();

            rows.forEach(r => {
                const procText = (r.procedure || '-') + (r.tooth ? ' (Tooth ' + r.tooth + ')' : '');
                const nameLines = pdf.splitTextToSize(String(r.patient_name || ''), cols[0][1] - 2);
                const procLines = pdf.splitTextToSize(procText, cols[1][1] - 2);
                const nLines = Math.max(nameLines.length, procLines.length);
                const rowH = nLines * lineH + 2;

                if (y + rowH > pageH - margin - 10) {
                    pdf.addPage();
                    y = margin;
                    drawHeader();
                }

                pdf.setFontSize(9);
                pdf.setTextColor(40, 40, 40);
                let x = margin;
                pdf.text(nameLines, x + 1, y); x += cols[0][1];
                pdf.text(procLines, x + 1, y); x += cols[1][1];
                pdf.text(unpaidFormatDate(r.date), x + 1, y); x += cols[2][1];
                pdf.text(formatPesoForPdf(r.value), x + cols[3][1] - 1, y, { align: 'right' }); x += cols[3][1];
                pdf.text(formatPesoForPdf(r.paid), x + cols[4][1] - 1, y, { align: 'right' }); x += cols[4][1];
                pdf.setFont(undefined, 'bold');
                pdf.text(formatPesoForPdf(r.balance), x + cols[5][1] - 1, y, { align: 'right' });
                pdf.setFont(undefined, 'normal');

                y += rowH;
                pdf.setDrawColor(235, 235, 235);
                pdf.line(margin, y - 3, pageW - margin, y - 3);
            });

            if (y + 12 > pageH - margin) { pdf.addPage(); y = margin; }
            y += 2;
            pdf.setDrawColor(150, 150, 150);
            pdf.line(margin, y, pageW - margin, y);
            y += 6;
            pdf.setFontSize(10);
            pdf.setFont(undefined, 'bold');
            pdf.setTextColor(13, 71, 161);
            pdf.text('Total balance (' + rows.length + ')', margin + 1, y);
            pdf.text(formatPesoForPdf(total), pageW - margin - 1, y, { align: 'right' });
            pdf.setFont(undefined, 'normal');
        }

        (function () {
            const _fetch = window.fetch;
            window.fetch = function (input, opts) {
                opts = opts || {};
                const url = typeof input === 'string' ? input : ((input && input.url) || '');
                const sameOrigin = url.startsWith('/') || url.startsWith(location.origin);
                const method = (opts.method || (input && input.method) || 'GET').toUpperCase();
                if (sameOrigin && method !== 'GET' && method !== 'HEAD') {
                    const meta = document.querySelector('meta[name="csrf-token"]');
                    opts.headers = new Headers(opts.headers || {});
                    if (meta) opts.headers.set('X-CSRFToken', meta.content);
                }
                return _fetch.call(this, input, opts);
            };
        })();


