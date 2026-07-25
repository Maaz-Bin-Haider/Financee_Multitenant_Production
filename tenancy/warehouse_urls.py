from django.urls import path

from . import warehouse_views

app_name = "quantity_warehouses"

urlpatterns = [
    path("quantity/", warehouse_views.warehouse_list, name="list"),
    path("quantity/default/", warehouse_views.default_warehouse, name="default"),
    path("quantity/create/", warehouse_views.create_warehouse, name="create"),
    path(
        "quantity/<int:warehouse_id>/",
        warehouse_views.update_warehouse,
        name="update",
    ),
    path(
        "quantity/<int:warehouse_id>/delete/",
        warehouse_views.delete_warehouse,
        name="delete",
    ),
]
