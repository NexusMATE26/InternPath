#include "internpath/matching.hpp"
#include <array>
#include <exception>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<int> parse_csv(const std::string& input) {
    std::vector<int> values;
    std::size_t begin = 0;
    do {
        const auto end = input.find(',', begin);
        const std::string part = input.substr(begin, end == std::string::npos ? end : end - begin);
        if (part.empty()) throw std::invalid_argument("empty CSV token");
        std::size_t parsed = 0;
        int value = std::stoi(part, &parsed);
        if (parsed != part.size()) throw std::invalid_argument("invalid integer token");
        values.push_back(value);
        if (end == std::string::npos) break;
        begin = end + 1;
    } while (true);
    return values;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 9) {
            throw std::invalid_argument("Usage: internpath_dsa --student a,b --required a,b --weights a,b --mandatory 0,1");
        }
        std::array<std::vector<int>, 4> inputs;
        constexpr std::array<const char*,4> flags{"--student","--required","--weights","--mandatory"};
        for (std::size_t i = 0; i < inputs.size(); ++i) {
            if (std::string(argv[1 + 2*i]) != flags[i]) {
                throw std::invalid_argument(std::string("expected ") + flags[i]);
            }
            inputs[i] = parse_csv(argv[2 + 2*i]);
        }
        const auto r = internpath::score_requirements(inputs[0], inputs[1], inputs[2], inputs[3]);
        std::cout << "{\"earned_points\":" << r.earned_points
                  << ",\"max_points\":" << r.max_points
                  << ",\"missing_mandatory\":" << r.missing_mandatory
                  << ",\"mandatory_requirements_met\":" << (r.missing_mandatory == 0 ? "true" : "false")
                  << ",\"coverage_percent\":" << std::fixed << std::setprecision(2) << r.coverage_percent
                  << "}" << std::endl;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "internpath_dsa error: " << error.what() << std::endl;
        return 2;
    }
}
