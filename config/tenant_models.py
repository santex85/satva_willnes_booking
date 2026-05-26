from django_tenants.models import TenantMixin, DomainMixin
from django.db import models

class Client(TenantMixin):
    name = models.CharField(max_length=100, verbose_name="Название салона")
    created_on = models.DateField(auto_now_add=True, verbose_name="Дата создания")

    # Автоматическое создание схемы БД при сохранении клиента
    auto_create_schema = True

    class Meta:
        verbose_name = 'Клиент (Салон)'
        verbose_name_plural = 'Клиенты (Салоны)'

    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    class Meta:
        verbose_name = 'Домен субдомена'
        verbose_name_plural = 'Домены субдоменов'
