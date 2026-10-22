#include "internpath/matching.hpp"
#include <algorithm>
#include <stdexcept>

namespace internpath {
MatchResult score_requirements(const std::vector<int>& student_levels,
                               const std::vector<int>& required_levels,
                               const std::vector<int>& weights,
                               const std::vector<int>& mandatory) {
    const auto n = student_levels.size();
    if (n == 0 || n > 256 || required_levels.size() != n ||
        weights.size() != n || mandatory.size() != n) {
        throw std::invalid_argument("arrays must have the same nonzero length, at most 256");
    }
    MatchResult result;
    for (std::size_t i = 0; i < n; ++i) {
        int level = student_levels[i];
        int required = required_levels[i];
        int weight = weights[i];
        int is_mandatory = mandatory[i];
        if (level < 0 || level > 3 || required < 1 || required > 3 ||
            weight < 1 || weight > 5 || (is_mandatory != 0 && is_mandatory != 1)) {
            throw std::invalid_argument("levels/weights/mandatory value out of range");
        }
        result.earned_points += weight * (6 * std::min(level, required) / required);
        result.max_points += weight * 6;
        if (is_mandatory && level < required) ++result.missing_mandatory;
    }
    result.coverage_percent = 100.0 * result.earned_points / result.max_points;
    return result;
}
}
