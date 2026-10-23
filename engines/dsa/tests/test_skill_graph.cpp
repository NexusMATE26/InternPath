#include "internpath/graph/skill_graph.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <string>
#include <vector>

using internpath::graph::SkillGraph;
using internpath::graph::SkillNode;

int main() {
    std::cout << "--- Starting SkillGraph Tests ---\n";

    // 1. Empty Graph
    {
        SkillGraph graph;
        assert(graph.skill_count() == 0);
        assert(graph.edge_count() == 0);
        assert(!graph.contains_skill(1));
        assert(graph.get_skill(1) == nullptr);
        assert(graph.get_prerequisites(1).empty());
        assert(graph.get_unlocked_skills(1).empty());
        assert(graph.dfs(1).empty());
        assert(graph.bfs(1).empty());

        auto topo = graph.topological_sort();
        assert(topo.is_dag && topo.order.empty());

        auto stages = graph.find_learning_stages();
        assert(stages.empty());

        auto cycle = graph.detect_cycle();
        assert(!cycle.has_cycle && cycle.cycle_path.empty());

        assert(graph.validate_graph());
        std::cout << "[PASS] 1. Empty Graph\n";
    }

    // 2. Single Skill & Self-Loop Rejection
    {
        SkillGraph graph;
        assert(graph.add_skill(1, "Python", "Languages", 5, "Programming language"));
        assert(graph.skill_count() == 1);
        assert(graph.contains_skill(1));
        assert(graph.get_skill(1)->name == "Python");

        // Reject self-loop
        assert(!graph.add_prerequisite(1, 1));
        assert(graph.edge_count() == 0);

        // DFS and BFS
        auto dfs_res = graph.dfs(1);
        assert(dfs_res.size() == 1 && dfs_res[0] == 1);
        auto bfs_res = graph.bfs(1);
        assert(bfs_res.size() == 1 && bfs_res[0] == 1);

        // Topo sort and stages
        auto topo = graph.topological_sort();
        assert(topo.is_dag && topo.order.size() == 1 && topo.order[0] == 1);

        auto stages = graph.find_learning_stages();
        assert(stages.size() == 1 && stages[0].size() == 1 && stages[0][0] == 1);

        assert(graph.validate_graph());
        std::cout << "[PASS] 2. Single Skill & Self-Loop Rejection\n";
    }

    // 3. Invalid IDs and Duplicate Skill Rejection
    {
        SkillGraph graph;
        assert(graph.add_skill(1, "Python"));
        assert(!graph.add_skill(1, "Python Duplicate")); // duplicate skill ID rejected
        assert(!graph.add_skill(0, "Invalid ID"));       // ID <= 0 rejected
        assert(!graph.add_skill(-5, "Negative ID"));     // Negative ID rejected

        // Prerequisites with non-existent skills
        assert(!graph.add_prerequisite(1, 999));
        assert(!graph.add_prerequisite(999, 1));
        assert(!graph.add_prerequisite(888, 999));

        assert(!graph.remove_prerequisite(1, 999));
        assert(!graph.remove_prerequisite(999, 1));

        assert(graph.edge_count() == 0);
        std::cout << "[PASS] 3. Invalid IDs and Duplicate Skill Rejection\n";
    }

    // 4. Duplicate Edge Rejection
    {
        SkillGraph graph;
        assert(graph.add_skill(1, "Git"));
        assert(graph.add_skill(2, "Open Source"));

        assert(graph.add_prerequisite(1, 2));
        assert(graph.edge_count() == 1);

        // Duplicate edge rejection:
        assert(!graph.add_prerequisite(1, 2));
        assert(graph.edge_count() == 1);

        auto prereqs = graph.get_prerequisites(2);
        assert(prereqs.size() == 1 && prereqs[0] == 1);

        auto unlocked = graph.get_unlocked_skills(1);
        assert(unlocked.size() == 1 && unlocked[0] == 2);

        // Removal
        assert(graph.remove_prerequisite(1, 2));
        assert(graph.edge_count() == 0);
        assert(graph.get_prerequisites(2).empty());
        assert(graph.get_unlocked_skills(1).empty());

        std::cout << "[PASS] 4. Duplicate Edge Rejection & Removal\n";
    }

    // 5. Direct Cycle Rejection (A -> B, attempt B -> A)
    {
        SkillGraph graph;
        assert(graph.add_skill(1, "C++"));
        assert(graph.add_skill(2, "Data Structures"));

        assert(graph.add_prerequisite(1, 2)); // C++ -> Data Structures
        assert(graph.has_path(1, 2));
        assert(!graph.has_path(2, 1));

        // Attempting to add reverse edge (Data Structures -> C++) would create cycle 1 -> 2 -> 1
        assert(!graph.add_prerequisite(2, 1));
        assert(graph.edge_count() == 1);

        auto cycle = graph.detect_cycle();
        assert(!cycle.has_cycle);
        assert(graph.validate_graph());

        std::cout << "[PASS] 5. Direct Cycle Rejection\n";
    }

    // 6. Multi-Node Cycle Rejection & Detection with Exact Path
    {
        SkillGraph graph;
        assert(graph.add_skill(1, "Foundations"));
        assert(graph.add_skill(2, "Intermediate"));
        assert(graph.add_skill(3, "Advanced"));
        assert(graph.add_skill(4, "Expert"));

        assert(graph.add_prerequisite(1, 2));
        assert(graph.add_prerequisite(2, 3));
        assert(graph.add_prerequisite(3, 4));

        // Path exists 1 -> 4
        assert(graph.has_path(1, 4));

        // Reject multi-node back-edge 4 -> 1
        assert(!graph.add_prerequisite(4, 1));
        // Reject multi-node back-edge 4 -> 2
        assert(!graph.add_prerequisite(4, 2));

        assert(graph.edge_count() == 3);
        assert(graph.validate_graph());

        // Test cycle detection algorithm when a back-edge is forced:
        assert(graph.force_add_prerequisite(4, 2)); // creates cycle 2 -> 3 -> 4 -> 2
        assert(!graph.validate_graph());

        auto cycle = graph.detect_cycle();
        assert(cycle.has_cycle);
        // Verify reconstructed cycle path: starts and ends at the cycle vertex
        assert(cycle.cycle_path.size() >= 3);
        assert(cycle.cycle_path[0] == cycle.cycle_path[cycle.cycle_path.size() - 1]);
        std::cout << "Reconstructed multi-node cycle path: ";
        for (std::size_t i = 0; i < cycle.cycle_path.size(); ++i) {
            std::cout << cycle.cycle_path[i] << (i + 1 < cycle.cycle_path.size() ? " -> " : "\n");
        }

        // Clean up forced cycle
        assert(graph.remove_prerequisite(4, 2));
        assert(graph.validate_graph());

        std::cout << "[PASS] 6. Multi-Node Cycle Rejection & Path Detection\n";
    }

    // 7. Disconnected Graph
    {
        SkillGraph graph;
        // Component 1: 10 -> 11
        assert(graph.add_skill(10, "HTML"));
        assert(graph.add_skill(11, "CSS"));
        assert(graph.add_prerequisite(10, 11));

        // Component 2: 20 -> 21 -> 22
        assert(graph.add_skill(20, "C"));
        assert(graph.add_skill(21, "OS"));
        assert(graph.add_skill(22, "Distributed Systems"));
        assert(graph.add_prerequisite(20, 21));
        assert(graph.add_prerequisite(21, 22));

        // Isolated Node: 30
        assert(graph.add_skill(30, "Soft Skills"));

        assert(graph.skill_count() == 6);
        assert(graph.edge_count() == 3);
        assert(graph.validate_graph());

        auto topo = graph.topological_sort();
        assert(topo.is_dag && topo.order.size() == 6);

        // Verify topological order properties:
        // Position of 10 < 11
        // Position of 20 < 21 < 22
        int pos_10 = -1, pos_11 = -1, pos_20 = -1, pos_21 = -1, pos_22 = -1;
        for (std::size_t i = 0; i < topo.order.size(); ++i) {
            int id = topo.order[i];
            if (id == 10) pos_10 = static_cast<int>(i);
            if (id == 11) pos_11 = static_cast<int>(i);
            if (id == 20) pos_20 = static_cast<int>(i);
            if (id == 21) pos_21 = static_cast<int>(i);
            if (id == 22) pos_22 = static_cast<int>(i);
        }
        assert(pos_10 < pos_11);
        assert(pos_20 < pos_21 && pos_21 < pos_22);

        // Learning stages
        auto stages = graph.find_learning_stages();
        assert(stages.size() == 3);
        // Stage 1 must contain 10, 20, 30 (zero in-degree)
        assert(stages[0].size() == 3);
        // Stage 2 must contain 11, 21
        assert(stages[1].size() == 2);
        // Stage 3 must contain 22
        assert(stages[2].size() == 1 && stages[2][0] == 22);

        std::cout << "[PASS] 7. Disconnected Graph & Parallel Stages\n";
    }

    // 8. Diamond Dependencies & Shared Prerequisite Closure
    {
        // Graph structure:
        //        1 (Python)
        //       / \
        //      v   v
        // 2 (Flask) 3 (FastAPI)
        //      \   /
        //       v v
        // 4 (Microservices)
        SkillGraph graph;
        assert(graph.add_skill(1, "Python"));
        assert(graph.add_skill(2, "Flask"));
        assert(graph.add_skill(3, "FastAPI"));
        assert(graph.add_skill(4, "Microservices"));

        assert(graph.add_prerequisite(1, 2));
        assert(graph.add_prerequisite(1, 3));
        assert(graph.add_prerequisite(2, 4));
        assert(graph.add_prerequisite(3, 4));

        assert(graph.validate_graph());

        // Reverse Prerequisite Closure for skill 4
        auto closure = graph.get_prerequisite_closure(4);
        // Must contain 1, 2, 3. Crucially, 1 must be present ONLY ONCE!
        assert(closure.size() == 3);
        int count_1 = 0, count_2 = 0, count_3 = 0;
        for (std::size_t i = 0; i < closure.size(); ++i) {
            if (closure[i] == 1) ++count_1;
            if (closure[i] == 2) ++count_2;
            if (closure[i] == 3) ++count_3;
        }
        assert(count_1 == 1 && count_2 == 1 && count_3 == 1);

        // Stages for diamond
        auto stages = graph.find_learning_stages();
        assert(stages.size() == 3);
        assert(stages[0].size() == 1 && stages[0][0] == 1); // Stage 1: Python
        assert(stages[1].size() == 2);                      // Stage 2: Flask and FastAPI in parallel
        assert(stages[2].size() == 1 && stages[2][0] == 4); // Stage 3: Microservices

        // BFS vs DFS
        auto bfs_nodes = graph.bfs(1);
        assert(bfs_nodes.size() == 4);
        assert(bfs_nodes[0] == 1);

        auto dfs_nodes = graph.dfs(1);
        assert(dfs_nodes.size() == 4);
        assert(dfs_nodes[0] == 1);

        std::cout << "[PASS] 8. Diamond Dependencies & Single Shared Prerequisite\n";
    }

    // 9. Determinism of Traversals & Topological Ordering
    {
        SkillGraph graph;
        for (int i = 1; i <= 8; ++i) {
            graph.add_skill(i, "Skill " + std::to_string(i));
        }
        graph.add_prerequisite(1, 3);
        graph.add_prerequisite(1, 4);
        graph.add_prerequisite(2, 4);
        graph.add_prerequisite(2, 5);
        graph.add_prerequisite(3, 6);
        graph.add_prerequisite(4, 7);
        graph.add_prerequisite(5, 8);

        auto topo1 = graph.topological_sort();
        auto topo2 = graph.topological_sort();
        assert(topo1.order.size() == topo2.order.size());
        for (std::size_t i = 0; i < topo1.order.size(); ++i) {
            assert(topo1.order[i] == topo2.order[i]);
        }

        auto dfs1 = graph.dfs(1);
        auto dfs2 = graph.dfs(1);
        assert(dfs1.size() == dfs2.size());
        for (std::size_t i = 0; i < dfs1.size(); ++i) {
            assert(dfs1[i] == dfs2[i]);
        }

        std::cout << "[PASS] 9. Deterministic Traversals\n";
    }

    // 10. Large Synthetic DAG (150 vertices, >250 edges)
    {
        SkillGraph graph;
        const int kNodes = 150;
        for (int i = 1; i <= kNodes; ++i) {
            assert(graph.add_skill(i, "Skill_" + std::to_string(i)));
        }

        int added_edges = 0;
        for (int i = 3; i <= kNodes; ++i) {
            // Edges from earlier to later nodes guarantee acyclicity
            assert(graph.add_prerequisite(i - 1, i));
            assert(graph.add_prerequisite(i - 2, i));
            added_edges += 2;
            if (i % 5 == 0 && i >= 6) {
                assert(graph.add_prerequisite(i - 5, i));
                ++added_edges;
            }
        }

        assert(graph.skill_count() == kNodes);
        assert(graph.edge_count() == static_cast<std::size_t>(added_edges));
        assert(graph.validate_graph());

        auto topo = graph.topological_sort();
        assert(topo.is_dag && topo.order.size() == kNodes);

        // Verify topological sorting invariant: for every edge u -> v, pos(u) < pos(v)
        std::vector<int> pos(kNodes + 1, -1);
        for (std::size_t i = 0; i < topo.order.size(); ++i) {
            pos[topo.order[i]] = static_cast<int>(i);
        }

        for (int i = 1; i <= kNodes; ++i) {
            auto unl = graph.get_unlocked_skills(i);
            for (std::size_t j = 0; j < unl.size(); ++j) {
                int neighbor = unl[j];
                assert(pos[i] < pos[neighbor]);
            }
        }

        auto cycle = graph.detect_cycle();
        assert(!cycle.has_cycle);

        std::cout << "[PASS] 10. Large Synthetic DAG (150 nodes, " << added_edges << " edges)\n";
    }

    std::cout << "All SkillGraph unit tests passed successfully!\n";
    return 0;
}
