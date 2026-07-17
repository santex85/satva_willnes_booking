from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context
from rest_framework import status
from config.models import Client, Domain

class TenantRegistrationTestCase(TenantTestCase):
    def setUp(self):
        super().setUp()
        
        # Switch to public schema context to create the public tenant and domain
        with schema_context('public'):
            self.public_tenant, _ = Client.objects.get_or_create(
                schema_name='public',
                defaults={'name': 'Public Shared Schema'}
            )
            self.public_domain, _ = Domain.objects.get_or_create(
                domain='testserver',
                tenant=self.public_tenant,
                defaults={'is_primary': True}
            )
        
        # Using TenantClient configured with the public tenant schema context
        self.client = TenantClient(self.public_tenant)

    def test_successful_registration(self):
        payload = {
            'name': 'Spa Aura Moscow',
            'subdomain': 'spa-aura',
            'email': 'admin@spaaura.ru',
            'password': 'supersecretpass123',
            'cabinets': ['Кабинет Релакс', 'Кабинет Арома', 'VIP Сьют'],
            'services': ['massage', 'facial', 'aromatherapy']
        }
        
        # Make request on public schema
        response = self.client.post('/api/v1/public/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['subdomain'], 'spa-aura')
        self.assertEqual(response.json()['domain'], 'spa-aura.localhost')

        with schema_context('public'):
            # Verify Client exists in DB
            client_exists = Client.objects.filter(schema_name='spa_aura').exists()
            self.assertTrue(client_exists)

            # Verify Domain exists in DB
            domain_exists = Domain.objects.filter(domain='spa-aura.localhost').exists()
            self.assertTrue(domain_exists)

    def test_missing_fields_validation(self):
        # Missing subdomain
        payload = {
            'name': 'Spa Aura Moscow',
            'email': 'admin@spaaura.ru',
            'password': 'supersecretpass123',
        }
        response = self.client.post('/api/v1/public/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

        # Missing name
        payload = {
            'subdomain': 'spa-aura',
            'email': 'admin@spaaura.ru',
            'password': 'supersecretpass123',
        }
        response = self.client.post('/api/v1/public/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

    def test_invalid_subdomain_format(self):
        # Subdomain with uppercase letters and spaces
        payload = {
            'name': 'Spa Aura Moscow',
            'subdomain': 'Spa Aura',
            'email': 'admin@spaaura.ru',
            'password': 'supersecretpass123',
        }
        response = self.client.post('/api/v1/public/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

        # Subdomain with special characters
        payload['subdomain'] = 'spa_aura!'
        response = self.client.post('/api/v1/public/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reserved_subdomain(self):
        payload = {
            'name': 'Spa Aura Moscow',
            'subdomain': 'public',
            'email': 'admin@spaaura.ru',
            'password': 'supersecretpass123',
        }
        response = self.client.post('/api/v1/public/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('зарезервирован', response.json()['error'])

    def test_registration_from_tenant_subdomain(self):
        # Create a tenant client representing a request coming from the active tenant (schema 'test')
        tenant_client = TenantClient(self.tenant)
        
        payload = {
            'name': 'Spa Aura Moscow',
            'subdomain': 'spa-aura-from-tenant',
            'email': 'admin@spaaura.ru',
            'password': 'supersecretpass123',
            'cabinets': ['Кабинет Релакс'],
            'services': ['massage']
        }
        
        # When sending from 'testserver' (tenant domain), the request is intercepted by TenantMainMiddleware
        # and runs in the 'test' schema context. Thanks to wrapping with schema_context('public') inside
        # views.py, it should still successfully create the tenant Client row in the public schema.
        response = tenant_client.post('/api/v1/public/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.json()['success'])
        
        with schema_context('public'):
            self.assertTrue(Client.objects.filter(schema_name='spa_aura_from_tenant').exists())

