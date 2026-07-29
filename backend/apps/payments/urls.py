from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PaymentViewSet, SimulatedWaveCheckoutView, WaveWebhookView

router = DefaultRouter()
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("", include(router.urls)),
    # Public : protégé par la signature HMAC de Wave, pas par un jeton.
    path("webhooks/wave/", WaveWebhookView.as_view(), name="wave-webhook"),
    path(
        "payments/simulate/<str:reference>/",
        SimulatedWaveCheckoutView.as_view(),
        name="wave-simulate",
    ),
]
