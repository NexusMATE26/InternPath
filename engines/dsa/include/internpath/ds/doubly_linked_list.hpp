#pragma once
#include <cstddef>
#include <initializer_list>
#include <iterator>
#include <stdexcept>
#include <utility>

namespace internpath::ds {

template<class T>
class DoublyLinkedList {
private:
    struct NodeBase {
        NodeBase* prev = nullptr;
        NodeBase* next = nullptr;
    };

    struct Node : public NodeBase {
        T value;
        template<class... Args>
        explicit Node(Args&&... args) : value(std::forward<Args>(args)...) {}
    };

    NodeBase sentinel_;
    std::size_t size_ = 0;

    void init_sentinel() noexcept {
        sentinel_.prev = &sentinel_;
        sentinel_.next = &sentinel_;
        size_ = 0;
    }

    static Node* to_node(NodeBase* b) noexcept {
        return static_cast<Node*>(b);
    }

    static const Node* to_node(const NodeBase* b) noexcept {
        return static_cast<const Node*>(b);
    }

public:
    using size_type = std::size_t;
    using value_type = T;

    class const_iterator;

    class iterator {
    public:
        using iterator_category = std::bidirectional_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using pointer = T*;
        using reference = T&;

        iterator() = default;
        explicit iterator(NodeBase* node) : node_(node) {}

        reference operator*() const { return to_node(node_)->value; }
        pointer operator->() const { return &(to_node(node_)->value); }

        iterator& operator++() {
            node_ = node_->next;
            return *this;
        }

        iterator operator++(int) {
            iterator tmp = *this;
            node_ = node_->next;
            return tmp;
        }

        iterator& operator--() {
            node_ = node_->prev;
            return *this;
        }

        iterator operator--(int) {
            iterator tmp = *this;
            node_ = node_->prev;
            return tmp;
        }

        bool operator==(const iterator& other) const { return node_ == other.node_; }
        bool operator!=(const iterator& other) const { return node_ != other.node_; }

    private:
        friend class DoublyLinkedList;
        friend class const_iterator;
        NodeBase* node_ = nullptr;
    };

    class const_iterator {
    public:
        using iterator_category = std::bidirectional_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using pointer = const T*;
        using reference = const T&;

        const_iterator() = default;
        explicit const_iterator(const NodeBase* node) : node_(node) {}
        const_iterator(const iterator& it) : node_(it.node_) {}

        reference operator*() const { return to_node(node_)->value; }
        pointer operator->() const { return &(to_node(node_)->value); }

        const_iterator& operator++() {
            node_ = node_->next;
            return *this;
        }

        const_iterator operator++(int) {
            const_iterator tmp = *this;
            node_ = node_->next;
            return tmp;
        }

        const_iterator& operator--() {
            node_ = node_->prev;
            return *this;
        }

        const_iterator operator--(int) {
            const_iterator tmp = *this;
            node_ = node_->prev;
            return tmp;
        }

        bool operator==(const const_iterator& other) const { return node_ == other.node_; }
        bool operator!=(const const_iterator& other) const { return node_ != other.node_; }

    private:
        friend class DoublyLinkedList;
        const NodeBase* node_ = nullptr;
    };

    DoublyLinkedList() noexcept {
        init_sentinel();
    }

    DoublyLinkedList(std::initializer_list<T> items) : DoublyLinkedList() {
        try {
            for (const auto& item : items) {
                push_back(item);
            }
        } catch (...) {
            clear();
            throw;
        }
    }

    ~DoublyLinkedList() {
        clear();
    }

    DoublyLinkedList(const DoublyLinkedList& other) : DoublyLinkedList() {
        try {
            for (const auto& item : other) {
                push_back(item);
            }
        } catch (...) {
            clear();
            throw;
        }
    }

    DoublyLinkedList(DoublyLinkedList&& other) noexcept : DoublyLinkedList() {
        swap(other);
    }

    DoublyLinkedList& operator=(const DoublyLinkedList& other) {
        if (this != &other) {
            DoublyLinkedList tmp(other);
            swap(tmp);
        }
        return *this;
    }

    DoublyLinkedList& operator=(DoublyLinkedList&& other) noexcept {
        if (this != &other) {
            DoublyLinkedList tmp(std::move(other));
            swap(tmp);
        }
        return *this;
    }

    size_type size() const noexcept { return size_; }
    bool empty() const noexcept { return size_ == 0; }

    T& front() {
        if (empty()) throw std::out_of_range("DoublyLinkedList::front");
        return to_node(sentinel_.next)->value;
    }

    const T& front() const {
        if (empty()) throw std::out_of_range("DoublyLinkedList::front");
        return to_node(sentinel_.next)->value;
    }

    T& back() {
        if (empty()) throw std::out_of_range("DoublyLinkedList::back");
        return to_node(sentinel_.prev)->value;
    }

    const T& back() const {
        if (empty()) throw std::out_of_range("DoublyLinkedList::back");
        return to_node(sentinel_.prev)->value;
    }

    iterator begin() noexcept { return iterator(sentinel_.next); }
    iterator end() noexcept { return iterator(&sentinel_); }
    const_iterator begin() const noexcept { return const_iterator(sentinel_.next); }
    const_iterator end() const noexcept { return const_iterator(&sentinel_); }
    const_iterator cbegin() const noexcept { return const_iterator(sentinel_.next); }
    const_iterator cend() const noexcept { return const_iterator(&sentinel_); }

    template<class... Args>
    iterator emplace(const_iterator pos, Args&&... args) {
        NodeBase* target = const_cast<NodeBase*>(pos.node_);
        Node* new_node = new Node(std::forward<Args>(args)...);
        new_node->next = target;
        new_node->prev = target->prev;
        target->prev->next = new_node;
        target->prev = new_node;
        ++size_;
        return iterator(new_node);
    }

    iterator insert(const_iterator pos, const T& value) {
        return emplace(pos, value);
    }

    iterator insert(const_iterator pos, T&& value) {
        return emplace(pos, std::move(value));
    }

    iterator erase(const_iterator pos) {
        if (pos == cend()) {
            throw std::out_of_range("DoublyLinkedList::erase end() iterator");
        }
        NodeBase* target = const_cast<NodeBase*>(pos.node_);
        NodeBase* next_node = target->next;
        target->prev->next = target->next;
        target->next->prev = target->prev;
        delete to_node(target);
        --size_;
        return iterator(next_node);
    }

    template<class... Args>
    T& emplace_front(Args&&... args) {
        return *emplace(cbegin(), std::forward<Args>(args)...);
    }

    void push_front(const T& value) { emplace_front(value); }
    void push_front(T&& value) { emplace_front(std::move(value)); }

    template<class... Args>
    T& emplace_back(Args&&... args) {
        return *emplace(cend(), std::forward<Args>(args)...);
    }

    void push_back(const T& value) { emplace_back(value); }
    void push_back(T&& value) { emplace_back(std::move(value)); }

    void pop_front() {
        if (empty()) throw std::out_of_range("DoublyLinkedList::pop_front");
        erase(cbegin());
    }

    void pop_back() {
        if (empty()) throw std::out_of_range("DoublyLinkedList::pop_back");
        erase(const_iterator(sentinel_.prev));
    }

    void clear() noexcept {
        NodeBase* curr = sentinel_.next;
        while (curr != &sentinel_) {
            NodeBase* next = curr->next;
            delete to_node(curr);
            curr = next;
        }
        init_sentinel();
    }

    void swap(DoublyLinkedList& other) noexcept {
        if (this == &other) return;

        bool this_empty = empty();
        bool other_empty = other.empty();

        if (!this_empty && !other_empty) {
            NodeBase* this_first = sentinel_.next;
            NodeBase* this_last = sentinel_.prev;
            NodeBase* other_first = other.sentinel_.next;
            NodeBase* other_last = other.sentinel_.prev;

            sentinel_.next = other_first;
            sentinel_.prev = other_last;
            other_first->prev = &sentinel_;
            other_last->next = &sentinel_;

            other.sentinel_.next = this_first;
            other.sentinel_.prev = this_last;
            this_first->prev = &other.sentinel_;
            this_last->next = &other.sentinel_;
        } else if (this_empty && !other_empty) {
            sentinel_.next = other.sentinel_.next;
            sentinel_.prev = other.sentinel_.prev;
            sentinel_.next->prev = &sentinel_;
            sentinel_.prev->next = &sentinel_;
            other.sentinel_.next = &other.sentinel_;
            other.sentinel_.prev = &other.sentinel_;
        } else if (!this_empty && other_empty) {
            other.sentinel_.next = sentinel_.next;
            other.sentinel_.prev = sentinel_.prev;
            other.sentinel_.next->prev = &other.sentinel_;
            other.sentinel_.prev->next = &other.sentinel_;
            sentinel_.next = &sentinel_;
            sentinel_.prev = &sentinel_;
        }

        using std::swap;
        swap(size_, other.size_);
    }

    bool operator==(const DoublyLinkedList& other) const {
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

    bool operator!=(const DoublyLinkedList& other) const {
        return !(*this == other);
    }
};

} // namespace internpath::ds
