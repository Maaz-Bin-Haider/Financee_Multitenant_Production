from django.urls import path
from .views import createPurchaseReturn,purchase_return_lookup, get_purchase_return,get_purchase_return_summary
from . import quantity_views

app_name = "purchaseReturn"

urlpatterns = [
    path('create-purchase-return/',createPurchaseReturn, name="create_purchase_return"),
    path('lookup/<str:serial>/',purchase_return_lookup,name="purchase_return_lookup"),
    path('get-purchase-return/',get_purchase_return, name="get_purchase_return"),
    path('get-purchase-return-summary/',get_purchase_return_summary, name="get_purchase_return_summary"),
    path('quantity-sources/', quantity_views.sources, name="quantity_sources"),
]
