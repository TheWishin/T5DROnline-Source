/* Host-only, fake pad/clock regression of the in-game question (src/directfight/ui_logic.h): no game, addresses,
 * network or SDL. */
#include "../../src/directfight/ui_logic.h"
#include <cstdio>
#include <cstdlib>
using namespace df::ui;
static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"line %d: %s\n",__LINE__,#x); std::exit(1); } } while(0)
static const uint64_t L=kInputLockMs;
static Prompt prompt(uint64_t rev=1) {
    Prompt p; p.generation="launch"; p.session="session"; p.prompt="offer"; p.match="match";
    p.kind="rematch"; p.rev=rev; p.remaining_ms=10000; p.countdown_ms=9000; p.total_ms=10000;
    p.allowed={"accept","decline"}; return p;
}
static void decisions() {
    Menu m; CHECK(m.update(prompt(),100,"launch","session"));
    CHECK(m.locked(100)&&m.locked(100+L-1)&&!m.locked(100+L));
    CHECK(!m.tick(kConfirm,true,101)); // held KO attack never accepts
    CHECK(!m.tick(0,true,102)); CHECK(!m.tick(kConfirm,true,103)); // released, but the question is new: locked
    CHECK(!m.tick(0,true,100+L)); // armed now
    CHECK(!m.tick(kConfirm,true,101+L,false)); // rollback cannot dispatch or consume an edge
    CHECK(m.tick(kConfirm,true,101+L)); CHECK(m.pending().seq==1&&m.pending().action=="accept");
    CHECK(m.waiting());
    CHECK(!m.tick(0,true,102+L)); CHECK(!m.tick(kCancel,true,103+L)); // one outstanding action
    Prompt ack=prompt(2); ack.ack_seq=1; ack.ack_status="ok"; ack.allowed={"decline"};
    CHECK(m.update(ack,104+L,"launch","session")); CHECK(!m.pending().seq); CHECK(!m.locked(104+L)); // same question
    CHECK(!m.tick(kCancel,true,105+L)); CHECK(!m.tick(0,true,106+L)); CHECK(m.tick(kCancel,true,107+L));
    CHECK(m.pending().seq==2&&m.pending().action=="decline");
}
static void directions_do_not_block() {
    Menu m; CHECK(m.update(prompt(),0,"launch","session"));
    const uint16_t back=0x0080, punch=0x1000|0x8000; // LEFT held, triangle + square mashed
    CHECK(!m.tick(back,true,L)); CHECK(!m.tick(back|punch,true,L+1)); CHECK(!m.tick(back,true,L+2));
    CHECK(m.tick(back|kConfirm,true,L+3)); CHECK(m.pending().action=="accept");
}
static void countdown() {
    Menu m; Prompt p=prompt(); CHECK(m.update(p,1000,"launch","session"));
    CHECK(m.countdown(1000)==9000); CHECK(m.countdown(5000)==5000); CHECK(m.countdown(10000)==0);
    CHECK(m.visible(10500)); CHECK(!m.visible(11000)); CHECK(m.countdown(11000)==0);
    Prompt c=prompt(2); c.countdown_ms=0; c.allowed={}; c.opp_state="decline"; CHECK(m.update(c,2000,"launch","session"));
    CHECK(m.countdown(2001)==0); CHECK(m.visible(2001));
    CHECK(!m.tick(0,true,2000+L)); CHECK(!m.tick(kConfirm,true,2001+L)); CHECK(!m.tick(kCancel,true,2002+L)); // nothing allowed
}
static void identities_expiry_focus() {
    Menu m; Prompt p=prompt(); CHECK(!m.update(p,100,"other","session")); CHECK(!m.update(p,100,"launch","other"));
    CHECK(m.update(p,100,"launch","session")); CHECK(!m.update(p,100,"launch","session"));
    CHECK(!m.tick(0,true,100+L)); CHECK(!m.tick(0,false,101+L)); // device switch: arm again
    CHECK(!m.tick(kConfirm,true,103+L)); CHECK(!m.tick(0,true,104+L));
    CHECK(!m.tick(kConfirm|kCancel,true,105+L)); // ambiguous press does nothing
    CHECK(!m.tick(0,true,106+L)); CHECK(!m.tick(kNext,true,107+L)); // Square: no action in this question
    CHECK(!m.tick(0,true,108+L)); CHECK(m.tick(kCancel,true,109+L)); CHECK(m.pending().action=="decline");
    Prompt next=prompt(2); next.prompt="new"; CHECK(m.update(next,200+L,"launch","session"));
    CHECK(m.pending().seq==1); // prompt revision cannot drop an unacknowledged action
    CHECK(!m.visible(10200+L)); CHECK(!m.tick(kConfirm,true,10200+L)); CHECK(m.remaining(10200+L)==0);
    next.rev=3; next.ack_seq=1; next.ack_status="rejected";
    CHECK(m.update(next,300+L,"launch","session")); CHECK(!m.pending().seq);
    m.invalidate(); CHECK(!m.visible(301+L)); CHECK(!m.update(next,301+L,"launch","session"));
}
static void contexts() {
    const struct { const char* action; uint16_t button; } cases[]={
        {"ready",kConfirm},{"back_to_line",kConfirm},{"sit_out",kCancel},{"lobby",kCancel},{"next",kNext}};
    for(const auto& c:cases) {
        Menu m; Prompt p=prompt(); p.allowed={c.action}; CHECK(m.update(p,10,"launch","session"));
        CHECK(!m.tick(0,true,10+L)); CHECK(m.tick(c.button,true,11+L)); CHECK(m.pending().action==c.action);
    }
    Menu m; Prompt p=prompt(); p.allowed={"decline"}; p.policy="auto_unless_declined";
    CHECK(m.update(p,10,"launch","session")); CHECK(!m.tick(0,true,10+L)); CHECK(!m.tick(kConfirm,true,11+L));
    CHECK(!m.tick(0,true,12+L)); CHECK(m.tick(kCancel,true,13+L)); // server owns auto start, UI may only decline
}
static void challenger() {
    Menu m; Prompt p=prompt(); p.kind="challenger";
    p.remaining_ms=p.countdown_ms=p.total_ms=15000;
    CHECK(m.update(p,100,"launch","session"));
    CHECK(m.visible(100)&&m.countdown(100)==15000);
    // A held Practice kick cannot accept the arriving offer.
    CHECK(!m.tick(kConfirm,true,100+L)); CHECK(!m.tick(kConfirm,true,101+L));
    CHECK(!m.tick(0,true,102+L)); CHECK(m.tick(kConfirm,true,103+L));
    CHECK(m.pending().action=="accept");
    CHECK(m.countdown(14100)==1000); CHECK(!m.visible(15100));
    CHECK(!m.tick(kCancel,true,15101));
    Menu decline; CHECK(decline.update(p,0,"launch","session"));
    CHECK(!decline.tick(0,true,L)); CHECK(decline.tick(kCancel,true,L+1));
    CHECK(decline.pending().action=="decline");
    OfflineCapture capture;
    CHECK(!capture.tick(false,kConfirm,true)); // no prompt: ordinary Practice input
    CHECK(capture.tick(true,kConfirm,true));
    CHECK(capture.tick(true,0,true)); // still neutral while the question is shown
    CHECK(capture.tick(false,kConfirm,true)); // hidden while accept is held
    CHECK(capture.tick(false,0,false)); // unplug/switch cannot release a held edge
    CHECK(!capture.tick(false,0,true));
    CHECK(!capture.tick(false,kConfirm,true)); // next Practice press is available
    CHECK(capture.tick(true,0,true)); capture.reset(); CHECK(!capture.held());
}
static void parsing() {
    const std::string good=R"({"v":1,"generation":"launch","session":"session","rev":1,"prompt":"offer","match":"match","kind":"rematch","allowed":["accept","decline"],"remaining_ms":2000,"countdown_ms":1500,"total_ms":2000,"title":"Ready?","opponent":"Bob: deciding","opp_state":"deciding","status":"","key_confirm":"Z","key_cancel":"X","ack_seq":0,"ack_status":""})";
    Prompt p; CHECK(parse_prompt(good,p)); CHECK(p.title=="Ready?"&&p.permits("accept"));
    CHECK(p.countdown_ms==1500&&p.total_ms==2000&&p.opponent=="Bob: deciding"&&p.key_confirm=="Z"&&p.key_cancel=="X");
    CHECK(!parse_prompt(good+"garbage",p)); CHECK(!parse_prompt("{",p));
    CHECK(!parse_prompt(std::string(kMessageMax+1,' '),p));
    auto bad=[&](const std::string& from,const std::string& to) { std::string s=good; size_t n=s.find(from); CHECK(n!=std::string::npos); s.replace(n,from.size(),to); CHECK(!parse_prompt(s,p)); };
    bad("\"v\":1","\"v\":2"); bad("\"v\":1","\"v\":1,\"v\":1");
    bad("\"rev\":1","\"rev\":-1"); bad("\"rev\":1","\"rev\":1.5");
    bad("\"rev\":1","\"rev\":18446744073709551616");
    bad("\"rev\":1","\"rev\":01"); bad("\"rev\":1","\"rev\":true");
    bad("\"remaining_ms\":2000","\"remaining_ms\":120001"); bad("1500","120001");
    bad("[\"accept\",\"decline\"]","[\"accept\",\"accept\"]");
    bad("\"Z\"","\"ABCDEFGHIJKLMNOPQ\"");
    bad("Ready?","\\uD800"); bad("Ready?","\\u0000"); bad("Ready?","\\q");
    bad("Ready?",std::string(1,(char)0xff)); bad("Ready?",std::string(kTextMax+1,'a'));
    std::string unicode=good; unicode.replace(unicode.find("Ready?"),6,"\\uD83D\\uDE00");
    CHECK(parse_prompt(unicode,p)); CHECK(p.title=="\xf0\x9f\x98\x80");
}
int main() { decisions(); directions_do_not_block(); countdown(); identities_expiry_focus(); contexts(); challenger(); parsing();
    std::printf("PASS %u checks\n",checks); }
