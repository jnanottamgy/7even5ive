"""A made-up college portal that behaves like the real ones PortMax meets.

It exists so every part of PortMax can be tested end to end without touching a real portal:
the two-step login with a CAPTCHA, one session per student, an idle timeout, Referer and
User-Agent checks that log a session out on the spot, server-rendered HTML tables, and pages
PortMax must never fetch (fees, logout).
"""
