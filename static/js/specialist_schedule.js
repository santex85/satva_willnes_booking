function toggleServices() {
    const hiddenServices = document.querySelectorAll('.service-hidden');
    const toggleBtn = document.getElementById('toggle-services-btn');
    
    if (!toggleBtn || hiddenServices.length === 0) return;
    
    const isHidden = hiddenServices[0].classList.contains('d-none');
    
    hiddenServices.forEach(function(service) {
        if (isHidden) {
            service.classList.remove('d-none');
        } else {
            service.classList.add('d-none');
        }
    });
    
    if (isHidden) {
        toggleBtn.innerHTML = '<i class="bi bi-chevron-up"></i> Скрыть';
    } else {
        const hiddenCount = hiddenServices.length;
        toggleBtn.innerHTML = `<i class="bi bi-chevron-down"></i> Показать еще (${hiddenCount})`;
    }
}

