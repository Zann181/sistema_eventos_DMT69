from django.urls import path

from attendees import views

app_name = "attendees"

urlpatterns = [
    path("", views.attendee_list, name="list"),
    path("new/", views.attendee_create, name="create"),
    path("event-day/new/", views.attendee_event_day_create, name="event_day_create"),
    path("expenses/new/", views.attendee_expense_create, name="expense_create"),
    path("cash-drop/new/", views.attendee_cash_drop_create, name="cash_drop_create"),
    path("categories/new/", views.attendee_category_create, name="category_create"),
    path("check-in/", views.attendee_check_in, name="check_in"),
    path("check-in/preview/", views.attendee_check_in_preview, name="check_in_preview"),
    path("check-in/confirm/", views.attendee_confirm_check_in, name="confirm_check_in"),
    path("mark-checked-in/", views.attendee_mark_checked_in, name="mark_checked_in"),
    path("delete/", views.attendee_delete, name="delete"),
    path("export/excel/", views.attendee_export_excel, name="export_excel"),
    path("share/<str:qr_code>/", views.attendee_whatsapp_share, name="whatsapp_share"),
    path("share/<str:qr_code>/card.png", views.attendee_whatsapp_card, name="whatsapp_card"),
    path("share/<str:qr_code>/qr.png", views.attendee_whatsapp_qr_file, name="whatsapp_qr_file"),
    path("share/<str:qr_code>/flyer.jpg", views.attendee_whatsapp_flyer_file, name="whatsapp_flyer_file"),
    path("<str:cc>/qr/", views.attendee_qr_detail, name="qr_detail"),
]
