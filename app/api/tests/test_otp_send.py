from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.organizations.models import SMSCode


class SendOtpSendTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    @override_settings(
        DEV_OTP_BYPASS=False,
        SMS_LOGIN="login",
        SMS_PASSWORD="pass",
        SMS_SENDER="sender",
        SMS_API_URL="https://sms.example/api",
    )
    @patch("api.v1.views.requests.post")
    def test_send_otp_success_persists_code(self, post):
        post.return_value = Mock(status_code=200, text="OK")

        phone = "+996700000000"
        res = self.api.post("/v1/auth/send-otp/", {"phone": phone}, format="json")
        self.assertEqual(res.status_code, 200)

        self.assertTrue(
            SMSCode.objects.filter(phone_number=phone, purpose=SMSCode.PURPOSE_LOGIN).exists()
        )

    @override_settings(
        DEV_OTP_BYPASS=False,
        SMS_LOGIN="login",
        SMS_PASSWORD="pass",
        SMS_SENDER="sender",
        SMS_API_URL="https://sms.example/api",
    )
    @patch("api.v1.views.requests.post")
    def test_send_otp_provider_error_returns_500_and_deletes_code(self, post):
        post.return_value = Mock(status_code=500, text="ERROR")

        phone = "+996700000000"
        res = self.api.post("/v1/auth/send-otp/", {"phone": phone}, format="json")
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.data.get("error"), "server_error")

        self.assertFalse(
            SMSCode.objects.filter(phone_number=phone, purpose=SMSCode.PURPOSE_LOGIN).exists()
        )

    @override_settings(
        DEV_OTP_BYPASS=False,
        SMS_LOGIN="",
        SMS_PASSWORD="",
        SMS_SENDER="",
    )
    def test_send_otp_missing_sms_config_returns_500_and_deletes_code(self):
        phone = "+996700000000"
        res = self.api.post("/v1/auth/send-otp/", {"phone": phone}, format="json")
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.data.get("error"), "server_error")

        self.assertFalse(
            SMSCode.objects.filter(phone_number=phone, purpose=SMSCode.PURPOSE_LOGIN).exists()
        )
