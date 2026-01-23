(function() {
    'use strict';

    function getGuestBookings() {
        var el = document.getElementById('guest-bookings-data');
        if (!el || !el.textContent) return {};
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            console.warn('reports: failed to parse guest-bookings-data', e);
            return {};
        }
    }

    function formatDuration(minutes) {
        if (minutes >= 60) {
            var h = Math.floor(minutes / 60);
            var m = minutes % 60;
            return m ? h + ' ч ' + m + ' мин' : h + ' ч';
        }
        return minutes + ' мин';
    }

    function formatPrice(val) {
        var n = parseFloat(val);
        return isNaN(n) ? '0,00' : n.toFixed(2).replace('.', ',');
    }

    function formatDate(iso) {
        if (!iso) return '—';
        var d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        var day = ('0' + d.getDate()).slice(-2);
        var month = ('0' + (d.getMonth() + 1)).slice(-2);
        var year = d.getFullYear();
        return day + '.' + month + '.' + year;
    }

    function escapeHtml(s) {
        if (s == null || s === undefined) return '';
        var div = document.createElement('div');
        div.textContent = String(s);
        return div.innerHTML;
    }

    function toggleMergeButton() {
        var btn = document.getElementById('reports-merge-btn');
        var cbs = document.querySelectorAll('.guest-merge-cb:checked');
        if (btn) btn.style.display = cbs.length >= 2 ? 'inline-block' : 'none';
    }

    function mergeGuests() {
        var cbs = document.querySelectorAll('.guest-merge-cb:checked');
        if (cbs.length < 2) return;
        var names = Array.from(cbs).map(function(c) { return c.value; });
        var data = getGuestBookings();
        var allBookings = [];
        var allRooms = [];
        var allServices = {};
        names.forEach(function(n) {
            var list = data[n] || [];
            list.forEach(function(b) {
                allBookings.push(b);
                if (b.guest_room_number) allRooms.push(b.guest_room_number);
                allServices[b.service_name] = true;
            });
        });
        allBookings.sort(function(a, b) {
            var da = a.date + 'T' + (a.time || '00:00');
            var db = b.date + 'T' + (b.time || '00:00');
            return da.localeCompare(db);
        });
        var visitCount = allBookings.length;
        var totalAmount = 0;
        var totalMinutes = 0;
        var firstDate = null;
        var lastDate = null;
        allBookings.forEach(function(b) {
            totalAmount += parseFloat(b.price) || 0;
            totalMinutes += parseInt(b.duration_minutes, 10) || 0;
            if (b.date) {
                if (!firstDate || b.date < firstDate) firstDate = b.date;
                if (!lastDate || b.date > lastDate) lastDate = b.date;
            }
        });
        var avgCheck = visitCount ? totalAmount / visitCount : 0;
        var rooms = Array.from(new Set(allRooms)).filter(Boolean);
        var services = Object.keys(allServices).sort();
        var mergedName = names.join(' + ');
        var roomDisplay = rooms.length ? rooms.join(', ') : '—';

        var tbody = document.getElementById('reports-guest-tbody');
        if (!tbody) return;

        var hideSet = new Set(names);
        tbody.querySelectorAll('tr.guest-row').forEach(function(tr) {
            var n = tr.getAttribute('data-guest-name');
            if (!n || !hideSet.has(n)) return;
            tr.classList.add('d-none');
            tr.querySelectorAll('.guest-merge-cb').forEach(function(cb) { cb.checked = false; });
            var next = tr.nextElementSibling;
            if (next && next.classList.contains('detail-row')) next.classList.add('d-none');
        });

        var detailId = 'guest-detail-merged-' + Date.now();

        var bookingsHtml = allBookings.map(function(b) {
            return '<tr><td>' + formatDate(b.date) + '</td><td>' + escapeHtml(b.time || '') +
                '</td><td>' + escapeHtml(b.service_variant) + '</td><td>' + escapeHtml(b.specialist) +
                '</td><td>' + escapeHtml(b.cabinet) + '</td><td>' + escapeHtml(b.status) +
                '</td><td class="text-end">' + formatPrice(b.price) + '</td></tr>';
        }).join('');

        var urlParams = new URLSearchParams(window.location.search);
        var startDate = urlParams.get('start_date') || '';
        var endDate = urlParams.get('end_date') || '';
        var guestNamesParam = encodeURIComponent(names.join(','));
        var downloadUrl = '/reports/download-guest/?start_date=' + encodeURIComponent(startDate) + 
                         '&end_date=' + encodeURIComponent(endDate) + 
                         '&guest_names=' + guestNamesParam;

        var detailHtml = '<tr class="detail-row guest-merged-detail">' +
            '<td colspan="11" class="p-0 border-0 align-top">' +
            '<div class="collapse" id="' + detailId + '">' +
            '<div class="p-3 bg-light">' +
            '<div class="d-flex justify-content-end mb-2">' +
            '<a href="' + downloadUrl + '" class="btn btn-sm btn-success guest-download-btn" data-merged-names="' + escapeHtml(JSON.stringify(names)) + '">' +
            '<i class="bi bi-download"></i> Скачать отчёт по гостю</a>' +
            '</div>' +
            '<table class="table table-sm table-bordered mb-0">' +
            '<thead><tr><th>Дата</th><th>Время</th><th>Услуга</th><th>Специалист</th><th>Кабинет</th><th>Статус</th><th class="text-end">Сумма</th></tr></thead>' +
            '<tbody>' + (bookingsHtml || '<tr><td colspan="7" class="text-muted">Нет визитов</td></tr>') + '</tbody>' +
            '</table></div></div></td></tr>';

        var mainHtml = '<tr class="guest-row guest-merged" data-merged-names="' + escapeHtml(JSON.stringify(names)) + '">' +
            '<td class="align-top"></td>' +
            '<td class="align-top">1</td>' +
            '<td class="align-top">' +
            '<div class="d-flex align-items-center gap-2">' +
            '<button type="button" class="btn btn-link p-0 text-start text-decoration-none guest-accordion-btn flex-grow-1" data-bs-toggle="collapse" data-bs-target="#' + detailId + '" aria-expanded="false">' +
            escapeHtml(mergedName) + ' <i class="bi bi-chevron-down guest-chevron"></i></button>' +
            '<a href="' + downloadUrl + '" class="btn btn-sm btn-success guest-download-btn" data-merged-names="' + escapeHtml(JSON.stringify(names)) + '" title="Скачать отчёт по гостю">' +
            '<i class="bi bi-download"></i></a>' +
            '</div>' +
            '</td>' +
            '<td class="align-top">' + escapeHtml(roomDisplay) + '</td>' +
            '<td class="text-end align-top"><span class="badge bg-primary">' + visitCount + '</span></td>' +
            '<td class="text-end align-top">' + formatPrice(totalAmount) + '</td>' +
            '<td class="text-end align-top">' + formatPrice(avgCheck) + '</td>' +
            '<td class="text-end align-top">' + formatDuration(totalMinutes) + '</td>' +
            '<td class="align-top">' + formatDate(firstDate) + '</td>' +
            '<td class="align-top">' + formatDate(lastDate) + '</td>' +
            '<td class="align-top">' + escapeHtml(services.join(', ')) + '</td>' +
            '</tr>';

        var frag = document.createDocumentFragment();
        var tmp = document.createElement('tbody');
        tmp.innerHTML = mainHtml + detailHtml;
        while (tmp.firstChild) frag.appendChild(tmp.firstChild);
        tbody.insertBefore(frag, tbody.firstChild);

        toggleMergeButton();
    }

    function setupAccordionChevrons() {
        document.addEventListener('show.bs.collapse', function(e) {
            if (!e.target || !e.target.id) return;
            var btn = document.querySelector('[data-bs-target="#' + e.target.id + '"]');
            var chev = btn && btn.querySelector('.guest-chevron');
            if (chev) {
                chev.classList.remove('bi-chevron-down');
                chev.classList.add('bi-chevron-up');
            }
        });
        document.addEventListener('hide.bs.collapse', function(e) {
            if (!e.target || !e.target.id) return;
            var btn = document.querySelector('[data-bs-target="#' + e.target.id + '"]');
            var chev = btn && btn.querySelector('.guest-chevron');
            if (chev) {
                chev.classList.remove('bi-chevron-up');
                chev.classList.add('bi-chevron-down');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        var tbody = document.getElementById('reports-guest-tbody');
        if (!tbody) return;

        tbody.addEventListener('change', function(e) {
            if (e.target && e.target.classList.contains('guest-merge-cb')) toggleMergeButton();
        });

        var mergeBtn = document.getElementById('reports-merge-btn');
        if (mergeBtn) mergeBtn.addEventListener('click', mergeGuests);

        toggleMergeButton();
        setupAccordionChevrons();
    });
})();
