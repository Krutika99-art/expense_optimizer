from django.db import migrations, models
import django.db.models.deletion


LEGACY_TYPE_MAP = {
    'FOOD': 'Food',
    'Food': 'Food',
    'GROCERIES': 'Groceries',
    'Groceries': 'Groceries',
    'DINING': 'Dining Out',
    'Dining Out': 'Dining Out',
    'TRAVEL': 'Travel',
    'Travel': 'Travel',
    'TRANSPORT': 'Transport',
    'Transport': 'Transport',
    'FUEL': 'Fuel',
    'Fuel': 'Fuel',
    'UTILITIES': 'Utilities',
    'Utilities': 'Utilities',
    'RENT': 'Rent',
    'Rent': 'Rent',
    'EMI': 'EMI/Loans',
    'EMI/Loans': 'EMI/Loans',
    'INSURANCE': 'Insurance',
    'Insurance': 'Insurance',
    'EDUCATION': 'Education',
    'Education': 'Education',
    'ENTERTAINMENT': 'Entertainment',
    'Entertainment': 'Entertainment',
    'HEALTH': 'Health',
    'Health': 'Health',
    'SHOPPING': 'Shopping',
    'Shopping': 'Shopping',
    'PERSONAL_CARE': 'Personal Care',
    'Personal Care': 'Personal Care',
    'HOUSEHOLD': 'Household',
    'Household': 'Household',
    'GIFTS': 'Gifts',
    'Gifts': 'Gifts',
    'SUBSCRIPTIONS': 'Subscriptions',
    'Subscriptions': 'Subscriptions',
    'SAVINGS': 'Savings',
    'Savings': 'Savings',
    'MISC': 'Miscellaneous',
    'Miscellaneous': 'Miscellaneous',
    'OTHER': 'Other',
    'Other': 'Other',
}

DEFAULT_TYPE_NAMES = [
    'Dining Out',
    'Education',
    'EMI/Loans',
    'Entertainment',
    'Food',
    'Fuel',
    'Gifts',
    'Groceries',
    'Health',
    'Household',
    'Insurance',
    'Miscellaneous',
    'Other',
    'Personal Care',
    'Rent',
    'Savings',
    'Shopping',
    'Subscriptions',
    'Transport',
    'Travel',
    'Utilities',
]


def normalize_legacy_type(raw_value):
    if raw_value in LEGACY_TYPE_MAP:
        return LEGACY_TYPE_MAP[raw_value]
    if not raw_value:
        return 'Other'
    cleaned = str(raw_value).replace('_', ' ').strip()
    return cleaned.title() if cleaned.isupper() else cleaned


def migrate_category_types(apps, schema_editor):
    Category = apps.get_model('core', 'Category')
    CategoryType = apps.get_model('core', 'CategoryType')

    for type_name in DEFAULT_TYPE_NAMES:
        CategoryType.objects.get_or_create(name=type_name)

    for category in Category.objects.all():
        type_name = normalize_legacy_type(getattr(category, 'legacy_category_type', ''))
        category_type, _ = CategoryType.objects.get_or_create(name=type_name)
        category.category_type_id = category_type.id
        category.save(update_fields=['category_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_revert_category_hierarchy'),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoryType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.RenameField(
            model_name='category',
            old_name='category_type',
            new_name='legacy_category_type',
        ),
        migrations.AddField(
            model_name='category',
            name='category_type',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='categories', to='core.categorytype'),
        ),
        migrations.RunPython(migrate_category_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='category',
            name='category_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='categories', to='core.categorytype'),
        ),
        migrations.RemoveField(
            model_name='category',
            name='legacy_category_type',
        ),
    ]
