"""Django settings for CiviCRM demo project.

Demonstrates civi-py Django integration.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-demo-key-change-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "true").lower() == "true"

ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # CiviCRM integration
    "civi_py.contrib.django",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Serve static files with uvicorn
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # CiviCRM middleware - adds request.civi_client
    "civi_py.contrib.django.CiviMiddleware",
]

ROOT_URLCONF = "civicrm_demo.urls"

from civi_py.contrib.django.webui import TEMPLATES_DIR as WEBUI_TEMPLATES_DIR

# Shared Jinja2 templates directory
SHARED_TEMPLATES_DIR = BASE_DIR.parent.parent / "shared" / "templates"

TEMPLATES = [
    # Jinja2 backend for shared templates (used for main app views)
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [SHARED_TEMPLATES_DIR],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "examples.shared.jinja_env.get_django_env",
        },
    },
    # Jinja2 backend for WebUI templates (CiviCRM Explorer)
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [WEBUI_TEMPLATES_DIR],
        "APP_DIRS": False,
        "NAME": "webui_jinja2",
    },
    # Django templates backend for admin and fallback
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # CiviCRM context processor - adds civi_client to all templates
                "civi_py.contrib.django.templatetags.civi_tags.civi_context_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "civicrm_demo.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Use WhiteNoise for static files with ASGI servers (uvicorn)
# In DEBUG mode, use simple storage; in production, use compressed manifest
if DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# CiviCRM Configuration
# =============================================================================
# These settings are used by civi_py.contrib.django

CIVICRM_URL = os.getenv("CIVI_BASE_URL", "http://localhost:8080/civicrm/ajax/api4")
CIVICRM_API_KEY = os.getenv("CIVI_API_KEY", "")
CIVICRM_SITE_KEY = os.getenv("CIVI_SITE_KEY", "")
CIVICRM_TIMEOUT = int(os.getenv("CIVI_TIMEOUT", "30"))
CIVICRM_VERIFY_SSL = os.getenv("CIVI_VERIFY_SSL", "true").lower() == "true"
CIVICRM_DEBUG = DEBUG
