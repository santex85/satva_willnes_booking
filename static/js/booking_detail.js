document.addEventListener('DOMContentLoaded', function() {
    const container = document.querySelector('.card-body');
    if (container && typeof initBookingEditForm === 'function') {
        initBookingEditForm(container, {
            onInit() {}
        });
    }
});

