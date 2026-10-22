#include "internpath/ds/doubly_linked_list.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

using internpath::ds::DoublyLinkedList;

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
    // 1. Basic empty state and exceptions
    DoublyLinkedList<int> list;
    assert(list.empty() && list.size() == 0);
    bool thrown = false;
    try { list.pop_front(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { list.pop_back(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { (void)list.front(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { (void)list.back(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { list.erase(list.cend()); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);

    // 2. push_front, push_back, front, back
    list.push_back(20);
    list.push_front(10);
    list.push_back(30);
    list.push_front(0);
    // [0, 10, 20, 30]
    assert(list.size() == 4 && !list.empty());
    assert(list.front() == 0);
    assert(list.back() == 30);

    // 3. Bidirectional iteration
    int expected_forward[] = {0, 10, 20, 30};
    int idx = 0;
    for (auto it = list.begin(); it != list.end(); ++it) {
        assert(*it == expected_forward[idx++]);
    }
    assert(idx == 4);

    int expected_backward[] = {30, 20, 10, 0};
    idx = 0;
    auto rev_it = list.end();
    while (rev_it != list.begin()) {
        --rev_it;
        assert(*rev_it == expected_backward[idx++]);
    }
    assert(idx == 4);

    // 4. Middle insertion
    // Current: [0, 10, 20, 30]
    // Find node with value 20 and insert 15 before it:
    auto it_20 = list.begin();
    ++it_20; // 10
    ++it_20; // 20
    assert(*it_20 == 20);
    auto inserted_it = list.insert(it_20, 15);
    assert(*inserted_it == 15);
    assert(list.size() == 5);
    // Now: [0, 10, 15, 20, 30]

    // 5. Middle removal (requirement 10: Test linked-list removal from the middle)
    // Erase 15:
    auto next_after_erase = list.erase(inserted_it);
    assert(*next_after_erase == 20);
    assert(list.size() == 4);

    // Erase 20 from middle:
    auto next_after_20 = list.erase(next_after_erase);
    assert(*next_after_20 == 30);
    assert(list.size() == 3);
    // Now: [0, 10, 30]
    assert(list.front() == 0 && list.back() == 30);

    // 6. pop_front and pop_back
    list.pop_front(); // removes 0 -> [10, 30]
    assert(list.front() == 10 && list.size() == 2);
    list.pop_back();  // removes 30 -> [10]
    assert(list.back() == 10 && list.size() == 1);
    list.pop_back();  // removes 10 -> empty
    assert(list.empty() && list.size() == 0);

    // 7. Initializer list, strings, and equality
    DoublyLinkedList<std::string> s1 = {"Vite", "React", "FastAPI", "C++20"};
    DoublyLinkedList<std::string> s2 = {"Vite", "React", "FastAPI", "C++20"};
    DoublyLinkedList<std::string> s3 = {"Vite", "Vue"};
    assert(s1 == s2);
    assert(s1 != s3);
    assert(s1.front() == "Vite" && s1.back() == "C++20");

    // 8. Copy and self-assignment
    auto s1_copy = s1;
    assert(s1_copy == s1);
    s1_copy = s1_copy;
    assert(s1_copy == s1);

    // 9. Move operations
    DoublyLinkedList<std::string> s1_moved(std::move(s1_copy));
    assert(s1_moved == s1);
    assert(s1_copy.empty() && s1_copy.size() == 0);

    DoublyLinkedList<std::string> s1_move_assign;
    s1_move_assign = std::move(s1_moved);
    assert(s1_move_assign == s1);
    assert(s1_moved.empty());

    // 10. Move-only objects (std::unique_ptr)
    DoublyLinkedList<std::unique_ptr<int>> ptrs;
    ptrs.push_back(std::make_unique<int>(100));
    ptrs.push_front(std::make_unique<int>(50));
    ptrs.emplace_back(std::make_unique<int>(150));
    assert(*ptrs.front() == 50 && *ptrs.back() == 150);
    assert(ptrs.size() == 3);
    ptrs.pop_front();
    ptrs.pop_back();
    assert(*ptrs.front() == 100 && ptrs.size() == 1);

    // 11. Exception safety on throwing copy
    {
        ThrowOnCopy::alive_count = 0;
        ThrowOnCopy::copy_count_before_throw = 1000;
        DoublyLinkedList<ThrowOnCopy> src;
        for (int i = 0; i < 5; ++i) src.emplace_back(i);
        assert(ThrowOnCopy::alive_count == 5);

        ThrowOnCopy::copy_count_before_throw = 2;
        bool copy_failed = false;
        try {
            DoublyLinkedList<ThrowOnCopy> failed_copy(src);
        } catch (const std::runtime_error&) {
            copy_failed = true;
        }
        assert(copy_failed);
        assert(ThrowOnCopy::alive_count == 5);
        assert(src.size() == 5);
    }
    assert(ThrowOnCopy::alive_count == 0);

    std::cout << "DoublyLinkedList tests passed\n";
    return 0;
}
