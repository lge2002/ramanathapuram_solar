from django.db import models

class ramanadhapuram_forecast(models.Model):
    city = models.CharField(max_length=100) 
    values = models.TextField() 
    type = models.CharField(max_length=50, default="Cloud Coverage")
    timestamp = models.DateTimeField(db_index=True) 
    # pass_field = models.CharField(max_length=100, null=True, blank=True)  # Correct: db_column matches your DB

    class Meta:
        unique_together = ('city', 'timestamp',)

    def __str__(self):
        return f"{self.city} - {self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.values[:50]}..."