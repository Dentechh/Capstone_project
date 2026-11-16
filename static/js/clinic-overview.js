// Clinic Overview: for every dentist listed in Settings: a greeting banner,
// today's schedule and an activity summary (today + next 7 days).
// Dr. Capizonda (owner) comes first; the server sends the list in order.
(function () {
    var lastLoad = 0;
    var loading = false;

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined) n.textContent = text;
        return n;
    }

    function icon(name, cls) {
        var s = el('span', 'material-symbols-rounded' + (cls ? ' ' + cls : ''), name);
        s.setAttribute('aria-hidden', 'true');
        return s;
    }

    function stat(href, section, iconName, value, label) {
        var a = el('a', 'co-stat');
        a.href = href;
        a.addEventListener('click', function (e) { e.preventDefault(); showSection(section); });
        var ic = el('span', 'co-stat__icon');
        ic.setAttribute('aria-hidden', 'true');
        ic.appendChild(icon(iconName));
        var data = el('span', 'co-stat__data');
        data.appendChild(el('strong', '', String(value)));
        data.appendChild(el('span', '', label));
        a.appendChild(ic);
        a.appendChild(data);
        return a;
    }

    function scheduleCard(dentist) {
        var card = el('div', 'recent-activity co-schedule');
        var head = el('div', 'recent-header');
        var text = el('div', 'recent-header__text');
        text.appendChild(el('h3', '', "Today's Schedule"));
        text.appendChild(el('p', '', 'Accepted appointments for ' + dentist.name));
        head.appendChild(text);
        card.appendChild(head);

        var list = el('div', 'recent-list');
        if (!dentist.schedule.length) {
            var empty = el('div', 'recent-empty');
            empty.appendChild(icon('event_busy', 'recent-empty__icon'));
            empty.appendChild(el('p', '', 'No appointments today.'));
            list.appendChild(empty);
        }
        dentist.schedule.forEach(function (row) {
            var a = el('a', 'recent-item');
            a.href = '#section-WeeklyClients';
            a.addEventListener('click', function (e) { e.preventDefault(); showSection('WeeklyClients'); });
            var av = el('span', 'recent-avatar', (row.name || '?').charAt(0).toUpperCase());
            av.setAttribute('aria-hidden', 'true');
            var info = el('span', 'recent-info');
            info.appendChild(el('strong', '', row.name));
            info.appendChild(el('span', 'recent-sub', row.service || 'Service not specified'));
            var meta = el('span', 'recent-meta');
            meta.appendChild(el('span', 'recent-date co-time', row.time || 'No time'));
            a.appendChild(av);
            a.appendChild(info);
            a.appendChild(meta);
            list.appendChild(a);
        });
        card.appendChild(list);
        return card;
    }


    function miniStat(value, label) {
        var s = el('div', 'co-mini');
        s.appendChild(el('strong', '', String(value)));
        s.appendChild(el('span', '', label));
        return s;
    }

    function serviceChips(services) {
        var wrap = el('div', 'co-chips');
        if (!services || !services.length) {
            wrap.appendChild(el('span', 'co-muted', 'No services booked.'));
            return wrap;
        }
        services.forEach(function (s) {
            var chip = el('span', 'co-chip', s.name);
            chip.appendChild(el('b', '', String(s.count)));
            wrap.appendChild(chip);
        });
        return wrap;
    }

    function summaryPanel(title, sub, sum, extra) {
        var p = el('div', 'co-panel');
        var h = el('div', 'co-panel__head');
        h.appendChild(el('h4', '', title));
        h.appendChild(el('span', 'co-muted', sub));
        p.appendChild(h);

        var grid = el('div', 'co-minis');
        grid.appendChild(miniStat(sum.accepted, 'Accepted'));
        grid.appendChild(miniStat(sum.pending, 'Pending'));
        grid.appendChild(miniStat(sum.patients, 'Patients'));
        p.appendChild(grid);

        if (sum.first_time) {
            var span = sum.first_time === sum.last_time ? sum.first_time : sum.first_time + ' - ' + sum.last_time;
            p.appendChild(el('p', 'co-line', 'Appointment times: ' + span));
        }
        p.appendChild(el('p', 'co-label', 'Services'));
        p.appendChild(serviceChips(sum.services));
        if (extra) p.appendChild(extra);
        return p;
    }

    function weekDays(week) {
        var wrap = el('div', 'co-days');
        if (week.busiest_day) {
            wrap.appendChild(el('p', 'co-line', 'Busiest day: ' + week.busiest_day + ' (' + week.busiest_count + ' accepted)'));
        }
        var max = 1;
        (week.days || []).forEach(function (d) { if (d.accepted > max) max = d.accepted; });
        (week.days || []).forEach(function (d) {
            var row = el(d.schedule.length ? 'details' : 'div', 'co-day');
            var head = el(d.schedule.length ? 'summary' : 'div', 'co-day__head');
            head.appendChild(el('span', 'co-day__label', d.label));
            var bar = el('span', 'co-day__bar');
            var fill = el('i');
            fill.style.width = Math.round((d.accepted / max) * 100) + '%';
            bar.appendChild(fill);
            head.appendChild(bar);
            var txt = d.accepted + ' accepted';
            if (d.pending) txt += ', ' + d.pending + ' pending';
            head.appendChild(el('span', 'co-day__count', txt));
            row.appendChild(head);
            if (d.schedule.length) {
                var ul = el('ul', 'co-day__list');
                d.schedule.forEach(function (r) {
                    ul.appendChild(el('li', '', (r.time ? r.time + ' - ' : '') + r.name + (r.service ? ' (' + r.service + ')' : '')));
                });
                row.appendChild(ul);
            }
            wrap.appendChild(row);
        });
        return wrap;
    }

    function summaryCard(d, dateLabel) {
        var card = el('div', 'recent-activity co-summary');
        var head = el('div', 'recent-header');
        var text = el('div', 'recent-header__text');
        text.appendChild(el('h3', '', 'Activity Summary'));
        text.appendChild(el('p', '', 'Today and the next 7 days for ' + d.name));
        head.appendChild(text);
        card.appendChild(head);

        var grid = el('div', 'co-panels');
        var today = d.today || { accepted: 0, pending: 0, patients: 0, services: [] };
        var week = d.week || { accepted: 0, pending: 0, patients: 0, services: [], days: [] };
        grid.appendChild(summaryPanel('Today', dateLabel, today));
        grid.appendChild(summaryPanel('Next 7 Days', week.range_label || '', week, weekDays(week)));
        card.appendChild(grid);
        return card;
    }

    function dentistBlock(d, greeting, dateLabel) {
        var block = el('section', 'co-dentist');

        var banner = el('div', 'co-banner');
        var mark = el('img', 'co-banner__mark');
        mark.src = document.getElementById('coDentists').getAttribute('data-logo') || '';
        mark.alt = '';
        mark.setAttribute('aria-hidden', 'true');
        banner.appendChild(mark);

        var body = el('div', 'co-banner__text');
        body.appendChild(el('p', 'co-greeting', greeting + ','));
        var h = el('h2', 'co-name', d.name);
        if (d.owner) h.appendChild(el('span', 'co-owner', 'Clinic Owner'));
        else h.appendChild(el('span', 'co-owner co-owner--collab', 'Collaborating Dentist'));
        body.appendChild(h);
        body.appendChild(el('p', 'co-sub', 'Schedule today. ' + dateLabel));

        var stats = el('div', 'co-stats');
        stats.appendChild(stat('#section-WeeklyClients', 'WeeklyClients', 'event_available', d.accepted_today, 'Accepted Today'));
        stats.appendChild(stat('#section-appointments', 'appointments', 'hourglass_top', d.pending_requests, 'Pending Requests'));
        stats.appendChild(stat('#section-mypatients', 'mypatients', 'groups', d.total_patients || 0, 'Total Patients'));
        body.appendChild(stats);
        banner.appendChild(body);

        block.appendChild(banner);
        block.appendChild(scheduleCard(d));
        block.appendChild(summaryCard(d, dateLabel));
        return block;
    }

    function render(data) {
        var root = document.getElementById('coDentists');
        root.textContent = '';
        data.dentists.forEach(function (d) {
            root.appendChild(dentistBlock(d, data.greeting, data.date_label));
        });
    }

    function fail() {
        var root = document.getElementById('coDentists');
        if (root && !lastLoad) {
            root.textContent = 'Could not load the clinic overview. Please try again.';
        }
    }

    window.loadClinicOverview = function () {
        if (loading) return;
        loading = true;
        fetch('/admin/clinic_overview', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.success) { render(d); lastLoad = Date.now(); } else { fail(); }
            })
            .catch(fail)
            .then(function () { loading = false; });
    };

    // Called by showSection(): refetch at most once a minute.
    window.clinicOverviewOpened = function () {
        if (Date.now() - lastLoad > 60000) window.loadClinicOverview();
    };
})();