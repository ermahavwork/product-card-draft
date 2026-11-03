from django.urls import path

from card_draft import views

urlpatterns = [
    path("", views.index),
    path("api/models", views.models),
    path("api/examples", views.examples),
    path("api/draft", views.draft),
]
