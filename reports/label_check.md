# Gold-label hand check (M1)

For each instance, compare the patch with the derived labels: gold files = modified non-test files; gold functions = innermost chunk containing each removed line or insertion point (at `base_commit`). Mark ✅/❌.

## pallets__flask-4045

- base_commit: `d8c37f43724cd9fb0870f77877b7c4c7e38a19e0`
- gold files: `src/flask/blueprints.py`
- gold functions: `src/flask/blueprints.py::Blueprint.__init__`, `src/flask/blueprints.py::Blueprint.add_url_rule`
- your check: 

```diff
diff --git a/src/flask/blueprints.py b/src/flask/blueprints.py
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -188,6 +188,10 @@ def __init__(
             template_folder=template_folder,
             root_path=root_path,
         )
+
+        if "." in name:
+            raise ValueError("'name' may not contain a dot '.' character.")
+
         self.name = name
         self.url_prefix = url_prefix
         self.subdomain = subdomain
@@ -360,12 +364,12 @@ def add_url_rule(
         """Like :meth:`Flask.add_url_rule` but for a blueprint.  The endpoint for
         the :func:`url_for` function is prefixed with the name of the blueprint.
         """
-        if endpoint:
-            assert "." not in endpoint, "Blueprint endpoints should not contain dots"
-        if view_func and hasattr(view_func, "__name__"):
-            assert (
-                "." not in view_func.__name__
-            ), "Blueprint view function name should not contain dots"
+        if endpoint and "." in endpoint:
+            raise ValueError("'endpoint' may not contain a dot '.' character.")
+
+        if view_func and hasattr(view_func, "__name__") and "." in view_func.__name__:
+            raise ValueError("'view_func' name may not contain a dot '.' character.")
+
         self.record(lambda s: s.add_url_rule(rule, endpoint, view_func, **options))
 
     def app_template_filter(self, name: t.Optional[str] = None) -> t.Callable:
```

## psf__requests-2317

- base_commit: `091991be0da19de9108dbe5e3752917fea3d7fdc`
- gold files: `requests/sessions.py`
- gold functions: `requests/sessions.py::<module>`, `requests/sessions.py::Session.request`
- your check: 

```diff
diff --git a/requests/sessions.py b/requests/sessions.py
--- a/requests/sessions.py
+++ b/requests/sessions.py
@@ -13,7 +13,7 @@
 from datetime import datetime
 
 from .auth import _basic_auth_str
-from .compat import cookielib, OrderedDict, urljoin, urlparse, builtin_str
+from .compat import cookielib, OrderedDict, urljoin, urlparse
 from .cookies import (
     cookiejar_from_dict, extract_cookies_to_jar, RequestsCookieJar, merge_cookies)
 from .models import Request, PreparedRequest, DEFAULT_REDIRECT_LIMIT
@@ -425,7 +425,7 @@ def request(self, method, url,
             If Tuple, ('cert', 'key') pair.
         """
 
-        method = builtin_str(method)
+        method = to_native_string(method)
 
         # Create the Request.
         req = Request(
```

## django__django-11099

- base_commit: `d26b2424437dabeeca94d7900b37d2df4410da0c`
- gold files: `django/contrib/auth/validators.py`
- gold functions: `django/contrib/auth/validators.py::ASCIIUsernameValidator`, `django/contrib/auth/validators.py::UnicodeUsernameValidator`
- your check: 

```diff
diff --git a/django/contrib/auth/validators.py b/django/contrib/auth/validators.py
--- a/django/contrib/auth/validators.py
+++ b/django/contrib/auth/validators.py
@@ -7,7 +7,7 @@
 
 @deconstructible
 class ASCIIUsernameValidator(validators.RegexValidator):
-    regex = r'^[\w.@+-]+$'
+    regex = r'^[\w.@+-]+\Z'
     message = _(
         'Enter a valid username. This value may contain only English letters, '
         'numbers, and @/./+/-/_ characters.'
@@ -17,7 +17,7 @@ class ASCIIUsernameValidator(validators.RegexValidator):
 
 @deconstructible
 class UnicodeUsernameValidator(validators.RegexValidator):
-    regex = r'^[\w.@+-]+$'
+    regex = r'^[\w.@+-]+\Z'
     message = _(
         'Enter a valid username. This value may contain only letters, '
         'numbers, and @/./+/-/_ characters.'
```
