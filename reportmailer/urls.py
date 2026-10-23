from django.urls import path
from . import views
app_name='reportmailer'
urlpatterns=[
    path('',views.report_email_module,name='report_email'),
    path('settings/',views.settings_get,name='settings_get'),
    path('settings/save/',views.settings_save,name='settings_save'),
    path('recipients/',views.recipients_list,name='recipients_list'),
    path('recipients/add/',views.recipient_write,{'action':'add'},name='recipient_add'),
    path('recipients/update/',views.recipient_write,{'action':'update'},name='recipient_update'),
    path('recipients/delete/',views.recipient_write,{'action':'delete'},name='recipient_delete'),
    path('log/',views.log_list,name='log_list'),
    path('send-now/',views.send,{'trigger':'manual'},name='send_now'),
    path('send-test/',views.send,{'trigger':'test'},name='send_test'),
    path('rearm/',views.rearm_day,name='rearm_day'),
]
