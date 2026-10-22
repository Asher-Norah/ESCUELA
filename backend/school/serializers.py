from rest_framework import serializers

MAX_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png"}


class StudentLookupSerializer(serializers.Serializer):
    reg_no = serializers.CharField(max_length=20)
    date_of_birth = serializers.DateField()


class StudentActivateSerializer(StudentLookupSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    address = serializers.CharField(required=False, allow_blank=True)
    nationality = serializers.CharField(required=False, allow_blank=True, max_length=60)
    profile_image = serializers.ImageField()

    def validate_profile_image(self, image):
        if image.size > MAX_PHOTO_BYTES:
            raise serializers.ValidationError("Photo must be under 2 MB.")
        if image.content_type not in ALLOWED_PHOTO_TYPES:
            raise serializers.ValidationError("Photo must be a JPEG or PNG.")
        return image