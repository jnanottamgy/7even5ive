# R8 optimises the libraries (Compose is most of the app); our own code is kept as written, so
# serialization, the WebView bridge and reflection-free-but-untested paths behave exactly as in
# the debug build the tests run on.
-keep class com.sevenfive.app.** { *; }
-keepattributes *Annotation*, InnerClasses, Signature, EnclosingMethod
