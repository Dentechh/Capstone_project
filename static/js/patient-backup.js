/* Backup & Restore popup for the admin My Patients page. */
(function () {
    var modal = document.getElementById('backupModal');
    if (!modal) return;

    var $ = function (id) { return document.getElementById(id); };
    var csrf = function () { return ($('bkCsrf') || {}).value || ''; };
    var dlBtn = $('bkDownloadBtn'), fileIn = $('bkFile'), restoreBtn = $('bkRestoreBtn'),
        summary = $('bkSummary'), status = $('bkStatus');

    function say(msg, kind) {
        status.textContent = msg || '';
        status.className = 'bk-status' + (kind ? ' is-' + kind : '');
    }
    function line(parent, label, value) {
        var div = document.createElement('div');
        var b = document.createElement('strong');
        b.textContent = value;
        div.appendChild(b);
        div.appendChild(document.createTextNode(' ' + label));
        parent.appendChild(div);
    }
    function post(url, form) {
        form.append('csrf_token', csrf());
        return fetch(url, { method: 'POST', body: form, headers: { 'X-CSRFToken': csrf() } });
    }
    function errorOf(res) {
        return res.json().then(function (d) { return d.message || 'Something went wrong.'; },
            function () { return 'Something went wrong. Please try again.'; });
    }

    window.openBackupModal = function () {
        say('');
        summary.hidden = true;
        fileIn.value = '';
        restoreBtn.disabled = true;
        modal.style.display = 'flex';
    };
    window.closeBackupModal = function () { modal.style.display = 'none'; };
    modal.addEventListener('click', function (e) { if (e.target === modal) window.closeBackupModal(); });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.style.display === 'flex') window.closeBackupModal();
    });

    /* ---- downloads (backup file, Excel, Word) ---- */
    function download(url, fields, button, busyMsg, fallbackName) {
        var form = new FormData();
        Object.keys(fields).forEach(function (k) { form.append(k, fields[k]); });
        var all = [dlBtn, $('bkXlsxBtn'), $('bkDocxBtn')];
        all.forEach(function (b) { b.disabled = true; });
        say(busyMsg);
        post(url, form).then(function (res) {
            if (!res.ok) return errorOf(res).then(function (m) { throw new Error(m); });
            var cd = res.headers.get('Content-Disposition') || '';
            var m = /filename="([^"]+)"/.exec(cd);
            var name = m ? m[1] : fallbackName;
            return res.blob().then(function (blob) {
                var href = URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = href; a.download = name;
                document.body.appendChild(a); a.click(); a.remove();
                setTimeout(function () { URL.revokeObjectURL(href); }, 10000);
                say('Downloaded: ' + name, 'ok');
            });
        }).catch(function (err) {
            say(err.message || 'The download failed.', 'error');
        }).then(function () { all.forEach(function (b) { b.disabled = false; }); });
    }

    dlBtn.addEventListener('click', function () {
        download('/admin/backup/export', { include_charts: $('bkCharts').checked ? '1' : '0' },
            dlBtn, 'Preparing your backup. This can take a minute...', 'capizonda-backup.json');
    });
    $('bkXlsxBtn').addEventListener('click', function () {
        download('/admin/backup/report', { format: 'xlsx' }, this,
            'Preparing the Excel file...', 'capizonda-patient-records.xlsx');
    });
    $('bkDocxBtn').addEventListener('click', function () {
        download('/admin/backup/report', { format: 'docx' }, this,
            'Preparing the Word document...', 'capizonda-patient-records.docx');
    });

    /* ---- choose a file: show what it contains (writes nothing) ---- */
    fileIn.addEventListener('change', function () {
        summary.hidden = true;
        restoreBtn.disabled = true;
        if (!fileIn.files.length) { say(''); return; }
        var form = new FormData();
        form.append('backup_file', fileIn.files[0]);
        say('Reading the backup file...');
        post('/admin/backup/preview', form).then(function (res) {
            if (!res.ok) return errorOf(res).then(function (m) { throw new Error(m); });
            return res.json();
        }).then(function (d) {
            var s = d.summary;
            summary.textContent = '';
            var meta = document.createElement('div');
            meta.className = 'bk-meta';
            var when = s.created_at ? new Date(s.created_at).toLocaleString() : 'unknown date';
            meta.textContent = 'Backup made ' + when + (s.created_by ? ' by ' + s.created_by : '');
            summary.appendChild(meta);
            line(summary, 'patients will be restored', s.patients_new);
            line(summary, 'patient accounts will be restored', s.accounts_new);
            line(summary, 'treatment records will be restored', s.treatment_records_new);
            line(summary, 'appointments will be restored', s.appointments_new);
            var skipped = s.patients_skipped + s.accounts_skipped;
            if (skipped) {
                var note = document.createElement('div');
                note.className = 'bk-meta';
                note.textContent = s.patients_skipped + ' patients and ' + s.accounts_skipped +
                    ' accounts already exist and will be left untouched.';
                summary.appendChild(note);
            }
            summary.hidden = false;
            var nothing = !(s.patients_new || s.accounts_new);
            restoreBtn.disabled = nothing;
            say(nothing ? 'Everything in this file is already in the system. Nothing to restore.' : '', nothing ? 'ok' : '');
        }).catch(function (err) {
            say(err.message || 'Could not read the file.', 'error');
        });
    });

    /* ---- restore ---- */
    restoreBtn.addEventListener('click', function () {
        if (!fileIn.files.length) return;
        var form = new FormData();
        form.append('backup_file', fileIn.files[0]);
        restoreBtn.disabled = true; fileIn.disabled = true;
        say('Restoring... please keep this window open.');
        post('/admin/backup/import', form).then(function (res) {
            if (!res.ok) return errorOf(res).then(function (m) { throw new Error(m); });
            return res.json();
        }).then(function (d) {
            say(d.message + ' Reloading the list...', 'ok');
            if (typeof window.showToast === 'function') { try { window.showToast(d.message, 'success'); } catch (e) {} }
            setTimeout(function () { window.location.reload(); }, 1800);
        }).catch(function (err) {
            say(err.message || 'The restore failed.', 'error');
            restoreBtn.disabled = false;
        }).then(function () { fileIn.disabled = false; });
    });
})();