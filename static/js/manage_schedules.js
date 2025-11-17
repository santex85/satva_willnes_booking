function toggleAllDays(checkbox) {
    const checkboxes = document.querySelectorAll('.day-checkbox');
    checkboxes.forEach(cb => cb.checked = checkbox.checked);
}

function selectAllDays() {
    const checkboxes = document.querySelectorAll('.day-checkbox');
    checkboxes.forEach(cb => cb.checked = true);
    const selectAllCheckbox = document.getElementById('selectAll');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = true;
    }
}

function getSelectedDays() {
    const checkboxes = document.querySelectorAll('.day-checkbox:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.value));
}

function applyTimeToSelected() {
    const selectedDays = getSelectedDays();
    if (selectedDays.length === 0) {
        alert('Выберите хотя бы один день');
        return;
    }
    const modal = new bootstrap.Modal(document.getElementById('applyTimeModal'));
    modal.show();
}

function confirmApplyTime() {
    const startTime = document.getElementById('bulkStartTime').value;
    const endTime = document.getElementById('bulkEndTime').value;
    
    if (!startTime || !endTime) {
        alert('Укажите время начала и окончания');
        return;
    }
    
    if (startTime >= endTime) {
        alert('Время начала должно быть меньше времени окончания');
        return;
    }
    
    const selectedDays = getSelectedDays();
    selectedDays.forEach(dayIndex => {
        const row = document.querySelector(`tr[data-day-index="${dayIndex}"]`);
        if (row) {
            const startInput = row.querySelector('input[name$="-start_time"]');
            const endInput = row.querySelector('input[name$="-end_time"]');
            if (startInput) startInput.value = startTime;
            if (endInput) endInput.value = endTime;
        }
    });
    
    const modalInstance = bootstrap.Modal.getInstance(document.getElementById('applyTimeModal'));
    if (modalInstance) {
        modalInstance.hide();
    }
    alert(`Время применено к ${selectedDays.length} дням`);
}

function clearSelectedDays() {
    const selectedDays = getSelectedDays();
    if (selectedDays.length === 0) {
        alert('Нет выбранных дней');
        return;
    }
    
    if (!confirm(`Очистить расписание для ${selectedDays.length} выбранных дней?`)) {
        return;
    }
    
    selectedDays.forEach(dayIndex => {
        const row = document.querySelector(`tr[data-day-index="${dayIndex}"]`);
        if (row) {
            const deleteCheckbox = row.querySelector('input[name$="-DELETE"]');
            if (deleteCheckbox) {
                deleteCheckbox.checked = true;
            }
            const startInput = row.querySelector('input[name$="-start_time"]');
            const endInput = row.querySelector('input[name$="-end_time"]');
            if (startInput) startInput.value = '';
            if (endInput) endInput.value = '';
        }
    });
    
    alert(`Расписание очищено для ${selectedDays.length} дней`);
}

function copySchedule() {
    const sourceId = document.getElementById('sourceSpecialistSelect').value;
    const container = document.querySelector('[data-specialist-id]');
    const targetId = container ? container.dataset.specialistId : null;
    
    if (!sourceId) {
        alert('Выберите специалиста для копирования');
        return;
    }
    
    if (sourceId == targetId) {
        alert('Нельзя копировать расписание к самому себе');
        return;
    }
    
    const containerEl = document.querySelector('[data-copy-schedule-url]');
    const copyUrl = containerEl ? containerEl.dataset.copyScheduleUrl : null;
    if (!copyUrl) {
        alert('Ошибка: URL для копирования не найден');
        return;
    }
    
    const formData = new FormData();
    formData.append('source_specialist_id', sourceId);
    formData.append('target_specialist_id', targetId);
    formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    
    fetch(copyUrl, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(data.message);
            const modalInstance = bootstrap.Modal.getInstance(document.getElementById('copyScheduleModal'));
            if (modalInstance) {
                modalInstance.hide();
            }
            location.reload();
        } else {
            alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Ошибка при копировании расписания');
    });
}

function applyTemplate() {
    const templateId = document.getElementById('templateSelect').value;
    const container = document.querySelector('[data-specialist-id]');
    const specialistId = container ? container.dataset.specialistId : null;
    
    if (!templateId) {
        alert('Выберите шаблон');
        return;
    }
    
    if (!confirm('Применить шаблон? Существующее расписание для дней из шаблона будет обновлено.')) {
        return;
    }
    
    const containerEl = document.querySelector('[data-apply-template-url]');
    const applyUrl = containerEl ? containerEl.dataset.applyTemplateUrl : null;
    if (!applyUrl) {
        alert('Ошибка: URL для применения шаблона не найден');
        return;
    }
    
    const formData = new FormData();
    formData.append('template_id', templateId);
    formData.append('specialist_id', specialistId);
    formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    
    fetch(applyUrl, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(data.message);
            const modalInstance = bootstrap.Modal.getInstance(document.getElementById('applyTemplateModal'));
            if (modalInstance) {
                modalInstance.hide();
            }
            location.reload();
        } else {
            alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Ошибка при применении шаблона');
    });
}

