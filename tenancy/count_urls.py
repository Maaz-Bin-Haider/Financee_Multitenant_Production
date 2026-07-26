from django.urls import path

from . import count_views

app_name = "quantity_counts"
urlpatterns = [
    path("", count_views.counts, name="page"),
    path("navigate/", count_views.navigate, name="navigate"),
    path("summary/", count_views.summary, name="summary"),
]
