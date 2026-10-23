#include "internpath/matching.hpp"
#include "internpath/graph/skill_graph.hpp"
#include "internpath/graph/learning_path_engine.hpp"
#include "nlohmann/json.hpp"

#include <array>
#include <exception>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using internpath::ds::DynamicArray;
using internpath::ds::HashTable;
using internpath::graph::LearningPathEngine;
using internpath::graph::LearningPlan;
using internpath::graph::SkillGraph;
using internpath::graph::StudentSkill;
using internpath::graph::TargetRequirement;

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

SkillGraph build_curated_skill_graph() {
    SkillGraph g;
    g.add_skill(1, "Programming Foundations", "Foundations", 3, "Core logic, variables, control flow");
    g.add_skill(2, "Python Programming", "Languages", 3, "Python syntax, idioms, OOP");
    g.add_skill(3, "C++ Systems Programming", "Languages", 3, "C++20, memory, pointers, RAII");
    g.add_skill(4, "Backend APIs (FastAPI)", "Backend", 3, "REST APIs, async, HTTP, serialization");
    g.add_skill(5, "Data Structures & Algorithms", "Algorithms", 3, "Trees, graphs, dynamic programming");
    g.add_skill(6, "High-Scale Distributed Systems", "Systems", 3, "Consensus, caching, microservices");
    g.add_skill(7, "Git & Linux Fundamentals", "Tools", 3, "Version control, bash, debugging");
    g.add_skill(8, "Docker & Containerization", "DevOps", 3, "Images, containers, docker-compose");
    g.add_skill(9, "Relational Databases & SQL", "Backend", 3, "Schema design, indexing, transactions");
    g.add_skill(10, "Cloud Deployment & K8s", "DevOps", 3, "Kubernetes, cloud architecture, CI/CD");

    // Dependencies (Prerequisite -> Unlocked)
    g.add_prerequisite(1, 2);  // Foundations -> Python
    g.add_prerequisite(1, 3);  // Foundations -> C++
    g.add_prerequisite(2, 4);  // Python -> Backend (FastAPI)
    g.add_prerequisite(9, 4);  // SQL -> Backend (FastAPI)
    g.add_prerequisite(3, 5);  // C++ -> DSA
    g.add_prerequisite(4, 6);  // Backend -> Distributed Systems
    g.add_prerequisite(5, 6);  // DSA -> Distributed Systems
    g.add_prerequisite(7, 8);  // Git/Linux -> Docker
    g.add_prerequisite(8, 10); // Docker -> Kubernetes
    return g;
}

void print_learning_plan_json(const LearningPlan& plan) {
    std::cout << "{\n"
              << "  \"achievable\": " << (plan.is_achievable ? "true" : "false") << ",\n"
              << "  \"message\": \"" << plan.message << "\",\n"
              << "  \"target_skills\": [";
    for (std::size_t i = 0; i < plan.target_skills.size(); ++i) {
        std::cout << plan.target_skills[i] << (i + 1 < plan.target_skills.size() ? ", " : "");
    }
    std::cout << "],\n  \"missing_skills\": [";
    for (std::size_t i = 0; i < plan.missing_skills.size(); ++i) {
        std::cout << plan.missing_skills[i] << (i + 1 < plan.missing_skills.size() ? ", " : "");
    }
    std::cout << "],\n  \"prerequisite_closure\": [";
    for (std::size_t i = 0; i < plan.prerequisite_closure.size(); ++i) {
        std::cout << plan.prerequisite_closure[i] << (i + 1 < plan.prerequisite_closure.size() ? ", " : "");
    }
    std::cout << "],\n  \"total_estimated_effort\": {\n"
              << "    \"min_hours\": " << plan.total_estimated_effort.min_hours << ",\n"
              << "    \"max_hours\": " << plan.total_estimated_effort.max_hours << "\n"
              << "  },\n  \"stages\": [\n";

    for (std::size_t s = 0; s < plan.stages.size(); ++s) {
        const auto& stage = plan.stages[s];
        std::cout << "    {\n"
                  << "      \"stage_number\": " << stage.stage_number << ",\n"
                  << "      \"stage_title\": \"" << stage.stage_title << "\",\n"
                  << "      \"stage_effort\": {\"min_hours\": " << stage.stage_effort.min_hours
                  << ", \"max_hours\": " << stage.stage_effort.max_hours << "},\n"
                  << "      \"skills\": [\n";
        for (std::size_t k = 0; k < stage.skills.size(); ++k) {
            const auto& sk = stage.skills[k];
            std::cout << "        {\n"
                      << "          \"skill_id\": " << sk.skill_id << ",\n"
                      << "          \"skill_name\": \"" << sk.skill_name << "\",\n"
                      << "          \"category\": \"" << sk.category << "\",\n"
                      << "          \"current_level\": " << sk.current_level << ",\n"
                      << "          \"target_level\": " << sk.target_level << ",\n"
                      << "          \"level_delta\": " << sk.level_delta << ",\n"
                      << "          \"is_verified\": " << (sk.is_verified ? "true" : "false") << ",\n"
                      << "          \"verification_status\": \"" << sk.verification_status << "\",\n"
                      << "          \"estimated_effort\": {\"min_hours\": " << sk.estimated_effort.min_hours
                      << ", \"max_hours\": " << sk.estimated_effort.max_hours << "},\n"
                      << "          \"rationale\": \"" << sk.rationale << "\"\n"
                      << "        }" << (k + 1 < stage.skills.size() ? ",\n" : "\n");
        }
        std::cout << "      ]\n"
                  << "    }" << (s + 1 < plan.stages.size() ? ",\n" : "\n");
    }
    std::cout << "  ],\n  \"algorithm_trace\": {\n"
              << "    \"graph_representation\": \"Directed Adjacency Lists via HashTable<int, DynamicArray<int>>\",\n"
              << "    \"graph_node_count\": " << plan.trace.graph_node_count << ",\n"
              << "    \"graph_edge_count\": " << plan.trace.graph_edge_count << ",\n"
              << "    \"prerequisite_closure_nodes_visited\": " << plan.trace.prerequisite_closure_nodes_visited << ",\n"
              << "    \"kahn_queue_enqueues\": " << plan.trace.kahn_queue_enqueues << ",\n"
              << "    \"kahn_queue_dequeues\": " << plan.trace.kahn_queue_dequeues << ",\n"
              << "    \"topo_stages_formed\": " << plan.trace.topo_stages_formed << ",\n"
              << "    \"execution_time_microseconds\": " << std::fixed << std::setprecision(2)
              << plan.trace.execution_time_microseconds << "\n"
              << "  }\n}\n";
}

void execute_plan_from_json(const nlohmann::json& req) {
    SkillGraph graph;

    // 1. Populate skills from JSON (Single source of truth from PostgreSQL)
    if (req.contains("skills") && req["skills"].is_array()) {
        for (const auto& s : req["skills"]) {
            int id = s.value("id", 0);
            std::string name = s.value("name", "Skill " + std::to_string(id));
            std::string category = s.value("category", "General");
            int max_level = s.value("max_level", 3);
            std::string desc = s.value("description", "");
            graph.add_skill(id, name, category, max_level, desc);
        }
    }

    // 2. Populate prerequisite edges from JSON
    if (req.contains("prerequisites") && req["prerequisites"].is_array()) {
        for (const auto& p : req["prerequisites"]) {
            int from_id = p.value("prereq_id", p.value("from", 0));
            int to_id = p.value("skill_id", p.value("to", 0));
            if (from_id > 0 && to_id > 0) {
                graph.add_prerequisite(from_id, to_id);
            }
        }
    }

    // 3. Targets
    DynamicArray<TargetRequirement> targets;
    if (req.contains("targets") && req["targets"].is_array()) {
        for (const auto& t : req["targets"]) {
            int sid = t.value("skill_id", 0);
            int req_lvl = t.value("required_level", 1);
            bool mandatory = t.value("mandatory", true);
            std::string context = t.value("role_context", "Target Requirement");
            targets.push_back(TargetRequirement{sid, req_lvl, mandatory, context});
        }
    }

    // 4. Student Skills
    HashTable<int, StudentSkill> student;
    if (req.contains("student_skills") && req["student_skills"].is_array()) {
        for (const auto& st : req["student_skills"]) {
            int sid = st.value("skill_id", 0);
            int declared_lvl = st.value("declared_level", st.value("level", 0));
            int verified_lvl = st.value("verified_level", 0);
            bool is_ver = st.value("is_verified", false);
            student.insert(
                sid,
                StudentSkill{
                    sid,
                    declared_lvl,
                    is_ver ? (verified_lvl > 0 ? verified_lvl : declared_lvl) : 0,
                    is_ver
                }
            );
        }
    }

    LearningPathEngine engine;
    LearningPlan plan = engine.generate_plan(graph, student, targets);
    print_learning_plan_json(plan);
}

} // namespace

int main(int argc, char** argv) {
    try {
        if (argc < 2) {
            std::cerr << "Usage:\n"
                      << "  Matching Mode: internpath_dsa --student a,b --required a,b --weights a,b --mandatory 0,1\n"
                      << "  Plan Stdin:    internpath_dsa --plan-stdin < request.json\n"
                      << "  Plan JSON:     internpath_dsa --plan-json '<json>'\n"
                      << "  Plan Demo:     internpath_dsa --demo-plan\n"
                      << "  Custom Plan:   internpath_dsa --plan --target <id:level,...> [--student <id:level:v|u,...>]\n";
            return 1;
        }

        std::string mode = argv[1];

        // Mode 1: Phase 1 Matching Mode (strict contract preservation)
        if (mode == "--student") {
            if (argc != 9) {
                throw std::invalid_argument("Usage: internpath_dsa --student a,b --required a,b --weights a,b --mandatory 0,1");
            }
            std::array<std::vector<int>, 4> inputs;
            constexpr std::array<const char*, 4> flags{"--student", "--required", "--weights", "--mandatory"};
            for (std::size_t i = 0; i < inputs.size(); ++i) {
                if (std::string(argv[1 + 2 * i]) != flags[i]) {
                    throw std::invalid_argument(std::string("expected ") + flags[i]);
                }
                inputs[i] = parse_csv(argv[2 + 2 * i]);
            }
            const auto r = internpath::score_requirements(inputs[0], inputs[1], inputs[2], inputs[3]);
            std::cout << "{\"earned_points\":" << r.earned_points
                      << ",\"max_points\":" << r.max_points
                      << ",\"missing_mandatory\":" << r.missing_mandatory
                      << ",\"mandatory_requirements_met\":" << (r.missing_mandatory == 0 ? "true" : "false")
                      << ",\"coverage_percent\":" << std::fixed << std::setprecision(2) << r.coverage_percent
                      << "}" << std::endl;
            return 0;
        }

        // Mode 2: Phase 3.2 Plan from STDIN (Production transport from PostgreSQL backend)
        if (mode == "--plan-stdin") {
            std::string input_str((std::istreambuf_iterator<char>(std::cin)),
                                  std::istreambuf_iterator<char>());
            if (input_str.empty()) {
                throw std::invalid_argument("Empty JSON payload on stdin for --plan-stdin");
            }
            auto req = nlohmann::json::parse(input_str);
            execute_plan_from_json(req);
            return 0;
        }

        // Mode 3: Phase 3.2 Plan from JSON argument
        if (mode == "--plan-json") {
            if (argc < 3) {
                throw std::invalid_argument("Expected JSON string after --plan-json");
            }
            auto req = nlohmann::json::parse(argv[2]);
            execute_plan_from_json(req);
            return 0;
        }

        // Mode 4: Academic Demo Plan (curated graph)
        if (mode == "--demo-plan") {
            SkillGraph graph = build_curated_skill_graph();
            LearningPathEngine engine;

            HashTable<int, StudentSkill> student;
            student.insert(1, StudentSkill{1, 2, 2, true});  // Foundations verified level 2
            student.insert(2, StudentSkill{2, 2, 2, true});  // Python verified level 2
            student.insert(7, StudentSkill{7, 1, 0, false}); // Git declared level 1 (unverified)

            DynamicArray<TargetRequirement> targets;
            targets.push_back(TargetRequirement{6, 3, true, "Distributed Systems Engineering Intern"});

            LearningPlan plan = engine.generate_plan(graph, student, targets);
            print_learning_plan_json(plan);
            return 0;
        }

        // Mode 5: Custom Learning Path Generation (CLI flags)
        if (mode == "--plan") {
            SkillGraph graph = build_curated_skill_graph();
            LearningPathEngine engine;

            DynamicArray<TargetRequirement> targets;
            HashTable<int, StudentSkill> student;

            for (int i = 2; i < argc; ++i) {
                std::string arg = argv[i];
                if (arg == "--target" && i + 1 < argc) {
                    std::string target_str = argv[++i];
                    std::stringstream ss(target_str);
                    std::string token;
                    while (std::getline(ss, token, ',')) {
                        auto colon = token.find(':');
                        if (colon != std::string::npos) {
                            int id = std::stoi(token.substr(0, colon));
                            int lvl = std::stoi(token.substr(colon + 1));
                            targets.push_back(TargetRequirement{id, lvl, true, "Target Requirement"});
                        }
                    }
                } else if (arg == "--student" && i + 1 < argc) {
                    std::string student_str = argv[++i];
                    std::stringstream ss(student_str);
                    std::string token;
                    while (std::getline(ss, token, ',')) {
                        auto c1 = token.find(':');
                        if (c1 != std::string::npos) {
                            int id = std::stoi(token.substr(0, c1));
                            auto c2 = token.find(':', c1 + 1);
                            int lvl = 1;
                            bool ver = false;
                            if (c2 != std::string::npos) {
                                lvl = std::stoi(token.substr(c1 + 1, c2 - c1 - 1));
                                std::string v_str = token.substr(c2 + 1);
                                ver = (v_str == "v" || v_str == "true" || v_str == "1");
                            } else {
                                lvl = std::stoi(token.substr(c1 + 1));
                            }
                            student.insert(id, StudentSkill{id, lvl, ver ? lvl : 0, ver});
                        }
                    }
                }
            }

            if (targets.empty()) {
                targets.push_back(TargetRequirement{6, 3, true, "Distributed Systems Intern"});
            }

            LearningPlan plan = engine.generate_plan(graph, student, targets);
            print_learning_plan_json(plan);
            return 0;
        }

        std::cerr << "internpath_dsa error: unrecognized option " << mode << std::endl;
        return 1;
    } catch (const std::exception& error) {
        std::cerr << "internpath_dsa error: " << error.what() << std::endl;
        return 2;
    }
}
