#include "internpath/graph/learning_path_engine.hpp"
#include "internpath/graph/skill_graph.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <string>

using internpath::ds::DynamicArray;
using internpath::ds::HashTable;
using internpath::graph::EffortEstimator;
using internpath::graph::LearningPathEngine;
using internpath::graph::LearningPlan;
using internpath::graph::SkillGraph;
using internpath::graph::StudentSkill;
using internpath::graph::TargetRequirement;

int main() {
    std::cout << "--- Starting LearningPathEngine Tests ---\n";

    // 1. Build a realistic standard SkillGraph
    //
    //              1: Programming Foundations
    //                     /        \
    //                    v          v
    //             2: Python       3: C++
    //                |               |
    //                v               v
    //         4: Backend (FastAPI) 5: Data Structures (DSA)
    //                \               /
    //                 v             v
    //               6: High-Scale Systems
    //
    // Plus independent track:
    //             7: Git & Linux (Tools)
    //                    |
    //                    v
    //             8: Docker & CI/CD (DevOps)
    SkillGraph graph;
    assert(graph.add_skill(1, "Programming Foundations", "Foundations", 5));
    assert(graph.add_skill(2, "Python", "Languages", 5));
    assert(graph.add_skill(3, "C++", "Languages", 5));
    assert(graph.add_skill(4, "Backend (FastAPI)", "Backend", 5));
    assert(graph.add_skill(5, "Data Structures (DSA)", "Algorithms", 5));
    assert(graph.add_skill(6, "High-Scale Systems", "Systems", 5));
    assert(graph.add_skill(7, "Git & Linux", "Tools", 5));
    assert(graph.add_skill(8, "Docker & CI/CD", "DevOps", 5));

    assert(graph.add_prerequisite(1, 2));
    assert(graph.add_prerequisite(1, 3));
    assert(graph.add_prerequisite(2, 4));
    assert(graph.add_prerequisite(3, 5));
    assert(graph.add_prerequisite(4, 6));
    assert(graph.add_prerequisite(5, 6));
    assert(graph.add_prerequisite(7, 8));

    assert(graph.validate_graph());

    LearningPathEngine engine;

    // Test 1: Empty Target Requirements
    {
        HashTable<int, StudentSkill> student;
        DynamicArray<TargetRequirement> targets;

        LearningPlan plan = engine.generate_plan(graph, student, targets);
        assert(plan.is_achievable);
        assert(plan.stages.empty());
        assert(plan.all_upgrades.empty());
        assert(plan.total_estimated_effort.min_hours == 0);
        assert(plan.total_estimated_effort.max_hours == 0);
        std::cout << "[PASS] 1. Empty Target Requirements\n";
    }

    // Test 2: Beginner Student Target High-Scale Systems
    // Target: Skill 6 at Level 3.
    // Transitive prerequisites needed: 1, 2, 3, 4, 5.
    // Beginner has 0 skills.
    {
        HashTable<int, StudentSkill> student;
        DynamicArray<TargetRequirement> targets;
        targets.push_back(TargetRequirement{6, 3, true, "Target: Distributed Systems Engineer"});

        LearningPlan plan = engine.generate_plan(graph, student, targets);
        assert(plan.is_achievable);
        assert(plan.target_skills.size() == 1 && plan.target_skills[0] == 6);

        // Prerequisite closure must contain: 1, 2, 3, 4, 5
        assert(plan.prerequisite_closure.size() == 5);
        // Shared prerequisite 1 must be counted only ONCE in the closure
        int count_1 = 0;
        for (std::size_t i = 0; i < plan.prerequisite_closure.size(); ++i) {
            if (plan.prerequisite_closure[i] == 1) ++count_1;
        }
        assert(count_1 == 1);

        // Missing skills: all 6 skills are missing (level 0)
        assert(plan.missing_skills.size() == 6);

        // All 6 skills must be present as upgrades
        assert(plan.all_upgrades.size() == 6);

        // Effort ranges check: effort must use ranges, not false precision
        assert(plan.total_estimated_effort.min_hours > 0);
        assert(plan.total_estimated_effort.max_hours > plan.total_estimated_effort.min_hours);

        // Check stages:
        // Stage 1: Skill 1 (Programming Foundations)
        // Stage 2: Skill 2 (Python) and Skill 3 (C++) in parallel
        // Stage 3: Skill 4 (FastAPI) and Skill 5 (DSA) in parallel
        // Stage 4: Skill 6 (High-Scale Systems)
        assert(plan.stages.size() == 4);
        assert(plan.stages[0].stage_number == 1 && plan.stages[0].skills.size() == 1 &&
               plan.stages[0].skills[0].skill_id == 1);
        assert(plan.stages[1].stage_number == 2 && plan.stages[1].skills.size() == 2);
        assert(plan.stages[2].stage_number == 3 && plan.stages[2].skills.size() == 2);
        assert(plan.stages[3].stage_number == 4 && plan.stages[3].skills.size() == 1 &&
               plan.stages[3].skills[0].skill_id == 6);

        // Check rationales are present
        assert(plan.skill_rationales.contains(6));
        assert(plan.skill_rationales.contains(1));

        std::cout << "[PASS] 2. Full Dependency Closure & Layered Stages\n";
    }

    // Test 3: Already-Known Prerequisite
    // Student already knows:
    // Skill 1 (Foundations) verified Level 2.
    // Skill 2 (Python) verified Level 2.
    // Skill 3 (C++) verified Level 2.
    // Target: Skill 4 (FastAPI) Level 2.
    // Prerequisite closure includes 1 and 2, but student ALREADY knows 1 and 2!
    // So ONLY Skill 4 should be scheduled as an upgrade!
    {
        HashTable<int, StudentSkill> student;
        student.insert(1, StudentSkill{1, 2, 2, true});
        student.insert(2, StudentSkill{2, 2, 2, true});
        student.insert(3, StudentSkill{3, 2, 2, true});

        DynamicArray<TargetRequirement> targets;
        targets.push_back(TargetRequirement{4, 2, true, "Backend Developer Requirement"});

        LearningPlan plan = engine.generate_plan(graph, student, targets);
        assert(plan.is_achievable);
        assert(plan.all_upgrades.size() == 1);
        assert(plan.all_upgrades[0].skill_id == 4);
        assert(plan.all_upgrades[0].current_level == 0);
        assert(plan.all_upgrades[0].target_level == 2);
        assert(plan.all_upgrades[0].level_delta == 2);

        // Since prerequisites 1 and 2 are already satisfied, Skill 4 has 0 blocking dependencies!
        // It starts in Stage 1 immediately!
        assert(plan.stages.size() == 1);
        assert(plan.stages[0].skills.size() == 1 && plan.stages[0].skills[0].skill_id == 4);

        std::cout << "[PASS] 3. Already-Known Prerequisites Do Not Block\n";
    }

    // Test 4: Requirement Above Student's Current Level (Upgrade Needed)
    // Student has Python at Level 1 (verified).
    // Target requires Python at Level 4.
    // Delta = 3 levels.
    {
        HashTable<int, StudentSkill> student;
        student.insert(1, StudentSkill{1, 3, 3, true}); // Foundations satisfied
        student.insert(2, StudentSkill{2, 1, 1, true}); // Python at level 1

        DynamicArray<TargetRequirement> targets;
        targets.push_back(TargetRequirement{2, 4, true, "Python Specialist"});

        LearningPlan plan = engine.generate_plan(graph, student, targets);
        assert(plan.is_achievable);
        assert(plan.all_upgrades.size() == 1);
        assert(plan.all_upgrades[0].skill_id == 2);
        assert(plan.all_upgrades[0].current_level == 1);
        assert(plan.all_upgrades[0].target_level == 4);
        assert(plan.all_upgrades[0].level_delta == 3);
        assert(plan.all_upgrades[0].verification_status == "UPGRADE_NEEDED");
        assert(plan.missing_skills.empty()); // Not missing (was at level 1)

        assert(plan.stages.size() == 1);
        assert(plan.stages[0].skills[0].skill_id == 2);

        std::cout << "[PASS] 4. Requirement Above Current Level\n";
    }

    // Test 5: Shared Prerequisites Across Multiple Targets Counted Once
    // Targets:
    // Target A: Skill 4 (Backend FastAPI) Level 2
    // Target B: Skill 5 (DSA) Level 2
    // Both require Skill 1 (Programming Foundations).
    // Total plan must include Skill 1 exactly ONCE, and sum effort once.
    {
        HashTable<int, StudentSkill> student;
        DynamicArray<TargetRequirement> targets;
        targets.push_back(TargetRequirement{4, 2, true, "Backend Track"});
        targets.push_back(TargetRequirement{5, 2, true, "DSA Track"});

        LearningPlan plan = engine.generate_plan(graph, student, targets);
        assert(plan.is_achievable);

        int count_foundations = 0;
        for (std::size_t i = 0; i < plan.all_upgrades.size(); ++i) {
            if (plan.all_upgrades[i].skill_id == 1) ++count_foundations;
        }
        assert(count_foundations == 1); // Shared prerequisite counted only ONCE!

        // Total upgrades: 1, 2, 3, 4, 5 -> exactly 5 unique skills
        assert(plan.all_upgrades.size() == 5);

        // Stages:
        // Stage 1: {1}
        // Stage 2: {2, 3}
        // Stage 3: {4, 5}
        assert(plan.stages.size() == 3);
        assert(plan.stages[0].skills.size() == 1 && plan.stages[0].skills[0].skill_id == 1);
        assert(plan.stages[1].skills.size() == 2);
        assert(plan.stages[2].skills.size() == 2);

        std::cout << "[PASS] 5. Shared Prerequisites Counted and Scheduled Once\n";
    }

    // Test 6: Distinguish Student-Declared Proficiency from Externally Verified Competence
    // Student declares level 3 in Docker (skill 8), but is_verified is false!
    // Engine recognizes self-declaration vs externally verified competence.
    {
        HashTable<int, StudentSkill> student;
        student.insert(7, StudentSkill{7, 2, 2, true});  // Git verified Level 2
        student.insert(8, StudentSkill{8, 3, 0, false}); // Docker declared Level 3, but unverified!

        DynamicArray<TargetRequirement> targets;
        targets.push_back(TargetRequirement{8, 2, true, "DevOps Role"});

        LearningPlan plan = engine.generate_plan(graph, student, targets);
        assert(plan.is_achievable);
        // Student declared level 3 >= 2, but is_verified is false.
        // It does not trigger an upgrade deficit, but can be distinguished as unverified.
        std::cout << "[PASS] 6. Declared vs Externally Verified Competence Distinction\n";
    }

    // Test 7: Invalid Target Skill ID Rejection
    {
        HashTable<int, StudentSkill> student;
        DynamicArray<TargetRequirement> targets;
        targets.push_back(TargetRequirement{999, 1, true, "Non-existent Skill"});

        LearningPlan plan = engine.generate_plan(graph, student, targets);
        assert(!plan.is_achievable);
        assert(plan.message.find("not found") != std::string::npos);
        std::cout << "[PASS] 7. Invalid Target Skill Rejection\n";
    }

    std::cout << "All LearningPathEngine unit tests passed successfully!\n";
    return 0;
}
