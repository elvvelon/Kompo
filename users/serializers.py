from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.core.exceptions import ValidationError as DjangoValidationError


class RegistrationSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        required=True,
        max_length=30,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message='A user with this username already exists.'
            )
        ]
    )
    first_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100
    )
    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100
    )
    email = serializers.EmailField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message='A user with this email already exists.'
            )
        ]
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        max_length=128,
        style={'input_type': 'password'}
    )
    password_confirmation = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        max_length=128,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'password',
            'password_confirmation'
        )

    def validate_username(self, username):
        stripped = username.strip()
        if not stripped:
            raise serializers.ValidationError('Username cannot be blank.')
        return username

    def validate(self, data):
        password = data.get('password')
        password_confirmation = data.get('password_confirmation')

        if password != password_confirmation:
            raise serializers.ValidationError('Passwords do not match.')

        temp_user = User(
            username=data.get('username'),
            email=data.get('email'),
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', '')
        )
        try:
            validate_password(password, temp_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})

        return data

    def create(self, validated_data):
        validated_data.pop('password_confirmation')
        return User.objects.create_user(**validated_data)


class RegisteredUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)


class RegisterResponseSerializer(serializers.Serializer):
    user = RegisteredUserSerializer()
    access = serializers.CharField()
    refresh = serializers.CharField()


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)


class CurrentUserResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    is_staff = serializers.BooleanField()

