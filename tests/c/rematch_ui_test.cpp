/* Host-only, fake pad/clock regression: no game, addresses, network or SDL. */
#include "../../src/directfight/ui_logic.h"
#include <cstdio>
#include <cstdlib>
using namespace df::ui;
static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"line %d: %s\n",__LINE__,#x); std::exit(1); } } while(0)
static Prompt prompt(uint64_t rev=1) {
    Prompt p; p.generation="launch"; p.session="session"; p.prompt="offer"; p.match="match";
    p.kind="rematch"; p.rev=rev; p.remaining_ms=10000; p.allowed={"accept","decline","next"}; return p;
}
static void decisions() {
    Menu m; CHECK(m.update(prompt(),100,"launch","session"));
    CHECK(!m.tick(kConfirm,true,101)); // held KO attack never accepts
    CHECK(!m.tick(kConfirm,true,102)); CHECK(!m.tick(0,true,103));
    CHECK(!m.tick(kConfirm,true,104,false)); // rollback cannot dispatch or consume an edge
    CHECK(m.tick(kConfirm,true,104)); CHECK(m.pending().seq==1&&m.pending().action=="accept");
    CHECK(!m.tick(0,true,105)); CHECK(!m.tick(kCancel,true,106)); // one outstanding action
    Prompt ack=prompt(2); ack.ack_seq=1; ack.ack_status="ok"; ack.kind="waiting"; ack.allowed={"decline"};
    CHECK(m.update(ack,106,"launch","session")); CHECK(!m.pending().seq);
    CHECK(!m.tick(kCancel,true,107)); CHECK(!m.tick(0,true,108)); CHECK(m.tick(kCancel,true,109));
    CHECK(m.pending().seq==2&&m.pending().action=="decline");
}
static void identities_expiry_focus() {
    Menu m; Prompt p=prompt(); CHECK(!m.update(p,100,"other","session")); CHECK(!m.update(p,100,"launch","other"));
    CHECK(m.update(p,100,"launch","session")); CHECK(!m.update(p,100,"launch","session"));
    CHECK(!m.tick(0,true,101)); CHECK(!m.tick(0,false,102));
    CHECK(!m.tick(kConfirm,true,103)); CHECK(!m.tick(0,true,104));
    CHECK(!m.tick(kConfirm|kCancel,true,105)); // ambiguous press does nothing
    CHECK(!m.tick(0,true,106)); CHECK(m.tick(kNext,true,107)); CHECK(m.pending().action=="next");
    Prompt next=prompt(2); next.prompt="new"; CHECK(m.update(next,200,"launch","session"));
    CHECK(m.pending().seq==1); // prompt revision cannot drop an unacknowledged action
    CHECK(!m.visible(10200)); CHECK(!m.tick(kConfirm,true,10200)); CHECK(m.remaining(10200)==0);
    next.rev=3; next.ack_seq=1; next.ack_status="rejected";
    CHECK(m.update(next,300,"launch","session")); CHECK(!m.pending().seq);
    m.invalidate(); CHECK(!m.visible(301)); CHECK(!m.update(next,301,"launch","session"));
}
static void contexts() {
    const struct { const char* action; uint16_t button; } cases[]={
        {"ready",kConfirm},{"back_to_line",kConfirm},{"sit_out",kCancel},{"lobby",kCancel},{"next",kNext}};
    for(const auto& c:cases) {
        Menu m; Prompt p=prompt(); p.allowed={c.action}; CHECK(m.update(p,10,"launch","session"));
        CHECK(!m.tick(0,true,11)); CHECK(m.tick(c.button,true,12)); CHECK(m.pending().action==c.action);
    }
    Menu m; Prompt p=prompt(); p.allowed={"decline"}; p.policy="auto_unless_declined";
    CHECK(m.update(p,10,"launch","session")); CHECK(!m.tick(0,true,11)); CHECK(!m.tick(kConfirm,true,12));
    CHECK(!m.tick(0,true,13)); CHECK(m.tick(kCancel,true,14)); // server owns auto start, UI may only decline
}
static void parsing() {
    const std::string good=R"({"v":1,"generation":"launch","session":"session","rev":1,"prompt":"offer","match":"match","kind":"rematch","allowed":["accept","decline"],"remaining_ms":2000,"title":"Ready?","ack_seq":0,"ack_status":""})";
    Prompt p; CHECK(parse_prompt(good,p)); CHECK(p.title=="Ready?"&&p.permits("accept"));
    CHECK(!parse_prompt(good+"garbage",p)); CHECK(!parse_prompt("{",p));
    CHECK(!parse_prompt(std::string(kMessageMax+1,' '),p));
    auto bad=[&](const std::string& from,const std::string& to) { std::string s=good; size_t n=s.find(from); CHECK(n!=std::string::npos); s.replace(n,from.size(),to); CHECK(!parse_prompt(s,p)); };
    bad("\"v\":1","\"v\":2"); bad("\"v\":1","\"v\":1,\"v\":1");
    bad("\"rev\":1","\"rev\":-1"); bad("\"rev\":1","\"rev\":1.5");
    bad("\"rev\":1","\"rev\":18446744073709551616");
    bad("\"rev\":1","\"rev\":01"); bad("\"rev\":1","\"rev\":true");
    bad("2000","120001"); bad("[\"accept\",\"decline\"]","[\"accept\",\"accept\"]");
    bad("Ready?","\\uD800"); bad("Ready?","\\u0000"); bad("Ready?","\\q");
    bad("Ready?",std::string(1,(char)0xff)); bad("Ready?",std::string(kTextMax+1,'a'));
    std::string unicode=good; unicode.replace(unicode.find("Ready?"),6,"\\uD83D\\uDE00");
    CHECK(parse_prompt(unicode,p)); CHECK(p.title=="\xf0\x9f\x98\x80");
}
int main() { decisions(); identities_expiry_focus(); contexts(); parsing(); std::printf("PASS %u checks\n",checks); }
