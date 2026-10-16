#include <atomic>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <memory>
#include <thread>
#include <chrono>
#include "Plugin.h"
#include "BlackoutState.h"

class AircraftBlackout : public FPPPlugins::Plugin, public FPPPlugins::ChannelDataPlugin {
    std::shared_ptr<const blackout::State> state;
    std::atomic<bool> stopping{false};
    std::atomic<uint64_t> frames{0};
    std::atomic<int64_t> lastFrame{0};
    std::thread worker;
    std::string boot;
    void readState() {
        std::ifstream config("/home/fpp/media/config/aircraft-blackout.native");
        blackout::State targets, next;
        if (!blackout::parse(config, targets)) {
            next = *std::atomic_load(&state);
            next.permit = false;
        } else {
            std::ifstream input("/run/aircraft-blackout/snapshot");
            bool match = blackout::parse(input, next) && next.enforce == targets.enforce && next.channels.size() == targets.channels.size();
            if (match) {
                for (size_t i=0; i<next.channels.size(); ++i)
                    if (next.channels[i].channel != targets.channels[i].channel || next.channels[i].value != targets.channels[i].value) match = false;
            }
            if (!match) { next = targets; next.permit = false; }
        }
        std::atomic_store(&state, std::make_shared<const blackout::State>(std::move(next)));
    }
    void status() {
        auto s = std::atomic_load(&state);
        auto now = blackout::nowMs();
        const char* temp = "/run/aircraft-blackout/native-status.json.tmp";
        std::ofstream o(temp);
        o << "{\"heartbeat_ms\":" << now << ",\"frames\":" << frames.load()
          << ",\"last_frame_ms\":" << lastFrame.load()
          << ",\"enforce\":" << (s->enforce?"true":"false")
          << ",\"blocked\":" << (s->blocked(boot,now)?"true":"false")
          << ",\"channels\":" << s->channels.size() << "}";
        o.close();
        if (o) std::rename(temp, "/run/aircraft-blackout/native-status.json");
    }
    void stop() {
        stopping = true;
        if (worker.joinable()) worker.join();
    }
public:
    AircraftBlackout() : FPPPlugins::Plugin("fpp-aircraft-blackout"), state(std::make_shared<const blackout::State>()) {
        std::ifstream b("/proc/sys/kernel/random/boot_id"); b >> boot;
        readState();
        worker = std::thread([this] {
            int n=0;
            while (!stopping) {
                readState();
                if (++n % 10 == 0) status();
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        });
    }
    ~AircraftBlackout() override { stop(); }
#if defined(FPP_PLUGIN_API_VERSION) && FPP_PLUGIN_API_VERSION >= 6
    std::function<bool()> shutdown() override { stop(); return nullptr; }
#endif
    void modifyChannelData(int, uint8_t* data) override {
        auto s = std::atomic_load(&state);
        auto now = blackout::nowMs();
        s->apply(data, boot, now);
        ++frames;
        lastFrame = now;
    }
};
extern "C" FPPPlugins::Plugin* createPlugin() { return new AircraftBlackout(); }
