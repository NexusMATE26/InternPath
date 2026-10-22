#pragma once
#include "internpath/ds/dynamic_array.hpp"
#include <cstddef>
#include <initializer_list>
#include <stdexcept>
#include <utility>

namespace internpath::ds {

template<class T, class Container = DynamicArray<T>>
class Stack {
public:
    using container_type = Container;
    using value_type = typename Container::value_type;
    using size_type = typename Container::size_type;

    Stack() = default;

    Stack(std::initializer_list<T> items) {
        for (const auto& item : items) {
            push(item);
        }
    }

    void push(const T& value) { container_.push_back(value); }
    void push(T&& value) { container_.push_back(std::move(value)); }

    template<class... Args>
    decltype(auto) emplace(Args&&... args) {
        return container_.emplace_back(std::forward<Args>(args)...);
    }

    void pop() {
        if (empty()) throw std::out_of_range("Stack::pop empty stack");
        container_.pop_back();
    }

    T& top() {
        if (empty()) throw std::out_of_range("Stack::top empty stack");
        return container_.back();
    }

    const T& top() const {
        if (empty()) throw std::out_of_range("Stack::top empty stack");
        return container_.back();
    }

    size_type size() const noexcept { return container_.size(); }
    bool empty() const noexcept { return container_.empty(); }
    void clear() noexcept { container_.clear(); }

    void swap(Stack& other) noexcept {
        container_.swap(other.container_);
    }

    bool operator==(const Stack& other) const {
        return container_ == other.container_;
    }

    bool operator!=(const Stack& other) const {
        return container_ != other.container_;
    }

private:
    Container container_;
};

} // namespace internpath::ds
