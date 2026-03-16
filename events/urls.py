from django.urls import path

from events import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("new/", views.event_create, name="create"),
    path("<int:event_id>/edit/", views.event_update, name="update"),
    path("qr-preview/", views.qr_preview, name="qr_preview"),
    path("<int:event_id>/switch/", views.switch_event, name="switch"),
]
