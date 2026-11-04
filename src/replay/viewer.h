/* Local replay viewer policy. No guest memory, devices, files or online state. */
#pragma once
#include <algorithm>
#include <cstdint>
#include <limits>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace rv {

struct Viewer {
    bool paused = false;
    double speed = 1.0;
    int control = 0;                       /* 0 recording, 1 local P1, 2 local P2 */
    bool verified = true;
    uint32_t unverified_from = (std::numeric_limits<uint32_t>::max)();
    bool seek_pending = false;
    uint32_t seek_frame = 0;
    bool step_pending = false;

    /* One complete, strictly parsed command. Invalid input has no effects.
     * The caller supplies the seekable portion of this replay, inclusive.
     * Taking control permanently taints the playback, including after a seek
     * or switching back to recorded input; it never claims verification again. */
    bool command(const std::string& text, uint32_t frame, uint32_t min_frame, uint32_t max_frame)
    {
        std::istringstream input(text);
        std::string op, arg, extra;
        if (!(input >> op)) return false;
        input >> arg;
        if (input >> extra) return false;
        if (op == "pause" && arg.empty()) { paused = true; step_pending = false; return true; }
        if (op == "resume" && arg.empty()) { paused = false; step_pending = false; return true; }
        if (op == "step" && arg.empty()) { paused = true; step_pending = true; return true; }
        if (op == "speed") {
            /* A fixed set also rejects NaN, infinity and locale-dependent numbers. */
            if (arg == "0.25") speed = 0.25;
            else if (arg == "0.5") speed = 0.5;
            else if (arg == "1" || arg == "1.0") speed = 1.0;
            else if (arg == "2" || arg == "2.0") speed = 2.0;
            else if (arg == "4" || arg == "4.0") speed = 4.0;
            else return false;
            return true;
        }
        if (op == "seek") {
            if (arg.empty() || min_frame > max_frame) return false;
            uint32_t value = 0;
            for (char c : arg) {
                if (c < '0' || c > '9') return false;
                const uint32_t digit = static_cast<uint32_t>(c - '0');
                value = value > ((std::numeric_limits<uint32_t>::max)() - digit) / 10u
                      ? (std::numeric_limits<uint32_t>::max)() : value * 10u + digit;
            }
            seek_frame = (std::max)(min_frame, (std::min)(max_frame, value));
            seek_pending = true;
            step_pending = false;
            return true;
        }
        if (op == "control" && (arg == "0" || arg == "1" || arg == "2")) {
            control = arg[0] - '0';
            if (control) {
                verified = false;
                unverified_from = (std::min)(unverified_from, frame);
            }
            return true;
        }
        return false;
    }

    bool permit_frame()
    {
        if (!paused) return true;
        if (!step_pending) return false;
        step_pending = false;
        return true;
    }

    bool take_seek(uint32_t* target)
    {
        if (!seek_pending || !target) return false;
        *target = seek_frame;
        seek_pending = false;
        return true;
    }
};

/* Bounded checkpoint index. Keep the earliest checkpoint as a fallback so an
 * evicted interval can still be reached by resimulation. T owns the snapshot
 * (normally compressed memory plus the frame-boundary host state). */
template<class T> class Checkpoints {
public:
    struct Entry { uint32_t frame; T state; };

    explicit Checkpoints(size_t limit = 8, uint32_t interval = 300)
        : limit_(std::max<size_t>(2, limit)), interval_((std::max)(1u, interval)) {}

    bool due(uint32_t frame) const
    {
        return entries_.empty() || (frame >= entries_.back().frame && frame - entries_.back().frame >= interval_);
    }

    void add(uint32_t frame, T state)
    {
        auto at = std::lower_bound(entries_.begin(), entries_.end(), frame,
                                  [](const Entry& e, uint32_t f) { return e.frame < f; });
        if (at != entries_.end() && at->frame == frame) at->state = std::move(state);
        else entries_.insert(at, Entry{frame, std::move(state)});
        while (entries_.size() > limit_) entries_.erase(entries_.begin() + 1);
    }

    const Entry* at_or_before(uint32_t frame) const
    {
        const Entry* found = nullptr;
        for (const Entry& e : entries_) {
            if (e.frame > frame) break;
            found = &e;
        }
        return found;
    }

    void discard_after(uint32_t frame)
    {
        entries_.erase(std::remove_if(entries_.begin(), entries_.end(),
                                     [frame](const Entry& e) { return e.frame > frame; }), entries_.end());
    }
    void clear() { entries_.clear(); }
    size_t size() const { return entries_.size(); }
    const std::vector<Entry>& entries() const { return entries_; }

private:
    size_t limit_;
    uint32_t interval_;
    std::vector<Entry> entries_;
};

} // namespace rv
