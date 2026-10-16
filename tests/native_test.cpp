#include "../src/BlackoutState.h"
#include <cassert>
#include <sstream>
#include <vector>
int main() {
    const std::string boot="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    blackout::State s;
    std::istringstream good("AB1 "+boot+" 4000 1 1 2\n1 0\n4 8\n");
    assert(blackout::parse(good,s));
    uint8_t frame[]={255,77,88,255};
    s.apply(frame,boot,1000); assert(frame[0]==255 && frame[3]==255);
    s.apply(frame,boot,4000); assert(frame[0]==0 && frame[3]==8 && frame[1]==77 && frame[2]==88);
    assert(s.blocked("wrong-boot",1000));
    assert(s.blocked(boot,-2000));
    s.permit=false; assert(s.blocked(boot,1000));
    s.enforce=false; frame[0]=123; s.apply(frame,boot,4000);assert(frame[0]==123);
    for(const auto& rows : {"0 0", "8388609 0", "1 256", "1 -1", "1 0\ntrailing"}) {
        std::istringstream bad("AB1 "+boot+" 4000 0 1 1\n"+rows);
        assert(!blackout::parse(bad,s));
    }
    std::istringstream duplicate("AB1 "+boot+" 4000 0 1 2\n1 0\n1 1\n");assert(!blackout::parse(duplicate,s));
    std::istringstream truncated("AB1 "+boot+" 4000 0 1 2\n1 0\n");assert(!blackout::parse(truncated,s));
    std::istringstream corrupt("broken");assert(!blackout::parse(corrupt,s));
}
