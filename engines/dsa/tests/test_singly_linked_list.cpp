#include "internpath/ds/singly_linked_list.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

using internpath::ds::SinglyLinkedList;

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
    SinglyLinkedList<int> list;
    assert(list.empty() && list.size() == 0);
    bool thrown = false;
    try { list.pop_front(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { (void)list.front(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);

    // 2. push_front and push_back
    list.push_front(20);
    list.push_front(10);
    list.push_back(30);
    list.push_back(40);
    assert(list.size() == 4 && !list.empty());
    assert(list.front() == 10);

    // 3. Forward iteration
    int expected[] = {10, 20, 30, 40};
    int idx = 0;
    for (int v : list) {
        assert(v == expected[idx++]);
    }
    assert(idx == 4);

    // 4. pop_front
    list.pop_front();
    assert(list.front() == 20 && list.size() == 3);
    list.pop_front();
    list.pop_front();
    assert(list.front() == 40 && list.size() == 1);
    list.pop_front();
    assert(list.empty() && list.size() == 0);

    // 4b. remove_first_if
    list.push_back(1);
    list.push_back(2);
    list.push_back(3);
    list.push_back(4);
    // remove middle (3)
    bool rm = list.remove_first_if([](int v){ return v == 3; });
    assert(rm && list.size() == 3);
    // remove tail (4)
    rm = list.remove_first_if([](int v){ return v == 4; });
    assert(rm && list.size() == 2);
    // remove head (1)
    rm = list.remove_first_if([](int v){ return v == 1; });
    assert(rm && list.size() == 1 && list.front() == 2);
    // remove non-existent
    rm = list.remove_first_if([](int v){ return v == 99; });
    assert(!rm && list.size() == 1);
    // remove last item (2)
    rm = list.remove_first_if([](int v){ return v == 2; });
    assert(rm && list.empty());
    // remove on empty
    rm = list.remove_first_if([](int v){ return v == 2; });
    assert(!rm);

    // 5. Append after drain (verifying tail reset)
    list.push_back(100);
    assert(list.front() == 100 && list.size() == 1);
    list.clear();
    assert(list.empty() && list.size() == 0);

    // 6. Initializer list and equality
    SinglyLinkedList<std::string> s1 = {"Algorithms", "DataStructures", "Systems"};
    SinglyLinkedList<std::string> s2 = {"Algorithms", "DataStructures", "Systems"};
    SinglyLinkedList<std::string> s3 = {"Algorithms", "Networks"};
    assert(s1 == s2);
    assert(s1 != s3);
    assert(s1.front() == "Algorithms");

    // 7. Copy and self-assignment
    auto s1_copy = s1;
    assert(s1_copy == s1);
    s1_copy = s1_copy;
    assert(s1_copy == s1);

    // 8. Move operations
    SinglyLinkedList<std::string> s1_moved(std::move(s1_copy));
    assert(s1_moved == s1);
    assert(s1_copy.empty() && s1_copy.size() == 0);

    SinglyLinkedList<std::string> s1_move_assign;
    s1_move_assign = std::move(s1_moved);
    assert(s1_move_assign == s1);
    assert(s1_moved.empty());

    // 9. Move-only types (std::unique_ptr)
    SinglyLinkedList<std::unique_ptr<int>> ptrs;
    ptrs.push_back(std::make_unique<int>(1));
    ptrs.push_front(std::make_unique<int>(0));
    ptrs.emplace_back(std::make_unique<int>(2));
    assert(*ptrs.front() == 0);
    assert(ptrs.size() == 3);
    ptrs.pop_front();
    assert(*ptrs.front() == 1);

    // 10. Exception safety & zero leaks on throwing copy
    {
        ThrowOnCopy::alive_count = 0;
        ThrowOnCopy::copy_count_before_throw = 1000;
        SinglyLinkedList<ThrowOnCopy> src;
        for (int i = 0; i < 5; ++i) src.emplace_back(i);
        assert(ThrowOnCopy::alive_count == 5);

        ThrowOnCopy::copy_count_before_throw = 3;
        bool copy_failed = false;
        try {
            SinglyLinkedList<ThrowOnCopy> failed_copy(src);
        } catch (const std::runtime_error&) {
            copy_failed = true;
        }
        assert(copy_failed);
        assert(ThrowOnCopy::alive_count == 5);
        assert(src.size() == 5);
    }
    assert(ThrowOnCopy::alive_count == 0);

    std::cout << "SinglyLinkedList tests passed\n";
    return 0;
}
