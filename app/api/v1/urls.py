from django.urls import re_path

from . import views

urlpatterns = [
    # Spec uses no trailing slashes, but we accept optional slash everywhere.
    # This avoids 301/308 redirects on POST/DELETE (which can drop the request body).
    re_path(r"^health/?$", views.health),

    re_path(r"^specialists/?$", views.SpecialistListAPIView.as_view()),

    # universal professionals endpoints
    re_path(r"^professionals/?$", views.ProfessionalListAPIView.as_view()),
    # legacy aliases (still supported): search/filter as separate routes
    re_path(r"^professionals/search/?$", views.ProfessionalSearchAPIView.as_view()),
    re_path(r"^professionals/filter/?$", views.ProfessionalFilterAPIView.as_view()),
    re_path(r"^professionals/(?P<professional_id>\d+)/?$", views.ProfessionalDetailAPIView.as_view()),
    re_path(
        r"^professionals/(?P<professional_id>\d+)/calendar/?$",
        views.ProfessionalCalendarAPIView.as_view(),
    ),
    re_path(
        r"^professionals/(?P<professional_id>\d+)/available-services/?$",
        views.ProfessionalAvailableServicesAPIView.as_view(),
    ),
    re_path(
        r"^professionals/(?P<professional_id>\d+)/available-times/?$",
        views.ProfessionalAvailableTimesAPIView.as_view(),
    ),
    re_path(
        r"^professionals/(?P<professional_id>\d+)/reviews/?$",
        views.ProfessionalReviewsAPIView.as_view(),
    ),

    # services as separate category
    re_path(r"^services/?$", views.ServiceListAPIView.as_view()),

    # organizations / branches / feature flags
    re_path(r"^organizations/?$", views.OrganizationsAPIView.as_view()),
    re_path(r"^organizations/(?P<organization_id>\d+)/?$", views.OrganizationDetailAPIView.as_view()),
    re_path(
        r"^organizations/(?P<organization_id>\d+)/professionals/?$",
        views.OrganizationProfessionalsAPIView.as_view(),
    ),
    re_path(
        r"^organizations/(?P<organization_id>\d+)/services/?$",
        views.OrganizationServicesAPIView.as_view(),
    ),
    re_path(
        r"^organizations/(?P<organization_id>\d+)/branches/?$",
        views.OrganizationBranchesAPIView.as_view(),
    ),
    re_path(r"^branches/?$", views.BranchesAPIView.as_view()),
    re_path(r"^branches/(?P<branch_id>\d+)/?$", views.BranchDetailAPIView.as_view()),
    re_path(r"^branches/(?P<branch_id>\d+)/professionals/?$", views.BranchProfessionalsAPIView.as_view()),
    re_path(r"^branches/(?P<branch_id>\d+)/specialists/?$", views.BranchSpecialistsAPIView.as_view()),
    re_path(r"^features/?$", views.FeatureFlagsAPIView.as_view()),

    re_path(r"^auth/send-otp/?$", views.SendOtpAPIView.as_view()),
    re_path(r"^auth/verify-otp/?$", views.VerifyOtpAPIView.as_view()),
    re_path(r"^auth/complete-profile/?$", views.CompleteClientProfileAPIView.as_view()),

    re_path(r"^meta/phone-countries/?$", views.PhoneCountriesAPIView.as_view()),

    re_path(r"^bookings/my/?$", views.MyBookingsAPIView.as_view()),
    re_path(r"^bookings/(?P<booking_id>\d+)/?$", views.CancelBookingAPIView.as_view()),
    re_path(r"^bookings/?$", views.BookingCreateAPIView.as_view()),

    # --- Professional cabinet ---
    re_path(r"^pro/auth/login/?$", views.ProAuthLoginAPIView.as_view()),
    re_path(r"^pro/auth/send-otp/?$", views.ProSendOtpAPIView.as_view()),
    re_path(r"^pro/auth/verify-otp/?$", views.ProVerifyOtpAPIView.as_view()),

    re_path(r"^pro/me/?$", views.ProMeAPIView.as_view()),
    re_path(r"^pro/me/calendar/?$", views.ProCalendarAPIView.as_view()),
    re_path(r"^pro/me/schedule/?$", views.ProScheduleAPIView.as_view()),
    re_path(r"^pro/me/schedule-exceptions/?$", views.ProScheduleExceptionsAPIView.as_view()),
    re_path(
        r"^pro/me/schedule-exceptions/(?P<exception_id>\d+)/?$",
        views.ProScheduleExceptionDeleteAPIView.as_view(),
    ),
    re_path(r"^pro/me/bookings/?$", views.ProBookingsAPIView.as_view()),
]
