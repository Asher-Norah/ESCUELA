from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("teacher", "Teacher"),
        ("student", "Student"),
        ("parent", "Parent"),
    ]
    APPROVAL_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    approval_status = models.CharField(max_length=10, choices=APPROVAL_CHOICES, default="pending")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    profile_image = models.ImageField(upload_to="profiles/", blank=True)