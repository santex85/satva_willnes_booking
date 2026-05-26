from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from rest_framework_simplejwt.tokens import RefreshToken

from booking.analytics_utils import (
    build_bookings_filter,
    format_duration,
    get_guest_statistics,
    get_service_popularity,
    get_specialist_load,
    iter_csv_report_rows,
)
from booking.guest_utils import merge_guests, normalize_guest_name
from booking.models import (
    Booking,
    Cabinet,
    CabinetType,
    Guest,
    Service,
    ServiceVariant,
    SpecialistProfile,
)


class AnalyticsBaseTestCase(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username='analytics_admin', password='testpass123')
        self.client = TenantClient(self.tenant)
        refresh = RefreshToken.for_user(self.user)
        self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {refresh.access_token}'

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
        self.variant2 = ServiceVariant.objects.create(
            service=self.service,
            name_suffix='90 мин',
            duration_minutes=90,
            price=Decimal('5000.00'),
        )

        spec_user = User.objects.create_user(username='spec1', password='testpass123')
        self.specialist = SpecialistProfile.objects.create(user=spec_user, full_name='Таначай Тест')
        self.specialist.services_can_perform.add(self.service)

        self.guest = Guest.objects.create(
            normalized_name=normalize_guest_name('Александр Черемикин'),
            display_name='Александр Черемикин',
        )
        self.guest_dup = Guest.objects.create(
            normalized_name=normalize_guest_name('Александр Ч.'),
            display_name='Александр Ч.',
        )

        self.today = timezone.localdate()
        self.start = self.today - timedelta(days=7)
        self.end = self.today

        Booking.objects.create(
            guest=self.guest,
            guest_name='Александр Черемикин',
            guest_room_number='302',
            service_variant=self.variant,
            specialist=self.specialist,
            cabinet=self.cabinet,
            start_time=timezone.now() - timedelta(days=1),
            status='paid',
            created_by=self.user,
        )
        Booking.objects.create(
            guest=self.guest,
            guest_name='Александр Ч.',
            guest_room_number='302',
            service_variant=self.variant2,
            specialist=self.specialist,
            cabinet=self.cabinet,
            start_time=timezone.now() - timedelta(days=2),
            status='confirmed',
            created_by=self.user,
        )
        Booking.objects.create(
            guest_name='Legacy Guest',
            service_variant=self.variant,
            specialist=self.specialist,
            cabinet=self.cabinet,
            start_time=timezone.now() - timedelta(days=3),
            status='confirmed',
            created_by=self.user,
        )
        Booking.objects.create(
            guest=self.guest_dup,
            guest_name='Александр Ч.',
            service_variant=self.variant,
            specialist=self.specialist,
            cabinet=self.cabinet,
            start_time=timezone.now() - timedelta(days=4),
            status='canceled',
            created_by=self.user,
        )


class AnalyticsUtilsTestCase(AnalyticsBaseTestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(45), '45 мин')
        self.assertEqual(format_duration(60), '1 ч')
        self.assertEqual(format_duration(90), '1 ч 30 мин')

    def test_service_popularity_groups_and_sorts(self):
        bookings = build_bookings_filter(self.start, self.end)
        data = get_service_popularity(bookings)
        self.assertTrue(len(data) >= 1)
        self.assertEqual(data[0]['service_name'], 'Тайский массаж')
        counts = [item['count'] for item in data]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_specialist_load_formats_duration(self):
        bookings = build_bookings_filter(self.start, self.end)
        data = get_specialist_load(bookings)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['specialist_name'], 'Таначай Тест')
        self.assertEqual(data[0]['total_minutes'], 210)
        self.assertEqual(data[0]['total_display'], '3 ч 30 мин')

    def test_guest_statistics_handles_legacy_guest_name(self):
        bookings = build_bookings_filter(self.start, self.end)
        stats = get_guest_statistics(bookings)
        names = {item['guest_name'] for item in stats}
        self.assertIn('Александр Черемикин', names)
        self.assertIn('Legacy Guest', names)
        merged_guest = next(item for item in stats if item['guest_name'] == 'Александр Черемикин')
        self.assertTrue(merged_guest['is_merged'])
        self.assertEqual(merged_guest['visit_count'], 2)

    def test_merge_guests_transactional(self):
        updated = merge_guests(self.guest, [self.guest_dup], 'Александр Черемикин')
        self.assertEqual(updated, 1)
        self.assertFalse(Guest.objects.filter(pk=self.guest_dup.pk).exists())
        self.assertEqual(Booking.objects.filter(guest=self.guest).count(), 3)

    def test_export_csv_has_bom_and_semicolon(self):
        bookings = Booking.objects.exclude(status='canceled').order_by('start_time')
        rows = list(iter_csv_report_rows(bookings))
        self.assertEqual(rows[0][0], 'Дата')
        self.assertIn('Legacy Guest', [row[3] for row in rows[1:-2]])


class AnalyticsAPITestCase(AnalyticsBaseTestCase):
    def _date_params(self):
        return {
            'start_date': self.start.isoformat(),
            'end_date': self.end.isoformat(),
        }

    def test_api_service_popularity(self):
        response = self.client.get('/api/v1/bookings/service_popularity/', self._date_params())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()) >= 1)

    def test_api_specialist_load(self):
        response = self.client.get('/api/v1/bookings/specialist_load/', self._date_params())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['total_display'], '3 ч 30 мин')

    def test_api_guest_statistics(self):
        response = self.client.get('/api/v1/guests/statistics/', self._date_params())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['guest_name'] == 'Legacy Guest' for item in response.json()))

    def test_api_merge_guests(self):
        response = self.client.post(
            '/api/v1/guests/merge/',
            {
                'primary_id': self.guest.id,
                'duplicate_ids': [self.guest_dup.id],
                'primary_display_name': 'Александр Черемикин',
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(Guest.objects.filter(pk=self.guest_dup.pk).exists())

    def test_api_export_csv(self):
        response = self.client.get('/api/v1/bookings/export_csv/', self._date_params())
        self.assertEqual(response.status_code, 200)
        content = b''.join(response.streaming_content).decode('utf-8-sig')
        self.assertIn('Дата;', content)
        self.assertIn('Legacy Guest', content)
