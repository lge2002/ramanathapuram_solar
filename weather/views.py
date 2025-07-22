from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import ramanadhapuram_forecast
from .serializers import ramanadhapuram_forecast, ramanadhapuram_forecastSerializer

class ramanadhapuram_forecastAPIView(APIView):
    def get(self, request):
        data = ramanadhapuram_forecast.objects.all().order_by('-timestamp')
        serializer = ramanadhapuram_forecastSerializer(data, many=True)
        return Response(serializer.data)