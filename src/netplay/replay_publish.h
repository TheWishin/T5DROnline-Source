/* Publish a completed replay snapshot without claiming success after exhausted
 * sharing-violation retries. The caller keeps the old destination and .tmp on
 * failure; a later snapshot/session end can retry. No filesystem dependency. */
#pragma once

namespace rp { namespace detail {
template <class Replace, class Pause>
bool publish_retry(Replace replace, Pause pause, unsigned attempts = 50)
{
    for (unsigned i = 0; i < attempts; ++i) {
        if (replace()) return true;
        if (i + 1 < attempts) pause();
    }
    return false;
}
} }
