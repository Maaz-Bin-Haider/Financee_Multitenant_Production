from django.urls import path
from .views import purchasing,get_purchase,get_purchase_summary, purchase_serial_check
from . import quantity_views

app_name = "purchase"

urlpatterns = [
    path('purchasing/',purchasing,name="purchasing"),
    path('get-purchase/',get_purchase,name="get_purchase"),
    path('get-purchase-summary/',get_purchase_summary,name="get_purchase_summary"),
    path('check-serials/', purchase_serial_check, name="purchase_serial_check"),
    path('quantity-tax-codes/', quantity_views.tax_codes,
         name="quantity_tax_codes"),
]
