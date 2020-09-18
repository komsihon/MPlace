from django.contrib import admin


class ProductAdmin(admin.ModelAdmin):
    fields = ('app', 'provider', 'lang', 'name', 'slug', 'tags', 'cost', 'duration', 'duration_text',
              'phone', 'email', 'callback', 'is_one_off', 'template_name', 'short_description', 'details')
