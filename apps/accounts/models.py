# apps/accounts/models.py
import hashlib
import hmac
from django.db import models
from django.contrib.auth.models import AbstractUser, Permission, UserManager


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('user_level', 10)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    objects = CustomUserManager()
    """
    Custom user model for Dispatcharr.
    Inherits from Django's AbstractUser to add additional fields if needed.
    """

    class UserLevel(models.IntegerChoices):
        STREAMER = 0, "Streamer"
        STANDARD = 1, "Standard User"
        ADMIN = 10, "Admin"

    avatar_config = models.JSONField(default=dict, blank=True, null=True)
    channel_profiles = models.ManyToManyField(
        "dispatcharr_channels.ChannelProfile",
        blank=True,
        related_name="users",
    )
    user_level = models.IntegerField(default=UserLevel.STREAMER)
    custom_properties = models.JSONField(default=dict, blank=True, null=True)
    api_key = models.CharField(max_length=200, blank=True, null=True, db_index=False)
    api_key_prefix = models.CharField(
        max_length=16, blank=True, null=True, db_index=True,
        help_text="First 8 chars of the raw key for indexed lookup.",
    )
    stream_limit = models.IntegerField(default=0)

    @staticmethod
    def hash_api_key(raw_key: str) -> str:
        """Return a SHA-256 hex digest of the raw API key."""
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def set_api_key(self, raw_key: str):
        """Store the hashed key and a prefix for efficient DB lookup."""
        self.api_key = self.hash_api_key(raw_key)
        self.api_key_prefix = raw_key[:8]

    def verify_api_key(self, raw_key: str) -> bool:
        """Constant-time comparison of the supplied key against the stored hash."""
        if not self.api_key:
            return False
        candidate_hash = self.hash_api_key(raw_key)
        return hmac.compare_digest(self.api_key, candidate_hash)

    def __str__(self):
        return self.username

    def get_groups(self):
        """
        Returns the groups (roles) the user belongs to.
        """
        return self.groups.all()

    def get_permissions(self):
        """
        Returns the permissions assigned to the user and their groups.
        """
        return self.user_permissions.all() | Permission.objects.filter(group__user=self)
