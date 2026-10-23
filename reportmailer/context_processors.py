from django.conf import settings

def report_email_feature(request):
    return {"report_email_enabled": settings.REPORT_EMAIL_ENABLED}
