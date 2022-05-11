from rest_framework import routers
from .views import ProxmoxVMView

# DefaultRouter() class comes from Django REST Framework,
# it automatically handle requests to APi URLs exposed by API using different HTTP methos.
# the result is that it is not necessary to manually create multiple URL rules, only one.
router = routers.DefaultRouter()

router.register(r"proxbox", ProxmoxVMView)

# variable Django uses for path mappings
urlpatterns = router.urls