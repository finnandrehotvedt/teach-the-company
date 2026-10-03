from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("control/", admin.site.urls),
    path("", include("academy.urls")),
]

admin.site.site_header = "Teach the Company — moderation"
admin.site.site_title = "Teach the Company"
admin.site.index_title = "Review learning projects and public challenges"
