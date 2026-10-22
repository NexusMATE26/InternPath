#pragma once
#include <vector>

namespace internpath {
struct MatchResult {
    int earned_points{};
    int max_points{};
    int missing_mandatory{};
    double coverage_percent{};
};

// Temporary phase-1 std::vector contract. We will replace teaching containers
// with well-tested custom structures where the DSA lab requires them.
MatchResult score_requirements(
    const std::vector<int>& student_levels,
    const std::vector<int>& required_levels,
    const std::vector<int>& weights,
    const std::vector<int>& mandatory
);
}
