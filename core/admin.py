from django.contrib import admin
from .models import (
    UserProfile,
    CategoryType,
    Category,
    Expense,
    Budget,
    Income,
)

admin.site.register(UserProfile)
admin.site.register(CategoryType)
admin.site.register(Category)
admin.site.register(Expense)
admin.site.register(Budget)
admin.site.register(Income)
