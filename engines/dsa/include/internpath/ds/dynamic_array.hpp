#pragma once
#include <cstddef>
#include <memory>
#include <stdexcept>
#include <utility>
#include <initializer_list>

namespace internpath::ds {

template<class T>
class DynamicArray {
public:
    using size_type = std::size_t;
    using value_type = T;

    DynamicArray() = default;

    DynamicArray(std::initializer_list<T> items) {
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
        size_ = items.size();
        capacity_ = items.size();
    }

    explicit DynamicArray(size_type count, const T& value = T()) {
        if (count == 0) return;
        T* fresh = alloc_.allocate(count);
        size_type constructed = 0;
        try {
            for (; constructed < count; ++constructed) {
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, value);
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            alloc_.deallocate(fresh, count);
            throw;
        }
        data_ = fresh;
        size_ = count;
        capacity_ = count;
    }

    ~DynamicArray() {
        clear();
        deallocate();
    }

    DynamicArray(const DynamicArray& other) {
        if (other.size_ == 0) return;
        T* fresh = alloc_.allocate(other.size_);
        size_type constructed = 0;
        try {
            for (; constructed < other.size_; ++constructed) {
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, other.data_[constructed]);
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            alloc_.deallocate(fresh, other.size_);
            throw;
        }
        data_ = fresh;
        size_ = other.size_;
        capacity_ = other.size_;
    }

    DynamicArray(DynamicArray&& other) noexcept {
        swap(other);
    }

    DynamicArray& operator=(const DynamicArray& other) {
        if (this != &other) {
            DynamicArray tmp(other);
            swap(tmp);
        }
        return *this;
    }

    DynamicArray& operator=(DynamicArray&& other) noexcept {
        if (this != &other) {
            DynamicArray tmp(std::move(other));
            swap(tmp);
        }
        return *this;
    }

    size_type size() const noexcept { return size_; }
    size_type capacity() const noexcept { return capacity_; }
    bool empty() const noexcept { return size_ == 0; }

    T* data() noexcept { return data_; }
    const T* data() const noexcept { return data_; }

    T* begin() noexcept { return data_; }
    const T* begin() const noexcept { return data_; }
    T* end() noexcept { return data_ ? data_ + size_ : nullptr; }
    const T* end() const noexcept { return data_ ? data_ + size_ : nullptr; }

    const T* cbegin() const noexcept { return begin(); }
    const T* cend() const noexcept { return end(); }

    T& operator[](size_type i) noexcept { return data_[i]; }
    const T& operator[](size_type i) const noexcept { return data_[i]; }

    T& at(size_type i) {
        if (i >= size_) throw std::out_of_range("DynamicArray::at");
        return data_[i];
    }
    const T& at(size_type i) const {
        if (i >= size_) throw std::out_of_range("DynamicArray::at");
        return data_[i];
    }

    T& front() {
        if (empty()) throw std::out_of_range("DynamicArray::front");
        return data_[0];
    }
    const T& front() const {
        if (empty()) throw std::out_of_range("DynamicArray::front");
        return data_[0];
    }

    T& back() {
        if (empty()) throw std::out_of_range("DynamicArray::back");
        return data_[size_ - 1];
    }
    const T& back() const {
        if (empty()) throw std::out_of_range("DynamicArray::back");
        return data_[size_ - 1];
    }

    void reserve(size_type new_cap) {
        if (new_cap <= capacity_) return;
        if (new_cap > std::allocator_traits<decltype(alloc_)>::max_size(alloc_)) {
            throw std::length_error("DynamicArray capacity too large");
        }
        T* fresh = alloc_.allocate(new_cap);
        size_type constructed = 0;
        try {
            for (; constructed < size_; ++constructed) {
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, std::move_if_noexcept(data_[constructed]));
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            alloc_.deallocate(fresh, new_cap);
            throw;
        }
        for (size_type j = 0; j < size_; ++j) {
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + j);
        }
        deallocate();
        data_ = fresh;
        capacity_ = new_cap;
    }

    void shrink_to_fit() {
        if (capacity_ <= size_) return;
        if (size_ == 0) {
            deallocate();
            return;
        }
        T* fresh = alloc_.allocate(size_);
        size_type constructed = 0;
        try {
            for (; constructed < size_; ++constructed) {
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, std::move_if_noexcept(data_[constructed]));
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            alloc_.deallocate(fresh, size_);
            throw;
        }
        for (size_type j = 0; j < size_; ++j) {
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + j);
        }
        deallocate();
        data_ = fresh;
        capacity_ = size_;
    }

    void resize(size_type new_size, const T& value = T()) {
        if (new_size < size_) {
            while (size_ > new_size) {
                --size_;
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + size_);
            }
        } else if (new_size > size_) {
            reserve(new_size);
            while (size_ < new_size) {
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, data_ + size_, value);
                ++size_;
            }
        }
    }

    template<class... Args>
    T& emplace_back(Args&&... args) {
        if (size_ < capacity_) {
            std::allocator_traits<decltype(alloc_)>::construct(
                alloc_, data_ + size_, std::forward<Args>(args)...);
            ++size_;
            return data_[size_ - 1];
        }

        const size_type max_cap = std::allocator_traits<decltype(alloc_)>::max_size(alloc_);
        if (size_ >= max_cap) {
            throw std::length_error("DynamicArray capacity too large");
        }
        size_type new_cap = capacity_ ? capacity_ * 2 : 1;
        if (new_cap < capacity_ || new_cap > max_cap) {
            new_cap = max_cap;
        }

        T* fresh = alloc_.allocate(new_cap);
        try {
            std::allocator_traits<decltype(alloc_)>::construct(
                alloc_, fresh + size_, std::forward<Args>(args)...);
        } catch (...) {
            alloc_.deallocate(fresh, new_cap);
            throw;
        }

        size_type constructed = 0;
        try {
            for (; constructed < size_; ++constructed) {
                std::allocator_traits<decltype(alloc_)>::construct(
                    alloc_, fresh + constructed, std::move_if_noexcept(data_[constructed]));
            }
        } catch (...) {
            for (size_type j = 0; j < constructed; ++j) {
                std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + j);
            }
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, fresh + size_);
            alloc_.deallocate(fresh, new_cap);
            throw;
        }

        for (size_type j = 0; j < size_; ++j) {
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + j);
        }
        if (data_) {
            alloc_.deallocate(data_, capacity_);
        }

        data_ = fresh;
        capacity_ = new_cap;
        ++size_;
        return data_[size_ - 1];
    }

    void push_back(const T& value) { emplace_back(value); }
    void push_back(T&& value) { emplace_back(std::move(value)); }

    void pop_back() {
        if (empty()) throw std::out_of_range("DynamicArray::pop_back");
        --size_;
        std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + size_);
    }

    void clear() noexcept {
        while (size_) {
            --size_;
            std::allocator_traits<decltype(alloc_)>::destroy(alloc_, data_ + size_);
        }
    }

    void swap(DynamicArray& other) noexcept {
        using std::swap;
        swap(data_, other.data_);
        swap(size_, other.size_);
        swap(capacity_, other.capacity_);
    }

    bool operator==(const DynamicArray& other) const {
        if (size_ != other.size_) return false;
        for (size_type i = 0; i < size_; ++i) {
            if (!(data_[i] == other.data_[i])) return false;
        }
        return true;
    }

    bool operator!=(const DynamicArray& other) const {
        return !(*this == other);
    }

private:
    void deallocate() noexcept {
        if (data_) {
            alloc_.deallocate(data_, capacity_);
        }
        data_ = nullptr;
        capacity_ = 0;
    }

    std::allocator<T> alloc_;
    T* data_ = nullptr;
    size_type size_ = 0;
    size_type capacity_ = 0;
};

} // namespace internpath::ds
