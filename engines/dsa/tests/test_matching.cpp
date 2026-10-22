#include "internpath/matching.hpp"
#include <iostream>
#include <stdexcept>

int main() {
    using internpath::score_requirements;
    const auto demo = score_requirements({2,1,0,1}, {2,2,1,1}, {5,4,3,2}, {1,1,0,0});
    if (demo.earned_points != 54 || demo.max_points != 84 || demo.missing_mandatory != 1 ||
        demo.coverage_percent < 64.28 || demo.coverage_percent > 64.30) {
        std::cerr << "demo matching score mismatch\n";
        return 1;
    }
    const auto capped = score_requirements({3}, {2}, {5}, {1});
    if (capped.earned_points != 30 || capped.missing_mandatory != 0) {
        std::cerr << "overqualification cap incorrect\n";
        return 1;
    }
    bool rejected = false;
    try { score_requirements({2}, {2,1}, {5}, {1}); }
    catch (const std::invalid_argument&) { rejected = true; }
    if (!rejected) return 1;
    rejected = false;
    try { score_requirements({4}, {2}, {5}, {1}); }
    catch (const std::invalid_argument&) { rejected = true; }
    if (!rejected) return 1;
    rejected = false;
    try { score_requirements({0}, {1}, {0}, {1}); }
    catch (const std::invalid_argument&) { rejected = true; }
    if (!rejected) return 1;
    return 0;
}
