#include "internpath/ds/circular_queue.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

using internpath::ds::CircularQueue;

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
    CircularQueue<int> q;
    assert(q.empty() && q.size() == 0);
    bool thrown = false;
    try { q.dequeue(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { (void)q.front(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);
    thrown = false;
    try { (void)q.back(); } catch (const std::out_of_range&) { thrown = true; }
    assert(thrown);

    // 2. Simple FIFO enqueue and dequeue
    q.enqueue(10);
    q.enqueue(20);
    q.emplace(30);
    assert(q.size() == 3 && !q.empty());
    assert(q.front() == 10);
    assert(q.back() == 30);
    q.dequeue();
    assert(q.front() == 20 && q.size() == 2);
    q.dequeue();
    assert(q.front() == 30 && q.size() == 1);
    q.dequeue();
    assert(q.empty() && q.size() == 0);

    // 3. Queue wraparound WITHOUT growth (Requirement 9)
    CircularQueue<int> wrap_q(4);
    assert(wrap_q.capacity() == 4);
    wrap_q.enqueue(1);
    wrap_q.enqueue(2);
    wrap_q.enqueue(3);
    // Dequeue 2 items: head advances from 0 -> 2
    wrap_q.dequeue(); // removes 1
    wrap_q.dequeue(); // removes 2
    assert(wrap_q.size() == 1 && wrap_q.front() == 3);
    // Enqueue 3 items: tail wraps around index 3 -> 0 -> 1 -> 2
    wrap_q.enqueue(4);
    wrap_q.enqueue(5);
    wrap_q.enqueue(6);
    assert(wrap_q.size() == 4);
    assert(wrap_q.capacity() == 4); // No growth yet!
    assert(wrap_q.front() == 3);
    assert(wrap_q.back() == 6);
    // Verify FIFO ordering across wraparound
    assert(wrap_q.front() == 3); wrap_q.dequeue();
    assert(wrap_q.front() == 4); wrap_q.dequeue();
    assert(wrap_q.front() == 5); wrap_q.dequeue();
    assert(wrap_q.front() == 6); wrap_q.dequeue();
    assert(wrap_q.empty());

    // 4. Queue wraparound WITH automatic capacity growth (Requirement 9)
    CircularQueue<int> grow_q(4);
    grow_q.enqueue(100);
    grow_q.enqueue(101);
    grow_q.enqueue(102);
    grow_q.dequeue(); // head is now 1
    grow_q.dequeue(); // head is now 2
    grow_q.enqueue(103);
    grow_q.enqueue(104);
    grow_q.enqueue(105);
    // Capacity 4 is full: contains [102, 103, 104, 105], wrapped around
    assert(grow_q.size() == 4 && grow_q.capacity() == 4);
    // This enqueue forces automatic capacity growth from 4 -> 8 and un-wraps elements
    grow_q.enqueue(106);
    assert(grow_q.size() == 5 && grow_q.capacity() >= 8);
    assert(grow_q.front() == 102);
    assert(grow_q.back() == 106);

    int expected_grow[] = {102, 103, 104, 105, 106};
    for (int exp : expected_grow) {
        assert(grow_q.front() == exp);
        grow_q.dequeue();
    }
    assert(grow_q.empty());

    // 5. Self-referencing enqueue across reallocation
    CircularQueue<std::string> self_ref(2);
    self_ref.enqueue("internpath_long_string_heap_allocated_for_safety_check");
    self_ref.enqueue("second_long_string_element");
    // Capacity is full (2/2); enqueueing front forces growth while reading from front
    self_ref.enqueue(self_ref.front());
    assert(self_ref.size() == 3);
    assert(self_ref.back() == "internpath_long_string_heap_allocated_for_safety_check");

    // 6. Initializer list, strings, and equality
    CircularQueue<std::string> q1 = {"Task1", "Task2", "Task3"};
    CircularQueue<std::string> q2 = {"Task1", "Task2", "Task3"};
    CircularQueue<std::string> q3 = {"Task1", "Task4"};
    assert(q1 == q2);
    assert(q1 != q3);

    // 7. Copy and self-assignment across wrapped state
    CircularQueue<int> wrapped_copy_src(4);
    wrapped_copy_src.enqueue(10);
    wrapped_copy_src.enqueue(20);
    wrapped_copy_src.dequeue(); // head = 1
    wrapped_copy_src.enqueue(30);
    wrapped_copy_src.enqueue(40);
    // [20, 30, 40] wrapped
    CircularQueue<int> wrapped_copy(wrapped_copy_src);
    assert(wrapped_copy == wrapped_copy_src);
    wrapped_copy = wrapped_copy;
    assert(wrapped_copy == wrapped_copy_src);

    // 8. Move operations
    CircularQueue<int> moved(std::move(wrapped_copy));
    assert(moved == wrapped_copy_src);
    assert(wrapped_copy.empty());

    CircularQueue<int> move_assign;
    move_assign = std::move(moved);
    assert(move_assign == wrapped_copy_src);
    assert(moved.empty());

    // 9. Move-only objects (std::unique_ptr)
    CircularQueue<std::unique_ptr<int>> ptrs;
    ptrs.enqueue(std::make_unique<int>(1));
    ptrs.emplace(std::make_unique<int>(2));
    assert(*ptrs.front() == 1 && *ptrs.back() == 2);
    ptrs.dequeue();
    assert(*ptrs.front() == 2);
    ptrs.dequeue();
    assert(ptrs.empty());

    // 10. Exception safety on throwing copy
    {
        ThrowOnCopy::alive_count = 0;
        ThrowOnCopy::copy_count_before_throw = 1000;
        CircularQueue<ThrowOnCopy> src;
        for (int i = 0; i < 5; ++i) src.emplace(i);
        assert(ThrowOnCopy::alive_count == 5);

        ThrowOnCopy::copy_count_before_throw = 2;
        bool copy_failed = false;
        try {
            CircularQueue<ThrowOnCopy> failed_copy(src);
        } catch (const std::runtime_error&) {
            copy_failed = true;
        }
        assert(copy_failed);
        assert(ThrowOnCopy::alive_count == 5);
        assert(src.size() == 5);
    }
    assert(ThrowOnCopy::alive_count == 0);

    std::cout << "CircularQueue tests passed\n";
    return 0;
}
