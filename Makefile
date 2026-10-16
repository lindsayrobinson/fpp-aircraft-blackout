.DEFAULT_GOAL := all
SRCDIR ?= /opt/fpp/src
CXX ?= g++
# Compile against the installed FPP headers to match that device's plugin ABI.
CPPFLAGS += -I$(SRCDIR)
CXXFLAGS += -std=c++17 -O2 -fPIC -pthread -Wall -Wextra
LDLIBS += -L$(SRCDIR) -lfpp -pthread
all: libfpp-aircraft-blackout.so
libfpp-aircraft-blackout.so: src/AircraftBlackout.cpp src/BlackoutState.h $(SRCDIR)/Plugin.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -shared src/AircraftBlackout.cpp $(LDLIBS) -o $@
clean:
	rm -f libfpp-aircraft-blackout.so
.PHONY: all clean
