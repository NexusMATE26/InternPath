#pragma once

#include "internpath/ds/circular_queue.hpp"
#include "internpath/ds/dynamic_array.hpp"
#include "internpath/ds/hash_table.hpp"
#include "internpath/ds/stack.hpp"

#include <cstddef>
#include <string>
#include <utility>

namespace internpath::graph {

/**
 * SkillNode: Represents a node in the SkillGraph.
 */
struct SkillNode {
    int id{0};
    std::string name;
    std::string category{"General"};
    int max_level{5};
    std::string description;

    bool operator==(const SkillNode& other) const noexcept {
        return id == other.id;
    }
    bool operator!=(const SkillNode& other) const noexcept {
        return id != other.id;
    }
};

/**
 * CycleResult: Represents the outcome of 3-color cycle detection.
 * If has_cycle is true, cycle_path contains the exact cycle sequence [u0, u1, ..., un, u0].
 */
struct CycleResult {
    bool has_cycle{false};
    ds::DynamicArray<int> cycle_path;
};

/**
 * TopoSortResult: Outcome of Kahn's topological sort.
 */
struct TopoSortResult {
    bool is_dag{true};
    ds::DynamicArray<int> order;
};

/**
 * SkillGraph: Directed Graph representing skill prerequisites and learning dependencies.
 *
 * Directed edge A -> B means:
 *   - A is a prerequisite of B.
 *   - Completing A is required before starting B.
 *   - In forward adjacency: A unlocks B.
 *   - In reverse adjacency: B requires A.
 *
 * Uses InternPath custom data structures:
 *   - ds::HashTable for node metadata and adjacency index lookup
 *   - ds::DynamicArray for edge lists and traversal paths
 *   - ds::Stack for Depth-First Search
 *   - ds::CircularQueue for Breadth-First Search and Kahn's topological sort
 */
class SkillGraph {
public:
    SkillGraph() = default;

    /**
     * Add a skill node to the graph.
     * Returns true on success, false if ID <= 0 or skill already exists.
     */
    bool add_skill(int skill_id,
                   const std::string& name,
                   const std::string& category = "General",
                   int max_level = 5,
                   const std::string& description = "") {
        if (skill_id <= 0 || contains_skill(skill_id)) {
            return false;
        }
        SkillNode node{skill_id, name, category, max_level, description};
        nodes_.insert(skill_id, std::move(node));
        forward_adj_.insert(skill_id, ds::DynamicArray<int>());
        reverse_adj_.insert(skill_id, ds::DynamicArray<int>());
        return true;
    }

    bool add_skill(const SkillNode& node) {
        return add_skill(node.id, node.name, node.category, node.max_level, node.description);
    }

    /**
     * Check if a skill exists in the graph.
     */
    bool contains_skill(int skill_id) const noexcept {
        return nodes_.contains(skill_id);
    }

    /**
     * Get pointer to skill node metadata, or nullptr if not found.
     */
    const SkillNode* get_skill(int skill_id) const {
        return nodes_.find(skill_id);
    }

    std::size_t skill_count() const noexcept {
        return nodes_.size();
    }

    std::size_t edge_count() const noexcept {
        std::size_t count = 0;
        for (const auto& entry : forward_adj_) {
            count += entry.value.size();
        }
        return count;
    }

    /**
     * Returns all registered skill IDs.
     */
    ds::DynamicArray<int> all_skill_ids() const {
        ds::DynamicArray<int> ids;
        ids.reserve(nodes_.size());
        for (const auto& entry : nodes_) {
            ids.push_back(entry.key);
        }
        return ids;
    }

    /**
     * Add directed prerequisite edge: prereq_id -> skill_id
     * (prereq_id must be completed before skill_id).
     *
     * Rejects:
     *   - Self-loops (prereq_id == skill_id)
     *   - Invalid skill IDs (either not in graph)
     *   - Duplicate edges (prereq_id -> skill_id already present)
     *   - Edges that would create a directed cycle (if path already exists from skill_id to prereq_id)
     *
     * Provides strong exception safety.
     */
    bool add_prerequisite(int prereq_id, int skill_id) {
        // 1. Reject invalid skill IDs
        if (!contains_skill(prereq_id) || !contains_skill(skill_id)) {
            return false;
        }

        // 2. Reject self-loops
        if (prereq_id == skill_id) {
            return false;
        }

        auto* fwd_list = forward_adj_.find(prereq_id);
        auto* rev_list = reverse_adj_.find(skill_id);
        if (!fwd_list || !rev_list) {
            return false;
        }

        // 3. Reject duplicate edges
        for (std::size_t i = 0; i < fwd_list->size(); ++i) {
            if ((*fwd_list)[i] == skill_id) {
                return false;
            }
        }

        // 4. Reject cycle creation: if skill_id can already reach prereq_id,
        // adding prereq_id -> skill_id would create a directed cycle.
        if (has_path(skill_id, prereq_id)) {
            return false;
        }

        // 5. Transactional insert with rollback on exception (strong exception safety)
        fwd_list->push_back(skill_id);
        try {
            rev_list->push_back(prereq_id);
        } catch (...) {
            fwd_list->pop_back();
            throw;
        }
        return true;
    }

    /**
     * Remove directed prerequisite edge: prereq_id -> skill_id.
     * Returns true if edge was found and removed, false otherwise.
     */
    bool remove_prerequisite(int prereq_id, int skill_id) noexcept {
        auto* fwd_list = forward_adj_.find(prereq_id);
        auto* rev_list = reverse_adj_.find(skill_id);
        if (!fwd_list || !rev_list) {
            return false;
        }

        bool found_fwd = false;
        for (std::size_t i = 0; i < fwd_list->size(); ++i) {
            if ((*fwd_list)[i] == skill_id) {
                for (std::size_t j = i + 1; j < fwd_list->size(); ++j) {
                    (*fwd_list)[j - 1] = (*fwd_list)[j];
                }
                fwd_list->pop_back();
                found_fwd = true;
                break;
            }
        }

        bool found_rev = false;
        for (std::size_t i = 0; i < rev_list->size(); ++i) {
            if ((*rev_list)[i] == prereq_id) {
                for (std::size_t j = i + 1; j < rev_list->size(); ++j) {
                    (*rev_list)[j - 1] = (*rev_list)[j];
                }
                rev_list->pop_back();
                found_rev = true;
                break;
            }
        }

        return found_fwd && found_rev;
    }

    /**
     * Unchecked prerequisite addition for testing cycle detection and validation algorithms.
     */
    bool force_add_prerequisite(int prereq_id, int skill_id) {
        if (!contains_skill(prereq_id) || !contains_skill(skill_id)) return false;
        auto* fwd_list = forward_adj_.find(prereq_id);
        auto* rev_list = reverse_adj_.find(skill_id);
        if (!fwd_list || !rev_list) return false;
        fwd_list->push_back(skill_id);
        rev_list->push_back(prereq_id);
        return true;
    }

    /**
     * Get direct prerequisites for skill_id (incoming edges).
     */
    ds::DynamicArray<int> get_prerequisites(int skill_id) const {
        const auto* list = reverse_adj_.find(skill_id);
        if (!list) return ds::DynamicArray<int>();
        return *list;
    }

    /**
     * Get skills directly unlocked by skill_id (outgoing edges).
     */
    ds::DynamicArray<int> get_unlocked_skills(int skill_id) const {
        const auto* list = forward_adj_.find(skill_id);
        if (!list) return ds::DynamicArray<int>();
        return *list;
    }

    /**
     * Check if a directed reachability path exists from start_id to target_id.
     * Complexity: O(V + E) using custom CircularQueue.
     */
    bool has_path(int start_id, int target_id) const {
        if (!contains_skill(start_id) || !contains_skill(target_id)) {
            return false;
        }
        if (start_id == target_id) return true;

        ds::HashTable<int, bool> visited;
        ds::CircularQueue<int> queue;

        visited.insert(start_id, true);
        queue.enqueue(start_id);

        while (!queue.empty()) {
            int current = queue.front();
            queue.dequeue();

            const auto* next_nodes = forward_adj_.find(current);
            if (!next_nodes) continue;

            for (std::size_t i = 0; i < next_nodes->size(); ++i) {
                int neighbor = (*next_nodes)[i];
                if (neighbor == target_id) {
                    return true;
                }
                if (!visited.contains(neighbor)) {
                    visited.insert(neighbor, true);
                    queue.enqueue(neighbor);
                }
            }
        }
        return false;
    }

    /**
     * Depth-First Search (DFS) starting from start_skill_id using custom ds::Stack.
     * Traverses all reachable skills. Complexity: O(V + E).
     */
    ds::DynamicArray<int> dfs(int start_skill_id) const {
        ds::DynamicArray<int> traversal;
        if (!contains_skill(start_skill_id)) return traversal;

        ds::HashTable<int, bool> visited;
        ds::Stack<int> stack;

        stack.push(start_skill_id);

        while (!stack.empty()) {
            int current = stack.top();
            stack.pop();

            if (visited.contains(current)) continue;
            visited.insert(current, true);
            traversal.push_back(current);

            const auto* neighbors = forward_adj_.find(current);
            if (neighbors) {
                // Push neighbors in reverse order so forward order is popped first
                for (std::size_t i = neighbors->size(); i > 0; --i) {
                    int next = (*neighbors)[i - 1];
                    if (!visited.contains(next)) {
                        stack.push(next);
                    }
                }
            }
        }
        return traversal;
    }

    /**
     * Breadth-First Search (BFS) starting from start_skill_id using custom ds::CircularQueue.
     *
     * IMPORTANT ALGORITHMIC NOTE:
     * BFS computes single-source shortest path in terms of edge hop counts in unweighted graphs.
     * BFS is NOT an optimal minimum-effort learning-path algorithm. A valid prerequisite learning
     * plan requires dependency closure, topological ordering, and separate multi-factor effort
     * calculations. BFS is used here specifically for level-order exploration and hop-distance analysis.
     *
     * Complexity: O(V + E).
     */
    ds::DynamicArray<int> bfs(int start_skill_id) const {
        ds::DynamicArray<int> traversal;
        if (!contains_skill(start_skill_id)) return traversal;

        ds::HashTable<int, bool> visited;
        ds::CircularQueue<int> queue;

        visited.insert(start_skill_id, true);
        queue.enqueue(start_skill_id);

        while (!queue.empty()) {
            int current = queue.front();
            queue.dequeue();
            traversal.push_back(current);

            const auto* neighbors = forward_adj_.find(current);
            if (neighbors) {
                for (std::size_t i = 0; i < neighbors->size(); ++i) {
                    int next = (*neighbors)[i];
                    if (!visited.contains(next)) {
                        visited.insert(next, true);
                        queue.enqueue(next);
                    }
                }
            }
        }
        return traversal;
    }

    /**
     * Three-Color Cycle Detection with Exact Cycle Path Reconstruction.
     *
     * Colors:
     *   0: WHITE (unvisited)
     *   1: GRAY  (visiting, active on current DFS recursion stack)
     *   2: BLACK (visited and all descendants completed)
     *
     * When a GRAY neighbor is encountered, a back-edge is detected. The exact cycle
     * sequence [v, ..., u, v] is reconstructed via parent pointers.
     *
     * Complexity: O(V + E).
     */
    CycleResult detect_cycle() const {
        ds::HashTable<int, int> color;      // skill_id -> color (0, 1, 2)
        ds::HashTable<int, int> parent;     // skill_id -> parent_id

        for (const auto& entry : nodes_) {
            color.insert(entry.key, 0); // WHITE
        }

        for (const auto& entry : nodes_) {
            int start_id = entry.key;
            const int* c = color.find(start_id);
            if (c && *c == 0) {
                CycleResult res = dfs_cycle_helper(start_id, color, parent);
                if (res.has_cycle) {
                    return res;
                }
            }
        }

        return CycleResult{false, ds::DynamicArray<int>()};
    }

    /**
     * Kahn's Topological Sorting Algorithm.
     * Returns ordering of all skills such that every prerequisite appears before its dependents.
     *
     * Complexity: O(V + E).
     */
    TopoSortResult topological_sort() const {
        ds::HashTable<int, int> in_degrees;
        ds::CircularQueue<int> zero_in_degree;
        ds::DynamicArray<int> order;

        for (const auto& entry : nodes_) {
            int id = entry.key;
            const auto* rev = reverse_adj_.find(id);
            int deg = rev ? static_cast<int>(rev->size()) : 0;
            in_degrees.insert(id, deg);
            if (deg == 0) {
                zero_in_degree.enqueue(id);
            }
        }

        while (!zero_in_degree.empty()) {
            int u = zero_in_degree.front();
            zero_in_degree.dequeue();
            order.push_back(u);

            const auto* fwd = forward_adj_.find(u);
            if (fwd) {
                for (std::size_t i = 0; i < fwd->size(); ++i) {
                    int v = (*fwd)[i];
                    int* deg = in_degrees.find(v);
                    if (deg) {
                        --(*deg);
                        if (*deg == 0) {
                            zero_in_degree.enqueue(v);
                        }
                    }
                }
            }
        }

        if (order.size() != nodes_.size()) {
            // Cycle detected: not a valid DAG
            return TopoSortResult{false, ds::DynamicArray<int>()};
        }

        return TopoSortResult{true, std::move(order)};
    }

    /**
     * Layered Topological Sorting for Learning Stages.
     * Groups skills into discrete chronological stages.
     * Stage 0 contains skills with no prerequisites.
     * Stage k contains skills whose prerequisites are fully completed in earlier stages.
     *
     * Complexity: O(V + E).
     */
    ds::DynamicArray<ds::DynamicArray<int>> find_learning_stages() const {
        ds::DynamicArray<ds::DynamicArray<int>> stages;

        ds::HashTable<int, int> in_degrees;
        ds::CircularQueue<int> current_queue;

        for (const auto& entry : nodes_) {
            int id = entry.key;
            const auto* rev = reverse_adj_.find(id);
            int deg = rev ? static_cast<int>(rev->size()) : 0;
            in_degrees.insert(id, deg);
            if (deg == 0) {
                current_queue.enqueue(id);
            }
        }

        std::size_t total_scheduled = 0;

        while (!current_queue.empty()) {
            ds::DynamicArray<int> stage;
            ds::CircularQueue<int> next_queue;

            while (!current_queue.empty()) {
                int u = current_queue.front();
                current_queue.dequeue();
                stage.push_back(u);
                ++total_scheduled;

                const auto* fwd = forward_adj_.find(u);
                if (fwd) {
                    for (std::size_t i = 0; i < fwd->size(); ++i) {
                        int v = (*fwd)[i];
                        int* deg = in_degrees.find(v);
                        if (deg) {
                            --(*deg);
                            if (*deg == 0) {
                                next_queue.enqueue(v);
                            }
                        }
                    }
                }
            }

            stages.push_back(std::move(stage));
            current_queue.swap(next_queue);
        }

        if (total_scheduled != nodes_.size()) {
            // Graph contains cycles, stages cannot cover entire graph
            return ds::DynamicArray<ds::DynamicArray<int>>();
        }

        return stages;
    }

    /**
     * Reverse Prerequisite Closure: Computes all ancestral prerequisites
     * required for a target skill.
     *
     * Shared prerequisites across multiple paths are visited and included exactly ONCE.
     * Complexity: O(V + E).
     */
    ds::DynamicArray<int> get_prerequisite_closure(int target_skill_id) const {
        ds::DynamicArray<int> targets;
        targets.push_back(target_skill_id);
        return get_prerequisite_closure(targets);
    }

    ds::DynamicArray<int> get_prerequisite_closure(const ds::DynamicArray<int>& target_skill_ids) const {
        ds::DynamicArray<int> closure;
        ds::HashTable<int, bool> visited;
        ds::CircularQueue<int> queue;

        // Target skills themselves mark the boundaries
        for (std::size_t i = 0; i < target_skill_ids.size(); ++i) {
            int tid = target_skill_ids[i];
            const auto* direct_prereqs = reverse_adj_.find(tid);
            if (direct_prereqs) {
                for (std::size_t j = 0; j < direct_prereqs->size(); ++j) {
                    int p = (*direct_prereqs)[j];
                    if (!visited.contains(p)) {
                        visited.insert(p, true);
                        queue.enqueue(p);
                    }
                }
            }
        }

        while (!queue.empty()) {
            int current = queue.front();
            queue.dequeue();
            closure.push_back(current);

            const auto* ancestors = reverse_adj_.find(current);
            if (ancestors) {
                for (std::size_t j = 0; j < ancestors->size(); ++j) {
                    int anc = (*ancestors)[j];
                    if (!visited.contains(anc)) {
                        visited.insert(anc, true);
                        queue.enqueue(anc);
                    }
                }
            }
        }

        return closure;
    }

    /**
     * Validate graph invariants:
     *   1. Forward and reverse edges match reciprocally.
     *   2. No self-loops.
     *   3. No duplicate edges.
     *   4. All edge endpoints exist in nodes_.
     *   5. No directed cycles.
     */
    bool validate_graph() const {
        for (const auto& entry : forward_adj_) {
            int u = entry.key;
            if (!contains_skill(u)) return false;

            const auto& neighbors = entry.value;
            for (std::size_t i = 0; i < neighbors.size(); ++i) {
                int v = neighbors[i];
                if (u == v) return false; // Self-loop
                if (!contains_skill(v)) return false; // Invalid neighbor ID

                // Check for duplicates
                for (std::size_t j = i + 1; j < neighbors.size(); ++j) {
                    if (neighbors[j] == v) return false;
                }

                // Check reverse adjacency reciprocity
                const auto* rev = reverse_adj_.find(v);
                if (!rev) return false;
                bool found = false;
                for (std::size_t k = 0; k < rev->size(); ++k) {
                    if ((*rev)[k] == u) {
                        found = true;
                        break;
                    }
                }
                if (!found) return false;
            }
        }

        // Check for cycles
        if (detect_cycle().has_cycle) {
            return false;
        }

        return true;
    }

private:
    CycleResult dfs_cycle_helper(int u,
                                ds::HashTable<int, int>& color,
                                ds::HashTable<int, int>& parent) const {
        color.insert_or_assign(u, 1); // GRAY (active)

        const auto* fwd = forward_adj_.find(u);
        if (fwd) {
            for (std::size_t i = 0; i < fwd->size(); ++i) {
                int v = (*fwd)[i];
                const int* c = color.find(v);
                int neighbor_color = c ? *c : 0;

                if (neighbor_color == 1) {
                    // Back-edge detected! Cycle found: v -> ... -> u -> v
                    ds::DynamicArray<int> cycle_path;
                    ds::DynamicArray<int> rev_path;
                    int curr = u;
                    while (curr != v) {
                        rev_path.push_back(curr);
                        const int* p = parent.find(curr);
                        if (!p) break;
                        curr = *p;
                    }
                    rev_path.push_back(v);

                    for (std::size_t k = rev_path.size(); k > 0; --k) {
                        cycle_path.push_back(rev_path[k - 1]);
                    }
                    cycle_path.push_back(v); // close the loop
                    return CycleResult{true, std::move(cycle_path)};
                }

                if (neighbor_color == 0) {
                    parent.insert_or_assign(v, u);
                    CycleResult res = dfs_cycle_helper(v, color, parent);
                    if (res.has_cycle) {
                        return res;
                    }
                }
            }
        }

        color.insert_or_assign(u, 2); // BLACK (completed)
        return CycleResult{false, ds::DynamicArray<int>()};
    }

    ds::HashTable<int, SkillNode> nodes_;
    ds::HashTable<int, ds::DynamicArray<int>> forward_adj_; // prereq -> unlocked
    ds::HashTable<int, ds::DynamicArray<int>> reverse_adj_; // skill -> prereqs
};

} // namespace internpath::graph
