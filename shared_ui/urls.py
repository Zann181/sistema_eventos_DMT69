from django.urls import path

from shared_ui import views

app_name = "shared_ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
