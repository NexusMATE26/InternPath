#pragma once
#include <cstddef>
#include <initializer_list>
#include <memory>
#include <stdexcept>
#include <utility>

namespace internpath::ds {

template<class T>
class CircularQueue {
public:
    using size_type = std::size_t;
    using value_type = T;

    CircularQueue() = default;

    explicit CircularQueue(size_type initial_cap) {
        if (initial_cap > 0) {
            data_ = alloc_.allocate(initial_cap);
            capacity_ = initial_cap;
        }
    }

    CircularQueue(std::initializer_list<T> items) {
        if (items.size() == 0) return;
        T* fresh = alloc_.allocate(items.size());
        size_type constructed = 0;
        try {
            for (const auto& item : items) {
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, item);
                ++constructed;
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            alloc_.deallocate(fresh, items.size());
            throw;
        }
        data_ = fresh;
        head_ = 0;
        size_ = items.size();
        capacity_ = items.size();
    }

    ~CircularQueue() {
        clear();
        deallocate();
    }

    CircularQueue(const CircularQueue& other) {
        if (other.size_ == 0) return;
        T* fresh = alloc_.allocate(other.size_);
        size_type constructed = 0;
        try {
            for (; constructed < other.size_; ++constructed) {
                size_type src_idx = (other.head_ + constructed) % other.capacity_;
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, other.data_[src_idx]);
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            alloc_.deallocate(fresh, other.size_);
            throw;
        }
        data_ = fresh;
        head_ = 0;
        size_ = other.size_;
        capacity_ = other.size_;
    }

    CircularQueue(CircularQueue&& other) noexcept {
        swap(other);
    }

    CircularQueue& operator=(const CircularQueue& other) {
        if (this != &other) {
            CircularQueue tmp(other);
            swap(tmp);
        }
        return *this;
    }

    CircularQueue& operator=(CircularQueue&& other) noexcept {
        if (this != &other) {
            CircularQueue tmp(std::move(other));
            swap(tmp);
        }
        return *this;
    }

    size_type size() const noexcept { return size_; }
    size_type capacity() const noexcept { return capacity_; }
    bool empty() const noexcept { return size_ == 0; }

    T& front() {
        if (empty()) throw std::out_of_range("CircularQueue::front empty queue");
        return data_[head_];
    }

    const T& front() const {
        if (empty()) throw std::out_of_range("CircularQueue::front empty queue");
        return data_[head_];
    }

    T& back() {
        if (empty()) throw std::out_of_range("CircularQueue::back empty queue");
        size_type last_idx = (head_ + size_ - 1) % capacity_;
        return data_[last_idx];
    }

    const T& back() const {
        if (empty()) throw std::out_of_range("CircularQueue::back empty queue");
        size_type last_idx = (head_ + size_ - 1) % capacity_;
        return data_[last_idx];
    }

    template<class... Args>
    T& emplace(Args&&... args) {
        if (size_ < capacity_) {
            size_type tail_idx = (head_ + size_) % capacity_;
            std::allocator_traits<decltype(alloc_)>::construct(
                alloc_, data_ + tail_idx, std::forward<Args>(args)...);
            ++size_;
            return data_[tail_idx];
        }

        const size_type max_cap = std::allocator_traits<decltype(alloc_)>::max_size(alloc_);
        if (size_ >= max_cap) {
            throw std::length_error("CircularQueue capacity too large");
        }
        size_type new_cap = capacity_ ? capacity_ * 2 : 4;
        if (new_cap < capacity_ || new_cap > max_cap) {
            new_cap = max_cap;
        }

        T* fresh = alloc_.allocate(new_cap);
        // 1. Construct new element at fresh + size_ FIRST (protects against args referencing old data)
        try {
            std::allocator_traits<decltype(alloc_)>::construct(
                alloc_, fresh + size_, std::forward<Args>(args)...);
        } catch (...) {
            alloc_.deallocate(fresh, new_cap);
            throw;
        }

        // 2. Transfer existing elements linearly into fresh[0 ... size_-1]
        size_type constructed = 0;
        try {
            for (; constructed < size_; ++constructed) {
                size_type src_idx = (head_ + constructed) % capacity_;
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, std::move_if_noexcept(data_[src_idx]));
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + size_);
            alloc_.deallocate(fresh, new_cap);
            throw;
        }

        // 3. Destroy old elements and free old storage
        for (size_type j = 0; j < size_; ++j) {
            size_type src_idx = (head_ + j) % capacity_;
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + src_idx);
        }
        if (data_) {
            alloc_.deallocate(data_, capacity_);
        }

        data_ = fresh;
        head_ = 0;
        capacity_ = new_cap;
        ++size_;
        return data_[size_ - 1];
    }

    void enqueue(const T& value) { emplace(value); }
    void enqueue(T&& value) { emplace(std::move(value)); }

    void dequeue() {
        if (empty()) throw std::out_of_range("CircularQueue::dequeue empty queue");
        std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + head_);
        head_ = (head_ + 1) % capacity_;
        --size_;
        if (size_ == 0) {
            head_ = 0;
        }
    }

    void clear() noexcept {
        while (size_ > 0) {
            size_type idx = (head_ + size_ - 1) % capacity_;
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + idx);
            --size_;
        }
        head_ = 0;
    }

    void swap(CircularQueue& other) noexcept {
        using std::swap;
        swap(data_, other.data_);
        swap(head_, other.head_);
        swap(size_, other.size_);
        swap(capacity_, other.capacity_);
    }

    bool operator==(const CircularQueue& other) const {
        if (size_ != other.size_) return false;
        for (size_type i = 0; i < size_; ++i) {
            size_type this_idx = (head_ + i) % capacity_;
            size_type other_idx = (other.head_ + i) % other.capacity_;
            if (!(data_[this_idx] == other.data_[other_idx])) return false;
        }
        return true;
    }

    bool operator!=(const CircularQueue& other) const {
        return !(*this == other);
    }

private:
    void deallocate() noexcept {
        if (data_) {
            alloc_.deallocate(data_, capacity_);
        }
        data_ = nullptr;
        head_ = 0;
        size_ = 0;
        capacity_ = 0;
    }

    std::allocator<T> alloc_;
    T* data_ = nullptr;
    size_type head_ = 0;
    size_type size_ = 0;
    size_type capacity_ = 0;
};

} // namespace internpath::ds
