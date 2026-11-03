/* Pure host menu policy; fake-clock/fake-pad tests need no game or runtime. */
#pragma once
#include <stdint.h>
#include <string>
#include <vector>
#include <map>
#include <limits>

namespace df { namespace ui {
constexpr size_t kMessageMax = 16384, kTextMax = 2048, kIdentityMax = 128;
constexpr uint16_t kConfirm = 0x4000, kCancel = 0x2000, kNext = 0x8000;
struct Prompt {
    uint64_t rev = 0, remaining_ms = 0, ack_seq = 0, received_ms = 0;
    std::string generation, session, prompt, match, kind, room_mode, policy;
    std::string title, body, confirm, cancel, next, ack_status;
    std::vector<std::string> allowed;
    bool permits(const std::string& a) const {
        for (const auto& v : allowed) if (v == a) return true;
        return false;
    }
    const char* mapped(uint16_t button) const {
        if(button==kConfirm) { if(permits("accept")) return "accept"; if(permits("ready")) return "ready";
            if(permits("back_to_line")) return "back_to_line"; }
        if(button==kCancel) { if(permits("decline")) return "decline"; if(permits("sit_out")) return "sit_out";
            if(permits("lobby")) return "lobby"; }
        if(button==kNext) { if(permits("next")) return "next"; if(permits("lobby")) return "lobby"; }
        return "";
    }
};
struct Action {
    uint64_t seq = 0;
    std::string generation, session, prompt, match, action;
};

/* Strict, bounded JSON subset: duplicate keys/types, overlong values, control
 * bytes, bad escapes/surrogates, negative/fractional counters are rejected.
 * Unknown fields are allowed only as scalar values for forward compatibility. */
class Reader {
    const std::string& s; size_t pos = 0;
    void ws() { while (pos < s.size() && (s[pos]==' ' || s[pos]=='\t' || s[pos]=='\r' || s[pos]=='\n')) ++pos; }
    bool take(char c) { ws(); if (pos == s.size() || s[pos] != c) return false; ++pos; return true; }
    bool hex(unsigned& cp) {
        cp = 0;
        for (int i=0;i<4;++i) { if (pos==s.size()) return false; char c=s[pos++];
            unsigned n = c>='0'&&c<='9' ? unsigned(c-'0') : c>='a'&&c<='f' ? unsigned(c-'a'+10) : c>='A'&&c<='F' ? unsigned(c-'A'+10) : 99;
            if(n>15) return false; cp=(cp<<4)|n; }
        return true;
    }
    static void utf8(std::string& out, unsigned cp) {
        if(cp<0x80) out+=(char)cp;
        else if(cp<0x800) { out+=(char)(0xc0|(cp>>6)); out+=(char)(0x80|(cp&63)); }
        else if(cp<0x10000) { out+=(char)(0xe0|(cp>>12)); out+=(char)(0x80|((cp>>6)&63)); out+=(char)(0x80|(cp&63)); }
        else { out+=(char)(0xf0|(cp>>18)); out+=(char)(0x80|((cp>>12)&63)); out+=(char)(0x80|((cp>>6)&63)); out+=(char)(0x80|(cp&63)); }
    }
    bool str(std::string& out) {
        if(!take('"')) return false; out.clear();
        while(pos<s.size()) {
            unsigned char c=(unsigned char)s[pos++];
            if(c=='"') return true;
            if(c<32) return false;
            if(c=='\\') {
                if(pos==s.size()) return false; c=(unsigned char)s[pos++];
                if(c=='u') { unsigned cp; if(!hex(cp)) return false;
                    if(cp>=0xd800&&cp<=0xdbff) { if(pos+2>s.size()||s[pos++]!='\\'||s[pos++]!='u') return false;
                        unsigned lo; if(!hex(lo)||lo<0xdc00||lo>0xdfff) return false; cp=0x10000+((cp-0xd800)<<10)+(lo-0xdc00); }
                    else if(cp>=0xdc00&&cp<=0xdfff) return false;
                    if(cp==0) return false; utf8(out,cp);
                } else { switch(c) {
                    case '"': case '\\': case '/': out+=(char)c; break;
                    case 'n': out+='\n'; break; case 'r': out+='\r'; break; case 't': out+='\t'; break;
                    case 'b': out+='\b'; break; case 'f': out+='\f'; break; default:return false; }
                }
            } else if(c>=0x80) {
                unsigned cp=0, n=0, min=0;
                if(c>=0xc2&&c<=0xdf) { cp=c&31; n=1; min=0x80; }
                else if(c>=0xe0&&c<=0xef) { cp=c&15; n=2; min=0x800; }
                else if(c>=0xf0&&c<=0xf4) { cp=c&7; n=3; min=0x10000; }
                else return false;
                for(unsigned j=0;j<n;++j) { if(pos==s.size()) return false; unsigned char d=(unsigned char)s[pos++];
                    if((d&0xc0)!=0x80) return false; cp=(cp<<6)|(d&63); }
                if(cp<min||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff)) return false; utf8(out,cp);
            } else out+=(char)c;
            if(out.size()>kTextMax) return false;
        }
        return false;
    }
    bool number(uint64_t& v) {
        ws(); size_t begin=pos; v=0;
        while(pos<s.size()&&s[pos]>='0'&&s[pos]<='9') {
            unsigned d=(unsigned)(s[pos++]-'0');
            if(v>(std::numeric_limits<uint64_t>::max()-d)/10) return false; v=v*10+d;
        }
        return pos>begin && (pos-begin==1 || s[begin]!='0');
    }
public:
    explicit Reader(const std::string& text):s(text) {}
    bool parse(Prompt& p) {
        if(s.empty()||s.size()>kMessageMax||!take('{')) return false;
        std::map<std::string,bool> seen; uint64_t version=0;
        for(unsigned fields=0;;++fields) {
            if(fields>40) return false;
            std::string key; if(!str(key)||seen[key]||!take(':')) return false; seen[key]=true;
            uint64_t* n=key=="v"?&version:key=="rev"?&p.rev:key=="remaining_ms"?&p.remaining_ms:key=="ack_seq"?&p.ack_seq:nullptr;
            std::string* t=key=="generation"?&p.generation:key=="session"?&p.session:key=="prompt"?&p.prompt:key=="match"?&p.match:
                key=="kind"?&p.kind:key=="room_mode"?&p.room_mode:key=="policy"?&p.policy:key=="title"?&p.title:key=="body"?&p.body:
                key=="confirm"?&p.confirm:key=="cancel"?&p.cancel:key=="next"?&p.next:key=="ack_status"?&p.ack_status:nullptr;
            if(n) { if(!number(*n)) return false; }
            else if(t) { if(!str(*t)) return false; }
            else if(key=="allowed") {
                if(!take('[')) return false; ws();
                if(pos<s.size()&&s[pos]==']') ++pos;
                else for(;;) { std::string a; if(!str(a)||a.size()>32||p.allowed.size()>=8) return false;
                    for(const auto& old:p.allowed) if(a==old) return false; p.allowed.push_back(a);
                    if(take(']')) break; if(!take(',')) return false; }
            } else { /* unknown scalar */
                ws(); std::string ignored;
                if(pos<s.size()&&s[pos]=='"') { if(!str(ignored)) return false; }
                else { size_t b=pos; while(pos<s.size()&&s[pos]!=','&&s[pos]!='}'&&s[pos]!=' '&&s[pos]!='\n'&&s[pos]!='\r'&&s[pos]!='\t') ++pos;
                    std::string v=s.substr(b,pos-b); if(v!="true"&&v!="false"&&v!="null") return false; }
            }
            if(take('}')) break; if(!take(',')) return false;
        }
        ws();
        return pos==s.size()&&version==1&&p.rev&&seen["remaining_ms"]&&seen["allowed"]&&
            !p.generation.empty()&&p.generation.size()<=kIdentityMax&&!p.session.empty()&&p.session.size()<=kIdentityMax&&
            p.prompt.size()<=kIdentityMax&&p.match.size()<=kIdentityMax&&p.kind.size()<=32&&p.remaining_ms<=120000&&
            (p.kind=="hidden"||(!p.prompt.empty()&&!p.match.empty()));
    }
};
inline bool parse_prompt(const std::string& text, Prompt& out) { Prompt p; if(!Reader(text).parse(p)) return false; out=p; return true; }

class Menu {
    Prompt p_; Action pending_; uint64_t seq_=0; bool armed_=false, focused_=false;
    uint16_t previous_=0;
public:
    const Prompt& prompt() const { return p_; }
    const Action& pending() const { return pending_; }
    void invalidate() { p_.kind="hidden"; p_.remaining_ms=0; armed_=false; focused_=false; previous_=0; }
    bool update(const Prompt& p, uint64_t now, const std::string& generation, const std::string& session) {
        if(p.generation!=generation||p.session!=session||p.rev<=p_.rev) return false;
        if(pending_.seq && p.ack_seq==pending_.seq && (p.ack_status=="ok"||p.ack_status=="rejected")) pending_=Action();
        if(p.prompt!=p_.prompt||p.match!=p_.match||p.kind!=p_.kind) { armed_=false; previous_=0; }
        p_=p; p_.received_ms=now; return true;
    }
    bool visible(uint64_t now) const {
        return p_.rev && p_.kind!="hidden" && p_.kind!="" && p_.remaining_ms && now>=p_.received_ms && now-p_.received_ms<p_.remaining_ms;
    }
    uint64_t remaining(uint64_t now) const { return visible(now)?p_.remaining_ms-(now-p_.received_ms):0; }
    bool tick(uint16_t buttons, bool focus, uint64_t now, bool live=true) {
        if(!live) return false;
        if(!focus||!visible(now)) { armed_=false; previous_=buttons; focused_=focus; return false; }
        if(!focused_) armed_=false; focused_=true;
        const uint16_t relevant=(uint16_t)(buttons&(kConfirm|kCancel|kNext));
        if(!armed_) { if(!buttons) armed_=true; previous_=buttons; return false; }
        uint16_t edge=(uint16_t)(relevant&~previous_); previous_=buttons;
        if(!edge||pending_.seq || (edge&(edge-1))) return false;
        const char* action=p_.mapped(edge);
        if(!*action) return false;
        pending_={++seq_,p_.generation,p_.session,p_.prompt,p_.match,action}; return true;
    }
};
} }
