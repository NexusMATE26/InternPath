#pragma once
#include <cstddef>
#include <initializer_list>
#include <iterator>
#include <stdexcept>
#include <utility>

namespace internpath::ds {

template<class T>
class SinglyLinkedList {
private:
    struct Node {
        T value;
        Node* next = nullptr;

        template<class... Args>
        explicit Node(Args&&... args) : value(std::forward<Args>(args)...), next(nullptr) {}
    };

    Node* head_ = nullptr;
    Node* tail_ = nullptr;
    std::size_t size_ = 0;

public:
    using size_type = std::size_t;
    using value_type = T;

    class iterator {
    public:
        using iterator_category = std::forward_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using pointer = T*;
        using reference = T&;

        iterator() = default;
        explicit iterator(Node* node) : current_(node) {}

        reference operator*() const { return current_->value; }
        pointer operator->() const { return &(current_->value); }

        iterator& operator++() {
            if (current_) current_ = current_->next;
            return *this;
        }

        iterator operator++(int) {
            iterator tmp = *this;
            if (current_) current_ = current_->next;
            return tmp;
        }

        bool operator==(const iterator& other) const { return current_ == other.current_; }
        bool operator!=(const iterator& other) const { return current_ != other.current_; }

    private:
        friend class SinglyLinkedList;
        Node* current_ = nullptr;
    };

    class const_iterator {
    public:
        using iterator_category = std::forward_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using pointer = const T*;
        using reference = const T&;

        const_iterator() = default;
        explicit const_iterator(const Node* node) : current_(node) {}
        const_iterator(const iterator& it) : current_(it.current_) {}

        reference operator*() const { return current_->value; }
        pointer operator->() const { return &(current_->value); }

        const_iterator& operator++() {
            if (current_) current_ = current_->next;
            return *this;
        }

        const_iterator operator++(int) {
            const_iterator tmp = *this;
            if (current_) current_ = current_->next;
            return tmp;
        }

        bool operator==(const const_iterator& other) const { return current_ == other.current_; }
        bool operator!=(const const_iterator& other) const { return current_ != other.current_; }

    private:
        const Node* current_ = nullptr;
    };

    SinglyLinkedList() = default;

    SinglyLinkedList(std::initializer_list<T> items) {
        try {
            for (const auto& item : items) {
                push_back(item);
            }
        } catch (...) {
            clear();
            throw;
        }
    }

    ~SinglyLinkedList() {
        clear();
    }

    SinglyLinkedList(const SinglyLinkedList& other) {
        try {
            for (const auto& item : other) {
                push_back(item);
            }
        } catch (...) {
            clear();
            throw;
        }
    }

    SinglyLinkedList(SinglyLinkedList&& other) noexcept {
        swap(other);
    }

    SinglyLinkedList& operator=(const SinglyLinkedList& other) {
        if (this != &other) {
            SinglyLinkedList tmp(other);
            swap(tmp);
        }
        return *this;
    }

    SinglyLinkedList& operator=(SinglyLinkedList&& other) noexcept {
        if (this != &other) {
            SinglyLinkedList tmp(std::move(other));
            swap(tmp);
        }
        return *this;
    }

    size_type size() const noexcept { return size_; }
    bool empty() const noexcept { return size_ == 0; }

    T& front() {
        if (empty()) throw std::out_of_range("SinglyLinkedList::front");
        return head_->value;
    }

    const T& front() const {
        if (empty()) throw std::out_of_range("SinglyLinkedList::front");
        return head_->value;
    }

    template<class... Args>
    T& emplace_front(Args&&... args) {
        Node* new_node = new Node(std::forward<Args>(args)...);
        new_node->next = head_;
        head_ = new_node;
        if (!tail_) {
            tail_ = new_node;
        }
        ++size_;
        return head_->value;
    }

    void push_front(const T& value) { emplace_front(value); }
    void push_front(T&& value) { emplace_front(std::move(value)); }

    template<class... Args>
    T& emplace_back(Args&&... args) {
        Node* new_node = new Node(std::forward<Args>(args)...);
        if (tail_) {
            tail_->next = new_node;
            tail_ = new_node;
        } else {
            head_ = new_node;
            tail_ = new_node;
        }
        ++size_;
        return tail_->value;
    }

    void push_back(const T& value) { emplace_back(value); }
    void push_back(T&& value) { emplace_back(std::move(value)); }

    void pop_front() {
        if (empty()) throw std::out_of_range("SinglyLinkedList::pop_front");
        Node* old = head_;
        head_ = head_->next;
        delete old;
        --size_;
        if (size_ == 0) {
            tail_ = nullptr;
        }
    }

    template<class Predicate>
    bool remove_first_if(Predicate&& pred) {
        if (!head_) return false;
        if (pred(head_->value)) {
            pop_front();
            return true;
        }
        Node* prev = head_;
        while (prev->next && !pred(prev->next->value)) {
            prev = prev->next;
        }
        if (prev->next) {
            Node* target = prev->next;
            prev->next = target->next;
            if (target == tail_) {
                tail_ = prev;
            }
            delete target;
            --size_;
            return true;
        }
        return false;
    }

    void clear() noexcept {
        while (head_) {
            Node* next = head_->next;
            delete head_;
            head_ = next;
        }
        tail_ = nullptr;
        size_ = 0;
    }

    void swap(SinglyLinkedList& other) noexcept {
        using std::swap;
        swap(head_, other.head_);
        swap(tail_, other.tail_);
        swap(size_, other.size_);
    }

    iterator begin() noexcept { return iterator(head_); }
    iterator end() noexcept { return iterator(nullptr); }
    const_iterator begin() const noexcept { return const_iterator(head_); }
    const_iterator end() const noexcept { return const_iterator(nullptr); }
    const_iterator cbegin() const noexcept { return const_iterator(head_); }
    const_iterator cend() const noexcept { return const_iterator(nullptr); }

    bool operator==(const SinglyLinkedList& other) const {
        if (size_ != other.size_) return false;
        auto it1 = cbegin();
        auto it2 = other.cbegin();
        while (it1 != cend() && it2 != other.cend()) {
            if (!(*it1 == *it2)) return false;
            ++it1;
            ++it2;
        }
        return true;
    }

    bool operator!=(const SinglyLinkedList& other) const {
        return !(*this == other);
    }
};

} // namespace internpath::ds
