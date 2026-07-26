from django.urls import path

from . import transfer_views

app_name = "quantity_transfers"

urlpatterns = [
    path("", transfer_views.transfers, name="page"),
    path("navigate/", transfer_views.navigate, name="navigate"),
    path("summary/", transfer_views.summary, name="summary"),
]
