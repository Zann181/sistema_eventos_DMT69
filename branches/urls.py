from django.urls import path

from branches import views

app_name = "branches"

urlpatterns = [
    path("", views.branch_list, name="list"),
    path("new/", views.branch_create, name="create"),
    path("<slug:slug>/edit/", views.branch_update, name="update"),
    path("<slug:slug>/staff/<int:assignment_id>/toggle/", views.branch_assignment_toggle, name="assignment_toggle"),
    path("<slug:slug>/staff/<int:user_id>/event/<int:event_id>/toggle/", views.branch_staff_event_toggle, name="staff_event_toggle"),
    path("<int:branch_id>/switch/", views.switch_branch, name="switch"),
]
