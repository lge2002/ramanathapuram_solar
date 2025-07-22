from django.urls import path
from .views import ramanadhapuram_forecastAPIView

urlpatterns = [
    path('api/cloud/', ramanadhapuram_forecastAPIView.as_view(), name='cloud-api'),
]
