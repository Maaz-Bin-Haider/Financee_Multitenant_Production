from django.urls import path

from . import report_views

app_name = "quantity_reports"

urlpatterns = [
    path("", report_views.reports_page, name="index"),
    path("api/<slug:key>/", report_views.report_api, name="api"),
    path("export/<slug:key>.csv", report_views.report_csv, name="csv"),
    path("export/<slug:key>.xls", report_views.report_excel, name="excel"),
]
