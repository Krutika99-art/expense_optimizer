from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Budget, Category, CategoryType, Expense, Income
from .views import _build_predictive_analytics


class RegisterViewTests(TestCase):
    def test_authenticated_user_can_open_register_page(self):
        user = User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='testpass123',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('register'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/register.html')


class CategoryTypeAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
        )

    def test_superuser_can_create_category_type_from_admin_page(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('admin_category_types'),
            {'name': 'Investments'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(CategoryType.objects.filter(name='Investments').exists())

    def test_category_display_uses_dynamic_category_type_name(self):
        category_type = CategoryType.objects.create(name='Taxes')
        category = Category.objects.create(name='Property Tax', category_type=category_type)

        self.assertEqual(category.get_category_type_display(), 'Taxes')


class PredictiveAnalyticsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='memberpass123',
        )
        category_type = CategoryType.objects.create(name='Needs')
        self.category = Category.objects.create(name='Food', category_type=category_type)

    def test_predictive_analytics_builds_future_forecast(self):
        today = timezone.localdate()
        Income.objects.create(
            user=self.user,
            amount='10000.00',
            income_date=today,
            description='Salary',
        )
        Budget.objects.create(
            user=self.user,
            category=self.category,
            month=today.month,
            year=today.year,
            amount='1000.00',
        )
        Expense.objects.create(
            user=self.user,
            category=self.category,
            amount='800.00',
            expense_date=today,
            description='Groceries',
        )

        predictions = _build_predictive_analytics(self.user)

        self.assertEqual(len(predictions['forecast_rows']), 3)
        self.assertIn('Next month forecast', predictions['summary'])
        self.assertIn(predictions['forecast_rows'][0]['risk_level'], ['Low', 'Medium', 'High'])

    def test_dashboard_renders_predictive_analytics(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Predictive Analytics')


class ExpenseFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='expenseuser',
            email='expense@example.com',
            password='expensepass123',
        )
        self.category_type = CategoryType.objects.create(name='Needs')
        self.category = Category.objects.create(name='Food', category_type=self.category_type)

    def test_add_expense_page_does_not_show_existing_category_selector(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('add_expense'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Existing Category')
        self.assertNotContains(response, 'Select an existing category')
        self.assertContains(response, 'Category Name')

    def test_add_expense_requires_new_category_fields(self):
        today = timezone.localdate()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('add_expense'),
            {
                'category': str(self.category.id),
                'amount': '100.00',
                'expense_date': today.isoformat(),
                'description': 'Lunch',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a category name and select a category type.')
        self.assertFalse(Expense.objects.filter(user=self.user, amount='100.00').exists())

    def test_add_expense_creates_expense_with_new_category(self):
        today = timezone.localdate()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('add_expense'),
            {
                'category_name': 'Transport',
                'category_type': str(self.category_type.id),
                'amount': '250.00',
                'expense_date': today.isoformat(),
                'description': 'Taxi',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Expense.objects.filter(user=self.user, category__name='Transport').exists())


class AiChatbotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='chatuser',
            email='chat@example.com',
            password='chatpass123',
        )
        category_type = CategoryType.objects.create(name='Daily')
        self.category = Category.objects.create(name='Food', category_type=category_type)

    def test_chatbot_page_renders_for_member(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('ai_chatbot'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI Finance Chatbot')

    def test_chatbot_reply_uses_user_financial_data(self):
        today = timezone.localdate()
        Expense.objects.create(
            user=self.user,
            category=self.category,
            amount='450.00',
            expense_date=today,
            description='Dinner',
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ai_chatbot_reply'),
            {'message': 'What is my biggest expense?'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Food', response.json()['reply'])

    def test_chatbot_page_post_displays_fallback_response(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ai_chatbot'),
            {'message': 'How risky are my finances?'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'How risky are my finances?')
        self.assertContains(response, 'Your current risk level')

    def test_chatbot_explains_how_system_works(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ai_chatbot_reply'),
            {'message': 'How does the whole system work?'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('add income, expenses, and category budgets', response.json()['reply'])

    def test_chatbot_explains_predictive_analytics_process(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ai_chatbot_reply'),
            {'message': 'How does predictive analytics work?'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('last 6 months', response.json()['reply'])
