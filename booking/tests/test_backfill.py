from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from booking.models import (
    Booking,
    Cabinet,
    CabinetType,
    Guest,
    Service,
    ServiceVariant,
    SpecialistProfile,
)


class BackfillGuestsTestCase(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username='backfill_admin', password='pass12345')

        self.cabinet_type = CabinetType.objects.create(name='Массажный')
        self.cabinet = Cabinet.objects.create(name='Кабинет 1', cabinet_type=self.cabinet_type)
        self.service = Service.objects.create(name='Тайский массаж')
        self.service.required_cabinet_types.add(self.cabinet_type)
        self.variant = ServiceVariant.objects.create(
            service=self.service,
            name_suffix='60 мин',
            duration_minutes=60,
            price=Decimal('3500.00'),
        )
        spec_user = User.objects.create_user(username='spec_bf', password='pass12345')
        self.specialist = SpecialistProfile.objects.create(user=spec_user, full_name='Мастер Тест')
        self.specialist.services_can_perform.add(self.service)

        # Две legacy-брони с одинаковым именем (разный регистр/пробелы)
        self._booking('Виктория Лоскутова', days=1)
        self._booking('виктория  лоскутова', days=2)
        # Legacy с другим именем
        self._booking('Иван Иванов', days=3)

    def _booking(self, guest_name, days):
        return Booking.objects.create(
            guest=None,
            guest_name=guest_name,
            service_variant=self.variant,
            specialist=self.specialist,
            cabinet=self.cabinet,
            start_time=timezone.now() - timedelta(days=days),
            status='confirmed',
            created_by=self.user,
        )

    def test_dry_run_creates_nothing(self):
        out = StringIO()
        call_command('backfill_guests', '--dry-run', stdout=out)
        self.assertEqual(Guest.objects.count(), 0)
        self.assertEqual(Booking.objects.filter(guest__isnull=True).count(), 3)

    def test_backfill_creates_and_links(self):
        out = StringIO()
        call_command('backfill_guests', stdout=out)

        # Две "Виктория Лоскутова" схлопываются в одного Guest, плюс "Иван Иванов"
        self.assertEqual(Guest.objects.count(), 2)
        self.assertEqual(Booking.objects.filter(guest__isnull=True).count(), 0)

        victoria = Guest.objects.get(normalized_name='Виктория Лоскутова')
        self.assertEqual(Booking.objects.filter(guest=victoria).count(), 2)

    def test_backfill_is_idempotent(self):
        call_command('backfill_guests', stdout=StringIO())
        guests_after_first = Guest.objects.count()
        call_command('backfill_guests', stdout=StringIO())
        self.assertEqual(Guest.objects.count(), guests_after_first)
        self.assertEqual(Booking.objects.filter(guest__isnull=True).count(), 0)
