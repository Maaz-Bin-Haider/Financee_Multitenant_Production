from django.urls import path
from .exports import record_export
app_name="activity"
urlpatterns=[path("record/",record_export,name="record")]
