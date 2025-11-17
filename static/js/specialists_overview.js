document.addEventListener('DOMContentLoaded', function() {
    const toggleButtons = document.querySelectorAll('[data-services-toggle]');
    toggleButtons.forEach((btn) => {
        const targetSelector = btn.getAttribute('data-bs-target');
        if (!targetSelector) return;
        const targetEl = document.querySelector(targetSelector);
        if (!targetEl) return;

        targetEl.addEventListener('show.bs.collapse', () => {
            btn.innerHTML = '<i class="bi bi-list-ul"></i> Скрыть услуги';
        });
        targetEl.addEventListener('hide.bs.collapse', () => {
            btn.innerHTML = '<i class="bi bi-list-ul"></i> Показать услуги';
        });
    });
});

