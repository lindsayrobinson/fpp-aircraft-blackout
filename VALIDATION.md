# Validation — 16 October 2026

- 19 Python unit tests: passed.
- HTTP integration smoke test: passed against a simulated local receiver and a real monitor subprocess. Verified HTTP authentication, write protection, configuration, aircraft entry, clear hold, lost-track latch, acknowledgement and persistent manual blackout.
- Native channel parser/override tests: passed with AddressSanitizer and UndefinedBehaviorSanitizer. Leak checking disabled because this environment blocks LeakSanitizer process inspection.
- Native FPP adapter: compiled successfully against the FalconChristmas/fpp 10.0 checkout headers. Not linked/loaded inside a running FPP here.
- Panel JavaScript syntax and shell script syntax: passed.

No test used your actual receiver, FPP device, Falcon or fixtures. Confirm FPP version, receiver JSON URL and absolute channel mapping; follow README commissioning checks before show use.

## v0.2 FPP settings integration

- Embedded settings PHP and bridge: PHP 8.3 syntax checks passed.
- FPP-style wrapper plus actual monitor process integration passed: status, persisted latitude/longitude/radius/channel overrides, manual blackout, invalid settings, signed token expiry/tampering, method validation and unavailable-monitor response. Internal monitor password is absent from rendered HTML.
- Existing 19 Python tests and receiver HTTP integration smoke test passed.
- Native override tests passed; native hook source is unchanged.
- Settings JavaScript syntax and installation shell syntax passed.
- Background monitor defaults to loopback; existing saved settings remain in the same configuration files.

No live FPP 10.2 installation or physical DMX hardware is available here. Confirm the menu entry, settings persistence and blackout behaviour on the device after upgrading.
