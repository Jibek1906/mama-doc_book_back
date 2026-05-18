from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),

    path("specialists/", views.SpecialistListAPIView.as_view()),

    path("doctors/", views.DoctorListAPIView.as_view()),
    path("doctors/<int:doctor_id>/", views.DoctorDetailAPIView.as_view()),
    path("doctors/<int:doctor_id>/calendar/", views.DoctorCalendarAPIView.as_view()),
    path("doctors/<int:doctor_id>/reviews/", views.DoctorReviewsAPIView.as_view()),

    path("auth/send-otp/", views.SendOtpAPIView.as_view()),
    path("auth/verify-otp/", views.VerifyOtpAPIView.as_view()),
    path("meta/phone-countries/", views.PhoneCountriesAPIView.as_view()),

    path("bookings/", views.BookingCreateAPIView.as_view()),
    path("bookings/my/", views.MyBookingsAPIView.as_view()),
    path("bookings/<int:booking_id>/", views.CancelBookingAPIView.as_view()),
]
