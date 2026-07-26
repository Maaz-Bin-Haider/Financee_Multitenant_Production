from django.urls import path

from .audit_views import audit_log

app_name = "quantity_audit"

urlpatterns = [
    path("", audit_log, name="log"),
]
