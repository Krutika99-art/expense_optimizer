import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import ActivityLog, Budget, Category, CategoryType, Expense, Income, Notification, UserProfile


def landing(request):
    return render(request, 'landing.html')


def _get_role_home_url(user):
    if user.is_superuser:
        return reverse_lazy('admin_analytics')
    return reverse_lazy('dashboard')


def _is_valid_password_length(password):
    return len(password or '') >= 8


class CustomAuthenticationForm(AuthenticationForm):
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if password and not _is_valid_password_length(password):
            raise forms.ValidationError('Password must be at least 8 characters long.')

        return super().clean()


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = CustomAuthenticationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        data = kwargs.get('data')
        if data:
            data = data.copy()
            identifier = data.get('username', '').strip()
            if '@' in identifier:
                matched_user = User.objects.filter(email__iexact=identifier).first()
                if matched_user:
                    data['username'] = matched_user.username
            kwargs['data'] = data
        return kwargs

    def get_success_url(self):
        return _get_role_home_url(self.request.user)


def _log_activity(user, action):
    ActivityLog.objects.create(user=user, action=action)


def _create_notification(user, message):
    recent_since = timezone.now() - timedelta(hours=12)
    exists = Notification.objects.filter(
        user=user,
        message=message,
        created_at__gte=recent_since,
    ).exists()
    if not exists:
        Notification.objects.create(user=user, message=message)


def _get_category_types():
    return CategoryType.objects.order_by('name')


def _get_monthly_income_total(user, year, month):
    return (
        Income.objects.filter(
            user=user,
            income_date__year=year,
            income_date__month=month,
        ).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )


def _get_monthly_expense_total(user, year, month):
    return (
        Expense.objects.filter(
            user=user,
            expense_date__year=year,
            expense_date__month=month,
        ).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )


def _get_monthly_budget_total(user, year, month):
    return (
        Budget.objects.filter(
            user=user,
            year=year,
            month=month,
        ).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )


def register(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        if not username or not email or not password1 or not password2:
            messages.error(request, 'All fields are required.')
        elif not _is_valid_password_length(password1):
            messages.error(request, 'Password must be at least 8 characters long.')
        elif password1 != password2:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
            )
            UserProfile.objects.create(user=user, role='MEMBER')

            messages.success(request, 'Registration successful. You can now log in.')
            return redirect('login')

    return render(request, 'registration/register.html')


def simple_password_reset(request):
    if request.user.is_authenticated:
        return redirect(_get_role_home_url(request.user))

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('new_password1', '')
        password2 = request.POST.get('new_password2', '')

        if not username or not email or not password1 or not password2:
            messages.error(request, 'All fields are required.')
        elif password1 != password2:
            messages.error(request, 'New password and confirm password must match.')
        else:
            user = User.objects.filter(username=username, email=email).first()
            if not user:
                messages.error(request, 'No account found with the provided username and email.')
            else:
                user.set_password(password1)
                user.save(update_fields=['password'])
                messages.success(request, 'Password reset successful. Please login.')
                return redirect('login')

    return render(request, 'registration/password_reset_form.html')


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={'role': 'MEMBER'},
    )
    return render(
        request,
        'profile.html',
        {
            'profile_user': request.user,
            'profile': profile,
        },
    )


@login_required
def edit_profile(request):
    user = request.user
    form_data = {
        'username': user.username,
        'email': user.email,
    }
    form_errors = []

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        form_data['username'] = username
        form_data['email'] = email

        if not username:
            form_errors.append('Username is required.')
        elif User.objects.filter(username=username).exclude(id=user.id).exists():
            form_errors.append('Username already exists.')

        if not email:
            form_errors.append('Email is required.')

        password_changed = bool(password1 or password2)
        if password_changed and password1 != password2:
            form_errors.append('Password and confirm password must match.')

        if not form_errors:
            user.username = username
            user.email = email
            if password_changed:
                user.set_password(password1)
            user.save()

            if password_changed:
                authenticated_user = authenticate(
                    request,
                    username=user.username,
                    password=password1,
                )
                if authenticated_user:
                    auth_login(request, authenticated_user)

            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')

        messages.error(request, 'Please correct the highlighted errors.')

    return render(
        request,
        'edit_profile.html',
        {
            'form_data': form_data,
            'form_errors': form_errors,
        },
    )


def _calculate_user_financials(user):
    user_expenses = Expense.objects.filter(user=user)

    total_income = (
        Income.objects.filter(user=user).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )
    total_expense = (
        user_expenses.aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )
    total_budget = (
        Budget.objects.filter(user=user).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )

    savings = total_income - total_expense
    income_gap_to_budget = max(Decimal('0.00'), total_budget - total_income)
    income_gap_to_expense = max(Decimal('0.00'), total_expense - total_income)

    if total_budget > 0:
        budget_utilization = ((total_expense / total_budget) * Decimal('100')).quantize(Decimal('0.01'))
    else:
        budget_utilization = Decimal('0.00')

    if budget_utilization >= Decimal('100.00'):
        utilization_status = 'Overspending'
        utilization_color = 'danger'
    elif budget_utilization >= Decimal('80.00'):
        utilization_status = 'Warning'
        utilization_color = 'warning'
    else:
        utilization_status = 'Safe'
        utilization_color = 'success'

    if total_income > 0:
        health_score = (savings / total_income) * Decimal('100.00')
        health_score = max(Decimal('0.00'), min(Decimal('100.00'), health_score))
    else:
        health_score = Decimal('0.00')
    health_score = health_score.quantize(Decimal('0.01'))

    if health_score >= Decimal('70.00'):
        health_status = 'Excellent'
        health_color = 'success'
    elif health_score >= Decimal('50.00'):
        health_status = 'Good'
        health_color = 'primary'
    elif health_score >= Decimal('30.00'):
        health_status = 'Average'
        health_color = 'warning'
    else:
        health_status = 'Poor'
        health_color = 'danger'

    bes = Decimal('0.00')
    if total_budget > 0:
        bes = max(Decimal('0.00'), Decimal('100.00') - budget_utilization)

    sss = max(Decimal('0.00'), min(Decimal('100.00'), health_score))

    current_date = timezone.localdate()
    current_month_expense = (
        user_expenses.filter(
            expense_date__year=current_date.year,
            expense_date__month=current_date.month,
        ).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )
    prev_month_last_day = current_date.replace(day=1) - timedelta(days=1)
    previous_month_expense = (
        user_expenses.filter(
            expense_date__year=prev_month_last_day.year,
            expense_date__month=prev_month_last_day.month,
        ).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )
    if previous_month_expense > 0:
        variation = (
            abs(current_month_expense - previous_month_expense)
            / previous_month_expense
            * Decimal('100.00')
        )
        ess = max(Decimal('0.00'), Decimal('100.00') - variation)
    else:
        ess = Decimal('100.00')
    ess = max(Decimal('0.00'), min(Decimal('100.00'), ess))

    category_totals = list(
        user_expenses.values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    highest_category = category_totals[0] if category_totals else None
    least_category = category_totals[-1] if category_totals else None
    highest_category_total = highest_category['total'] if highest_category else Decimal('0.00')

    if total_expense > 0:
        highest_category_percentage = (highest_category_total / total_expense) * Decimal('100.00')
        ccs = max(Decimal('0.00'), Decimal('100.00') - highest_category_percentage)
    else:
        highest_category_percentage = Decimal('0.00')
        ccs = Decimal('100.00')
    ccs = max(Decimal('0.00'), min(Decimal('100.00'), ccs))

    foi = (
        Decimal('0.35') * bes
        + Decimal('0.35') * sss
        + Decimal('0.15') * ess
        + Decimal('0.15') * ccs
    ).quantize(Decimal('0.01'))

    if foi >= Decimal('80.00'):
        foi_status = 'Highly Optimized'
        foi_color = 'success'
    elif foi >= Decimal('60.00'):
        foi_status = 'Moderately Optimized'
        foi_color = 'primary'
    elif foi >= Decimal('40.00'):
        foi_status = 'Needs Attention'
        foi_color = 'warning'
    else:
        foi_status = 'Financial Risk'
        foi_color = 'danger'

    current_month_start = current_date.replace(day=1)
    month_starts = []
    for offset in range(5, -1, -1):
        year = current_month_start.year
        month = current_month_start.month - offset
        while month <= 0:
            month += 12
            year -= 1
        month_starts.append(date(year, month, 1))
    trend_start_date = month_starts[0]

    expense_by_month = {
        (item['month'].date() if hasattr(item['month'], 'date') else item['month']): item['total']
        for item in (
            Expense.objects.filter(user=user, expense_date__gte=trend_start_date)
            .annotate(month=TruncMonth('expense_date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
    }
    income_by_month = {
        (item['month'].date() if hasattr(item['month'], 'date') else item['month']): item['total']
        for item in (
            Income.objects.filter(user=user, income_date__gte=trend_start_date)
            .annotate(month=TruncMonth('income_date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
    }
    budget_by_month = {
        (item['year'], item['month']): item['total']
        for item in (
            Budget.objects.filter(user=user, year__gte=trend_start_date.year)
            .values('year', 'month')
            .annotate(total=Sum('amount'))
            .order_by('year', 'month')
        )
    }

    trend_months = []
    expense_values = []
    income_values = []
    budget_values = []
    savings_values = []
    for month_start in month_starts:
        trend_months.append(month_start.strftime('%b %Y'))
        month_expense = expense_by_month.get(month_start, Decimal('0.00'))
        month_income = income_by_month.get(month_start, Decimal('0.00'))
        month_budget = budget_by_month.get((month_start.year, month_start.month), Decimal('0.00'))
        expense_values.append(float(month_expense))
        income_values.append(float(month_income))
        budget_values.append(float(month_budget))
        savings_values.append(month_income - month_expense)

    increasing_expense_trend = False
    increase_streak = 0
    for i in range(1, len(expense_values)):
        if expense_values[i] > expense_values[i - 1]:
            increase_streak += 1
            if increase_streak >= 3:
                increasing_expense_trend = True
                break
        else:
            increase_streak = 0

    savings_improving = (
        len(savings_values) >= 3
        and savings_values[-1] > savings_values[-2] > savings_values[-3]
    )

    alerts = []
    if total_budget > total_income:
        alerts.append(
            {
                'level': 'warning',
                'message': (
                    f"Budget is higher than income by {income_gap_to_budget}. "
                    'Consider lowering the budget or increasing income.'
                ),
            }
        )
    if total_expense > total_income:
        alerts.append(
            {
                'level': 'danger',
                'message': (
                    f"Expenses are higher than income by {income_gap_to_expense}. "
                    'Reduce spending to avoid running a deficit.'
                ),
            }
        )
    if total_expense > 0 and highest_category and highest_category_percentage > Decimal('40.00'):
        alerts.append(
            {
                'level': 'warning',
                'message': (
                    f"High concentration in {highest_category['category__name']}. "
                    'Consider cost control.'
                ),
            }
        )
    if foi < Decimal('40.00'):
        alerts.append({'level': 'danger', 'message': 'Financial Risk detected.'})
    negative_savings_streak = 0
    continuous_negative_savings = False
    for value in savings_values:
        if value < 0:
            negative_savings_streak += 1
            if negative_savings_streak >= 2:
                continuous_negative_savings = True
                break
        else:
            negative_savings_streak = 0
    if continuous_negative_savings:
        alerts.append({'level': 'danger', 'message': 'Continuous negative savings trend.'})

    return {
        'total_income': total_income,
        'total_expense': total_expense,
        'total_budget': total_budget,
        'savings': savings,
        'income_gap_to_budget': income_gap_to_budget,
        'income_gap_to_expense': income_gap_to_expense,
        'budget_utilization': budget_utilization,
        'utilization_status': utilization_status,
        'utilization_color': utilization_color,
        'health_score': health_score,
        'financial_health_score': health_score,
        'health_status': health_status,
        'health_color': health_color,
        'foi': foi,
        'foi_status': foi_status,
        'foi_color': foi_color,
        'top_category': highest_category['category__name'] if highest_category else 'N/A',
        'top_category_percentage': highest_category_percentage,
        'least_category': least_category['category__name'] if least_category else 'N/A',
        'alerts': alerts,
        'trend_months': trend_months,
        'expense_values': expense_values,
        'income_values': income_values,
        'budget_values': budget_values,
        'increasing_expense_trend': increasing_expense_trend,
        'savings_improving': savings_improving,
    }


def _calculate_user_risk(user, financials):
    budget_utilization = financials.get('budget_utilization', Decimal('0.00'))
    savings = financials.get('savings', Decimal('0.00'))
    health_score = financials.get('health_score', Decimal('0.00'))

    current_date = timezone.localdate()
    previous_month_last_day = current_date.replace(day=1) - timedelta(days=1)

    current_month_expense = (
        Expense.objects.filter(
            user=user,
            expense_date__year=current_date.year,
            expense_date__month=current_date.month,
        ).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )
    previous_month_expense = (
        Expense.objects.filter(
            user=user,
            expense_date__year=previous_month_last_day.year,
            expense_date__month=previous_month_last_day.month,
        ).aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )

    if previous_month_expense > 0:
        growth_rate = (
            ((current_month_expense - previous_month_expense) / previous_month_expense)
            * Decimal('100.00')
        )
    else:
        growth_rate = Decimal('0.00')
    growth_rate = growth_rate.quantize(Decimal('0.01'))

    risk_score = 0
    if savings < 0:
        risk_score += 40
    if growth_rate > Decimal('25.00'):
        risk_score += 30
    if budget_utilization > Decimal('80.00'):
        risk_score += 20
    if health_score < Decimal('30.00'):
        risk_score += 10

    if risk_score <= 20:
        risk_level = 'Low Risk'
        badge_color = 'success'
    elif risk_score <= 40:
        risk_level = 'Moderate Risk'
        badge_color = 'warning'
    elif risk_score <= 70:
        risk_level = 'High Risk'
        badge_color = 'danger'
    else:
        risk_level = 'Critical Risk'
        badge_color = 'dark'

    return {
        'risk_level': risk_level,
        'risk_score': risk_score,
        'growth_rate': growth_rate,
        'expense_growth': growth_rate,
        'risk_badge_color': badge_color,
    }


def _format_money(value):
    return f"{(value or Decimal('0.00')).quantize(Decimal('0.01'))}"


def _shift_month(month_start, offset):
    year = month_start.year
    month = month_start.month + offset
    while month > 12:
        month -= 12
        year += 1
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _forecast_series(values, periods=3):
    if not values:
        return [Decimal('0.00') for _ in range(periods)]

    weights = [Decimal(index + 1) for index in range(len(values))]
    weighted_total = sum(value * weight for value, weight in zip(values, weights))
    baseline = weighted_total / sum(weights)

    changes = [
        values[index] - values[index - 1]
        for index in range(1, len(values))
    ]
    average_change = Decimal('0.00')
    if changes:
        average_change = sum(changes) / Decimal(len(changes))

    forecasts = []
    for period in range(1, periods + 1):
        predicted_value = baseline + (average_change * Decimal(period))
        forecasts.append(max(Decimal('0.00'), predicted_value).quantize(Decimal('0.01')))
    return forecasts


def _build_predictive_analytics(user):
    current_date = timezone.localdate()
    current_month_start = current_date.replace(day=1)
    historical_months = [_shift_month(current_month_start, offset) for offset in range(-5, 1)]
    future_months = [_shift_month(current_month_start, offset) for offset in range(1, 4)]
    trend_start_date = historical_months[0]

    expense_by_month = {
        (item['month'].date() if hasattr(item['month'], 'date') else item['month']): item['total']
        for item in (
            Expense.objects.filter(user=user, expense_date__gte=trend_start_date)
            .annotate(month=TruncMonth('expense_date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
    }
    income_by_month = {
        (item['month'].date() if hasattr(item['month'], 'date') else item['month']): item['total']
        for item in (
            Income.objects.filter(user=user, income_date__gte=trend_start_date)
            .annotate(month=TruncMonth('income_date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
    }
    budget_by_month = {
        (item['year'], item['month']): item['total']
        for item in (
            Budget.objects.filter(user=user, year__gte=trend_start_date.year)
            .values('year', 'month')
            .annotate(total=Sum('amount'))
            .order_by('year', 'month')
        )
    }

    expense_history = [
        expense_by_month.get(month_start, Decimal('0.00'))
        for month_start in historical_months
    ]
    income_history = [
        income_by_month.get(month_start, Decimal('0.00'))
        for month_start in historical_months
    ]
    budget_history = [
        budget_by_month.get((month_start.year, month_start.month), Decimal('0.00'))
        for month_start in historical_months
    ]

    expense_forecast = _forecast_series(expense_history)
    income_forecast = _forecast_series(income_history)
    budget_forecast = _forecast_series(budget_history)
    if all(value == Decimal('0.00') for value in budget_forecast):
        latest_budget = next((value for value in reversed(budget_history) if value > 0), Decimal('0.00'))
        budget_forecast = [latest_budget for _ in future_months]

    forecast_rows = []
    for index, month_start in enumerate(future_months):
        predicted_expense = expense_forecast[index]
        predicted_income = income_forecast[index]
        predicted_budget = budget_forecast[index]
        predicted_savings = (predicted_income - predicted_expense).quantize(Decimal('0.01'))

        if predicted_income > 0 and predicted_expense > predicted_income:
            risk_level = 'High'
            risk_color = 'danger'
        elif predicted_budget > 0 and predicted_expense > predicted_budget:
            risk_level = 'Medium'
            risk_color = 'warning'
        else:
            risk_level = 'Low'
            risk_color = 'success'

        forecast_rows.append(
            {
                'month': month_start.strftime('%b %Y'),
                'expense': predicted_expense,
                'income': predicted_income,
                'budget': predicted_budget,
                'savings': predicted_savings,
                'risk_level': risk_level,
                'risk_color': risk_color,
            }
        )

    first_forecast = forecast_rows[0] if forecast_rows else None
    summary = 'Add income, expense, and budget history to unlock reliable forecasts.'
    headline_color = 'secondary'
    if first_forecast:
        summary = (
            f"Next month forecast: expense {_format_money(first_forecast['expense'])}, "
            f"income {_format_money(first_forecast['income'])}, "
            f"savings {_format_money(first_forecast['savings'])}."
        )
        headline_color = first_forecast['risk_color']

    return {
        'summary': summary,
        'headline_color': headline_color,
        'forecast_rows': forecast_rows,
        'history_labels': [month_start.strftime('%b %Y') for month_start in historical_months],
        'future_labels': [month_start.strftime('%b %Y') for month_start in future_months],
        'expense_history_values': [float(value) for value in expense_history],
        'income_history_values': [float(value) for value in income_history],
        'expense_forecast_values': [float(value) for value in expense_forecast],
        'income_forecast_values': [float(value) for value in income_forecast],
    }


def _get_top_expense_category(user):
    return (
        Expense.objects.filter(user=user)
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
        .first()
    )


def _get_system_chatbot_response(message):
    lowered_message = (message or '').lower()
    asks_how = any(phrase in lowered_message for phrase in ['how', 'process', 'workflow', 'flow', 'steps', 'guide'])

    if any(phrase in lowered_message for phrase in ['whole process', 'whole system', 'system works', 'system work', 'how system', 'how the system', 'workflow', 'process works']):
        return (
            'The system works in a simple flow: first you add income, expenses, and category budgets. '
            'Then the app groups your records by month and category, compares budget vs actual spending, '
            'calculates savings and risk, and shows dashboards, charts, notifications, reports, and future forecasts. '
            'The AI chatbot sits on top of that data so you can ask questions in plain language instead of reading every table manually.'
        )

    if asks_how and any(word in lowered_message for word in ['use', 'start', 'begin', 'operate']):
        return (
            'To use the app, start by adding income, then create budgets for categories, then record expenses regularly. '
            'Open the Dashboard for quick totals, Financial Overview for health/risk/trends, Category Analysis for budget vs expense details, '
            'and Predictive Analytics to see the next 3 months forecast.'
        )

    if asks_how and any(word in lowered_message for word in ['predict', 'prediction', 'forecast', 'future', 'analytics']):
        return (
            'Predictive analytics uses your last 6 months of income, expense, and budget history. '
            'It gives recent months more weight, calculates the average monthly change, and predicts the next 3 months. '
            'Each future month is marked Low, Medium, or High risk depending on whether predicted expenses exceed budget or income.'
        )

    if (
        any(phrase in lowered_message for phrase in ['risk score', 'health score', 'foi', 'optimization index'])
        or (
            asks_how
            and any(word in lowered_message for word in ['score', 'foi', 'optimization'])
            and any(word in lowered_message for word in ['calculate', 'work', 'system', 'process'])
        )
    ):
        return (
            'The app estimates financial health using savings, budget utilization, expense stability, and category concentration. '
            'Risk increases when savings are negative, expenses grow quickly, budget utilization crosses safe limits, or the health score is low. '
            'The Financial Optimization Index summarizes how optimized the account is.'
        )

    if asks_how and any(word in lowered_message for word in ['report', 'pdf', 'csv', 'excel', 'download', 'export']):
        return (
            'Reports collect your key income, expense, budget, savings, risk, and optimization metrics into downloadable files. '
            'Use PDF for a readable summary, CSV for spreadsheet analysis, and Excel when available for a workbook-style export.'
        )

    if asks_how and any(word in lowered_message for word in ['notification', 'alert', 'warning']):
        return (
            'Notifications are created when the system detects important conditions, such as budget utilization above 80%, '
            'expenses higher than income, low financial health, high category concentration, critical risk, or a high-risk future forecast.'
        )

    if asks_how and any(word in lowered_message for word in ['category', 'categories']):
        return (
            'Categories organize expenses and budgets, such as Food, Travel, Bills, or Education. '
            'Category Analysis compares how much you planned for each category against how much you actually spent, '
            'then highlights over-budget areas and spending concentration.'
        )

    if asks_how and any(word in lowered_message for word in ['budget', 'expense', 'income']):
        return (
            'Income records money coming in, expenses record money going out, and budgets define planned spending limits by category and month. '
            'The system compares these three pieces to calculate savings, utilization, overspending, trends, and future risk.'
        )

    if any(phrase in lowered_message for phrase in ['features', 'what features', 'modules', 'pages']):
        return (
            'Main features include user registration/login, income tracking, expense tracking, category management, monthly budgets, '
            'dashboard KPIs, financial overview, category analysis, predictive analytics, notifications, downloadable reports, '
            'admin analytics, and this AI chatbot.'
        )

    if any(phrase in lowered_message for phrase in ['about project', 'about this project', 'what is this project', 'purpose']):
        return (
            'This project is an Expense Optimizer. Its purpose is to help users record financial activity, compare budgets with real spending, '
            'understand savings and risk, forecast future financial behavior, and make better budgeting decisions.'
        )

    return None


def _build_chatbot_response(user, message):
    cleaned_message = (message or '').strip()
    lowered_message = cleaned_message.lower()

    if not cleaned_message:
        return {
            'reply': 'Ask me about your spending, savings, budget, risk, next month forecast, or how the system works.',
            'suggestions': _get_chatbot_suggestions(),
        }

    system_reply = _get_system_chatbot_response(cleaned_message)
    if system_reply:
        return {
            'reply': system_reply,
            'suggestions': _get_chatbot_suggestions(),
        }

    financials = _calculate_user_financials(user)
    risk = _calculate_user_risk(user, financials)
    predictions = _build_predictive_analytics(user)
    next_forecast = predictions['forecast_rows'][0] if predictions['forecast_rows'] else None
    top_category = _get_top_expense_category(user)

    if any(word in lowered_message for word in ['forecast', 'predict', 'future', 'next month', 'upcoming']):
        if next_forecast:
            reply = (
                f"For {next_forecast['month']}, I predict income of {_format_money(next_forecast['income'])}, "
                f"expenses of {_format_money(next_forecast['expense'])}, and savings of "
                f"{_format_money(next_forecast['savings'])}. The forecast risk level is "
                f"{next_forecast['risk_level']}."
            )
        else:
            reply = 'I need more income and expense history before I can make a useful forecast.'
    elif any(word in lowered_message for word in ['risk', 'danger', 'safe', 'health']):
        reply = (
            f"Your current risk level is {risk['risk_level']} with a score of {risk['risk_score']}. "
            f"Financial health is {financials['health_status']} at {financials['health_score']}%."
        )
    elif any(word in lowered_message for word in ['budget', 'over budget', 'limit']):
        reply = (
            f"Your total budget is {_format_money(financials['total_budget'])} and total expenses are "
            f"{_format_money(financials['total_expense'])}. Budget utilization is "
            f"{financials['budget_utilization']}%, marked as {financials['utilization_status']}."
        )
    elif any(word in lowered_message for word in ['save', 'saving', 'savings']):
        reply = (
            f"Your current savings are {_format_money(financials['savings'])}. "
            f"Your financial optimization index is {financials['foi']}%, which is "
            f"{financials['foi_status']}."
        )
    elif any(word in lowered_message for word in ['spend', 'expense', 'category', 'highest', 'top']):
        if top_category:
            reply = (
                f"Your highest spending category is {top_category['category__name']} with "
                f"{_format_money(top_category['total'])} spent. Total expenses are "
                f"{_format_money(financials['total_expense'])}."
            )
        else:
            reply = 'I do not see expense data yet. Add expenses and I can identify your top category.'
    elif any(word in lowered_message for word in ['income', 'earn', 'salary']):
        reply = (
            f"Your recorded income total is {_format_money(financials['total_income'])}. "
            f"Compared with expenses of {_format_money(financials['total_expense'])}, "
            f"your net savings are {_format_money(financials['savings'])}."
        )
    elif any(word in lowered_message for word in ['help', 'what can you do', 'commands']):
        reply = (
            'I can explain your spending, budget usage, savings, risk level, top category, future predictions, '
            'and how the whole Expense Optimizer system works. Try asking: "How does the system work?", '
            '"How does predictive analytics work?", or "Am I over budget?"'
        )
    else:
        reply = (
            f"Here is the quick picture: income {_format_money(financials['total_income'])}, "
            f"expenses {_format_money(financials['total_expense'])}, savings "
            f"{_format_money(financials['savings'])}, and risk {risk['risk_level']}. "
            'You can ask me to explain forecast, budget, savings, or top spending category.'
        )

    return {
        'reply': reply,
        'suggestions': _get_chatbot_suggestions(),
    }


def _get_chatbot_suggestions():
    return [
        'How does the system work?',
        'How does prediction work?',
        'Predict my next month',
        'Am I over budget?',
    ]


def _build_admin_analytics_context():
    total_users = User.objects.count()
    users = list(User.objects.filter(is_superuser=False))
    total_accounts = len(users)
    total_expense = Expense.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_income = Income.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_budget = Budget.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    user_metrics = []
    foi_sum = Decimal('0.00')
    for account in users:
        financials = _calculate_user_financials(account)
        risk_metrics = _calculate_user_risk(account, financials)
        foi_sum += financials['foi']
        user_metrics.append(
            {
                'user': account,
                'username': account.username,
                'email': account.email or '',
                'total_income': financials['total_income'],
                'total_expense': financials['total_expense'],
                'total_budget': financials['total_budget'],
                'foi': financials['foi'],
                'risk_score': risk_metrics['risk_score'],
                'risk_level': risk_metrics['risk_level'],
                'growth_rate': risk_metrics['growth_rate'],
            }
        )

    average_foi = Decimal('0.00')
    if users:
        average_foi = (foi_sum / Decimal(len(users))).quantize(Decimal('0.01'))

    top_risk_accounts = sorted(user_metrics, key=lambda item: item['risk_score'], reverse=True)[:5]
    top_performing_accounts = sorted(user_metrics, key=lambda item: item['foi'], reverse=True)[:5]
    highest_risk_account = top_risk_accounts[0] if top_risk_accounts else None
    risk_rows = sorted(user_metrics, key=lambda item: item['risk_score'], reverse=True)
    high_risk_accounts_count = sum(1 for item in risk_rows if item['risk_score'] >= 70)

    most_common_category = (
        Expense.objects.values('category__name')
        .annotate(expense_count=Count('id'))
        .order_by('-expense_count')
        .first()
    )

    current_date = timezone.localdate()
    current_month_start = current_date.replace(day=1)
    month_starts = []
    for offset in range(5, -1, -1):
        year = current_month_start.year
        month = current_month_start.month - offset
        while month <= 0:
            month += 12
            year -= 1
        month_starts.append(date(year, month, 1))
    trend_start_date = month_starts[0]

    expense_by_month = {
        (item['month'].date() if hasattr(item['month'], 'date') else item['month']): item['total']
        for item in (
            Expense.objects.filter(expense_date__gte=trend_start_date)
            .annotate(month=TruncMonth('expense_date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
    }
    trend_months = [month_start.strftime('%b %Y') for month_start in month_starts]
    system_expense_values = [
        float(expense_by_month.get(month_start, Decimal('0.00')))
        for month_start in month_starts
    ]
    income_by_month = {
        (item['month'].date() if hasattr(item['month'], 'date') else item['month']): item['total']
        for item in (
            Income.objects.filter(income_date__gte=trend_start_date)
            .annotate(month=TruncMonth('income_date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )
    }
    system_income_values = [
        float(income_by_month.get(month_start, Decimal('0.00')))
        for month_start in month_starts
    ]

    category_spending = list(
        Expense.objects.values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')[:6]
    )
    category_labels = [item['category__name'] or 'Uncategorized' for item in category_spending]
    category_values = [float(item['total'] or Decimal('0.00')) for item in category_spending]
    top_categories = category_spending[:5]

    recent_activities = []
    for account in User.objects.order_by('-date_joined')[:3]:
        recent_activities.append(
            {
                'icon': 'bi-person-plus-fill',
                'message': f"{account.username} account was created",
                'timestamp': account.date_joined.strftime('%d %b %Y, %I:%M %p'),
                'sort_key': account.date_joined,
            }
        )
    for item in Expense.objects.select_related('user').order_by('-expense_date', '-id')[:3]:
        activity_time = timezone.make_aware(
            datetime.combine(item.expense_date, time.min),
            timezone.get_current_timezone(),
        )
        recent_activities.append(
            {
                'icon': 'bi-receipt-cutoff',
                'message': f"{item.user.username} added an expense",
                'timestamp': item.expense_date.strftime('%d %b %Y'),
                'sort_key': activity_time,
            }
        )
    for item in Income.objects.select_related('user').order_by('-income_date', '-id')[:2]:
        activity_time = timezone.make_aware(
            datetime.combine(item.income_date, time.min),
            timezone.get_current_timezone(),
        )
        recent_activities.append(
            {
                'icon': 'bi-cash-stack',
                'message': f"{item.user.username} recorded income",
                'timestamp': item.income_date.strftime('%d %b %Y'),
                'sort_key': activity_time,
            }
        )
    recent_activities = sorted(recent_activities, key=lambda item: item['sort_key'], reverse=True)[:6]

    admin_notifications = []
    for item in top_risk_accounts[:3]:
        if item['risk_score'] >= 70:
            admin_notifications.append(
                {
                    'message': f"{item['user'].username} is in the {item['risk_level'].lower()} risk zone.",
                    'timestamp': f"Risk score {item['risk_score']}",
                }
            )
    admin_notifications = admin_notifications[:3]

    return {
        'total_users': total_users,
        'total_accounts': total_accounts,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_budget': total_budget,
        'average_foi': average_foi,
        'high_risk_accounts_count': high_risk_accounts_count,
        'highest_risk_account': highest_risk_account,
        'most_common_category': most_common_category,
        'top_risk_accounts': top_risk_accounts,
        'top_performing_accounts': top_performing_accounts,
        'risk_rows': risk_rows,
        'recent_activities': recent_activities,
        'trend_months': trend_months,
        'system_expense_values': system_expense_values,
        'system_income_values': system_income_values,
        'category_labels': category_labels,
        'category_values': category_values,
        'top_categories': top_categories,
        'user_metrics': user_metrics,
        'admin_notifications': admin_notifications,
        'admin_notifications_count': len(admin_notifications),
        'generated_date': current_date.strftime('%Y-%m-%d'),
    }


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect('admin_analytics')

    financials = _calculate_user_financials(request.user)
    total_income = financials['total_income']
    total_expense = financials['total_expense']
    total_budget = financials['total_budget']

    net_savings = total_income - total_expense
    savings_rate = Decimal('0.00')
    if total_income > 0:
        savings_rate = ((net_savings / total_income) * Decimal('100')).quantize(Decimal('0.01'))

    context = {
        'total_income': total_income,
        'total_expense': total_expense,
        'total_budget': total_budget,
        'net_savings': net_savings,
        'savings_rate': savings_rate,
        'unread_notifications_count': Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count(),
        'predictive_analytics': _build_predictive_analytics(request.user),
    }
    return render(request, 'dashboard.html', context)


@login_required
def account_snapshot(request):
    metrics = _calculate_user_financials(request.user)
    account_metrics = [
        {
            'account_id': request.user.id,
            'account_name': request.user.username,
            'account_type': 'User Account',
            'total_income': metrics['total_income'],
            'total_expense': metrics['total_expense'],
            'total_budget': metrics['total_budget'],
            'savings': metrics['savings'],
            'utilization': metrics['budget_utilization'],
            'FOI': metrics['foi'],
        }
    ]

    context = {
        'account_metrics': account_metrics,
        'best_account': account_metrics[0],
        'lowest_account': account_metrics[0],
    }
    return render(request, 'account_snapshot.html', context)


@login_required
def financial_overview(request):
    context = {'account_name': f"{request.user.username}'s Finances"}
    context.update(_calculate_user_financials(request.user))
    context.update(_calculate_user_risk(request.user, context))
    context['predictive_analytics'] = _build_predictive_analytics(request.user)

    if context['budget_utilization'] > Decimal('80.00'):
        _create_notification(request.user, 'Budget utilization exceeds 80%.')
    if context['income_gap_to_budget'] > Decimal('0.00'):
        _create_notification(request.user, 'Budget is higher than income.')
    if context['income_gap_to_expense'] > Decimal('0.00'):
        _create_notification(request.user, 'Expenses are higher than income.')
    if context['financial_health_score'] < Decimal('30.00'):
        _create_notification(request.user, 'Financial health score is low.')
    if context.get('top_category_percentage', Decimal('0.00')) > Decimal('50.00'):
        _create_notification(request.user, 'High concentration in a single category.')
    if context['risk_score'] > 70:
        _create_notification(request.user, 'Financial risk score is critical.')
    next_forecast = context['predictive_analytics']['forecast_rows'][0] if context['predictive_analytics']['forecast_rows'] else None
    if next_forecast and next_forecast['risk_level'] == 'High':
        _create_notification(request.user, 'Predictive analytics shows high risk next month.')

    return render(request, 'financial_overview.html', context)


@login_required
def ai_chatbot(request):
    if request.user.is_superuser:
        return redirect('admin_analytics')

    welcome = _build_chatbot_response(request.user, '')
    chat_messages = []
    if request.method == 'POST':
        user_message = request.POST.get('message', '').strip()
        if user_message:
            bot_response = _build_chatbot_response(request.user, user_message)
            chat_messages = [
                {'role': 'user', 'text': user_message},
                {'role': 'bot', 'text': bot_response['reply']},
            ]

    return render(
        request,
        'ai_chatbot.html',
        {
            'welcome_message': (
                'Hi, I am your AI finance assistant. Ask me about your expenses, '
                'budget, savings, risk, or future predictions.'
            ),
            'suggestions': welcome['suggestions'],
            'chat_messages': chat_messages,
        },
    )


@login_required
def ai_chatbot_reply(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method.'}, status=405)

    if request.user.is_superuser:
        return JsonResponse({'error': 'Chatbot is available for member accounts.'}, status=403)

    response = _build_chatbot_response(request.user, request.POST.get('message', ''))
    return JsonResponse(response)


@login_required
def notifications(request):
    notes = Notification.objects.filter(user=request.user).order_by('-created_at')
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'notifications.html', {'notifications': notes})


@login_required
def admin_activity_log(request):
    if not request.user.is_superuser:
        return redirect('dashboard')

    logs = ActivityLog.objects.select_related('user').order_by('-timestamp')
    return render(request, 'admin/admin_activity_log.html', {'logs': logs})


@login_required
def admin_analytics(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Not allowed')

    return render(request, 'admin_dashboard.html', _build_admin_analytics_context())


@login_required
def admin_system_reports(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Not allowed')

    return render(request, 'admin/admin_system_reports.html', _build_admin_analytics_context())


@login_required
def admin_financial_breakdown(request, metric_type):
    if not request.user.is_superuser:
        return redirect('dashboard')

    metric_map = {
        'income': {
            'label': 'Income',
            'model': Income,
            'date_field': 'income_date',
            'title': 'System Income by User',
        },
        'expense': {
            'label': 'Expense',
            'model': Expense,
            'date_field': 'expense_date',
            'title': 'System Expenses by User',
        },
        'budget': {
            'label': 'Budget',
            'model': Budget,
            'date_field': None,
            'title': 'System Budget by User',
        },
    }
    selected_metric = metric_map.get(metric_type)
    if not selected_metric:
        return redirect('admin_analytics')

    users = list(User.objects.filter(is_superuser=False).order_by('username'))
    rows = []
    total_amount = Decimal('0.00')
    model = selected_metric['model']
    date_field = selected_metric['date_field']

    for user in users:
        entries = model.objects.filter(user=user)
        amount = entries.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        if date_field:
            latest_entry = entries.order_by(f'-{date_field}', '-id').first()
            latest_date = getattr(latest_entry, date_field) if latest_entry else None
        else:
            latest_entry = entries.order_by('-year', '-month', '-id').first()
            latest_date = f"{latest_entry.month:02d}/{latest_entry.year}" if latest_entry else None

        rows.append(
            {
                'user': user,
                'amount': amount,
                'entry_count': entries.count(),
                'latest_date': latest_date,
            }
        )
        total_amount += amount

    rows.sort(key=lambda item: item['amount'], reverse=True)

    return render(
        request,
        'admin/admin_financial_breakdown.html',
        {
            'metric_type': metric_type,
            'metric_label': selected_metric['label'],
            'page_title': selected_metric['title'],
            'rows': rows,
            'total_amount': total_amount,
        },
    )


@login_required
def admin_users(request):
    if not request.user.is_superuser:
        return redirect('dashboard')

    users = User.objects.all().order_by('id')
    return render(request, 'admin/admin_users.html', {'users': users})


@login_required
def admin_accounts(request):
    if not request.user.is_superuser:
        return redirect('dashboard')

    users = User.objects.filter(is_superuser=False).order_by('id')
    return render(request, 'admin/admin_accounts.html', {'users': users})


@login_required
def admin_categories(request):
    if not request.user.is_superuser:
        return redirect('dashboard')

    form_data = {
        'name': '',
        'category_type': '',
    }

    if request.method == 'POST':
        form_data = {
            'name': request.POST.get('name', '').strip(),
            'category_type': request.POST.get('category_type', '').strip(),
        }

        if not form_data['name'] or not form_data['category_type']:
            messages.error(request, 'Category name and category type are required.')
        else:
            category_type = CategoryType.objects.filter(id=form_data['category_type']).first()
            if not category_type:
                messages.error(request, 'Please select a valid category type.')
            else:
                category, created = Category.objects.get_or_create(
                    name=form_data['name'],
                    category_type=category_type,
                )
                if created:
                    messages.success(request, 'Category created successfully.')
                    return redirect('admin_categories')
                messages.info(request, 'That category already exists.')

    categories = (
        Category.objects.annotate(
            expense_count=Count('expense', distinct=True),
            budget_count=Count('budget', distinct=True),
            usage_count=Count('expense', distinct=True) + Count('budget', distinct=True),
        )
        .select_related('category_type')
        .order_by('name', 'category_type__name')
    )

    return render(
        request,
        'admin/admin_categories.html',
        {
            'categories': categories,
            'category_types': _get_category_types(),
            'form_data': form_data,
            'total_categories': categories.count(),
        },
    )


@login_required
def edit_category(request, id):
    if not request.user.is_superuser:
        return redirect('dashboard')

    category = get_object_or_404(Category, id=id)
    form_data = {
        'name': category.name,
        'category_type': str(category.category_type_id),
    }

    if request.method == 'POST':
        form_data = {
            'name': request.POST.get('name', '').strip(),
            'category_type': request.POST.get('category_type', '').strip(),
        }

        if not form_data['name'] or not form_data['category_type']:
            messages.error(request, 'Category name and category type are required.')
        else:
            category_type = CategoryType.objects.filter(id=form_data['category_type']).first()
            if not category_type:
                messages.error(request, 'Please select a valid category type.')
            else:
                duplicate_exists = Category.objects.filter(
                    name=form_data['name'],
                    category_type=category_type,
                ).exclude(id=category.id).exists()

                if duplicate_exists:
                    messages.error(request, 'A category with the same name and type already exists.')
                else:
                    category.name = form_data['name']
                    category.category_type = category_type
                    category.save(update_fields=['name', 'category_type'])
                    messages.success(request, 'Category updated successfully.')
                    return redirect('admin_categories')

    return render(
        request,
        'admin/admin_edit_category.html',
        {
            'category': category,
            'category_types': _get_category_types(),
            'form_data': form_data,
        },
    )


@login_required
def admin_category_types(request):
    if not request.user.is_superuser:
        return redirect('dashboard')

    form_data = {'name': ''}

    if request.method == 'POST':
        form_data = {'name': request.POST.get('name', '').strip()}

        if not form_data['name']:
            messages.error(request, 'Category type name is required.')
        else:
            category_type, created = CategoryType.objects.get_or_create(name=form_data['name'])
            if created:
                messages.success(request, 'Category type created successfully.')
                return redirect('admin_category_types')
            messages.info(request, 'That category type already exists.')

    category_types = (
        CategoryType.objects.annotate(category_count=Count('categories', distinct=True))
        .order_by('name')
    )

    return render(
        request,
        'admin/admin_category_types.html',
        {
            'category_types': category_types,
            'form_data': form_data,
            'total_category_types': category_types.count(),
        },
    )


@login_required
def edit_category_type(request, id):
    if not request.user.is_superuser:
        return redirect('dashboard')

    category_type = get_object_or_404(CategoryType, id=id)
    form_data = {'name': category_type.name}

    if request.method == 'POST':
        form_data = {'name': request.POST.get('name', '').strip()}

        if not form_data['name']:
            messages.error(request, 'Category type name is required.')
        else:
            duplicate_exists = (
                CategoryType.objects.filter(name=form_data['name'])
                .exclude(id=category_type.id)
                .exists()
            )
            if duplicate_exists:
                messages.error(request, 'A category type with that name already exists.')
            else:
                category_type.name = form_data['name']
                category_type.save(update_fields=['name'])
                messages.success(request, 'Category type updated successfully.')
                return redirect('admin_category_types')

    return render(
        request,
        'admin/admin_edit_category_type.html',
        {
            'category_type': category_type,
            'form_data': form_data,
        },
    )


@login_required
def delete_category_type(request, id):
    if not request.user.is_superuser:
        return redirect('dashboard')

    if request.method != 'POST':
        return HttpResponseForbidden('Invalid request method.')

    category_type = get_object_or_404(CategoryType, id=id)
    next_url = request.POST.get('next', '').strip() or 'admin_category_types'

    if category_type.categories.exists():
        messages.error(request, 'This category type cannot be removed because it is already used by categories.')
        return redirect(next_url)

    category_type.delete()
    messages.success(request, 'Category type removed successfully.')
    return redirect(next_url)


@login_required
def delete_user(request, id):
    if not request.user.is_superuser:
        return redirect('dashboard')

    user = get_object_or_404(User, id=id)
    if user.id == request.user.id:
        messages.error(request, 'You cannot delete your own admin account.')
        return redirect('admin_users')

    user.delete()
    messages.success(request, 'User deleted successfully.')
    return redirect('admin_users')


@login_required
def toggle_user_status(request, id):
    if not request.user.is_superuser:
        return redirect('dashboard')

    user = get_object_or_404(User, id=id)
    if user.id == request.user.id:
        messages.error(request, 'You cannot disable your own admin account.')
        return redirect('admin_users')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    status = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f'User {user.username} {status} successfully.')
    return redirect('admin_users')


@login_required
def export_group_pdf(request, group_id=None):
    metrics = _calculate_user_financials(request.user)

    response = HttpResponse(content_type='application/pdf')
    safe_user_name = slugify(request.user.username) or 'user'
    response['Content-Disposition'] = f'attachment; filename="user_{safe_user_name}_report.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, title='User Financial Summary Report')
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph('<b>Expense and Budget Optimization Analysis</b>', styles['Title']))
    elements.append(Paragraph('<b>User Financial Summary Report</b>', styles['Heading2']))
    elements.append(Spacer(1, 12))

    generated_date = timezone.localdate().strftime('%Y-%m-%d')
    section_one = [
        ['Username', request.user.username],
        ['Generated Date', generated_date],
    ]
    section_one_table = Table(section_one, colWidths=[150, 340])
    section_one_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 1: User Details</b>', styles['Heading3']))
    elements.append(section_one_table)
    elements.append(Spacer(1, 12))

    metrics_table_data = [
        ['Metric', 'Value'],
        ['Total Income', str(metrics['total_income'])],
        ['Total Expense', str(metrics['total_expense'])],
        ['Total Budget', str(metrics['total_budget'])],
        ['Savings', str(metrics['savings'])],
        ['Budget Utilization', f"{metrics['budget_utilization']}%"],
        ['Financial Health Score', f"{metrics['financial_health_score']}%"],
        ['Financial Optimization Index (FOI)', f"{metrics['foi']}%"],
        ['FOI Status', metrics['foi_status']],
    ]
    metrics_table = Table(metrics_table_data, colWidths=[250, 240])
    metrics_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 2: Financial Metrics</b>', styles['Heading3']))
    elements.append(metrics_table)
    elements.append(Spacer(1, 12))

    insights_table_data = [
        ['Insight', 'Value'],
        ['Top Category', metrics['top_category']],
        ['Least Category', metrics['least_category']],
    ]
    insights_table = Table(insights_table_data, colWidths=[250, 240])
    insights_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#198754')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 3: Category Insights</b>', styles['Heading3']))
    elements.append(insights_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph('<b>Section 4: Alerts</b>', styles['Heading3']))
    if metrics['alerts']:
        for alert in metrics['alerts']:
            elements.append(Paragraph(f"- {alert['message']}", styles['BodyText']))
    else:
        elements.append(Paragraph('No critical alerts for this user.', styles['BodyText']))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph('<b>Section 5: Final Evaluation</b>', styles['Heading3']))
    elements.append(
        Paragraph(
            (
                f"Financial Optimization Index: <b>{metrics['foi']}%</b><br/>"
                f"Overall Status: <b>{metrics['foi_status']}</b>"
            ),
            styles['BodyText'],
        )
    )

    doc.build(elements)
    return response


@login_required
def export_admin_analytics_pdf(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Not allowed')

    context = _build_admin_analytics_context()
    total_users = context['total_accounts']
    total_income = context['total_income']
    total_expense = context['total_expense']
    total_budget = context['total_budget']
    average_foi = context['average_foi']
    user_metrics = context['user_metrics']
    top_risk_accounts = context['top_risk_accounts']
    top_categories = context['top_categories']

    response = HttpResponse(content_type='application/pdf')
    generated_date = context['generated_date']
    response['Content-Disposition'] = (
        f'attachment; filename="admin_analytics_report_{generated_date}.pdf"'
    )

    doc = SimpleDocTemplate(response, pagesize=A4, title='Admin Analytics Report')
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph('<b>Expense Optimizer</b>', styles['Title']))
    elements.append(Paragraph('<b>Admin Analytics Report</b>', styles['Heading2']))
    elements.append(Spacer(1, 12))

    overview_table = Table(
        [
            ['Generated Date', generated_date],
            ['Generated By', request.user.username],
            ['User Accounts', str(total_users)],
        ],
        colWidths=[170, 320],
    )
    overview_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 1: Overview</b>', styles['Heading3']))
    elements.append(overview_table)
    elements.append(Spacer(1, 12))

    system_metrics_table = Table(
        [
            ['Metric', 'Value'],
            ['Total Income', str(total_income)],
            ['Total Expense', str(total_expense)],
            ['Total Budget', str(total_budget)],
            ['Average FOI', f'{average_foi}%'],
        ],
        colWidths=[220, 270],
    )
    system_metrics_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 2: System Metrics</b>', styles['Heading3']))
    elements.append(system_metrics_table)
    elements.append(Spacer(1, 12))

    user_rows = [['User', 'Income', 'Expense', 'Budget', 'FOI', 'Risk']]
    for item in sorted(user_metrics, key=lambda entry: entry['total_expense'], reverse=True)[:10]:
        user_rows.append(
            [
                item['username'],
                str(item['total_income']),
                str(item['total_expense']),
                str(item['total_budget']),
                f"{item['foi']}%",
                item['risk_level'],
            ]
        )
    user_metrics_table = Table(user_rows, colWidths=[90, 75, 75, 75, 65, 110])
    user_metrics_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#198754')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 1), (4, -1), 'RIGHT'),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 3: Top User Accounts by Expense</b>', styles['Heading3']))
    elements.append(user_metrics_table)
    elements.append(Spacer(1, 12))

    risk_rows = [['User', 'Risk Level', 'FOI']]
    for item in top_risk_accounts:
        risk_rows.append([item['username'], item['risk_level'], f"{item['foi']}%"])
    risk_table = Table(risk_rows, colWidths=[180, 180, 130])
    risk_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc3545')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 4: High Risk Accounts</b>', styles['Heading3']))
    elements.append(risk_table)
    elements.append(Spacer(1, 12))

    category_rows = [['Category', 'Total Expense']]
    for item in top_categories:
        category_rows.append([item['category__name'] or 'Uncategorized', str(item['total'] or Decimal('0.00'))])
    category_table = Table(category_rows, colWidths=[250, 240])
    category_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6f42c1')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ]
        )
    )
    elements.append(Paragraph('<b>Section 5: Top Spending Categories</b>', styles['Heading3']))
    elements.append(category_table)

    doc.build(elements)
    return response


@login_required
def export_admin_analytics_csv(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Not allowed')

    context = _build_admin_analytics_context()
    total_users = context['total_accounts']
    total_income = context['total_income']
    total_expense = context['total_expense']
    total_budget = context['total_budget']
    average_foi = context['average_foi']
    user_metrics = context['user_metrics']
    top_categories = context['top_categories']

    generated_date = context['generated_date']
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="admin_system_report_{generated_date}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(['Admin System Report'])
    writer.writerow(['Generated Date', generated_date])
    writer.writerow(['Generated By', request.user.username])
    writer.writerow([])
    writer.writerow(['System Summary'])
    writer.writerow(['Total User Accounts', total_users])
    writer.writerow(['Total Income', total_income])
    writer.writerow(['Total Expense', total_expense])
    writer.writerow(['Total Budget', total_budget])
    writer.writerow(['Average FOI', f'{average_foi}%'])
    writer.writerow([])
    writer.writerow(['User-wise Financial Summary'])
    writer.writerow(['Username', 'Email', 'Income', 'Expense', 'Budget', 'FOI', 'Risk Level'])
    for item in sorted(user_metrics, key=lambda entry: entry['total_expense'], reverse=True):
        writer.writerow(
            [
                item['username'],
                item['email'],
                item['total_income'],
                item['total_expense'],
                item['total_budget'],
                f"{item['foi']}%",
                item['risk_level'],
            ]
        )
    writer.writerow([])
    writer.writerow(['Top Spending Categories'])
    writer.writerow(['Category', 'Total Expense'])
    for item in top_categories:
        writer.writerow([item['category__name'] or 'Uncategorized', item['total'] or Decimal('0.00')])

    return response


@login_required
def download_report(request, format, group_id=None):
    export_format = (format or '').strip().lower()

    if export_format == 'pdf':
        return export_group_pdf(request)

    expenses = Expense.objects.filter(user=request.user)
    incomes = Income.objects.filter(user=request.user)
    budgets = Budget.objects.filter(user=request.user)

    total_expense = sum((item.amount for item in expenses), Decimal('0.00'))
    total_income = sum((item.amount for item in incomes), Decimal('0.00'))
    total_budget = sum((item.amount for item in budgets), Decimal('0.00'))
    total_savings = total_income - total_expense

    safe_user_name = slugify(request.user.username) or 'user'
    report_rows = [
        ['Metric', 'Value'],
        ['Total Income', str(total_income)],
        ['Total Expense', str(total_expense)],
        ['Total Budget', str(total_budget)],
        ['Total Savings', str(total_savings)],
    ]

    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="{safe_user_name}_report.csv"'
        )
        writer = csv.writer(response)
        for row in report_rows:
            writer.writerow(row)
        return response

    if export_format == 'excel':
        try:
            from openpyxl import Workbook
        except ImportError:
            return HttpResponse('Excel export is unavailable: openpyxl is not installed.', status=503)

        wb = Workbook()
        ws = wb.active
        ws.title = 'Financial Report'
        for row in report_rows:
            ws.append(row)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{safe_user_name}_report.xlsx"'
        )
        wb.save(response)
        return response

    return HttpResponse('Unsupported report format.', status=400)


def _resolve_category_from_request(request, allow_existing=True):
    category_id = request.POST.get('category', '').strip()
    category_name = request.POST.get('category_name', '').strip()
    category_type = request.POST.get('category_type', '').strip()

    if category_id:
        if not allow_existing:
            return None, 'Please enter a category name and select a category type.'
        category = Category.objects.filter(id=category_id).first()
        if category:
            return category, None
        return None, 'Please select a valid category.'

    if category_name or category_type:
        if not category_name or not category_type:
            return None, 'To create a new category, provide both category name and category type.'
        category_type_obj = CategoryType.objects.filter(id=category_type).first()
        if not category_type_obj:
            return None, 'Please select a valid category type.'
        category, _ = Category.objects.get_or_create(
            name=category_name,
            category_type=category_type_obj,
        )
        return category, None

    return None, 'Please enter a category name and select a category type.'


@login_required
def delete_category(request, id):
    if not request.user.is_superuser:
        return redirect('dashboard')

    if request.method != 'POST':
        return HttpResponseForbidden('Invalid request method.')

    next_url = request.POST.get('next', '').strip() or 'financial_overview'
    category = get_object_or_404(Category, id=id)

    in_use = Expense.objects.filter(category=category).exists() or Budget.objects.filter(category=category).exists()
    if in_use:
        messages.error(
            request,
            'This category cannot be removed because it is already used in expenses or budgets.',
        )
        return redirect(next_url)

    category.delete()
    messages.success(request, 'Category removed successfully.')
    return redirect(next_url)


def _get_expense_form_context(form_data=None, expense=None):
    if form_data is None:
        form_data = {
            'category': str(expense.category_id) if expense else '',
            'category_name': '',
            'category_type': '',
            'amount': str(expense.amount) if expense else '',
            'expense_date': expense.expense_date.isoformat() if expense else '',
            'description': expense.description or '' if expense else '',
        }

    return {
        'categories': Category.objects.select_related('category_type').order_by('name', 'category_type__name'),
        'category_types': _get_category_types(),
        'form_data': form_data,
        'expense': expense,
        'is_edit_mode': expense is not None,
    }


def _get_budget_form_context(form_data=None, budget=None):
    if form_data is None:
        form_data = {
            'category': str(budget.category_id) if budget else '',
            'category_name': '',
            'category_type': '',
            'month': str(budget.month) if budget else '',
            'year': str(budget.year) if budget else '',
            'amount': str(budget.amount) if budget else '',
        }

    return {
        'categories': Category.objects.select_related('category_type').order_by('name', 'category_type__name'),
        'category_types': _get_category_types(),
        'form_data': form_data,
        'budget': budget,
        'is_edit_mode': budget is not None,
    }


def _get_income_form_context(form_data=None, income=None):
    if form_data is None:
        form_data = {
            'amount': str(income.amount) if income else '',
            'income_date': income.income_date.isoformat() if income else '',
            'description': income.description or '' if income else '',
        }

    return {
        'form_data': form_data,
        'income': income,
        'is_edit_mode': income is not None,
    }


@login_required
def expense_history(request):
    expenses = Expense.objects.filter(user=request.user).select_related('category')
    user_categories = (
        Category.objects.filter(expense__user=request.user)
        .select_related('category_type')
        .distinct()
        .order_by('name', 'category_type__name')
    )

    filter_data = {
        'category': request.GET.get('category', '').strip(),
        'start_date': request.GET.get('start_date', '').strip(),
        'end_date': request.GET.get('end_date', '').strip(),
        'min_amount': request.GET.get('min_amount', '').strip(),
        'max_amount': request.GET.get('max_amount', '').strip(),
    }

    if filter_data['category'].isdigit():
        expenses = expenses.filter(category_id=int(filter_data['category']))

    if filter_data['start_date']:
        try:
            expenses = expenses.filter(expense_date__gte=date.fromisoformat(filter_data['start_date']))
        except ValueError:
            messages.error(request, 'Ignoring invalid start date filter.')

    if filter_data['end_date']:
        try:
            expenses = expenses.filter(expense_date__lte=date.fromisoformat(filter_data['end_date']))
        except ValueError:
            messages.error(request, 'Ignoring invalid end date filter.')

    if filter_data['min_amount']:
        try:
            expenses = expenses.filter(amount__gte=Decimal(filter_data['min_amount']))
        except InvalidOperation:
            messages.error(request, 'Ignoring invalid minimum amount filter.')

    if filter_data['max_amount']:
        try:
            expenses = expenses.filter(amount__lte=Decimal(filter_data['max_amount']))
        except InvalidOperation:
            messages.error(request, 'Ignoring invalid maximum amount filter.')

    expenses = expenses.order_by('-expense_date', '-id')
    filtered_total = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(
        request,
        'expense_history.html',
        {
            'expenses': expenses,
            'categories': user_categories,
            'filter_data': filter_data,
            'filtered_total': filtered_total,
            'filtered_count': expenses.count(),
        },
    )


@login_required
def add_expense(request, group_id=None):
    context = _get_expense_form_context()

    if request.method == 'POST':
        context = _get_expense_form_context(
            {
                'category': '',
                'category_name': request.POST.get('category_name', '').strip(),
                'category_type': request.POST.get('category_type', '').strip(),
                'amount': request.POST.get('amount', '').strip(),
                'expense_date': request.POST.get('expense_date', '').strip(),
                'description': request.POST.get('description', '').strip(),
            }
        )
        amount_raw = request.POST.get('amount', '').strip()
        expense_date_raw = request.POST.get('expense_date', '').strip()
        description = request.POST.get('description', '').strip()

        category, category_error = _resolve_category_from_request(request, allow_existing=False)

        if category_error:
            messages.error(request, category_error)
        elif not amount_raw or not expense_date_raw:
            messages.error(request, 'Amount and expense date are required.')
        else:
            try:
                amount = Decimal(amount_raw)
                if amount < 0:
                    raise InvalidOperation
            except InvalidOperation:
                messages.error(request, 'Please enter a valid non-negative amount.')
                return render(request, 'add_expense.html', context)

            try:
                expense_date = date.fromisoformat(expense_date_raw)
            except ValueError:
                messages.error(request, 'Please enter a valid expense date.')
                return render(request, 'add_expense.html', context)

            Expense.objects.create(
                user=request.user,
                category=category,
                amount=amount,
                expense_date=expense_date,
                description=description or None,
            )
            _log_activity(request.user, 'Added expense')
            messages.success(request, 'Expense added successfully.')

            monthly_income = _get_monthly_income_total(
                request.user,
                expense_date.year,
                expense_date.month,
            )
            monthly_expense = _get_monthly_expense_total(
                request.user,
                expense_date.year,
                expense_date.month,
            )
            if monthly_income > Decimal('0.00') and monthly_expense > monthly_income:
                messages.warning(
                    request,
                    (
                        f"This month's expenses exceed income by "
                        f"{monthly_expense - monthly_income}."
                    ),
                )
            return redirect('expense_history')

    return render(request, 'add_expense.html', context)


@login_required
def budget_history(request):
    budgets = (
        Budget.objects.filter(user=request.user)
        .select_related('category')
        .order_by('-year', '-month', 'category__name', '-id')
    )
    filtered_total = budgets.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(
        request,
        'budget_history.html',
        {
            'budgets': budgets,
            'filtered_total': filtered_total,
            'filtered_count': budgets.count(),
        },
    )


@login_required
def income_history(request):
    incomes = (
        Income.objects.filter(user=request.user)
        .order_by('-income_date', '-id')
    )
    filtered_total = incomes.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(
        request,
        'income_history.html',
        {
            'incomes': incomes,
            'filtered_total': filtered_total,
            'filtered_count': incomes.count(),
        },
    )


@login_required
def edit_expense(request, id):
    expense = get_object_or_404(Expense, id=id, user=request.user)
    context = _get_expense_form_context(expense=expense)

    if request.method == 'POST':
        context = _get_expense_form_context(
            {
                'category': request.POST.get('category', '').strip(),
                'category_name': request.POST.get('category_name', '').strip(),
                'category_type': request.POST.get('category_type', '').strip(),
                'amount': request.POST.get('amount', '').strip(),
                'expense_date': request.POST.get('expense_date', '').strip(),
                'description': request.POST.get('description', '').strip(),
            },
            expense=expense,
        )
        amount_raw = request.POST.get('amount', '').strip()
        expense_date_raw = request.POST.get('expense_date', '').strip()
        description = request.POST.get('description', '').strip()

        category, category_error = _resolve_category_from_request(request)

        if category_error:
            messages.error(request, category_error)
        elif not amount_raw or not expense_date_raw:
            messages.error(request, 'Amount and expense date are required.')
        else:
            try:
                amount = Decimal(amount_raw)
                if amount < 0:
                    raise InvalidOperation
            except InvalidOperation:
                messages.error(request, 'Please enter a valid non-negative amount.')
                return render(request, 'add_expense.html', context)

            try:
                expense_date = date.fromisoformat(expense_date_raw)
            except ValueError:
                messages.error(request, 'Please enter a valid expense date.')
                return render(request, 'add_expense.html', context)

            expense.category = category
            expense.amount = amount
            expense.expense_date = expense_date
            expense.description = description or None
            expense.save(update_fields=['category', 'amount', 'expense_date', 'description'])

            _log_activity(request.user, 'Updated expense')
            messages.success(request, 'Expense updated successfully.')

            monthly_income = _get_monthly_income_total(
                request.user,
                expense.expense_date.year,
                expense.expense_date.month,
            )
            monthly_expense = _get_monthly_expense_total(
                request.user,
                expense.expense_date.year,
                expense.expense_date.month,
            )
            if monthly_income > Decimal('0.00') and monthly_expense > monthly_income:
                messages.warning(
                    request,
                    (
                        f"This month's expenses exceed income by "
                        f"{monthly_expense - monthly_income}."
                    ),
                )
            return redirect('expense_history')

    return render(request, 'add_expense.html', context)


@login_required
def delete_expense(request, id):
    if request.method != 'POST':
        return HttpResponseForbidden('Invalid request method.')

    expense = get_object_or_404(Expense, id=id, user=request.user)
    expense.delete()
    _log_activity(request.user, 'Deleted expense')
    messages.success(request, 'Expense deleted successfully.')
    return redirect('expense_history')


@login_required
def add_budget(request, group_id=None):
    context = _get_budget_form_context()

    if request.method == 'POST':
        context = _get_budget_form_context(
            {
                'category': request.POST.get('category', '').strip(),
                'category_name': request.POST.get('category_name', '').strip(),
                'category_type': request.POST.get('category_type', '').strip(),
                'month': request.POST.get('month', '').strip(),
                'year': request.POST.get('year', '').strip(),
                'amount': request.POST.get('amount', '').strip(),
            }
        )
        month_raw = request.POST.get('month', '').strip()
        year_raw = request.POST.get('year', '').strip()
        amount_raw = request.POST.get('amount', '').strip()

        category, category_error = _resolve_category_from_request(request)

        if category_error:
            messages.error(request, category_error)
        elif not month_raw or not year_raw or not amount_raw:
            messages.error(request, 'Category, month, year, and budget amount are required.')
        else:
            try:
                month = int(month_raw)
                year = int(year_raw)
                amount = Decimal(amount_raw)
                if month < 1 or month > 12 or year < 2000 or amount < 0:
                    raise ValueError
            except (ValueError, InvalidOperation):
                messages.error(request, 'Please enter valid month, year, and non-negative budget amount.')
                return render(request, 'add_budget.html', context)

            Budget.objects.update_or_create(
                user=request.user,
                category=category,
                month=month,
                year=year,
                defaults={'amount': amount},
            )
            _log_activity(request.user, 'Added budget')
            messages.success(request, 'Budget saved successfully.')

            monthly_income = _get_monthly_income_total(request.user, year, month)
            monthly_budget = _get_monthly_budget_total(request.user, year, month)
            if monthly_income > Decimal('0.00') and monthly_budget > monthly_income:
                messages.warning(
                    request,
                    (
                        f"Budget for {month:02d}/{year} exceeds income by "
                        f"{monthly_budget - monthly_income}."
                    ),
                )
            return redirect('financial_overview')

    return render(request, 'add_budget.html', context)


@login_required
def edit_budget(request, id):
    budget = get_object_or_404(Budget, id=id, user=request.user)
    context = _get_budget_form_context(budget=budget)

    if request.method == 'POST':
        context = _get_budget_form_context(
            {
                'category': request.POST.get('category', '').strip(),
                'category_name': request.POST.get('category_name', '').strip(),
                'category_type': request.POST.get('category_type', '').strip(),
                'month': request.POST.get('month', '').strip(),
                'year': request.POST.get('year', '').strip(),
                'amount': request.POST.get('amount', '').strip(),
            },
            budget=budget,
        )
        month_raw = request.POST.get('month', '').strip()
        year_raw = request.POST.get('year', '').strip()
        amount_raw = request.POST.get('amount', '').strip()

        category, category_error = _resolve_category_from_request(request)

        if category_error:
            messages.error(request, category_error)
        elif not month_raw or not year_raw or not amount_raw:
            messages.error(request, 'Category, month, year, and budget amount are required.')
        else:
            try:
                month = int(month_raw)
                year = int(year_raw)
                amount = Decimal(amount_raw)
                if month < 1 or month > 12 or year < 2000 or amount < 0:
                    raise ValueError
            except (ValueError, InvalidOperation):
                messages.error(request, 'Please enter valid month, year, and non-negative budget amount.')
                return render(request, 'add_budget.html', context)

            budget.category = category
            budget.month = month
            budget.year = year
            budget.amount = amount
            budget.save(update_fields=['category', 'month', 'year', 'amount'])

            _log_activity(request.user, 'Updated budget')
            messages.success(request, 'Budget updated successfully.')

            monthly_income = _get_monthly_income_total(request.user, year, month)
            monthly_budget = _get_monthly_budget_total(request.user, year, month)
            if monthly_income > Decimal('0.00') and monthly_budget > monthly_income:
                messages.warning(
                    request,
                    (
                        f"Budget for {month:02d}/{year} exceeds income by "
                        f"{monthly_budget - monthly_income}."
                    ),
                )
            return redirect('budget_history')

    return render(request, 'add_budget.html', context)


@login_required
def delete_budget(request, id):
    if request.method != 'POST':
        return HttpResponseForbidden('Invalid request method.')

    budget = get_object_or_404(Budget, id=id, user=request.user)
    budget.delete()
    _log_activity(request.user, 'Deleted budget')
    messages.success(request, 'Budget deleted successfully.')
    return redirect('budget_history')


@login_required
def add_income(request, group_id=None):
    context = _get_income_form_context()

    if request.method == 'POST':
        context = _get_income_form_context(
            {
                'amount': request.POST.get('amount', '').strip(),
                'income_date': request.POST.get('income_date', '').strip(),
                'description': request.POST.get('description', '').strip(),
            }
        )
        amount_raw = request.POST.get('amount', '').strip()
        income_date_raw = request.POST.get('income_date', '').strip()
        description = request.POST.get('description', '').strip()

        if not amount_raw or not income_date_raw:
            messages.error(request, 'Amount and income date are required.')
        else:
            try:
                amount = Decimal(amount_raw)
                if amount < 0:
                    raise InvalidOperation
            except InvalidOperation:
                messages.error(request, 'Please enter a valid non-negative amount.')
                return render(request, 'add_income.html', context)

            try:
                income_date = date.fromisoformat(income_date_raw)
            except ValueError:
                messages.error(request, 'Please enter a valid income date.')
                return render(request, 'add_income.html', context)

            Income.objects.create(
                user=request.user,
                amount=amount,
                income_date=income_date,
                description=description or None,
            )
            _log_activity(request.user, 'Added income')
            messages.success(request, 'Income added successfully.')
            return redirect('income_history')

    return render(request, 'add_income.html', context)


@login_required
def edit_income(request, id):
    income = get_object_or_404(Income, id=id, user=request.user)
    context = _get_income_form_context(income=income)

    if request.method == 'POST':
        context = _get_income_form_context(
            {
                'amount': request.POST.get('amount', '').strip(),
                'income_date': request.POST.get('income_date', '').strip(),
                'description': request.POST.get('description', '').strip(),
            },
            income=income,
        )
        amount_raw = request.POST.get('amount', '').strip()
        income_date_raw = request.POST.get('income_date', '').strip()
        description = request.POST.get('description', '').strip()

        if not amount_raw or not income_date_raw:
            messages.error(request, 'Amount and income date are required.')
        else:
            try:
                amount = Decimal(amount_raw)
                if amount < 0:
                    raise InvalidOperation
            except InvalidOperation:
                messages.error(request, 'Please enter a valid non-negative amount.')
                return render(request, 'add_income.html', context)

            try:
                income_date = date.fromisoformat(income_date_raw)
            except ValueError:
                messages.error(request, 'Please enter a valid income date.')
                return render(request, 'add_income.html', context)

            income.amount = amount
            income.income_date = income_date
            income.description = description or None
            income.save(update_fields=['amount', 'income_date', 'description'])

            _log_activity(request.user, 'Updated income')
            messages.success(request, 'Income updated successfully.')
            return redirect('income_history')

    return render(request, 'add_income.html', context)


@login_required
def delete_income(request, id):
    if request.method != 'POST':
        return HttpResponseForbidden('Invalid request method.')

    income = get_object_or_404(Income, id=id, user=request.user)
    income.delete()
    _log_activity(request.user, 'Deleted income')
    messages.success(request, 'Income deleted successfully.')
    return redirect('income_history')


@login_required
def financial_analysis(request):
    expenses = Expense.objects.filter(user=request.user)
    budgets = Budget.objects.filter(user=request.user)
    incomes = Income.objects.filter(user=request.user)
    total_income = incomes.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_expense = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_budget = budgets.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    category_expense = list(
        expenses.values('category_id', 'category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    category_budget = list(
        budgets.values('category_id', 'category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    budget_map = {
        item['category_id']: (item['total'] or Decimal('0.00'))
        for item in (
            budgets.values('category_id')
            .annotate(total=Sum('amount'))
            .order_by()
        )
    }
    expense_map = {
        item['category_id']: (item['total'] or Decimal('0.00'))
        for item in category_expense
    }

    analysis_table = []
    suggestions = []
    category_ids = []
    for item in category_expense:
        category_ids.append(item['category_id'])
    for item in category_budget:
        if item['category_id'] not in category_ids:
            category_ids.append(item['category_id'])

    category_names = {
        item['category_id']: item['category__name']
        for item in category_expense + category_budget
    }

    for category_id in category_ids:
        category_name = category_names.get(category_id, 'Uncategorized')
        expense_amount = expense_map.get(category_id, Decimal('0.00'))
        budget_amount = budget_map.get(category_id, Decimal('0.00'))
        percent = Decimal('0.00')
        if total_expense > 0:
            percent = ((expense_amount / total_expense) * Decimal('100')).quantize(Decimal('0.01'))

        status = 'Safe'
        if budget_amount > 0 and expense_amount > budget_amount:
            status = 'Over Budget'
            suggestions.append(f"{category_name} spending exceeds budget.")

        analysis_table.append(
            {
                'category': category_name,
                'budget': budget_amount,
                'expense': expense_amount,
                'percent': percent,
                'status': status,
            }
        )

    expense_breakdown = []
    for item in category_expense:
        expense_amount = item['total'] or Decimal('0.00')
        percent = Decimal('0.00')
        if total_expense > 0:
            percent = ((expense_amount / total_expense) * Decimal('100')).quantize(Decimal('0.01'))
        expense_breakdown.append(
            {
                'category': item['category__name'],
                'amount': expense_amount,
                'percent': percent,
            }
        )

    budget_breakdown = []
    for item in category_budget:
        budget_amount = item['total'] or Decimal('0.00')
        percent = Decimal('0.00')
        if total_budget > 0:
            percent = ((budget_amount / total_budget) * Decimal('100')).quantize(Decimal('0.01'))
        budget_breakdown.append(
            {
                'category': item['category__name'],
                'amount': budget_amount,
                'percent': percent,
            }
        )

    if total_budget > total_income:
        suggestions.append(
            f"Total budget is higher than income by {total_budget - total_income}. Revise budget targets."
        )
    if total_expense > total_income:
        suggestions.append(
            f"Total expenses are higher than income by {total_expense - total_income}. Reduce spending in top categories."
        )

    if not suggestions and analysis_table:
        suggestions.append('No major category overspending detected. Keep monitoring trends.')

    top_category = expense_breakdown[0]['category'] if expense_breakdown else None
    least_category = expense_breakdown[-1]['category'] if expense_breakdown else None
    top_budget_category = budget_breakdown[0]['category'] if budget_breakdown else None
    chart_labels = [item['category'] for item in expense_breakdown]
    chart_values = [float(item['amount']) for item in expense_breakdown]
    budget_chart_labels = [item['category'] for item in budget_breakdown]
    budget_chart_values = [float(item['amount']) for item in budget_breakdown]

    context = {
        'total_income': total_income,
        'total_expense': total_expense,
        'total_budget': total_budget,
        'analysis_table': analysis_table,
        'expense_breakdown': expense_breakdown,
        'budget_breakdown': budget_breakdown,
        'top_category': top_category,
        'least_category': least_category,
        'top_budget_category': top_budget_category,
        'suggestions': suggestions,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'budget_chart_labels': budget_chart_labels,
        'budget_chart_values': budget_chart_values,
        'predictive_analytics': _build_predictive_analytics(request.user),
    }
    return render(request, 'financial_analysis.html', context)
