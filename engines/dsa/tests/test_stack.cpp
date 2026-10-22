#include "internpath/ds/stack.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

using internpath::ds::Stack;

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
    Stack<int> s;
    assert(s.empty() && s.size() == 0);
    bool thrown = false;
    try { s.pop(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { (void)s.top(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);

    // 2. Push, top, and pop (LIFO)
    s.push(10);
    s.push(20);
    s.emplace(30);
    assert(s.size() == 3 && !s.empty());
    assert(s.top() == 30);
    s.pop();
    assert(s.top() == 20 && s.size() == 2);
    s.pop();
    assert(s.top() == 10 && s.size() == 1);
    s.pop();
    assert(s.empty() && s.size() == 0);

    // 3. Clear
    s.push(1);
    s.push(2);
    s.clear();
    assert(s.empty() && s.size() == 0);

    // 4. Initializer list and equality
    Stack<std::string> st1 = {"Frame0", "Frame1", "Frame2"};
    Stack<std::string> st2 = {"Frame0", "Frame1", "Frame2"};
    Stack<std::string> st3 = {"Frame0", "Frame1"};
    assert(st1 == st2);
    assert(st1 != st3);
    assert(st1.top() == "Frame2");

    // 5. Copy operations and self-assignment
    auto st_copy = st1;
    assert(st_copy == st1);
    st_copy = st_copy;
    assert(st_copy == st1);

    // 6. Move operations
    Stack<std::string> st_moved(std::move(st_copy));
    assert(st_moved == st1);
    assert(st_copy.empty());

    Stack<std::string> st_move_assign;
    st_move_assign = std::move(st_moved);
    assert(st_move_assign == st1);
    assert(st_moved.empty());

    // 7. Move-only types (std::unique_ptr)
    Stack<std::unique_ptr<int>> ptrs;
    ptrs.push(std::make_unique<int>(42));
    ptrs.emplace(std::make_unique<int>(84));
    assert(*ptrs.top() == 84);
    ptrs.pop();
    assert(*ptrs.top() == 42);
    ptrs.pop();
    assert(ptrs.empty());

    // 8. Exception safety on throwing copy
    {
        ThrowOnCopy::alive_count = 0;
        ThrowOnCopy::copy_count_before_throw = 1000;
        Stack<ThrowOnCopy> src;
        for (int i = 0; i < 5; ++i) src.emplace(i);
        assert(ThrowOnCopy::alive_count == 5);

        ThrowOnCopy::copy_count_before_throw = 2;
        bool copy_failed = false;
        try {
            Stack<ThrowOnCopy> failed_copy(src);
        } catch (const std::runtime_error&) {
            copy_failed = true;
        }
        assert(copy_failed);
        assert(ThrowOnCopy::alive_count == 5);
        assert(src.size() == 5);
    }
    assert(ThrowOnCopy::alive_count == 0);

    std::cout << "Stack tests passed\n";
    return 0;
}
