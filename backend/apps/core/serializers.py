from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AuditLog, Notification, School, SchoolYear, Subscription

User = get_user_model()


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = "__all__"


class SchoolSerializer(serializers.ModelSerializer):
    subscription = SubscriptionSerializer(read_only=True)
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "id", "name", "slug", "address", "phone", "email",
            "country", "currency", "subscription", "is_active",
            "student_count", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_student_count(self, obj):
        from apps.students.models import Student, StudentStatus

        return Student.all_objects.filter(school=obj, status=StudentStatus.ACTIVE).count()


class SchoolYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolYear
        fields = [
            "id", "label", "start_date", "end_date",
            "tuition_months", "is_current",
        ]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_date": "La fin de l'exercice doit suivre son début."}
            )
        return attrs


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=10)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name",
            "phone", "role", "school", "is_active", "password",
        ]
        read_only_fields = ["school"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        # Le nouvel utilisateur est rattaché à l'établissement de son créateur : un
        # administrateur ne peut pas provisionner de compte dans une autre école.
        validated_data["school"] = self.context["request"].user.school
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "user_label", "action", "entity", "entity_id",
            "before", "after", "ip_address", "timestamp",
        ]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = ["school", "status", "sent_at", "error", "created_at"]


class LoginSerializer(TokenObtainPairSerializer):
    """Ajoute le profil et l'établissement à la réponse d'authentification.

    Évite au client un aller-retour supplémentaire au démarrage, et lui donne de quoi
    adapter la navigation au rôle dès la connexion.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["school_id"] = user.school_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        data["user"] = {
            "id": user.id,
            "email": user.email,
            "full_name": user.get_full_name(),
            "role": user.role,
        }
        data["school"] = (
            {
                "id": user.school.id,
                "name": user.school.name,
                "currency": user.school.currency,
            }
            if user.school
            else None
        )
        return data
