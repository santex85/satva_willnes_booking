document.addEventListener('DOMContentLoaded', function() {
    const slotRadios = document.querySelectorAll('.slot-radio');
    const cabinetSelections = document.querySelectorAll('.cabinet-selection');
    
    // Скрываем все выборы кабинетов при загрузке
    cabinetSelections.forEach(function(selection) {
        selection.style.display = 'none';
    });
    
    // Обработчик изменения выбора слота
    slotRadios.forEach(function(radio) {
        radio.addEventListener('change', function() {
            // Скрываем все выборы кабинетов
            cabinetSelections.forEach(function(selection) {
                selection.style.display = 'none';
                const select = selection.querySelector('.cabinet-select');
                if (select) {
                    select.removeAttribute('required');
                }
            });
            
            // Показываем выбор кабинета для выбранного слота
            if (this.checked) {
                const slotId = this.id;
                const cabinetSelection = document.querySelector('[data-slot-id="' + slotId + '"]');
                if (cabinetSelection) {
                    cabinetSelection.style.display = 'block';
                    const select = cabinetSelection.querySelector('.cabinet-select');
                    if (select) {
                        select.setAttribute('required', 'required');
                    }
                }
            }
        });
    });
    
    // Обработчик отправки формы - добавляем выбранный кабинет к значению слота
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function(e) {
            const selectedSlot = document.querySelector('.slot-radio:checked');
            if (!selectedSlot) {
                e.preventDefault();
                alert('Пожалуйста, выберите время');
                return false;
            }
            
            const slotId = selectedSlot.id;
            const cabinetSelect = document.querySelector('.cabinet-select[data-slot-id="' + slotId + '"]');
            
            if (cabinetSelect && cabinetSelect.value) {
                // Добавляем ID кабинета к значению слота
                selectedSlot.value = selectedSlot.value + '|' + cabinetSelect.value;
            } else if (cabinetSelect) {
                // Проверяем, есть ли доступные кабинеты
                if (cabinetSelect.options.length > 1) {
                    e.preventDefault();
                    alert('Пожалуйста, выберите кабинет');
                    return false;
                }
            }
        });
    }
});

