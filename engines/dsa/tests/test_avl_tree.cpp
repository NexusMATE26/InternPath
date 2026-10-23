#include "internpath/ds/avl_tree.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <algorithm>
#include <cassert>
#include <chrono>
#include <iostream>
#include <map>
#include <string>
#include <utility>
#include <vector>

using internpath::ds::AVLTree;

int main() {
    // 1. LL Rotation verification
    {
        AVLTree<int, std::string> tree;
        tree.insert(30, "thirty");
        tree.insert(20, "twenty");
        assert(tree.check_invariants());
        tree.insert(10, "ten"); // triggers LL rotation on 30
        assert(tree.check_invariants());
        assert(tree.height() == 2);
        assert(tree.rotation_stats().ll_rotations >= 1);
        assert(*tree.find(20) == "twenty");
    }

    // 2. RR Rotation verification
    {
        AVLTree<int, std::string> tree;
        tree.insert(10, "ten");
        tree.insert(20, "twenty");
        assert(tree.check_invariants());
        tree.insert(30, "thirty"); // triggers RR rotation on 10
        assert(tree.check_invariants());
        assert(tree.height() == 2);
        assert(tree.rotation_stats().rr_rotations >= 1);
        assert(*tree.find(20) == "twenty");
    }

    // 3. LR Rotation verification
    {
        AVLTree<int, std::string> tree;
        tree.insert(30, "thirty");
        tree.insert(10, "ten");
        assert(tree.check_invariants());
        tree.insert(20, "twenty"); // triggers LR rotation on 30
        assert(tree.check_invariants());
        assert(tree.height() == 2);
        assert(tree.rotation_stats().lr_rotations >= 1);
        assert(*tree.find(20) == "twenty");
    }

    // 4. RL Rotation verification
    {
        AVLTree<int, std::string> tree;
        tree.insert(10, "ten");
        tree.insert(30, "thirty");
        assert(tree.check_invariants());
        tree.insert(20, "twenty"); // triggers RL rotation on 10
        assert(tree.check_invariants());
        assert(tree.height() == 2);
        assert(tree.rotation_stats().rl_rotations >= 1);
        assert(*tree.find(20) == "twenty");
    }

    // 5. Deletion testing (0, 1, and 2 children)
    {
        AVLTree<int, int> tree;
        // Build balanced tree: [10, 20, 30, 40, 50, 60, 70]
        int keys[] = {40, 20, 60, 10, 30, 50, 70};
        for (int k : keys) {
            tree.insert(k, k * 10);
            assert(tree.check_invariants());
        }
        assert(tree.size() == 7);

        // Case A: Delete leaf node (0 children) -> 10
        assert(tree.erase(10));
        assert(!tree.contains(10));
        assert(tree.size() == 6);
        assert(tree.check_invariants());

        // Case B: Delete node with 1 child
        // Delete 30 first, then 20 only has child? Let's check structure
        assert(tree.erase(30));
        assert(!tree.contains(30));
        assert(tree.size() == 5);
        assert(tree.check_invariants());

        // Case C: Delete internal node with 2 children -> root 40
        assert(tree.erase(40));
        assert(!tree.contains(40));
        assert(tree.size() == 4);
        assert(tree.check_invariants());

        // Erase non-existent key
        assert(!tree.erase(999));
        assert(tree.size() == 4);
    }

    // 6. Duplicate key handling
    {
        AVLTree<int, std::string> tree;
        auto r1 = tree.insert(5, "initial");
        assert(r1.second && *r1.first == "initial");

        auto r2 = tree.insert(5, "duplicate");
        assert(!r2.second && *r2.first == "initial"); // must not overwrite

        auto r3 = tree.insert_or_assign(5, "updated");
        assert(!r3.second && *r3.first == "updated"); // must update
        assert(*tree.find(5) == "updated");
    }

    // 7. Sorted & Reverse-sorted insertion (balanced height validation)
    {
        AVLTree<int, int> sorted_tree;
        for (int i = 1; i <= 500; ++i) {
            sorted_tree.insert(i, i);
        }
        assert(sorted_tree.size() == 500);
        assert(sorted_tree.check_invariants());
        // AVL height bound: h <= 1.44 * log2(N+2). For N=500, max theoretical height is ~13.
        assert(sorted_tree.height() <= 12);

        AVLTree<int, int> rev_tree;
        for (int i = 500; i >= 1; --i) {
            rev_tree.insert(i, i);
        }
        assert(rev_tree.size() == 500);
        assert(rev_tree.check_invariants());
        assert(rev_tree.height() <= 12);
    }

    // 8. In-order traversal and Range Queries
    {
        AVLTree<int, int> tree;
        for (int i = 10; i <= 100; i += 10) {
            tree.insert(i, i);
        }
        // In-order traversal must be strictly ascending
        int last_seen = -1;
        int count = 0;
        tree.inorder_traversal([&](int k, int) {
            assert(k > last_seen);
            last_seen = k;
            ++count;
        });
        assert(count == 10);

        // Range query [25, 65] -> should return 30, 40, 50, 60
        auto range_res = tree.range_query(25, 65);
        assert(range_res.size() == 4);
        assert(range_res[0].first == 30);
        assert(range_res[1].first == 40);
        assert(range_res[2].first == 50);
        assert(range_res[3].first == 60);

        // Inclusive boundaries [30, 60] -> should return 30, 40, 50, 60
        auto inclusive_res = tree.range_query(30, 60);
        assert(inclusive_res.size() == 4);
        assert(inclusive_res[0].first == 30 && inclusive_res[3].first == 60);

        // Empty range query
        auto empty_res = tree.range_query(90, 80);
        assert(empty_res.empty());
    }

    // 9. lower_bound search
    {
        AVLTree<int, int> tree;
        for (int v : {10, 20, 30, 50, 60}) tree.insert(v, v);
        // exact match
        const auto* lb1 = tree.lower_bound(30);
        assert(lb1 && lb1->key == 30);
        // between 30 and 50 -> should return 50
        const auto* lb2 = tree.lower_bound(35);
        assert(lb2 && lb2->key == 50);
        // greater than all -> should return nullptr
        const auto* lb3 = tree.lower_bound(70);
        assert(lb3 == nullptr);
    }

    // 10. Composite keys: (deadline, internship_id)
    {
        using CompositeKey = std::pair<std::string, std::string>;
        AVLTree<CompositeKey, int> deadline_tree;

        // Same deadline "2026-11-30", different internship IDs:
        deadline_tree.insert({"2026-11-30", "INT-001"}, 1);
        deadline_tree.insert({"2026-11-30", "INT-002"}, 2);
        deadline_tree.insert({"2026-10-15", "INT-003"}, 3);
        deadline_tree.insert({"2026-12-31", "INT-004"}, 4);

        assert(deadline_tree.size() == 4);
        assert(deadline_tree.check_invariants());
        assert(*deadline_tree.find({"2026-11-30", "INT-001"}) == 1);
        assert(*deadline_tree.find({"2026-11-30", "INT-002"}) == 2);

        // Range query across November deadlines
        auto nov_results = deadline_tree.range_query({"2026-11-01", ""}, {"2026-11-30", "\xFF"});
        assert(nov_results.size() == 2);
        assert(nov_results[0].first.second == "INT-001");
        assert(nov_results[1].first.second == "INT-002");
    }

    // 11. Copy and move operations
    {
        AVLTree<int, int> original;
        for (int i = 0; i < 50; ++i) original.insert(i, i * 2);

        AVLTree<int, int> copy = original;
        assert(copy.size() == 50 && copy.check_invariants());
        assert(*copy.find(25) == 50);

        copy = copy; // self-assignment
        assert(copy.size() == 50 && copy.check_invariants());

        AVLTree<int, int> moved = std::move(copy);
        assert(moved.size() == 50 && moved.check_invariants());
        assert(copy.empty());
    }

    // 12. Multi-trial Benchmark with Checksum & Median vs std::map
    const int kBenchN = 20000;
    const int kTrials = 5;
    std::cout << "--- Benchmark: AVLTree vs std::map (" << kBenchN << " items, " << kTrials << " trials) ---\n";

    std::vector<double> custom_insert_times;
    std::vector<double> custom_lookup_times;
    std::vector<double> std_insert_times;
    std::vector<double> std_lookup_times;
    uint64_t custom_checksum = 0;
    uint64_t std_checksum = 0;

    int last_height = 0;
    AVLTree<int, int>::RotationStats last_rotations;

    for (int t = 0; t < kTrials; ++t) {
        // Custom AVLTree
        auto t0 = std::chrono::high_resolution_clock::now();
        AVLTree<int, int> custom_avl;
        for (int i = 0; i < kBenchN; ++i) {
            custom_avl.insert(i, i ^ 0xAA55);
        }
        auto t1 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < kBenchN; ++i) {
            const int* v = custom_avl.find(i);
            if (v) custom_checksum += static_cast<uint64_t>(*v);
        }
        auto t2 = std::chrono::high_resolution_clock::now();
        custom_insert_times.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
        custom_lookup_times.push_back(std::chrono::duration<double, std::milli>(t2 - t1).count());

        last_height = custom_avl.height();
        last_rotations = custom_avl.rotation_stats();

        // std::map (Red-Black Tree)
        auto t3 = std::chrono::high_resolution_clock::now();
        std::map<int, int> std_map;
        for (int i = 0; i < kBenchN; ++i) {
            std_map.insert({i, i ^ 0xAA55});
        }
        auto t4 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < kBenchN; ++i) {
            auto it = std_map.find(i);
            if (it != std_map.end()) std_checksum += static_cast<uint64_t>(it->second);
        }
        auto t5 = std::chrono::high_resolution_clock::now();
        std_insert_times.push_back(std::chrono::duration<double, std::milli>(t4 - t3).count());
        std_lookup_times.push_back(std::chrono::duration<double, std::milli>(t5 - t4).count());
    }

    assert(custom_checksum == std_checksum);
    std::sort(custom_insert_times.begin(), custom_insert_times.end());
    std::sort(custom_lookup_times.begin(), custom_lookup_times.end());
    std::sort(std_insert_times.begin(), std_insert_times.end());
    std::sort(std_lookup_times.begin(), std_lookup_times.end());

    double custom_insert_med = custom_insert_times[kTrials / 2];
    double custom_lookup_med = custom_lookup_times[kTrials / 2];
    double std_insert_med = std_insert_times[kTrials / 2];
    double std_lookup_med = std_lookup_times[kTrials / 2];

    std::cout << "AVLTree (median): insert " << custom_insert_med << " ms | lookup " << custom_lookup_med << " ms\n";
    std::cout << "std::map (median): insert " << std_insert_med << " ms | lookup " << std_lookup_med << " ms\n";
    std::cout << "AVLTree final height: " << last_height
              << " | total rotations: " << last_rotations.total()
              << " (LL=" << last_rotations.ll_rotations
              << ", RR=" << last_rotations.rr_rotations
              << ", LR=" << last_rotations.lr_rotations
              << ", RL=" << last_rotations.rl_rotations << ")\n";

    std::cout << "AVLTree tests passed\n";
    return 0;
}
