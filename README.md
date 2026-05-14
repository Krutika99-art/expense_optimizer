# Expense Optimizer

Expense Optimizer is a Django-based personal finance web application for tracking income, expenses, and budgets. It helps users understand spending behavior, compare budgets against actual expenses, monitor savings, and review financial health through dashboards, reports, and category-level analysis.

The repository also includes a Power BI report file (`ExpenseOptimizerApplication.pbix`) for additional financial visualization.

## Features

- User registration, login, logout, profile editing, and password reset flow
- Role-based experience for members and admin users
- Income, expense, and budget CRUD workflows
- Dynamic category and category type management
- Dashboard with financial totals, trends, savings, and budget utilization
- Financial analysis with category breakdowns and budget-vs-expense status
- Predictive analytics and optimization indicators
- Notifications and activity logs
- Admin analytics, user management, account overview, and system reports
- PDF, CSV, and spreadsheet-style report exports
- Power BI dashboard file for external reporting

## Tech Stack

- Python 3.12+
- Django 6.0.2
- MySQL
- HTML, CSS, and JavaScript
- ReportLab for PDF exports
- OpenPyXL for workbook exports
- Power BI for dashboard reporting

## Project Structure

```text
expense_optimizer/
|-- config/                       # Django project settings and root URLs
|-- core/                         # Main application
|   |-- migrations/               # Database migrations
|   |-- static/                   # CSS and JavaScript assets
|   |-- templates/                # App templates
|   |-- admin.py                  # Django admin registrations
|   |-- models.py                 # Data models
|   |-- urls.py                   # App URL routes
|   `-- views.py                  # View and report logic
|-- ExpenseOptimizerApplication.pbix
|-- manage.py
|-- requirements.txt
`-- README.md
```

## Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd expense_optimizer
```

2. Create and activate a virtual environment:

```bash
python -m venv env
env\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a MySQL database:

```sql
CREATE DATABASE expense_optimizer_db;
```

5. Configure environment variables:

```bash
copy .env.example .env
```

Update `.env` with your local database password and a secure Django secret key. This project reads environment variables from your shell, so set them before running Django if you do not use a separate `.env` loader.

Required variables:

```text
DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
```

Example for PowerShell:

```powershell
$env:DJANGO_SECRET_KEY="replace-this-with-a-secure-secret-key"
$env:DJANGO_DEBUG="True"
$env:DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1"
$env:DB_NAME="expense_optimizer_db"
$env:DB_USER="root"
$env:DB_PASSWORD="your-mysql-password"
$env:DB_HOST="localhost"
$env:DB_PORT="3306"
```

6. Apply migrations:

```bash
python manage.py migrate
```

7. Create an admin user:

```bash
python manage.py createsuperuser
```

8. Start the development server:

```bash
python manage.py runserver
```

Open the app at `http://127.0.0.1:8000/`.

## Main Routes

- `/` - Landing page
- `/register/` - User registration
- `/login/` - Login
- `/dashboard/` - User dashboard
- `/financial-overview/` - Financial overview
- `/analysis/` - Financial analysis
- `/expenses/` - Expense history
- `/budgets/` - Budget history
- `/incomes/` - Income history
- `/admin-analytics/` - Custom admin analytics
- `/admin/` - Django admin

## Data Model Overview

- `UserProfile` stores each user's application role.
- `CategoryType` and `Category` organize financial records.
- `Income` stores income entries by date.
- `Expense` stores expense entries by category and date.
- `Budget` stores monthly category-level budgets.
- `Notification` stores user alerts.
- `ActivityLog` stores important user actions.

## Reporting

The app supports downloadable reports through Django views and includes Power BI reporting through `ExpenseOptimizerApplication.pbix`. Connect the Power BI report to the same MySQL database to visualize the current finance data.
