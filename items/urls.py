from django.urls import path

from .views import create_new_item,update_item_view,autocomplete_item,items_hub,items_list_json
from . import quantity_views

app_name = "items"

urlpatterns = [
    path('quantity/units/', quantity_views.units, name='quantity_units'),
    path('quantity/products/', quantity_views.create_product,
         name='quantity_create_product'),
    path('quantity/products/<int:product_id>/', quantity_views.update_product,
         name='quantity_update_product'),
    path('quantity/variants/', quantity_views.create_variant,
         name='quantity_create_variant'),
    path('quantity/variants/<int:variant_id>/', quantity_views.update_variant,
         name='quantity_update_variant'),
    path('quantity/catalog/', quantity_views.catalog, name='quantity_catalog'),
    path('quantity/suggest-sku/', quantity_views.suggest_sku,
         name='quantity_suggest_sku'),
    path('items-dash/', items_hub, name='itemsDash'),
    path('add-new-item/',create_new_item,name='add_new_item'),
    path('update-item/',update_item_view,name='update_item'),
    path('autocomplete-item/', autocomplete_item, name='autocomplete_item'),
    path('items-list/', items_list_json, name='items_list'),
]
