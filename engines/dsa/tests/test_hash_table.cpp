#include "internpath/ds/hash_table.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <algorithm>
#include <cassert>
#include <chrono>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

using internpath::ds::HashTable;

struct ForcedCollisionHash {
    std::size_t operator()(const std::string&) const noexcept {
        return 42; // All strings hash to the same bucket
    }
};

struct ThrowOnCopy {
    static int alive_count;
    static int copy_count_before_throw;
    int id = 0;

    ThrowOnCopy(int v = 0) : id(v) { ++alive_count; }
    ThrowOnCopy(const ThrowOnCopy& other) : id(other.id) {
        if (--copy_count_before_throw <= 0) {
            throw std::runtime_error("Simulated copy failure");
        }
        ++alive_count;
    }
    ThrowOnCopy(ThrowOnCopy&& other) noexcept : id(other.id) {
        ++alive_count;
    }
    ThrowOnCopy& operator=(const ThrowOnCopy& other) {
        if (this != &other) {
            if (--copy_count_before_throw <= 0) {
                throw std::runtime_error("Simulated copy assignment failure");
            }
            id = other.id;
        }
        return *this;
    }
    ThrowOnCopy& operator=(ThrowOnCopy&& other) noexcept {
        id = other.id;
        return *this;
    }
    ~ThrowOnCopy() { --alive_count; }
};
int ThrowOnCopy::alive_count = 0;
int ThrowOnCopy::copy_count_before_throw = 1000;

int main() {
    // 1. Empty table behavior
    HashTable<std::string, int> ht;
    assert(ht.empty() && ht.size() == 0);
    assert(ht.find("missing") == nullptr);
    assert(!ht.contains("missing"));
    assert(!ht.erase("missing"));
    assert(ht.load_factor() == 0.0f);

    // 2. Insert and Duplicate keys
    auto res1 = ht.insert("apple", 100);
    assert(res1.second && *res1.first == 100);
    assert(ht.size() == 1 && !ht.empty());
    assert(ht.contains("apple"));
    assert(*ht.find("apple") == 100);

    // Duplicate insert: should reject update
    auto res2 = ht.insert("apple", 999);
    assert(!res2.second && *res2.first == 100);
    assert(*ht.find("apple") == 100);

    // insert_or_assign: should update existing value
    auto res3 = ht.insert_or_assign("apple", 200);
    assert(!res3.second && *res3.first == 200);
    assert(*ht.find("apple") == 200);

    // insert_or_assign on new key: should insert
    auto res4 = ht.insert_or_assign("banana", 300);
    assert(res4.second && *res4.first == 300);
    assert(ht.size() == 2);

    // operator[] access and insertion
    assert(ht["apple"] == 200);
    ht["cherry"] = 400;
    assert(ht.size() == 3 && ht["cherry"] == 400);

    // 3. Removal
    assert(ht.erase("banana"));
    assert(!ht.contains("banana"));
    assert(ht.find("banana") == nullptr);
    assert(ht.size() == 2);
    assert(!ht.erase("banana")); // erasing already-removed key returns false

    // 4. Forced collisions test
    HashTable<std::string, int, ForcedCollisionHash> collision_table(8);
    collision_table.insert("keyA", 1);
    collision_table.insert("keyB", 2);
    collision_table.insert("keyC", 3);
    collision_table.insert("keyD", 4);
    assert(collision_table.size() == 4);
    assert(collision_table.collision_count() == 3);
    assert(collision_table.max_bucket_length() == 4);
    assert(collision_table.non_empty_buckets() == 1);
    // All keys must still be found despite forced collisions
    assert(*collision_table.find("keyA") == 1);
    assert(*collision_table.find("keyB") == 2);
    assert(*collision_table.find("keyC") == 3);
    assert(*collision_table.find("keyD") == 4);
    // Erase from middle of collision bucket
    assert(collision_table.erase("keyC"));
    assert(!collision_table.contains("keyC"));
    assert(collision_table.size() == 3);
    assert(collision_table.collision_count() == 2);

    // 5. Rehashing and Load Factor
    HashTable<int, int> rehash_table(8);
    std::size_t initial_buckets = rehash_table.bucket_count();
    for (int i = 0; i < 50; ++i) {
        rehash_table.insert(i, i * 10);
        assert(rehash_table.load_factor() <= rehash_table.max_load_factor() + 0.05f);
    }
    assert(rehash_table.size() == 50);
    assert(rehash_table.bucket_count() > initial_buckets);
    for (int i = 0; i < 50; ++i) {
        assert(rehash_table.contains(i));
        assert(*rehash_table.find(i) == i * 10);
    }

    // 6. Invariant preservation (sum of bucket sizes == size)
    std::size_t sum_bucket_sizes = 0;
    for (std::size_t b = 0; b < rehash_table.bucket_count(); ++b) {
        sum_bucket_sizes += rehash_table.bucket_size(b);
    }
    assert(sum_bucket_sizes == rehash_table.size());

    // 7. Copy and move operations
    HashTable<int, int> copy_table = rehash_table;
    assert(copy_table.size() == rehash_table.size());
    assert(copy_table.contains(25) && *copy_table.find(25) == 250);
    copy_table = copy_table; // self-assignment
    assert(copy_table.size() == rehash_table.size());

    HashTable<int, int> moved_table = std::move(copy_table);
    assert(moved_table.size() == 50);
    assert(copy_table.empty());

    // 8. Large dataset verification
    HashTable<int, int> large_table;
    const int kLargeCount = 5000;
    for (int i = 0; i < kLargeCount; ++i) {
        large_table.insert(i, i * 2);
    }
    assert(large_table.size() == kLargeCount);
    for (int i = 0; i < kLargeCount; ++i) {
        assert(*large_table.find(i) == i * 2);
    }
    // Erase even numbers
    for (int i = 0; i < kLargeCount; i += 2) {
        assert(large_table.erase(i));
    }
    assert(large_table.size() == kLargeCount / 2);
    for (int i = 0; i < kLargeCount; ++i) {
        if (i % 2 == 0) {
            assert(!large_table.contains(i));
        } else {
            assert(large_table.contains(i));
        }
    }

    // 9. Exception safety test
    {
        ThrowOnCopy::alive_count = 0;
        ThrowOnCopy::copy_count_before_throw = 1000;
        HashTable<int, ThrowOnCopy> src;
        for (int i = 0; i < 6; ++i) {
            src.insert(i, ThrowOnCopy(i));
        }
        assert(ThrowOnCopy::alive_count == 6);

        ThrowOnCopy::copy_count_before_throw = 3;
        bool copy_failed = false;
        try {
            HashTable<int, ThrowOnCopy> failed_copy(src);
        } catch (const std::runtime_error&) {
            copy_failed = true;
        }
        assert(copy_failed);
        assert(ThrowOnCopy::alive_count == 6);
        assert(src.size() == 6);
    }
    assert(ThrowOnCopy::alive_count == 0);

    // 10. Multi-trial Benchmark with Checksum & Median vs std::unordered_map
    const int kBenchN = 20000;
    const int kTrials = 5;
    std::cout << "--- Benchmark: HashTable vs std::unordered_map (" << kBenchN << " items, " << kTrials << " trials) ---\n";

    std::vector<double> custom_insert_times;
    std::vector<double> custom_lookup_times;
    std::vector<double> std_insert_times;
    std::vector<double> std_lookup_times;
    uint64_t custom_checksum = 0;
    uint64_t std_checksum = 0;

    for (int t = 0; t < kTrials; ++t) {
        // Custom HashTable
        auto t0 = std::chrono::high_resolution_clock::now();
        HashTable<int, int> custom_ht;
        for (int i = 0; i < kBenchN; ++i) {
            custom_ht.insert(i, i ^ 0x55AA);
        }
        auto t1 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < kBenchN; ++i) {
            const int* v = custom_ht.find(i);
            if (v) custom_checksum += static_cast<uint64_t>(*v);
        }
        auto t2 = std::chrono::high_resolution_clock::now();
        custom_insert_times.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
        custom_lookup_times.push_back(std::chrono::duration<double, std::milli>(t2 - t1).count());

        // std::unordered_map
        auto t3 = std::chrono::high_resolution_clock::now();
        std::unordered_map<int, int> std_umap;
        for (int i = 0; i < kBenchN; ++i) {
            std_umap.insert({i, i ^ 0x55AA});
        }
        auto t4 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < kBenchN; ++i) {
            auto it = std_umap.find(i);
            if (it != std_umap.end()) std_checksum += static_cast<uint64_t>(it->second);
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

    std::cout << "HashTable (median): insert " << custom_insert_med << " ms | lookup " << custom_lookup_med << " ms\n";
    std::cout << "std::unordered_map (median): insert " << std_insert_med << " ms | lookup " << std_lookup_med << " ms\n";
    std::cout << "HashTable tests passed\n";
    return 0;
}
