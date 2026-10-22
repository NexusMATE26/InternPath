#include "internpath/ds/dynamic_array.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <memory>
#include <stdexcept>
#include <string>
#include <iostream>

using internpath::ds::DynamicArray;

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
    // 1. Basic empty state
    DynamicArray<int> a;
    assert(a.empty() && a.size()==0 && a.capacity()==0);
    bool thrown=false;try { a.pop_back(); } catch(const std::out_of_range&) { thrown=true; } assert(thrown);
    thrown=false;try { (void)a.front(); } catch(const std::out_of_range&) { thrown=true; } assert(thrown);
    thrown=false;try { (void)a.back(); } catch(const std::out_of_range&) { thrown=true; } assert(thrown);

    // 2. Growth and access
    for(int i=0;i<1000;++i) a.push_back(i);
    assert(a.size()==1000 && a.capacity()>=1000);
    for(int i=0;i<1000;++i) assert(a.at(i)==i);
    assert(a.front()==0);
    assert(a.back()==999);
    thrown=false;try { (void)a.at(1000); } catch(const std::out_of_range&) { thrown=true; } assert(thrown);

    // 3. Copy operations
    auto b=a; b[0]=9999;assert(a[0]==0 && b[0]==9999);
    DynamicArray<int> c; c = a; assert(c[999]==999);
    c=c; assert(c.size()==1000);

    // 4. Move operations
    DynamicArray<int> d(std::move(c)); assert(d.size()==1000 && c.empty());
    DynamicArray<int> e; e=std::move(d); assert(e.size()==1000 && d.empty());
    e.clear(); assert(e.empty()); e.push_back(7); e.pop_back(); assert(e.empty());

    // 5. Initializer list and strings
    DynamicArray<std::string> s={"C++","RTOS"};
    assert(s.size()==2);
    assert(s[0]=="C++" && s[1]=="RTOS");
    assert(s.front()=="C++" && s.back()=="RTOS");

    // 6. Move-only objects
    DynamicArray<std::unique_ptr<int>> owners;
    owners.emplace_back(std::make_unique<int>(42));
    owners.emplace_back(std::make_unique<int>(13));
    assert(*owners[0]==42 && *owners[1]==13);

    // 7. Geometric capacity expansion
    DynamicArray<int> growth;std::size_t prior=0;
    for(int i=0;i<32;++i){growth.push_back(i);assert(growth.capacity()>=growth.size());assert(growth.capacity()>=prior);prior=growth.capacity();}

    // 8. Self-referencing push_back & emplace_back across reallocation
    DynamicArray<std::string> self_ref;
    self_ref.push_back("a_string_that_is_long_enough_to_allocate_on_the_heap_1234567890");
    self_ref.push_back(self_ref[0]); // Capacity expands from 1 to 2; self_ref[0] must not dangle
    assert(self_ref.size()==2);
    assert(self_ref[0]==self_ref[1]);
    self_ref.emplace_back(self_ref.back()); // Capacity expands from 2 to 4
    assert(self_ref.size()==3);
    assert(self_ref[2]==self_ref[0]);

    // 9. shrink_to_fit
    DynamicArray<int> stf;
    stf.reserve(100);
    assert(stf.capacity()==100 && stf.empty());
    stf.push_back(1);
    stf.push_back(2);
    stf.shrink_to_fit();
    assert(stf.size()==2 && stf.capacity()==2);
    assert(stf[0]==1 && stf[1]==2);

    // 10. Equality and iteration
    DynamicArray<int> eq1 = {10, 20, 30};
    DynamicArray<int> eq2 = {10, 20, 30};
    DynamicArray<int> eq3 = {10, 20, 40};
    assert(eq1 == eq2);
    assert(eq1 != eq3);
    const auto& const_eq = eq1;
    int sum = 0;
    for (auto it = const_eq.cbegin(); it != const_eq.cend(); ++it) {
        sum += *it;
    }
    assert(sum == 60);

    // 11. Exception safety & zero memory leak on throwing constructor
    {
        ThrowOnCopy::alive_count = 0;
        ThrowOnCopy::copy_count_before_throw = 1000;
        DynamicArray<ThrowOnCopy> src;
        for (int i = 0; i < 5; ++i) src.emplace_back(i);
        assert(ThrowOnCopy::alive_count == 5);

        // Make copy constructor throw after 2 items
        ThrowOnCopy::copy_count_before_throw = 2;
        bool copy_failed = false;
        try {
            DynamicArray<ThrowOnCopy> copy_arr(src);
        } catch (const std::runtime_error&) {
            copy_failed = true;
        }
        assert(copy_failed);
        // All temporary elements constructed during failed copy must have been destroyed
        assert(ThrowOnCopy::alive_count == 5);
        assert(src.size() == 5);
    }
    assert(ThrowOnCopy::alive_count == 0);

    std::cout << "DynamicArray tests passed\n";
    return 0;
}
