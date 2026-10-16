# Validation — 16 October 2026

- 19 Python unit tests: passed.
- HTTP integration smoke test: passed against a simulated local receiver and a real monitor subprocess. Verified HTTP authentication, write protection, configuration, aircraft entry, clear hold, lost-track latch, acknowledgement and persistent manual blackout.
- Native channel parser/override tests: passed with AddressSanitizer and UndefinedBehaviorSanitizer. Leak checking disabled because this environment blocks LeakSanitizer process inspection.
- Native FPP adapter: compiled successfully against the FalconChristmas/fpp 10.0 checkout headers. Not linked/loaded inside a running FPP here.
- Panel JavaScript syntax and shell script syntax: passed.

No test used your actual receiver, FPP device, Falcon or fixtures. Confirm FPP version, receiver JSON URL and absolute channel mapping; follow README commissioning checks before show use.
