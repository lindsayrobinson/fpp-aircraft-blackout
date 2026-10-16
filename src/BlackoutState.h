#pragma once
#include <cstdint>
#include <istream>
#include <string>
#include <vector>
#include <time.h>
namespace blackout {
constexpr int MaxChannels = 8192 * 1024; // FPP Sequence.h FPPD_MAX_CHANNELS
struct Override { int channel; uint8_t value; };
inline int64_t nowMs() {
    timespec t{};
    clock_gettime(CLOCK_BOOTTIME, &t);
    return int64_t(t.tv_sec)*1000+t.tv_nsec/1000000;
}
struct State {
    std::string boot;
    int64_t expires = 0;
    bool permit = false, enforce = false;
    std::vector<Override> channels;
    bool blocked(const std::string& currentBoot, int64_t now) const {
        return !permit || boot != currentBoot || expires <= now || expires-now > 5000;
    }
    void apply(uint8_t* data, const std::string& currentBoot, int64_t now) const {
        if (enforce && blocked(currentBoot, now))
            for (const auto& c : channels) data[c.channel-1] = c.value;
    }
};
inline bool parse(std::istream& in, State& out) {
    State next;
    std::string magic, extra;
    int permit, enforce, count;
    if (!(in >> magic >> next.boot >> next.expires >> permit >> enforce >> count) ||
        magic != "AB1" || next.boot.size() != 36 || next.expires < 0 ||
        (permit != 0 && permit != 1) || (enforce != 0 && enforce != 1) || count < 0 || count > 1024)
        return false;
    next.permit = permit; next.enforce = enforce;
    for (int i=0; i<count; ++i) {
        int ch, val;
        if (!(in >> ch >> val) || ch < 1 || ch > MaxChannels || val < 0 || val > 255) return false;
        for (const auto& old : next.channels) if (old.channel == ch) return false;
        next.channels.push_back({ch, uint8_t(val)});
    }
    if (in >> extra) return false;
    out = std::move(next);
    return true;
}
}
