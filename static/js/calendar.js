    let calendar;
    let currentView = 'timeGridDay';
    let currentResourceType = 'specialist';
    let canManageClosures = false;
    let copyShortcutsEnabled = false;
    const SUPPORTED_VIEWS = ['dayGridMonth', 'timeGridWeek', 'timeGridThreeDay', 'timeGridDay'];
    const WIDTH_MODE_STORAGE_KEY = 'calendarWidthMode';
    const VIEW_STORAGE_KEY = 'calendarView';
    const DATE_STORAGE_KEY = 'calendarDate';
    let currentWidthMode = 'standard'; // standard | wide | fullscreen
    let currentDate = null;
    let quickBookingModal = null;
    let closureFeedUrl = '';
    let closureCreateUrl = '';
    const closureDeleteBaseUrl = "/calendar/closures/";
    let duplicateBookingUrl = '';
    const quickBookingFormEl = document.getElementById('quickBookingForm');
    const quickRecurrenceToggle = document.getElementById('quick_recurrence_enabled');
    const quickRecurrenceSettings = document.querySelector('[data-role="quick-recurrence-settings"]');
    const quickRecurrenceFrequency = document.getElementById('quick_recurrence_frequency');
    const quickRecurrenceIntervalLabel = document.querySelector('[data-role="quick-recurrence-interval-label"]');
    const quickRecurrenceWeekdaysBlock = document.querySelector('[data-role="quick-recurrence-weekdays"]');
    const quickRecurrenceEndType = document.getElementById('quick_recurrence_end_type');
    const quickRecurrenceCountField = document.querySelector('[data-role="quick-recurrence-count-field"]');
    const quickRecurrenceUntilField = document.querySelector('[data-role="quick-recurrence-until-field"]');
    const quickRecurrenceOccurrences = document.getElementById('quick_recurrence_occurrences');
    const quickRecurrenceExcludedDisplay = document.querySelector('[data-role="quick-recurrence-excluded-display"]');
    const quickRecurrenceExcludedHidden = document.getElementById('quick_recurrence_excluded_dates');
    let bookingEditModal;
    const bookingEditModalEl = document.getElementById('bookingEditModal');
    const bookingEditModalBody = document.getElementById('bookingEditModalBody');
    const closureFormEl = document.getElementById('cabinetClosureForm');
    const closureModalEl = document.getElementById('cabinetClosureModal');
    const closureDeleteModalEl = document.getElementById('closureDeleteModal');
    const closureDeleteCabinetNameEl = document.getElementById('closureDeleteCabinetName');
    const closureDeletePeriodEl = document.getElementById('closureDeletePeriod');
    const confirmClosureDeleteBtn = document.getElementById('confirmClosureDeleteBtn');
    let cabinetClosureModal;
    let closureDeleteModal;
    let pendingClosureDeleteId = null;
    let closureStartPicker = null;
    let closureEndPicker = null;
    let hoveredBookingEvent = null;
    let copiedBookingBuffer = null;
    let lastSlotSelection = null;
    let copyPasteHandlerAttached = false;
    let resultModalInstance = null;
    let resultModalHideTimeout = null;
    const isMacPlatform = typeof navigator !== 'undefined' && navigator.platform ? navigator.platform.toUpperCase().includes('MAC') : false;

    // Получаем CSRF token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');

    document.addEventListener('DOMContentLoaded', function() {
        // Читаем data-атрибуты из DOM
        const calendarPage = document.getElementById("calendar-page");
        if (calendarPage) {
            canManageClosures = calendarPage.dataset.canManageClosures === "true";
            copyShortcutsEnabled = calendarPage.dataset.copyShortcutsEnabled === "true";
            closureFeedUrl = calendarPage.dataset.closureFeedUrl || '';
            closureCreateUrl = calendarPage.dataset.closureCreateUrl || '';
            duplicateBookingUrl = calendarPage.dataset.duplicateBookingUrl || '';
        }
        
        restoreWidthMode();
        applyWidthModeClass();
        restoreViewState();
        updateViewSwitcherButtons();
        initCalendar();
        if (copyShortcutsEnabled) {
            initCopyPasteShortcuts();
        }
        updateWidthButton();
        initQuickBookingModal();
        initCabinetClosureModals();
        attachNavigationControls();
        updateCalendarTitle();
    });

    function initCalendar() {
        const calendarEl = document.getElementById('calendar');

        const eventSources = [
            {
                url: '/calendar/feed/',
            }
        ];
        if (canManageClosures) {
            eventSources.push({
                url: closureFeedUrl,
                className: 'cabinet-closure-event',
            });
        }

        calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: currentView,
            initialDate: currentDate || undefined,
            locale: 'ru',
            headerToolbar: false,
            nowIndicator: true,
            views: {
                timeGridThreeDay: {
                    type: 'timeGrid',
                    duration: { days: 3 }
                }
            },
            // Адаптивность для мобильных устройств
            height: 'auto',
            aspectRatio: window.innerWidth < 768 ? 1.5 : 1.8,
            eventDisplay: 'block',
            eventTimeFormat: {
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            },
            eventSources: eventSources,
            slotMinTime: '08:00:00',
            slotMaxTime: '22:00:00',
            slotDuration: '00:30:00',
            eventClick: function(info) {
                info.jsEvent.preventDefault();
                const eventType = info.event.extendedProps ? info.event.extendedProps.eventType : 'booking';
                if (eventType === 'closure') {
                    if (canManageClosures && info.event.extendedProps.canDelete) {
                        promptClosureDelete(info.event);
                    }
                    return;
                }
                saveViewState();
                openBookingEditModal(info.event.id);
            },
            dateClick: function(info) {
                // Обработка клика на свободный слот
                const view = info.view.type;
                let targetDate = new Date(info.date);

                if (view === 'dayGridMonth') {
                    if (copyShortcutsEnabled && copiedBookingBuffer) {
                        targetDate.setHours(copiedBookingBuffer.startHours, copiedBookingBuffer.startMinutes, 0, 0);
                    } else {
                        targetDate.setHours(9, 0, 0, 0);
                    }
                }

                lastSlotSelection = new Date(targetDate);

                if (copyShortcutsEnabled && copiedBookingBuffer) {
                    info.jsEvent.preventDefault();
                    duplicateCopiedBooking(targetDate);
                    return;
                }

                // В месячном виде открываем модальное окно с выбранной датой
                openQuickBookingModal(targetDate, info.dateStr);
            },
            eventDidMount: function(info) {
                const eventType = info.event.extendedProps ? info.event.extendedProps.eventType : 'booking';
                if (eventType === 'closure') {
                    info.el.classList.add('cabinet-closure-event');
                    info.el.style.right = '';
                    return;
                }
                const viewType = info.view ? info.view.type : calendar.view.type;
                if (viewType === 'timeGridWeek' || viewType === 'timeGridDay') {
                    const currentRight = info.el.style.right;
                    if (!currentRight || currentRight === '0%') {
                        info.el.style.right = '25%';
                    }
                } else {
                    info.el.style.right = '';
                }
            },
            eventDrop: function(info) {
                // Обработка перетаскивания события
                handleEventDrop(info);
            },
            eventMouseEnter: handleEventMouseEnter,
            eventMouseLeave: handleEventMouseLeave,
            datesSet: function() {
                saveViewState();
                updateViewSwitcherButtons();
                updateCalendarTitle();
            },
            eventStartEditable: true,
            eventDurationEditable: false,  // Запрещаем изменение длительности через drag
            editable: true,
            allDaySlot: false
        });

        calendar.render();
        setTimeout(() => calendar.updateSize(), 100);
    }

    function handleEventMouseEnter(info) {
        if (!copyShortcutsEnabled) {
            return;
        }
        if (!info || !info.event) {
            return;
        }
        const eventType = info.event.extendedProps ? info.event.extendedProps.eventType : 'booking';
        if (eventType !== 'booking') {
            return;
        }
        hoveredBookingEvent = info.event;
    }

    function handleEventMouseLeave(info) {
        if (!copyShortcutsEnabled) {
            return;
        }
        if (!info || !info.event) {
            return;
        }
        if (hoveredBookingEvent && hoveredBookingEvent.id === info.event.id) {
            hoveredBookingEvent = null;
        }
    }

    function initCopyPasteShortcuts() {
        if (copyPasteHandlerAttached) {
            return;
        }
        if (!copyShortcutsEnabled) {
            return;
        }
        document.addEventListener('keydown', handleCopyPasteShortcut, true);
        copyPasteHandlerAttached = true;
    }

    function handleCopyPasteShortcut(event) {
        if (!copyShortcutsEnabled) {
            return;
        }
        const activeElement = document.activeElement;
        const isIgnoredElement = activeElement
            && (activeElement.tagName === 'INPUT'
                || activeElement.tagName === 'TEXTAREA'
                || activeElement.isContentEditable);

        if (isIgnoredElement) {
            return;
        }

        const key = event.key ? event.key.toLowerCase() : '';
        const hasModifier = event.metaKey || event.ctrlKey;

        if (key === 'escape' && copiedBookingBuffer) {
            clearCopyBuffer(true);
            return;
        }

        if (!hasModifier) {
            return;
        }

        if (!event.shiftKey && !event.altKey && key === 'c') {
            if (!hoveredBookingEvent) {
                return;
            }
            const eventType = hoveredBookingEvent.extendedProps ? hoveredBookingEvent.extendedProps.eventType : 'booking';
            if (eventType !== 'booking') {
                return;
            }
            const seriesId = hoveredBookingEvent.extendedProps ? hoveredBookingEvent.extendedProps.seriesId : null;
            if (seriesId) {
                showResultModal('Копирование невозможно', 'Нельзя копировать бронирования из серии', false);
                event.preventDefault();
                return;
            }
            const startDate = hoveredBookingEvent.start ? new Date(hoveredBookingEvent.start) : null;
            copiedBookingBuffer = {
                bookingId: hoveredBookingEvent.id,
                title: hoveredBookingEvent.title || 'Бронирование',
                startHours: startDate ? startDate.getHours() : 0,
                startMinutes: startDate ? startDate.getMinutes() : 0,
                copiedAt: Date.now()
            };
            showResultModal(
                'Скопировано',
                `Выберите слот и нажмите ${getPasteShortcutLabel()} для вставки`,
                true
            );
            event.preventDefault();
            return;
        }

        if (!event.shiftKey && !event.altKey && key === 'v') {
            if (!copiedBookingBuffer) {
                showResultModal('Копирование не выполнено', `Сначала наведите на бронирование и нажмите ${getCopyShortcutLabel()}`, false);
                event.preventDefault();
                return;
            }
            if (!lastSlotSelection) {
                showResultModal('Нет выбранного слота', `Кликните по свободному времени и затем нажмите ${getPasteShortcutLabel()}`, false);
                event.preventDefault();
                return;
            }
            duplicateCopiedBooking(new Date(lastSlotSelection));
            event.preventDefault();
        }
    }

    function duplicateCopiedBooking(targetDate) {
        if (!copyShortcutsEnabled) {
            return;
        }
        if (!copiedBookingBuffer) {
            return;
        }
        if (!(targetDate instanceof Date) || isNaN(targetDate.getTime())) {
            showResultModal('Ошибка', 'Не удалось определить целевую дату для вставки', false);
            return;
        }

        const formData = new FormData();
        formData.append('booking_id', copiedBookingBuffer.bookingId);
        formData.append('start_datetime', formatDateForInput(targetDate));

        fetch(duplicateBookingUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            },
            body: formData
        })
            .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
            .then(({ ok, data }) => {
                if (ok && data.success) {
                    // Показываем предупреждение если есть конфликты
                    let message = data.message || 'Бронирование скопировано';
                    if (data.warning) {
                        message += `\n\n⚠️ Внимание: ${data.warning}`;
                        showResultModal('Готово с предупреждением', message, true);
                    } else {
                        showResultModal('Готово', message, true);
                    }
                    if (calendar) {
                        calendar.refetchEvents();
                    }
                } else {
                    const errorMessage = (data && (data.error || data.message)) || 'Не удалось скопировать бронирование';
                    showResultModal('Ошибка', errorMessage, false);
                }
            })
            .catch((error) => {
                console.error('Error duplicating booking:', error);
                showResultModal('Ошибка', 'Произошла ошибка при копировании бронирования', false);
            });
    }

    function clearCopyBuffer(showMessage) {
        if (!copyShortcutsEnabled) {
            return;
        }
        copiedBookingBuffer = null;
        if (showMessage) {
            showResultModal('Буфер очищен', `Скопируйте бронирование клавишами ${getCopyShortcutLabel()}`, true);
        }
    }

    function getCopyShortcutLabel() {
        return isMacPlatform ? '⌘C' : 'Ctrl+C';
    }

    function getPasteShortcutLabel() {
        return isMacPlatform ? '⌘V' : 'Ctrl+V';
    }

    function switchView(viewType) {
        currentView = viewType;
        if (calendar) {
            calendar.setOption('visibleRange', null);
            calendar.changeView(viewType);
            saveViewState();
            updateViewSwitcherButtons();
            updateCalendarTitle();
        }
    }

    function updateWidthButton() {
        const btn = document.getElementById('toggle-width-btn');
        if (!btn) return;
        const modes = {
            standard: { text: 'Широкий режим', icon: 'bi bi-arrows-expand' },
            wide: { text: 'Полноэкр.', icon: 'bi bi-arrows-fullscreen' },
            fullscreen: { text: 'Стандартный режим', icon: 'bi bi-arrows-collapse' }
        };
        const mode = modes[currentWidthMode] || modes.standard;
        btn.innerHTML = `<i class="${mode.icon}"></i> ${mode.text}`;
    }

    function updateViewSwitcherButtons() {
        const buttons = document.querySelectorAll('[data-view-switch]');
        buttons.forEach(button => {
            const targetView = button.getAttribute('data-view-switch');
            if (targetView === currentView) {
                button.classList.add('active', 'btn-primary');
                button.classList.remove('btn-outline-primary');
            } else {
                button.classList.remove('active', 'btn-primary');
                button.classList.add('btn-outline-primary');
            }
        });
    }

    function attachNavigationControls() {
        const prevBtn = document.getElementById('calendar-prev-btn');
        const nextBtn = document.getElementById('calendar-next-btn');
        const todayBtn = document.getElementById('calendar-today-btn');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => navigateCalendar(-1));
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => navigateCalendar(1));
        }

        if (todayBtn) {
            todayBtn.addEventListener('click', () => goToToday());
        }
    }

    function updateCalendarTitle() {
        const titleContainer = document.getElementById('calendar-current-range');
        if (!titleContainer || !calendar || !calendar.view) {
            return;
        }
        titleContainer.textContent = calendar.view.title || '';
    }

    function toggleCalendarWidth() {
        const container = document.getElementById('calendar-page');
        if (!container) return;

        if (currentWidthMode === 'standard') {
            currentWidthMode = 'wide';
        } else if (currentWidthMode === 'wide') {
            currentWidthMode = 'fullscreen';
        } else {
            currentWidthMode = 'standard';
        }

        applyWidthModeClass();
        updateWidthButton();
        saveWidthMode();
        if (calendar) {
            setTimeout(() => calendar.updateSize(), 200);
        }
    }

    function applyWidthModeClass() {
        const container = document.getElementById('calendar-page');
        if (!container) return;

        container.classList.remove('calendar-wide', 'calendar-fullscreen');

        if (currentWidthMode === 'wide') {
            container.classList.add('calendar-wide');
        } else if (currentWidthMode === 'fullscreen') {
            container.classList.add('calendar-fullscreen');
        }
    }

    function saveWidthMode() {
        try {
            localStorage.setItem(WIDTH_MODE_STORAGE_KEY, currentWidthMode);
        } catch (e) {
            console.warn('Unable to save width mode preference', e);
        }
    }

    function restoreWidthMode() {
        try {
            const savedMode = localStorage.getItem(WIDTH_MODE_STORAGE_KEY);
            if (savedMode && ['standard', 'wide', 'fullscreen'].includes(savedMode)) {
                currentWidthMode = savedMode;
            }
        } catch (e) {
            console.warn('Unable to read width mode preference', e);
        }
    }

    function toggleQuickRecurrenceSettings(forceEnabled) {
        if (!quickRecurrenceSettings || !quickRecurrenceToggle) return;
        const enabled = typeof forceEnabled === 'boolean' ? forceEnabled : quickRecurrenceToggle.checked;
        quickRecurrenceSettings.classList.toggle('d-none', !enabled);
        if (!enabled) {
            if (quickRecurrenceExcludedDisplay) quickRecurrenceExcludedDisplay.value = '';
            if (quickRecurrenceExcludedHidden) quickRecurrenceExcludedHidden.value = '';
        }
    }

    function updateQuickRecurrenceIntervalLabel() {
        if (!quickRecurrenceIntervalLabel || !quickRecurrenceFrequency) return;
        const freq = quickRecurrenceFrequency.value;
        let suffix = 'дней';
        switch (freq) {
            case 'weekly':
                suffix = 'недель';
                break;
            case 'monthly':
                suffix = 'месяцев';
                break;
            case 'yearly':
                suffix = 'лет';
                break;
        }
        quickRecurrenceIntervalLabel.textContent = suffix;
    }

    function updateQuickRecurrenceFrequencyState() {
        updateQuickRecurrenceIntervalLabel();
        if (!quickRecurrenceWeekdaysBlock) return;
        if (quickRecurrenceFrequency && quickRecurrenceFrequency.value === 'weekly') {
            quickRecurrenceWeekdaysBlock.classList.remove('d-none');
        } else {
            quickRecurrenceWeekdaysBlock.classList.add('d-none');
        }
    }

    function updateQuickRecurrenceEndState() {
        if (!quickRecurrenceEndType) return;
        const type = quickRecurrenceEndType.value || 'count';
        if (quickRecurrenceCountField) {
            quickRecurrenceCountField.classList.toggle('d-none', type !== 'count');
        }
        if (quickRecurrenceUntilField) {
            quickRecurrenceUntilField.classList.toggle('d-none', type !== 'until');
        }
    }

    function syncQuickExcludedDates() {
        if (!quickRecurrenceExcludedHidden || !quickRecurrenceExcludedDisplay) return;
        const raw = quickRecurrenceExcludedDisplay.value.trim();
        if (!raw) {
            quickRecurrenceExcludedHidden.value = '';
            return;
        }
        const parts = raw.split(',').map((item) => item.trim()).filter(Boolean);
        const isoDates = [];
        parts.forEach((item) => {
            if (!item) return;
            const normalized = item.replace(/\//g, '.');
            const isoMatch = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
            if (isoMatch) {
                isoDates.push(`${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`);
                return;
            }
            const match = normalized.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
            if (match) {
                const day = match[1].padStart(2, '0');
                const month = match[2].padStart(2, '0');
                const year = match[3];
                isoDates.push(`${year}-${month}-${day}`);
            }
        });
        quickRecurrenceExcludedHidden.value = isoDates.length ? JSON.stringify(isoDates) : '';
    }

    function resetQuickRecurrenceControls() {
        if (!quickRecurrenceToggle) return;
        quickRecurrenceToggle.checked = false;
        toggleQuickRecurrenceSettings(false);
        if (quickRecurrenceFrequency && quickRecurrenceFrequency.options.length) {
            quickRecurrenceFrequency.value = quickRecurrenceFrequency.options[0].value;
        }
        if (quickRecurrenceOccurrences) {
            quickRecurrenceOccurrences.value = 2;
        }
        if (quickRecurrenceEndType) {
            quickRecurrenceEndType.value = 'count';
        }
        if (quickRecurrenceWeekdaysBlock) {
            quickRecurrenceWeekdaysBlock.querySelectorAll('input[type=\"checkbox\"]').forEach((checkbox) => {
                checkbox.checked = false;
            });
        }
        if (quickRecurrenceExcludedDisplay) quickRecurrenceExcludedDisplay.value = '';
        if (quickRecurrenceExcludedHidden) quickRecurrenceExcludedHidden.value = '';
        updateQuickRecurrenceFrequencyState();
        updateQuickRecurrenceEndState();
    }

    if (quickRecurrenceToggle) {
        quickRecurrenceToggle.addEventListener('change', function() {
            toggleQuickRecurrenceSettings();
        });
    }

    if (quickRecurrenceFrequency) {
        quickRecurrenceFrequency.addEventListener('change', function() {
            updateQuickRecurrenceFrequencyState();
        });
    }

    if (quickRecurrenceEndType) {
        quickRecurrenceEndType.addEventListener('change', function() {
            updateQuickRecurrenceEndState();
        });
    }

    if (quickRecurrenceExcludedDisplay) {
        quickRecurrenceExcludedDisplay.addEventListener('blur', syncQuickExcludedDates);
    }

    toggleQuickRecurrenceSettings(quickRecurrenceToggle ? quickRecurrenceToggle.checked : false);
    updateQuickRecurrenceFrequencyState();
    updateQuickRecurrenceEndState();

    function openBookingEditModal(bookingId) {
        if (!bookingEditModalEl || !bookingEditModalBody) {
            window.location.href = `/booking/${bookingId}/`;
            return;
        }

        if (!bookingEditModal) {
            bookingEditModal = new bootstrap.Modal(bookingEditModalEl);
        }

        bookingEditModalBody.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Загрузка...</span>
                </div>
                <p class="mt-3 text-muted">Загружаем данные бронирования…</p>
            </div>
        `;

        bookingEditModal.show();

        fetch(`/booking/${bookingId}/?modal=1`, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (!data || !data.success) {
                    throw new Error(data && data.error ? data.error : 'Ошибка загрузки бронирования');
                }
                bookingEditModalBody.innerHTML = data.html;
                initBookingEditForm(bookingEditModalBody, {
                    onInit(form) {
                        form.dataset.ajax = 'true';
                        form.addEventListener('submit', handleBookingModalSubmit);
                    }
                });
            })
            .catch(error => {
                console.error('Error loading booking form:', error);
                bookingEditModalBody.innerHTML = `
                    <div class="alert alert-danger mb-0">
                        <i class="bi bi-exclamation-triangle"></i> Не удалось загрузить форму. <a href="/booking/${bookingId}/" class="alert-link">Открыть на отдельной странице</a>.
                    </div>
                `;
            });
    }

    function handleBookingModalSubmit(event) {
        event.preventDefault();
        const form = event.target;
        if (!form) return;

        if (form.dataset.submitting === 'true') {
            return;
        }
        form.dataset.submitting = 'true';

        const submitButton = form.querySelector('button[type="submit"]');
        let originalButtonHTML = '';
        if (submitButton) {
            originalButtonHTML = submitButton.innerHTML;
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Сохранение...';
        }

        const formData = new FormData(form);
        const actionUrl = form.getAttribute('action') || `/booking/${form.dataset.bookingId}/`;

        fetch(actionUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(data => {
                        throw data;
                    }).catch(() => {
                        throw new Error('Ошибка при сохранении бронирования');
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Обновляем логи если форма еще открыта
                    const logsBody = bookingEditModalBody.querySelector('[data-role="booking-logs-body"]');
                    if (logsBody) {
                        const refreshBtn = bookingEditModalBody.querySelector('[data-role="refresh-logs"]');
                        if (refreshBtn) {
                            refreshBtn.click();
                        }
                    }
                    
                    bookingEditModal.hide();
                    calendar.refetchEvents();
                    // Показываем предупреждение если есть конфликты
                    let message = data.message || 'Бронирование успешно обновлено';
                    if (data.warning) {
                        message += `\n\n⚠️ Внимание: ${data.warning}`;
                        showResultModal('Успех с предупреждением', message, true);
                    } else {
                        showResultModal('Успех', message, true);
                    }
                } else {
                    if (data.html) {
                        bookingEditModalBody.innerHTML = data.html;
                        initBookingEditForm(bookingEditModalBody, {
                            onInit(newForm) {
                                newForm.dataset.ajax = 'true';
                                newForm.addEventListener('submit', handleBookingModalSubmit);
                            }
                        });
                    }
                    if (data.error) {
                        showResultModal('Ошибка', data.error, false);
                    }
                }
            })
            .catch(error => {
                console.error('Error submitting booking form:', error);
                const message = error && error.error ? error.error : (error && error.message ? error.message : 'Не удалось сохранить изменения. Попробуйте позже.');
                showResultModal('Ошибка', message, false);
            })
            .finally(() => {
                if (submitButton && submitButton.isConnected) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalButtonHTML;
                }
                form.dataset.submitting = 'false';
            });
    }

    function openQuickBookingModal(date, dateStr) {
        // Форматируем дату для отображения
        const localDate = new Date(date);
        
        // Проверяем, является ли это кликом из месячного вида
        const isMonthView = calendar.view.type === 'dayGridMonth';
        
        let formattedDate;
        if (isMonthView) {
            // Для месячного вида показываем только дату без времени
            formattedDate = localDate.toLocaleDateString('ru-RU', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
        } else {
            // Для временных видов показываем дату и время
            formattedDate = localDate.toLocaleString('ru-RU', {
                weekday: 'short',
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        document.getElementById('selectedDateTime').textContent = formattedDate;

        // Форматируем дату в локальное время для отправки на сервер
        // Формат: YYYY-MM-DDTHH:MM (локальное время, не UTC)
        const year = localDate.getFullYear();
        const month = String(localDate.getMonth() + 1).padStart(2, '0');
        const day = String(localDate.getDate()).padStart(2, '0');
        const hours = String(localDate.getHours()).padStart(2, '0');
        const minutes = String(localDate.getMinutes()).padStart(2, '0');
        const localDateTime = `${year}-${month}-${day}T${hours}:${minutes}`;

        document.getElementById('start_datetime').value = localDateTime;

        // Сбрасываем форму
        document.getElementById('quickBookingForm').reset();
        document.getElementById('start_datetime').value = localDateTime;
        document.getElementById('specialist').innerHTML = '<option value="">Сначала выберите услугу</option>';
        document.getElementById('cabinet').innerHTML = '<option value="">Сначала выберите услугу, специалиста и время</option>';
        resetQuickRecurrenceControls();

        // Показываем модальное окно
        if (!quickBookingModal) {
            quickBookingModal = new bootstrap.Modal(document.getElementById('quickBookingModal'));
        }
        quickBookingModal.show();
        
        // Загружаем кабинеты автоматически при показе модального окна, если услуга и специалист уже выбраны
        const modalElement = document.getElementById('quickBookingModal');
        const handleModalShown = function() {
            setTimeout(function() {
                const serviceVariantId = document.getElementById('service_variant').value;
                const specialistId = document.getElementById('specialist').value;
                const startDatetime = document.getElementById('start_datetime').value;
                
                if (serviceVariantId && specialistId && startDatetime) {
                    loadAvailableCabinets();
                }
            }, 100);
        };
        modalElement.addEventListener('shown.bs.modal', handleModalShown, { once: true });
    }

    function initQuickBookingModal() {
        const modalElement = document.getElementById('quickBookingModal');
        if (!modalElement) return;

        quickBookingModal = new bootstrap.Modal(modalElement);
        resetQuickRecurrenceControls();

        const cancelButton = modalElement.querySelector('[data-action="quick-booking-cancel"]');
        if (cancelButton) {
            cancelButton.addEventListener('click', function() {
                hideQuickBookingModal();
            });
        }
    }

    function hideQuickBookingModal() {
        if (quickBookingModal) {
            quickBookingModal.hide();
            return;
        }

        const modalElement = document.getElementById('quickBookingModal');
        if (!modalElement) return;
        const instance = bootstrap.Modal.getInstance(modalElement);
        if (instance) {
            instance.hide();
        }
    }

    function initCabinetClosureModals() {
        if (!canManageClosures) {
            return;
        }
        const startInput = document.getElementById('id_start_time');
        const endInput = document.getElementById('id_end_time');
        if (closureModalEl) {
            cabinetClosureModal = new bootstrap.Modal(closureModalEl);
            closureModalEl.addEventListener('hidden.bs.modal', () => {
                if (closureFormEl) {
                    closureFormEl.reset();
                }
                clearClosureErrors();
            });
        }
        if (closureFormEl) {
            closureFormEl.addEventListener('submit', handleCabinetClosureSubmit);
        }
        if (closureDeleteModalEl) {
            closureDeleteModal = new bootstrap.Modal(closureDeleteModalEl);
        }
        if (confirmClosureDeleteBtn) {
            confirmClosureDeleteBtn.addEventListener('click', handleClosureDelete);
        }
        if (window.flatpickr) {
            const localeConfig = window.flatpickr.l10ns && window.flatpickr.l10ns.ru ? window.flatpickr.l10ns.ru : 'ru';
            const baseOptions = {
                enableTime: true,
                time_24hr: true,
                dateFormat: 'Y-m-d\\TH:i',
                altInput: true,
                altFormat: 'd.m.Y, H:i',
                allowInput: true,
                minuteIncrement: 5,
                locale: localeConfig
            };
            if (startInput) {
                if (startInput._flatpickr) {
                    startInput._flatpickr.destroy();
                }
                closureStartPicker = window.flatpickr(startInput, Object.assign({}, baseOptions, {
                    onChange: function(selectedDates) {
                        if (!closureEndPicker || !selectedDates.length) {
                            return;
                        }
                        const startDate = selectedDates[0];
                        closureEndPicker.set('minDate', startDate);
                        const currentEnd = closureEndPicker.selectedDates[0];
                        if (!currentEnd || currentEnd <= startDate) {
                            const defaultEnd = new Date(startDate.getTime() + 60 * 60 * 1000);
                            closureEndPicker.setDate(defaultEnd, false);
                        }
                    }
                }));
            }
            if (endInput) {
                if (endInput._flatpickr) {
                    endInput._flatpickr.destroy();
                }
                closureEndPicker = window.flatpickr(endInput, Object.assign({}, baseOptions));
            }
            if (closureStartPicker && closureEndPicker) {
                const selectedStart = closureStartPicker.selectedDates[0];
                if (selectedStart) {
                    closureEndPicker.set('minDate', selectedStart);
                }
            }
        }
    }

    function clearClosureErrors() {
        const errorBlocks = document.querySelectorAll('[data-role^="closure-error-"]');
        errorBlocks.forEach((block) => {
            block.classList.add('d-none');
            block.textContent = '';
        });
    }

    function showClosureErrors(errors) {
        clearClosureErrors();
        if (!errors) return;

        const nonFieldBlock = document.querySelector('[data-role="closure-error-non-field"]');
        const errorMessages = [];
        Object.entries(errors).forEach(([field, messages]) => {
            const messageText = Array.isArray(messages) ? messages.join(' ') : messages;
            if (field === '__all__' && nonFieldBlock) {
                nonFieldBlock.textContent = messageText;
                nonFieldBlock.classList.remove('d-none');
            } else {
                const block = document.querySelector(`[data-role="closure-error-${field}"]`);
                if (block) {
                    block.textContent = messageText;
                    block.classList.remove('d-none');
                } else {
                    errorMessages.push(messageText);
                }
            }
        });
        if (nonFieldBlock && errorMessages.length) {
            nonFieldBlock.textContent = errorMessages.join(' ');
            nonFieldBlock.classList.remove('d-none');
        }
    }

    function formatDateForInput(date) {
        const pad = (value) => value.toString().padStart(2, '0');
        const year = date.getFullYear();
        const month = pad(date.getMonth() + 1);
        const day = pad(date.getDate());
        const hours = pad(date.getHours());
        const minutes = pad(date.getMinutes());
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    }

    function openCabinetClosureModal(date) {
        if (!canManageClosures || !cabinetClosureModal || !closureFormEl) {
            return;
        }
        clearClosureErrors();
        closureFormEl.reset();

        const startInput = document.getElementById('id_start_time');
        const endInput = document.getElementById('id_end_time');

        const baseDate = date instanceof Date ? new Date(date) : new Date();
        const startDate = new Date(baseDate);
        startDate.setSeconds(0, 0);

        const endDate = new Date(startDate);
        endDate.setHours(endDate.getHours() + 1);

        if (closureStartPicker) {
            closureStartPicker.setDate(startDate, false);
            if (closureEndPicker) {
                closureEndPicker.set('minDate', startDate);
            }
        } else if (startInput) {
            startInput.value = formatDateForInput(startDate);
        }
        if (closureEndPicker) {
            closureEndPicker.setDate(endDate, false);
        } else if (endInput) {
            endInput.value = formatDateForInput(endDate);
        }

        cabinetClosureModal.show();
    }

    function handleCabinetClosureSubmit(event) {
        event.preventDefault();
        if (!closureFormEl) return;

        const submitButton = closureFormEl.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Сохранение...';
        }

        const formData = new FormData(closureFormEl);
        fetch(closureCreateUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            },
            body: formData
        })
            .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
            .then(({ ok, data }) => {
                if (ok && data.success) {
                    if (cabinetClosureModal) {
                        cabinetClosureModal.hide();
                    }
                    showResultModal('Успех', data.message || 'Закрытие кабинета создано', true);
                    if (calendar) {
                        calendar.refetchEvents();
                    }
                } else {
                    showClosureErrors(data.errors);
                    const message = data.errors ? Object.values(data.errors).flat().join(' ') : (data.error || 'Не удалось создать закрытие');
                    showResultModal('Ошибка', message, false);
                }
            })
            .catch((error) => {
                console.error('Error creating cabinet closure:', error);
                showResultModal('Ошибка', 'Произошла ошибка при создании закрытия кабинета', false);
            })
            .finally(() => {
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = '<i class="bi bi-door-closed-fill"></i> Закрыть';
                }
            });
    }

    function promptClosureDelete(event) {
        if (!canManageClosures || !closureDeleteModal || !event) {
            return;
        }
        pendingClosureDeleteId = event.id;

        if (closureDeleteCabinetNameEl) {
            closureDeleteCabinetNameEl.textContent = event.extendedProps.cabinet || '';
        }
        if (closureDeletePeriodEl) {
            const start = new Date(event.start);
            const end = new Date(event.end);
            const formatter = new Intl.DateTimeFormat('ru-RU', {
                day: '2-digit',
                month: 'long',
                hour: '2-digit',
                minute: '2-digit'
            });
            closureDeletePeriodEl.textContent = `${formatter.format(start)} — ${formatter.format(end)}`;
        }

        closureDeleteModal.show();
    }

    function handleClosureDelete() {
        if (!pendingClosureDeleteId) {
            return;
        }
        const deleteUrl = `${closureDeleteBaseUrl}${pendingClosureDeleteId}/delete/`;
        confirmClosureDeleteBtn.disabled = true;
        confirmClosureDeleteBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Удаление...';

        fetch(deleteUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            }
        })
            .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
            .then(({ ok, data }) => {
                if (ok && data.success) {
                    closureDeleteModal.hide();
                    showResultModal('Успех', data.message || 'Закрытие кабинета удалено', true);
                    if (calendar) {
                        calendar.refetchEvents();
                    }
                } else {
                    const message = data.error || 'Не удалось удалить закрытие кабинета';
                    showResultModal('Ошибка', message, false);
                }
            })
            .catch((error) => {
                console.error('Error deleting cabinet closure:', error);
                showResultModal('Ошибка', 'Произошла ошибка при удалении закрытия кабинета', false);
            })
            .finally(() => {
                confirmClosureDeleteBtn.disabled = false;
                confirmClosureDeleteBtn.innerHTML = '<i class="bi bi-trash"></i> Удалить';
                pendingClosureDeleteId = null;
            });
    }

    function handleEventDrop(info) {
        // Откатываем событие на случай ошибки
        const revert = info.revert;

        const event = info.event;
        const newStart = event.start;
        const bookingId = event.id;

        // Форматируем дату в локальное время (YYYY-MM-DDTHH:MM)
        // FullCalendar работает с локальным временем, поэтому просто форматируем
        const year = newStart.getFullYear();
        const month = String(newStart.getMonth() + 1).padStart(2, '0');
        const day = String(newStart.getDate()).padStart(2, '0');
        const hours = String(newStart.getHours()).padStart(2, '0');
        const minutes = String(newStart.getMinutes()).padStart(2, '0');
        const startDatetime = `${year}-${month}-${day}T${hours}:${minutes}`;

        // Отправляем AJAX запрос
        const formData = new FormData();
        formData.append('booking_id', bookingId);
        formData.append('start_datetime', startDatetime);

        fetch('/booking/update-time/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': csrftoken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                // Показываем ошибку
                showResultModal('Ошибка', data.error, false);
                // Откатываем изменение
                revert();
                // Обновляем календарь
                calendar.refetchEvents();
            } else {
                // Показываем успех с предупреждением если есть конфликты
                let message = data.message || 'Время бронирования изменено';
                if (data.warning) {
                    message += `\n\n⚠️ Внимание: ${data.warning}`;
                    showResultModal('Успех с предупреждением', message, true);
                } else {
                    showResultModal('Успех', message, true);
                }
            }
        })
        .catch(error => {
            console.error('Error updating booking time:', error);
            showResultModal('Ошибка', 'Произошла ошибка при изменении времени', false);
            // Откатываем изменение
            revert();
            // Обновляем календарь
            calendar.refetchEvents();
        });
    }

    function saveViewState() {
        if (!calendar) return;
        try {
            currentView = calendar.view.type;
            const currentMoment = calendar.getDate();
            currentDate = currentMoment;
            localStorage.setItem(VIEW_STORAGE_KEY, currentView);
            localStorage.setItem(DATE_STORAGE_KEY, currentMoment.toISOString());
        } catch (e) {
            console.warn('Unable to persist calendar view state', e);
        }
    }

    function restoreViewState() {
        try {
            const savedView = localStorage.getItem(VIEW_STORAGE_KEY);
            const allowedViews = ['dayGridMonth', 'timeGridWeek', 'timeGridDay', 'timeGridThreeDay'];
            if (savedView && allowedViews.includes(savedView)) {
                currentView = savedView;
            }
            const savedDate = localStorage.getItem(DATE_STORAGE_KEY);
            if (savedDate) {
                const parsedDate = new Date(savedDate);
                if (!isNaN(parsedDate.getTime())) {
                    currentDate = parsedDate;
                }
            }
        } catch (e) {
            console.warn('Unable to restore calendar view state', e);
        }
    }

    function cleanupModalBackdrops() {
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach((backdrop) => backdrop.remove());
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('padding-right');
    }

    function showResultModal(title, message, isSuccess) {
        const modalElement = document.getElementById('resultModal');
        if (!modalElement) {
            console.warn('Result modal element not found');
            return;
        }

        if (!resultModalInstance) {
            resultModalInstance = new bootstrap.Modal(modalElement, {
                backdrop: false,
                keyboard: true
            });

            modalElement.addEventListener('hidden.bs.modal', () => {
                cleanupModalBackdrops();
            });
        }

        if (resultModalHideTimeout) {
            clearTimeout(resultModalHideTimeout);
            resultModalHideTimeout = null;
        }

        document.getElementById('resultTitle').textContent = title;
        document.getElementById('resultHeader').className = isSuccess ? 'modal-header bg-success text-white' : 'modal-header bg-danger text-white';
        document.getElementById('resultBody').innerHTML = `<p>${message}</p>`;

        cleanupModalBackdrops();
        resultModalInstance.show();

        resultModalHideTimeout = setTimeout(() => {
            if (resultModalInstance) {
                resultModalInstance.hide();
            }
        }, 2000);
    }

    // Функция загрузки доступных кабинетов
    function loadAvailableCabinets() {
        const serviceVariantId = document.getElementById('service_variant').value;
        const specialistId = document.getElementById('specialist').value;
        const startDatetime = document.getElementById('start_datetime').value;
        const cabinetSelect = document.getElementById('cabinet');

        if (!serviceVariantId || !specialistId || !startDatetime) {
            cabinetSelect.innerHTML = '<option value="">Сначала выберите услугу, специалиста и время</option>';
            return;
        }

        // Показываем загрузку
        cabinetSelect.innerHTML = '<option value="">Загрузка...</option>';
        cabinetSelect.disabled = true;

        // Загружаем доступные кабинеты
        fetch(`/api/available-cabinets/?service_variant_id=${serviceVariantId}&specialist_id=${specialistId}&datetime=${encodeURIComponent(startDatetime)}`)
            .then(response => response.json())
            .then(data => {
                cabinetSelect.disabled = false;
                if (data.error) {
                    cabinetSelect.innerHTML = `<option value="">${data.error}</option>`;
                    return;
                }

                cabinetSelect.innerHTML = '<option value="">-- Выберите кабинет (опционально) --</option>';
                if (data.cabinets && data.cabinets.length > 0) {
                    data.cabinets.forEach(cabinet => {
                        const option = document.createElement('option');
                        option.value = cabinet.id;
                        option.textContent = cabinet.name;
                        cabinetSelect.appendChild(option);
                    });
                } else {
                    cabinetSelect.innerHTML = '<option value="">Нет доступных кабинетов</option>';
                }
            })
            .catch(error => {
                console.error('Error loading cabinets:', error);
                cabinetSelect.disabled = false;
                cabinetSelect.innerHTML = '<option value="">Ошибка загрузки</option>';
            });
    }

    // Загрузка специалистов при выборе услуги
    document.getElementById('service_variant').addEventListener('change', function() {
        const serviceVariantId = this.value;
        const specialistSelect = document.getElementById('specialist');

        if (!serviceVariantId) {
            specialistSelect.innerHTML = '<option value="">Сначала выберите услугу</option>';
            document.getElementById('cabinet').innerHTML = '<option value="">Сначала выберите услугу, специалиста и время</option>';
            return;
        }

        // Показываем загрузку
        specialistSelect.innerHTML = '<option value="">Загрузка...</option>';

        // Загружаем специалистов
        fetch(`/api/specialists-for-service/?service_variant_id=${serviceVariantId}`)
            .then(response => response.json())
            .then(data => {
                specialistSelect.innerHTML = '<option value="">Выберите специалиста</option>';
                data.forEach(specialist => {
                    const option = document.createElement('option');
                    option.value = specialist.id;
                    option.textContent = specialist.full_name;
                    specialistSelect.appendChild(option);
                });
                
                // Сбрасываем кабинеты
                document.getElementById('cabinet').innerHTML = '<option value="">Сначала выберите специалиста и время</option>';
            })
            .catch(error => {
                console.error('Error loading specialists:', error);
                specialistSelect.innerHTML = '<option value="">Ошибка загрузки</option>';
            });
    });

    // Загрузка кабинетов при изменении специалиста
    document.getElementById('specialist').addEventListener('change', function() {
        loadAvailableCabinets();
    });

    // Обработка отправки формы
    document.getElementById('quickBookingForm').addEventListener('submit', function(e) {
        e.preventDefault();

        syncQuickExcludedDates();

        const formData = new FormData(this);
        const submitButton = this.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Создание...';

        fetch('/booking/quick-create/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': formData.get('csrfmiddlewaretoken')
            }
        })
        .then(response => response.json())
        .then(data => {
            submitButton.disabled = false;
            submitButton.innerHTML = '<i class="bi bi-check-circle"></i> Создать';

            // Закрываем модальное окно формы
            hideQuickBookingModal();

            // Показываем результат
            const resultModal = new bootstrap.Modal(document.getElementById('resultModal'));

            if (data.success) {
                // Показываем предупреждение если есть конфликты
                if (data.warning) {
                    document.getElementById('resultTitle').textContent = 'Успех с предупреждением';
                    document.getElementById('resultHeader').className = 'modal-header bg-warning text-dark';
                    document.getElementById('resultBody').innerHTML = `<p>${data.message}</p><p class="mt-2"><strong>⚠️ Внимание:</strong> ${data.warning}</p>`;
                } else {
                    document.getElementById('resultTitle').textContent = 'Успех';
                    document.getElementById('resultHeader').className = 'modal-header bg-success text-white';
                    document.getElementById('resultBody').innerHTML = `<p>${data.message}</p>`;
                }
            } else {
                document.getElementById('resultTitle').textContent = 'Ошибка';
                document.getElementById('resultHeader').className = 'modal-header bg-danger text-white';
                document.getElementById('resultBody').innerHTML = `<p>${data.error}</p>`;
            }

            resultModal.show();

            // Обновляем календарь
            calendar.refetchEvents();

            // Закрываем модальное окно результата через 2 секунды
            setTimeout(() => {
                bootstrap.Modal.getInstance(document.getElementById('resultModal')).hide();
            }, 2000);
        })
        .catch(error => {
            console.error('Error creating booking:', error);
            submitButton.disabled = false;
            submitButton.innerHTML = '<i class="bi bi-check-circle"></i> Создать';

            hideQuickBookingModal();

            const resultModal = new bootstrap.Modal(document.getElementById('resultModal'));
            document.getElementById('resultTitle').textContent = 'Ошибка';
            document.getElementById('resultHeader').className = 'modal-header bg-danger text-white';
            document.getElementById('resultBody').innerHTML = '<p>Произошла ошибка при создании бронирования</p>';
            resultModal.show();
        });
    });

    function navigateCalendar(direction) {
        if (!calendar) return;
        if (direction < 0) {
            calendar.prev();
        } else {
            calendar.next();
        }
    }

    function goToToday() {
        if (!calendar) return;
        calendar.today();
    }

