from rest_framework import serializers
from .models import ramanadhapuram_forecast

class ramanadhapuram_forecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = ramanadhapuram_forecast
        fields = '__all__'
