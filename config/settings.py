"""Настройки локального прототипа: без базы данных и входа пользователей."""

import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
ROOT_URLCONF = "config.urls"
INSTALLED_APPS = ["django.contrib.staticfiles"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
DATABASES = {}
STATIC_URL = "static/"
FRONTEND_DIR = BASE_DIR / "frontend" / "dist" / "frontend" / "browser"
STATICFILES_DIRS = [FRONTEND_DIR]
WHITENOISE_USE_FINDERS = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 200_000
